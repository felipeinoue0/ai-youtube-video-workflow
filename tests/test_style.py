"""Reference transcript stats and the kit check — driven through the CLI process."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

YOUTUBE = """0:00
Did you know Rome never fell in a day?
0:04
It took centuries. You will see why.
0:10
The empire split in two.
"""

SRT = """1
00:00:00,000 --> 00:00:03,000
First line here.

2
00:00:03,000 --> 00:00:06,000
Second line here.
"""

ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
hello there

00:00:02.000 --> 00:00:04.000 align:start
hello there <00:00:02.500><c>general</c> kenobi
"""

PLAIN = "One two three. Four five six seven? " + "Word " * 60 + "end."

STYLE_FRONT = """+++
words_per_minute = 150
phrase_words_target = 12
phrase_words_max = 22
+++

# Style guide
Short, calm sentences.
"""

VISUAL_FRONT = """+++
aspect_ratio = "16:9"
anchor = "cinematic digital painting, warm dusk light, muted earth palette, soft film grain"
avoid = "text, logos, modern objects"
+++

# Visual style
"""


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> str:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


@pytest.fixture
def refs(tmp_path: Path) -> Path:
    ok(tmp_path, "channel", "new", "c")
    return tmp_path / "channels" / "c" / "references"


def stats(root: Path) -> dict:
    return json.loads(ok(root, "references", "stats", "c", "--json"))


def by_file(data: dict) -> dict[str, dict]:
    return {t["file"]: t for t in data["transcripts"]}


def test_youtube_transcript_copy(tmp_path: Path, refs: Path) -> None:
    (refs / "rome.txt").write_text(YOUTUBE)
    s = by_file(stats(tmp_path))["rome.txt"]
    assert s["format"] == "youtube"
    assert s["words"] == 21 and s["sentences"] == 4
    # the last line has no end time: it is given the pace of the rest (10 s for 16 words)
    assert s["words_per_minute"] == 96.0
    assert s["sentence_words_median"] == 4.5 and s["sentence_words_p90"] == 9
    assert s["question_share"] == 0.25
    assert s["second_person_per_100_words"] == 9.52
    assert s["hook"].startswith("Did you know Rome") and s["hook"].endswith("split in two.")


def test_srt_and_rolling_vtt(tmp_path: Path, refs: Path) -> None:
    (refs / "a.srt").write_text(SRT)
    (refs / "b.vtt").write_text(ROLLING_VTT)
    data = by_file(stats(tmp_path))
    assert data["a.srt"]["words"] == 6 and data["a.srt"]["words_per_minute"] == 60.0
    # the rolling cue repeats "hello there"; the tags are dropped
    assert data["b.vtt"]["words"] == 4 and data["b.vtt"]["hook"] == "hello there general kenobi"


def test_plain_text_has_no_pace_and_a_word_limited_hook(tmp_path: Path, refs: Path) -> None:
    (refs / "plain.md").write_text(PLAIN)
    (refs / "ignored.pdf").write_text("not a transcript")
    data = stats(tmp_path)
    assert [t["file"] for t in data["transcripts"]] == ["plain.md"]
    s = data["transcripts"][0]
    assert s["format"] == "plain" and s["words_per_minute"] is None and s["duration_seconds"] is None
    assert s["hook"].startswith("One two three. Four five six seven?")
    assert data["recommended"]["words_per_minute"] is None


def test_recommendation_is_the_median(tmp_path: Path, refs: Path) -> None:
    (refs / "rome.txt").write_text(YOUTUBE)
    (refs / "a.srt").write_text(SRT)
    (refs / "b.vtt").write_text(ROLLING_VTT)
    assert stats(tmp_path)["recommended"]["words_per_minute"] == 60
    report = ok(tmp_path, "references", "stats", "c")
    assert "words_per_minute = 60" in report and "rome.txt (youtube)" in report


def test_no_transcripts_is_a_clear_error(tmp_path: Path, refs: Path) -> None:
    result = ytflow(tmp_path, "references", "stats", "c")
    assert result.returncode == 1 and "no transcripts in" in result.stderr


def test_fresh_kit_fails_the_check(tmp_path: Path, refs: Path) -> None:
    result = ytflow(tmp_path, "kit", "check", "c")
    assert result.returncode == 1
    assert "words_per_minute = 0 is outside 90–220" in result.stdout
    assert "anchor must be one sentence" in result.stdout
    assert "kit v1: 5 file(s) with problems" in result.stdout


def test_filled_style_files_pass(tmp_path: Path, refs: Path) -> None:
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit / "style-guide.md").write_text(STYLE_FRONT)
    (kit / "visual-style.md").write_text(VISUAL_FRONT)
    out = ok(tmp_path, "kit", "check", "c", "--file", "style-guide.md", "--file", "visual-style.md")
    assert out.splitlines() == ["style-guide.md: ok", "visual-style.md: ok", "kit v1: ok"]


@pytest.mark.parametrize(
    ("file", "old", "new", "expected"),
    [
        ("style-guide.md", "words_per_minute = 150", "words_per_minute = 400", "outside 90–220"),
        ("style-guide.md", "phrase_words_max = 22", "phrase_words_max = 8", "below phrase_words_target"),
        ("style-guide.md", "phrase_words_target = 12\n", "", "phrase_words_target is missing"),
        ("style-guide.md", "+++\n\n# Style", "\n# Style", "never closed"),
        ("style-guide.md", "words_per_minute = 150", "words_per_minute = = 1", "not valid TOML"),
        ("style-guide.md", "Short, calm", "TODO(ytflow): short, calm", "placeholder"),
        ("visual-style.md", '"16:9"', '"4:3"', "aspect_ratio must be"),
        ("visual-style.md", "cinematic digital painting, warm dusk light, muted", "nice", "anchor must be"),
        ("visual-style.md", "cinematic digital painting,", "very " * 40, "anchor must be"),
    ],
)
def test_kit_check_names_each_problem(tmp_path: Path, refs: Path, file: str, old: str, new: str, expected: str) -> None:
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    text = STYLE_FRONT if file == "style-guide.md" else VISUAL_FRONT
    assert old in text
    (kit / file).write_text(text.replace(old, new))
    result = ytflow(tmp_path, "kit", "check", "c", "--file", file)
    assert result.returncode == 1 and expected in result.stdout, result.stdout


def test_kit_check_reads_the_videos_kit(tmp_path: Path, refs: Path) -> None:
    kit1 = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit1 / "style-guide.md").write_text(STYLE_FRONT)
    ok(tmp_path, "video", "new", "c", "first")
    kit2 = Path(ok(tmp_path, "kit", "new", "c"))
    (kit2 / "style-guide.md").write_text(STYLE_FRONT.replace("150", "400"))
    assert ytflow(tmp_path, "kit", "check", "c", "--file", "style-guide.md").returncode == 1  # latest: v2
    ok(tmp_path, "kit", "check", "c", "first", "--file", "style-guide.md")
    bad = ytflow(tmp_path, "kit", "check", "c", "--file", "nope.md")
    assert bad.returncode == 1 and "unknown kit file" in bad.stderr
