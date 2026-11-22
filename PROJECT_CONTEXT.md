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

**Per channel (once):**

1. **Branding** — step-by-step guidance for creating the logo and banner in a
   design tool such as Canva (sizes, safe areas, prompts and style direction),
   then the channel description and channel tags.

**Per video:**

2. **Style references** — the creator gives a few transcripts of videos they
   like. The agent extracts what makes them work (hook, pacing, structure,
   tone, phrase length) and records it as a style guide for the new script.
3. **Script** — a script for the new video, organized by time and phrase
   (start, end, phrase text, chapter), using the style guide.
4. **Image prompts** — one detailed background-image prompt per phrase part,
   for Google Flow. Every prompt is named `<enumerate_id>_<part_of_phrase>`
   (for example `012_the-river-at-dawn`), and the creator saves each generated
   image under that name, so the files sort into timeline order and drop
   straight into an editor.
5. **Voiceover** — a narration file generated from the timed script, ready to
   paste into ElevenLabs to produce the audio.
6. **Edit** — the creator hands back the images and the audio; the agent
   generates a Kdenlive project with:
   - subtitles to a good readability standard, on a semi-opaque box behind the
     text;
   - a chapter title in the top-left corner for each important section;
   - a fade in at the start and a fade out at the end of the video;
   - a simple transition between every pair of images, varied across the video
     (fade plus other simple ones) so a long video does not feel repetitive;
   - a slow, professional camera effect on each static image (pan, zoom in,
     zoom out), varied from image to image.
7. **Publish** — the title, description and tags, based on the title the
   creator chose.

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
- **In progress**: nothing yet

## Backlog

In build order. Each item is its own issue and branch.

1. Workspace layout and versioning: `ytflow` commands to create a channel and a video folder and to start a new version of a step.
2. Branding skill: Canva logo/banner guidance, channel description and tags.
3. Style-reference skill: analyze the given transcripts into a style guide.
4. Script skill and timed-script format: a validated file of start, end, phrase and chapter.
5. Image-prompt skill: Google Flow prompts named `<enumerate_id>_<part_of_phrase>`, plus a check that every expected image file exists.
6. Voiceover skill: the ElevenLabs narration file from the timed script.
7. Kdenlive project generator: images and audio on the timeline, subtitles on a box, chapter titles top-left, fade in/out, varied transitions, slow camera motion.
8. Publish skill: title, description and tags from the chosen title.
