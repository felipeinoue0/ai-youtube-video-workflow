"""Title, description, tags and captions — driven through the CLI process."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 20
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

TEMPLATE = """+++
base_tags = ["roman history", "ancient rome"]
+++
{summary}

Chapters:
{chapters}

Subscribe for a new story from {title} and more.
"""

SCRIPT = """# T
## Silver
- Alpha beta gamma delta.
## Soldiers
- Epsilon zeta eta.
## Crisis
- Theta iota kappa.
"""

FILLED = """<!-- timeline v1 · kit v1 -->
# How a Silver Coin Broke Rome

> options: The Coin That Ruined an Empire

## Summary
Rome fell one coin at a time.
This is how debased silver emptied the soldiers' pay.

## Tags
- roman coins
- Ancient  Rome
- inflation
"""


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def ffmpeg(*args: str) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def kit(root: Path) -> Path:
    return root / "channels" / "c" / "kit" / "v1"


def setup(root: Path, seconds: float = 12.0, timeline: bool = True) -> Path:
    ok(root, "channel", "new", "c")
    (kit(root) / "style-guide.md").write_text(STYLE)
    (kit(root) / "voice.md").write_text(VOICE)
    (kit(root) / "publish.md").write_text(TEMPLATE)
    preset = kit(root) / "edit-preset.toml"
    preset.write_text("\n".join(line for line in preset.read_text().splitlines() if "TODO(ytflow)" not in line))
    ok(root, "video", "new", "c", "v")
    video = root / "channels" / "c" / "videos" / "v"
    version = Path(ok(root, "version", "new", str(video / "script")).stdout.strip())
    (version / "script.md").write_text(SCRIPT)
    ok(root, "script", "build", "c", "v")
    ok(root, "voiceover", "text", "c", "v")
    for name in ("01_silver", "02_soldiers", "03_crisis"):
        ffmpeg(
            "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", str(seconds), str(video / "audio" / f"{name}.wav")
        )
    ok(root, "align", "c", "v", "--method", "chapters")
    for phrase in json.loads((version / "script.json").read_text())["phrases"]:
        ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=teal:s=320x180",
            "-frames:v",
            "1",
            str(video / "images" / f"{phrase['name']}.png"),
        )
    if timeline:
        ok(root, "timeline", "build", "c", "v")
    return video


def test_kit_check_validates_the_publish_template(tmp_path: Path) -> None:
    ok(tmp_path, "channel", "new", "c")
    fresh = ytflow(tmp_path, "kit", "check", "c", "--file", "publish.md").stdout
    assert "placeholder" in fresh and "base_tags must be a non-empty list" in fresh
    (kit(tmp_path) / "publish.md").write_text('+++\nbase_tags = ["a"]\n+++\n{summary} {summary}\n{footer} <b>\n')
    out = ytflow(tmp_path, "kit", "check", "c", "--file", "publish.md").stdout
    assert "needs {summary} exactly once (found 2)" in out and "needs {chapters} exactly once (found 0)" in out
    assert "rejects '<' and '>'" in out and "footer" not in out  # any {slot} is allowed; publish.md fills it
    (kit(tmp_path) / "publish.md").write_text(TEMPLATE)
    assert "publish.md: ok" in ok(tmp_path, "kit", "check", "c", "--file", "publish.md").stdout


def test_publish_builds_description_tags_and_captions(tmp_path: Path) -> None:
    video = setup(tmp_path)
    source = Path(ok(tmp_path, "publish", "init", "c", "v").stdout.strip())
    assert source == video / "publish" / "v1" / "publish.md"
    assert source.read_text().startswith("<!-- timeline v1 · kit v1 -->\n# TODO")
    todo = ytflow(tmp_path, "publish", "build", "c", "v")
    assert todo.returncode == 1 and "title line is missing or still TODO" in todo.stdout
    assert not (source.parent / "publish.json").exists()

    source.write_text(FILLED)
    result = ok(tmp_path, "publish", "build", "c", "v")
    assert "warning" not in result.stdout and "publish v1: ok — 28-character title" in result.stdout
    version = source.parent
    # chapters start at 0:00, then where each chapter's first phrase is cut in (0.5 s lead, 12 s + 1 s break)
    assert (version / "description.txt").read_text() == (
        "Rome fell one coin at a time. This is how debased silver emptied the soldiers' pay.\n\n"
        "Chapters:\n0:00 Silver\n0:13 Soldiers\n0:26 Crisis\n\n"
        "Subscribe for a new story from How a Silver Coin Broke Rome and more.\n"
    )
    assert (version / "title.txt").read_text() == "How a Silver Coin Broke Rome\n"
    # base tags first; "Ancient  Rome" is a duplicate of a base tag once case and spaces are ignored
    assert (version / "tags.txt").read_text() == "roman history, ancient rome, roman coins, inflation\n"
    # the timeline's subtitles, 0.5 s lead included, as YouTube captions
    assert (
        (version / "captions.srt")
        .read_text()
        .startswith("1\n00:00:00,500 --> 00:00:12,500\nAlpha beta gamma delta.\n\n2\n00:00:13,500 --> ")
    )
    data = json.loads((version / "publish.json").read_text())
    assert data["timeline_version"] == "v1" and data["kit_version"] == "v1"
    assert data["tags"] == ["roman history", "ancient rome", "roman coins", "inflation"]
    assert "publish    v1" in ok(tmp_path, "status", "c", "v").stdout


def test_publish_enforces_youtube_limits(tmp_path: Path) -> None:
    setup(tmp_path)
    source = Path(ok(tmp_path, "publish", "init", "c", "v").stdout.strip())
    long_title = "A" * 101
    source.write_text(FILLED.replace("How a Silver Coin Broke Rome", long_title).replace("Rome fell", "Rome <fell>"))
    out = ytflow(tmp_path, "publish", "build", "c", "v").stdout
    assert "title is 101 characters; YouTube allows 100" in out and "'<' and '>' in the summary" in out
    many = "\n".join(f"- tag number {i}" for i in range(40))
    source.write_text(FILLED.replace("How a Silver Coin Broke Rome", "B" * 80).replace("- inflation", many))
    result = ytflow(tmp_path, "publish", "build", "c", "v")
    assert result.returncode == 1 and "YouTube allows 500 — drop some video tags" in result.stdout
    assert "past 70 it is cut off in search" not in result.stdout  # warnings only print on success
    source.write_text(FILLED.replace("How a Silver Coin Broke Rome", "B" * 80))
    assert "title is 80 characters; past 70 it is cut off" in ok(tmp_path, "publish", "build", "c", "v").stdout


def test_short_chapters_leave_the_chapter_list_out(tmp_path: Path) -> None:
    video = setup(tmp_path, seconds=4.0)
    source = Path(ok(tmp_path, "publish", "init", "c", "v").stdout.strip())
    source.write_text(FILLED)
    out = ok(tmp_path, "publish", "build", "c", "v").stdout
    assert "YouTube needs 10s" in out and "chapter list is left out" in out
    description = (video / "publish" / "v1" / "description.txt").read_text()
    assert "0:00" not in description and "Chapters:" not in description


def test_publish_init_needs_a_timeline_and_carries_text_over(tmp_path: Path) -> None:
    video = setup(tmp_path, timeline=False)
    early = ytflow(tmp_path, "publish", "init", "c", "v")
    assert early.returncode == 1 and "ytflow timeline build c v" in early.stderr
    ok(tmp_path, "timeline", "build", "c", "v")
    (Path(ok(tmp_path, "publish", "init", "c", "v").stdout.strip())).write_text(FILLED)
    ok(tmp_path, "timeline", "build", "c", "v")  # timeline v2
    second = ok(tmp_path, "publish", "init", "c", "v")
    assert "carried the title, summary and tags over from v1" in second.stderr
    text = (video / "publish" / "v2" / "publish.md").read_text()
    assert text == FILLED.replace("timeline v1", "timeline v2")


SECTIONED_TEMPLATE = """+++
base_tags = ["comece hoje internet"]
+++
{summary}

🧰 FERRAMENTAS CITADAS NO VÍDEO
{ferramentas}

💬 {pergunta}

▶️ CONTINUE ASSISTINDO
{continue_assistindo}

⏱️ CAPÍTULOS
{chapters}

#ComeceHojeInternet {hashtags}
"""

SECTIONED = """<!-- timeline v1 · kit v1 -->
# Título

## Summary
Primeira linha do resumo,
continuando o mesmo parágrafo.

Segundo parágrafo.

## Ferramentas
ChatGPT: https://chatgpt.com
Canva: https://www.canva.com

## Pergunta
Qual você vai testar primeiro?

## Continue assistindo
Internet do zero
https://www.youtube.com/watch?v=abc

## Hashtags
#InteligenciaArtificial #YouTube

## Extra
Not in the template.

## Tags
- ia
"""


def test_publish_fills_template_slots_from_sections(tmp_path: Path) -> None:
    video = setup(tmp_path, timeline=True)
    (kit(tmp_path) / "publish.md").write_text(SECTIONED_TEMPLATE)
    assert "publish.md: ok" in ok(tmp_path, "kit", "check", "c", "--file", "publish.md").stdout
    source = Path(ok(tmp_path, "publish", "init", "c", "v").stdout.strip())
    source.write_text(
        SECTIONED.replace("## Continue assistindo\nInternet do zero\nhttps://www.youtube.com/watch?v=abc\n\n", "")
    )
    missing = ytflow(tmp_path, "publish", "build", "c", "v")
    assert (
        missing.returncode == 1 and "{continue_assistindo} needs a '## Continue assistindo' section" in missing.stdout
    )

    source.write_text(SECTIONED)
    out = ok(tmp_path, "publish", "build", "c", "v").stdout
    assert "section 'extra' is not in the description template" in out
    description = (video / "publish" / "v1" / "description.txt").read_text()
    assert description.startswith(
        "Primeira linha do resumo, continuando o mesmo parágrafo.\n\nSegundo parágrafo.\n\n"
        "🧰 FERRAMENTAS CITADAS NO VÍDEO\nChatGPT: https://chatgpt.com\nCanva: https://www.canva.com\n\n"
        "💬 Qual você vai testar primeiro?\n\n▶️ CONTINUE ASSISTINDO\nInternet do zero\nhttps://www.youtube.com/watch?v=abc\n"
    )
    assert "⏱️ CAPÍTULOS\n0:00 Silver\n" in description
    assert description.endswith("#ComeceHojeInternet #InteligenciaArtificial #YouTube\n")
    assert "Not in the template" not in description

    source.write_text(SECTIONED.replace("Qual você vai testar primeiro?", "TODO: a question"))
    todo = ytflow(tmp_path, "publish", "build", "c", "v")
    assert todo.returncode == 1 and "the 'pergunta' section is still TODO" in todo.stdout
