from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .util import atomic_json


class Embedder(Protocol):
    @property
    def metadata(self) -> dict[str, str]: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def synthetic_vectors(count: int, dimensions: int, seed: int = 7) -> list[list[float]]:
    generator = random.Random(seed)
    return [[generator.uniform(-1.0, 1.0) for _ in range(dimensions)] for _ in range(count)]


def exhaustive(vector: list[float], vectors: list[list[float]], limit: int) -> list[int]:
    scored = [
        (index, sum(a * b for a, b in zip(vector, candidate, strict=True)))
        for index, candidate in enumerate(vectors)
    ]
    return [index for index, _ in sorted(scored, key=lambda item: (-item[1], item[0]))[:limit]]


def benchmark_embeddings(
    adapter: Embedder, texts: list[str], memory_bytes: Callable[[], int] | None = None
) -> dict[str, Any]:
    before = memory_bytes() if memory_bytes else None
    started = time.perf_counter()
    vectors = adapter.embed(texts)
    elapsed = time.perf_counter() - started
    after = memory_bytes() if memory_bytes else None
    return {
        "kind": "embedding",
        "model": adapter.metadata,
        "items": len(texts),
        "dimensions": len(vectors[0]) if vectors else 0,
        "elapsed_seconds": elapsed,
        "items_per_second": len(texts) / elapsed if elapsed else math.inf,
        "vram_bytes_delta": None if before is None or after is None else after - before,
    }


def benchmark_indexes(
    factory: Callable[[str, str, int], Any],
    vectors: list[list[float]],
    queries: list[list[float]],
    limit: int = 10,
    include_fp16: bool = False,
) -> list[dict[str, Any]]:
    configurations = [("flat", "fp32"), ("hnsw", "fp32")]
    if include_fp16:
        configurations.extend((("flat", "fp16"), ("hnsw", "fp16")))
    truth = [set(exhaustive(query, vectors, limit)) for query in queries]
    reports = []
    for kind, dtype in configurations:
        index = factory(kind, dtype, len(vectors[0]))
        started = time.perf_counter()
        index.upsert([str(i) for i in range(len(vectors))], vectors, [{} for _ in vectors])
        build_seconds = time.perf_counter() - started
        started = time.perf_counter()
        actual = [{int(item_id) for item_id, _ in index.query(query, limit)} for query in queries]
        query_seconds = time.perf_counter() - started
        index.close()
        recall = sum(
            len(expected & found) / len(expected)
            for expected, found in zip(truth, actual, strict=True)
        ) / len(truth)
        reports.append(
            {
                "kind": kind,
                "dtype": dtype,
                "vectors": len(vectors),
                "dimensions": len(vectors[0]),
                "queries": len(queries),
                "build_seconds": build_seconds,
                "query_seconds": query_seconds,
                "recall_at_k": recall,
                "k": limit,
            }
        )
    return reports


def write_report(path: Path, report: Any) -> None:
    atomic_json(path, report)
