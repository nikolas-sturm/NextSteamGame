from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from .models import Provenance, RawGame, ReviewEvidence
from .util import atomic_json, stable_id


class AcquisitionError(RuntimeError):
    """Typed upstream acquisition failure."""


class MissingApp(AcquisitionError):
    pass


class IneligibleApp(AcquisitionError):
    pass


class Transport(Protocol):
    def get(self, url: str, *, params: dict[str, object]) -> httpx.Response: ...


@dataclass
class RateLimiter:
    requests_per_second: float = 1.0
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last: float | None = None

    def wait(self) -> None:
        now = self.clock()
        if self._last is not None:
            self.sleep(max(0.0, 1.0 / self.requests_per_second - (now - self._last)))
        self._last = self.clock()


class JsonClient:
    def __init__(
        self,
        transport: Transport | None = None,
        limiter: RateLimiter | None = None,
        retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.transport: Transport = transport or cast(
            Transport, httpx.Client(timeout=30, follow_redirects=True)
        )
        self.limiter = limiter or RateLimiter()
        self.retries = retries
        self.sleep = sleep
        self.last_retry_count = 0
        self.total_retry_count = 0

    def fetch(self, url: str, params: dict[str, object]) -> tuple[Any, Provenance]:
        self.last_retry_count = 0
        for attempt in range(self.retries):
            self.limiter.wait()
            response = self.transport.get(url, params=params)
            if response.status_code == 404:
                raise MissingApp(str(params.get("appid", "unknown")))
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                body = response.content
                provenance = Provenance(
                    source=self.__class__.__name__,
                    upstream_id=str(
                        params.get("appid", params.get("page", params.get("request", "unknown")))
                    ),
                    fetched_at=datetime.now(UTC).isoformat(),
                    url=str(response.request.url),
                    payload_sha256=hashlib.sha256(body).hexdigest(),
                )
                return response.json(), provenance
            if attempt + 1 < self.retries:
                self.last_retry_count += 1
                self.total_retry_count += 1
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after else 2**attempt + random.random()
                self.sleep(delay)
        response.raise_for_status()
        raise AssertionError("unreachable")


class SteamStoreClient(JsonClient):
    URL = "https://store.steampowered.com/api/appdetails"
    REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

    def game(self, appid: int) -> tuple[dict[str, Any], Provenance]:
        payload, provenance = self.fetch(self.URL, {"appids": appid, "l": "english"})
        record = payload.get(str(appid), {})
        if not record.get("success") or "data" not in record:
            raise MissingApp(str(appid))
        detail: dict[str, Any] = record["data"]
        if detail.get("type") not in {None, "game"}:
            raise IneligibleApp(f"{appid}: type={detail.get('type')}")
        return detail, provenance

    def reviews(self, appid: int, limit: int = 20) -> tuple[list[dict[str, Any]], Provenance]:
        payload, provenance = self.fetch(
            self.REVIEWS_URL.format(appid=appid),
            {"json": 1, "language": "english", "num_per_page": limit},
        )
        return payload["reviews"], provenance


class SteamSpyClient(JsonClient):
    URL = "https://steamspy.com/api.php"

    def game(self, appid: int) -> tuple[dict[str, Any], Provenance]:
        payload, provenance = self.fetch(self.URL, {"request": "appdetails", "appid": appid})
        if not payload or int(payload.get("appid", appid)) != appid:
            raise MissingApp(str(appid))
        return payload, provenance

    def catalog_page(self, page: int) -> tuple[dict[str, dict[str, Any]], Provenance]:
        payload, provenance = self.fetch(self.URL, {"request": "all", "page": page})
        return payload, provenance


def acquire(
    appids: Iterable[int], store: SteamStoreClient, spy: SteamSpyClient, state_path: Path
) -> tuple[list[RawGame], list[ReviewEvidence]]:
    state: dict[str, Any] = {
        "completed": [],
        "games": [],
        "reviews": [],
        "skips": [],
        "failures": [],
        "retries": 0,
    }
    if state_path.exists():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        state.update(loaded)
    completed = set(state["completed"])
    for appid in appids:
        if appid in completed:
            continue
        retries_before = store.total_retry_count + spy.total_retry_count
        terminal = False
        try:
            detail, store_prov = store.game(appid)

            stats, spy_prov = spy.game(appid)

            review_rows, review_prov = store.reviews(appid)

            game = RawGame(
                appid=appid,
                name=detail["name"],
                description=detail.get("short_description", ""),
                tags=tuple(stats.get("tags", {})),
                genres=tuple(item["description"] for item in detail.get("genres", [])),
                developer=", ".join(detail.get("developers", [])),
                publisher=", ".join(detail.get("publishers", [])),
                positive=int(stats.get("positive", 0)),
                negative=int(stats.get("negative", 0)),
                owners=str(stats.get("owners", "0 .. 0")),
                provenance=(store_prov, spy_prov),
                release_year=_release_year(detail.get("release_date", {}).get("date")),
                header_image_url=detail.get("header_image"),
            )
            reviews = [
                ReviewEvidence(
                    evidence_id=stable_id("review", appid, row["recommendationid"]),
                    appid=appid,
                    review_id=str(row["recommendationid"]),
                    text=row["review"],
                    recommended=bool(row["voted_up"]),
                    playtime_minutes=int(row["author"].get("playtime_forever", 0)),
                    provenance=review_prov,
                )
                for row in review_rows
            ]
            state["games"].append(game_to_dict(game))
            state["reviews"].extend(review_to_dict(review) for review in reviews)
            terminal = True
        except (MissingApp, IneligibleApp) as error:
            state["skips"].append(
                {"appid": appid, "type": type(error).__name__, "message": str(error)}
            )
            terminal = True
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            state["failures"].append(
                {"appid": appid, "type": type(error).__name__, "message": str(error)}
            )
        finally:
            state["retries"] += store.total_retry_count + spy.total_retry_count - retries_before
            if terminal:
                state["completed"].append(appid)
                completed.add(appid)
            atomic_json(state_path, state)
    return [game_from_dict(row) for row in state["games"]], [
        review_from_dict(row) for row in state["reviews"]
    ]


def _release_year(value: object) -> int | None:
    match = next(iter(__import__("re").findall(r"\b(?:19|20)\d{2}\b", str(value))), None)
    return int(match) if match else None


def provenance_from_dict(row: dict[str, Any]) -> Provenance:
    return Provenance(**row)


def game_to_dict(game: RawGame) -> dict[str, Any]:
    return {
        **game.__dict__,
        "tags": list(game.tags),
        "genres": list(game.genres),
        "provenance": [item.__dict__ for item in game.provenance],
    }


def game_from_dict(row: dict[str, Any]) -> RawGame:
    return RawGame(
        **{key: value for key, value in row.items() if key not in {"tags", "genres", "provenance"}},
        tags=tuple(row["tags"]),
        genres=tuple(row["genres"]),
        provenance=tuple(provenance_from_dict(item) for item in row["provenance"]),
    )


def review_to_dict(review: ReviewEvidence) -> dict[str, Any]:
    return {**review.__dict__, "provenance": review.provenance.__dict__}


def review_from_dict(row: dict[str, Any]) -> ReviewEvidence:
    return ReviewEvidence(
        **{key: value for key, value in row.items() if key != "provenance"},
        provenance=provenance_from_dict(row["provenance"]),
    )
