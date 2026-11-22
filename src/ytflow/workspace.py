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
    kit_file: str | None = None  # the kit file this step reads; it must be filled first
    done_file: str | None = None  # a version is done when it holds this file (else: any file)


CHANNEL_STEPS = (
    Step("branding", "branding", "create the logo and banner in Canva and write the channel description and tags"),
)

VIDEO_STEPS = (
    Step(
        "script",
        "script",
        "write script.md from the kit's style guide and run ytflow script build",
        kit_file="style-guide.md",
        done_file="script.json",
    ),
    Step(
        "prompts",
        "image-prompts",
        "run ytflow prompts init, write a scene per phrase, then ytflow prompts build",
        kit_file="visual-style.md",
        done_file="prompts.json",
    ),
    Step(
        "images", "image-prompts", "generate the images in Google Flow and save them under their prompt names", "input"
    ),
    Step(
        "voiceover",
        "voiceover",
        "export the narration text for ElevenLabs: ytflow voiceover text",
        kit_file="voice.md",
        done_file="voiceover.json",
    ),
    Step("audio", "voiceover", "generate the narration in ElevenLabs and save it in audio/", "input"),
    Step(
        "timing",
        "voiceover",
        "align the narration to the script: ytflow align",
        done_file="timing.json",
    ),
    Step(
        "timeline",
        "edit",
        "build the edit: ytflow timeline build, then preview and export it",
        kit_file="edit-preset.toml",
        done_file="timeline.json",
    ),
    Step(
        "publish",
        "publish",
        "write the title, description and tags: ytflow publish init, then ytflow publish build",
        kit_file="publish.md",
        done_file="publish.json",
    ),
)

# Which skill fills each kit file. The channel steps (branding, style) fill theirs before
# the first video; voice and edit preset are filled during the first video's steps.
KIT_OWNERS = {
    "publish.md": "branding",
    "style-guide.md": "style",
    "visual-style.md": "style",
    "voice.md": "voiceover",
    "edit-preset.toml": "edit",
}
CHANNEL_KIT_FILES = ("publish.md", "style-guide.md", "visual-style.md")

KIT_TEMPLATES: dict[str, str] = {
    "style-guide.md": f"""+++
# The numbers the script step uses. Measured from the references by
# `ytflow references stats`; `ytflow kit check` validates them.
words_per_minute = 0      # narration pace
phrase_words_target = 0   # typical words per phrase (one subtitle / one image)
phrase_words_max = 0      # longest phrase allowed
+++

# Style guide

How this channel's scripts read. Filled by the style skill from the reference
transcripts in `references/`; every video's script follows it.

{TODO_MARK}: hook (first 15 seconds)
{TODO_MARK}: structure (chapters, how a chapter opens and closes)
{TODO_MARK}: pacing and phrase length
{TODO_MARK}: tone and vocabulary
""",
    "visual-style.md": f"""+++
# Read by the image-prompt step; `ytflow kit check` validates it.
aspect_ratio = "16:9"
anchor = ""   # one sentence appended verbatim to every Google Flow prompt
avoid = ""    # what every image must not contain
+++

# Visual style

The anchor every Google Flow prompt is built on, so every video looks like the
same channel.

{TODO_MARK}: art style
{TODO_MARK}: palette and lighting
{TODO_MARK}: aspect ratio (16:9 for long-form)
{TODO_MARK}: what to avoid
""",
    "voice.md": f"""+++
# Read by `ytflow voiceover text`; `ytflow kit check` validates it.
voice = ""                        # ElevenLabs voice name
voice_id = ""                     # its voice id, to find the same voice again
model = "eleven_multilingual_v2"
stability = 0.5                   # 0–1
similarity = 0.75                 # 0–1
style = 0.0                       # 0–1
speed = 1.0                       # 0.7–1.2
chapter_break = 1.0               # seconds of pause between chapters (0 = none)

[pronunciations]                  # word as written = spelling the voice says right
# "Nero" = "Neer-oh"
+++

# Voice

The ElevenLabs voice and settings this channel uses for every video. Filled by
the voiceover skill during the first video.

{TODO_MARK}: why this voice (gender, age, accent, energy) and voices tried
{TODO_MARK}: delivery notes (pace, emphasis, what to re-generate)
""",
    "edit-preset.toml": f"""# The edit every video gets. Read by `ytflow timeline build`;
# `ytflow kit check` validates it.
# {TODO_MARK}: review these defaults with the edit skill, then delete this line.

[subtitles]
font = "Noto Sans"
size = 48                 # pixels at the video height below
color = "#ffffff"
box_color = "#000000"     # the box behind the text
box_opacity = 0.6         # 0 transparent – 1 solid
max_chars_per_line = 42
max_lines = 2
margin_bottom = 60
min_seconds = 1.0         # shortest time a subtitle stays on screen

[chapters]
position = "top-left"
font = "Noto Sans"
size = 40
seconds = 5.0             # how long the chapter title shows
margin = 48

[video]
width = 1920
height = 1080
fps = 30
fade_in_seconds = 1.0
fade_out_seconds = 1.5

[audio]
lead_seconds = 0.5        # image before the narration starts
tail_seconds = 1.5        # image after it ends

[transitions]
# the first type is the calm one: every chapter change and every other cut
types = ["dissolve", "wipe-left", "wipe-right", "slide-up"]
seconds = 0.6

[camera]
moves = ["zoom-in", "zoom-out", "pan-left", "pan-right"]
max_zoom = 1.12           # never more than 12% in
zoom_per_second = 0.03    # slow: a 4 s image moves 12%
""",
    "publish.md": f"""+++
# Read by `ytflow publish build`; `ytflow kit check` validates it.
base_tags = []   # tags every video gets, e.g. ["roman history", "ancient rome"]
+++
{{summary}}

{{chapters}}

{TODO_MARK}: links (sources, other videos, socials), one per line
{TODO_MARK}: a short call to action in the channel's tone
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

    def videos_using_kit(self, channel: str, kit: str) -> list[str]:
        """Videos of a channel pinned to a kit version."""
        videos_dir = self.channel(channel) / "videos"
        if not videos_dir.is_dir():
            return []
        metas = sorted(p / "video.toml" for p in videos_dir.iterdir() if (p / "video.toml").is_file())
        return [m.parent.name for m in metas if tomllib.loads(m.read_text()).get("kit") == kit]

    def editable_kit(
        self, channel: str, video: str | None = None, files: tuple[str, ...] = ()
    ) -> tuple[Path, list[str]]:
        """The kit version a skill may write to, and the videos that forced a new one.

        The target is the video's kit, or the channel's latest. It is edited in place
        while no video uses it, or when every file to write still carries its
        placeholder: no video can have relied on an unfilled file. Otherwise editing
        would change what a video was made with, so a new version is started from a
        copy of the latest kit instead.
        """
        for name in files:
            if name not in KIT_TEMPLATES:
                raise WorkspaceError(f"unknown kit file {name!r} (kit files: {', '.join(KIT_TEMPLATES)})")
        target = self.video_kit(channel, video) if video else self.kit_dir(self.channel(channel), None)
        if files and all(TODO_MARK in (target / name).read_text(errors="replace") for name in files):
            return target, []
        users = self.videos_using_kit(channel, target.name)
        if not users:
            return target, []
        return self.create_kit_version(channel), users

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


def version_dir(step_dir: Path, version: str | None) -> Path:
    """A named version of a step (``v2``), or its latest when version is None."""
    if version is None:
        latest = latest_version(step_dir)
        if latest is None:
            raise WorkspaceError(f"no {step_dir.name} version yet — run: ytflow version new {step_dir}")
        return latest
    if not VERSION_RE.match(version) or not (step_dir / version).is_dir():
        raise WorkspaceError(f"no {step_dir.name} version {version!r}")
    return step_dir / version


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
    if step.done_file and not (latest / step.done_file).is_file():
        return False, f"{latest.name} (no {step.done_file} yet)"
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
    kit = ws.kit_dir(channel_dir, None)
    todo = kit_todo_files(kit)
    lines.append(f"  {'kit':<10} {kit.name}" + (f", still TODO: {', '.join(todo)}" if todo else ", complete"))
    for name in CHANNEL_KIT_FILES:
        if name in todo and next_action is None:
            next_action = fill_kit_action(kit, name)
    videos_dir = channel_dir / "videos"
    names = sorted(p.name for p in videos_dir.iterdir() if (p / "video.toml").is_file()) if videos_dir.is_dir() else []
    lines.append(f"  {'videos':<10} {', '.join(names) if names else 'none'}")
    if next_action is None and not names:
        next_action = f"start the first video: ytflow video new {channel} <video>"
    return lines, next_action


def fill_kit_action(kit: Path, name: str) -> str:
    return f"fill {name} in kit {kit.name} (skill: {KIT_OWNERS[name]})"


def images_state(video_dir: Path) -> tuple[bool, str] | None:
    """Images against the latest built prompts: (done, "12/42 images"), or None before prompts exist."""
    import json

    from ytflow.images import check

    prompts = latest_version(video_dir / "prompts")
    if prompts is None or not (prompts / "prompts.json").is_file():
        return None
    expected = [p["name"] for p in json.loads((prompts / "prompts.json").read_text())["prompts"]]
    report = check(video_dir / "images", expected, "16:9", probe=False)
    return not report.missing, f"{len(report.present)}/{len(expected)} images"


def audio_state(video_dir: Path) -> tuple[bool, str] | None:
    """Narration audio against the latest voiceover export, or None before the export exists."""
    import json

    from ytflow.voiceover import COMPILED, check_audio

    voiceover = latest_version(video_dir / "voiceover")
    if voiceover is None or not (voiceover / COMPILED).is_file():
        return None
    chapters = [c["file"] for c in json.loads((voiceover / COMPILED).read_text())["chapters"]]
    report = check_audio(video_dir / "audio", chapters)
    if report.layout == "single":
        return not report.problems, report.files[0].name
    if report.layout == "chapters":
        done = not report.missing and not report.problems
        return done, f"{len(report.files)}/{len(chapters)} chapter files"
    return False, "empty"


def video_status(ws: Workspace, channel: str, video: str) -> tuple[list[str], str | None]:
    """Report lines and the next action for a video, or None when every step is done."""
    video_dir = ws.video(channel, video)
    kit = ws.video_kit(channel, video)
    todo = kit_todo_files(kit)
    lines = [f"video {channel}/{video} (kit {kit.name})"]
    next_action: str | None = None
    for step in VIDEO_STEPS:
        done, desc = step_state(video_dir, step)
        if step.name == "images" and (counted := images_state(video_dir)):
            done, desc = counted
        if step.name == "audio" and (counted := audio_state(video_dir)):
            done, desc = counted
        lines.append(f"  {step.name:<10} {desc}")
        if not done and next_action is None:
            if step.kit_file in todo:
                next_action = fill_kit_action(kit, step.kit_file)
            else:
                next_action = f"{step.action} (skill: {step.skill})"
    return lines, next_action
