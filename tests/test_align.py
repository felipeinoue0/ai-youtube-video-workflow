"""Aligning the narration to the script — driven through the CLI process, audio generated with ffmpeg.

faster-whisper is an optional extra that downloads a model, so the suite drives the
word-matching path with ``--words`` (the same matching the whisper path uses) and the
character-count path with real per-chapter audio.
"""

from __future__ import annotations

import json
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
model = "eleven_multilingual_v2"
stability = 0.5
similarity = 0.75
style = 0.0
speed = 1.0
chapter_break = 1.0
+++
"""

SCRIPT = """# T
## One
- Alpha beta gamma.
- Delta epsilon.
- Omicron pi.
## Two
- Zeta eta theta iota kappa lambda mu nu.
"""

# what a recogniser heard in one narration file: "omicron pi" missed, "nu" misheard
HEARD = [
    ("Alpha", 0.5, 0.8),
    ("beta", 0.8, 1.1),
    ("gamma.", 1.1, 1.5),
    ("Delta", 2.0, 2.3),
    ("epsilon.", 2.3, 2.8),
    *[(w, 4.0 + i * 0.5, 4.4 + i * 0.5) for i, w in enumerate("zeta eta theta iota kappa lambda mu new".split())],
]


def ytflow(root: Path, *args: str, no_whisper: bool = False) -> subprocess.CompletedProcess[str]:
    if no_whisper:  # as if the optional extra were not installed
        code = "import sys; sys.modules['faster_whisper'] = None; from ytflow.cli import main; sys.exit(main())"
        command = [sys.executable, "-c", code, "--root", str(root), *args]
    else:
        command = [sys.executable, "-m", "ytflow", "--root", str(root), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def ok(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def silence(path: Path, seconds: float) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", str(seconds), path],
        check=True,
    )


def setup(root: Path) -> Path:
    ok(root, "channel", "new", "c")
    kit = root / "channels" / "c" / "kit" / "v1"
    (kit / "style-guide.md").write_text(STYLE)
    (kit / "voice.md").write_text(VOICE)
    ok(root, "video", "new", "c", "v")
    video = root / "channels" / "c" / "videos" / "v"
    script = Path(ok(root, "version", "new", str(video / "script")).stdout.strip())
    (script / "script.md").write_text(SCRIPT)
    ok(root, "script", "build", "c", "v")
    ok(root, "voiceover", "text", "c", "v")
    return video


def words_file(path: Path, heard: list[tuple[str, float, float]]) -> Path:
    path.write_text(json.dumps([{"word": w, "start": s, "end": e} for w, s, e in heard]))
    return path


def spans(video: Path, version: str = "v1") -> list[tuple[float, float]]:
    data = json.loads((video / "timing" / version / "timing.json").read_text())
    return [(p["start"], p["end"]) for p in data["phrases"]]


def test_align_from_word_timestamps(tmp_path: Path) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "narration.wav", 9.0)
    words = words_file(tmp_path / "words.json", HEARD)
    result = ok(tmp_path, "align", "c", "v", "--words", str(words))
    assert result.stdout.splitlines()[0] == str(video / "timing" / "v1" / "timing.json")
    assert "timing v1: words, 80% of words heard, 4 phrases, 0:09" in result.stdout
    assert "warning: 003_omicron-pi: none of its words were heard" in result.stdout

    assert spans(video) == [
        (0.5, 1.5),  # heard exactly
        (2.0, 2.8),
        (2.8, 4.0),  # unheard: the gap between its neighbours
        (4.0, 7.9),  # "nu" ends with the misheard "new", not at the end of the audio
    ]
    data = json.loads((video / "timing" / "v1" / "timing.json").read_text())
    assert data["method"] == "words" and data["timing"] == "aligned" and data["matched"] == 0.8
    assert data["script_version"] == "v1" and data["voiceover_version"] == "v1"
    assert data["audio"] == [{"file": "audio/narration.wav", "start": 0.0, "duration": 9.0}]
    assert data["duration"] == 9.0
    assert [(c["title"], c["start"], c["end"]) for c in data["chapters"]] == [("One", 0.5, 4.0), ("Two", 4.0, 7.9)]
    assert (
        (video / "timing" / "v1" / "subtitles.srt")
        .read_text()
        .startswith("1\n00:00:00,500 --> 00:00:01,500\nAlpha beta gamma.\n\n2\n00:00:02,000 --> 00:00:02,800\n")
    )
    status = ok(tmp_path, "status", "c", "v").stdout
    assert "timing     v1" in status


def test_align_refuses_audio_that_is_not_the_script(tmp_path: Path) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "narration.wav", 9.0)
    words = words_file(tmp_path / "words.json", HEARD[:-2] + HEARD[-1:])  # "mu" missed too: 11 of 15 heard
    result = ytflow(tmp_path, "align", "c", "v", "--words", str(words))
    assert result.returncode == 1 and "only 73% of the script's words were heard" in result.stderr
    assert not (video / "timing").exists() or not list((video / "timing").iterdir())


def test_align_by_characters_with_per_chapter_audio(tmp_path: Path) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "01_one.wav", 3.0)
    silence(video / "audio" / "02_two.wav", 2.0)
    result = ytflow(tmp_path, "align", "c", "v", no_whisper=True)
    assert result.returncode == 0, result.stderr
    assert "timing v1: chapters, 4 phrases, 0:06" in result.stdout
    assert "  0:04 Two" in result.stdout
    # chapter One (3 s) shared by characters 15 : 13 : 10; chapter Two after the 1 s chapter break
    one = 3.0 / 38
    expected = [(0.0, 15 * one), (15 * one, 28 * one), (28 * one, 3.0), (4.0, 6.0)]
    assert spans(video) == [(round(s, 3), round(e, 3)) for s, e in expected]
    data = json.loads((video / "timing" / "v1" / "timing.json").read_text())
    assert data["matched"] is None
    assert data["audio"] == [
        {"file": "audio/01_one.wav", "start": 0.0, "duration": 3.0},
        {"file": "audio/02_two.wav", "start": 4.0, "duration": 2.0},
    ]


def test_one_narration_file_needs_whisper_or_word_timestamps(tmp_path: Path) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "narration.wav", 9.0)
    result = ytflow(tmp_path, "align", "c", "v", no_whisper=True)
    assert result.returncode == 1 and "uv sync --extra align" in result.stderr
    assert "one audio file per chapter" in result.stderr
    forced = ytflow(tmp_path, "align", "c", "v", "--method", "chapters")
    assert forced.returncode == 1 and "--method chapters needs one audio file per chapter" in forced.stderr
    whisper = ytflow(tmp_path, "align", "c", "v", "--method", "whisper", no_whisper=True)
    assert whisper.returncode == 1 and "faster-whisper is not installed" in whisper.stderr


@pytest.mark.parametrize(
    ("content", "message"),
    [("not json", "cannot read word timestamps"), ('[{"word": "a"}]', "expected [{word, start, end}, ...]")],
)
def test_bad_word_timestamps_are_a_clear_error(tmp_path: Path, content: str, message: str) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "narration.wav", 9.0)
    (tmp_path / "words.json").write_text(content)
    result = ytflow(tmp_path, "align", "c", "v", "--words", str(tmp_path / "words.json"))
    assert result.returncode == 1 and message in result.stderr


def test_align_needs_complete_audio(tmp_path: Path) -> None:
    video = setup(tmp_path)
    silence(video / "audio" / "01_one.wav", 3.0)
    result = ytflow(tmp_path, "align", "c", "v", no_whisper=True)
    assert result.returncode == 1 and "run: ytflow audio check c v" in result.stderr
