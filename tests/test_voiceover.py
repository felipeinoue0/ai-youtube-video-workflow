"""Narration text for ElevenLabs and the narration audio check — driven through the CLI process."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 12
+++
"""

VOICE = """+++
voice = "Adam"
voice_id = "abc123"
model = "{model}"
stability = 0.5
similarity = 0.75
style = 0.0
speed = 1.0
chapter_break = {pause}

[pronunciations]
"Nero" = "Neer-oh"
"SPQR" = "S P Q R"
"Caligula" = "Kuh-LIG-yoo-luh"
+++

# Voice
A calm, low narrator.
"""

SCRIPT = """# The Emperor
## Rome burns
- Nero watched the city of Rome burn.
- The Neronian years began in fire.
## The standard
- Every legion carried SPQR into battle.
- Its eagle never touched the ground.
"""


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def setup(root: Path, model: str = "eleven_multilingual_v2", pause: str = "1.0") -> Path:
    ok(root, "channel", "new", "c")
    kit = root / "channels" / "c" / "kit" / "v1"
    (kit / "style-guide.md").write_text(STYLE)
    (kit / "voice.md").write_text(VOICE.format(model=model, pause=pause))
    ok(root, "video", "new", "c", "v")
    video = root / "channels" / "c" / "videos" / "v"
    script = Path(ok(root, "version", "new", str(video / "script")).stdout.strip())
    (script / "script.md").write_text(SCRIPT)
    ok(root, "script", "build", "c", "v")
    return video


def tone(path: Path, seconds: float) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", str(seconds), path],
        check=True,
    )


def test_voiceover_text_needs_a_filled_voice_kit(tmp_path: Path) -> None:
    video = setup(tmp_path)
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit / "voice.md").write_text((kit / "voice.md").read_text().replace("speed = 1.0", "speed = 2"))
    result = ytflow(tmp_path, "voiceover", "text", "c", "v")
    assert result.returncode == 1
    assert "voice.md in kit v1 is not ready (speed = 2 is outside 0.7–1.2)" in result.stderr
    assert not (video / "voiceover").exists() or not list((video / "voiceover").iterdir())


def test_kit_check_reports_voice_problems(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    fresh = ytflow(tmp_path, "kit", "check", "c", "--file", "voice.md")
    assert fresh.returncode == 1 and "voice is missing" in fresh.stdout and "placeholder" in fresh.stdout
    bad = VOICE.format(model="", pause="9").replace('"Neer-oh"', '""')
    (kit / "voice.md").write_text(bad)
    out = ytflow(tmp_path, "kit", "check", "c", "--file", "voice.md").stdout
    assert "model is missing" in out
    assert "chapter_break = 9 is outside 0–3.0" in out
    assert "pronunciation for 'Nero' must be a non-empty string" in out


def test_voiceover_text_exports_narration_chapters_and_settings(tmp_path: Path) -> None:
    video = setup(tmp_path)
    result = ok(tmp_path, "voiceover", "text", "c", "v")
    version = video / "voiceover" / "v1"
    assert result.stdout.strip() == str(version / "narration.txt")
    assert "warning: pronunciation 'Caligula' never appears" in result.stderr

    text = (version / "narration.txt").read_text()
    assert text == (
        "Neer-oh watched the city of Rome burn. The Neronian years began in fire."
        '\n\n<break time="1s" />\n\n'
        "Every legion carried S P Q R into battle. Its eagle never touched the ground.\n"
    )
    chapters = sorted(p.name for p in (version / "chapters").iterdir())
    assert chapters == ["01_rome-burns.txt", "02_the-standard.txt"]
    assert (version / "chapters" / "02_the-standard.txt").read_text().startswith("Every legion carried S P Q R")

    data = json.loads((version / "voiceover.json").read_text())
    assert data["script_version"] == "v1" and data["kit_version"] == "v1"
    assert data["settings"]["voice"] == "Adam" and data["settings"]["voice_id"] == "abc123"
    assert data["pronunciations"] == {"Nero": 1, "SPQR": 1, "Caligula": 0}
    assert data["characters"] == len(text)
    first = data["chapters"][0]
    assert first["file"] == "01_rome-burns"
    assert first["phrases"] == ["001_nero-watched-the-city-of", "002_the-neronian-years-began-in"]
    script = json.loads((video / "script" / "v1" / "script.json").read_text())
    assert data["estimated_duration"] == script["duration"]
    assert first["estimated_duration"] == script["chapters"][0]["end"] - script["chapters"][0]["start"]


def test_voiceover_text_writes_a_version_only_when_something_changed(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")
    again = ok(tmp_path, "voiceover", "text", "c", "v")
    assert "already holds this export" in again.stderr
    assert sorted(p.name for p in (video / "voiceover").iterdir()) == ["v1"]
    script = Path(ok(tmp_path, "version", "new", "--copy", str(video / "script")).stdout.strip())
    (script / "script.md").write_text(SCRIPT.replace("burn.", "burn to the ground."))
    ok(tmp_path, "script", "build", "c", "v")
    ok(tmp_path, "voiceover", "text", "c", "v")
    v2 = video / "voiceover" / "v2"
    assert "burn to the ground." in (v2 / "narration.txt").read_text()
    assert json.loads((v2 / "voiceover.json").read_text())["script_version"] == "v2"


@pytest.mark.parametrize(
    ("model", "pause"), [("eleven_v3", "1.0"), ("eleven_v4", "1.0"), ("eleven_multilingual_v2", "0")]
)
def test_no_break_tag_when_the_model_ignores_it_or_no_pause(tmp_path: Path, model: str, pause: str) -> None:
    video = setup(tmp_path, model, pause)
    ok(tmp_path, "voiceover", "text", "c", "v")
    text = (video / "voiceover" / "v1" / "narration.txt").read_text()
    assert "<break" not in text and "burn. The Neronian years began in fire.\n\nEvery legion" in text


def test_audio_check_accepts_one_narration_file(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")
    none = ytflow(tmp_path, "audio", "check", "c", "v")
    assert none.returncode == 1 and "save narration.mp3" in none.stdout
    estimate = json.loads((video / "voiceover" / "v1" / "voiceover.json").read_text())["estimated_duration"]
    tone(video / "audio" / "narration.mp3", estimate)
    (video / "audio" / "notes.txt").write_text("not audio, ignored")
    out = ok(tmp_path, "audio", "check", "c", "v").stdout
    assert "audio: one file" in out and out.rstrip().endswith("ok") and "warning" not in out
    assert "audio      narration.mp3" in ok(tmp_path, "status", "c", "v").stdout


def test_audio_check_per_chapter_reports_missing_extra_and_durations(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")
    data = json.loads((video / "voiceover" / "v1" / "voiceover.json").read_text())
    audio = video / "audio"
    tone(audio / "01_rome-burns.mp3", data["chapters"][0]["estimated_duration"] * 2)
    tone(audio / "ElevenLabs_2026_Adam.mp3", 1)
    result = ytflow(tmp_path, "audio", "check", "c", "v")
    assert result.returncode == 1
    assert "- missing: 02_the-standard.mp3" in result.stdout
    assert "warning: ElevenLabs_2026_Adam.mp3 is not narration.<ext> or a chapter name" in result.stdout
    assert re.search(r"warning: 01_rome-burns\.mp3: the narration is 1\d\d% longer", result.stdout)
    assert "1/2 chapter files" in result.stdout
    assert "audio      1/2 chapter files" in ok(tmp_path, "status", "c", "v").stdout

    tone(audio / "02_the-standard.wav", data["chapters"][1]["estimated_duration"])
    (audio / "ElevenLabs_2026_Adam.mp3").unlink()
    out = ytflow(tmp_path, "audio", "check", "c", "v").stdout
    assert "2/2 chapter files" in out and out.rstrip().endswith("ok")

    tone(audio / "narration.mp3", data["estimated_duration"])
    tone(audio / "02_the-standard.mp3", 1)
    both = ytflow(tmp_path, "audio", "check", "c", "v")
    assert both.returncode == 1
    assert "keep one layout" in both.stdout and "02_the-standard is saved twice" in both.stdout


def test_audio_check_needs_the_voiceover_export(tmp_path: Path) -> None:
    setup(tmp_path)
    ok(tmp_path, "version", "new", "channels/c/videos/v/voiceover")
    result = ytflow(tmp_path, "audio", "check", "c", "v")
    assert result.returncode == 1 and "ytflow voiceover text c v" in result.stderr


def test_audio_check_takes_a_single_file_of_any_name_as_the_narration(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")
    estimate = json.loads((video / "voiceover" / "v1" / "voiceover.json").read_text())["estimated_duration"]
    tone(video / "audio" / "voz.mp3", estimate)
    out = ok(tmp_path, "audio", "check", "c", "v").stdout
    assert "voz.mp3" in out and "audio: one file" in out and "warning" not in out
    assert "audio      voz.mp3" in ok(tmp_path, "status", "c", "v").stdout
    tone(video / "audio" / "outra.mp3", 1)  # two unnamed files: neither is the narration
    assert ytflow(tmp_path, "audio", "check", "c", "v").returncode == 1
