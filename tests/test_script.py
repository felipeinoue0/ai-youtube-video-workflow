"""Script build: parsing, numbering, slugs, estimated timing — driven through the CLI process."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 12
+++
# Style guide
"""

GOOD = """# The Coin That Ended Rome

> Hook: open on the coin, not on the emperor.

## A Coin Loses Its Silver
- What if the greatest empire in history was never conquered at all?
- It starts with a single coin.

## Soldiers Want Real Money
- The army noticed first.
* Pay in bad coins, and loyalty goes too.

## The Last Emperor
- By 476, there was nothing left to defend.
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
def version(tmp_path: Path) -> Path:
    ok(tmp_path, "channel", "new", "c")
    (tmp_path / "channels" / "c" / "kit" / "v1" / "style-guide.md").write_text(STYLE)
    ok(tmp_path, "video", "new", "c", "rome")
    return Path(ok(tmp_path, "version", "new", "channels/c/videos/rome/script"))


def build(root: Path, version: Path, text: str) -> subprocess.CompletedProcess[str]:
    (version / "script.md").write_text(text)
    return ytflow(root, "script", "build", "c", "rome")


def test_build_numbers_names_and_times_every_phrase(tmp_path: Path, version: Path) -> None:
    result = build(tmp_path, version, GOOD)
    assert result.returncode == 0, result.stdout
    data = json.loads((version / "script.json").read_text())
    assert data["title"] == "The Coin That Ended Rome" and data["timing"] == "estimated"
    names = [p["name"] for p in data["phrases"]]
    assert names == [
        "001_what-if-the-greatest-empire",
        "002_it-starts-with-a-single",
        "003_the-army-noticed-first",
        "004_pay-in-bad-coins-and",
        "005_by-476-there-was-nothing",
    ]
    assert names == sorted(names)  # file names sort into timeline order
    first, second, third = data["phrases"][:3]
    # 150 wpm: 0.4 s per word
    assert (first["words"], first["start"], first["end"]) == (12, 0.0, 4.8)
    assert (second["start"], second["end"]) == (4.8, 7.2)
    assert third["start"] == 8.2  # one second of pause between chapters
    assert [c["title"] for c in data["chapters"]] == [
        "A Coin Loses Its Silver",
        "Soldiers Want Real Money",
        "The Last Emperor",
    ]
    assert [c["start"] for c in data["chapters"]] == [0.0, 8.2, 14.0]
    assert data["duration"] == data["phrases"][-1]["end"]
    assert "0:08 Soldiers Want Real Money (2 phrases)" in result.stdout
    assert "Hook" not in (version / "script.json").read_text()  # notes are not phrases


def test_short_chapters_warn_but_build(tmp_path: Path, version: Path) -> None:
    result = build(tmp_path, version, GOOD)
    assert "warning: chapter 'A Coin Loses Its Silver' is about 8s; YouTube needs 10s" in result.stdout
    two = GOOD.split("## The Last Emperor")[0]
    result = build(tmp_path, version, two)
    assert result.returncode == 0 and "2 chapter(s): YouTube shows chapters only from 3" in result.stdout


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (GOOD.replace("# The Coin That Ended Rome\n", ""), "missing the '# ' title line"),
        (GOOD + "\n# Another title\n", "a second '# ' title"),
        ("# T\n- orphan phrase\n## C\n- ok\n", "line 2: phrase before the first '## ' chapter"),
        (GOOD.replace("- The army noticed first.", "The army noticed first."), "not a title, chapter, phrase"),
        (
            GOOD.replace("- The army noticed first.", "- " + "word " * 13),
            "phrase has 13 words; the kit allows 12 — split it",
        ),
        (GOOD.replace("## The Last Emperor", "## " + "x" * 41), "chapter title is 41 characters"),
        (GOOD + "\n## Empty Chapter\n", "chapter 'Empty Chapter' has no phrases"),
        ("# T\n", "no '## ' chapters"),
        (GOOD.replace("- The army noticed first.", "- ..."), "empty phrase"),
    ],
)
def test_problems_are_named_and_block_the_json(tmp_path: Path, version: Path, text: str, expected: str) -> None:
    result = build(tmp_path, version, text)
    assert result.returncode == 1 and expected in result.stdout, result.stdout
    assert not (version / "script.json").exists()


def test_slugs_are_ascii_and_never_empty(tmp_path: Path, version: Path) -> None:
    text = (
        "# T\n## C\n- Équipe d’été à Paris.\n- 中文 字幕\n- A very-long-hyphenated-compound-word-indeed that goes on\n"
    )
    assert build(tmp_path, version, text).returncode == 0
    slugs = [p["slug"] for p in json.loads((version / "script.json").read_text())["phrases"]]
    assert slugs == ["equipe-dete-a-paris", "phrase", "a-very-long-hyphenated-compound"]
    assert all(len(s) <= 40 for s in slugs)


def test_ids_widen_past_999_phrases(tmp_path: Path, version: Path) -> None:
    text = "# T\n## C\n" + "".join(f"- Phrase number {i}.\n" for i in range(1000))
    assert build(tmp_path, version, text).returncode == 0
    phrases = json.loads((version / "script.json").read_text())["phrases"]
    assert phrases[0]["name"] == "0001_phrase-number-0" and phrases[-1]["id"] == "1000"


def test_build_needs_a_ready_style_guide(tmp_path: Path, version: Path) -> None:
    (tmp_path / "channels" / "c" / "kit" / "v1" / "style-guide.md").write_text(STYLE.replace("150", "0"))
    result = build(tmp_path, version, GOOD)
    assert result.returncode == 1 and "style-guide.md in kit v1 is not ready" in result.stderr


def test_build_reads_the_requested_version(tmp_path: Path, version: Path) -> None:
    (version / "script.md").write_text(GOOD)
    v2 = Path(ok(tmp_path, "version", "new", "channels/c/videos/rome/script"))
    missing = ytflow(tmp_path, "script", "build", "c", "rome")
    assert missing.returncode == 1 and "no script.md in" in missing.stderr
    ok(tmp_path, "script", "build", "c", "rome", "--version", "v1")
    assert (version / "script.json").is_file() and not (v2 / "script.json").exists()
