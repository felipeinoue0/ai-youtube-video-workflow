"""The title, description, tags and captions YouTube gets for a video.

The kit's ``publish.md`` is the channel's template: ``base_tags`` in its front
matter, and below it the description every video gets, with a ``{summary}``
and a ``{chapters}`` slot (``{title}`` may appear too).

Per video, ``ytflow publish init`` starts ``publish/v<N>/publish.md``::

    <!-- timeline v3 · kit v1 -->
    # The chosen title

    ## Summary
    Two or three sentences that open the description.

    ## Tags
    - a video tag

``ytflow publish build`` checks it against YouTube's limits and writes, next to
it, ``title.txt``, ``description.txt`` (the template filled in, chapter
timestamps from the timeline), ``tags.txt``, ``captions.srt`` (the timeline's
subtitles, to upload as captions) and ``publish.json``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ytflow.align import srt_time

SOURCE = "publish.md"
COMPILED = "publish.json"
TODO = "TODO"
HEADER_RE = re.compile(r"<!--\s*timeline (v\d+)\s*·\s*kit (v\d+)\s*-->")

# YouTube's limits
TITLE_MAX = 100
TITLE_VISIBLE = 70  # longer titles are cut off in search results and suggestions
DESCRIPTION_MAX = 5000
TAGS_MAX = 500  # characters, counting the commas and the quotes around multi-word tags
CHAPTERS_MIN = 3
CHAPTER_MIN_SECONDS = 10


def tags_field(tags: list[str]) -> str:
    """Tags as YouTube counts them: comma-separated, multi-word tags in quotes."""
    return ",".join(f'"{t}"' if " " in t else t for t in tags)


def check_template(data: dict, body: str) -> list[str]:
    """Problems with the kit's publish.md."""
    problems = []
    tags = data.get("base_tags")
    if not isinstance(tags, list) or not tags or not all(isinstance(t, str) and t.strip() for t in tags):
        problems.append("base_tags must be a non-empty list of tags every video gets")
    for slot in ("{summary}", "{chapters}"):
        count = body.count(slot)
        if count != 1:
            problems.append(f"the description template needs {slot} exactly once (found {count})")
    if re.search(r"[<>]", body):
        problems.append("YouTube rejects '<' and '>' in a description")
    return problems


def template_body(text: str) -> str:
    """The description template: the file after its front matter."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "+++":
        end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "+++"), len(lines) - 1)
        lines = lines[end + 1 :]
    return "\n".join(lines).strip("\n")


def init_text(timeline_version: str, kit_version: str, previous: str | None = None) -> str:
    """A new publish.md; the title, summary and tags carry over from the previous version."""
    header = f"<!-- timeline {timeline_version} · kit {kit_version} -->"
    if previous:
        return HEADER_RE.sub(header, previous, count=1) if HEADER_RE.search(previous) else f"{header}\n{previous}"
    return f"""{header}
# {TODO}: the chosen title

> Write 5 title options here as '>' notes; the creator picks one and it
> replaces the line above. Lines starting with '>' are ignored.

## Summary
{TODO}: two or three sentences that open the description: the promise of the video, in the channel's tone.

## Tags
- {TODO}: tags for this video only (the kit's base tags are added)
"""


@dataclass
class Metadata:
    title: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)  # slot name -> text, for the template's {slot}s
    timeline_version: str | None = None
    kit_version: str | None = None


def slot_name(heading: str) -> str:
    """The template slot a '## Heading' fills: lowercase ASCII, other characters as '_'."""
    ascii_text = unicodedata.normalize("NFKD", heading).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def paragraphs(lines: list[str]) -> str:
    """Lines joined with spaces, a blank line kept as a paragraph break."""
    out, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return "\n\n".join(out)


def parse(text: str) -> tuple[Metadata, list[str]]:
    meta = Metadata()
    problems: list[str] = []
    header = HEADER_RE.search(text)
    if header:
        meta.timeline_version, meta.kit_version = header.groups()
    section = None
    bodies: dict[str, list[str]] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith(">") or HEADER_RE.fullmatch(stripped):
            continue
        if stripped.startswith("## "):
            section = slot_name(stripped[3:])
            bodies.setdefault(section, [])
        elif stripped.startswith("# ") and section is None:
            if meta.title:
                problems.append(f"line {number}: a second '# ' title")
            meta.title = stripped[2:].strip()
        elif section == "tags":
            if stripped.startswith(("- ", "* ")):
                meta.tags.append(stripped[2:].strip())
            elif stripped:
                problems.append(f"line {number}: under Tags, one '- ' tag per line")
        elif section is not None:
            bodies[section].append(line)
        elif stripped:
            problems.append(f"line {number}: text before the first '## ' section")
    meta.summary = paragraphs(bodies.pop("summary", []))
    bodies.pop("tags", None)
    meta.sections = {name: "\n".join(lines).strip("\n") for name, lines in bodies.items()}
    return meta, problems


def chapter_lines(timeline: dict) -> tuple[list[str], list[str]]:
    """'0:00 Title' lines from the timeline's chapters, and why YouTube would ignore them."""
    duration = timeline["video"]["duration"]
    chapters = timeline["chapters"]
    starts = [0.0] + [c["start"] for c in chapters[1:]]
    lines, warnings = [], []
    for i, (chapter, start) in enumerate(zip(chapters, starts, strict=True)):
        seconds = int(start)
        stamp = (
            f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
            if duration >= 3600
            else f"{seconds // 60}:{seconds % 60:02d}"
        )
        lines.append(f"{stamp} {chapter['title']}")
        end = starts[i + 1] if i + 1 < len(starts) else duration
        if end - start < CHAPTER_MIN_SECONDS:
            warnings.append(f"chapter {chapter['title']!r} is {end - start:.0f}s; YouTube needs {CHAPTER_MIN_SECONDS}s")
    if len(chapters) < CHAPTERS_MIN:
        warnings.append(f"{len(chapters)} chapter(s): YouTube shows chapters only from {CHAPTERS_MIN}")
    return lines, warnings


def dedupe(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for tag in tags:
        key = " ".join(tag.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(" ".join(tag.split()))
    return out


@dataclass
class Result:
    title: str
    description: str
    tags: list[str]
    warnings: list[str]


def build(meta: Metadata, template: str, base_tags: list[str], timeline: dict) -> tuple[Result | None, list[str]]:
    problems: list[str] = []
    if not meta.title or TODO in meta.title:
        problems.append("the '# ' title line is missing or still TODO — the creator picks one of the options")
    elif len(meta.title) > TITLE_MAX:
        problems.append(f"title is {len(meta.title)} characters; YouTube allows {TITLE_MAX}")
    if not meta.summary or TODO in meta.summary:
        problems.append("the Summary is missing or still TODO")
    if any(TODO in t for t in meta.tags):
        problems.append("a tag is still TODO")
    for name, value in meta.sections.items():
        if TODO in value:
            problems.append(f"the '{name}' section is still TODO")
    for name, value in (("title", meta.title), ("summary", meta.summary), *meta.sections.items()):
        if re.search(r"[<>]", value):
            problems.append(f"YouTube rejects '<' and '>' in the {name}")
    if problems:
        return None, problems

    warnings: list[str] = []
    if len(meta.title) > TITLE_VISIBLE:
        warnings.append(f"title is {len(meta.title)} characters; past {TITLE_VISIBLE} it is cut off in search")
    lines, chapter_warnings = chapter_lines(timeline)
    if chapter_warnings:
        warnings += chapter_warnings
        warnings.append("the chapter list is left out of the description: YouTube would not show it")
        lines = []
        # and a label line right above the slot ("Chapters:") with it
        template = re.sub(r"(?m)^[^\n{}]{1,40}:[ \t]*\n(?=\{chapters\})", "", template)
    slots = {**meta.sections, "summary": meta.summary, "chapters": "\n".join(lines), "title": meta.title}
    wanted = set(re.findall(r"\{(\w+)\}", template))
    for name in sorted(wanted - slots.keys()):
        problems.append(f"the template's {{{name}}} needs a '## {name.replace('_', ' ').capitalize()}' section")
    for name in sorted(meta.sections.keys() - wanted):
        warnings.append(f"section '{name}' is not in the description template — left out")
    # one pass, so text inside a section is never read as a placeholder
    description = re.sub(r"\{(\w+)\}", lambda m: slots.get(m.group(1), m.group(0)), template)
    description = re.sub(r"\n{3,}", "\n\n", description).strip() + "\n"
    if len(description.encode()) > DESCRIPTION_MAX:
        problems.append(f"description is {len(description.encode())} bytes; YouTube allows {DESCRIPTION_MAX}")
    tags = dedupe(base_tags + meta.tags)
    field_ = tags_field(tags)
    if len(field_) > TAGS_MAX:
        problems.append(f"tags take {len(field_)} characters; YouTube allows {TAGS_MAX} — drop some video tags")
    if problems:
        return None, problems
    return Result(meta.title, description, tags, warnings), []


def captions(timeline: dict) -> str:
    blocks = [
        f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n" + "\n".join(s["lines"]) + "\n"
        for i, s in enumerate(timeline["subtitles"], 1)
    ]
    return "\n".join(blocks)


def write(version: Path, result: Result, timeline: dict, sources: dict) -> None:
    (version / "title.txt").write_text(result.title + "\n")
    (version / "description.txt").write_text(result.description)
    (version / "tags.txt").write_text(", ".join(result.tags) + "\n")
    (version / "captions.srt").write_text(captions(timeline))
    data = {**sources, "title": result.title, "description": result.description, "tags": result.tags}
    (version / COMPILED).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
