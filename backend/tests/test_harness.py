"""The harness rules in scripts/claude_hook.py block what they promise to block."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "claude_hook", ROOT / "scripts" / "claude_hook.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["claude_hook"] = module
    spec.loader.exec_module(module)
    return module


HOOK = _load_hook()


@pytest.mark.parametrize("command", HOOK.SELFTEST_BLOCKED)
def test_blocked(command: str) -> None:
    assert HOOK.blocked_reason(command) is not None


@pytest.mark.parametrize("command", HOOK.SELFTEST_ALLOWED)
def test_allowed(command: str) -> None:
    assert HOOK.blocked_reason(command) is None


def test_pre_bash_exit_code() -> None:
    assert HOOK.pre_bash({"tool_input": {"command": "git push --force"}}) == 2
    assert HOOK.pre_bash({"tool_input": {"command": "git status"}}) == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_shell_wrapper_passes_exit_code_through() -> None:
    """The bug this guards against: `python ... || python3 ...` turned exit 2 into 49."""
    wrapper = (ROOT / "scripts" / "claude_hook.sh").as_posix()
    blocked = json.dumps({"tool_input": {"command": "git push --force origin x"}})
    allowed = json.dumps({"tool_input": {"command": "git status"}})
    # The bash that skipif found: on Windows a bare "bash" resolves System32 (WSL) before PATH.
    bash = shutil.which("bash")
    assert bash is not None
    run = partial(subprocess.run, capture_output=True, text=True, check=False, cwd=ROOT)
    assert run([bash, wrapper, "pre-bash"], input=blocked).returncode == 2
    assert run([bash, wrapper, "pre-bash"], input=allowed).returncode == 0
