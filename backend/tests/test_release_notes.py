"""scripts/release_notes.py: one version everywhere, and a changelog section for it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release_notes.py"

CHANGELOG = """# Changelog

## [Unreleased]

- not released yet

## [1.2.0] - 2026-03-04

### Added
- second release

## [1.1.0] - 2026-02-01

- first release

[1.2.0]: https://example.invalid/compare/v1.1.0...v1.2.0
"""


def _tree(
    tmp_path: Path, *, declared: str = "1.2.0", package: str = "1.2.0", log: str = CHANGELOG
) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{declared}"\n', encoding="utf-8", newline="\n"
    )
    pkg = tmp_path / "backend" / "garminizer"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        f'"""x"""\n\n__version__ = "{package}"\n', encoding="utf-8", newline="\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(log, encoding="utf-8", newline="\n")
    return tmp_path


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_the_repository_itself_is_consistent() -> None:
    result = _run(ROOT, "--check")
    assert result.returncode == 0, result.stderr


def test_prints_only_the_section_of_the_tag(tmp_path: Path) -> None:
    result = _run(_tree(tmp_path), "v1.2.0")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "### Added\n- second release"


def test_last_section_stops_before_the_link_definitions(tmp_path: Path) -> None:
    result = _run(_tree(tmp_path, declared="1.1.0", package="1.1.0"), "v1.1.0")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "- first release"


@pytest.mark.parametrize(
    ("kwargs", "args", "message"),
    [
        ({"package": "1.1.0"}, ["--check"], "pyproject.toml says 1.2.0"),
        ({"declared": "1.3.0", "package": "1.3.0"}, ["--check"], "no section for 1.3.0"),
        ({}, ["v1.1.0"], "tag v1.1.0 does not match version 1.2.0"),
        ({}, ["1.2.0"], "expected v1.2.0"),
        (
            {"log": "# Changelog\n\n## [1.2.0]\n\n- undated\n"},
            ["--check"],
            "has no release date",
        ),
        (
            {"log": "# Changelog\n\n## [1.2.0] - 2026-03-04\n\n## [1.1.0] - 2026-02-01\n- x\n"},
            ["--check"],
            "is empty",
        ),
    ],
)
def test_inconsistencies_fail(
    tmp_path: Path, kwargs: dict[str, str], args: list[str], message: str
) -> None:
    result = _run(_tree(tmp_path, **kwargs), *args)
    assert result.returncode == 1
    assert message in result.stderr
    assert result.stdout == ""
