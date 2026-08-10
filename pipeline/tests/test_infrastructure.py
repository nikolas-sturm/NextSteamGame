from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_pipeline import SyntheticTransport

from nextsteam_pipeline.acquisition import RateLimiter, SteamSpyClient, SteamStoreClient, acquire
from nextsteam_pipeline.audit import ArtifactAuditError, audit_build
from nextsteam_pipeline.benchmark import benchmark_embeddings, benchmark_indexes, synthetic_vectors
from nextsteam_pipeline.discovery import (
    CatalogEntry,
    Eligibility,
    discover_catalog,
    select_slice,
    write_catalog,
)
from nextsteam_pipeline.evaluation import candidate_graph_size_report
from nextsteam_pipeline.ml import QwenEmbeddingAdapter
from nextsteam_pipeline.models import LANES, Provenance
from nextsteam_pipeline.runner import publish_fixture, run_compacted_pipeline
from nextsteam_pipeline.scale import acquire_shards, acquire_until_target, compact_shards
from nextsteam_pipeline.vector import build_lane_indexes


class CatalogClient:
    def catalog_page(self, page: int) -> tuple[dict[str, dict[str, Any]], Provenance]:
        payload = {
            str(page * 10 + 2): {
                "appid": page * 10 + 2,
                "name": "Eligible",
                "owners": "1,000 .. 2,000",
                "positive": 9,
                "negative": 1,
            },
            str(page * 10 + 1): {
                "appid": page * 10 + 1,
                "name": "",
                "owners": 0,
                "positive": 0,
                "negative": 0,
            },
        }
        return payload, Provenance(
            "SteamSpyClient",
            str(page),
            "2026-01-01T00:00:00Z",
            f"https://steamspy.invalid?page={page}",
            str(page) * 64,
        )


def test_catalog_discovery_filters_sorts_and_writes_manifest(tmp_path: Path) -> None:
    entries, provenance = discover_catalog(CatalogClient(), 2, Eligibility(100, 5))  # type: ignore[arg-type]
    assert [entry.appid for entry in entries] == [2, 12]
    appids, manifest = write_catalog(tmp_path, entries, provenance, Eligibility(100, 5))
    assert appids.read_text() == "2\n12\n"
    catalog = tmp_path / "catalog.parquet"
    published = json.loads(manifest.read_text())
    assert published["source"] == "SteamSpy request=all"
    assert catalog.is_file()
    assert published["catalog_parquet_sha256"]


class MissingTransport(SyntheticTransport):
    def get(self, url: str, *, params: dict[str, object]) -> Any:
        appid = int(params.get("appid", params.get("appids", 0)))
        if appid == 404 and "appdetails" in url:
            import httpx

            return httpx.Response(
                200, json={"404": {"success": False}}, request=httpx.Request("GET", url)
            )
        return super().get(url, params=params)


def test_acquisition_records_typed_skip_and_resume(tmp_path: Path) -> None:
    transport = MissingTransport()
    store = SteamStoreClient(transport, RateLimiter(1000, sleep=lambda _: None))
    spy = SteamSpyClient(transport, RateLimiter(1000, sleep=lambda _: None))
    games, _ = acquire([101, 404], store, spy, tmp_path / "state.json")
    state = json.loads((tmp_path / "state.json").read_text())
    assert [game.appid for game in games] == [101]
    assert state["completed"] == [101, 404]
    assert state["skips"][0]["type"] == "MissingApp"


def test_shards_compact_deterministically(tmp_path: Path) -> None:
    transport = SyntheticTransport()
    store = SteamStoreClient(transport, RateLimiter(1000, sleep=lambda _: None))
    spy = SteamSpyClient(transport, RateLimiter(1000, sleep=lambda _: None))
    shards = acquire_shards([3, 1, 2], tmp_path / "work", 2, store=store, spy=spy)
    compacted = tmp_path / "compact"
    report = compact_shards(shards, compacted)
    release = run_compacted_pipeline(
        compacted,
        tmp_path / "build-work",
        tmp_path / "builds",
        source_git_sha="test",
        pipeline_git_sha="test",
    )
    assert report["games"] == 3
    assert audit_build(release)["integrity"]["status"] == "passed"
    assert len(shards) == 2
    assert all(
        json.loads((shard / "manifest.json").read_text())["status"] == "complete"
        for shard in shards
    )


def test_scale_target_backfills_skips_and_compacts_exact_count(tmp_path: Path) -> None:
    transport = MissingTransport()
    store = SteamStoreClient(transport, RateLimiter(1000, sleep=lambda _: None))
    spy = SteamSpyClient(transport, RateLimiter(1000, sleep=lambda _: None))

    shards = acquire_until_target([404, 1, 2, 3], 3, tmp_path / "work", 3, store=store, spy=spy)
    report = compact_shards(shards, tmp_path / "compact", max_games=3)

    assert len(shards) == 2
    assert report["games"] == 3


class Matrix(list[list[float]]):
    def tolist(self) -> list[list[float]]:
        return list(self)


class FakeEmbeddingModel:
    def encode(self, texts: list[str], **kwargs: object) -> Matrix:
        dimensions = int(kwargs["truncate_dim"])
        return Matrix([[float(index + 1)] * dimensions for index, _ in enumerate(texts)])


def test_qwen_adapter_metadata_dimensions_and_no_download() -> None:
    adapter = QwenEmbeddingAdapter(
        "pinned-sha", "Represent game", 512, 2, loader=lambda _: FakeEmbeddingModel()
    )
    vectors = adapter.embed(["one", "two"])
    assert len(vectors[0]) == 512
    assert adapter.metadata["revision"] == "pinned-sha"
    assert adapter.metadata["offline_only"] == "true"


class FakeIndex:
    def __init__(self, *_: object, **__: object) -> None:
        self.vectors: list[list[float]] = []
        self.ids: list[str] = []

    def upsert(
        self, ids: list[str], vectors: list[list[float]], metadata: list[dict[str, str]]
    ) -> None:
        self.ids, self.vectors = ids, vectors

    def query(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        scored = [
            (item_id, sum(a * b for a, b in zip(vector, candidate, strict=True)))
            for item_id, candidate in zip(self.ids, self.vectors, strict=True)
        ]
        return sorted(scored, key=lambda item: (-item[1], item[0]))[:limit]

    def close(self) -> None:
        pass


def test_benchmarks_measure_fake_adapters_without_claims() -> None:
    adapter = QwenEmbeddingAdapter("sha", "Represent", 512, loader=lambda _: FakeEmbeddingModel())
    embedding = benchmark_embeddings(adapter, ["a", "b"], memory_bytes=lambda: 10)
    reports = benchmark_indexes(
        lambda *_: FakeIndex(), synthetic_vectors(20, 8), synthetic_vectors(3, 8, 9), 5
    )
    assert embedding["items"] == 2 and embedding["vram_bytes_delta"] == 0
    assert {(report["kind"], report["dtype"]) for report in reports} == {
        ("flat", "fp32"),
        ("hnsw", "fp32"),
    }
    assert all(0 <= report["recall_at_k"] <= 1 for report in reports)


def test_builds_one_index_per_lane(tmp_path: Path) -> None:
    created: list[FakeIndex] = []

    def factory(*args: object, **kwargs: object) -> FakeIndex:
        index = FakeIndex()
        created.append(index)
        return index

    records = [{"id": f"e-{lane}", "appid": 1, "lane": lane, "text": lane} for lane in LANES]
    adapter = QwenEmbeddingAdapter("sha", "Represent", 512, loader=lambda _: FakeEmbeddingModel())
    config = build_lane_indexes(tmp_path, records, adapter, factory)
    assert set(config["lanes"]) == set(LANES)
    assert len(created) == 4


def test_artifact_audit_verifies_integrity_and_semantic_coverage(tmp_path: Path) -> None:
    release = publish_fixture(tmp_path / "builds")

    report = audit_build(release)

    assert report["integrity"]["status"] == "passed"
    assert report["coverage"]["graph_source_ratio"] == 1.0
    assert set(report["coverage"]["lane_evidence"]) == set(LANES)

    metadata = release / "metadata.json"
    metadata.write_text(metadata.read_text() + " ")
    try:
        audit_build(release)
    except ArtifactAuditError as error:
        assert "checksum mismatch" in str(error)
    else:
        raise AssertionError("tampered artifact passed audit")


def test_candidate_graph_sizes_report_actual_not_claimed() -> None:
    report = candidate_graph_size_report([], lambda _: [], (500, 1000, 2000))
    assert [row["requested_games"] for row in report["reports"]] == [500, 1000, 2000]  # type: ignore[index]
    assert all(row["actual_games"] == 0 for row in report["reports"])  # type: ignore[union-attr]
    assert all(row["recall_at_k"] == 1.0 for row in report["reports"])  # type: ignore[union-attr]


def test_select_slice_is_deterministic_unique_and_covers_popularity(tmp_path: Path) -> None:
    entries = [
        CatalogEntry(
            appid=index,
            name=f"Synthetic catalog {index}",
            owners=index * 100,
            positive=index * 3,
            negative=index,
        )
        for index in range(1, 801)
    ]
    provenance = [
        Provenance(
            "SteamSpyClient",
            "0",
            "2026-01-01T00:00:00Z",
            "https://steamspy.invalid?page=0",
            "a" * 64,
        )
    ]
    write_catalog(tmp_path / "catalog", entries, provenance, Eligibility())
    first, first_manifest = select_slice(
        tmp_path / "catalog/catalog.parquet", tmp_path / "first", 200, "stable-seed"
    )
    second, _ = select_slice(
        tmp_path / "catalog/catalog.parquet", tmp_path / "second", 200, "stable-seed"
    )
    selected = [int(value) for value in first.read_text().splitlines()]
    assert first.read_bytes() == second.read_bytes()
    assert len(selected) == len(set(selected)) == 200
    assert any(appid <= 200 for appid in selected)
    assert any(appid > 600 for appid in selected)
    manifest = json.loads(first_manifest.read_text())
    assert manifest["selected_count"] == 200
    assert manifest["semantic_diversity"]["status"] == "not_assessed"
    assert manifest["strata_counts"]
