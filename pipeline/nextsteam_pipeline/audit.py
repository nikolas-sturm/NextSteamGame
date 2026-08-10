from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import polars as pl

from .models import LANES
from .util import checksum


class ArtifactAuditError(ValueError):
    pass


def _object(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ArtifactAuditError(f"{path.name} must contain a JSON object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ArtifactAuditError(f"{field} must be a list")
    return value


def _unique_ids(rows: list[Any], field: str, label: str) -> set[Any]:
    values = [row[field] for row in rows]
    if len(values) != len(set(values)):
        raise ArtifactAuditError(f"duplicate {label}")
    return set(values)


def audit_build(build: Path) -> dict[str, Any]:
    root = build.resolve(strict=True)
    manifest = _object(root / "manifest.json")
    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict) or not checksums:
        raise ArtifactAuditError("manifest checksums must be a non-empty object")
    for name, expected in checksums.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactAuditError(f"unsafe checksum path: {name}")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ArtifactAuditError(f"unsafe checksum path: {name}")
        if checksum(path) != expected:
            raise ArtifactAuditError(f"checksum mismatch: {name}")

    metadata = _object(root / "metadata.json")
    graph = _object(root / "graph.json")
    evidence = _object(root / "evidence.json")
    build_id = manifest.get("build_id")
    if any(value.get("build_id") != build_id for value in (metadata, graph, evidence)):
        raise ArtifactAuditError("runtime files do not share manifest build_id")
    if graph.get("lanes") != list(LANES):
        raise ArtifactAuditError("graph lanes do not match supported lanes")

    games = _list(metadata.get("games"), "metadata.games")
    evidence_rows = _list(evidence.get("evidence"), "evidence.evidence")
    records = _list(graph.get("records"), "graph.records")
    game_ids = _unique_ids(games, "appid", "game appid")
    evidence_ids = _unique_ids(evidence_rows, "id", "evidence id")
    source_ids = _unique_ids(records, "source_appid", "graph source")
    if not source_ids.issubset(game_ids):
        raise ArtifactAuditError("graph contains unknown source appid")

    degrees: list[int] = []
    referenced_evidence: set[str] = set()
    lane_edges: Counter[str] = Counter({lane: 0 for lane in LANES})
    edge_count = 0
    for record in records:
        candidates = _list(record.get("candidates"), "graph.records[].candidates")
        candidate_ids = _unique_ids(candidates, "appid", "candidate appid")
        if not candidate_ids.issubset(game_ids):
            raise ArtifactAuditError("graph contains unknown candidate appid")
        degrees.append(len(candidates))
        edge_count += len(candidates)
        for candidate in candidates:
            similarities = candidate.get("lane_similarities", {})
            for lane in LANES:
                if float(similarities.get(lane, 0.0)) > 0.0:
                    lane_edges[lane] += 1
            referenced_evidence.update(candidate.get("evidence_ids", []))
    if not referenced_evidence.issubset(evidence_ids):
        raise ArtifactAuditError("graph references unknown evidence id")

    counts = manifest.get("counts", {})
    actual_counts = {"games": len(games), "edges": edge_count, "evidence": len(evidence_rows)}
    if counts != actual_counts:
        raise ArtifactAuditError(
            f"manifest counts mismatch: expected {counts}, got {actual_counts}"
        )

    semantic = pl.read_parquet(root / "source" / "explanation_evidence.parquet").select(
        "appid", "lane"
    )
    lane_evidence: Counter[str] = Counter({lane: 0 for lane in LANES})
    lane_games: dict[str, set[int]] = {lane: set() for lane in LANES}
    for row in semantic.iter_rows(named=True):
        raw_lane = str(row["lane"])
        if raw_lane not in lane_games:
            raise ArtifactAuditError(f"unsupported semantic lane: {raw_lane}")
        lane_evidence[raw_lane] += 1
        lane_games[raw_lane].add(int(row["appid"]))

    sorted_degrees = sorted(degrees)
    p95_index = max(0, math.ceil(len(sorted_degrees) * 0.95) - 1) if sorted_degrees else 0
    evidence_game_ids = {int(row["appid"]) for row in evidence_rows}
    game_count = len(game_ids)
    return {
        "report_version": 1,
        "kind": "artifact_audit",
        "build_id": build_id,
        "evaluated_at": manifest.get("created_at"),
        "integrity": {
            "status": "passed",
            "checksums_verified": len(checksums),
            "counts": actual_counts,
        },
        "coverage": {
            "graph_source_ratio": len({row["source_appid"] for row in records if row["candidates"]})
            / game_count
            if game_count
            else 1.0,
            "evidence_game_ratio": len(evidence_game_ids) / game_count if game_count else 1.0,
            "lane_evidence": dict(lane_evidence),
            "lane_game_ratio": {
                lane: len(lane_games[lane]) / game_count if game_count else 1.0 for lane in LANES
            },
            "nonzero_lane_edge_ratio": {
                lane: lane_edges[lane] / edge_count if edge_count else 1.0 for lane in LANES
            },
        },
        "candidate_degree": {
            "minimum": sorted_degrees[0] if sorted_degrees else 0,
            "median": statistics.median(sorted_degrees) if sorted_degrees else 0,
            "p95": sorted_degrees[p95_index] if sorted_degrees else 0,
            "maximum": sorted_degrees[-1] if sorted_degrees else 0,
        },
        "limitations": [
            "Coverage and integrity do not establish human relevance or explanation correctness."
        ],
    }
