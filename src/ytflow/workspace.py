"""The creator's workspace on disk: channels, the channel kit, videos and step versions.

Layout (under the workspace root, `channels/` is gitignored)::

    channels/<channel>/
      channel.toml                 # name; the kit version new videos start from is the latest
      references/                  # reference transcripts the creator drops in (input)
      branding/v<N>/               # branding step outputs
      kit/v<N>/                    # the channel kit, read by every video
      videos/<video>/
        video.toml                 # the kit version this video was made with
        images/  audio/            # files the creator brings back from Google Flow / ElevenLabs
        <step>/v<N>/               # versioned step outputs

A version directory is never overwritten: a new iteration is always `v<N+1>`.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

CHANNELS_DIR = "channels"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")

# A placeholder line in a kit template; the kit is complete when no file carries one.
TODO_MARK = "TODO(ytflow)"


class WorkspaceError(Exception):
    """A problem the creator can fix; the CLI prints it and exits non-zero."""


@dataclass(frozen=True)
class Step:
    name: str
    skill: str
    action: str
    kind: str = "versioned"  # "versioned" (<step>/v<N>/) or "input" (files the creator adds)


CHANNEL_STEPS = (
    Step("branding", "branding", "create the logo and banner in Canva and write the channel description and tags"),
)

VIDEO_STEPS = (
    Step("script", "script", "write the script from the kit's style guide"),
    Step("prompts", "image-prompts", "write one Google Flow prompt per phrase part"),
    Step(
        "images", "image-prompts", "generate the images in Google Flow and save them under their prompt names", "input"
    ),
    Step("voiceover", "voiceover", "export the narration text for ElevenLabs"),
    Step("audio", "voiceover", "generate the narration in ElevenLabs and save it in audio/", "input"),
    Step("timing", "edit", "align the narration audio to the script"),
    Step("timeline", "edit", "build timeline.json and export the Kdenlive project"),
    Step("publish", "publish", "write the title, description and tags"),
)

KIT_TEMPLATES: dict[str, str] = {
    "style-guide.md": f"""# Style guide

How this channel's scripts read. Filled by the style skill from the reference
transcripts in `references/`; every video's script follows it.

{TODO_MARK}: hook (first 15 seconds)
{TODO_MARK}: structure (chapters, how a chapter opens and closes)
{TODO_MARK}: pacing and phrase length
{TODO_MARK}: tone and vocabulary
""",
    "visual-style.md": f"""# Visual style

The anchor every Google Flow prompt is built on, so every video looks like the
same channel.

{TODO_MARK}: art style
{TODO_MARK}: palette and lighting
{TODO_MARK}: aspect ratio (16:9 for long-form)
{TODO_MARK}: what to avoid
""",
    "voice.md": f"""# Voice

The ElevenLabs voice and settings this channel uses for every video.

{TODO_MARK}: voice name
{TODO_MARK}: model and settings (stability, similarity, style, speed)
{TODO_MARK}: pronunciation notes
""",
    "edit-preset.toml": f"""# The edit every video gets. Read by `ytflow timeline build`.
# {TODO_MARK}: review these defaults, then delete this line.

[subtitles]
font = "Noto Sans"
size = 48
color = "#ffffff"
box_color = "#000000"
box_opacity = 0.6
max_chars_per_line = 42

[chapters]
position = "top-left"
font = "Noto Sans"
size = 40

[video]
width = 1920
height = 1080
fps = 30
fade_in_seconds = 1.0
fade_out_seconds = 1.5

[transitions]
types = ["dissolve", "wipe-left", "wipe-right", "slide-up"]
seconds = 0.6

[camera]
moves = ["zoom-in", "zoom-out", "pan-left", "pan-right"]
max_zoom = 1.12
""",
    "publish.md": f"""# Publish template

Reused for every video's description and tags.

{TODO_MARK}: description template (intro line, chapters, links, call to action)
{TODO_MARK}: base tags every video gets
""",
}


def validate_name(kind: str, name: str) -> str:
    if not NAME_RE.match(name):
        raise WorkspaceError(
            f"invalid {kind} name {name!r}: use lowercase letters, digits and hyphens (e.g. my-channel)"
        )
    return name


def versions(step_dir: Path) -> list[int]:
    """Version numbers present under a step directory, ascending."""
    if not step_dir.is_dir():
        return []
    found = (VERSION_RE.match(p.name) for p in step_dir.iterdir() if p.is_dir())
    return sorted(int(m.group(1)) for m in found if m)


def latest_version(step_dir: Path) -> Path | None:
    found = versions(step_dir)
    return step_dir / f"v{found[-1]}" if found else None


def new_version(step_dir: Path, copy_latest: bool = False) -> Path:
    """Create `v<N+1>` under step_dir; with copy_latest, start from the latest version's files."""
    previous = latest_version(step_dir)
    target = step_dir / f"v{versions(step_dir)[-1] + 1 if previous else 1}"
    if copy_latest and previous is not None:
        shutil.copytree(previous, target)
    else:
        target.mkdir(parents=True)
    return target


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def channels(self) -> Path:
        return self.root / CHANNELS_DIR

    def channel(self, channel: str) -> Path:
        path = self.channels / validate_name("channel", channel)
        if not (path / "channel.toml").is_file():
            raise WorkspaceError(f"no channel {channel!r} in {self.channels} — run: ytflow channel new {channel}")
        return path

    def video(self, channel: str, video: str) -> Path:
        path = self.channel(channel) / "videos" / validate_name("video", video)
        if not (path / "video.toml").is_file():
            raise WorkspaceError(f"no video {video!r} in channel {channel!r} — run: ytflow video new {channel} {video}")
        return path

    def create_channel(self, channel: str) -> Path:
        path = self.channels / validate_name("channel", channel)
        if path.exists():
            raise WorkspaceError(f"channel {channel!r} already exists at {path}")
        for sub in ("references", "branding", "kit", "videos"):
            (path / sub).mkdir(parents=True)
        (path / "channel.toml").write_text(f'name = "{channel}"\n')
        kit = new_version(path / "kit")
        for name, text in KIT_TEMPLATES.items():
            (kit / name).write_text(text)
        return path

    def create_kit_version(self, channel: str) -> Path:
        return new_version(self.channel(channel) / "kit", copy_latest=True)

    def create_video(self, channel: str, video: str, kit: str | None = None) -> Path:
        channel_dir = self.channel(channel)
        path = channel_dir / "videos" / validate_name("video", video)
        if path.exists():
            raise WorkspaceError(f"video {video!r} already exists at {path}")
        kit_dir = self.kit_dir(channel_dir, kit)
        for sub in ("images", "audio"):
            (path / sub).mkdir(parents=True)
        (path / "video.toml").write_text(f'name = "{video}"\nkit = "{kit_dir.name}"\n')
        return path

    def video_kit(self, channel: str, video: str) -> Path:
        meta = tomllib.loads((self.video(channel, video) / "video.toml").read_text())
        return self.kit_dir(self.channel(channel), meta["kit"])

    @staticmethod
    def kit_dir(channel_dir: Path, kit: str | None) -> Path:
        if kit is None:
            latest = latest_version(channel_dir / "kit")
            if latest is None:
                raise WorkspaceError(f"channel at {channel_dir} has no kit version")
            return latest
        if not VERSION_RE.match(kit) or not (channel_dir / "kit" / kit).is_dir():
            raise WorkspaceError(
                f"no kit version {kit!r} (have: {', '.join(f'v{n}' for n in versions(channel_dir / 'kit'))})"
            )
        return channel_dir / "kit" / kit


def files_in(directory: Path) -> list[Path]:
    """Non-hidden files directly in a directory, sorted by name."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith("."))


def kit_todo_files(kit_dir: Path) -> list[str]:
    """Kit files that still carry a template placeholder."""
    return [p.name for p in files_in(kit_dir) if TODO_MARK in p.read_text(errors="replace")]


def step_state(base: Path, step: Step) -> tuple[bool, str]:
    """(done, description) for one step under a channel or video directory."""
    if step.kind == "input":
        count = len(files_in(base / step.name))
        return count > 0, f"{count} file(s)" if count else "empty"
    latest = latest_version(base / step.name)
    if latest is None:
        return False, "not started"
    if not files_in(latest):
        return False, f"{latest.name} (empty)"
    return True, latest.name


def channel_status(ws: Workspace, channel: str) -> tuple[list[str], str | None]:
    """Report lines and the next action for a channel, or None when the channel setup is done."""
    channel_dir = ws.channel(channel)
    lines = [f"channel {channel}"]
    next_action: str | None = None
    for step in CHANNEL_STEPS:
        done, desc = step_state(channel_dir, step)
        lines.append(f"  {step.name:<10} {desc}")
        if not done and next_action is None:
            next_action = f"{step.action} (skill: {step.skill})"
    kit = latest_version(channel_dir / "kit")
    todo = kit_todo_files(kit) if kit else []
    kit_desc = f"{kit.name}" + (f", still TODO: {', '.join(todo)}" if todo else ", complete") if kit else "missing"
    lines.append(f"  {'kit':<10} {kit_desc}")
    if todo and next_action is None:
        next_action = f"fill the channel kit {kit.name}: {', '.join(todo)} (skills: style, voiceover, edit, publish)"
    videos_dir = channel_dir / "videos"
    names = sorted(p.name for p in videos_dir.iterdir() if (p / "video.toml").is_file()) if videos_dir.is_dir() else []
    lines.append(f"  {'videos':<10} {', '.join(names) if names else 'none'}")
    if next_action is None and not names:
        next_action = f"start the first video: ytflow video new {channel} <video>"
    return lines, next_action


def video_status(ws: Workspace, channel: str, video: str) -> tuple[list[str], str | None]:
    """Report lines and the next action for a video, or None when every step is done."""
    video_dir = ws.video(channel, video)
    lines = [f"video {channel}/{video} (kit {ws.video_kit(channel, video).name})"]
    next_action: str | None = None
    for step in VIDEO_STEPS:
        done, desc = step_state(video_dir, step)
        lines.append(f"  {step.name:<10} {desc}")
        if not done and next_action is None:
            next_action = f"{step.action} (skill: {step.skill})"
    return lines, next_action
