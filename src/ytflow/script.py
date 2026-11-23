"""The timed script: the join key between phrases, images, narration and timeline.

The agent writes ``script.md``, which the creator reads and edits::

    # Working title of the video

    > Notes for the creator. Lines starting with ">" are ignored.

    ## Chapter title
    - One phrase per line: one subtitle, one image, one idea.
    - **Key words** between double asterisks are highlighted on screen.
    - The next phrase.

``ytflow script build`` validates it against the video's kit and writes
``script.json`` next to it, with what later steps need exactly: each phrase's
``<enumerate_id>_<part_of_phrase>`` name and its estimated start and end. The
estimates come from the kit's ``words_per_minute``; the alignment step replaces
them with the real narration times.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

SOURCE = "script.md"
COMPILED = "script.json"

SLUG_WORDS = 5
SLUG_MAX = 40
CHAPTER_TITLE_MAX = 40
CHAPTER_PAUSE_SECONDS = 1.0
# YouTube turns description timestamps into chapters only with at least three,
# the first at 0:00, each at least ten seconds long.
YOUTUBE_MIN_CHAPTERS = 3
YOUTUBE_MIN_CHAPTER_SECONDS = 10.0

WORD_RE = re.compile(r"[\w'’-]+")


@dataclass
class Phrase:
    id: str
    slug: str
    name: str
    chapter: int
    text: str
    words: int
    start: float = 0.0
    end: float = 0.0
    line: int = 0
    # [start, end) character spans of `text` to highlight on screen, marked **like this** in script.md
    highlights: list[list[int]] = field(default_factory=list)


@dataclass
class Chapter:
    index: int
    title: str
    start: float = 0.0
    end: float = 0.0
    line: int = 0


@dataclass
class Script:
    title: str
    words_per_minute: float
    chapters: list[Chapter] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.phrases[-1].end if self.phrases else 0.0

    def to_json(self) -> str:
        data = {
            "title": self.title,
            "words_per_minute": self.words_per_minute,
            "timing": "estimated",
            "duration": self.duration,
            "chapters": [asdict(c) for c in self.chapters],
            "phrases": [asdict(p) for p in self.phrases],
        }
        for item in (*data["chapters"], *data["phrases"]):
            del item["line"]
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


HIGHLIGHT = "**"


def unmark(text: str) -> tuple[str, list[list[int]], bool]:
    """Text without its **highlight** marks, the highlighted spans in it, and whether every mark is closed."""
    clean, spans, opened = "", [], None
    parts = text.split(HIGHLIGHT)
    for i, part in enumerate(parts):
        if i:
            if opened is None:
                opened = len(clean)
            else:
                if len(clean) > opened:
                    spans.append([opened, len(clean)])
                opened = None
        clean += part
    return clean, spans, opened is None


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def slugify(text: str) -> str:
    """The first words of a phrase as a lowercase, hyphenated ASCII slug."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_text.lower().replace("'", "").replace("’", ""))
    slug = ""
    for word in words[:SLUG_WORDS]:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > SLUG_MAX:
            break
        slug = candidate
    return slug or "phrase"


def parse(text: str) -> tuple[str | None, list[Chapter], list[tuple[int, int, str]], list[str]]:
    """(title, chapters, phrases as (chapter, line, text), problems)."""
    title: str | None = None
    chapters: list[Chapter] = []
    phrases: list[tuple[int, int, str]] = []
    problems: list[str] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(">"):
            continue
        if line.startswith("## "):
            chapters.append(Chapter(len(chapters) + 1, line[3:].strip(), line=number))
        elif line.startswith("# "):
            if title is not None:
                problems.append(f"line {number}: a second '# ' title; the script has one title")
            title = line[2:].strip()
        elif line.startswith(("- ", "* ")):
            if not chapters:
                problems.append(f"line {number}: phrase before the first '## ' chapter")
                continue
            phrases.append((chapters[-1].index, number, line[2:].strip()))
        else:
            problems.append(f"line {number}: not a title, chapter, phrase or '>' note — one phrase per '- ' line")
    return title, chapters, phrases, problems


def build(text: str, words_per_minute: float, phrase_words_max: int) -> tuple[Script | None, list[str]]:
    """Parse, number and time a script. Returns (script, problems); script is None on problems."""
    title, chapters, raw_phrases, problems = parse(text)
    if not title:
        problems.append("missing the '# ' title line")
    if not chapters:
        problems.append("no '## ' chapters")
    for chapter in chapters:
        if not chapter.title:
            problems.append(f"line {chapter.line}: empty chapter title")
        elif len(chapter.title) > CHAPTER_TITLE_MAX:
            problems.append(
                f"line {chapter.line}: chapter title is {len(chapter.title)} characters; "
                f"keep it within {CHAPTER_TITLE_MAX} so it fits the top-left corner"
            )
        if not any(c == chapter.index for c, _, _ in raw_phrases):
            problems.append(f"line {chapter.line}: chapter {chapter.title!r} has no phrases")

    width = max(3, len(str(len(raw_phrases))))
    phrases: list[Phrase] = []
    for i, (chapter, number, marked) in enumerate(raw_phrases, 1):
        text_, highlights, closed = unmark(marked)
        if not closed:
            problems.append(f"line {number}: a '**' highlight is never closed")
        words = count_words(text_)
        if words == 0:
            problems.append(f"line {number}: empty phrase")
        elif words > phrase_words_max:
            problems.append(f"line {number}: phrase has {words} words; the kit allows {phrase_words_max} — split it")
        id_ = f"{i:0{width}d}"
        slug = slugify(text_)
        phrases.append(Phrase(id_, slug, f"{id_}_{slug}", chapter, text_, words, line=number, highlights=highlights))
    if problems:
        return None, problems

    script = Script(title or "", words_per_minute, chapters, phrases)
    clock = 0.0
    previous: int | None = None
    for phrase in phrases:
        chapter = chapters[phrase.chapter - 1]
        if phrase.chapter != previous:  # first phrase of a chapter
            if previous is not None:
                clock += CHAPTER_PAUSE_SECONDS
            chapter.start = round(clock, 2)
            previous = phrase.chapter
        phrase.start = round(clock, 2)
        clock += phrase.words * 60 / words_per_minute
        phrase.end = round(clock, 2)
        chapter.end = phrase.end
    return script, []


def youtube_chapter_warnings(script: Script) -> list[str]:
    """Why YouTube would not show these chapters. Not errors: a short video may not want them."""
    warnings = []
    if len(script.chapters) < YOUTUBE_MIN_CHAPTERS:
        warnings.append(f"{len(script.chapters)} chapter(s): YouTube shows chapters only from {YOUTUBE_MIN_CHAPTERS}")
    for chapter in script.chapters:
        # a chapter lasts until the next one starts
        following = script.chapters[chapter.index] if chapter.index < len(script.chapters) else None
        length = (following.start if following else chapter.end) - chapter.start
        if length < YOUTUBE_MIN_CHAPTER_SECONDS:
            warnings.append(
                f"chapter {chapter.title!r} is about {length:.0f}s; YouTube needs {YOUTUBE_MIN_CHAPTER_SECONDS:.0f}s"
            )
    return warnings


def load(path: Path) -> dict:
    return json.loads(path.read_text())
