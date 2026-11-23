<div align="center">

<h1>ai-youtube-video-workflow</h1>

<p>AI agent skills that guide a creator from channel branding to a published YouTube video, one reviewable step at a time.</p>

<p>
  <a href="https://github.com/fiwon123/ai-youtube-video-workflow/actions/workflows/ci.yml"><img src="https://github.com/fiwon123/ai-youtube-video-workflow/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/fiwon123/ai-youtube-video-workflow/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-proprietary-blue" alt="License"></a>
  <img src="https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20WSL2%20%7C%20Windows-4c8bf5" alt="Platforms">
</p>

</div>

---

## Table of contents

- [About](#about)
- [How to use](#how-to-use)
- [Architecture](#architecture)
- [Repository](#repository)
- [How to develop](#how-to-develop)
- [Troubleshooting](#troubleshooting)
- [Tech stack](#tech-stack)
- [What is not proven](#what-is-not-proven)
- [License](#license)

## About

Making a long YouTube video with AI tools means juggling many of them by hand:
a design tool for the logo, reference videos for the style, an image generator
for every scene, a voice generator, a video editor, and YouTube's own metadata.
This project connects those steps. You run a guided workflow with an AI coding
agent (Claude Code, opencode or Codex). Each step produces a **versioned**
output you review and improve before moving on. It tells you what to make in
each external tool and generates everything that tool needs. It does not call
those tools for you.

> **Status**: repository set up; the workflow steps are being built in the
> order listed under [How to use](#how-to-use).

## How to use

You work with an AI agent inside this repository. Say **"let's continue"** (or
"start a new video"): the `guide` skill runs `ytflow status` and hands over to
the skill for the next step. Every step writes a new version under
`channels/<channel>/…/<step>/v<N>/`, so you can ask for another one and compare.

**Once per channel**

1. **Branding**: a short interview, then the logo and banner made in Canva
   (sizes, safe areas, style direction), the channel description and keywords,
   and the description template every video will use.
2. **Style**: give the agent 2–5 transcripts of videos you like. It measures
   them and writes the style guide (hook, pacing, structure, tone) and the
   visual anchor added to every image prompt.

**For every video**

3. **Script**: an outline, then the script, one phrase per line in chapters.
4. **Images**: one Google Flow prompt per phrase, named
   `<enumerate_id>_<part_of_phrase>` (e.g. `012_the-river-at-dawn`). Download
   the images; `ytflow images import` renames them in download order.
5. **Narration**: the text to paste into ElevenLabs. Save the audio back, and
   `ytflow align` times every phrase to the real voice.
6. **Edit**: a Kdenlive project with boxed subtitles, the chapter title
   top-left, a fade in and out, varied transitions and a slow pan or zoom on
   each image — plus a quick preview render.
7. **Publish**: pick your title; get the description with chapter timestamps,
   the tags, and the captions file.

The first video also settles the voice and the edit; they are stored in the
channel **kit**, so video 2, 3, 4 come out with the same style, look, voice and
edit without setting anything up again.

**[Walkthrough](docs/wiki/Walkthrough.md)**: one sample channel from an empty
folder to a finished video and the start of the next one, with every command
and its real output.

What you need: an AI coding agent, plus the tools you use along the way
(Canva, Google Flow, ElevenLabs, Kdenlive). None of them needs an API key here.
For the most precise timing, `uv sync --extra align` installs faster-whisper
(optional).

## Architecture

```text
You ──► agent skill (one per step) ──► ytflow CLI (numbers, timings, files)
              │
              ▼
   channels/<channel>/videos/<video>/<step>/v<N>/
              │
              ▼
You use the outputs in Canva · Google Flow · ElevenLabs
              │
              ▼
images + audio back ──► ytflow builds the Kdenlive project ──► you render and publish
```

The skills do the writing; the `ytflow` CLI does everything that has to be
exact (numbering, timings, file names, the Kdenlive project), and that part is
tested.

## Repository

- **Source**: <https://github.com/fiwon123/ai-youtube-video-workflow>
- **Issues**: <https://github.com/fiwon123/ai-youtube-video-workflow/issues>

## How to develop

### Prerequisites

- **Either** Docker (the dev sandbox), **or** Python 3.12 and
  [uv](https://docs.astral.sh/uv/) on the host
- `make` (all commands below are Make targets; native Windows uses
  `python scripts/dev-up.py` instead)
- Nothing for the AI agents: opencode, Claude Code and Codex are installed in
  the dev image. `make claude-auto`, `make opencode-auto` or `make codex-auto`
  starts one (drop `-auto` to have it ask before each action). It asks for its
  login once and keeps it in a Docker volume. `make doctor` checks Docker, the
  image and every login at once.

> **Demo, on any OS**: `docker compose up` starts the sandbox with nothing
> installed but Docker.

### Platforms

| Platform | Start the sandbox | Run an agent in it |
|---|---|---|
| **Linux / macOS** | `make dev-up` | `make claude-auto` (or `opencode-auto`, `codex-auto`) |
| **Windows + WSL2** | `make dev-up` (inside WSL2; clone into `~/`, not `/mnt/c`) | `make claude-auto` |
| **Windows native** | `python scripts/dev-up.py dev-up` | `python scripts/dev-up.py claude-auto` |

If PowerShell blocks the wrapper, run
`powershell -ExecutionPolicy Bypass -File .\scripts\dev-up.ps1 dev-up`.

### Quick start

```bash
make dev-up      # start the sandbox (does not rebuild; Ctrl-C leaves it running)
make check       # locked install + tests + lint + format
make dev-down    # stop
```

Without Docker: `uv sync` then `make check`.

### Commands

| Command | What it does |
|---|---|
| `make check` | `uv sync --locked`, pytest, ruff check, ruff format --check |
| `make test` / `lint` / `format` | one of those on its own |
| `make dev-up` | start the dev sandbox (does not rebuild) |
| `make dev-restart` | `dev-down` then `dev-up` |
| `make dev-build` | rebuild the image after a Dockerfile change |
| `make dev-shell` | shell inside the sandbox |
| `make doctor` | check Docker, the image, the GitHub token and the agent logins |
| `make wiki-push` | publish `docs/wiki/` to the GitHub wiki |

See [AGENTS.md](AGENTS.md) for the workflow every agent follows, and
[CONTRIBUTING.md](CONTRIBUTING.md) to report an issue or send a change.

## Troubleshooting

### `/bin/bash^M: bad interpreter`, `$'\r': command not found`, or `set: pipefail: invalid option name`

The scripts were checked out with Windows (CRLF) line endings. The repository
pins LF in `.gitattributes`; re-checkout the files:

```bash
git rm --cached -r . >/dev/null
git reset --hard
```

### `make` fails on native Windows

`make` there runs under `cmd.exe`/PowerShell, not a POSIX shell. Use WSL2, or
`python scripts/dev-up.py dev-up`.

### The container cannot write to the workspace

On Linux the sandbox runs as your UID/GID. If yours is not `1000`:
`make dev-up HOST_UID="$(id -u)" HOST_GID="$(id -g)"`. If root wrote to the
checkout earlier: `sudo chown -R "$(id -u):$(id -g)" .`

### Reset everything

```bash
make reset       # stops the sandbox and deletes its volumes, agent logins included
```

## Tech stack

| Layer | Technology |
|---|---|
| CLI | Python 3.12, uv, pytest, ruff |
| Workflow steps | agent skills (`.agents/skills/`, mirrored to `.claude/skills/`) |
| Media | ffmpeg, Kdenlive project files |
| Dev environment | Docker Compose sandbox with opencode, Claude Code and Codex |

## What is not proven

- **The Kdenlive project's native layout**: an earlier export was opened and
  checked in Kdenlive 26.08.2
  ([#27](https://github.com/fiwon123/ai-youtube-video-workflow/issues/27)).
  The export now writes Kdenlive's own 1.1 layout, modeled on a project saved
  by Kdenlive 26.08.2 (dissolves as clip fades, the subtitle list, chapter
  guides); that layout is tested by reading it back, and still has to be
  opened in Kdenlive to be called verified. Other Kdenlive versions are untried.
- **The external tools**: the [walkthrough](docs/wiki/Walkthrough.md) ran with
  stand-ins for Canva, Google Flow and ElevenLabs (generated images, a
  synthetic voice). Their real download names and settings screens may differ
  from what the skills describe.
- **The dev sandbox on macOS and native Windows**: it was only started on Linux.

## License

Proprietary, all rights reserved. See [LICENSE](LICENSE).
