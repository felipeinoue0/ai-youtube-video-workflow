# Project Context

> The agent reads this file first. It is the primary source of project identity:
> `AGENTS.md` is populated from it. Keep it current when a decision changes.

---

## Identity

- **Project Name**: ai-youtube-video-workflow
- **One-liner**: A set of AI agent skills, backed by a small Python CLI (`ytflow`), that guides a creator from channel branding to a published YouTube video, one reviewable step at a time.
- **GitHub repository**: https://github.com/fiwon123/ai-youtube-video-workflow

## Problem

Making a long-form YouTube video with AI tools means juggling many of them by
hand: a design tool for the logo and banner, reference videos for the writing
style, an image generator for every scene, a voice generator for the narration,
a video editor for subtitles, chapters, transitions and camera motion, and
YouTube itself for the title, description and tags. Nothing connects the steps,
so the creator re-explains the context to each tool, loses track of which file
belongs to which line of the script, and rebuilds the same edit every time.

## Goal

The creator runs one guided workflow per channel and per video. Each step is an
agent skill that produces a versioned output the creator reviews and iterates on
before moving on. At the end they have an edited video project ready to render
in Kdenlive, plus the title, description and tags to publish it. The workflow
**coordinates**: it tells the creator what to produce in which external tool
(Canva, Google Flow, ElevenLabs, Kdenlive) and generates everything those tools
need, and it does not call their APIs itself.

### The workflow

**Per channel (once, then refined):**

1. **Branding** — step-by-step guidance for creating the logo and banner in a
   design tool such as Canva (sizes, safe areas, prompts and style direction),
   then the channel description and channel tags.
2. **Style references** — the creator gives a few transcripts of videos they
   like. The agent extracts what makes them work (hook, pacing, structure,
   tone, phrase length) into the channel's style guide, and fixes the visual
   anchor every image prompt reuses.

Both write to the **channel kit** (`channels/<channel>/kit/v<N>/`), the
channel's memory that keeps video 2, 3, 4 consistent with video 1:

| File | Holds |
|---|---|
| `style-guide.md` | hook, structure, pacing, tone, phrase length |
| `visual-style.md` | the Google Flow prompt anchor: art style, palette, lighting, aspect ratio, what to avoid |
| `voice.md` | the ElevenLabs voice and settings, pronunciation notes |
| `edit-preset.toml` | subtitle font/size/box, chapter title style, transition set, camera-motion speed |
| `publish.md` | description template, base tags, links, call to action |

Each video records the kit version it was made with. When a video teaches
something worth keeping, the creator starts a new kit version and later videos
use it; earlier videos stay reproducible.

**Per video:**

3. **Script** — a script for the new video, organized by phrase (chapter,
   phrase text, estimated start and end), using the kit's style guide.
4. **Image prompts** — one detailed background-image prompt per phrase part,
   for Google Flow, built on the kit's visual anchor. Every prompt is named `<enumerate_id>_<part_of_phrase>`
   (for example `012_the-river-at-dawn`), and the creator saves each generated
   image under that name, so the files sort into timeline order and drop
   straight into an editor.
5. **Voiceover** — a narration file generated from the script, ready to
   paste into ElevenLabs with the kit's voice settings to produce the audio.
6. **Timing** — the script's times are estimates; the real ones come from the
   audio. `ytflow` aligns the known script text to the narration locally
   (faster-whisper word timestamps, an optional extra). Without the extra, the
   creator exports one audio file per chapter and each chapter's duration is
   spread over its phrases by character count.
7. **Edit** — the creator hands back the images and the audio; `ytflow` builds
   an editor-neutral `timeline.json` from the aligned script, the images, the
   audio and the kit's edit preset, then exports it to the editor. Kdenlive is
   the first exporter; the timeline has:
   - subtitles to a good readability standard, on a semi-opaque box behind the
     text;
   - a chapter title in the top-left corner for each important section;
   - a fade in at the start and a fade out at the end of the video;
   - a simple transition between every pair of images, varied across the video
     (fade plus other simple ones) so a long video does not feel repetitive;
   - a slow, professional camera effect on each static image (pan, zoom in,
     zoom out), varied from image to image.
8. **Publish** — the title, description (with chapter timestamps from the
   timeline) and tags, based on the title the creator chose and the kit's
   publish template.

A **guide** skill and `ytflow status` read the workspace and tell the creator
where they are and what to do next, so a first-time creator can go from an
empty folder to a finished project without knowing the step list.

Every step keeps versions (`v1`, `v2`, …) so the creator can compare
iterations and pick what is good before moving on.

## Stack

- **Language**: Python 3.12, managed with uv
- **Interface**: agent skills (`.agents/skills/`, mirrored to `.claude/skills/`) that call the `ytflow` CLI for the deterministic parts
- **Storage**: local filesystem: one folder per channel and per video, with versioned step outputs
- **AI/LLM**: whichever coding agent the creator runs (Claude Code, opencode, Codex) does the writing; the CLI makes no LLM API calls
- **External tools (used by the creator, not called by the code)**: Canva, Google Flow, ElevenLabs, Kdenlive
- **Media tooling**: ffmpeg (probing audio and image durations), Kdenlive project files (MLT XML)
- **Dev environment**: Docker Compose dev sandbox (`make dev-up`), or uv on the host

## Architecture

```text
Creator ──► agent skill (one per step) ──► ytflow CLI (validate, number, generate files)
                │                                   │
                ▼                                   ▼
   channels/<channel>/videos/<video>/<step>/v<N>/   (versioned outputs)
                │
                ▼
Creator uses the outputs in the external tools:
  Canva (logo, banner) · Google Flow (images) · ElevenLabs (audio)
                │
                ▼
images + audio back in the video folder ──► ytflow builds the Kdenlive project
                │
                ▼
Creator renders in Kdenlive ──► publish step: title, description, tags
```

## Design Decisions

- Coordinate, do not integrate: the workflow generates instructions and input files for Canva, Google Flow, ElevenLabs and Kdenlive, and the creator runs those tools. That keeps the project free of paid API keys and of vendor APIs that change often. (2026-11-22)
- Skills for judgment, CLI for determinism: writing (style guide, script, prompts, metadata) is done by the agent through skills; anything that must be exact (numbering, timings, file names, the Kdenlive XML) is done by tested Python code. (2026-11-22)
- `<enumerate_id>_<part_of_phrase>` file names are the join key between the script, the image prompts, the image files and the timeline, so the order never depends on a human renaming files. (2026-11-22)
- Every step writes a new version instead of overwriting, so iterating is cheap and a good earlier version is never lost. (2026-11-22)
- Channel kit: consistency across videos lives in a versioned, per-channel kit that every per-video step reads, not in each video's own files; otherwise video 2 starts over and drifts from video 1. (2026-11-22)
- Editor-neutral timeline: the CLI builds `timeline.json` first and exports it to an editor, so supporting a second editor means a new exporter, not a new pipeline. Kdenlive is first because the creator works on Linux. (2026-11-22)
- Real timings from the audio: subtitles and cuts follow the narration, not the script's estimates. Local alignment (faster-whisper, optional) keeps it free and offline; per-chapter audio with character-count distribution is the dependency-free fallback. (2026-11-22)
- ffmpeg decodes the audio for faster-whisper (16 kHz mono samples), not faster-whisper's own PyAV reader: faster-whisper 1.2.1 calls `av.open(..., metadata_errors=)`, which PyAV 19 rejects. One decoder for every step, and immune to that drift. (2026-11-22)
- No studio app: the product is skills plus a small CLI working on plain files; no GUI. (2026-11-22)
- Python CLI with uv: the editor step is file generation and media probing, which Python handles well, and uv gives a locked, reproducible environment. (2026-11-22)

## Topology

Components:
- kind: cli, path: ., purpose: the `ytflow` package (`src/ytflow/`) and its tests (`tests/`)
- kind: skills, path: .agents/skills/ (mirrored to .claude/skills/), purpose: one agent skill per workflow step

## Directory Layout

```text
src/ytflow/            # the CLI package
tests/                 # pytest suite
.agents/skills/        # agent skills (Codex); mirrored byte for byte in .claude/skills/
channels/              # creator workspace: channel and video outputs (gitignored)
```

## Key Commands

- **Install**: `uv sync`
- **Tests**: `uv run pytest`
- **Lint**: `uv run ruff check .`
- **Format**: `uv run ruff format .`
- **All checks**: `make check`
- **Run the CLI**: `uv run ytflow --help`

## Status

- **Done**: repository setup (workflow, agents, sandbox, CI)
- **In progress**: milestone v0.2.0 — first video end-to-end (see Backlog)

## Backlog

Milestone `v0.2.0 — first video end-to-end`: one successful path from an empty
workspace to a Kdenlive project and publish metadata. In build order; each item
is its own issue and branch.

1. #8 Workspace layout, step versioning, channel kit, `ytflow status`.
2. #9 Branding skill: Canva logo/banner guidance, channel description and tags.
3. #10 Style skill: reference transcripts to the kit's style guide and visual anchor.
4. #11 Script skill and validated timed-script format.
5. #12 Image-prompt skill: `<enumerate_id>_<part_of_phrase>` prompts and a missing-image check.
6. #13 Voiceover skill: ElevenLabs narration text and voice settings.
7. #14 Timing alignment of the narration to the script.
8. #15 `timeline.json` builder and Kdenlive exporter.
9. #16 Publish skill: title, description, tags.
10. #17 Guide skill and an end-to-end walkthrough of a sample video.

Later: a second editor exporter; making video N from an existing kit faster.
