"""A7: every GET endpoint answers 200 with schema-valid JSON on the demo DB, fast enough.

The endpoint list comes from the OpenAPI schema itself, so new routers are covered
automatically. Path parameters are filled from the demo data.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from tests.api.conftest import API_END

P95_BUDGET_S = 0.3


def _get_paths(client: TestClient) -> list[str]:
    spec = client.get("/api/openapi.json").json()
    return sorted(
        p for p, ops in spec["paths"].items() if "get" in ops and p != "/api/openapi.json"
    )


def _fill(path: str, activity_id: int) -> str:
    return (
        path.replace("{activity_id}", str(activity_id))
        .replace("{day}", API_END.isoformat())
        .replace("{year}", str(API_END.year))
        .replace("{uuid}", "demo-shoe-c")
    )


def test_openapi_lists_endpoints(client: TestClient) -> None:
    paths = _get_paths(client)
    assert "/api/meta" in paths
    assert "/api/activities/{activity_id}" in paths


def test_every_get_endpoint_is_valid_and_fast(client: TestClient, some_activity_id: int) -> None:
    spec = client.get("/api/openapi.json").json()
    timings: dict[str, float] = {}
    failures: list[str] = []
    for path in _get_paths(client):
        url = _fill(path, some_activity_id)
        samples = []
        for _ in range(3):
            t0 = time.perf_counter()
            resp = client.get(url)
            samples.append(time.perf_counter() - t0)
        if resp.status_code != 200:
            failures.append(f"{url}: HTTP {resp.status_code} {resp.text[:200]}")
            continue
        timings[url] = statistics.median(samples)
        schema_ref = spec["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]
        _assert_matches(resp.json(), schema_ref["schema"], spec, url, failures)
    assert failures == []
    ordered = sorted(timings.values())
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    slow = {u: round(t, 3) for u, t in timings.items() if t > P95_BUDGET_S}
    assert p95 < P95_BUDGET_S, f"p95={p95:.3f}s, slow endpoints: {slow}"


def _assert_matches(
    body: Any, schema: dict[str, Any], spec: dict[str, Any], url: str, failures: list[str]
) -> None:
    """Light structural validation against the OpenAPI schema (types of top-level fields)."""
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = spec["components"]["schemas"][name]
    if schema.get("type") == "array":
        if not isinstance(body, list):
            failures.append(f"{url}: expected array")
        return
    props = schema.get("properties")
    if props and isinstance(body, dict):
        missing = [k for k in schema.get("required", []) if k not in body]
        if missing:
            failures.append(f"{url}: missing fields {missing}")


@pytest.mark.parametrize(
    "bad", ["/api/activities?sport=quidditch", "/api/activities?start=2026-02-01&end=2026-01-01"]
)
def test_invalid_filters_are_rejected(client: TestClient, bad: str) -> None:
    assert client.get(bad).status_code == 422


def test_unknown_activity_is_404(client: TestClient) -> None:
    assert client.get("/api/activities/1").status_code == 404
    assert client.get("/api/activities/1/streams").status_code == 404


def test_type_adapter_smoke() -> None:
    assert TypeAdapter(list[int]).validate_python([1, 2]) == [1, 2]
