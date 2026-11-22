"""The skills are the product's interface: keep the two copies identical and every command they name real."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from ytflow.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"
MIRROR = ROOT / ".claude" / "skills"
SKILL_FILES = sorted(SKILLS.glob("*/SKILL.md"))


def command_paths(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    paths = {prefix}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                paths |= command_paths(sub, (*prefix, name))
    return paths


def test_there_are_skills() -> None:
    assert SKILL_FILES, "no skills found"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_is_mirrored_byte_for_byte(skill: Path) -> None:
    mirror = MIRROR / skill.parent.name / "SKILL.md"
    assert mirror.is_file(), f"copy {skill} to {mirror}"
    assert mirror.read_bytes() == skill.read_bytes(), f"{mirror} differs from {skill}: copy it again"


def test_no_mirror_without_source() -> None:
    extra = {p.parent.name for p in MIRROR.glob("*/SKILL.md")} - {p.parent.name for p in SKILL_FILES}
    assert not extra, f"skills only in .claude/skills: {extra}"


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_frontmatter_names_the_directory(skill: Path) -> None:
    text = skill.read_text()
    assert text.startswith("---\n")
    front = text.split("---\n")[1]
    assert re.search(rf"^name: {re.escape(skill.parent.name)}$", front, re.M)
    assert re.search(r"^description: \S", front, re.M)


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_ytflow_command_in_a_skill_exists(skill: Path) -> None:
    known = command_paths(build_parser())
    leaves = {p for p in known if not any(q[: len(p)] == p and q != p for q in known)}
    for match in re.finditer(r"\bytflow((?: [a-z][a-z-]*)+)", skill.read_text()):
        words = tuple(match.group(1).split())
        # the longest known command path the words start with must be a runnable command
        prefix = max((p for p in known if words[: len(p)] == p), key=len)
        assert prefix in leaves, f"{skill.parent.name}: 'ytflow{match.group(1)}' is not a ytflow command"
