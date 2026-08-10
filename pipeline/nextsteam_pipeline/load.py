from __future__ import annotations

import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx


def benchmark_api(
    base_url: str,
    payload: dict[str, Any],
    expected_build_id: str,
    requests: int,
    concurrency: int,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if requests <= 0 or concurrency <= 0:
        raise ValueError("requests and concurrency must be positive")
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    def send(client: httpx.Client) -> tuple[float, int | None, str | None, str | None]:
        started = time.perf_counter()
        status: int | None = None
        mode: str | None = None
        error_message: str | None = None
        try:
            response = client.post("/v1/recommendations", json=payload)
            status = response.status_code
            response.raise_for_status()
            body = response.json()
            if body.get("build_id") != expected_build_id:
                raise ValueError("response build_id mismatch")
            mode = str(body.get("retrieval", {}).get("mode", "missing"))
        except (httpx.HTTPError, ValueError, TypeError) as error:
            error_message = f"{type(error).__name__}: {error}"
        return (time.perf_counter() - started) * 1000, status, mode, error_message

    with httpx.Client(
        base_url=base_url,
        timeout=30,
        limits=limits,
        transport=transport,
    ) as client:
        client.get("/readyz").raise_for_status()
        send(client)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(executor.map(lambda _: send(client), range(requests)))
        elapsed = time.perf_counter() - started

    latencies = sorted(result[0] for result in results)
    statuses = Counter(result[1] for result in results if result[1] is not None)
    modes = Counter(result[2] for result in results if result[2] is not None)
    errors = [result[3] for result in results if result[3] is not None]
    return {
        "report_version": 1,
        "kind": "api_load",
        "build_id": expected_build_id,
        "requests": requests,
        "concurrency": concurrency,
        "elapsed_seconds": elapsed,
        "requests_per_second": requests / elapsed,
        "errors": len(errors),
        "error_samples": errors[:10],
        "status_counts": {str(key): value for key, value in sorted(statuses.items())},
        "retrieval_modes": dict(sorted(modes.items())),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "maximum": latencies[-1],
        },
        "limitations": [
            "Local load measurements do not predict production network or host performance."
        ],
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]
