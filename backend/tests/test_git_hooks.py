"""The git pre-commit hook blocks secrets and personal data (run in a throwaway repo)."""

from __future__ import annotations

import hashlib
import os
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


def _personal_address() -> str:
    return "@".join(["synthetic.person", "mailbox.test"])  # assembled so this file stays clean


def _history_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")  # a bare "bash" resolves System32 (WSL) first on Windows
    assert bash is not None
    return subprocess.run(
        [bash, "scripts/secret_scan.sh", "--history"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_commit_identity_with_a_personal_address_is_blocked(repo: Path) -> None:
    (repo / "notes.md").write_bytes(b"harmless\n")
    _git(repo, "add", "notes.md")
    proc = _git(repo, "-c", f"user.email={_personal_address()}", "commit", "-m", "test")
    assert proc.returncode != 0
    assert "ident:staged" in proc.stderr and "email" in proc.stderr
    assert _personal_address() not in proc.stderr + proc.stdout
    assert _git(repo, "commit", "-m", "test").returncode == 0  # noreply-style identity passes


def test_history_scan_checks_identities_and_only_dependabots_signoff(repo: Path) -> None:
    (repo / "notes.md").write_bytes(b"harmless\n")
    _git(repo, "add", "notes.md")
    signoff = "Bump x\n\nSigned-off-by: dependabot[bot] <support@github.com>"
    assert _git(repo, "commit", "-m", signoff).returncode == 0
    assert _history_scan(repo).returncode == 0, _history_scan(repo).stderr

    other = "@".join(["support", "github.com"])  # the same address outside Dependabot's sign-off
    message = f"Bump y\n\nSigned-off-by: someone <{other}>"
    assert _git(repo, "commit", "--allow-empty", "-m", message).returncode == 0
    proc = _history_scan(repo)
    assert proc.returncode != 0
    assert "msg:" in proc.stderr and "email" in proc.stderr
    _git(repo, "reset", "-q", "--hard", "HEAD~1")

    # a commit made without hooks (e.g. a web merge) with a personal author address
    no_hooks = ("-c", "core.hooksPath=no-hooks", "-c", f"user.email={_personal_address()}")
    assert _git(repo, *no_hooks, "commit", "--allow-empty", "-m", "merge").returncode == 0
    proc = _history_scan(repo)
    assert proc.returncode != 0
    assert "ident:" in proc.stderr and "email" in proc.stderr
    assert _personal_address() not in proc.stderr + proc.stdout


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


def _fake_tool(directory: Path, name: str, body: str) -> None:
    """A stand-in executable on PATH (bash script) so tests control what gitleaks reports."""
    directory.mkdir(exist_ok=True)
    tool = directory / name
    tool.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8", newline="\n")
    tool.chmod(0o755)


def _gitleaks_sh(
    repo: Path, fakes: Path, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    assert bash is not None
    env = {**os.environ, "PATH": f"{fakes}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [bash, str(repo / "scripts" / "gitleaks.sh"), *args],
        cwd=cwd or repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


GITLEAKS_LOG_EMPTY = "0 commits scanned.\nscanned ~0 bytes (0) in 40ms\nno leaks found"
GITLEAKS_LOG_HISTORY = "2 commits scanned.\nscanned ~120 bytes (120) in 40ms\nno leaks found"
GITLEAKS_LOG_STAGED = "0 commits scanned.\nscanned ~35 bytes (35) in 40ms\nno leaks found"


@pytest.mark.parametrize(
    ("mode", "log", "ok"),
    [
        ("history", GITLEAKS_LOG_EMPTY, False),  # the vacuous "no leaks found" of a broken mount
        ("history", "no leaks found", False),  # no count reported at all
        ("history", GITLEAKS_LOG_HISTORY, True),
        ("staged", GITLEAKS_LOG_EMPTY, False),
        ("staged", GITLEAKS_LOG_STAGED, True),  # --pre-commit always says "0 commits"
        ("range", GITLEAKS_LOG_EMPTY, False),
        ("range", GITLEAKS_LOG_HISTORY, True),
    ],
)
def test_gitleaks_never_passes_on_an_empty_scan(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, mode: str, log: str, ok: bool
) -> None:
    no_hooks = ("-c", "core.hooksPath=no-hooks")
    (repo / "notes.md").write_bytes(b"harmless\n")
    _git(repo, "add", "notes.md")
    assert _git(repo, *no_hooks, "commit", "-m", "one").returncode == 0
    (repo / "notes.md").write_bytes(b"harmless, twice\n")
    _git(repo, "add", "notes.md")
    if mode != "staged":
        assert _git(repo, *no_hooks, "commit", "-m", "two").returncode == 0
    (repo / "fake.log").write_text(log, encoding="utf-8", newline="\n")
    fakes = tmp_path_factory.mktemp("fakes")
    _fake_tool(fakes, "gitleaks", f'cat "{(repo / "fake.log").as_posix()}" >&2')
    args = ("range", "HEAD~1..HEAD") if mode == "range" else (mode,)
    proc = _gitleaks_sh(repo, fakes, *args)
    assert (proc.returncode == 0) is ok, proc.stderr
    if not ok:
        assert "gitleaks.sh: FAIL" in proc.stderr


@pytest.mark.skipif(shutil.which("gitleaks") is not None, reason="native gitleaks preferred")
def test_gitleaks_docker_mounts_the_git_dir_of_a_worktree(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    no_hooks = ("-c", "core.hooksPath=no-hooks")
    (repo / "notes.md").write_bytes(b"harmless\n")
    _git(repo, "add", "--all")
    assert _git(repo, *no_hooks, "commit", "-m", "one").returncode == 0
    worktree = tmp_path_factory.mktemp("worktree") / "wt"
    assert _git(repo, "worktree", "add", "-q", str(worktree)).returncode == 0
    fakes = tmp_path_factory.mktemp("fakes")
    argfile = (fakes / "docker.args").as_posix()
    _fake_tool(fakes, "docker", f'printf "%s\\n" "$@" > "{argfile}"; echo "1 commits scanned." >&2')
    proc = _gitleaks_sh(worktree, fakes, "history", cwd=worktree)
    assert proc.returncode == 0, proc.stderr
    docker_args = (fakes / "docker.args").read_text(encoding="utf-8").splitlines()
    assert "GIT_DIR=/gitcommon/worktrees/wt" in docker_args
    assert "GIT_WORK_TREE=/repo" in docker_args
    assert any(a.endswith("/.git:/gitcommon") for a in docker_args), docker_args
