"""Command-line entry point. Commands are added one workflow step at a time."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ytflow import __version__
from ytflow.align import COMPILED as TIMING_COMPILED
from ytflow.align import DEFAULT_MODEL, METHODS, MIN_MATCHED, AlignError, choose_method, lay_out, load_words, transcribe
from ytflow.align import align as align_narration
from ytflow.align import write as write_timing
from ytflow.branding import check_branding
from ytflow.images import apply_plan, image_files, import_plan
from ytflow.images import check as check_images
from ytflow.images import suggestion as image_suggestion
from ytflow.kdenlive import export as export_kdenlive
from ytflow.kit import KitError, check_kit, front_matter
from ytflow.media import MediaError, duration
from ytflow.preview import FILE as PREVIEW_FILE
from ytflow.preview import render as render_preview
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
from ytflow.subtitles import write as write_subtitles
from ytflow.timeline import COMPILED as TIMELINE_COMPILED
from ytflow.timeline import TimelineError, load_preset
from ytflow.timeline import build as build_timeline
from ytflow.timeline import write as write_timeline
from ytflow.voiceover import CHAPTERS_DIR, GENERATION_CHARACTERS, check_audio, duration_warning, same_export
from ytflow.voiceover import COMPILED as VOICEOVER_COMPILED
from ytflow.voiceover import TEXT as VOICEOVER_TEXT
from ytflow.voiceover import build as build_narration
from ytflow.voiceover import compiled as compiled_voiceover
from ytflow.voiceover import write as write_voiceover
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

    voiceover = sub.add_parser("voiceover", help="narration text for ElevenLabs").add_subparsers(
        dest="action", required=True
    )
    p = voiceover.add_parser("text", help="export the narration text with the kit's voice settings and spellings")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--script", dest="script_version", help="script version (default: latest)")
    p.set_defaults(func=cmd_voiceover_text)

    audio = sub.add_parser("audio", help="narration audio from ElevenLabs").add_subparsers(dest="action", required=True)
    p = audio.add_parser("check", help="check audio/ against the voiceover export: files, layout, durations")
    p.add_argument("channel")
    p.add_argument("video")
    p.set_defaults(func=cmd_audio_check)

    p = sub.add_parser("align", help="replace the script's estimated timings with where each phrase is spoken")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument(
        "--method",
        choices=METHODS,
        default="auto",
        help="default: words if --words, else whisper if installed, else chapters",
    )
    p.add_argument("--words", type=Path, help="word timestamps from another tool: [{word, start, end}, ...]")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"faster-whisper model (default: {DEFAULT_MODEL})")
    p.add_argument("--language", help="narration language for faster-whisper, e.g. en (default: detect)")
    p.set_defaults(func=cmd_align)

    timeline = sub.add_parser("timeline", help="the edit").add_subparsers(dest="action", required=True)
    p = timeline.add_parser("build", help="build timeline.json and subtitles.ass from the timing, images and preset")
    p.add_argument("channel")
    p.add_argument("video")
    p.set_defaults(func=cmd_timeline_build)
    p = timeline.add_parser("preview", help="render a draft of the timeline with ffmpeg (preview.mp4)")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--version", dest="step_version", help="timeline version (default: latest)")
    p.add_argument("--scale", type=float, default=0.5, help="output size as a share of the video size (default 0.5)")
    p.set_defaults(func=cmd_timeline_preview)

    export = sub.add_parser("export", help="write the timeline as an editor project").add_subparsers(
        dest="action", required=True
    )
    p = export.add_parser("kdenlive", help="write <video>.kdenlive next to timeline.json")
    p.add_argument("channel")
    p.add_argument("video")
    p.add_argument("--version", dest="step_version", help="timeline version (default: latest)")
    p.set_defaults(func=cmd_export_kdenlive)

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


def cmd_voiceover_text(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit, voice = ready_kit_file(ws, args.channel, args.video, "voice.md")
    script_dir, script = built_script(ws, args.channel, args.video, args.script_version)
    narration = build_narration(script, voice)
    data = compiled_voiceover(narration, script, script_dir.name, kit.name, voice)
    step_dir = ws.video(args.channel, args.video) / "voiceover"
    latest = latest_version(step_dir)
    if latest is not None and same_export(latest, narration, data):
        print(latest / VOICEOVER_TEXT)
        print(f"voiceover {latest.name} already holds this export — nothing new written", file=sys.stderr)
        return 0
    version = new_version(step_dir)
    write_voiceover(version, narration, data)
    print(version / VOICEOVER_TEXT)
    print(
        f"voiceover {version.name}: {data['characters']} characters, {len(narration.chapters)} chapter(s), "
        f"about {clock(script['duration'])} from script {script_dir.name}",
        file=sys.stderr,
    )
    for word, count in narration.uses.items():
        if count == 0:
            print(f"warning: pronunciation {word!r} never appears in this script", file=sys.stderr)
    if data["characters"] > GENERATION_CHARACTERS:
        print(
            f"note: over {GENERATION_CHARACTERS} characters — generate chapter by chapter from "
            f"{version / CHAPTERS_DIR}",
            file=sys.stderr,
        )
    return 0


def cmd_audio_check(args: argparse.Namespace) -> int:
    ws = workspace(args)
    video_dir = ws.video(args.channel, args.video)
    voiceover_dir, export = voiceover_export(ws, args.channel, args.video)
    chapters = {c["file"]: c for c in export["chapters"]}
    audio_dir = video_dir / "audio"
    report = check_audio(audio_dir, list(chapters))
    for problem in report.problems:
        print(f"- {problem}")
    for name in report.missing:
        print(f"- missing: {name}.mp3 (text: {voiceover_dir / CHAPTERS_DIR / name}.txt)")
    for extra in report.extra:
        print(f"warning: {extra.name} is not narration.<ext> or a chapter name — ignored")
    if report.layout == "none":
        print(f"audio: none in {audio_dir} — save narration.mp3, or one file per chapter named like chapters/")
        return 1
    total = 0.0
    for file in report.files:
        seconds = duration(file)
        total += seconds
        print(f"  {file.name:<40} {clock(seconds)}")
        chapter = chapters.get(file.stem)
        if chapter and (warning := duration_warning(seconds, chapter["estimated_duration"])):
            print(f"warning: {file.name}: {warning}")
    if report.layout == "single" or not report.missing:
        if warning := duration_warning(total, export["estimated_duration"]):
            print(f"warning: {warning}")
    stale = latest_version(video_dir / "script")
    if stale is not None and stale.name != export["script_version"]:
        print(f"warning: exported from script {export['script_version']}, but {stale.name} exists")
    bad = bool(report.problems or report.missing)
    layout = "one file" if report.layout == "single" else f"{len(report.files)}/{len(chapters)} chapter files"
    print(f"audio: {layout}, {clock(total)} — {'fix the problems above' if bad else 'ok'}")
    return 1 if bad else 0


def voiceover_export(ws: Workspace, channel: str, video: str) -> tuple[Path, dict]:
    directory = version_dir(ws.video(channel, video) / "voiceover", None)
    path = directory / VOICEOVER_COMPILED
    if not path.is_file():
        raise WorkspaceError(f"no {VOICEOVER_COMPILED} in {directory} — run: ytflow voiceover text {channel} {video}")
    return directory, json.loads(path.read_text())


def cmd_align(args: argparse.Namespace) -> int:
    ws = workspace(args)
    video_dir = ws.video(args.channel, args.video)
    voiceover_dir, export = voiceover_export(ws, args.channel, args.video)
    script_dir, script = built_script(ws, args.channel, args.video, export["script_version"])
    chapter_files = [c["file"] for c in export["chapters"]]
    report = check_audio(video_dir / "audio", chapter_files)
    if report.layout == "none" or report.problems or report.missing:
        raise WorkspaceError(
            f"the narration audio is not complete — run: ytflow audio check {args.channel} {args.video}"
        )
    method = choose_method(args.method, report.layout, args.words)
    named = [(f"audio/{f.name}", duration(f)) for f in report.files]
    parts = lay_out(named, export["chapter_break"] if report.layout == "chapters" else 0.0)
    index_of = {c["file"]: c["index"] for c in export["chapters"]}
    chapter_of_part = [index_of.get(f.stem) for f in report.files]

    def heard() -> list:
        if method == "words":
            return load_words(args.words)
        words = []
        for file, part in zip(report.files, parts, strict=True):
            print(f"transcribing {file.name} with faster-whisper ({args.model})…", file=sys.stderr)
            for word in transcribe(file, args.model, args.language):
                word.start += part.start
                word.end += part.start
                words.append(word)
        return words

    timing = align_narration(script, parts, chapter_of_part, method, heard)
    if timing.matched is not None and timing.matched < MIN_MATCHED:
        raise AlignError(
            f"only {timing.matched:.0%} of the script's words were heard in the audio — it may not be this script "
            f"(voiceover {voiceover_dir.name}, script {script_dir.name}); listen to it, or regenerate it"
        )
    version = new_version(video_dir / "timing")
    write_timing(version, timing, script_dir.name, voiceover_dir.name)
    print(version / TIMING_COMPILED)
    heard_note = f", {timing.matched:.0%} of words heard" if timing.matched is not None else ""
    print(f"timing {version.name}: {method}{heard_note}, {len(timing.phrases)} phrases, {clock(timing.duration)}")
    for chapter in timing.chapters:
        print(f"  {clock(chapter['start'])} {chapter['title']}")
    for name in timing.interpolated:
        print(f"warning: {name}: none of its words were heard; its time is estimated from its neighbours")
    if method == "chapters":
        print("note: character-count timing is approximate within a chapter — check the subtitles in subtitles.srt")
    return 0


def cmd_timeline_build(args: argparse.Namespace) -> int:
    ws = workspace(args)
    kit, _ = ready_kit_file(ws, args.channel, args.video, "edit-preset.toml")
    preset = load_preset(kit / "edit-preset.toml")
    video_dir = ws.video(args.channel, args.video)
    timing_dir = version_dir(video_dir / "timing", None)
    if not (timing_dir / TIMING_COMPILED).is_file():
        raise WorkspaceError(f"no {TIMING_COMPILED} in {timing_dir} — run: ytflow align {args.channel} {args.video}")
    timing = json.loads((timing_dir / TIMING_COMPILED).read_text())
    images: dict[str, str] = {}
    for path in image_files(video_dir / "images"):
        if path.stem in images:
            raise WorkspaceError(f"{path.stem} is saved twice in images/ — run: ytflow images check")
        images[path.stem] = f"images/{path.name}"
    sources = {
        "script_version": timing["script_version"],
        "voiceover_version": timing["voiceover_version"],
        "timing_version": timing_dir.name,
        "kit_version": kit.name,
    }
    result = build_timeline(timing, images, preset, sources)
    version = new_version(video_dir / "timeline")
    path = write_timeline(version, result)
    write_subtitles(version, result.data)
    print(path)
    data = result.data
    kinds: dict[str, int] = {}
    for transition in data["transitions"]:
        kinds[transition["type"]] = kinds.get(transition["type"], 0) + 1
    mix = ", ".join(f"{n} {kind}" for kind, n in sorted(kinds.items(), key=lambda item: -item[1]))
    print(
        f"timeline {version.name}: {len(data['clips'])} clips, {clock(data['video']['duration'])}, "
        f"{len(data['chapters'])} chapter titles; transitions: {mix or 'none'}"
    )
    for warning in result.warnings:
        print(f"warning: {warning}")
    latest_script = latest_version(video_dir / "script")
    if latest_script is not None and latest_script.name != timing["script_version"]:
        print(f"warning: timed from script {timing['script_version']}, but {latest_script.name} exists")
    return 0


def built_timeline(ws: Workspace, channel: str, video: str, version: str | None) -> tuple[Path, dict]:
    video_dir = ws.video(channel, video)
    if version is None and latest_version(video_dir / "timeline") is None:
        raise WorkspaceError(f"no timeline yet — run: ytflow timeline build {channel} {video}")
    directory = version_dir(video_dir / "timeline", version)
    path = directory / TIMELINE_COMPILED
    if not path.is_file():
        raise WorkspaceError(f"no {TIMELINE_COMPILED} in {directory} — run: ytflow timeline build {channel} {video}")
    return directory, json.loads(path.read_text())


def cmd_export_kdenlive(args: argparse.Namespace) -> int:
    ws = workspace(args)
    version, data = built_timeline(ws, args.channel, args.video, args.step_version)
    subtitles = version / "subtitles.ass"
    if not subtitles.is_file():
        raise WorkspaceError(f"no subtitles.ass in {version} — run: ytflow timeline build {args.channel} {args.video}")
    project = export_kdenlive(data, version / f"{args.video}.kdenlive", ws.video(args.channel, args.video), subtitles)
    print(project)
    return 0


def cmd_timeline_preview(args: argparse.Namespace) -> int:
    ws = workspace(args)
    video_dir = ws.video(args.channel, args.video)
    if not 0.1 <= args.scale <= 1:
        raise WorkspaceError("--scale must be between 0.1 and 1")
    version, data = built_timeline(ws, args.channel, args.video, args.step_version)
    output = version / PREVIEW_FILE
    print(f"rendering {clock(data['video']['duration'])} at {args.scale:g}× size…", file=sys.stderr)
    render_preview(data, video_dir, version / "subtitles.ass", output, args.scale)
    print(output)
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
    except (WorkspaceError, MediaError, KitError, AlignError, TimelineError) as err:
        print(f"ytflow: error: {err}", file=sys.stderr)
        return 1
