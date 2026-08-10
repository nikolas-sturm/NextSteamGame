from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Protocol


class VectorIndex(Protocol):
    def upsert(
        self, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, str]]
    ) -> None: ...

    def query(self, vector: list[float], limit: int) -> list[tuple[str, float]]: ...


class ZvecIndex:
    """Persistent Zvec boundary isolated from semantic and ranking policy."""

    def __init__(
        self,
        path: Path,
        dimensions: int,
        index_kind: Literal["flat", "hnsw"] = "hnsw",
        dtype: Literal["fp32", "fp16"] = "fp32",
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        try:
            import zvec
        except ImportError as error:
            raise RuntimeError("Install nextsteam-pipeline[zvec] to use Zvec") from error

        self._zvec: Any = zvec
        self._dimensions = dimensions
        if path.exists():
            self._collection: Any = zvec.open(str(path))
            return

        index_param = zvec.FlatIndexParam() if index_kind == "flat" else zvec.HnswIndexParam()
        data_type = zvec.DataType.VECTOR_FP32
        if dtype == "fp16":
            if not hasattr(zvec.DataType, "VECTOR_FP16"):
                raise ValueError("installed Zvec does not support FP16 vectors")
            data_type = zvec.DataType.VECTOR_FP16
        self.config = {"index_kind": index_kind, "dtype": dtype, "dimensions": dimensions}
        schema = zvec.CollectionSchema(
            name="nextsteam_vectors",
            fields=[zvec.FieldSchema("metadata_json", zvec.DataType.STRING, nullable=False)],
            vectors=[
                zvec.VectorSchema(
                    "embedding",
                    data_type,
                    dimension=dimensions,
                    index_param=index_param,
                )
            ],
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._collection = zvec.create_and_open(str(path), schema=schema)

    def upsert(
        self, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, str]]
    ) -> None:
        if not (len(ids) == len(vectors) == len(metadata)):
            raise ValueError("ids, vectors, and metadata must have equal lengths")
        if len(set(ids)) != len(ids):
            raise ValueError("ids must be unique within a batch")
        if any(len(vector) != self._dimensions for vector in vectors):
            raise ValueError(f"all vectors must have {self._dimensions} dimensions")
        docs = [
            self._zvec.Doc(
                id=item_id,
                fields={"metadata_json": json.dumps(fields, sort_keys=True)},
                vectors={"embedding": vector},
            )
            for item_id, vector, fields in zip(ids, vectors, metadata, strict=True)
        ]
        self._collection.upsert(docs)
        self._collection.flush()

    def close(self) -> None:
        """Release native collection lock before opening collection elsewhere."""
        collection = self._collection
        self._collection = None
        del collection

    def query(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        if len(vector) != self._dimensions:
            raise ValueError(f"query vector must have {self._dimensions} dimensions")
        if limit <= 0:
            raise ValueError("limit must be positive")
        docs = self._collection.query(
            self._zvec.Query(field_name="embedding", vector=vector), topk=limit
        )
        return [(str(doc.id), float(doc.score)) for doc in docs]


def build_lane_indexes(
    root: Path,
    records: list[dict[str, Any]],
    embedder: Any,
    factory: Any = ZvecIndex,
    index_kind: Literal["flat", "hnsw"] = "hnsw",
) -> dict[str, Any]:
    from .models import LANES

    root.mkdir(parents=True, exist_ok=True)
    configuration: dict[str, Any] = {"model": embedder.metadata, "lanes": {}}
    for lane in LANES:
        lane_records = [record for record in records if record["lane"] == lane]
        texts = [str(record["text"]) for record in lane_records]
        if not texts:
            continue
        vectors = embedder.embed(texts)
        index = factory(root / lane, len(vectors[0]), index_kind=index_kind)
        index.upsert(
            [str(record["id"]) for record in lane_records],
            vectors,
            [{"lane": lane, "appid": str(record["appid"])} for record in lane_records],
        )
        index.close()
        configuration["lanes"][lane] = {
            "count": len(vectors),
            "dimensions": len(vectors[0]),
            "index_kind": index_kind,
            "dtype": "fp32",
        }
    (root / "config.json").write_text(json.dumps(configuration, indent=2, sort_keys=True) + "\n")
    return configuration
