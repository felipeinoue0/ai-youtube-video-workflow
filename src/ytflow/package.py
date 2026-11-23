"""The video's working files in one folder, and the timed transcript of a script.

``ytflow script build`` writes ``transcript.md`` next to ``script.json``: every
line with its start, end, duration and image name, chapter by chapter.

``ytflow package`` gathers what the creator takes to the external tools into
``package/v<N>/``:

- ``script-timed.md`` — the transcript: time and line, per chapter;
- ``elevenlabs.txt`` and ``elevenlabs/<NN>_<chapter>.txt`` — only the spoken
  lines, to paste into ElevenLabs as they are: the pronunciation spellings are
  applied, chapters are separated by a blank line, and there is no markup (the
  voiceover step's ``narration.txt`` keeps its ``<break>`` pause tags);
- ``flow-prompts.txt`` — the Google Flow prompts, one per image;
- ``scenes.md`` — per image: its name ``<enumerate_id>_<part_of_phrase>``, its
  time, its line and what the scene shows;
- ``manifest.json`` — which versions of each step the package was made from.

Times are the script's estimates until ``ytflow align`` has timed the
narration of the same script version; then they are the real ones.
"""

from __future__ import annotations

import json
from pathlib import Path

TRANSCRIPT = "transcript.md"
MANIFEST = "manifest.json"


def stamp(seconds: float) -> str:
    """0:04.6, or 1:02:03.4 past an hour."""
    tenths = round(seconds * 10)
    minutes, tenths = divmod(tenths, 600)
    hours, minutes = divmod(minutes, 60)
    second = f"{tenths // 10:02d}.{tenths % 10}"
    return f"{hours}:{minutes:02d}:{second}" if hours else f"{minutes}:{second}"


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def timed(script: dict, timing: dict | None) -> tuple[list[dict], list[dict]]:
    """(phrases, chapters) with the aligned times when a timing is given, else the script's estimates."""
    if timing is None:
        return script["phrases"], script["chapters"]
    times = {p["name"]: p for p in timing["phrases"]}
    phrases = [{**p, "start": times[p["name"]]["start"], "end": times[p["name"]]["end"]} for p in script["phrases"]]
    spans = {c["index"]: c for c in timing["chapters"]}
    chapters = [{**c, "start": spans[c["index"]]["start"], "end": spans[c["index"]]["end"]} for c in script["chapters"]]
    return phrases, chapters


def times_note(script: dict, timing: dict | None) -> str:
    if timing is None:
        return (
            f"Times are **estimated** at {script['words_per_minute']:g} words per minute; "
            "`ytflow align` replaces them with the narration's real times."
        )
    return f"Times are **aligned** to the narration ({timing['method']})."


def transcript(script: dict, timing: dict | None = None) -> str:
    """The script as a timed transcript: per chapter, a table of every line."""
    phrases, chapters = timed(script, timing)
    total = phrases[-1]["end"] if phrases else 0.0
    out = [
        f"# {script['title']}",
        "",
        times_note(script, timing),
        "",
        f"Total {stamp(total)} · {len(phrases)} lines · {len(chapters)} chapters",
    ]
    for chapter in chapters:
        out += [
            "",
            f"## {stamp(chapter['start'])} — {chapter['title']}",
            "",
            "| # | Start | End | Duration | Image | Line |",
            "|---|---|---|---|---|---|",
        ]
        for phrase in (p for p in phrases if p["chapter"] == chapter["index"]):
            length = phrase["end"] - phrase["start"]
            out.append(
                f"| {phrase['id']} | {stamp(phrase['start'])} | {stamp(phrase['end'])} | {length:.1f} s "
                f"| {phrase['name']} | {cell(phrase['text'])} |"
            )
    return "\n".join(out) + "\n"


def scenes(script: dict, prompts: dict, timing: dict | None = None) -> str:
    """Per image: name, time, line and scene, chapter by chapter."""
    phrases, chapters = timed(script, timing)
    scene_of = {p["name"]: p["scene"] for p in prompts["prompts"]}
    out = [
        f"# Scenes — {script['title']}",
        "",
        "One image per line, generated in Google Flow from `flow-prompts.txt` and saved as",
        "`images/<name>.png` (the name below). " + times_note(script, timing),
    ]
    for chapter in chapters:
        out += ["", f"## {stamp(chapter['start'])} — {chapter['title']}"]
        for phrase in (p for p in phrases if p["chapter"] == chapter["index"]):
            length = phrase["end"] - phrase["start"]
            out += [
                "",
                f"### {phrase['name']}",
                f"{stamp(phrase['start'])} – {stamp(phrase['end'])} ({length:.1f} s)",
                "",
                f"> {phrase['text']}",
                "",
                f"Scene: {scene_of[phrase['name']]}",
            ]
    return "\n".join(out) + "\n"


def write(
    target: Path,
    script: dict,
    prompts: dict,
    timing: dict | None,
    sources: dict[str, Path | None],
) -> list[Path]:
    """Write the package into ``target``; ``sources`` maps step name to the version directory used."""
    voiceover, prompts_dir = sources["voiceover"], sources["prompts"]
    assert voiceover is not None and prompts_dir is not None
    written = []

    def put(name: str, text: str) -> None:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)

    put("script-timed.md", transcript(script, timing))
    chapters = sorted((voiceover / "chapters").glob("*.txt"))
    # only what the voice says: the chapter texts, no <break> tags a model could read aloud
    put("elevenlabs.txt", "\n\n".join(c.read_text().strip() for c in chapters) + "\n")
    for chapter in chapters:
        put(f"elevenlabs/{chapter.name}", chapter.read_text())
    put("flow-prompts.txt", (prompts_dir / "prompts.txt").read_text())
    put("scenes.md", scenes(script, prompts, timing))
    manifest = {step: (path.name if path else None) for step, path in sources.items()}
    manifest["times"] = "aligned" if timing else "estimated"
    put(MANIFEST, json.dumps(manifest, indent=2) + "\n")
    return written
