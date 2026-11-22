"""Image prompts: one scene per phrase, composed with the kit's visual anchor.

``prompts init`` writes ``prompts.md`` from the script, one section per phrase::

    ## 001_what-if-the-greatest-empire
    > What if the greatest empire in history was never conquered at all?
    scene: TODO(ytflow)

The agent replaces each ``TODO`` with the scene: subject, action, setting,
framing. ``prompts build`` appends the kit's anchor and avoid list to every
scene **verbatim**, so every image of every video carries the same style text,
and writes ``prompts.txt`` (to paste into Google Flow) and ``prompts.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ytflow.workspace import TODO_MARK

SOURCE = "prompts.md"
TEXT = "prompts.txt"
COMPILED = "prompts.json"
SCENE_WORDS = (5, 60)
HEADER_RE = re.compile(r"^<!-- script (v\d+) · kit (v\d+) -->$")


@dataclass
class Scene:
    name: str
    phrase: str
    scene: str
    line: int


def init_text(script: dict, script_version: str, kit_version: str, carried: dict[tuple[str, str], str]) -> str:
    """The prompts.md skeleton. carried maps (name, phrase) to a scene written in an earlier version."""
    parts = [
        f"<!-- script {script_version} · kit {kit_version} -->\n",
        f"# Image prompts — {script['title']}\n",
        "Write each scene: subject, action, setting, framing. No style words: the kit's anchor is added to\n"
        "every prompt by `ytflow prompts build`.\n",
    ]
    for phrase in script["phrases"]:
        scene = carried.get((phrase["name"], phrase["text"]), TODO_MARK)
        parts.append(f"## {phrase['name']}\n> {phrase['text']}\nscene: {scene}\n")
    return "\n".join(parts)


def written_scenes(text: str) -> dict[tuple[str, str], str]:
    """Scenes already written in a prompts.md, keyed by (name, phrase)."""
    _, scenes, _ = parse(text)
    return {(s.name, s.phrase): s.scene for s in scenes if s.scene and TODO_MARK not in s.scene}


def parse(text: str) -> tuple[str | None, list[Scene], list[str]]:
    """(script version, scenes, problems)."""
    script_version = None
    scenes: list[Scene] = []
    problems: list[str] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if m := HEADER_RE.match(line):
            script_version = m.group(1)
        elif line.startswith("## "):
            scenes.append(Scene(line[3:].strip(), "", "", number))
        elif not scenes:
            continue  # title and instructions above the first section
        elif line.startswith("> "):
            scenes[-1].phrase = line[2:].strip()
        elif line.startswith("scene:"):
            scenes[-1].scene = line[len("scene:") :].strip()
        elif line and scenes[-1].scene:
            scenes[-1].scene += " " + line  # a scene may wrap onto more lines
        elif line:
            problems.append(f"line {number}: expected '> phrase' or 'scene:' under {scenes[-1].name}")
    return script_version, scenes, problems


def compose(scene: str, anchor: str, avoid: str) -> str:
    prompt = f"{scene.rstrip('. ')}. {anchor.rstrip('. ')}."
    if avoid.strip():
        prompt += f" No {avoid.strip().rstrip('.')}."
    return prompt


def build(text: str, script: dict, anchor: str, avoid: str) -> tuple[list[dict] | None, list[str]]:
    """Validate the scenes against the script and compose the prompts."""
    _, scenes, problems = parse(text)
    expected = [p["name"] for p in script["phrases"]]
    found = [s.name for s in scenes]
    if found != expected:
        missing = [n for n in expected if n not in found]
        extra = [n for n in found if n not in expected]
        if missing:
            problems.append(f"sections missing for: {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}")
        if extra:
            problems.append(f"sections not in the script: {', '.join(extra[:5])}{' …' if len(extra) > 5 else ''}")
        if not missing and not extra:
            problems.append("sections are not in script order")
    anchor_words = anchor.lower()
    for s in scenes:
        words = len(s.scene.split())
        if not s.scene or TODO_MARK in s.scene:
            problems.append(f"line {s.line}: {s.name} has no scene yet")
        elif not SCENE_WORDS[0] <= words <= SCENE_WORDS[1]:
            problems.append(
                f"line {s.line}: {s.name} scene is {words} words; keep it {SCENE_WORDS[0]}–{SCENE_WORDS[1]}"
            )
        elif anchor_words and anchor_words[:40] in s.scene.lower():
            problems.append(f"line {s.line}: {s.name} repeats the anchor; it is added by the build")
    if problems:
        return None, problems
    by_name = {p["name"]: p for p in script["phrases"]}
    return [
        {"name": s.name, "phrase": by_name[s.name]["text"], "scene": s.scene, "prompt": compose(s.scene, anchor, avoid)}
        for s in scenes
    ], []


def prompts_text(prompts: list[dict]) -> str:
    return "\n".join(f"{p['name']}\n{p['prompt']}\n" for p in prompts)


def write(directory: Path, prompts: list[dict], script_version: str, kit_version: str) -> None:
    (directory / TEXT).write_text(prompts_text(prompts))
    data = {"script_version": script_version, "kit_version": kit_version, "prompts": prompts}
    (directory / COMPILED).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
