"""Command-line entry point. Commands are added one workflow step at a time."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ytflow import __version__
from ytflow.branding import check_branding
from ytflow.images import apply_plan, import_plan
from ytflow.images import check as check_images
from ytflow.images import suggestion as image_suggestion
from ytflow.kit import KitError, check_kit, front_matter
from ytflow.media import MediaError
from ytflow.prompts import COMPILED as PROMPTS_COMPILED
from ytflow.prompts import SOURCE as PROMPTS_SOURCE
from ytflow.prompts import TEXT as PROMPTS_TEXT
from ytflow.prompts import build as build_prompts
from ytflow.prompts import init_text as prompts_init_text
from ytflow.prompts import parse as parse_prompts
from ytflow.prompts import write as write_prompts
from ytflow.prompts import written_scenes
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

    prompts = sub.add_parser("prompts", help="image-prompt step").add_subparsers(dest="action", required=True)
    p = prompts.add_parser("init", help="start a prompts version with one scene per phrase of the script")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--script", dest="script_version", help="script version (default: latest)")
    p.set_defaults(func=cmd_prompts_init)
    p = prompts.add_parser("build", help="compose scenes with the kit's anchor into prompts.txt and prompts.json")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--version", dest="step_version", help="prompts version (default: latest)")
    p.set_defaults(func=cmd_prompts_build)

    images = sub.add_parser("images", help="images from Google Flow").add_subparsers(dest="action", required=True)
    p = images.add_parser("check", help="match images/ against the prompt names: missing, extra, aspect ratio")
    p.add_argument("channel")
    p.add_argument("video")
    p.set_defaults(func=cmd_images_check)
    p = images.add_parser("import", help="copy downloads (oldest first) to the missing image names")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--from", dest="source", type=Path, required=True, help="folder with the downloaded images")
    p.add_argument("--apply", action="store_true", help="copy the files (default: only show the plan)")
    p.set_defaults(func=cmd_images_import)

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


def ready_kit_file(ws: Workspace, channel: str, video: str, name: str) -> tuple[Path, dict]:
    """The video's kit and the front matter of one kit file, which must pass the kit check."""
    kit = ws.video_kit(channel, video)
    problems = check_kit(kit, (name,))[name]
    if problems:
        raise WorkspaceError(
            f"{name} in kit {kit.name} is not ready ({'; '.join(problems)}) — run: ytflow kit check {channel} {video}"
        )
    return kit, front_matter(kit / name)


def built_script(ws: Workspace, channel: str, video: str, version: str | None) -> tuple[Path, dict]:
    directory = version_dir(ws.video(channel, video) / "script", version)
    path = directory / SCRIPT_COMPILED
    if not path.is_file():
        raise WorkspaceError(f"no {SCRIPT_COMPILED} in {directory} — run: ytflow script build {channel} {video}")
    return directory, json.loads(path.read_text())


def built_prompts(ws: Workspace, channel: str, video: str) -> list[str]:
    directory = version_dir(ws.video(channel, video) / "prompts", None)
    path = directory / PROMPTS_COMPILED
    if not path.is_file():
        raise WorkspaceError(f"no {PROMPTS_COMPILED} in {directory} — run: ytflow prompts build {channel} {video}")
    return [p["name"] for p in json.loads(path.read_text())["prompts"]]


def cmd_prompts_init(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit, _ = ready_kit_file(ws, args.channel, args.video, "visual-style.md")
    script_dir, script = built_script(ws, args.channel, args.video, args.script_version)
    step_dir = ws.video(args.channel, args.video) / "prompts"
    previous = latest_version(step_dir)
    carried = {}
    if previous is not None and (previous / PROMPTS_SOURCE).is_file():
        carried = written_scenes((previous / PROMPTS_SOURCE).read_text())
    text = prompts_init_text(script, script_dir.name, kit.name, carried)
    reused = sum((p["name"], p["text"]) in carried for p in script["phrases"])
    target = new_version(step_dir)
    (target / PROMPTS_SOURCE).write_text(text)
    print(target / PROMPTS_SOURCE)
    note = f", {reused} scene(s) carried over from {previous.name}" if reused else ""
    print(f"{len(script['phrases'])} scene(s) to write from script {script_dir.name}{note}", file=sys.stderr)
    return 0


def cmd_prompts_build(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit, visual = ready_kit_file(ws, args.channel, args.video, "visual-style.md")
    version = version_dir(ws.video(args.channel, args.video) / "prompts", args.step_version)
    source = version / PROMPTS_SOURCE
    if not source.is_file():
        raise WorkspaceError(f"no {PROMPTS_SOURCE} in {version} — run: ytflow prompts init {args.channel} {args.video}")
    text = source.read_text()
    script_version, _, _ = parse_prompts(text)
    script_dir, script = built_script(ws, args.channel, args.video, script_version)
    prompts, problems = build_prompts(text, script, visual["anchor"], visual.get("avoid", ""))
    if prompts is None:
        for problem in problems:
            print(f"- {problem}")
        print(f"prompts {version.name}: {len(problems)} problem(s); {PROMPTS_COMPILED} not written")
        return 1
    write_prompts(version, prompts, script_dir.name, kit.name)
    latest_script = latest_version(script_dir.parent)
    if latest_script is not None and latest_script != script_dir:
        print(f"warning: made from script {script_dir.name}, but {latest_script.name} exists — run prompts init again")
    print(f"prompts {version.name}: ok — {len(prompts)} prompts in {version / PROMPTS_TEXT}")
    return 0


def cmd_images_check(args: argparse.Namespace) -> int:
    ws = workspace(args)
    _, visual = ready_kit_file(ws, args.channel, args.video, "visual-style.md")
    expected = built_prompts(ws, args.channel, args.video)
    report = check_images(ws.video(args.channel, args.video) / "images", expected, visual["aspect_ratio"])
    for name in report.missing:
        print(f"missing: {name}")
    for name in report.extra:
        hint = image_suggestion(name, report.missing)
        print(f"extra: {name}" + (f" (rename to {hint}{Path(name).suffix}?)" if hint else " (matches no prompt)"))
    for item in report.duplicates:
        print(f"duplicate: {item} (keep one)")
    for item in report.wrong_aspect:
        print(f"wrong aspect: {item}")
    for item in report.unreadable:
        print(f"unreadable: {item}")
    size = f", smallest {report.smallest[0]}x{report.smallest[1]}" if report.smallest else ""
    status = "ok" if report.ok else "not ready"
    print(f"images: {len(report.present)}/{report.expected} present{size} — {status}")
    return 0 if report.ok else 1


def cmd_images_import(args: argparse.Namespace) -> int:
    ws = workspace(args)
    images_dir = ws.video(args.channel, args.video) / "images"
    source = args.source.resolve()
    if not source.is_dir():
        raise WorkspaceError(f"{args.source} is not a folder")
    if source == images_dir.resolve():
        raise WorkspaceError("--from must be the downloads folder, not the video's images/ folder")
    plan = import_plan(source, images_dir, built_prompts(ws, args.channel, args.video))
    if not plan:
        print("nothing to import: no missing images, or no image files in the folder")
        return 0
    for src, dest in plan:
        print(f"{src.name} -> {dest.name}")
    if args.apply:
        apply_plan(plan)
        print(f"copied {len(plan)} file(s) into {images_dir}")
    else:
        print(f"{len(plan)} file(s) would be copied, oldest download first — check the pairs, then add --apply")
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
