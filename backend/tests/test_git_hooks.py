"""The git pre-commit hook blocks secrets and personal data (run in a throwaway repo)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None, reason="git/bash not available"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    for item in (".githooks", "scripts"):
        shutil.copytree(ROOT / item, tmp_path / item)
    for item in (".gitignore", ".gitleaks.toml"):
        shutil.copy2(ROOT / item, tmp_path / item)
    _git(tmp_path, "config", "core.hooksPath", ".githooks")
    return tmp_path


def test_env_file_is_blocked(repo: Path) -> None:
    (repo / ".env").write_bytes(b"APP_PASSWORD=change-me\n")
    _git(repo, "add", "--force", ".env")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "forbidden files staged" in proc.stderr


def test_ignored_file_is_blocked(repo: Path) -> None:
    (repo / "plan.md").write_bytes(b"local facts\n")
    _git(repo, "add", "--force", "plan.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "git-ignored files staged" in proc.stderr


def test_private_ip_is_blocked(repo: Path) -> None:
    private_ip = ".".join(["192", "168", "1", "20"])  # assembled so this file stays clean
    (repo / "config.txt").write_bytes(f"host = {private_ip}\n".encode())  # LF, not CRLF
    _git(repo, "add", "config.txt")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "private-ipv4" in proc.stderr


def _private_values(repo: Path, *values: str) -> None:
    (repo / "data").mkdir(exist_ok=True)
    (repo / "data" / "private_values.txt").write_text("\n".join(values) + "\n", encoding="utf-8")


def test_private_value_is_blocked(repo: Path) -> None:
    _private_values(repo, "Synthetic Person Name")
    (repo / "notes.md").write_bytes(b"written by Synthetic Person Name\n")
    _git(repo, "add", "notes.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "exact value" in proc.stderr
    assert "Synthetic Person Name" not in proc.stderr + proc.stdout  # values are never printed


def test_repository_owner_is_exempt_but_other_values_are_not(repo: Path) -> None:
    _private_values(repo, "synthetic-handle-42", "Synthetic Person Name")
    _git(repo, "remote", "add", "origin", "https://github.com/Synthetic-Handle-42/garminizer.git")
    (repo / "README.md").write_bytes(b"git clone https://github.com/synthetic-handle-42/x\n")
    _git(repo, "add", "README.md")
    proc = _git(repo, "commit", "-m", "readme")
    assert proc.returncode == 0, proc.stderr
    (repo / "notes.md").write_bytes(b"written by Synthetic Person Name\n")
    _git(repo, "add", "notes.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "exact value" in proc.stderr


def test_screenshots_need_the_manifest(repo: Path) -> None:
    shots = repo / "docs" / "screenshots"
    shots.mkdir(parents=True)
    (shots / "page-dark.png").write_bytes(b"\x89PNG not really\n")
    (shots / "MANIFEST.sha256").write_bytes(b"")
    _git(repo, "add", "docs")
    proc = _git(repo, "commit", "-m", "unlisted screenshot")
    assert proc.returncode != 0
    assert "MANIFEST" in proc.stderr
    digest = hashlib.sha256((shots / "page-dark.png").read_bytes()).hexdigest()
    for line in (f"{digest}  page-dark.png\n", f"{digest} *page-dark.png\n"):  # text / binary
        (shots / "MANIFEST.sha256").write_text(line, encoding="utf-8", newline="\n")
        _git(repo, "add", "docs")
        proc = _git(repo, "commit", "-m", "listed screenshot")
        assert proc.returncode == 0, proc.stderr
        _git(repo, "reset", "-q", "--soft", "HEAD~1")


def test_non_utf8_and_crlf_are_blocked(repo: Path) -> None:
    (repo / "notes.md").write_bytes("dash — here\n".encode("cp1252"))
    _git(repo, "add", "notes.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "not UTF-8" in proc.stderr
    (repo / "notes.md").write_bytes(b"line one\r\nline two\r\n")
    _git(repo, "add", "notes.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "CRLF" in proc.stderr
