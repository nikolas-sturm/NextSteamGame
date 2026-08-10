from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from nextsteam_pipeline.acquisition import RateLimiter, SteamSpyClient, SteamStoreClient, acquire
from nextsteam_pipeline.cli import app
from nextsteam_pipeline.models import LANES, Provenance, RawGame, ReviewEvidence
from nextsteam_pipeline.runner import _cached_stage, publish_fixture
from nextsteam_pipeline.semantics import DeterministicBaseline


class SyntheticTransport:
    def get(self, url: str, *, params: dict[str, object]) -> httpx.Response:
        appid = int(params.get("appid", params.get("appids", 0)))
        request = httpx.Request("GET", url, params=params)
        if "appreviews" in url:
            payload = {
                "reviews": [
                    {
                        "recommendationid": f"r{appid}",
                        "review": "Cozy combat solo mystery",
                        "voted_up": True,
                        "author": {"playtime_forever": 120},
                    }
                ]
            }
        elif "steamspy" in url:
            payload = {
                "tags": {"Crafting": 10},
                "positive": 90,
                "negative": 10,
                "owners": "1000 .. 2000",
            }
        else:
            payload = {
                str(appid): {
                    "success": True,
                    "data": {
                        "name": f"Synthetic {appid}",
                        "short_description": "Space crafting co-op",
                        "genres": [{"description": "Co-op"}],
                        "developers": ["Synthetic Studio"],
                        "publishers": ["Synthetic Publisher"],
                        "release_date": {"date": "1 Jan, 2025"},
                        "header_image": "https://example.invalid/header.jpg",
                    },
                }
            }
        return httpx.Response(200, json=payload, request=request)


def test_acquisition_resumes_without_network(tmp_path: Path) -> None:
    transport = SyntheticTransport()
    store = SteamStoreClient(transport, RateLimiter(1000, sleep=lambda _: None))
    spy = SteamSpyClient(transport, RateLimiter(1000, sleep=lambda _: None))
    state = tmp_path / "state.json"
    first = acquire([303], store, spy, state)

    class FailingTransport:
        def get(self, url: str, *, params: dict[str, object]) -> httpx.Response:
            raise AssertionError("resume made network request")

    resumed = acquire(
        [303],
        SteamStoreClient(FailingTransport(), RateLimiter(1000, sleep=lambda _: None)),
        SteamSpyClient(FailingTransport(), RateLimiter(1000, sleep=lambda _: None)),
        state,
    )
    assert resumed == first


def test_baseline_exact_lanes_and_direct_lineage() -> None:
    provenance = Provenance(
        "synthetic", "1", "2026-01-01T00:00:00Z", "https://example.invalid", "abc"
    )
    game = RawGame(
        1, "Game", "Space crafting co-op cozy", (), (), "Dev", "Pub", 1, 0, "0 .. 10", (provenance,)
    )
    review = ReviewEvidence(
        "ev_1", 1, "r1", "challenging solo mystery combat", True, 10, provenance
    )
    evidence = DeterministicBaseline().interpret(game, [review])
    assert {item.lane for item in evidence} == set(LANES)
    assert all(item.source_evidence_ids and item.excerpt for item in evidence)
    assert DeterministicBaseline().interpret(game, [review]) == evidence


def test_fixture_exact_runtime_contract_and_checksums(tmp_path: Path) -> None:
    release = publish_fixture(tmp_path / "fixture")
    expected = {
        "metadata.json",
        "graph.json",
        "evidence.json",
        "metadata.sqlite",
        "manifest.json",
        "source/games.parquet",
        "source/reviews.parquet",
        "source/identity.parquet",
        "source/candidate_edges.parquet",
        "source/explanation_evidence.parquet",
    }
    actual = {path.relative_to(release).as_posix() for path in release.rglob("*") if path.is_file()}
    assert actual == expected
    manifest = json.loads((release / "manifest.json").read_text())
    assert set(manifest) == {
        "build_id",
        "created_at",
        "artifact_schema_version",
        "api_compatibility_version",
        "source_git_sha",
        "pipeline_git_sha",
        "acquisition_windows",
        "models",
        "ontology_version",
        "scorer_version",
        "counts",
        "checksums",
        "evaluation_report_id",
    }
    assert set(manifest["checksums"]) == actual - {"manifest.json"}
    for relative, expected_hash in manifest["checksums"].items():
        assert hashlib.sha256((release / relative).read_bytes()).hexdigest() == expected_hash
    metadata = json.loads((release / "metadata.json").read_text())
    assert set(metadata["games"][0]) == {
        "appid",
        "name",
        "short_description",
        "release_year",
        "header_image_url",
        "steam_url",
    }
    graph = json.loads((release / "graph.json").read_text())
    assert graph["lanes"] == list(LANES)
    candidate = graph["records"][0]["candidates"][0]
    assert set(candidate["lane_similarities"]) == set(LANES)
    assert set(candidate["matched_concepts"]) == set(LANES)
    assert candidate["evidence_ids"]
    assert manifest["acquisition_windows"]["kind"] == "test_fixture"


def test_publish_is_immutable(tmp_path: Path) -> None:
    output = tmp_path / "fixture"
    publish_fixture(output)
    with pytest.raises(FileExistsError):
        publish_fixture(output)


def test_fixture_cli_is_explicit_and_safe(tmp_path: Path) -> None:
    output = tmp_path / "ci-fixture"
    result = CliRunner().invoke(app, ["publish-test-fixture", "--output", str(output)])
    assert result.exit_code == 0
    assert (output / "releases" / "synthetic-fixture-v1" / "manifest.json").is_file()
    with pytest.raises(ValueError, match="isolated"):
        publish_fixture(tmp_path / "production")


def test_stage_failure_then_safe_resume(tmp_path: Path) -> None:
    attempts = 0

    def build() -> tuple[list[int], list[int]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("synthetic failure")
        return [1, 2], [1, 2]

    with pytest.raises(RuntimeError, match="synthetic failure"):
        _cached_stage(tmp_path, "semantic", build, lambda rows: rows)
    assert json.loads((tmp_path / "stages/semantic.json").read_text())["status"] == "failed"
    assert _cached_stage(tmp_path, "semantic", build, lambda rows: rows) == [1, 2]
    assert _cached_stage(tmp_path, "semantic", build, lambda rows: rows) == [1, 2]
    assert attempts == 2
