"""Branding check and kit edit — driven through the CLI process, images made with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

GOOD_IDENTITY = '''
name = "History Explained"
handle = "@historyexplained"
language = "en"
description = """Ancient history explained in calm, well-researched documentaries."""
keywords = ["roman history", "ancient history", "documentary"]
'''


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> str:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def image(path: Path, width: int, height: int) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=navy:s={width}x{height}", "-frames:v", "1", path],
        check=True,
    )


@pytest.fixture
def branding(tmp_path: Path) -> Path:
    ok(tmp_path, "channel", "new", "c")
    return Path(ok(tmp_path, "version", "new", "channels/c/branding"))


def test_complete_branding_passes(tmp_path: Path, branding: Path) -> None:
    (branding / "identity.toml").write_text(GOOD_IDENTITY)
    image(branding / "logo.png", 800, 800)
    image(branding / "banner.jpg", 2560, 1440)
    assert ok(tmp_path, "branding", "check", "c").endswith("branding v1: ok")


def test_missing_files_are_named(tmp_path: Path, branding: Path) -> None:
    result = ytflow(tmp_path, "branding", "check", "c")
    assert result.returncode == 1
    assert "missing identity.toml" in result.stdout
    assert "missing logo" in result.stdout and "800x800" in result.stdout
    assert "missing banner" in result.stdout and "2560x1440" in result.stdout


@pytest.mark.parametrize(
    ("logo", "banner", "expected"),
    [
        ((800, 600), (2560, 1440), "logo is 800x600; it must be square"),
        ((64, 64), (2560, 1440), "at least 98x98"),
        ((800, 800), (1920, 1080), "banner is 1920x1080; YouTube needs at least 2048x1152"),
        ((800, 800), (2560, 1600), "it must be 16:9"),
    ],
)
def test_image_sizes_are_checked(
    tmp_path: Path, branding: Path, logo: tuple[int, int], banner: tuple[int, int], expected: str
) -> None:
    (branding / "identity.toml").write_text(GOOD_IDENTITY)
    image(branding / "logo.png", *logo)
    image(branding / "banner.png", *banner)
    result = ytflow(tmp_path, "branding", "check", "c")
    assert result.returncode == 1 and expected in result.stdout


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (("History Explained", "H" * 51), "name is 51 characters"),
        (("@historyexplained", "historyexplained"), "handle 'historyexplained' must be"),
        (("@historyexplained", "@hi"), "handle '@hi' must be"),
        (("calm, well-researched documentaries.", "x" * 1001), "description is"),
        (('"documentary"]', '"documentary", "Documentary"]'), "duplicates"),
        (
            ('"documentary"]', '"documentary", ' + ", ".join(f'"long keyword {i:03d}"' for i in range(40)) + "]"),
            "YouTube allows 500",
        ),
        (('keywords = ["roman history", "ancient history", "documentary"]', "keywords = []"), "non-empty list"),
        (("name =", "name = = "), "not valid TOML"),
    ],
)
def test_identity_limits(tmp_path: Path, branding: Path, change: tuple[str, str], expected: str) -> None:
    old, new = change
    assert old in GOOD_IDENTITY
    (branding / "identity.toml").write_text(GOOD_IDENTITY.replace(old, new))
    image(branding / "logo.png", 800, 800)
    image(branding / "banner.png", 2560, 1440)
    result = ytflow(tmp_path, "branding", "check", "c")
    assert result.returncode == 1 and expected in result.stdout, result.stdout


def test_check_reads_the_requested_version(tmp_path: Path, branding: Path) -> None:
    (branding / "identity.toml").write_text(GOOD_IDENTITY)
    image(branding / "logo.png", 800, 800)
    image(branding / "banner.png", 2560, 1440)
    ok(tmp_path, "version", "new", "channels/c/branding")  # v2, empty
    assert ytflow(tmp_path, "branding", "check", "c").returncode == 1
    assert ok(tmp_path, "branding", "check", "c", "--version", "v1").endswith("ok")
    assert "no branding version 'v7'" in ytflow(tmp_path, "branding", "check", "c", "--version", "v7").stderr


def test_unreadable_image_is_reported(tmp_path: Path, branding: Path) -> None:
    (branding / "identity.toml").write_text(GOOD_IDENTITY)
    (branding / "logo.png").write_text("not an image")
    image(branding / "banner.png", 2560, 1440)
    result = ytflow(tmp_path, "branding", "check", "c")
    assert result.returncode == 1 and "cannot read image" in result.stdout


def test_kit_edit_starts_a_new_version_once_a_video_uses_the_kit(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    kit1 = tmp_path / "channels" / "c" / "kit" / "v1"
    assert ok(tmp_path, "kit", "edit", "c") == str(kit1)  # no video yet: edit in place
    ok(tmp_path, "video", "new", "c", "first")
    result = ytflow(tmp_path, "kit", "edit", "c")
    assert result.returncode == 0
    assert result.stdout.strip() == str(kit1.parent / "v2")
    assert "used by first" in result.stderr
    assert ok(tmp_path, "kit", "edit", "c") == str(kit1.parent / "v2")  # v2 is still unused
