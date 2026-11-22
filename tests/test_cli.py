"""The CLI is driven the way a user runs it: as a process, not a function call."""

import subprocess
import sys

from ytflow import __version__


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ytflow", *args], capture_output=True, text=True, check=False)


def test_version_prints_the_package_version() -> None:
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"ytflow {__version__}"


def test_help_names_the_program() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert "usage: ytflow" in result.stdout
