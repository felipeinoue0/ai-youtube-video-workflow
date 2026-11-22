"""Workspace layout, versioning, the channel kit and status — driven through the CLI process."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from ytflow.workspace import KIT_TEMPLATES, TODO_MARK


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> str:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_channel_new_creates_layout_and_kit_v1(tmp_path: Path) -> None:
    path = Path(ok(tmp_path, "channel", "new", "my-channel"))
    assert path == tmp_path / "channels" / "my-channel"
    for sub in ("references", "branding", "videos"):
        assert (path / sub).is_dir()
    kit = path / "kit" / "v1"
    assert sorted(p.name for p in kit.iterdir()) == sorted(KIT_TEMPLATES)
    assert tomllib.loads((kit / "edit-preset.toml").read_text())["video"]["width"] == 1920


def test_channel_new_refuses_existing_and_bad_names(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    again = ytflow(tmp_path, "channel", "new", "c")
    assert again.returncode == 1 and "already exists" in again.stderr
    bad = ytflow(tmp_path, "channel", "new", "My Channel")
    assert bad.returncode == 1 and "invalid channel name" in bad.stderr


def test_root_comes_from_environment(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ytflow", "channel", "new", "c"],
        capture_output=True,
        text=True,
        check=False,
        env={"YTFLOW_ROOT": str(tmp_path), "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "channels" / "c" / "channel.toml").is_file()


def test_version_new_never_overwrites_and_can_copy(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    ok(tmp_path, "video", "new", "c", "v")
    step = "channels/c/videos/v/script"
    v1 = Path(ok(tmp_path, "version", "new", step))
    assert v1.name == "v1"
    (v1 / "script.md").write_text("first")
    v2 = Path(ok(tmp_path, "version", "new", step))
    assert v2.name == "v2" and list(v2.iterdir()) == []
    v3 = Path(ok(tmp_path, "version", "new", "--copy", step))
    assert v3.name == "v3" and list(v3.iterdir()) == []  # copies the latest (v2, empty)
    assert (v1 / "script.md").read_text() == "first"
    assert ok(tmp_path, "version", "latest", step) == str(v3)


def test_versions_sort_numerically(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    step = tmp_path / "channels" / "c" / "branding"
    for n in (1, 2, 10):
        (step / f"v{n}").mkdir()
    assert Path(ok(tmp_path, "version", "latest", str(step))).name == "v10"
    assert Path(ok(tmp_path, "version", "new", str(step))).name == "v11"


def test_version_paths_must_be_inside_channels(tmp_path: Path) -> None:
    result = ytflow(tmp_path, "version", "new", str(tmp_path / "elsewhere"))
    assert result.returncode == 1 and "is not inside" in result.stderr


def test_kit_new_copies_latest_and_videos_pin_their_kit(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    kit1 = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit1 / "voice.md").write_text("# Voice\nAdam, stability 0.5\n")
    ok(tmp_path, "video", "new", "c", "first")
    kit2 = Path(ok(tmp_path, "kit", "new", "c"))
    assert kit2.name == "v2"
    assert (kit2 / "voice.md").read_text() == "# Voice\nAdam, stability 0.5\n"
    ok(tmp_path, "video", "new", "c", "second")
    ok(tmp_path, "video", "new", "c", "third", "--kit", "v1")
    assert ok(tmp_path, "kit", "path", "c", "first") == str(kit1)
    assert ok(tmp_path, "kit", "path", "c", "second") == str(kit2)
    assert ok(tmp_path, "kit", "path", "c", "third") == str(kit1)
    assert ok(tmp_path, "kit", "path", "c") == str(kit2)
    bad = ytflow(tmp_path, "video", "new", "c", "fourth", "--kit", "v9")
    assert bad.returncode == 1 and "no kit version 'v9'" in bad.stderr


def test_video_new_needs_an_existing_channel(tmp_path: Path) -> None:
    result = ytflow(tmp_path, "video", "new", "nope", "v")
    assert result.returncode == 1 and "ytflow channel new nope" in result.stderr


def fill(kit: Path, *names: str) -> None:
    for name in names:
        p = kit / name
        p.write_text("\n".join(line for line in p.read_text().splitlines() if TODO_MARK not in line))


def next_line(output: str) -> str:
    return [line for line in output.splitlines() if line.startswith("next:")][-1]


def test_status_walks_the_creator_through_the_steps(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    channel = tmp_path / "channels" / "c"
    kit = channel / "kit" / "v1"
    assert "skill: branding" in next_line(ok(tmp_path, "status", "c"))

    (Path(ok(tmp_path, "version", "new", str(channel / "branding"))) / "identity.toml").write_text("x")
    out = ok(tmp_path, "status", "c")
    assert "still TODO" in out and next_line(out) == "next: fill publish.md in kit v1 (skill: branding)"
    fill(kit, "publish.md")
    assert next_line(ok(tmp_path, "status", "c")) == "next: fill style-guide.md in kit v1 (skill: style)"
    fill(kit, "style-guide.md", "visual-style.md")
    out = ok(tmp_path, "status", "c")
    assert "still TODO: edit-preset.toml, voice.md" in out  # filled during the first video
    assert "ytflow video new c" in next_line(out)

    ok(tmp_path, "video", "new", "c", "v")
    video = channel / "videos" / "v"
    assert "skill: script" in next_line(ok(tmp_path, "status", "c", "v"))

    script = Path(ok(tmp_path, "version", "new", str(video / "script")))
    assert "skill: script" in next_line(ok(tmp_path, "status", "c", "v"))  # empty version is not done
    (script / "script.md").write_text("x")
    (Path(ok(tmp_path, "version", "new", str(video / "prompts"))) / "prompts.md").write_text("x")
    out = ok(tmp_path, "status", "c", "v")
    assert "Google Flow" in next_line(out) and "images     empty" in out

    (video / "images" / "001_dawn.png").write_bytes(b"")
    assert next_line(ok(tmp_path, "status", "c", "v")) == "next: fill voice.md in kit v1 (skill: voiceover)"
    fill(kit, "voice.md")
    assert "skill: voiceover" in next_line(ok(tmp_path, "status", "c", "v"))

    for step in ("voiceover", "timing"):
        (Path(ok(tmp_path, "version", "new", str(video / step))) / "out.txt").write_text("x")
    (video / "audio" / "narration.mp3").write_bytes(b"")
    assert next_line(ok(tmp_path, "status", "c", "v")) == "next: fill edit-preset.toml in kit v1 (skill: edit)"
    fill(kit, "edit-preset.toml")
    for step in ("timeline", "publish"):
        (Path(ok(tmp_path, "version", "new", str(video / step))) / "out.txt").write_text("x")
    assert next_line(ok(tmp_path, "status", "c", "v")).startswith("next: done")


def test_kit_edit_fills_placeholders_in_place_but_never_rewrites_a_used_file(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    kits = tmp_path / "channels" / "c" / "kit"
    ok(tmp_path, "video", "new", "c", "first")
    # voice.md is still a placeholder: the video in progress fills it in its own kit
    assert ok(tmp_path, "kit", "edit", "c", "first", "--file", "voice.md") == str(kits / "v1")
    fill(kits / "v1", "voice.md")
    # now filled and used by "first": a change goes to a new version, "first" keeps v1
    result = ytflow(tmp_path, "kit", "edit", "c", "first", "--file", "voice.md")
    assert result.returncode == 0 and result.stdout.strip() == str(kits / "v2")
    assert "used by first" in result.stderr
    assert ok(tmp_path, "kit", "path", "c", "first") == str(kits / "v1")
    bad = ytflow(tmp_path, "kit", "edit", "c", "--file", "nope.md")
    assert bad.returncode == 1 and "unknown kit file" in bad.stderr


@pytest.mark.parametrize("args", [("status", "c", "missing"), ("kit", "path", "c", "missing")])
def test_unknown_video_is_a_clear_error(tmp_path: Path, args: tuple[str, ...]) -> None:
    ok(tmp_path, "channel", "new", "c")
    result = ytflow(tmp_path, *args)
    assert result.returncode == 1 and "ytflow video new c missing" in result.stderr
