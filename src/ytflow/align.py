"""Real phrase timings from the narration audio.

The script's timings are estimates from the kit's words per minute. Once the
narration exists, ``ytflow align`` replaces them with where each phrase is
actually spoken, by one of three methods:

- ``whisper`` — faster-whisper (the optional ``align`` extra) transcribes the
  audio with word timestamps; the heard words are matched to the script's words
  and each phrase spans its first to last word. Words the recogniser missed or
  misheard take their time from their matched neighbours.
- ``words`` — the same matching, with word timestamps from a JSON file made by
  another tool (``[{"word", "start", "end"}, ...]``, seconds on the narration
  timeline).
- ``chapters`` — no recognition: needs one audio file per chapter; each
  chapter's length is shared among its phrases by character count.

With per-chapter audio the chapters are laid end to end with the kit's
``chapter_break`` of silence between them; that sequence is the narration
timeline every time in ``timing.json`` refers to.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ytflow.script import WORD_RE

COMPILED = "timing.json"
SUBTITLES = "subtitles.srt"
METHODS = ("auto", "whisper", "words", "chapters")
DEFAULT_MODEL = "small"
# Below this share of script words heard, the audio probably is not this script.
MIN_MATCHED = 0.8
MIN_PHRASE_SECONDS = 0.05


class AlignError(Exception):
    """The narration cannot be aligned as asked."""


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class AudioPart:
    file: str
    start: float
    duration: float


@dataclass
class Timing:
    method: str
    audio: list[AudioPart]
    phrases: list[dict]
    chapters: list[dict]
    matched: float | None = None
    interpolated: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(self.audio[-1].start + self.audio[-1].duration, 3) if self.audio else 0.0


def token(word: str) -> str:
    """A word reduced for matching: ASCII, lowercase, letters and digits only."""
    ascii_word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_word.lower())


def lay_out(durations: list[tuple[str, float]], gap: float) -> list[AudioPart]:
    """Audio files end to end with a gap between them."""
    parts, clock = [], 0.0
    for i, (name, seconds) in enumerate(durations):
        if i:
            clock += gap
        parts.append(AudioPart(name, round(clock, 3), round(seconds, 3)))
        clock += seconds
    return parts


def spread(times: list, words: list[str], i: int, j: int, left: float, right: float) -> None:
    """Share left..right among words i..j-1 by character count."""
    right = max(right, left)
    weights = [max(len(words[k]), 1) for k in range(i, j)]
    clock = left
    for k, weight in zip(range(i, j), weights, strict=True):
        step = (right - left) * weight / sum(weights)
        times[k] = (clock, clock + step)
        clock += step


def match_words(script_words: list[str], heard: list[Word], total: float) -> tuple[list[tuple[float, float]], set[int]]:
    """(start, end) for every script word, and the indexes of the words heard exactly.

    A misheard run takes the time of the heard words it replaces; a run that was not
    heard at all shares the time between its neighbours. Both split it by character count.
    """
    a = [token(w) for w in script_words]
    b = [token(w.text) for w in heard]
    times: list[tuple[float, float] | None] = [None] * len(a)
    matched: set[int] = set()
    unheard: list[tuple[int, int]] = []
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(a2 - a1):
                times[a1 + k] = (heard[b1 + k].start, heard[b1 + k].end)
                matched.add(a1 + k)
        elif tag == "replace":
            spread(times, script_words, a1, a2, heard[b1].start, heard[b2 - 1].end)
        elif tag == "delete":
            unheard.append((a1, a2))
    for a1, a2 in unheard:  # after the rest, so both neighbours have times
        left = times[a1 - 1][1] if a1 > 0 else 0.0  # type: ignore[index]
        right = times[a2][0] if a2 < len(times) else total  # type: ignore[index]
        spread(times, script_words, a1, a2, left, right)
    return [t for t in times if t is not None], matched


def phrases_from_words(phrases: list[dict], heard: list[Word], total: float) -> tuple[list[dict], float, list[str]]:
    """Phrase spans from word timestamps: (phrases, share of words matched, fully interpolated phrase names)."""
    words: list[str] = []
    owner: list[int] = []
    for index, phrase in enumerate(phrases):
        for word in WORD_RE.findall(phrase["text"]):
            words.append(word)
            owner.append(index)
    times, matched = match_words(words, heard, total)
    out, interpolated = [], []
    for index, phrase in enumerate(phrases):
        spans = [times[k] for k in range(len(words)) if owner[k] == index]
        if not any(k in matched for k in range(len(words)) if owner[k] == index):
            interpolated.append(phrase["name"])
        out.append({**phrase, "start": spans[0][0], "end": spans[-1][1]})
    return out, (len(matched) / len(words) if words else 1.0), interpolated


def phrases_by_characters(phrases: list[dict], parts: dict[int, AudioPart]) -> list[dict]:
    """Each chapter's audio length shared among its phrases by character count."""
    out = []
    for chapter, part in parts.items():
        mine = [p for p in phrases if p["chapter"] == chapter]
        weights = [len(re.sub(r"\s", "", p["text"])) or 1 for p in mine]
        clock = part.start
        for phrase, weight in zip(mine, weights, strict=True):
            step = part.duration * weight / sum(weights)
            out.append({**phrase, "start": clock, "end": clock + step})
            clock += step
    return out


def tidy(phrases: list[dict]) -> list[dict]:
    """Rounded, in order, never overlapping, never empty."""
    previous_end = 0.0
    out = []
    for phrase in phrases:
        start = max(phrase["start"], previous_end)
        end = max(phrase["end"], start + MIN_PHRASE_SECONDS)
        out.append(
            {
                "name": phrase["name"],
                "chapter": phrase["chapter"],
                "text": phrase["text"],
                "start": round(start, 3),
                "end": round(end, 3),
            }
        )
        previous_end = end
    return out


def chapter_spans(chapters: list[dict], phrases: list[dict]) -> list[dict]:
    out = []
    for chapter in chapters:
        mine = [p for p in phrases if p["chapter"] == chapter["index"]]
        out.append(
            {"index": chapter["index"], "title": chapter["title"], "start": mine[0]["start"], "end": mine[-1]["end"]}
        )
    return out


def transcribe(path: Path, model_name: str, language: str | None) -> list[Word]:
    """Word timestamps from faster-whisper (the optional ``align`` extra)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise AlignError(
            "faster-whisper is not installed — run: uv sync --extra align "
            "(or save one audio file per chapter and use --method chapters)"
        ) from None
    import numpy as np  # installed with faster-whisper

    # Decode with ffmpeg rather than faster-whisper's PyAV reader: one decoder for every
    # step, and immune to PyAV API changes between releases.
    samples = np.frombuffer(decode_16k_mono(path), dtype=np.float32)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(samples, word_timestamps=True, language=language)
    return [Word(w.word.strip(), w.start, w.end) for segment in segments for w in segment.words or []]


def decode_16k_mono(path: Path) -> bytes:
    """The audio as 16 kHz mono float32 samples, the input Whisper expects."""
    import subprocess

    from ytflow.media import MediaError, ffmpeg

    result = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise MediaError(f"cannot decode audio {path}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def load_words(path: Path) -> list[Word]:
    try:
        data = json.loads(path.read_text())
        return [Word(str(w["word"]), float(w["start"]), float(w["end"])) for w in data]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        raise AlignError(
            f"cannot read word timestamps from {path}: expected [{{word, start, end}}, ...] ({err})"
        ) from None


def choose_method(method: str, layout: str, words_file: Path | None) -> str:
    if method == "auto":
        if words_file is not None:
            return "words"
        if whisper_available():
            return "whisper"
        if layout == "chapters":
            return "chapters"
        raise AlignError(
            "one narration file needs faster-whisper to find the phrases — run: uv sync --extra align, "
            "or save one audio file per chapter (audio/<NN>_<chapter>.mp3) for the character-count method"
        )
    if method == "words" and words_file is None:
        raise AlignError("--method words needs --words FILE")
    if method == "chapters" and layout != "chapters":
        raise AlignError("--method chapters needs one audio file per chapter (audio/<NN>_<chapter>.mp3)")
    return method


def align(
    script: dict,
    parts: list[AudioPart],
    chapter_of_part: list[int | None],
    method: str,
    heard: Callable[[], list[Word]] | None = None,
) -> Timing:
    """Phrase and chapter times on the narration timeline."""
    total = parts[-1].start + parts[-1].duration
    matched: float | None = None
    interpolated: list[str] = []
    if method == "chapters":
        by_chapter = {c: p for c, p in zip(chapter_of_part, parts, strict=True) if c is not None}
        raw = phrases_by_characters(script["phrases"], by_chapter)
    else:
        assert heard is not None
        raw, matched, interpolated = phrases_from_words(script["phrases"], heard(), total)
    phrases = tidy(raw)
    return Timing(method, parts, phrases, chapter_spans(script["chapters"], phrases), matched, interpolated)


def srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(phrases: list[dict]) -> str:
    blocks = [f"{i}\n{srt_time(p['start'])} --> {srt_time(p['end'])}\n{p['text']}\n" for i, p in enumerate(phrases, 1)]
    return "\n".join(blocks)


def write(version: Path, timing: Timing, script_version: str, voiceover_version: str) -> None:
    data = {
        "script_version": script_version,
        "voiceover_version": voiceover_version,
        "method": timing.method,
        "timing": "aligned",
        "matched": None if timing.matched is None else round(timing.matched, 3),
        "duration": timing.duration,
        "audio": [asdict(p) for p in timing.audio],
        "chapters": timing.chapters,
        "phrases": timing.phrases,
    }
    (version / COMPILED).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (version / SUBTITLES).write_text(srt(timing.phrases))
