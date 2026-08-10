from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import polars as pl

from .acquisition import (
    SteamSpyClient,
    SteamStoreClient,
    acquire,
    game_from_dict,
    review_from_dict,
)
from .canonical import MAPPING_VERSION, canonicalize
from .evaluation import evaluate, graph_coverage
from .graph import build_candidate_graph
from .ml import DeterministicEmbeddingAdapter
from .models import (
    CanonicalGame,
    Edge,
    InterpretedEvidence,
    Provenance,
    RawGame,
    ReviewEvidence,
    StageManifest,
)
from .semantics import DeterministicBaseline, SemanticAdapter
from .storage import publish
from .util import atomic_json, checksum, read_json, stable_id


def _cached_stage(
    workdir: Path,
    name: str,
    build: Any,
    load: Any,
    input_fingerprint: str = "standalone",
) -> Any:
    manifest_path = workdir / "stages" / f"{name}.json"
    data_path = workdir / "stages" / f"{name}.data.json"
    expected_input = hashlib.sha256(input_fingerprint.encode()).hexdigest()
    if manifest_path.exists() and data_path.exists():
        saved = read_json(manifest_path)
        valid_input = saved["input_checksums"].get("fingerprint") == expected_input
        valid_output = saved["output_checksums"].get(data_path.name) == checksum(data_path)
        if saved["status"] == "complete" and valid_input and valid_output:
            return load(read_json(data_path))
    stage = StageManifest(name, "1.0.0", "running", input_checksums={"fingerprint": expected_input})
    atomic_json(manifest_path, stage)
    try:
        value, rows = build()
        atomic_json(data_path, rows)
        stage.status = "complete"
        stage.output_checksums[data_path.name] = checksum(data_path)
        stage.counts["records"] = len(rows) if isinstance(rows, list) else 1
        atomic_json(manifest_path, stage)
        return value
    except BaseException as error:
        stage.status = "failed"
        stage.metadata["error"] = f"{type(error).__name__}: {error}"
        atomic_json(manifest_path, stage)
        raise


def run_pipeline(
    appids: list[int],
    workdir: Path,
    output: Path,
    adapter: SemanticAdapter | None = None,
    embedder: Any | None = None,
    *,
    source_git_sha: str = "unknown",
    pipeline_git_sha: str = "unknown",
) -> Path:
    if not appids:
        raise ValueError("at least one appid required")
    if len(set(appids)) != len(appids):
        raise ValueError("appids must be unique")
    workdir.mkdir(parents=True, exist_ok=True)
    acquire_manifest = workdir / "stages" / "acquire.json"
    stage = StageManifest("acquire", "1.0.0", "running", counts={"requested": len(appids)})
    atomic_json(acquire_manifest, stage)
    try:
        games, reviews = acquire(
            appids, SteamStoreClient(), SteamSpyClient(), workdir / "acquisition-state.json"
        )
        stage.status = "complete"
        stage.counts.update(games=len(games), reviews=len(reviews))
        atomic_json(acquire_manifest, stage)
    except BaseException as error:
        stage.status = "failed"
        stage.metadata["error"] = f"{type(error).__name__}: {error}"
        atomic_json(acquire_manifest, stage)
        raise
    return _run_acquired_pipeline(
        games,
        reviews,
        workdir,
        output,
        adapter,
        embedder,
        source_git_sha=source_git_sha,
        pipeline_git_sha=pipeline_git_sha,
        acquisition_kind="upstream_live",
    )


def run_compacted_pipeline(
    compacted: Path,
    workdir: Path,
    output: Path,
    adapter: SemanticAdapter | None = None,
    embedder: Any | None = None,
    *,
    source_git_sha: str = "unknown",
    pipeline_git_sha: str = "unknown",
) -> Path:
    games_path = compacted / "games.parquet"
    reviews_path = compacted / "reviews.parquet"
    manifest_path = compacted / "compaction-manifest.json"
    if not all(path.is_file() for path in (games_path, reviews_path, manifest_path)):
        raise FileNotFoundError("compacted input requires games, reviews, and compaction manifest")
    manifest = read_json(manifest_path)
    expected = manifest.get("checksums", {})
    actual = {"games.parquet": checksum(games_path), "reviews.parquet": checksum(reviews_path)}
    if expected != actual:
        raise ValueError("compacted input checksum mismatch")
    games = [game_from_dict(row) for row in pl.read_parquet(games_path).to_dicts()]
    reviews = [review_from_dict(row) for row in pl.read_parquet(reviews_path).to_dicts()]
    if manifest.get("games") != len(games) or manifest.get("reviews") != len(reviews):
        raise ValueError("compacted input count mismatch")
    workdir.mkdir(parents=True, exist_ok=True)
    atomic_json(
        workdir / "stages" / "load-compacted.json",
        StageManifest(
            "load-compacted",
            "1.0.0",
            "complete",
            input_checksums={**actual, "compaction-manifest.json": checksum(manifest_path)},
            counts={"games": len(games), "reviews": len(reviews)},
        ),
    )
    return _run_acquired_pipeline(
        games,
        reviews,
        workdir,
        output,
        adapter,
        embedder,
        source_git_sha=source_git_sha,
        pipeline_git_sha=pipeline_git_sha,
        acquisition_kind="compacted_scale",
    )


def _run_acquired_pipeline(
    games: list[RawGame],
    reviews: list[ReviewEvidence],
    workdir: Path,
    output: Path,
    adapter: SemanticAdapter | None,
    embedder: Any | None,
    *,
    source_git_sha: str,
    pipeline_git_sha: str,
    acquisition_kind: str,
) -> Path:
    if not games:
        raise ValueError("acquisition produced no eligible games")
    semantic = adapter or DeterministicBaseline()
    vectorizer = embedder or DeterministicEmbeddingAdapter()
    interpreted = _cached_stage(
        workdir,
        "interpret",
        lambda: _interpret(games, reviews, semantic),
        _load_interpreted,
        repr(
            (
                [asdict(game) for game in games],
                [asdict(review) for review in reviews],
                semantic.metadata,
            )
        ),
    )
    canonical = _cached_stage(
        workdir,
        "canonicalize",
        lambda: _canonical(games, interpreted),
        load_canonical,
        repr([asdict(item) for item in interpreted]),
    )
    edges = _cached_stage(
        workdir,
        "graph",
        lambda: _graph(canonical),
        _load_edges,
        repr([asdict(item) for item in canonical]),
    )
    evaluation = evaluate(canonical, edges, {"graph_coverage": graph_coverage})
    fetched = [item.fetched_at for game in games for item in game.provenance]
    provenance = {
        "source_git_sha": source_git_sha,
        "pipeline_git_sha": pipeline_git_sha,
        "acquisition_windows": {
            "started_at": min(fetched),
            "ended_at": max(fetched),
            "kind": acquisition_kind,
        },
        "models": [semantic.metadata, vectorizer.metadata],
        "ontology_version": MAPPING_VERSION,
        "scorer_version": "candidate-jaccard-v1",
        "evaluation_report_id": stable_id("evaluation", sorted(evaluation.items())),
    }
    return cast(
        Path,
        _cached_stage(
            workdir,
            "publish",
            lambda: _publish(
                output, games, reviews, interpreted, canonical, edges, provenance, vectorizer
            ),
            lambda row: Path(row["release"]),
            repr(
                (
                    [asdict(item) for item in edges],
                    provenance,
                    vectorizer.metadata,
                    str(output.resolve()),
                )
            ),
        ),
    )


def _interpret(
    games: list[RawGame], reviews: list[ReviewEvidence], adapter: SemanticAdapter
) -> tuple[list[InterpretedEvidence], list[dict[str, Any]]]:
    values = [
        item
        for game in games
        for item in adapter.interpret(
            game, [review for review in reviews if review.appid == game.appid]
        )
    ]
    return values, [asdict(item) for item in values]


def _canonical(
    games: list[RawGame], evidence: list[InterpretedEvidence]
) -> tuple[list[CanonicalGame], list[dict[str, Any]]]:
    values = [
        canonicalize(game, [item for item in evidence if item.appid == game.appid])
        for game in games
    ]
    return values, [asdict(item) for item in values]


def _graph(games: list[CanonicalGame]) -> tuple[list[Edge], list[dict[str, Any]]]:
    values = build_candidate_graph(games)
    return values, [asdict(item) for item in values]


def _publish(
    output: Path,
    games: list[RawGame],
    reviews: list[ReviewEvidence],
    interpreted: list[InterpretedEvidence],
    canonical: list[CanonicalGame],
    edges: list[Edge],
    provenance: dict[str, Any],
    embedder: Any,
) -> tuple[Path, dict[str, str]]:
    release = publish(output, games, reviews, interpreted, canonical, edges, provenance, embedder)
    return release, {"release": str(release)}


def _load_interpreted(rows: list[dict[str, Any]]) -> list[InterpretedEvidence]:
    return [
        InterpretedEvidence(**{**row, "source_evidence_ids": tuple(row["source_evidence_ids"])})
        for row in rows
    ]


def load_canonical(rows: list[dict[str, Any]]) -> list[CanonicalGame]:
    return [
        CanonicalGame(
            **{
                **row,
                "lanes": {k: tuple(v) for k, v in row["lanes"].items()},
                "lane_evidence_ids": {k: tuple(v) for k, v in row["lane_evidence_ids"].items()},
                "evidence_ids": tuple(row["evidence_ids"]),
            }
        )
        for row in rows
    ]


def _load_edges(rows: list[dict[str, Any]]) -> list[Edge]:
    return [
        Edge(
            **{
                **row,
                "reasons": tuple(row["reasons"]),
                "matched_concepts": {k: tuple(v) for k, v in row["matched_concepts"].items()},
                "evidence_ids": tuple(row["evidence_ids"]),
            }
        )
        for row in rows
    ]


def publish_fixture(output: Path) -> Path:
    if output.name in {"production", "releases"}:
        raise ValueError("fixture output must be isolated from production")
    now = "2026-01-01T00:00:00+00:00"
    provenance = Provenance(
        "test_fixture", "fixture-v1", now, "https://example.invalid/nextsteam-fixture", "0" * 64
    )
    games = [
        RawGame(
            900001,
            "Fixture Forge",
            "Cozy crafting space co-op",
            ("Crafting",),
            ("Co-op",),
            "Fixture Studio",
            "Fixture Publisher",
            90,
            10,
            "1000 .. 2000",
            (provenance,),
            2026,
            "https://example.invalid/forge.jpg",
        ),
        RawGame(
            900002,
            "Fixture Quest",
            "Relaxing building galaxy cooperative",
            ("Building",),
            ("Co-op",),
            "Fixture Studio",
            "Fixture Publisher",
            80,
            20,
            "1200 .. 2200",
            (provenance,),
            2026,
            "https://example.invalid/quest.jpg",
        ),
    ]
    reviews = [
        ReviewEvidence(
            stable_id("review", game.appid, "fixture"),
            game.appid,
            "fixture",
            "Challenging solo mystery combat",
            True,
            60,
            provenance,
        )
        for game in games
    ]
    model = DeterministicBaseline()
    vectorizer = DeterministicEmbeddingAdapter()
    interpreted = [
        item
        for game in games
        for item in model.interpret(
            game, [review for review in reviews if review.appid == game.appid]
        )
    ]
    canonical = [
        canonicalize(game, [item for item in interpreted if item.appid == game.appid])
        for game in games
    ]
    edges = build_candidate_graph(canonical)
    return publish(
        output,
        games,
        reviews,
        interpreted,
        canonical,
        edges,
        {
            "build_id": "synthetic-fixture-v1",
            "created_at": now,
            "source_git_sha": "test-fixture",
            "pipeline_git_sha": "test-fixture",
            "acquisition_windows": {"started_at": now, "ended_at": now, "kind": "test_fixture"},
            "models": [model.metadata, vectorizer.metadata],
            "ontology_version": MAPPING_VERSION,
            "scorer_version": "candidate-jaccard-v1",
            "evaluation_report_id": "evaluation_fixture_v1",
        },
        vectorizer,
    )
