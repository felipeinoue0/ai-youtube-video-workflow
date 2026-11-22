"""The images a creator brings back from Google Flow, matched to the prompt names."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ytflow.media import MediaError, image_size

SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
ASPECT_TOLERANCE = 0.02


@dataclass
class ImageReport:
    expected: int
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)  # file names that match no prompt
    duplicates: list[str] = field(default_factory=list)  # one name saved in several formats
    wrong_aspect: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    smallest: tuple[int, int] | None = None

    @property
    def ok(self) -> bool:
        return not (self.missing or self.extra or self.duplicates or self.wrong_aspect or self.unreadable)


def image_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)


def ratio(aspect: str) -> float:
    width, height = aspect.split(":")
    return int(width) / int(height)


def check(directory: Path, expected: list[str], aspect: str, probe: bool = True) -> ImageReport:
    report = ImageReport(expected=len(expected))
    by_stem: dict[str, list[Path]] = {}
    for path in image_files(directory):
        by_stem.setdefault(path.stem, []).append(path)
    wanted = set(expected)
    for name in expected:
        if name in by_stem:
            report.present.append(name)
        else:
            report.missing.append(name)
    for stem, paths in sorted(by_stem.items()):
        if stem not in wanted:
            report.extra.extend(p.name for p in paths)
        elif len(paths) > 1:
            report.duplicates.append(", ".join(p.name for p in paths))
    if not probe:
        return report
    target = ratio(aspect)
    for name in report.present:
        path = by_stem[name][0]
        try:
            width, height = image_size(path)
        except MediaError:
            report.unreadable.append(path.name)
            continue
        if abs(width / height - target) / target > ASPECT_TOLERANCE:
            report.wrong_aspect.append(f"{path.name} is {width}x{height}, not {aspect}")
        if report.smallest is None or width * height < report.smallest[0] * report.smallest[1]:
            report.smallest = (width, height)
    return report


def suggestion(extra: str, missing: list[str]) -> str | None:
    """A missing name with the same id as an extra file: probably renamed by a script change."""
    prefix = extra.split("_", 1)[0] + "_"
    return next((name for name in missing if name.startswith(prefix)), None)


def import_plan(source: Path, directory: Path, expected: list[str]) -> list[tuple[Path, Path]]:
    """Downloads (oldest first) paired with the missing names, in timeline order."""
    present = {p.stem for p in image_files(directory)}
    missing = [name for name in expected if name not in present]
    downloads = sorted(image_files(source), key=lambda p: (p.stat().st_mtime, p.name))
    return [(src, directory / f"{name}{src.suffix.lower()}") for src, name in zip(downloads, missing, strict=False)]


def apply_plan(plan: list[tuple[Path, Path]]) -> None:
    for src, dest in plan:
        shutil.copy2(src, dest)
