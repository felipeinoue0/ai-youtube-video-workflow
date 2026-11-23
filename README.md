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
- [Quick start](#quick-start)
- [How to use](#how-to-use)
- [Where your files are](#where-your-files-are)
- [Common questions](#common-questions)
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

This project connects those steps. You **talk to an AI coding agent**
(Claude Code, opencode or Codex) and it walks you through the video one step
at a time. In each step it writes what you need (the script, the image
prompts, the narration text, the Kdenlive project, the title and description),
tells you exactly what to do in the external tool, and checks what you bring
back. You review every result before moving on.

**In short:** you bring the ideas and press the buttons in Canva, Google Flow,
ElevenLabs and Kdenlive; the agent does the writing, the naming, the timing and
the editing setup.

> It does **not** call those tools for you and needs **no API key**. Nothing
> you create leaves your computer: everything stays in the `channels/` folder.

## Quick start

**1. Get what you need**

| You need | What for |
|---|---|
| An AI coding agent: [Claude Code](https://claude.com/claude-code), opencode or Codex | it runs the workflow |
| Either [Docker](https://docs.docker.com/get-docker/) **or** Python 3.12 + [uv](https://docs.astral.sh/uv/) | runs the `ytflow` tool |
| Accounts on Canva, Google Flow and ElevenLabs | logo/banner, images, voice |
| [Kdenlive](https://kdenlive.org/) (free) | the final edit and render |

**2. Get the project and start the agent**

```bash
git clone https://github.com/fiwon123/ai-youtube-video-workflow.git
cd ai-youtube-video-workflow

# With Docker (the agents are already installed inside):
make dev-up          # start the sandbox, then Ctrl-C to leave the logs
make claude-auto     # or: make opencode-auto / make codex-auto

# Or without Docker, with your own agent installed:
uv sync
claude               # open your agent in this folder
```

On Windows without WSL2, use `python scripts/dev-up.py dev-up` and
`python scripts/dev-up.py claude-auto` instead of `make`.

**3. Say what you want**

Just write to the agent in plain words, for example:

> *"Let's create a new channel about ancient history."*
>
> *"Let's continue."* (it finds where you stopped)
>
> *"Start a new video about the Roman roads."*

The `guide` skill checks where you are (`ytflow status`) and opens the right
step. You never need to remember a command; the agent runs them for you.

## How to use

Each step below is one conversation with the agent. When you are happy with a
result, say so and it moves to the next step. Not happy? Ask for changes: it
writes a **new version** (`v2`, `v3`, …) and keeps the old ones.

### Once per channel

| Step | The agent does | You do |
|---|---|---|
| **1. Branding** | asks a few questions, then writes the channel name ideas, description, keywords, the Canva sizes and style for the logo and banner, and the description template for every video | make the logo and banner in Canva, save them in the branding folder (the agent checks YouTube's sizes) and upload them to YouTube |
| **2. Style** | reads 2–5 transcripts of videos you like and writes the style guide (hook, pace, structure, tone) and the "visual anchor" added to every image prompt | paste the transcripts into the chat or a file |

### For every video

| Step | The agent does | You do |
|---|---|---|
| **3. Script** | an outline first, then the script: one phrase per line, grouped in chapters | read it and ask for changes until you like it |
| **4. Images** | one Google Flow prompt per phrase, named `001_the-river-at-dawn`, `002_…` | generate each image in Google Flow and download it; the agent renames the downloads (`ytflow images import`) and checks none is missing |
| **5. Narration** | the text to paste into ElevenLabs (and your chosen voice, saved for later videos) | generate the audio in ElevenLabs and save it in the video's `audio/` folder; the agent then times every phrase to the real voice (`ytflow align`) |
| **6. Edit** | a Kdenlive project: subtitles in a box, chapter title at the top-left, fade in/out, transitions and a slow zoom or pan on each image, plus a quick preview video | open the project in Kdenlive, watch it, tweak if you want, and render |
| **7. Publish** | title options, the description (with chapter timestamps), the tags and the captions file | pick a title and upload the video to YouTube |

**Video 2 and later are faster.** The first video saves your voice, edit
settings and style into the channel **kit**, so every new video uses them
automatically and looks like the first one.

Want to see a whole run with real commands and their output? Read the
**[Walkthrough](docs/wiki/Walkthrough.md)**.

Optional: for the most precise subtitle timing, run `uv sync --extra align`
once (installs faster-whisper). Without it, timing is estimated per chapter.

## Where your files are

Everything lives in `channels/` (never committed to git):

```text
channels/<channel>/
├── branding/v1/              brief, Canva guide, name/description/keywords, your logo + banner
├── references/               transcripts of videos you like (for the style step)
├── kit/v1/                   the channel's style, visual anchor, voice, edit settings
└── videos/<video>/
    ├── script/v1/            the script (and its timed version)
    ├── prompts/v1/           one Google Flow prompt per phrase
    ├── images/               your images: 001_…png, 002_…png, …
    ├── voiceover/v1/         the text for ElevenLabs
    ├── audio/                your narration audio
    ├── timing/v1/            when each phrase is spoken + subtitles.srt
    ├── timeline/v1/          the Kdenlive project (<video>.kdenlive) + preview.mp4
    ├── publish/v1/           title, description, tags
    └── package/v1/           everything you paste into the tools, in one folder
```

Tip: ask the agent *"make the package"* (`ytflow package`) to get one folder
with the timed script, the ElevenLabs text and the Flow prompts side by side.

## Common questions

**I don't like a result. What now?**
Tell the agent what to change. It writes a new version (`v2`) and the old one
is kept, so you can compare or go back.

**I stopped in the middle. How do I continue?**
Open the agent and say *"let's continue"*. It reads `ytflow status` and picks
up where you were.

**How do I start the next video?**
Say *"start a new video about …"*. Branding and style are already done, so it
starts at the script.

**I want to change the channel's style or voice.**
Ask for it. The agent writes a new kit version; videos already made keep the
kit they used, new videos get the new one.

**Do I need to know the `ytflow` commands?**
No. The agent runs them. `uv run ytflow --help` lists them if you are curious.

**My image downloads have random names.**
That is fine: the agent matches them to the prompts by name or download order,
and asks you only about the ones it cannot match.

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
  stand-ins for Canva, Google Flow and ElevenLabs. Real Google Flow downloads
  and a real ElevenLabs narration have since been imported on one channel
  ([#41](https://github.com/fiwon123/ai-youtube-video-workflow/issues/41));
  other accounts' settings screens may still differ from what the skills
  describe.
- **The dev sandbox on macOS and native Windows**: it was only started on Linux.

## License

Proprietary, all rights reserved. See [LICENSE](LICENSE).
