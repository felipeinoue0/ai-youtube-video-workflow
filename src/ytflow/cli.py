"""Command-line entry point. Commands are added one workflow step at a time."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ytflow import __version__
from ytflow.branding import check_branding
from ytflow.media import MediaError
from ytflow.workspace import (
    VERSION_RE,
    Workspace,
    WorkspaceError,
    channel_status,
    latest_version,
    new_version,
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
    step_dir = workspace(args).channel(args.channel) / "branding"
    if args.step_version:
        version_dir = step_dir / args.step_version
        if not VERSION_RE.match(args.step_version) or not version_dir.is_dir():
            raise WorkspaceError(f"no branding version {args.step_version!r}")
    else:
        version_dir = latest_version(step_dir)
        if version_dir is None:
            raise WorkspaceError(f"no branding version yet — run: ytflow version new {step_dir}")
    problems = check_branding(version_dir)
    for problem in problems:
        print(f"- {problem}")
    print(f"branding {version_dir.name}: " + (f"{len(problems)} problem(s)" if problems else "ok"))
    return 1 if problems else 0


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
    except (WorkspaceError, MediaError) as err:
        print(f"ytflow: error: {err}", file=sys.stderr)
        return 1
