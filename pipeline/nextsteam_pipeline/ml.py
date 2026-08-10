from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from .models import Lane

QWEN_DIMENSIONS = (512, 768, 1024, 1536, 2560)


@dataclass(frozen=True)
class DeterministicEmbeddingAdapter:
    """Auditable lexical baseline used until a pinned learned model is selected."""

    dimensions: int = 64

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "kind": "embedding",
            "model": "deterministic-hashing-baseline",
            "revision": "1.0.0",
            "dimension": str(self.dimensions),
            "dtype": "float32",
            "offline_only": "true",
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        output = []
        for text in texts:
            vector = [0.0] * self.dimensions
            tokens = re.findall(r"[a-z0-9]+", text.casefold())
            for token in tokens:
                digest = hashlib.sha256(token.encode()).digest()
                for offset in range(0, 8, 2):
                    index = int.from_bytes(digest[offset : offset + 2]) % self.dimensions
                    vector[index] += 1.0 if digest[offset + 8] & 1 else -1.0
            if not tokens:
                vector[0] = 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            output.append([value / norm for value in vector])
        return output


@dataclass
class ModernBertClassifier:
    model_name: str
    revision: str
    labels: dict[Lane, tuple[str, ...]]
    batch_size: int = 16
    bf16: bool = False
    loader: Any = None

    def __post_init__(self) -> None:
        if not self.revision:
            raise ValueError("revision must be pinned")
        if self.loader is not None:
            self._tokenizer, self._model, self._torch = self.loader(self)
            return
        import torch  # type: ignore[import-not-found]
        from transformers import (  # type: ignore[import-not-found]
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        dtype = torch.bfloat16 if self.bf16 else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, revision=self.revision, local_files_only=True
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name, revision=self.revision, local_files_only=True, dtype=dtype
        )
        self._torch = torch

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "kind": "classifier",
            "model": self.model_name,
            "revision": self.revision,
            "dtype": "bfloat16" if self.bf16 else "float32",
            "batch_size": str(self.batch_size),
            "offline_only": "true",
        }

    def classify(self, texts: list[str], lane: Lane) -> list[dict[str, float]]:
        labels = self.labels[lane]
        output: list[dict[str, float]] = []
        for start in range(0, len(texts), self.batch_size):
            encoded = self._tokenizer(
                texts[start : start + self.batch_size],
                padding=True,
                truncation=True,
                return_tensors="pt",
            )
            with self._torch.inference_mode():
                logits = self._model(**encoded).logits.float().softmax(dim=-1).cpu().tolist()
            output.extend(dict(zip(labels, row, strict=True)) for row in logits)
        return output


@dataclass
class QwenEmbeddingAdapter:
    revision: str
    instruction: str
    dimensions: Literal[512, 768, 1024, 1536, "full"] = 1024
    batch_size: int = 16
    bf16: bool = False
    loader: Any = None
    model_name: str = "Qwen/Qwen3-Embedding-4B"

    def __post_init__(self) -> None:
        if (
            self.dimensions not in (*QWEN_DIMENSIONS[:-1], "full")
            or not self.revision
            or not self.instruction
        ):
            raise ValueError("pinned revision, instruction, and supported dimensions required")
        self._resolved_dimensions = 2560 if self.dimensions == "full" else self.dimensions
        if self.loader is not None:
            self._model = self.loader(self)
            return
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        model_kwargs = {"dtype": "bfloat16" if self.bf16 else "float32"}
        self._model = SentenceTransformer(
            self.model_name,
            revision=self.revision,
            local_files_only=True,
            trust_remote_code=False,
            truncate_dim=self._resolved_dimensions,
            model_kwargs=model_kwargs,
        )

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "kind": "embedding",
            "model": self.model_name,
            "revision": self.revision,
            "instruction": self.instruction,
            "dimension": str(self.dimensions),
            "dtype": "bfloat16" if self.bf16 else "float32",
            "batch_size": str(self.batch_size),
            "offline_only": "true",
        }

    def embed(self, texts: list[str]) -> list[list[float]]:
        prompted = [f"{self.instruction}\n{text}" for text in texts]
        values = self._model.encode(
            prompted,
            batch_size=self.batch_size,
            precision="float32",
            normalize_embeddings=True,
            truncate_dim=self._resolved_dimensions,
            convert_to_numpy=True,
        )
        return cast(list[list[float]], values.tolist())
