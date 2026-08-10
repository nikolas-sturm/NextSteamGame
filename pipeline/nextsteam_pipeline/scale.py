from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl

from .acquisition import SteamSpyClient, SteamStoreClient, acquire
from .models import StageManifest
from .storage import write_parquet
from .util import atomic_json, checksum

ScaleTarget = Literal[500, 5000, 20000, "full"]


def bounded_appids(appids: list[int], target: ScaleTarget) -> list[int]:
    if len(set(appids)) != len(appids):
        raise ValueError("appids must be unique")
    return appids if target == "full" else appids[:target]


def acquire_shards(
    appids: list[int],
    workdir: Path,
    shard_size: int = 500,
    *,
    store: SteamStoreClient | None = None,
    spy: SteamSpyClient | None = None,
) -> list[Path]:
    if shard_size <= 0 or shard_size > 500:
        raise ValueError("shard_size must be between 1 and 500")
    outputs: list[Path] = []
    for start in range(0, len(appids), shard_size):
        shard = appids[start : start + shard_size]
        shard_id = f"{start // shard_size:06d}"
        root = workdir / "shards" / shard_id
        manifest_path = root / "manifest.json"
        games_path = root / "games.parquet"
        reviews_path = root / "reviews.parquet"
        if manifest_path.exists() and games_path.exists() and reviews_path.exists():
            saved = __import__("json").loads(manifest_path.read_text())
            if saved["status"] == "complete" and saved["output_checksums"] == {
                "games.parquet": checksum(games_path),
                "reviews.parquet": checksum(reviews_path),
            }:
                outputs.append(root)
                continue
        stage = StageManifest(
            "acquire-shard",
            "1.0.0",
            "running",
            counts={"requested": len(shard)},
            metadata={"shard_id": shard_id},
        )
        atomic_json(manifest_path, stage)
        try:
            games, reviews = acquire(
                shard, store or SteamStoreClient(), spy or SteamSpyClient(), root / "state.json"
            )
            write_parquet(games_path, [asdict(item) for item in games])
            write_parquet(reviews_path, [asdict(item) for item in reviews])
            state: dict[str, Any] = __import__("json").loads((root / "state.json").read_text())
            stage.status = "complete"
            stage.counts.update(
                games=len(games),
                reviews=len(reviews),
                skipped=len(state["skips"]),
                failures=len(state["failures"]),
            )
            stage.output_checksums = {
                "games.parquet": checksum(games_path),
                "reviews.parquet": checksum(reviews_path),
            }
            atomic_json(manifest_path, stage)
            outputs.append(root)
        except BaseException as error:
            stage.status = "failed"
            stage.metadata["error"] = f"{type(error).__name__}: {error}"
            atomic_json(manifest_path, stage)
            raise
    return outputs


def compact_shards(shards: list[Path], output: Path) -> dict[str, Any]:
    if not shards:
        raise ValueError("at least one shard required")
    output.mkdir(parents=True, exist_ok=True)
    games_sources = [str(path / "games.parquet") for path in sorted(shards)]
    review_sources = [str(path / "reviews.parquet") for path in sorted(shards)]
    games_path, reviews_path = output / "games.parquet", output / "reviews.parquet"
    pl.scan_parquet(games_sources).unique(subset="appid", keep="first").sort(
        "appid"
    ).collect().write_parquet(games_path, use_pyarrow=True)
    pl.scan_parquet(review_sources).unique(subset="evidence_id", keep="first").sort(
        ["appid", "evidence_id"]
    ).collect().write_parquet(reviews_path, use_pyarrow=True)
    database = duckdb.connect()
    try:
        game_row = database.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(games_path)]
        ).fetchone()
        review_row = database.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(reviews_path)]
        ).fetchone()
        duplicate_row = database.execute(
            "SELECT count(*) - count(DISTINCT appid) FROM read_parquet(?)", [str(games_path)]
        ).fetchone()
        if game_row is None or review_row is None or duplicate_row is None:
            raise ValueError("DuckDB validation returned no result")
        game_count, review_count, duplicate_count = map(
            int, (game_row[0], review_row[0], duplicate_row[0])
        )
    finally:
        database.close()
    if duplicate_count:
        raise ValueError("compaction produced duplicate appids")
    report = {
        "games": game_count,
        "reviews": review_count,
        "checksums": {
            "games.parquet": checksum(games_path),
            "reviews.parquet": checksum(reviews_path),
        },
    }
    atomic_json(output / "compaction-manifest.json", report)
    return report
