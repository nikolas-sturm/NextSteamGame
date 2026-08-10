from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from .canonical import MAPPING_VERSION
from .models import LANES, CanonicalGame, Edge, InterpretedEvidence, RawGame, ReviewEvidence
from .util import atomic_json, checksum, stable_id


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path, compression="zstd", use_pyarrow=True)


def validate_parquet(path: Path, expected_rows: int) -> None:
    database = duckdb.connect()
    try:
        actual = database.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()
    finally:
        database.close()
    if actual is None or actual[0] != expected_rows:
        raise ValueError(f"{path}: expected {expected_rows} rows, found {actual}")


def game_record(game: CanonicalGame) -> dict[str, Any]:
    return {
        key: getattr(game, key)
        for key in (
            "appid",
            "name",
            "short_description",
            "release_year",
            "header_image_url",
            "steam_url",
        )
    }


def publish(
    root: Path,
    games: list[RawGame],
    reviews: list[ReviewEvidence],
    interpreted: list[InterpretedEvidence],
    canonical: list[CanonicalGame],
    edges: list[Edge],
    provenance: dict[str, Any],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    created_at = str(provenance.get("created_at", datetime.now(UTC).isoformat()))
    build_id = str(provenance.get("build_id", stable_id("build", created_at, len(games))))
    final = root / "releases" / build_id
    if final.exists():
        raise FileExistsError(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{build_id}.", dir=final.parent))
    identity = [
        {"appid": game.appid, "developer": game.developer, "publisher": game.publisher}
        for game in canonical
    ]
    explanation = [
        {
            "id": item.evidence_id,
            "appid": item.appid,
            "source": item.model["name"],
            "excerpt": item.excerpt[:500],
            "lane": item.lane,
            "concept": item.value,
            "source_evidence_ids": list(item.source_evidence_ids),
        }
        for item in interpreted
    ]
    edge_rows = [asdict(edge) for edge in edges]
    files = {
        "source/games.parquet": [asdict(item) for item in games],
        "source/reviews.parquet": [asdict(item) for item in reviews],
        "source/identity.parquet": identity,
        "source/candidate_edges.parquet": edge_rows,
        "source/explanation_evidence.parquet": explanation,
    }
    for relative, rows in files.items():
        path = temporary / relative
        write_parquet(path, rows)
        validate_parquet(path, len(rows))
    game_rows: list[dict[str, Any]] = [game_record(game) for game in canonical]
    metadata: dict[str, Any] = {"build_id": build_id, "games": game_rows}
    grouped = []
    for game in sorted(canonical, key=lambda item: item.appid):
        candidates = [
            {
                "appid": edge.target_appid,
                "lane_similarities": edge.lane_similarities,
                "matched_concepts": edge.matched_concepts,
                "evidence_ids": list(edge.evidence_ids),
                "features": edge.features,
            }
            for edge in edges
            if edge.source_appid == game.appid
        ]
        grouped.append({"source_appid": game.appid, "candidates": candidates})
    evidence = {
        "build_id": build_id,
        "evidence": [
            {key: row[key] for key in ("id", "appid", "source", "excerpt")} for row in explanation
        ],
    }
    atomic_json(temporary / "metadata.json", metadata)
    atomic_json(
        temporary / "graph.json", {"build_id": build_id, "lanes": list(LANES), "records": grouped}
    )
    atomic_json(temporary / "evidence.json", evidence)
    database = sqlite3.connect(temporary / "metadata.sqlite")
    try:
        database.execute(
            "CREATE TABLE games (appid INTEGER PRIMARY KEY, name TEXT, "
            "short_description TEXT, release_year INTEGER, header_image_url TEXT, steam_url TEXT)"
        )
        database.executemany(
            "INSERT INTO games VALUES "
            "(:appid, :name, :short_description, :release_year, :header_image_url, :steam_url)",
            game_rows,
        )
        database.commit()
    finally:
        database.close()
    checksums = {
        path.relative_to(temporary).as_posix(): checksum(path)
        for path in sorted(temporary.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "build_id": build_id,
        "created_at": created_at,
        "artifact_schema_version": 1,
        "api_compatibility_version": 1,
        "source_git_sha": str(provenance["source_git_sha"]),
        "pipeline_git_sha": str(provenance["pipeline_git_sha"]),
        "acquisition_windows": provenance["acquisition_windows"],
        "models": provenance["models"],
        "ontology_version": str(provenance.get("ontology_version", MAPPING_VERSION)),
        "scorer_version": str(provenance.get("scorer_version", "candidate-jaccard-v1")),
        "counts": {"games": len(canonical), "edges": len(edges), "evidence": len(interpreted)},
        "checksums": checksums,
        "evaluation_report_id": str(provenance["evaluation_report_id"]),
    }
    atomic_json(temporary / "manifest.json", manifest)
    temporary.rename(final)
    atomic_json(root / "CURRENT.json", {"build_id": build_id})
    return final
