"""MCP server (`garminizer mcp`): tools through the SDK client, and a real stdio process.

Claude Desktop reads the protocol from the server's stdout, so a single stray print breaks the
connection: the subprocess tests assert that stdout carries nothing but JSON-RPC.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import anyio
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from garminizer import models as m
from garminizer.db import migrate
from garminizer.mcp_server import build_server, parse_day, parse_eaten_at
from tests.conftest import create_fresh_database

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)  # 13:00 in Berlin
TODAY = date(2026, 3, 11)
BURN = 2900.0
TOOLS = {
    "log_meal",
    "get_day_nutrition",
    "list_recent_meals",
    "update_meal",
    "delete_meal",
    "get_nutrition_targets",
    "set_nutrition_targets",
    "get_energy_context",
    "get_energy_balance",
    "get_weight_goal",
    "set_weight_goal",
    "set_checkpoint",
}
LUNCH = {
    "name": "Spaghetti with tomato sauce",
    "eaten_at": "12:30",
    "items": [
        {
            "food": "Spaghetti, cooked",
            "grams": 180,
            "kcal": 284,
            "protein_g": 10.4,
            "carbs_g": 55.6,
            "fat_g": 1.6,
            "fiber_g": 3.2,
        },
        {
            "food": "Olive oil",
            "amount": 1,
            "unit": "tbsp",
            "grams": 10,
            "kcal": 88,
            "protein_g": 0,
            "carbs_g": 0,
            "fat_g": 10,
        },
        {
            "food": "Tomato sauce",
            "grams": 150,
            "kcal": 75,
            "protein_g": 2.4,
            "carbs_g": 12,
            "fat_g": 2.3,
            "fiber_g": 2.9,
        },
    ],
    "notes": "Assumed 1 tbsp oil.",
    "confidence": "medium",
}


@pytest.fixture(scope="module")
def mcp_url() -> str:
    url = create_fresh_database("_mcp")
    migrate.upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    with Session(engine) as s:
        s.add(m.Athlete(id=1, time_zone="Europe/Berlin", weight_kg=70.0, is_demo=False))
        s.add(m.DailySummary(day=TODAY, total_kcal=BURN, active_kcal=900, bmr_kcal=2000))
        s.add(m.DailySummary(day=TODAY - timedelta(days=1), total_kcal=2500))
        s.add(
            m.Activity(
                activity_id=1,
                name="Morning run",
                sport_type="running",
                sport_group="run",
                start_time_utc=datetime(2026, 3, 11, 6, 0, tzinfo=UTC),
                start_time_local=datetime(2026, 3, 11, 7, 0),
                duration_s=3600,
                distance_m=12000,
                calories=800,
                training_load=120,
            )
        )
        s.commit()
    engine.dispose()
    return url


@pytest.fixture(scope="module")
def engine(mcp_url: str) -> Iterator[Engine]:
    eng = create_engine(mcp_url, poolclass=NullPool)
    yield eng
    eng.dispose()


@pytest.fixture
def server(engine: Engine) -> MCPServer[Any]:
    with engine.begin() as conn:  # every test starts with an empty food diary
        conn.execute(text("TRUNCATE garmin.meal, garmin.meal_item RESTART IDENTITY"))
        conn.execute(
            text("DELETE FROM garmin.app_setting WHERE key IN ('nutrition_targets', 'weight_goal')")
        )
    return build_server(
        sessionmaker(engine, expire_on_commit=False), fallback_tz="UTC", clock=lambda: NOW
    )


def _text(result: CallToolResult) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text


def call(server: MCPServer[Any], name: str, args: dict[str, Any] | None = None) -> Any:
    """Call a tool through the SDK client (initialize handshake, like Claude Desktop)."""

    async def go() -> CallToolResult:
        async with Client(server, mode="legacy") as client:
            return await client.call_tool(name, args or {})

    result = anyio.run(go)
    assert not result.is_error, _text(result)
    return json.loads(_text(result))


def call_error(server: MCPServer[Any], name: str, args: dict[str, Any]) -> str:
    async def go() -> CallToolResult:
        async with Client(server, mode="legacy") as client:
            return await client.call_tool(name, args)

    result = anyio.run(go)
    assert result.is_error
    return _text(result)


def _meals(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM garmin.meal ORDER BY meal_id")).mappings()
        return [dict(r) for r in rows]


# --- discovery -------------------------------------------------------------------------------


def test_tools_prompt_and_descriptions(server: MCPServer[Any]) -> None:
    async def go() -> tuple[Any, Any, Any]:
        async with Client(server, mode="legacy") as client:
            tools = await client.list_tools()
            prompts = await client.list_prompts()
            prompt = await client.get_prompt("log-meal-from-photo", {"details": "no dressing"})
            return tools, prompts, prompt

    tools, prompts, prompt = anyio.run(go)
    by_name = {t.name: t for t in tools.tools}
    assert set(by_name) == TOOLS
    log_meal = by_name["log_meal"]
    for phrase in ("grams", "USDA", "oil", "notes", "confidence", "update_meal"):
        assert phrase in (log_meal.description or ""), phrase
    schema = log_meal.input_schema
    assert schema["required"] == ["name"]
    item = schema["$defs"]["NutritionItemIn"]
    assert set(item["required"]) == {"food", "kcal"}
    assert item["additionalProperties"] is False
    assert by_name["get_day_nutrition"].annotations.read_only_hint is True
    assert by_name["delete_meal"].annotations.destructive_hint is True
    assert [p.name for p in prompts.prompts] == ["log-meal-from-photo"]
    message = prompt.messages[0].content
    assert isinstance(message, TextContent)
    assert "log_meal" in message.text
    assert "no dressing" in message.text


# --- logging ---------------------------------------------------------------------------------


def test_log_meal_lands_in_db_and_returns_the_day(server: MCPServer[Any], engine: Engine) -> None:
    out = call(server, "log_meal", LUNCH)
    assert out["stored"] is True
    meal = out["meal"]
    assert meal["kcal"] == pytest.approx(447.0)
    assert meal["protein_g"] == pytest.approx(12.8)
    assert meal["meal_type"] == "lunch"
    assert meal["eaten_at"] == "2026-03-11T12:30:00+01:00"
    assert out["warnings"] == []
    day = out["day_summary"]
    assert day["day"] == TODAY.isoformat()
    assert day["is_today"] is True
    assert day["totals"]["kcal"] == pytest.approx(447.0)
    assert day["garmin"]["total_kcal"] == BURN
    assert day["balance_kcal"] == pytest.approx(447.0 - BURN)
    balance = out["energy_balance"]
    assert balance["intake_kcal"] == pytest.approx(447.0)
    assert balance["bmr"]["source"] == "garmin"  # the test athlete has no sex/height/birth
    assert balance["baseline_kcal"] == 2500  # Garmin BMR 2000 x 1.25
    assert balance["goal_configured"] is False

    rows = _meals(engine)
    assert len(rows) == 1
    assert rows[0]["source"] == "claude"
    assert rows[0]["day"] == TODAY
    assert rows[0]["notes"] == "Assumed 1 tbsp oil."
    with engine.connect() as conn:
        items = conn.execute(text("SELECT count(*), sum(kcal) FROM garmin.meal_item")).one()
    assert items[0] == 3
    assert items[1] == pytest.approx(rows[0]["kcal"], abs=0.1)

    second = call(
        server,
        "log_meal",
        {
            "name": "Protein bar",
            "totals": {"kcal": 210, "protein_g": 20, "carbs_g": 22, "fat_g": 7},
        },
    )
    assert second["meal"]["meal_type"] == "lunch"  # now = 13:00 local
    assert second["day_summary"]["totals"]["meals"] == 2
    assert second["day_summary"]["totals"]["kcal"] == pytest.approx(657.0)


def test_mismatch_is_stored_with_a_warning(server: MCPServer[Any], engine: Engine) -> None:
    out = call(
        server,
        "log_meal",
        {"name": "Odd", "totals": {"kcal": 200, "protein_g": 30, "carbs_g": 40, "fat_g": 15}},
    )
    assert [w["code"] for w in out["warnings"]] == ["macro_kcal_mismatch"]
    assert len(_meals(engine)) == 1


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        ({"name": "Nothing"}, "totals.kcal"),
        ({"name": "Neg", "items": [{"food": "x", "kcal": -5}]}, "kcal"),
        ({"name": "Typo", "items": [{"food": "x", "kcal": 50, "protien_g": 3}]}, "protien_g"),
        ({"name": "Later", "totals": {"kcal": 100}, "eaten_at": "2026-03-12T09:00"}, "future"),
        ({"name": "When", "totals": {"kcal": 100}, "eaten_at": "lunchtime"}, "HH:MM"),
        ({"name": "Date", "totals": {"kcal": 100}, "eaten_at": "2026-03-10"}, "no time"),
        ({"name": "Type", "totals": {"kcal": 100}, "meal_type": "brunch"}, "meal_type"),
    ],
)
def test_bad_input_is_explained_to_claude(
    server: MCPServer[Any], engine: Engine, args: dict[str, Any], needle: str
) -> None:
    assert needle in call_error(server, "log_meal", args)
    assert _meals(engine) == []


def test_time_parsing() -> None:
    late = datetime(2026, 3, 10, 23, 30, tzinfo=UTC)  # 00:30 on 11 March in Berlin
    assert parse_eaten_at("20:15", BERLIN, late) == datetime(2026, 3, 10, 20, 15, tzinfo=BERLIN)
    assert parse_eaten_at("00:10", BERLIN, late) == datetime(2026, 3, 11, 0, 10, tzinfo=BERLIN)
    assert parse_eaten_at("2026-03-09T08:00", BERLIN, late) == datetime(2026, 3, 9, 8, 0)
    assert parse_eaten_at("2026-03-09T08:00Z", BERLIN, late) == datetime(
        2026, 3, 9, 8, 0, tzinfo=UTC
    )
    assert parse_eaten_at(None, BERLIN, late) is None
    assert parse_eaten_at("  ", BERLIN, late) is None
    with pytest.raises(ToolError):
        parse_eaten_at("25:00", BERLIN, late)
    assert parse_day(None, BERLIN, late) == date(2026, 3, 11)
    assert parse_day("Yesterday", BERLIN, late) == date(2026, 3, 10)
    assert parse_day("2026-02-01", BERLIN, late) == date(2026, 2, 1)
    with pytest.raises(ToolError):
        parse_day("soon", BERLIN, late)


# --- reading, correcting, deleting -----------------------------------------------------------


def test_list_update_and_delete(server: MCPServer[Any], engine: Engine) -> None:
    first = call(server, "log_meal", LUNCH)["meal"]["meal_id"]
    call(
        server,
        "log_meal",
        {"name": "Porridge", "eaten_at": "2026-03-10T07:30", "totals": {"kcal": 420}},
    )
    recent = call(server, "list_recent_meals", {"days": 2})
    assert recent["meals"] == 2
    assert [d["day"] for d in recent["days"]] == ["2026-03-11", "2026-03-10"]
    lunch = recent["days"][0]["meals"][0]
    assert lunch["meal_id"] == first
    assert lunch["time"] == "12:30"
    assert lunch["items"][0] == "Spaghetti, cooked (180 g): 284 kcal"
    assert call(server, "list_recent_meals", {"days": 1})["meals"] == 1

    new_items = [
        {
            "food": "Spaghetti, cooked",
            "grams": 250,
            "kcal": 395,
            "protein_g": 14.5,
            "carbs_g": 77.3,
            "fat_g": 2.3,
        }
    ]
    upd = call(server, "update_meal", {"meal_id": first, "items": new_items, "confidence": "high"})
    assert upd["updated"] is True
    assert upd["meal"]["kcal"] == 395
    assert upd["meal"]["confidence"] == "high"
    assert upd["meal"]["notes"] == "Assumed 1 tbsp oil."  # untouched
    assert upd["day_summary"]["totals"]["kcal"] == 395

    gone = call(server, "delete_meal", {"meal_id": first})
    assert gone["deleted"]["meal_id"] == first
    assert gone["day_summary"]["totals"]["meals"] == 0
    assert [r["name"] for r in _meals(engine)] == ["Porridge"]
    assert "list_recent_meals" in call_error(server, "delete_meal", {"meal_id": first})
    assert "list_recent_meals" in call_error(server, "update_meal", {"meal_id": 99, "name": "x"})


def test_get_day_nutrition(server: MCPServer[Any]) -> None:
    call(server, "log_meal", LUNCH)
    today = call(server, "get_day_nutrition")
    assert today["day"] == TODAY.isoformat()
    assert [x["name"] for x in today["meals"]] == [LUNCH["name"]]
    assert len(today["meals"][0]["items"]) == 3
    yesterday = call(server, "get_day_nutrition", {"day": "yesterday"})
    assert yesterday["meals"] == []
    assert yesterday["garmin"]["total_kcal"] == 2500
    assert "not a date" in call_error(server, "get_day_nutrition", {"day": "someday"})


def test_targets(server: MCPServer[Any]) -> None:
    empty = call(server, "get_nutrition_targets")
    assert empty["targets"]["kcal"] is None
    assert empty["weight_kg"] == 70.0
    assert empty["garmin_avg_total_kcal_28d"] == round((BURN + 2500) / 2)
    saved = call(server, "set_nutrition_targets", {"kcal": 2700, "protein_g_per_kg": 1.8})
    assert saved["saved"] is True
    assert saved["protein_target_g"] == 126  # 1.8 g/kg x 70 kg
    merged = call(server, "set_nutrition_targets", {"fiber_g": 35})
    assert (merged["targets"]["kcal"], merged["targets"]["fiber_g"]) == (2700, 35)
    cleared = call(server, "set_nutrition_targets", {"clear": ["kcal"]})
    assert cleared["targets"]["kcal"] is None
    assert "unknown target" in call_error(server, "set_nutrition_targets", {"clear": ["salt"]})
    assert call_error(server, "set_nutrition_targets", {"kcal": -5})
    day = call(server, "log_meal", LUNCH)["day_summary"]
    assert day["protein_target_g"] == 126
    assert day["remaining"]["protein_g"] == pytest.approx(126 - 12.8)


def test_energy_context(server: MCPServer[Any]) -> None:
    call(server, "log_meal", LUNCH)
    ctx = call(server, "get_energy_context")
    assert ctx["garmin"]["total_kcal"] == BURN
    assert [a["name"] for a in ctx["activities"]] == ["Morning run"]
    assert ctx["avg_total_kcal_7d"] == 2500
    assert ctx["intake"]["kcal"] == pytest.approx(447.0)
    assert ctx["balance_kcal"] == pytest.approx(447.0 - BURN)
    assert ctx["demo_data"] is False


# --- weight goal -----------------------------------------------------------------------------


def test_weight_goal_tools(server: MCPServer[Any]) -> None:
    assert call(server, "get_weight_goal")["configured"] is False
    assert "start_day" in call_error(server, "set_weight_goal", {"rate_kg_per_week": 0.5})
    saved = call(
        server,
        "set_weight_goal",
        {
            "start_day": (TODAY - timedelta(days=10)).isoformat(),
            "start_weight_kg": 71.0,
            "rate_kg_per_week": 0.5,
            "end_day": (TODAY + timedelta(days=60)).isoformat(),
            "sex": "Male",
            "height_cm": 178,
            "birth_date": "1990-01-01",
        },
    )
    assert saved["saved"] is True and saved["configured"] is True
    assert saved["settings"]["sex"] == "male"
    assert saved["target_daily_balance_kcal"] == -550
    assert saved["bmr_today"]["source"] == "formulas"
    changed = call(server, "set_weight_goal", {"rate_kg_per_week": 0.25})
    assert changed["settings"]["start_weight_kg"] == 71.0  # unchanged
    assert changed["target_daily_balance_kcal"] == -275
    goal = call(server, "get_weight_goal", {"days": 3})
    assert len(goal["recent_days"]) == 3
    assert goal["recent_days"][0]["day"] == TODAY.isoformat()
    sunday = goal["checkpoints"][0]["day"]
    accepted = call(server, "set_checkpoint", {"day": sunday})
    assert accepted["settings"]["accepted_checkpoints"] == [sunday]
    assert "not a checkpoint" in call_error(
        server, "set_checkpoint", {"day": (TODAY + timedelta(days=1)).isoformat()}
    )


def test_energy_balance_tool(server: MCPServer[Any]) -> None:
    call(server, "log_meal", LUNCH)
    bal = call(server, "get_energy_balance")
    assert (bal["day"], bal["is_today"], bal["as_of"]) == (TODAY.isoformat(), True, "13:00")
    assert [a["name"] for a in bal["activities"]] == ["Morning run"]
    # no bmrCalories stored: the resting share is BMR / 24 h over the hour
    assert bal["training_kcal"] == round(800 - 2000 / 24)
    assert bal["burn_kcal"] == bal["baseline_kcal"] + bal["training_kcal"]
    assert bal["balance_kcal"] == round(447.0 - bal["burn_kcal"])
    assert bal["garmin_total_kcal"] == BURN
    yesterday = call(server, "get_energy_balance", {"day": "yesterday"})
    assert yesterday["is_today"] is False and yesterday["meals"] == 0


# --- stdout hygiene and the real stdio transport ---------------------------------------------


def _env(url: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "TZ"}}
    env["DATABASE_URL"] = url
    env["PYTHONUNBUFFERED"] = "1"
    return env


def test_import_and_build_write_nothing_to_stdout(mcp_url: str, tmp_path: Path) -> None:
    code = (
        "import garminizer.mcp_server as s\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import sessionmaker\n"
        "import os\n"
        "server = s.build_server(sessionmaker(create_engine(os.environ['DATABASE_URL'])))\n"
        "assert server.name == 'garminizer'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,  # no .env here
        env=_env(mcp_url),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode(errors="replace")
    assert proc.stdout == b""


class _StdioPeer:
    """A JSON-RPC peer on a child's stdin/stdout; a thread collects every stdout line."""

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self.proc = proc
        self.lines: queue.Queue[bytes | None] = queue.Queue()
        self.raw: list[bytes] = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.raw.append(line)
            self.lines.put(line)
        self.lines.put(None)

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()

    def response(self, msg_id: int, timeout: float = 90) -> dict[str, Any]:
        while True:
            line = self.lines.get(timeout=timeout)
            assert line is not None, "server closed stdout"
            message = cast(dict[str, Any], json.loads(line))
            if message.get("id") == msg_id:
                return message


def test_stdio_server_speaks_only_json_rpc(mcp_url: str, engine: Engine, tmp_path: Path) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE garmin.meal, garmin.meal_item RESTART IDENTITY"))
    stderr = (tmp_path / "stderr.log").open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "garminizer.cli", "mcp"],
        cwd=tmp_path,
        env=_env(mcp_url),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
    )
    peer = _StdioPeer(proc)
    try:
        peer.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            }
        )
        init = peer.response(1)
        assert init["result"]["serverInfo"]["name"] == "garminizer"
        assert init["result"]["protocolVersion"] == "2025-06-18"
        assert "tools" in init["result"]["capabilities"]
        peer.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        peer.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in peer.response(2)["result"]["tools"]}
        assert names == TOOLS
        args = {**LUNCH, "eaten_at": "2026-03-11T12:30"}
        peer.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "log_meal", "arguments": args},
            }
        )
        result = peer.response(3)["result"]
        assert result["isError"] is False
        stored = json.loads(result["content"][0]["text"])
        assert stored["meal"]["kcal"] == pytest.approx(447.0)
        assert stored["day_summary"]["garmin"]["total_kcal"] == BURN
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        try:
            proc.wait(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill()
            stderr.close()
    deadline = datetime.now(UTC) + timedelta(seconds=10)
    while datetime.now(UTC) < deadline:  # let the reader thread drain stdout
        try:
            if peer.lines.get(timeout=1) is None:
                break
        except queue.Empty:
            continue
    log = (tmp_path / "stderr.log").read_text(encoding="utf-8", errors="replace")
    assert proc.returncode == 0, log
    assert peer.raw, "no output"
    for line in peer.raw:
        message = json.loads(line)  # anything else on stdout would break Claude Desktop
        assert message["jsonrpc"] == "2.0"
    assert "ready (stdio)" in log  # logging went to stderr
    rows = _meals(engine)
    assert [(r["name"], r["source"]) for r in rows] == [(LUNCH["name"], "claude")]
