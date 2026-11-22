"""The narration text for ElevenLabs, and the narration audio the creator brings back.

``ytflow voiceover text`` reads the built script and the kit's ``voice.md`` and
writes, in ``voiceover/v<N>/``:

- ``narration.txt`` — the whole narration, one paragraph per chapter, with a
  pause between chapters and the kit's pronunciation spellings applied;
- ``chapters/<NN>_<slug>.txt`` — the same text one chapter per file, for
  generating chapter by chapter (long videos, re-recording one chapter);
- ``voiceover.json`` — what was exported: script and kit versions, the voice
  settings to use, and each chapter's file and phrases.

The creator generates the audio in ElevenLabs and saves it in the video's
``audio/`` folder, either as one ``narration.<ext>`` or as one file per chapter
named like the chapter text files. ``ytflow audio check`` verifies that.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ytflow.script import slugify

TEXT = "narration.txt"
CHAPTERS_DIR = "chapters"
COMPILED = "voiceover.json"
NARRATION = "narration"
AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")

# The ElevenLabs text-to-speech box takes about this many characters per
# generation on most plans; longer narrations are generated chapter by chapter.
GENERATION_CHARACTERS = 5000
# ElevenLabs reads <break time="1.0s" /> in its v2 models; eleven_v3 does not.
BREAK_TAG_MAX_SECONDS = 3.0
# How far the narration may run from the script's estimate before it looks wrong.
DURATION_TOLERANCE = 0.25

SETTINGS = ("voice", "voice_id", "model", "stability", "similarity", "style", "speed")


def check_voice(data: dict) -> list[str]:
    """Problems with voice.md's front matter."""
    problems = []
    for key in ("voice", "model"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            problems.append(f"{key} is missing")
    if not isinstance(data.get("voice_id", ""), str):
        problems.append("voice_id must be a string")
    for key, low, high in (
        ("stability", 0, 1),
        ("similarity", 0, 1),
        ("style", 0, 1),
        ("speed", 0.7, 1.2),
        ("chapter_break", 0, BREAK_TAG_MAX_SECONDS),
    ):
        value = data.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool):
            problems.append(f"{key} is missing")
        elif not low <= value <= high:
            problems.append(f"{key} = {value} is outside {low}–{high}")
    spellings = data.get("pronunciations", {})
    if not isinstance(spellings, dict):
        problems.append("[pronunciations] must be a table of word = spoken spelling")
    else:
        for word, spoken in spellings.items():
            if not isinstance(spoken, str) or not spoken.strip():
                problems.append(f"pronunciation for {word!r} must be a non-empty string")
            elif not re.search(r"\w", word):
                problems.append(f"pronunciation key {word!r} has no letters")
    return problems


def break_tag(model: str, seconds: float) -> str:
    """The pause between chapters ElevenLabs understands for this model ('' for none)."""
    if seconds <= 0 or model.startswith("eleven_v3"):
        return ""
    return f'<break time="{seconds:g}s" />'


def respell(text: str, spellings: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Replace whole words by their spoken spelling, longest first. Returns (text, uses per word)."""
    uses: dict[str, int] = {}
    for word in sorted(spellings, key=len, reverse=True):
        pattern = re.compile(rf"(?<![\w'’-]){re.escape(word)}(?![\w'’-])")
        spoken = spellings[word]
        text, count = pattern.subn(lambda _, spoken=spoken: spoken, text)  # a function: no backslash escapes
        uses[word] = count
    return text, uses


@dataclass
class ChapterText:
    index: int
    title: str
    file: str
    text: str
    phrases: list[str]


@dataclass
class Narration:
    chapters: list[ChapterText]
    pause: str
    uses: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        separator = f"\n\n{self.pause}\n\n" if self.pause else "\n\n"
        return separator.join(c.text for c in self.chapters) + "\n"


def chapter_file(index: int, title: str) -> str:
    return f"{index:02d}_{slugify(title)}"


def build(script: dict, voice: dict) -> Narration:
    """The narration of a built script with the kit's voice settings."""
    spellings = voice.get("pronunciations", {})
    uses = dict.fromkeys(spellings, 0)
    chapters = []
    for chapter in script["chapters"]:
        phrases = [p for p in script["phrases"] if p["chapter"] == chapter["index"]]
        text, counted = respell(" ".join(p["text"] for p in phrases), spellings)
        for word, count in counted.items():
            uses[word] += count
        chapters.append(
            ChapterText(
                chapter["index"],
                chapter["title"],
                chapter_file(chapter["index"], chapter["title"]),
                text,
                [p["name"] for p in phrases],
            )
        )
    return Narration(chapters, break_tag(voice["model"], voice["chapter_break"]), uses)


def compiled(narration: Narration, script: dict, script_version: str, kit_version: str, voice: dict) -> dict:
    estimates = {c["index"]: round(c["end"] - c["start"], 2) for c in script["chapters"]}
    return {
        "script_version": script_version,
        "kit_version": kit_version,
        "settings": {key: voice.get(key, "") for key in SETTINGS},
        "chapter_break": voice["chapter_break"],
        "characters": len(narration.text),
        "estimated_duration": script["duration"],
        "pronunciations": narration.uses,
        "chapters": [
            {
                "index": c.index,
                "title": c.title,
                "file": c.file,
                "characters": len(c.text),
                "estimated_duration": estimates[c.index],
                "phrases": c.phrases,
            }
            for c in narration.chapters
        ],
    }


def same_export(version: Path, narration: Narration, data: dict) -> bool:
    """True when a voiceover version already holds exactly this export."""
    try:
        previous = json.loads((version / COMPILED).read_text())
        return previous == data and (version / TEXT).read_text() == narration.text
    except (OSError, json.JSONDecodeError):
        return False


def write(version: Path, narration: Narration, data: dict) -> None:
    (version / TEXT).write_text(narration.text)
    chapters = version / CHAPTERS_DIR
    chapters.mkdir(exist_ok=True)
    for chapter in narration.chapters:
        (chapters / f"{chapter.file}.txt").write_text(chapter.text + "\n")
    (version / COMPILED).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@dataclass
class AudioReport:
    layout: str  # "single", "chapters" or "none"
    files: list[Path] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # chapter names without audio
    extra: list[Path] = field(default_factory=list)  # files that match neither layout
    problems: list[str] = field(default_factory=list)


def audio_files(audio_dir: Path) -> list[Path]:
    if not audio_dir.is_dir():
        return []
    return sorted(
        p
        for p in audio_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def check_audio(audio_dir: Path, chapter_names: list[str]) -> AudioReport:
    """Which layout audio/ uses, and what is missing or does not belong."""
    files = audio_files(audio_dir)
    by_stem: dict[str, list[Path]] = {}
    for path in files:
        by_stem.setdefault(path.stem, []).append(path)
    report = AudioReport("none")
    for stem, paths in sorted(by_stem.items()):
        if len(paths) > 1:
            report.problems.append(f"{stem} is saved twice: {', '.join(p.name for p in paths)} — keep one")
    single = by_stem.get(NARRATION, [])
    per_chapter = [name for name in chapter_names if name in by_stem]
    if single and per_chapter:
        report.problems.append(
            f"both {single[0].name} and per-chapter files are in audio/ — keep one layout, move the other out"
        )
    if single:
        report.layout, report.files = "single", single[:1]
    elif per_chapter:
        report.layout = "chapters"
        report.files = [by_stem[name][0] for name in per_chapter]
        report.missing = [name for name in chapter_names if name not in by_stem]
    known = {NARRATION, *chapter_names}
    report.extra = [p for p in files if p.stem not in known]
    return report


def duration_warning(actual: float, estimated: float) -> str | None:
    if estimated <= 0:
        return None
    ratio = actual / estimated
    if abs(ratio - 1) <= DURATION_TOLERANCE:
        return None
    direction = "longer" if ratio > 1 else "shorter"
    return (
        f"the narration is {abs(ratio - 1):.0%} {direction} than the script's estimate — "
        "check for missing or repeated text, or the voice speed"
    )
