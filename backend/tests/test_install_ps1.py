"""install.ps1: the Windows installer, run for real against a fake `docker` on PATH.

The fake records every call and answers from a scenario file, so the tests cover what the
installer does to Docker (and what it refuses to do) without touching any container.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "install.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")

pytestmark = pytest.mark.skipif(SHELL is None, reason="PowerShell not available")

FAKE_DOCKER = r"""
import json, os, sys

args = sys.argv[1:]
with open(os.environ["FAKE_DOCKER_SCENARIO"], encoding="utf-8") as fh:
    scenario = json.load(fh)
with open(os.environ["FAKE_DOCKER_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"args": args, "cwd": os.getcwd()}) + "\n")

def answer(text="", code=0):
    sys.stdout.write(text)
    sys.exit(code)

if args[:1] == ["info"]:
    answer(code=scenario.get("info", 0))
if args[:3] == ["compose", "version", "--short"]:
    answer(scenario.get("compose_version", "2.27.0") + "\n")
if args[:2] == ["compose", "ls"]:
    answer(json.dumps(scenario.get("projects", [])))
if args[:2] == ["volume", "ls"]:
    answer("\n".join(scenario.get("volumes", [])))
if args[:2] == ["compose", "ps"]:
    answer("\n".join(scenario.get("running", [])))
if args[:2] == ["compose", "exec"]:
    answer(code=scenario.get("backup", 0))
if args[:2] == ["compose", "pull"]:
    answer(code=scenario.get("pull", 0))
if args[:2] == ["compose", "up"]:
    answer(code=scenario.get("up", 0))
answer()
"""


class Installer:
    """One sandbox: an install folder, a fake docker and a dashboard that answers /api/health."""

    def __init__(self, tmp_path: Path, port: int) -> None:
        self.dir = tmp_path / "Garminizer"
        self.menu = tmp_path / "menu"
        self.port = port
        self.log = tmp_path / "docker.log"
        self.scenario = tmp_path / "scenario.json"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "fake_docker.py"
        fake.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
        if os.name == "nt":
            (bin_dir / "docker.cmd").write_text(
                f'@"{sys.executable}" -I "{fake}" %*\r\n', encoding="utf-8", newline=""
            )
        else:
            shim = bin_dir / "docker"
            shim.write_text(
                f'#!/bin/sh\nexec "{sys.executable}" -I "{fake}" "$@"\n',
                encoding="utf-8",
                newline="\n",
            )
            shim.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DOCKER_SCENARIO": str(self.scenario),
            "FAKE_DOCKER_LOG": str(self.log),
        }
        self.env.pop("COMPOSE_PROJECT_NAME", None)

    def run(
        self, *args: str, scenario: dict[str, Any] | None = None, version: str = "0.1.0"
    ) -> subprocess.CompletedProcess[str]:
        self.scenario.write_text(json.dumps(scenario or {}), encoding="utf-8")
        assert SHELL is not None
        command = [SHELL, "-NoProfile", "-NonInteractive"]
        if os.name == "nt":
            command += ["-ExecutionPolicy", "Bypass"]
        command += ["-File", str(SCRIPT), "-InstallDir", str(self.dir), "-Source", str(ROOT)]
        command += ["-Version", version, "-ShortcutDir", str(self.menu), "-NoOpen"]
        # Never start the real Docker Desktop when the fake reports a stopped daemon. (The
        # ProgramFiles variable cannot be redirected: Windows resets it for each process.)
        command += ["-DockerDesktop", str(self.dir.parent / "no-docker-desktop.exe"), *args]
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env,
            check=False,
            timeout=300,
        )

    def install(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return self.run("-Port", str(self.port), *args, **kwargs)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return [json.loads(line)["args"] for line in lines]

    def cwds(self, *prefix: str) -> list[str]:
        lines = self.log.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        return [r["cwd"] for r in records if r["args"][: len(prefix)] == list(prefix)]

    def settings(self) -> dict[str, str]:
        text = (self.dir / ".env").read_text(encoding="utf-8")
        pairs = re.findall(r"^([A-Z_]+)=(.*)$", text, flags=re.MULTILINE)
        return dict(pairs)


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        ok = self.path == "/api/health"
        self.send_response(200 if ok else 404)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}' if ok else b"")

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def box(tmp_path: Path) -> Iterator[Installer]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield Installer(tmp_path, server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def _started(calls: list[list[str]]) -> bool:
    return any(c[:2] in (["compose", "pull"], ["compose", "up"]) for c in calls)


def test_script_is_ascii_with_lf_endings() -> None:
    raw = SCRIPT.read_bytes()
    assert raw.isascii(), "Windows PowerShell 5.1 reads a BOM-less script in the system code page"
    assert b"\r" not in raw


def test_prepare_only_writes_compose_and_env_without_docker(box: Installer) -> None:
    result = box.run("-PrepareOnly", "-TimeZone", "Europe/Berlin")
    assert result.returncode == 0, result.stdout + result.stderr
    assert box.calls() == []
    assert (box.dir / "compose.yml").read_bytes() == (ROOT / "compose.yml").read_bytes()

    raw = (box.dir / ".env").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "a byte-order mark breaks Compose's .env parser"
    assert b"\r" not in raw
    env = box.settings()
    password = env["POSTGRES_PASSWORD"]
    assert re.fullmatch(r"[A-Za-z0-9]{32}", password)
    assert re.fullmatch(r"[A-Za-z0-9]{64}", env["APP_SECRET_KEY"])
    assert env["DATABASE_URL"] == (
        f"postgresql+psycopg://garminizer:{password}@127.0.0.1:55433/garminizer"
    )
    assert env["TZ"] == "Europe/Berlin"
    assert env["GARMINIZER_VERSION"] == "0.1.0"
    assert env["APP_PORT"] == "8420"
    output = result.stdout + result.stderr
    assert password not in output
    assert env["APP_SECRET_KEY"] not in output


def test_every_installation_gets_its_own_secrets(box: Installer, tmp_path: Path) -> None:
    assert box.run("-PrepareOnly").returncode == 0
    first = box.settings()
    box.dir = tmp_path / "second"
    assert box.run("-PrepareOnly").returncode == 0
    second = box.settings()
    assert first["POSTGRES_PASSWORD"] != second["POSTGRES_PASSWORD"]
    assert first["APP_SECRET_KEY"] != second["APP_SECRET_KEY"]


def test_running_again_keeps_secrets_and_moves_the_version(box: Installer) -> None:
    assert box.run("-PrepareOnly", "-TimeZone", "Europe/Berlin").returncode == 0
    before = box.settings()
    result = box.run("-PrepareOnly", "-Port", "8421", "-DbPort", "55434", version="v0.2.0")
    assert result.returncode == 0, result.stdout + result.stderr
    after = box.settings()
    assert after["GARMINIZER_VERSION"] == "0.2.0"
    assert after["APP_PORT"] == "8421"
    assert after["DB_PORT"] == "55434"
    assert after["DATABASE_URL"] == before["DATABASE_URL"].replace(":55433/", ":55434/")
    for key in ("POSTGRES_PASSWORD", "APP_SECRET_KEY", "TZ"):
        assert after[key] == before[key]


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")
def test_docker_compose_accepts_the_generated_files(box: Installer) -> None:
    assert box.run("-PrepareOnly").returncode == 0
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=box.dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_fresh_install_pulls_starts_and_adds_the_shortcut(box: Installer) -> None:
    result = box.install()
    assert result.returncode == 0, result.stdout + result.stderr
    calls = box.calls()
    compose = [c for c in calls if c[:2] in (["compose", "pull"], ["compose", "up"])]
    assert compose == [["compose", "pull"], ["compose", "up", "-d", "--no-build"]]
    assert not any(c[:2] == ["compose", "exec"] for c in calls), "nothing to back up yet"
    assert [Path(p).resolve() for p in box.cwds("compose", "up")] == [box.dir.resolve()]
    assert f"http://localhost:{box.port}" in result.stdout
    assert box.settings()["POSTGRES_PASSWORD"] not in result.stdout + result.stderr
    shortcut = box.menu / "Garminizer.url"
    if os.name == "nt":
        assert f"URL=http://localhost:{box.port}/" in shortcut.read_text(encoding="ascii")
    else:
        assert not shortcut.exists()


def test_update_backs_up_before_pulling(box: Installer) -> None:
    assert box.install().returncode == 0
    box.log.unlink()
    here = [{"Name": "garminizer", "ConfigFiles": str(box.dir / "compose.yml")}]
    result = box.install(scenario={"projects": here, "running": ["db", "app", "worker"]})
    assert result.returncode == 0, result.stdout + result.stderr
    steps = [c[:2] for c in box.calls() if c[:2] != ["compose", "ps"] and c[0] == "compose"]
    assert steps[-3:] == [["compose", "exec"], ["compose", "pull"], ["compose", "up"]]


def test_failed_backup_stops_the_update(box: Installer) -> None:
    assert box.install().returncode == 0
    box.log.unlink()
    result = box.install(scenario={"running": ["worker"], "backup": 1})
    assert result.returncode == 1
    assert "the backup failed, so nothing was updated" in result.stdout
    assert not _started(box.calls())


def test_refuses_when_garminizer_runs_from_another_folder(box: Installer, tmp_path: Path) -> None:
    elsewhere = tmp_path / "clone" / "compose.yml"
    # Several projects, as on a real computer: Windows PowerShell 5.1 passes a JSON list down
    # the pipeline as one object, which once hid the garminizer entry behind the others.
    projects = [
        {"Name": "another-app", "ConfigFiles": str(tmp_path / "a" / "compose.yml")},
        {"Name": "garminizer", "ConfigFiles": str(elsewhere)},
        {"Name": "garminizer-dev", "ConfigFiles": str(tmp_path / "clone" / "compose.dev.yml")},
    ]
    result = box.install(scenario={"projects": projects})
    assert result.returncode == 1
    assert f"already installed in {elsewhere.parent}" in result.stdout
    assert not _started(box.calls())
    assert not box.dir.exists(), "nothing may be written next to a running installation"


def test_other_compose_projects_do_not_block(box: Installer, tmp_path: Path) -> None:
    other = {"Name": "garminizer-demo", "ConfigFiles": str(tmp_path / "x" / "compose.demo.yml")}
    assert box.install(scenario={"projects": [other]}).returncode == 0


def test_refuses_an_orphaned_database_volume(box: Installer) -> None:
    result = box.install(scenario={"volumes": ["garminizer_pgdata", "garminizer_pgdata_old"]})
    assert result.returncode == 1
    assert "earlier installation exists (Docker volume garminizer_pgdata)" in result.stdout
    assert not _started(box.calls())
    assert not box.dir.exists()


def test_a_similarly_named_volume_is_not_the_database(box: Installer) -> None:
    assert box.install(scenario={"volumes": ["garminizer_pgdata_old"]}).returncode == 0


def test_failed_pull_does_not_start_anything(box: Installer) -> None:
    result = box.install(scenario={"pull": 1})
    assert result.returncode == 1
    assert "could not be downloaded" in result.stdout
    assert not any(c[:2] == ["compose", "up"] for c in box.calls())


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ({"info": 1}, "Docker is installed but not running"),
        ({"compose_version": "2.20.3"}, "Docker Compose 2.24.0 or newer is needed"),
    ],
)
def test_docker_problems_are_explained(
    box: Installer, scenario: dict[str, Any], message: str
) -> None:
    result = box.install(scenario=scenario)
    assert result.returncode == 1
    assert message in result.stdout
    assert not box.dir.exists()


def test_missing_release_files_fail_before_anything_is_written(
    box: Installer, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert SHELL is not None
    command = [SHELL, "-NoProfile", "-NonInteractive"]
    if os.name == "nt":
        command += ["-ExecutionPolicy", "Bypass"]
    command += ["-File", str(SCRIPT), "-InstallDir", str(box.dir), "-Source", str(empty)]
    command += ["-Version", "0.1.0", "-PrepareOnly"]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=box.env, check=False
    )
    assert result.returncode == 1
    assert "compose.yml not found" in result.stdout
    assert not box.dir.exists()
