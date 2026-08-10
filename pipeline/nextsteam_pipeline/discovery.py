from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from .acquisition import SteamSpyClient
from .models import Provenance
from .util import atomic_json, checksum


@dataclass(frozen=True)
class CatalogEntry:
    appid: int
    name: str
    owners: int
    positive: int
    negative: int


@dataclass(frozen=True)
class Eligibility:
    min_owners: int = 0
    min_reviews: int = 0
    require_name: bool = True

    def accepts(self, entry: CatalogEntry) -> bool:
        return (
            entry.owners >= self.min_owners
            and entry.positive + entry.negative >= self.min_reviews
            and (not self.require_name or bool(entry.name.strip()))
        )


def _owner_floor(value: object) -> int:
    if isinstance(value, int):
        return value
    first = str(value).replace(",", "").split("..", maxsplit=1)[0].strip()
    try:
        return int(first)
    except ValueError:
        return 0


def discover_catalog(
    client: SteamSpyClient, pages: int, eligibility: Eligibility
) -> tuple[list[CatalogEntry], list[Provenance]]:
    if pages <= 0:
        raise ValueError("pages must be positive")
    entries: dict[int, CatalogEntry] = {}
    provenance: list[Provenance] = []
    for page in range(pages):
        payload, source = client.catalog_page(page)
        provenance.append(source)
        for key, row in payload.items():
            appid = int(row.get("appid", key))
            entry = CatalogEntry(
                appid=appid,
                name=str(row.get("name", "")),
                owners=_owner_floor(row.get("owners", 0)),
                positive=int(row.get("positive", 0)),
                negative=int(row.get("negative", 0)),
            )
            if appid > 0 and eligibility.accepts(entry):
                entries[appid] = entry
    return sorted(entries.values(), key=lambda item: item.appid), provenance


def write_catalog(
    output: Path,
    entries: list[CatalogEntry],
    provenance: list[Provenance],
    eligibility: Eligibility,
) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    appids_path = output / "appids.txt"
    appids_path.write_text("".join(f"{entry.appid}\n" for entry in entries), encoding="utf-8")
    catalog_path = output / "catalog.parquet"
    pl.DataFrame(
        {
            "appid": [entry.appid for entry in entries],
            "name": [entry.name for entry in entries],
            "owner_floor": [entry.owners for entry in entries],
            "positive": [entry.positive for entry in entries],
            "negative": [entry.negative for entry in entries],
        }
    ).write_parquet(catalog_path, compression="zstd", use_pyarrow=True)
    manifest_path = output / "catalog-manifest.json"
    atomic_json(
        manifest_path,
        {
            "created_at": datetime.now(UTC).isoformat(),
            "source": "SteamSpy request=all",
            "count": len(entries),
            "eligibility": asdict(eligibility),
            "appids_sha256": checksum(appids_path),
            "catalog_parquet_sha256": checksum(catalog_path),
            "pages": [asdict(item) for item in provenance],
        },
    )
    return appids_path, manifest_path


def _rank_quantiles(values: list[tuple[int, int]], quantiles: int) -> dict[int, int]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    size = len(ordered)
    return {
        appid: min(quantiles - 1, index * quantiles // size)
        for index, (appid, _) in enumerate(ordered)
    }


def select_slice(
    catalog_path: Path,
    output: Path,
    count: int,
    seed: str,
    quantiles: int = 4,
) -> tuple[Path, Path]:
    if not 100 <= count <= 500:
        raise ValueError("selection count must be between 100 and 500")
    if quantiles < 2:
        raise ValueError("quantiles must be at least 2")
    rows = (
        pl.read_parquet(catalog_path)
        .select("appid", "owner_floor", "positive", "negative")
        .to_dicts()
    )
    if count > len(rows):
        raise ValueError("selection count exceeds eligible catalog")
    owner_strata = _rank_quantiles(
        [(int(row["appid"]), int(row["owner_floor"])) for row in rows], quantiles
    )
    review_strata = _rank_quantiles(
        [(int(row["appid"]), int(row["positive"]) + int(row["negative"])) for row in rows],
        quantiles,
    )
    strata: dict[tuple[int, int], list[int]] = {}
    for row in rows:
        appid = int(row["appid"])
        strata.setdefault((owner_strata[appid], review_strata[appid]), []).append(appid)

    def selection_key(appid: int) -> tuple[str, int]:
        digest = hashlib.sha256(f"{seed}\x1f{appid}".encode()).hexdigest()
        return digest, appid

    active = sorted(strata)
    selected: list[int] = []
    base, remainder = divmod(count, len(active))
    for index, key in enumerate(active):
        quota = base + (index < remainder)
        selected.extend(sorted(strata[key], key=selection_key)[:quota])
    if len(selected) < count:
        selected_set = set(selected)
        remaining = sorted(
            (int(row["appid"]) for row in rows if int(row["appid"]) not in selected_set),
            key=selection_key,
        )
        selected.extend(remaining[: count - len(selected)])
    selected = sorted(selected, key=selection_key)
    output.mkdir(parents=True, exist_ok=True)
    appids_path = output / "appids.txt"
    appids_path.write_text("".join(f"{appid}\n" for appid in selected), encoding="utf-8")
    selected_counts: dict[str, int] = {}
    for appid in selected:
        label = f"owners_q{owner_strata[appid]}_reviews_q{review_strata[appid]}"
        selected_counts[label] = selected_counts.get(label, 0) + 1
    manifest_path = output / "selection-manifest.json"
    atomic_json(
        manifest_path,
        {
            "source_catalog": str(catalog_path),
            "source_checksum": checksum(catalog_path),
            "method": "owner_review_rank_quantiles_stable_hash_v1",
            "seed": seed,
            "quantiles": quantiles,
            "requested_count": count,
            "selected_count": len(selected),
            "strata_counts": dict(sorted(selected_counts.items())),
            "selected_checksum": checksum(appids_path),
            "semantic_diversity": {
                "status": "not_assessed",
                "reason": "catalog has no acquired semantic evidence",
                "later_audit": "post_acquisition_semantic_lane_coverage",
            },
        },
    )
    return appids_path, manifest_path
