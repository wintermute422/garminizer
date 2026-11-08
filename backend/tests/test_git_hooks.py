"""The git pre-commit hook blocks secrets and personal data (run in a throwaway repo)."""

from __future__ import annotations

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
    (repo / ".env").write_text("APP_PASSWORD=change-me\n")
    _git(repo, "add", "--force", ".env")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "forbidden files staged" in proc.stderr


def test_ignored_file_is_blocked(repo: Path) -> None:
    (repo / "plan.md").write_text("local facts\n")
    _git(repo, "add", "--force", "plan.md")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "git-ignored files staged" in proc.stderr


def test_private_ip_is_blocked(repo: Path) -> None:
    private_ip = ".".join(["192", "168", "1", "20"])  # assembled so this file stays clean
    (repo / "config.txt").write_text(f"host = {private_ip}\n")
    _git(repo, "add", "config.txt")
    proc = _git(repo, "commit", "-m", "test")
    assert proc.returncode != 0
    assert "private-ipv4" in proc.stderr
