"""The editor-neutral timeline: what the edit is, before any editor is involved.

``ytflow timeline build`` reads the aligned timing (``timing/v<N>/timing.json``),
the images (``images/<name>.*``), the narration audio and the kit's
``edit-preset.toml``, and writes ``timeline/v<N>/timeline.json``:

- one **clip** per phrase: its image, on screen from the moment its phrase is
  spoken until the next phrase starts, with a slow **camera move** across it;
- a **transition** centred on every cut, varied across the video; chapter
  changes always get the calm one (the first type in the preset);
- one **subtitle** per phrase, wrapped to the preset's line length and held
  long enough to read;
- a **chapter title** at the start of each chapter, in the top-left corner;
- a fade in at the start and a fade out at the end.

Every time is in seconds and lies on a frame boundary. Exporters (Kdenlive
first, an ffmpeg preview) turn this file into a project; they make no edit
decisions of their own.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

COMPILED = "timeline.json"

TRANSITIONS = (
    "dissolve",
    "wipe-left",
    "wipe-right",
    "wipe-up",
    "wipe-down",
    "slide-left",
    "slide-right",
    "slide-up",
    "slide-down",
)
BOX_STYLES = ("block", "lines")
MOVES = ("zoom-in", "zoom-out", "pan-left", "pan-right", "pan-up", "pan-down")

PRESET_DEFAULTS: dict[str, dict] = {
    "subtitles": {
        "font": "Noto Sans",
        "size": 48,
        "color": "#ffffff",
        "box_color": "#000000",
        "box_opacity": 0.6,
        "max_chars_per_line": 42,
        "max_lines": 2,
        "margin_bottom": 60,
        "min_seconds": 1.0,
        "bold": False,
        "box_padding": 12,
        "box_style": "block",  # one box around the whole subtitle (libass >= 0.17); "lines": one per line
        "highlight_color": "#ffd166",
        "fade_ms": 0,
    },
    "chapters": {
        "position": "top-left",
        "font": "Noto Sans",
        "size": 40,
        "seconds": 5.0,
        "margin": 48,
        "color": "#ffffff",
        "box_opacity": 0.6,
        "bold": True,
        "underline": False,
        "slide": False,
    },
    "video": {"width": 1920, "height": 1080, "fps": 30, "fade_in_seconds": 1.0, "fade_out_seconds": 1.5},
    "audio": {"lead_seconds": 0.5, "tail_seconds": 1.5},
    "transitions": {"types": ["dissolve", "wipe-left", "wipe-right", "slide-up"], "seconds": 0.6},
    "camera": {"moves": ["zoom-in", "zoom-out", "pan-left", "pan-right"], "max_zoom": 1.12, "zoom_per_second": 0.03},
}

# Reading speed above which a subtitle is hard to follow (characters per second).
MAX_CHARS_PER_SECOND = 20
# Gaps between subtitles shorter than this are closed, so text does not flicker.
CLOSE_GAP_SECONDS = 0.7


class TimelineError(Exception):
    """The timeline cannot be built from these inputs."""


def load_preset(path: Path) -> dict:
    """edit-preset.toml over the defaults, so a kit made before a new key still works."""
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as err:
        raise TimelineError(f"{path.name}: not valid TOML: {err}") from None
    preset = {section: dict(values) for section, values in PRESET_DEFAULTS.items()}
    for section, values in data.items():
        if isinstance(values, dict):
            preset.setdefault(section, {}).update(values)
    return preset


def is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def check_preset(preset: dict) -> list[str]:
    problems = []

    def number(section: str, key: str, low: float, high: float) -> None:
        value = preset[section].get(key)
        if not is_number(value):
            problems.append(f"[{section}] {key} must be a number")
        elif not low <= value <= high:
            problems.append(f"[{section}] {key} = {value} is outside {low}–{high}")

    number("subtitles", "size", 16, 160)
    number("subtitles", "box_opacity", 0, 1)
    number("subtitles", "max_chars_per_line", 20, 80)
    number("subtitles", "max_lines", 1, 3)
    number("subtitles", "margin_bottom", 0, 400)
    number("subtitles", "min_seconds", 0.5, 3)
    number("subtitles", "box_padding", 0, 80)
    number("subtitles", "fade_ms", 0, 1000)
    number("chapters", "box_opacity", 0, 1)
    if preset["subtitles"].get("box_style") not in BOX_STYLES:
        problems.append(f"[subtitles] box_style must be one of {', '.join(BOX_STYLES)}")
    for section, key in (("subtitles", "bold"), ("chapters", "bold"), ("chapters", "underline"), ("chapters", "slide")):
        if not isinstance(preset[section].get(key), bool):
            problems.append(f"[{section}] {key} must be true or false")
    number("chapters", "size", 16, 160)
    number("chapters", "seconds", 1, 30)
    number("chapters", "margin", 0, 400)
    number("video", "width", 320, 7680)
    number("video", "height", 240, 4320)
    number("video", "fps", 12, 120)
    number("video", "fade_in_seconds", 0, 5)
    number("video", "fade_out_seconds", 0, 5)
    number("audio", "lead_seconds", 0, 5)
    number("audio", "tail_seconds", 0, 10)
    number("transitions", "seconds", 0.1, 2)
    number("camera", "max_zoom", 1, 1.5)
    number("camera", "zoom_per_second", 0.005, 0.2)
    for section, key in (
        ("subtitles", "color"),
        ("subtitles", "box_color"),
        ("subtitles", "highlight_color"),
        ("chapters", "color"),
    ):
        value = preset[section].get(key)
        if not (isinstance(value, str) and len(value) == 7 and value.startswith("#")):
            problems.append(f"[{section}] {key} must be a colour like #ffffff")
    if preset["chapters"].get("position") != "top-left":
        problems.append('[chapters] position must be "top-left" (the only position so far)')
    for section, key, allowed in (("transitions", "types", TRANSITIONS), ("camera", "moves", MOVES)):
        values = preset[section].get(key)
        if not isinstance(values, list) or not values:
            problems.append(f"[{section}] {key} must be a non-empty list")
            continue
        unknown = [v for v in values if v not in allowed]
        if unknown:
            problems.append(f"[{section}] unknown {key}: {', '.join(map(str, unknown))} (known: {', '.join(allowed)})")
    return problems


def check_preset_file(path: Path) -> list[str]:
    try:
        return check_preset(load_preset(path))
    except TimelineError as err:
        return [str(err).removeprefix(f"{path.name}: ")]


@dataclass
class Frames:
    """Snaps seconds to frame boundaries."""

    fps: int

    def snap(self, seconds: float) -> float:
        return round(round(seconds * self.fps) / self.fps, 4)

    @property
    def one(self) -> float:
        return 1 / self.fps


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap, then balanced: two lines of similar length read better than one long and one short."""
    words = text.split()
    lines: list[str] = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    if len(lines) == 2:  # move words down while it makes the lines more even
        best = lines
        for split in range(1, len(words)):
            first, second = " ".join(words[:split]), " ".join(words[split:])
            if len(first) <= width and len(second) <= width:
                if abs(len(first) - len(second)) < abs(len(best[0]) - len(best[1])):
                    best = [first, second]
        lines = best
    return lines


def blocks(text: str, width: int, max_lines: int, highlights: list[list[int]] | None = None) -> list[dict]:
    """The phrase cut into on-screen blocks of at most max_lines lines, each with its highlight spans.

    A block is {"text", "lines", "highlights"}; spans are [start, end) in the block's text, which is
    its lines joined by single spaces.
    """
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    lines: list[list[tuple[int, int]]] = []
    for word in words:
        if lines and lines[-1][-1][1] - lines[-1][0][0] + 1 + (word[1] - word[0]) <= width:
            lines[-1].append(word)
        else:
            lines.append([word])
    out = []
    for i in range(0, len(lines), max_lines):
        chunk = [w for line in lines[i : i + max_lines] for w in line]
        pieces = [text[a:b] for a, b in chunk]
        block_text = " ".join(pieces)
        spans, offset = [], 0
        for (a, b), piece in zip(chunk, pieces, strict=True):
            for hs, he in highlights or []:
                lo, hi = max(a, hs), min(b, he)
                if lo < hi:
                    spans.append([offset + lo - a, offset + hi - a])
            offset += len(piece) + 1
        merged: list[list[int]] = []
        for span in spans:  # neighbouring highlighted words become one span, the space between included
            if merged and span[0] <= merged[-1][1] + 1:
                merged[-1][1] = span[1]
            else:
                merged.append(span)
        out.append({"text": block_text, "lines": wrap(block_text, width), "highlights": merged})
    return out


def rect(x: float, y: float, w: float, h: float) -> dict:
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def camera(move: str, seconds: float, max_zoom: float, per_second: float) -> dict:
    """The part of the image in view at the clip's start and end, as fractions of the image."""
    zoom = 1 + min(max_zoom - 1, per_second * seconds)
    side = 1 / zoom
    full, centre = rect(0, 0, 1, 1), rect((1 - side) / 2, (1 - side) / 2, side, side)
    mid = (1 - side) / 2
    ends = {
        "zoom-in": (full, centre),
        "zoom-out": (centre, full),
        "pan-left": (rect(1 - side, mid, side, side), rect(0, mid, side, side)),
        "pan-right": (rect(0, mid, side, side), rect(1 - side, mid, side, side)),
        "pan-up": (rect(mid, 1 - side, side, side), rect(mid, 0, side, side)),
        "pan-down": (rect(mid, 0, side, side), rect(mid, 1 - side, side, side)),
    }
    start, end = ends[move]
    return {"type": move, "zoom": round(zoom, 4), "from": start, "to": end}


def transition_types(types: list[str], count: int, chapter_cuts: set[int]) -> list[str]:
    """One type per cut: the calm first type at chapter changes; inside a chapter, a varied
    type and the calm one alternate, the varied ones taking turns across the whole video."""
    calm, others = types[0], types[1:] or types[:1]
    out, turn, since_chapter = [], 0, 0
    for cut in range(count):
        if cut in chapter_cuts:
            out.append(calm)
            since_chapter = 0
            continue
        since_chapter += 1
        if since_chapter % 2:
            out.append(others[turn % len(others)])
            turn += 1
        else:
            out.append(calm)
    return out


@dataclass
class Timeline:
    data: dict
    warnings: list[str] = field(default_factory=list)


def build(
    timing: dict,
    images: dict[str, str],
    preset: dict,
    sources: dict,
    highlights: dict[str, list[list[int]]] | None = None,
) -> Timeline:
    """The timeline from aligned timing, image paths per phrase name and the edit preset."""
    video, audio = preset["video"], preset["audio"]
    frames = Frames(int(video["fps"]))
    lead = frames.snap(audio["lead_seconds"])
    phrases = timing["phrases"]
    duration = frames.snap(lead + timing["duration"] + audio["tail_seconds"])
    warnings: list[str] = []

    missing = [p["name"] for p in phrases if p["name"] not in images]
    if missing:
        raise TimelineError(f"{len(missing)} image(s) missing, first {missing[0]} — run: ytflow images check")

    # cuts: the image changes when its phrase starts being spoken
    cuts = [0.0] + [frames.snap(lead + p["start"]) for p in phrases[1:]] + [duration]
    chapter_cuts = {i for i in range(1, len(phrases)) if phrases[i]["chapter"] != phrases[i - 1]["chapter"]}
    types = transition_types(preset["transitions"]["types"], len(phrases) - 1, {c - 1 for c in chapter_cuts})
    moves = preset["camera"]["moves"]

    transitions = []
    for i in range(1, len(phrases)):
        shorter = min(cuts[i] - cuts[i - 1], cuts[i + 1] - cuts[i])
        seconds = frames.snap(min(preset["transitions"]["seconds"], shorter / 2))
        if seconds < 2 * frames.one:
            seconds = 0.0  # a clip too short to share: a straight cut
        transitions.append({"at": cuts[i], "seconds": seconds, "type": types[i - 1] if seconds else "cut"})

    clips = []
    for i, phrase in enumerate(phrases):
        before = transitions[i - 1]["seconds"] / 2 if i else 0.0
        after = transitions[i]["seconds"] / 2 if i < len(transitions) else 0.0
        start, end = frames.snap(cuts[i] - before), frames.snap(cuts[i + 1] + after)
        move = camera(
            moves[i % len(moves)], end - start, preset["camera"]["max_zoom"], preset["camera"]["zoom_per_second"]
        )
        clips.append(
            {"name": phrase["name"], "image": images[phrase["name"]], "start": start, "end": end, "camera": move}
        )

    style = preset["subtitles"]
    subtitles = []
    for i, phrase in enumerate(phrases):
        start = frames.snap(lead + phrase["start"])
        end = frames.snap(lead + phrase["end"])
        following = frames.snap(lead + phrases[i + 1]["start"]) if i + 1 < len(phrases) else duration
        end = max(end, start + style["min_seconds"])
        if following - end < CLOSE_GAP_SECONDS:
            end = following
        end = frames.snap(min(end, following - 2 * frames.one) if i + 1 < len(phrases) else min(end, duration))
        cps = len(phrase["text"]) / max(end - start, frames.one)
        if cps > MAX_CHARS_PER_SECOND:
            warnings.append(f"{phrase['name']}: {cps:.0f} characters per second is fast to read")
        # a phrase too long for max_lines becomes consecutive blocks, timed by their share of its characters
        parts = blocks(
            phrase["text"],
            int(style["max_chars_per_line"]),
            int(style["max_lines"]),
            (highlights or {}).get(phrase["name"]),
        )
        total = sum(len(b["text"]) for b in parts)
        clock = start
        for k, part in enumerate(parts):
            share = len(part["text"]) / total
            stop = end if k == len(parts) - 1 else frames.snap(clock + (end - start) * share)
            subtitles.append({"name": phrase["name"], "start": clock, "end": stop, **part})
            clock = stop

    fade_in = frames.snap(video["fade_in_seconds"])
    chapters = []
    for chapter in timing["chapters"]:
        start = frames.snap(max(lead + chapter["start"], fade_in))
        end = frames.snap(min(start + preset["chapters"]["seconds"], lead + chapter["end"]))
        chapters.append({"index": chapter["index"], "title": chapter["title"], "start": start, "end": max(end, start)})

    data = {
        "version": 1,
        "sources": sources,
        "video": {
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": int(video["fps"]),
            "duration": duration,
            "fade_in": fade_in,
            "fade_out": frames.snap(video["fade_out_seconds"]),
        },
        "audio": [
            {"file": a["file"], "start": frames.snap(lead + a["start"]), "duration": a["duration"]}
            for a in timing["audio"]
        ],
        "clips": clips,
        "transitions": transitions,
        "subtitles": subtitles,
        "chapters": chapters,
        "style": {"subtitles": dict(style), "chapters": dict(preset["chapters"])},
    }
    return Timeline(data, warnings)


def write(version: Path, timeline: Timeline) -> Path:
    path = version / COMPILED
    path.write_text(json.dumps(timeline.data, indent=2, ensure_ascii=False) + "\n")
    return path


def load(path: Path) -> dict:
    return json.loads(path.read_text())
