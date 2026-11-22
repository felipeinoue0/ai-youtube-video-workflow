"""The channel kit's machine-readable parts, and their checks.

Prose kit files may start with TOML front matter between ``+++`` lines. That is
where later steps read exact values from: the script's pace and phrase length,
the image prompts' visual anchor. Everything below the front matter is for the
agent and the creator to read.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path

from ytflow.workspace import KIT_TEMPLATES, TODO_MARK

FENCE = "+++"
ASPECT_RATIOS = ("16:9", "9:16", "1:1")


class KitError(Exception):
    """A kit file cannot be read."""


def front_matter(path: Path) -> dict:
    """The TOML between the leading ``+++`` lines; {} when there is none."""
    text = path.read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return {}
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == FENCE)
    except StopIteration:
        raise KitError(f"{path.name}: front matter opened with {FENCE} is never closed") from None
    try:
        return tomllib.loads("\n".join(lines[1:end]))
    except tomllib.TOMLDecodeError as err:
        raise KitError(f"{path.name}: front matter is not valid TOML: {err}") from None


def number(data: dict, key: str, low: float, high: float) -> list[str]:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        return [f"{key} is missing"]
    if not low <= value <= high:
        return [f"{key} = {value} is outside {low}–{high}"]
    return []


def check_style_guide(path: Path) -> list[str]:
    data = front_matter(path)
    problems = number(data, "words_per_minute", 90, 220)
    problems += number(data, "phrase_words_target", 4, 30)
    problems += number(data, "phrase_words_max", 6, 45)
    target, most = data.get("phrase_words_target"), data.get("phrase_words_max")
    if isinstance(target, int | float) and isinstance(most, int | float) and most < target:
        problems.append("phrase_words_max is below phrase_words_target")
    return problems


def check_visual_style(path: Path) -> list[str]:
    data = front_matter(path)
    problems = []
    if data.get("aspect_ratio") not in ASPECT_RATIOS:
        problems.append(f"aspect_ratio must be one of {', '.join(ASPECT_RATIOS)}")
    anchor = data.get("anchor")
    if not isinstance(anchor, str) or not 8 <= len(anchor.split()) <= 40:
        problems.append("anchor must be one sentence of 8–40 words, appended to every image prompt")
    if not isinstance(data.get("avoid", ""), str):
        problems.append("avoid must be a string")
    return problems


def check_toml(path: Path) -> list[str]:
    try:
        tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as err:
        return [f"not valid TOML: {err}"]
    return []


def check_edit_preset(path: Path) -> list[str]:
    from ytflow.timeline import check_preset_file

    return check_preset_file(path)


def check_voice_file(path: Path) -> list[str]:
    from ytflow.voiceover import check_voice

    return check_voice(front_matter(path))


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    "style-guide.md": check_style_guide,
    "visual-style.md": check_visual_style,
    "voice.md": check_voice_file,
    "edit-preset.toml": check_edit_preset,
}


def check_kit(kit_dir: Path, files: tuple[str, ...] = ()) -> dict[str, list[str]]:
    """Problems per kit file (only the named files, or all of them)."""
    report: dict[str, list[str]] = {}
    for name in files or tuple(KIT_TEMPLATES):
        path = kit_dir / name
        if not path.is_file():
            report[name] = ["missing"]
            continue
        problems = [f"still has a {TODO_MARK} placeholder"] if TODO_MARK in path.read_text(errors="replace") else []
        try:
            problems += CHECKS.get(name, lambda _: [])(path)
        except KitError as err:
            problems.append(str(err).removeprefix(f"{name}: "))
        report[name] = problems
    return report
