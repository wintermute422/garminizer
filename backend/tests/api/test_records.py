"""S4: /api/records endpoints, cross-checked against the base tables of the demo DB."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.analytics.curves import STANDARD_DISTANCES_M
from tests.api.conftest import API_END

LABELS = [
    "400 m",
    "1 km",
    "1 mile",
    "5 km",
    "10 km",
    "15 km",
    "Half marathon",
    "30 km",
    "Marathon",
]


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, query: str, **params: Any) -> Any:
    return s.execute(text(query), params).scalar()


def windows(body: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {w["key"]: w["points"] for w in body["windows"]}


@pytest.mark.parametrize(("metric", "sport"), [("speed", "run"), ("power", "ride"), ("hr", "run")])
def test_curves_are_non_increasing_envelopes_of_best_efforts(
    client: TestClient, sql: Session, metric: str, sport: str
) -> None:
    params = {"metric": metric, "sport": sport} if metric != "speed" else {}
    resp = client.get("/api/records/curves", params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["metric"], body["sport_group"]) == (metric, sport)
    assert [w["key"] for w in body["windows"]] == ["all", "365d", "90d"]
    assert all(w["label"] for w in body["windows"])
    raw: dict[int, float] = {
        int(d): float(v)
        for d, v in sql.execute(
            text(
                "SELECT b.duration_s, max(b.value) FROM garmin.activity_best_effort b "
                "JOIN garmin.activity a USING (activity_id) "
                "WHERE b.metric = :m AND a.sport_group = :s GROUP BY 1"
            ),
            {"m": metric, "s": sport},
        )
    }
    assert raw
    points = windows(body)["all"]
    assert [p["duration_s"] for p in points] == sorted(raw)
    values = [p["value"] for p in points]
    assert all(a >= b for a, b in itertools.pairwise(values)), "curve rises"
    for p in points:
        longer = max(v for d, v in raw.items() if d >= p["duration_s"])
        assert p["value"] == pytest.approx(longer)
        holder = sql.execute(
            text(
                "SELECT max(b.value), a.sport_group, a.start_time_local::date "
                "FROM garmin.activity_best_effort b JOIN garmin.activity a USING (activity_id) "
                "WHERE b.activity_id = :i AND b.metric = :m AND b.duration_s >= :d "
                "GROUP BY 2, 3"
            ),
            {"i": p["activity_id"], "m": metric, "d": p["duration_s"]},
        ).one()
        assert holder[0] == pytest.approx(p["value"])
        assert holder[1] == sport
        assert holder[2].isoformat() == p["day"]


def test_curve_windows_are_relative_to_last_data_day(client: TestClient) -> None:
    # Run power: the demo's best short efforts are older than 90 days.
    w = windows(client.get("/api/records/curves", params={"metric": "power"}).json())
    # The demo spans 150 days: the 365-day window equals all time.
    assert w["365d"] == w["all"]
    cut = (API_END - timedelta(days=89)).isoformat()
    assert w["90d"]
    best_all = {p["duration_s"]: p["value"] for p in w["all"]}
    for p in w["90d"]:
        assert p["day"] >= cut
        assert p["value"] <= best_all[p["duration_s"]]
    # Some all-time bests are older than 90 days, so the windows really differ.
    assert any(p["day"] < cut for p in w["all"])
    assert w["90d"] != w["all"]


def test_distances_bests_and_progression(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/records/distances")
    assert resp.status_code == 200
    body = resp.json()
    assert [d["label"] for d in body] == LABELS
    assert [d["distance_m"] for d in body] == pytest.approx(list(STANDARD_DISTANCES_M))
    with_best = 0
    for d in body:
        history = sql.execute(
            text(
                "SELECT bd.seconds, bd.activity_id, a.start_time_local::date, a.name "
                "FROM garmin.activity_best_distance bd JOIN garmin.activity a USING (activity_id) "
                "WHERE a.sport_group = 'run' AND bd.distance_m = :d "
                "ORDER BY a.start_time_local, bd.activity_id"
            ),
            {"d": d["distance_m"]},
        ).all()
        if not history:
            assert d["best"] is None
            assert d["best_this_year"] is None
            assert d["progression"] == []
            continue
        with_best += 1
        expected_steps: list[tuple[float, int, date]] = []
        for seconds, aid, day, _ in history:
            if not expected_steps or seconds < expected_steps[-1][0]:
                expected_steps.append((seconds, aid, day))
        prog = d["progression"]
        assert [(p["activity_id"], p["day"]) for p in prog] == [
            (aid, day.isoformat()) for _, aid, day in expected_steps
        ]
        secs = [p["seconds"] for p in prog]
        assert all(a > b for a, b in itertools.pairwise(secs)), "not strictly faster"
        assert [p["day"] for p in prog] == sorted(p["day"] for p in prog)
        fastest = min(history, key=lambda r: r[0])
        best = d["best"]
        assert best["seconds"] == pytest.approx(fastest[0])
        assert (best["activity_id"], best["day"], best["name"]) == (
            prog[-1]["activity_id"],
            prog[-1]["day"],
            fastest[3],
        )
        # All demo activities are in the year of the last data day.
        assert d["best_this_year"] == best
    assert with_best >= 5


def test_personal_records_with_activity_names(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/records/personal")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == scalar(sql, "SELECT count(*) FROM garmin.personal_record") > 0
    assert set(body[0]) == {
        "record_id",
        "type_id",
        "type_key",
        "value",
        "activity_id",
        "achieved_at",
        "activity_name",
    }
    for r in body:
        assert r["value"] == pytest.approx(
            scalar(
                sql,
                "SELECT value FROM garmin.personal_record WHERE record_id = :i",
                i=r["record_id"],
            )
        )
        if r["activity_id"] is not None:
            name = scalar(
                sql, "SELECT name FROM garmin.activity WHERE activity_id = :i", i=r["activity_id"]
            )
            assert r["activity_name"] == name


@pytest.mark.parametrize(
    ("metric", "sport", "column"),
    [
        ("distance", "run", "distance_m"),
        ("duration", "run", "duration_s"),
        ("elevation", "ride", "elevation_gain_m"),
    ],
)
def test_cumulative_per_day_of_year(
    client: TestClient, sql: Session, metric: str, sport: str, column: str
) -> None:
    params = {} if metric == "distance" else {"metric": metric, "sport": sport}
    resp = client.get("/api/records/cumulative", params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["metric"], body["sport_group"]) == (metric, sport)
    assert [y["year"] for y in body["years"]] == [API_END.year]
    year = body["years"][0]
    points = year["points"]
    last_doy = API_END.timetuple().tm_yday
    assert [p["day_of_year"] for p in points] == list(range(1, last_doy + 1))
    values = [p["value"] for p in points]
    assert all(a <= b for a, b in itertools.pairwise(values))
    assert values[-1] == year["total"]

    def total_until(end: date) -> float:
        return float(
            scalar(
                sql,
                f"SELECT coalesce(sum({column}), 0) FROM garmin.activity "
                "WHERE sport_group = :sport AND start_time_local >= :a AND start_time_local < :b",
                sport=sport,
                a=date(API_END.year, 1, 1),
                b=end,
            )
        )

    assert year["total"] == pytest.approx(total_until(API_END + timedelta(days=1)), abs=0.1)
    assert year["total"] > 0
    march_31 = date(API_END.year, 3, 31).timetuple().tm_yday
    assert points[march_31 - 1]["value"] == pytest.approx(
        total_until(date(API_END.year, 4, 1)), abs=0.1
    )


def test_cumulative_unknown_metric_is_rejected(client: TestClient) -> None:
    assert client.get("/api/records/cumulative", params={"metric": "steps"}).status_code == 422


@pytest.mark.parametrize(
    ("by", "column"),
    [
        ("distance", "distance_m"),
        ("duration", "duration_s"),
        ("elevation", "elevation_gain_m"),
        ("load", "training_load"),
        ("speed", "avg_speed_mps"),
    ],
)
def test_top_activities(client: TestClient, sql: Session, by: str, column: str) -> None:
    params = {} if by == "distance" else {"by": by}
    resp = client.get("/api/records/top", params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 10
    assert {"activity_id", "name", "sport_group", "start_time_local", "has_track"} <= set(body[0])
    values = [a[column] for a in body]
    assert all(a >= b for a, b in itertools.pairwise(values))
    expected = [
        r[0]
        for r in sql.execute(
            text(
                f"SELECT {column} FROM garmin.activity WHERE {column} IS NOT NULL "
                f"ORDER BY {column} DESC LIMIT 10"
            )
        )
    ]
    assert values == pytest.approx(expected)


def test_top_sport_filter_and_limits(client: TestClient, sql: Session) -> None:
    body = client.get("/api/records/top", params={"by": "speed", "sport": "run", "limit": 5}).json()
    assert len(body) == 5
    assert {a["sport_group"] for a in body} == {"run"}
    fastest = scalar(
        sql, "SELECT max(avg_speed_mps) FROM garmin.activity WHERE sport_group = 'run'"
    )
    assert body[0]["avg_speed_mps"] == pytest.approx(fastest)
    assert len(client.get("/api/records/top", params={"limit": 50}).json()) == 50
    for bad in ({"limit": 0}, {"limit": 51}, {"by": "calories"}, {"sport": "quidditch"}):
        assert client.get("/api/records/top", params=bad).status_code == 422, bad
