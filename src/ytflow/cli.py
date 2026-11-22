"""Command-line entry point. Commands are added one workflow step at a time."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ytflow import __version__
from ytflow.branding import check_branding
from ytflow.kit import KitError, check_kit, front_matter
from ytflow.media import MediaError
from ytflow.references import as_dict, measure, recommend, reference_files
from ytflow.script import COMPILED as SCRIPT_COMPILED
from ytflow.script import SOURCE as SCRIPT_SOURCE
from ytflow.script import build as build_script
from ytflow.script import youtube_chapter_warnings
from ytflow.workspace import (
    KIT_TEMPLATES,
    Workspace,
    WorkspaceError,
    channel_status,
    latest_version,
    new_version,
    version_dir,
    video_status,
)

ROOT_ENV = "YTFLOW_ROOT"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytflow",
        description="Guide a YouTube video from channel branding to publish.",
    )
    parser.add_argument("--version", action="version", version=f"ytflow {__version__}")
    parser.add_argument(
        "--root",
        type=Path,
        help=f"workspace root holding channels/ (default: ${ROOT_ENV}, else the current directory)",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    channel = sub.add_parser("channel", help="manage channels").add_subparsers(dest="action", required=True)
    p = channel.add_parser("new", help="create a channel with kit v1")
    p.add_argument("channel")
    p.set_defaults(func=cmd_channel_new)

    kit = sub.add_parser("kit", help="manage the channel kit").add_subparsers(dest="action", required=True)
    p = kit.add_parser("new", help="start the next kit version from the latest one")
    p.add_argument("channel")
    p.set_defaults(func=cmd_kit_new)
    p = kit.add_parser("edit", help="print a kit version safe to write to (starts a new one if a video uses it)")
    p.add_argument("channel")
    p.add_argument("video", nargs="?", help="edit the kit this video uses instead of the latest")
    p.add_argument("--file", dest="files", action="append", default=[], help="kit file to write (repeatable)")
    p.set_defaults(func=cmd_kit_edit)
    p = kit.add_parser("check", help="check the kit's files: placeholders left and front-matter values")
    p.add_argument("channel")
    p.add_argument("video", nargs="?", help="check the kit this video uses instead of the latest")
    p.add_argument("--file", dest="files", action="append", default=[], help="kit file to check (repeatable)")
    p.set_defaults(func=cmd_kit_check)
    p = kit.add_parser("path", help="print the kit directory a video uses (or the channel's latest)")
    p.add_argument("channel")
    p.add_argument("video", nargs="?")
    p.set_defaults(func=cmd_kit_path)

    video = sub.add_parser("video", help="manage videos").add_subparsers(dest="action", required=True)
    p = video.add_parser("new", help="create a video that uses the latest (or a chosen) kit version")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--kit", help="kit version, e.g. v2 (default: latest)")
    p.set_defaults(func=cmd_video_new)

    version = sub.add_parser("version", help="manage step versions").add_subparsers(dest="action", required=True)
    p = version.add_parser("new", help="create the next version directory of a step and print its path")
    p.add_argument("step_dir", type=Path, help="the step directory, e.g. channels/c/videos/v/script")
    p.add_argument("--copy", action="store_true", help="start from a copy of the latest version")
    p.set_defaults(func=cmd_version_new)
    p = version.add_parser("latest", help="print the latest version directory of a step")
    p.add_argument("step_dir", type=Path)
    p.set_defaults(func=cmd_version_latest)

    branding = sub.add_parser("branding", help="branding step").add_subparsers(dest="action", required=True)
    p = branding.add_parser("check", help="check identity.toml, logo and banner against YouTube's limits")
    p.add_argument("channel")
    p.add_argument("--version", dest="step_version", help="branding version, e.g. v2 (default: latest)")
    p.set_defaults(func=cmd_branding_check)

    refs = sub.add_parser("references", help="reference transcripts").add_subparsers(dest="action", required=True)
    p = refs.add_parser("stats", help="measure the transcripts in channels/<channel>/references/")
    p.add_argument("channel")
    p.add_argument("--json", action="store_true", help="print JSON instead of a report")
    p.set_defaults(func=cmd_references_stats)

    script = sub.add_parser("script", help="script step").add_subparsers(dest="action", required=True)
    p = script.add_parser("build", help="validate script.md against the kit and write script.json")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--version", dest="step_version", help="script version, e.g. v2 (default: latest)")
    p.set_defaults(func=cmd_script_build)

    p = sub.add_parser("status", help="show where a channel or video is and what to do next")
    p.add_argument("channel")
    p.add_argument("video", nargs="?")
    p.set_defaults(func=cmd_status)
    return parser


def workspace(args: argparse.Namespace) -> Workspace:
    root = args.root or os.environ.get(ROOT_ENV) or "."
    return Workspace(Path(root).resolve())


def step_path(args: argparse.Namespace) -> Path:
    """A step directory is relative to the workspace root unless absolute."""
    path = args.step_dir if args.step_dir.is_absolute() else workspace(args).root / args.step_dir
    channels = workspace(args).channels.resolve()
    resolved = path.resolve()
    if channels not in resolved.parents:
        raise WorkspaceError(f"{args.step_dir} is not inside {channels}")
    return resolved


def cmd_channel_new(args: argparse.Namespace) -> int:
    ws = workspace(args)
    path = ws.create_channel(args.channel)
    print(path)
    print(f"next: create the branding (skill: branding), then fill the kit in {path / 'kit' / 'v1'}", file=sys.stderr)
    return 0


def cmd_kit_new(args: argparse.Namespace) -> int:
    print(workspace(args).create_kit_version(args.channel))
    return 0


def cmd_kit_edit(args: argparse.Namespace) -> int:
    path, users = workspace(args).editable_kit(args.channel, args.video, tuple(args.files))
    if users:
        print(
            f"that kit is used by {', '.join(users)}, which keep it; started kit {path.name} for later videos",
            file=sys.stderr,
        )
    print(path)
    return 0


def cmd_kit_check(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit = ws.video_kit(args.channel, args.video) if args.video else ws.kit_dir(ws.channel(args.channel), None)
    for name in args.files:
        if name not in KIT_TEMPLATES:
            raise WorkspaceError(f"unknown kit file {name!r} (kit files: {', '.join(KIT_TEMPLATES)})")
    report = check_kit(kit, tuple(args.files))
    for name, problems in report.items():
        print(f"{name}: {'ok' if not problems else ''}".rstrip())
        for problem in problems:
            print(f"  - {problem}")
    bad = sum(1 for problems in report.values() if problems)
    print(f"kit {kit.name}: " + (f"{bad} file(s) with problems" if bad else "ok"))
    return 1 if bad else 0


def cmd_references_stats(args: argparse.Namespace) -> int:
    directory = workspace(args).channel(args.channel) / "references"
    files = reference_files(directory)
    if not files:
        raise WorkspaceError(f"no transcripts in {directory} — save them there as .txt, .srt or .vtt")
    stats = [measure(f) for f in files]
    targets = recommend(stats)
    if args.json:
        print(json.dumps({"transcripts": [as_dict(s) for s in stats], "recommended": targets}, indent=2))
        return 0
    for s in stats:
        pace = f"{s.words_per_minute:g} wpm over {s.duration_seconds:g}s" if s.words_per_minute else "no timing"
        print(f"{s.file} ({s.format}): {s.words} words, {s.sentences} sentences, {pace}")
        print(f"  sentence words: median {s.sentence_words_median:g}, p90 {s.sentence_words_p90:g}")
        print(
            f"  questions: {s.question_share:.0%} of sentences; 'you': {s.second_person_per_100_words:g} per 100 words"
        )
        print(f"  hook: {s.hook}")
    print("recommended front matter for style-guide.md:")
    for key, value in targets.items():
        print(f"  {key} = {value if value is not None else '(no timed transcript: choose, e.g. 150)'}")
    return 0


def cmd_kit_path(args: argparse.Namespace) -> int:
    ws = workspace(args)
    if args.video:
        print(ws.video_kit(args.channel, args.video))
    else:
        print(ws.kit_dir(ws.channel(args.channel), None))
    return 0


def cmd_video_new(args: argparse.Namespace) -> int:
    print(workspace(args).create_video(args.channel, args.video, args.kit))
    return 0


def cmd_version_new(args: argparse.Namespace) -> int:
    print(new_version(step_path(args), copy_latest=args.copy))
    return 0


def cmd_version_latest(args: argparse.Namespace) -> int:
    latest = latest_version(step_path(args))
    if latest is None:
        raise WorkspaceError(f"{args.step_dir} has no versions yet")
    print(latest)
    return 0


def cmd_branding_check(args: argparse.Namespace) -> int:
    version = version_dir(workspace(args).channel(args.channel) / "branding", args.step_version)
    problems = check_branding(version)
    for problem in problems:
        print(f"- {problem}")
    print(f"branding {version.name}: " + (f"{len(problems)} problem(s)" if problems else "ok"))
    return 1 if problems else 0


def clock(seconds: float) -> str:
    """YouTube timestamp: m:ss, or h:mm:ss from an hour."""
    total = int(seconds)
    h, m, s = total // 3600, total % 3600 // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cmd_script_build(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit = ws.video_kit(args.channel, args.video)
    kit_problems = check_kit(kit, ("style-guide.md",))["style-guide.md"]
    if kit_problems:
        raise WorkspaceError(
            f"style-guide.md in kit {kit.name} is not ready ({'; '.join(kit_problems)}) — "
            f"run: ytflow kit check {args.channel} {args.video}"
        )
    style = front_matter(kit / "style-guide.md")
    version = version_dir(ws.video(args.channel, args.video) / "script", args.step_version)
    source = version / SCRIPT_SOURCE
    if not source.is_file():
        raise WorkspaceError(f"no {SCRIPT_SOURCE} in {version}")
    script, problems = build_script(source.read_text(), style["words_per_minute"], style["phrase_words_max"])
    if script is None:
        for problem in problems:
            print(f"- {problem}")
        print(f"script {version.name}: {len(problems)} problem(s); {SCRIPT_COMPILED} not written")
        return 1
    (version / SCRIPT_COMPILED).write_text(script.to_json())
    print(f"{script.title}")
    for chapter in script.chapters:
        count = sum(1 for p in script.phrases if p.chapter == chapter.index)
        print(f"  {clock(chapter.start)} {chapter.title} ({count} phrase{'s' if count != 1 else ''})")
    target = style["phrase_words_target"]
    average = sum(p.words for p in script.phrases) / len(script.phrases)
    print(
        f"{len(script.phrases)} phrases, {average:.1f} words on average (kit target {target}), "
        f"about {clock(script.duration)} at {style['words_per_minute']} wpm"
    )
    for warning in youtube_chapter_warnings(script):
        print(f"warning: {warning}")
    print(f"script {version.name}: ok — wrote {version / SCRIPT_COMPILED}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ws = workspace(args)
    lines, next_action = channel_status(ws, args.channel)
    if args.video:
        video_lines, video_next = video_status(ws, args.channel, args.video)
        lines += video_lines
        next_action = next_action or video_next
    print("\n".join(lines))
    print(f"next: {next_action}" if next_action else "next: done — every step has an output")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (WorkspaceError, MediaError, KitError) as err:
        print(f"ytflow: error: {err}", file=sys.stderr)
        return 1
