"""install.cmd: the double-click wrapper around install.ps1.

It must download the script to a file and run that file. A command line that pipes a download
into PowerShell (`powershell -Command "irm <url> | iex"`) is blocked by Windows Defender as
Trojan:Win32/Commando.B!ml, which is what the first version of this wrapper did.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "install.cmd"

windows_only = pytest.mark.skipif(os.name != "nt", reason="cmd.exe is Windows only")


def test_wrapper_is_ascii_with_lf_endings_and_without_labels() -> None:
    raw = WRAPPER.read_bytes()
    assert raw.isascii()
    assert b"\r" not in raw
    # cmd.exe can miss labels in files with LF endings, so the wrapper must not jump.
    assert not re.search(r"(?mi)^\s*:|\bgoto\b|\bcall\s+:", raw.decode("ascii"))


def test_wrapper_does_not_pipe_a_download_into_powershell() -> None:
    commands = [
        line.lower()
        for line in WRAPPER.read_text(encoding="ascii").splitlines()
        if not line.lower().startswith("rem")
    ]
    text = "\n".join(commands)
    for banned in (
        "iex",
        "invoke-expression",
        "irm ",
        "invoke-restmethod",
        "invoke-webrequest",
        "downloadstring",
        "-command",
        "-encodedcommand",
        "|",
    ):
        assert banned not in text, f"{banned!r} makes antivirus software block the wrapper"
    assert "curl.exe" in text
    assert re.search(r'powershell .*-file "%gz_script%"', text)


def _run(tmp_path: Path, url: str) -> subprocess.CompletedProcess[str]:
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {**os.environ, "GARMINIZER_INSTALLER_URL": url, "TEMP": str(temp), "TMP": str(temp)}
    return subprocess.run(
        ["cmd", "/c", str(WRAPPER)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        env=env,
        check=False,
        timeout=180,
    )


@windows_only
def test_wrapper_downloads_the_script_then_runs_it_as_a_file(tmp_path: Path) -> None:
    marker = tmp_path / "ran.txt"
    script = tmp_path / "fake-install.ps1"
    script.write_text(
        f"Set-Content -LiteralPath '{marker}' -Value $PSCommandPath\n", encoding="ascii"
    )
    result = _run(tmp_path, script.as_uri())
    assert marker.exists(), result.stdout + result.stderr
    ran_from = Path(marker.read_text(encoding="utf-8-sig").strip())
    assert ran_from == tmp_path / "temp" / "garminizer-install.ps1"
    assert not ran_from.exists(), "the downloaded script is removed afterwards"
    assert "Could not download" not in result.stdout


@windows_only
def test_wrapper_reports_a_failed_download_and_runs_nothing(tmp_path: Path) -> None:
    result = _run(tmp_path, (tmp_path / "missing.ps1").as_uri())
    assert "Could not download the Garminizer installer" in result.stdout
    assert not (tmp_path / "temp" / "garminizer-install.ps1").exists()
