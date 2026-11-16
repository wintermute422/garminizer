"""Version consistency and release notes.

  release_notes.py --check     pyproject.toml and garminizer.__version__ agree and CHANGELOG.md
                               has a dated section for that version (check.sh, CI)
  release_notes.py v0.1.0      the same checks for that tag, then prints the section
                               (.github/workflows/release.yml uses it as the release text)

`--root DIR` reads another tree (tests).
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?[ \t]*$")
INIT_VERSION = re.compile(r'^__version__ = "(?P<version>[^"]+)"$', re.MULTILINE)


class ReleaseError(Exception):
    pass


def project_version(root: Path) -> str:
    """The one version of the tree; pyproject.toml and the package must agree."""
    with (root / "pyproject.toml").open("rb") as fh:
        declared = str(tomllib.load(fh)["project"]["version"])
    init = (root / "backend" / "garminizer" / "__init__.py").read_text(encoding="utf-8")
    match = INIT_VERSION.search(init)
    if match is None:
        raise ReleaseError("backend/garminizer/__init__.py has no __version__")
    if match["version"] != declared:
        raise ReleaseError(
            f"pyproject.toml says {declared}, garminizer.__version__ says {match['version']}"
        )
    return declared


def notes(root: Path, version: str) -> str:
    """The CHANGELOG.md section of ``version`` (without its heading)."""
    lines = (root / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    body: list[str] | None = None
    for line in lines:
        heading = HEADING.match(line)
        if heading is not None:
            if body is not None:
                break
            if heading["version"] == version:
                if heading["date"] is None:
                    raise ReleaseError(f"CHANGELOG.md: [{version}] has no release date")
                body = []
            continue
        if body is not None:
            # Link definitions at the end of the file are not part of the last section.
            if re.match(r"^\[[^\]]+\]: ", line):
                break
            body.append(line)
    if body is None:
        raise ReleaseError(f"CHANGELOG.md has no section for {version}")
    text = "\n".join(body).strip()
    if not text:
        raise ReleaseError(f"CHANGELOG.md: the section for {version} is empty")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", nargs="?", help="release tag, e.g. v0.1.0")
    parser.add_argument("--check", action="store_true", help="only verify the current tree")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    if bool(args.tag) == bool(args.check):
        parser.error("give either a tag or --check")
    try:
        version = project_version(args.root)
        if args.tag and args.tag != f"v{version}":
            raise ReleaseError(
                f"tag {args.tag} does not match version {version} (expected v{version})"
            )
        text = notes(args.root, version)
    except (ReleaseError, OSError, KeyError) as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print(f"release_notes: OK (version {version}, changelog section present)")
    else:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
