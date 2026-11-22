"""Measure reference transcripts: pace, sentence length, hook, questions, second person.

Reads the formats a creator actually has:

- SRT and WebVTT subtitle files (cue times ``00:00:01,000 --> 00:00:04,000``);
- YouTube's "Show transcript" copy, a timestamp (``0:00``, ``1:02:03``) on its own
  line or at the start of the line;
- plain text (no timing: pace cannot be measured, everything else can).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

SUFFIXES = (".txt", ".md", ".srt", ".vtt")
HOOK_SECONDS = 15.0
HOOK_WORDS = 40  # without timing, the hook is the first sentences up to this many words

CUE_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{3})")
STAMP_RE = re.compile(r"^\(?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\)?(?:\s+(.*))?$")
TAG_RE = re.compile(r"<[^>]+>|\[[^\]]*\]")  # VTT voice/timing tags, [Music], [Applause]
SENTENCE_RE = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")
WORD_RE = re.compile(r"[\w'’-]+")
SECOND_PERSON = {"you", "your", "you're", "yours", "yourself", "you’re", "you'll", "you’ll"}


@dataclass(frozen=True)
class Segment:
    start: float | None
    end: float | None
    text: str


@dataclass(frozen=True)
class TranscriptStats:
    file: str
    format: str
    words: int
    sentences: int
    duration_seconds: float | None
    words_per_minute: float | None
    sentence_words_median: float
    sentence_words_p90: float
    question_share: float
    second_person_per_100_words: float
    hook: str


def seconds(h: str | None, m: str, s: str, ms: str = "0") -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(text: str) -> tuple[str, list[Segment]]:
    """(format, segments). Segment times are None for plain text."""
    lines = [line.strip() for line in text.replace("﻿", "").splitlines()]
    if any(CUE_RE.match(line) for line in lines):
        return "subtitles", parse_cues(lines)
    stamped = [m for line in lines if (m := STAMP_RE.match(line))]
    if len(stamped) >= 2:
        return "youtube", parse_stamps(lines)
    body = " ".join(line for line in lines if line)
    return "plain", [Segment(None, None, clean(body))] if body else []


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", text)).strip()


def parse_cues(lines: list[str]) -> list[Segment]:
    segments: list[Segment] = []
    current: tuple[float, float] | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current and (body := clean(" ".join(buffer))):
            # rolling captions repeat the previous cue's line; keep only what is new
            if segments and body.startswith(segments[-1].text):
                body = body[len(segments[-1].text) :].strip()
            if body:
                segments.append(Segment(current[0], current[1], body))

    for line in lines:
        if m := CUE_RE.match(line):
            flush()
            g = m.groups()
            current, buffer = (seconds(*g[0:4]), seconds(*g[4:8])), []
        elif not line or line.isdigit() or line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            continue
        elif current:
            buffer.append(line)
    flush()
    return segments


def parse_stamps(lines: list[str]) -> list[Segment]:
    raw: list[tuple[float, list[str]]] = []
    for line in lines:
        if not line:
            continue
        if m := STAMP_RE.match(line):
            raw.append((seconds(m.group(1), m.group(2), m.group(3)), [m.group(4)] if m.group(4) else []))
        elif raw:
            raw[-1][1].append(line)
    segments = []
    for i, (start, parts) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else None
        if body := clean(" ".join(parts)):
            segments.append(Segment(start, end, body))
    return segments


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text) if words(s)]


def percentile(values: list[int], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return float(ordered[index])


def hook(segments: list[Segment], all_sentences: list[str]) -> str:
    if segments and segments[0].start is not None:
        return " ".join(s.text for s in segments if s.start is not None and s.start < HOOK_SECONDS)
    taken: list[str] = []
    for sentence in all_sentences:
        taken.append(sentence)
        if sum(len(words(s)) for s in taken) >= HOOK_WORDS:
            break
    return " ".join(taken)


def measure(path: Path) -> TranscriptStats:
    fmt, segments = parse(path.read_text(errors="replace"))
    text = " ".join(s.text for s in segments)
    all_words = words(text)
    all_sentences = sentences(text)
    lengths = [len(words(s)) for s in all_sentences] or [0]
    timed = [s for s in segments if s.start is not None]
    duration: float | None = None
    if timed:
        last = timed[-1]
        # the last YouTube line has no end; give it the pace of the rest
        if last.end is None and len(timed) > 1:
            pace = (last.start - timed[0].start) / max(1, len(words(" ".join(s.text for s in timed[:-1]))))
            duration = last.start + pace * len(words(last.text)) - timed[0].start
        elif last.end is not None:
            duration = last.end - timed[0].start
    wpm = round(len(all_words) / (duration / 60), 1) if duration and duration > 0 else None
    return TranscriptStats(
        file=path.name,
        format=fmt,
        words=len(all_words),
        sentences=len(all_sentences),
        duration_seconds=round(duration, 1) if duration else None,
        words_per_minute=wpm,
        sentence_words_median=float(statistics.median(lengths)),
        sentence_words_p90=percentile(lengths, 0.9),
        question_share=round(
            sum(s.rstrip("\"')]").endswith("?") for s in all_sentences) / max(1, len(all_sentences)), 3
        ),
        second_person_per_100_words=round(
            100 * sum(w.lower() in SECOND_PERSON for w in all_words) / max(1, len(all_words)), 2
        ),
        hook=hook(segments, all_sentences),
    )


def reference_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)


def recommend(stats: list[TranscriptStats]) -> dict[str, float | int | None]:
    """Targets for the style guide's front matter, from the references' medians."""
    paces = [s.words_per_minute for s in stats if s.words_per_minute]
    return {
        "words_per_minute": round(statistics.median(paces)) if paces else None,
        "phrase_words_target": round(statistics.median(s.sentence_words_median for s in stats)) if stats else None,
        "phrase_words_max": round(statistics.median(s.sentence_words_p90 for s in stats)) if stats else None,
    }


def as_dict(stats: TranscriptStats) -> dict:
    return asdict(stats)
