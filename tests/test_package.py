"""The timed transcript and the package folder — driven through the CLI process."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 14
+++
"""

VISUAL = """+++
aspect_ratio = "16:9"
anchor = "cinematic digital painting, warm low sun, muted ochre and teal palette, soft film grain"
avoid = "text, letters, watermarks"
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

[pronunciations]
"IA" = "I.A."
+++
"""

SCRIPT = """# Começar com IA
## O começo
- A IA não faz tudo por você.
- Mas ela tira as desculpas do caminho | de verdade.
## O desafio
- Publique um vídeo em sete dias.
"""

SCENES = [
    "a person at a kitchen table with a laptop and a cup of coffee, wide shot",
    "a narrow path cleared through tall grass toward an open field, wide shot",
    "a wall calendar with seven days circled in pencil, close-up",
]


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def video_dir(root: Path) -> Path:
    return root / "channels" / "c" / "videos" / "v"


def setup(root: Path, script: str = SCRIPT) -> Path:
    ok(root, "channel", "new", "c")
    kit = root / "channels" / "c" / "kit" / "v1"
    (kit / "style-guide.md").write_text(STYLE)
    (kit / "visual-style.md").write_text(VISUAL)
    (kit / "voice.md").write_text(VOICE)
    ok(root, "video", "new", "c", "v")
    version = Path(ok(root, "version", "new", str(video_dir(root) / "script")).stdout.strip())
    (version / "script.md").write_text(script)
    ok(root, "script", "build", "c", "v")
    return version


def write_scenes(root: Path) -> None:
    prompts = Path(ok(root, "prompts", "init", "c", "v").stdout.strip())
    scenes = iter(SCENES)
    lines = [
        f"scene: {next(scenes)}" if line.startswith("scene: ") else line for line in prompts.read_text().splitlines()
    ]
    prompts.write_text("\n".join(lines) + "\n")
    ok(root, "prompts", "build", "c", "v")


def table_rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        if line.startswith("| ") and not line.startswith("| #"):
            rows.append([c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)[1:-1]])
    return rows


def test_script_build_writes_a_timed_transcript(tmp_path: Path) -> None:
    version = setup(tmp_path)
    script = json.loads((version / "script.json").read_text())
    text = (version / "transcript.md").read_text()
    assert text.startswith("# Começar com IA\n\nTimes are **estimated** at 150 words per minute")
    second = script["chapters"][1]["start"]
    assert f"Total 0:{script['duration']:04.1f} · 3 lines · 2 chapters" in text
    assert "## 0:00.0 — O começo" in text and f"## 0:{second:04.1f} — O desafio" in text
    rows = table_rows(text)
    assert [r[0] for r in rows] == ["001", "002", "003"]
    for row, phrase in zip(rows, script["phrases"], strict=True):
        start, end = phrase["start"], phrase["end"]
        assert row[1] == f"0:{start:04.1f}" and row[2] == f"0:{end:04.1f}"
        assert row[3] == f"{end - start:.1f} s"
        assert row[4] == phrase["name"] and row[5] == phrase["text"]  # a '|' in the text is escaped
    assert rows[1][5] == "Mas ela tira as desculpas do caminho | de verdade."


def test_package_gathers_everything_in_one_folder(tmp_path: Path) -> None:
    setup(tmp_path)
    video = video_dir(tmp_path)
    missing = ytflow(tmp_path, "package", "c", "v")
    assert missing.returncode == 1
    assert "Flow prompts from script v1" in missing.stderr and "ElevenLabs text from script v1" in missing.stderr
    write_scenes(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")

    result = ok(tmp_path, "package", "c", "v")
    package = video / "package" / "v1"
    assert result.stdout.splitlines()[0] == str(package)
    assert "package v1: script v1, 3 images, 2 ElevenLabs chapter files; times estimated" in result.stdout
    assert sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()) == [
        "elevenlabs.txt",
        "elevenlabs/01_o-comeco.txt",
        "elevenlabs/02_o-desafio.txt",
        "flow-prompts.txt",
        "manifest.json",
        "scenes.md",
        "script-timed.md",
    ]
    # only the spoken lines: spellings applied, chapters on their own paragraph, no markup at all
    narration = (package / "elevenlabs.txt").read_text()
    assert narration == (
        "A I.A. não faz tudo por você. Mas ela tira as desculpas do caminho | de verdade.\n\n"
        "Publique um vídeo em sete dias.\n"
    )
    assert "<break" in (video / "voiceover" / "v1" / "narration.txt").read_text()  # the export keeps its pauses
    assert (package / "flow-prompts.txt").read_text() == (video / "prompts" / "v1" / "prompts.txt").read_text()
    assert (package / "script-timed.md").read_text() == (video / "script" / "v1" / "transcript.md").read_text()

    scenes = (package / "scenes.md").read_text()
    names = [p["name"] for p in json.loads((video / "script" / "v1" / "script.json").read_text())["phrases"]]
    for name, scene in zip(names, SCENES, strict=True):
        block = scenes.split(f"### {name}\n", 1)[1].split("###", 1)[0]
        assert re.match(r"0:\d\d\.\d – 0:\d\d\.\d \(\d+\.\d s\)\n", block)
        assert f"Scene: {scene}" in block
    assert scenes.index(names[0]) < scenes.index("— O desafio") < scenes.index(names[2])
    manifest = json.loads((package / "manifest.json").read_text())
    assert manifest == {"script": "v1", "prompts": "v1", "voiceover": "v1", "timing": None, "times": "estimated"}


def test_package_uses_the_aligned_times_of_the_same_script(tmp_path: Path) -> None:
    setup(tmp_path)
    video = video_dir(tmp_path)
    write_scenes(tmp_path)
    ok(tmp_path, "voiceover", "text", "c", "v")
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    for name, seconds in (("01_o-comeco", 6.0), ("02_o-desafio", 4.0)):
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                str(seconds),
                str(video / "audio" / f"{name}.wav"),
            ],
            check=True,
        )
    ok(tmp_path, "align", "c", "v", "--method", "chapters")
    result = ok(tmp_path, "package", "c", "v")
    assert "times aligned (v1)" in result.stdout
    timed = (video / "package" / "v1" / "script-timed.md").read_text()
    assert "Times are **aligned** to the narration (chapters)" in timed
    assert "Total 0:11.0" in timed and "## 7:" not in timed and "## 0:07.0 — O desafio" in timed  # 6 s + 1 s break
    assert json.loads((video / "package" / "v1" / "manifest.json").read_text())["timing"] == "v1"

    # a new script version: its package refuses the old prompts and voiceover, and ignores the old timing
    v2 = Path(ok(tmp_path, "version", "new", "--copy", str(video / "script")).stdout.strip())
    (v2 / "script.md").write_text(SCRIPT.replace("sete dias", "sete dias, sem medo"))
    ok(tmp_path, "script", "build", "c", "v")
    stale = ytflow(tmp_path, "package", "c", "v")
    assert stale.returncode == 1 and "Flow prompts from script v2" in stale.stderr
    older = ok(tmp_path, "package", "c", "v", "--script", "v1")
    assert "package v2: script v1" in older.stdout and "times aligned" in older.stdout
