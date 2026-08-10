from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl

from .acquisition import SteamSpyClient, SteamStoreClient, acquire
from .models import StageManifest
from .storage import write_parquet
from .util import atomic_json, checksum, read_json

ScaleTarget = Literal[500, 1000, 2000, 5000, 20000, "full"]


def bounded_appids(appids: list[int], target: ScaleTarget) -> list[int]:
    if len(set(appids)) != len(appids):
        raise ValueError("appids must be unique")
    return appids if target == "full" else appids[:target]


def acquire_shards(
    appids: list[int],
    workdir: Path,
    shard_size: int = 500,
    *,
    shard_offset: int = 0,
    store: SteamStoreClient | None = None,
    spy: SteamSpyClient | None = None,
) -> list[Path]:
    if shard_size <= 0 or shard_size > 500:
        raise ValueError("shard_size must be between 1 and 500")
    if shard_offset < 0:
        raise ValueError("shard_offset must be non-negative")
    outputs: list[Path] = []
    for start in range(0, len(appids), shard_size):
        shard = appids[start : start + shard_size]
        shard_id = f"{shard_offset + start // shard_size:06d}"
        root = workdir / "shards" / shard_id
        manifest_path = root / "manifest.json"
        games_path = root / "games.parquet"
        reviews_path = root / "reviews.parquet"
        if manifest_path.exists() and games_path.exists() and reviews_path.exists():
            saved = read_json(manifest_path)
            if _complete_shard(saved, root, shard):
                outputs.append(root)
                continue
        stage = StageManifest(
            "acquire-shard",
            "1.1.0",
            "running",
            counts={"requested": len(shard)},
            metadata={"shard_id": shard_id, "appids_sha256": _appids_checksum(shard)},
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


def acquire_until_target(
    appids: list[int],
    target: int,
    workdir: Path,
    shard_size: int = 500,
    *,
    store: SteamStoreClient | None = None,
    spy: SteamSpyClient | None = None,
) -> list[Path]:
    if target <= 0:
        raise ValueError("target must be positive")
    if len(set(appids)) != len(appids):
        raise ValueError("appids must be unique")
    input_path = workdir / "scale-input.json"
    fingerprint = _appids_checksum(appids)
    if input_path.exists():
        if read_json(input_path).get("appids_sha256") != fingerprint:
            raise ValueError("scale workdir belongs to a different appid catalog")
    else:
        atomic_json(input_path, {"appids_sha256": fingerprint, "count": len(appids)})

    outputs: list[Path] = []
    acquired = 0
    cursor = 0
    shard_root = workdir / "shards"
    for index, root in enumerate(sorted(shard_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9]"))):
        if root.name != f"{index:06d}":
            raise ValueError("scale workdir has non-contiguous shard IDs")
        saved = read_json(root / "manifest.json")
        requested = int(saved.get("counts", {}).get("requested", 0))
        shard = appids[cursor : cursor + requested]
        if requested <= 0 or not _complete_shard(saved, root, shard):
            break
        outputs.append(root)
        acquired += int(saved["counts"]["games"])
        cursor += requested

    while acquired < target and cursor < len(appids):
        available = len(appids) - cursor
        request_count = min(shard_size, available, max(target - acquired, min(50, available)))
        batch = appids[cursor : cursor + request_count]
        new_outputs = acquire_shards(
            batch,
            workdir,
            request_count,
            shard_offset=len(outputs),
            store=store,
            spy=spy,
        )
        outputs.extend(new_outputs)
        acquired += sum(
            int(read_json(path / "manifest.json")["counts"]["games"]) for path in new_outputs
        )
        cursor += request_count
    if acquired < target:
        raise ValueError(f"catalog exhausted after acquiring {acquired} of {target} eligible games")
    return outputs


def _appids_checksum(appids: list[int]) -> str:
    payload = "".join(f"{appid}\n" for appid in appids).encode()
    return hashlib.sha256(payload).hexdigest()


def _complete_shard(saved: dict[str, Any], root: Path, appids: list[int]) -> bool:
    saved_fingerprint = saved.get("metadata", {}).get("appids_sha256")
    if saved_fingerprint is None:
        state = read_json(root / "state.json")
        attempted = set(state.get("completed", []))
        attempted.update(int(item["appid"]) for item in state.get("failures", []))
        if attempted != set(appids):
            raise ValueError(f"{root}: legacy shard input does not match current catalog")
    elif saved_fingerprint != _appids_checksum(appids):
        raise ValueError(f"{root}: shard input does not match current catalog")
    games_path = root / "games.parquet"
    reviews_path = root / "reviews.parquet"
    if not games_path.is_file() or not reviews_path.is_file():
        return False
    return saved.get("status") == "complete" and saved.get("output_checksums") == {
        "games.parquet": checksum(games_path),
        "reviews.parquet": checksum(reviews_path),
    }


def compact_shards(
    shards: list[Path], output: Path, max_games: int | None = None
) -> dict[str, Any]:
    if not shards:
        raise ValueError("at least one shard required")
    if max_games is not None and max_games <= 0:
        raise ValueError("max_games must be positive")
    output.mkdir(parents=True, exist_ok=True)
    games_sources = [str(path / "games.parquet") for path in sorted(shards)]
    review_sources = [str(path / "reviews.parquet") for path in sorted(shards)]
    games_path, reviews_path = output / "games.parquet", output / "reviews.parquet"
    games = pl.scan_parquet(games_sources).unique(subset="appid", keep="first").sort("appid")
    if max_games is not None:
        games = games.head(max_games)
    game_rows = games.collect()
    if max_games is not None and len(game_rows) != max_games:
        raise ValueError(f"expected {max_games} compacted games, found {len(game_rows)}")
    game_rows.write_parquet(games_path, use_pyarrow=True)
    selected = pl.scan_parquet(games_path).select("appid")
    pl.scan_parquet(review_sources).unique(subset="evidence_id", keep="first").join(
        selected, on="appid", how="semi"
    ).sort(["appid", "evidence_id"]).collect().write_parquet(reviews_path, use_pyarrow=True)
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
