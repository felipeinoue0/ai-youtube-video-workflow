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


@dataclass
class ImportPlan:
    pairs: list[tuple[Path, Path, str]] = field(default_factory=list)  # (download, target, how it was paired)
    unmatched: list[Path] = field(default_factory=list)  # downloads left without a name
    missing: list[str] = field(default_factory=list)  # names still without an image after the plan
    problems: list[str] = field(default_factory=list)
    in_place: bool = False  # the downloads are already in images/: rename rather than copy


def named_after(stem: str, name: str) -> bool:
    """Google Flow names a download after its prompt's first line plus a hash: <name>_<hash>."""
    return stem == name or stem.startswith(f"{name}_")


def import_plan(
    source: Path, directory: Path, expected: list[str], explicit: dict[str, str] | None = None
) -> ImportPlan:
    """Pair downloads with the missing image names: explicit pairs, then by name, then by download order.

    Download order is used only when every remaining download has its own time; files copied
    out together share one, and pairing them by order would be a guess.
    """
    in_place = source.resolve() == directory.resolve()
    present = {p.stem for p in image_files(directory) if p.stem in expected}
    missing = [name for name in expected if name not in present]
    downloads = [p for p in image_files(source) if not (in_place and p.stem in expected)]
    plan = ImportPlan(in_place=in_place)
    taken_files: set[Path] = set()
    taken_names: set[str] = set()

    def take(download: Path, name: str, how: str) -> None:
        plan.pairs.append((download, directory / f"{name}{download.suffix.lower()}", how))
        taken_files.add(download)
        taken_names.add(name)

    by_file = {p.name: p for p in downloads}
    for file_name, name in (explicit or {}).items():
        download = by_file.get(file_name)
        if download is None:
            plan.problems.append(f"--pair: no image {file_name!r} to import")
        elif name not in expected:
            plan.problems.append(f"--pair: {name!r} is not an image name of this video")
        elif name not in missing:
            plan.problems.append(f"--pair: {name} already has its image")
        elif name in taken_names or download in taken_files:
            plan.problems.append(f"--pair: {file_name} or {name} is paired twice")
        else:
            take(download, name, "pair")

    for download in downloads:
        if download in taken_files:
            continue
        names = [n for n in missing if n not in taken_names and named_after(download.stem, n)]
        if names:
            take(download, max(names, key=len), "name")

    rest = [d for d in downloads if d not in taken_files]
    names_left = [n for n in missing if n not in taken_names]
    times = [d.stat().st_mtime_ns for d in rest]
    if rest and names_left and len(set(times)) == len(times):
        rest.sort(key=lambda d: (d.stat().st_mtime_ns, d.name))
        for download, name in zip(rest, names_left, strict=False):
            take(download, name, "order")
        rest = [d for d in rest if d not in taken_files]
    plan.unmatched = sorted(rest)
    plan.missing = [n for n in missing if n not in taken_names]
    plan.pairs.sort(key=lambda pair: expected.index(pair[1].stem))
    return plan


def apply_plan(plan: ImportPlan) -> None:
    for download, target, _ in plan.pairs:
        if plan.in_place:
            download.rename(target)
        else:
            shutil.copy2(download, target)
