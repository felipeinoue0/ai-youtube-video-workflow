# AGENTS.md

> **Source**: Product sections below are populated from `PROJECT_CONTEXT.md`.
> Update that file first when the project's identity or a decision changes.

### Product

## Project Objective

ai-youtube-video-workflow — a set of AI agent skills, backed by a small Python
CLI (`ytflow`), that guides a creator from channel branding to a published
YouTube video, one reviewable step at a time.

### Problem

Making a long-form YouTube video with AI tools means juggling many of them by
hand — a design tool for the logo and banner, reference videos for the style,
an image generator per scene, a voice generator, a video editor, and YouTube's
own metadata. Nothing connects the steps, so the creator re-explains the
context to every tool, loses track of which file belongs to which line of the
script, and rebuilds the same edit for every video.

### Goal

The creator runs one guided workflow per channel and per video. Each step is an
agent skill that writes a **versioned** output the creator reviews and iterates
on: branding (Canva guidance, channel description and tags) → style guide from
reference transcripts → timed script → Google Flow image prompts named
`<enumerate_id>_<part_of_phrase>` → ElevenLabs narration file → a Kdenlive
project (boxed subtitles, top-left chapter titles, fade in/out, varied
transitions, slow camera motion) → title, description and tags. The workflow
**coordinates** the external tools; it does not call their APIs. The full step
list is in `PROJECT_CONTEXT.md` → "The workflow".

### Main Technology

- Language: Python 3.12, managed with uv (`pyproject.toml`, `uv.lock`)
- Interface: agent skills (`.agents/skills/`, mirrored to `.claude/skills/`) that call the `ytflow` CLI
- Storage: local filesystem — `channels/<channel>/videos/<video>/<step>/v<N>/` (gitignored)
- AI: the coding agent the creator runs does the writing; the code calls no LLM API
- External tools (run by the creator): Canva, Google Flow, ElevenLabs, Kdenlive
- Media: ffmpeg for probing durations; Kdenlive project files (MLT XML)
- Development: Docker Compose dev sandbox (`make dev-up`), or uv on the host

### Core Architecture

```text
Creator → agent skill (one per step) → ytflow CLI (validate, number, generate files)
  ↓
channels/<channel>/videos/<video>/<step>/v<N>/   (versioned outputs)
  ↓
Creator runs Canva / Google Flow / ElevenLabs with those outputs
  ↓
images + audio back in the video folder → ytflow builds the Kdenlive project
  ↓
Creator renders in Kdenlive → publish step: title, description, tags
```

**Skills for judgment, CLI for determinism.** Writing (style guide, script,
prompts, metadata) belongs in a skill. Anything that must be exact — numbering,
timings, file names, the Kdenlive XML — belongs in tested Python code under
`src/ytflow/`. Settled decisions and their reasons: `PROJECT_CONTEXT.md` →
"Design Decisions"; the build order: `PROJECT_CONTEXT.md` → "Backlog".

## Project Structure

```
src/ytflow/            # the CLI package (entry point: ytflow.cli:main)
tests/                 # pytest suite
.agents/skills/        # agent skills (Codex); mirrored byte for byte in .claude/skills/
.opencode/             # agent prompts, shared instructions, session memory (gitignored)
scripts/               # dev-sandbox helpers (dev-up.py launcher, agent pins, token)
docs/wiki/             # wiki source, published with make wiki-push
channels/              # creator workspace: channel and video outputs (gitignored)
```

## Development Commands

### CLI

```bash
uv sync                      # install the locked environment (.venv)
uv run ytflow --help         # run the CLI
uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format src tests # format
```

### Docker Compose (optional)

```bash
docker compose up            # Start the project — no host prerequisites (any OS)
docker compose down          # Stop services
docker compose logs -f       # View logs
```

`docker compose up` is the demo path and works on Linux, macOS and Windows with
nothing installed but Docker: every host-derived value has an inline default and
the host-only agent mounts live in `docker-compose.agent.yml`, which this command
does not load.

### Dev loop (`dev-up`)

```bash
make dev-up        # start the developer loop — does NOT rebuild
make dev-restart   # dev-down, then dev-up — also does NOT rebuild
make dev-build     # the only rebuild path: after a Dockerfile, entrypoint or
                   # dependency-manifest change
make dev-down      # stop (volumes kept)
```

- `dev-up` ends on the log stream. Ctrl-C stops the logs, not the containers.
- It touches the entrypoint's start marker and re-creates the container, so a
  sandbox that was started earlier through the demo path (`docker compose up`)
  does not stay asleep.
- It never passes `--build`: Compose still builds an image that does not exist,
  so a cold checkout is unaffected, but a cached image is not rebuilt on every
  start. A rebuild belongs to `dev-build`.

### Platforms (Linux / macOS / WSL2 / Windows)

The Makefile targets POSIX hosts. On native Windows, where `make` runs under
`cmd.exe`/PowerShell, use the cross-platform launcher instead — it maps the same
targets onto the same Compose files:

```powershell
python scripts/dev-up.py dev-up      # or: .\scripts\dev-up.ps1 dev-up
```

Rules that differ per platform:

- **Starting the project never requires an agent.** `dev-up` works everywhere;
  the agents are only what the agent targets run.
- **The agents run on every host OS.** opencode, Claude Code and Codex are
  installed in the dev image, so nothing depends on a host install — a macOS or
  Windows host runs `make claude-auto` (or `python scripts/dev-up.py
  claude-auto`) the same way Linux does.
- **Line endings are pinned LF** by `.gitattributes`, because the bind-mounted
  scripts are parsed by bash inside the Linux container. A Windows checkout with
  `core.autocrlf=true` otherwise fails with `/bin/bash^M: bad interpreter`.

### Run All Checks

```bash
make check
```

`make check` runs `uv sync --locked` (fails when `pyproject.toml` and
`uv.lock` disagree, instead of rewriting the lock), `pytest`, `ruff check` and
`ruff format --check`. Every step propagates its exit code. Prefer `check` over
listing commands separately: agents follow whatever `check` runs, so a check
missing from it is a check nobody performs. Add every new check to it.

pytest exits 5 when it collects no tests, and `make check` treats that as a
failure on purpose: a gate that ran nothing is not green.

The project needs no secrets today — it calls no external API — so there is no
`.env.example`. If one is ever added, `make setup` creates `.env` from it the
first time (mode 600) and never overwrites it afterwards.

## Runtime Environment

The AI agent runs at the workspace root — inside the dev sandbox by default, or
on the host. Any of the supported agents works; none of the rules below depend
on which one.

### Agents and terminals

| Agent | Reads | Sandbox target | Auto mode |
|---|---|---|---|
| opencode | `AGENTS.md`, `opencode.json`, `.opencode/` | `make opencode` | `make opencode-auto` — `--auto`; `opencode.json` deny rules still apply |
| Claude Code | `CLAUDE.md` (imports this file and the instructions), `.claude/settings.json` | `make claude` | `make claude-auto` — `--dangerously-skip-permissions`: no prompts, the container is the boundary; `.env` Read/Edit deny rules still apply |
| Codex | `AGENTS.md` | `make codex` | `make codex-auto` — no approval prompts, **and no file deny list** |

- **Every agent follows the same instruction files**, whichever one you run:
  `.opencode/instructions/workflow.md`, `testing.md` and `memory.md`, and the
  skills under `.agents/skills/` (mirrored in `.claude/skills/`). opencode loads them through
  `opencode.json`, Claude Code through the imports in `CLAUDE.md`; any other
  agent must read them at the start of a session. `.opencode/` is where they
  live, not a statement about which agent runs.
- **Sign in once per project.** Each agent asks for its login on first run —
  paste an API key or sign in with an account — and writes it to its own state
  directory, which is a named Docker volume (`docker-compose.yml`). It survives
  `dev-up`, `dev-restart` and `dev-build`; only `make reset` (`down --volumes`)
  signs you out. Nothing is mounted from the host and no key passes through a
  compose variable, so a project's logins are isolated from the host's and from
  every other project's.
- **Codex runs without its own sandbox in the container.** Its sandbox
  (bubblewrap) cannot create a namespace inside an unprivileged container, so
  `make codex` passes `--sandbox danger-full-access` and the container is the
  boundary. `make codex-auto` also skips the approval prompts.
- **The secrets are not in the sandbox.** Codex has no file deny list, so a
  rule cannot stop it reading `.env`; instead `.env` is an empty read-only file
  inside the container (`scripts/masked-env`, mounted in `docker-compose.yml`)
  for every agent in every mode, and `check-secrets` refuses to start the
  sandbox while any other `.env*`/`.envrc` file is in the checkout. A command
  that needs a key runs on the host. `GH_TOKEN` is still forwarded so agents
  can use `gh`; give the sandbox a fine-grained token if that matters.
- **Upgrading an agent is one command**: `make claude-upgrade` (or
  `opencode-upgrade`, `codex-upgrade`, or `agents-upgrade` for all three) looks
  up the vendor's latest release, rewrites the pin in the `Dockerfile`
  (`CLAUDE_CODE_VERSION` and friends), rebuilds, and re-creates a running
  sandbox. Logins are kept. `AGENT_VERSION=X.Y.Z` pins an exact version instead.
  Commit the pin change, so the whole project moves together. `make
  agents-version` shows what the sandbox runs next to the latest releases.
  Drop an agent the project does not use from `SANDBOX_AGENTS`.
- **A stale image is refused, not run.** `dev-up` does not rebuild, so the image
  carries a hash of the files it was built from (`IMAGE_INPUTS`: the Dockerfile
  and every file it COPYs). After an edit, `dev-up` and the agent targets stop
  and name `make dev-build`. Add a file to `IMAGE_INPUTS` (and to the launcher's
  list) when you add a `COPY`.
- **`make doctor`** checks Docker, the image, the GitHub token, the sandbox and
  every agent's login in one go, and names the fix for anything that fails.

Install the GitHub CLI on the host; the sandbox forwards its token.

### What the agent CAN do

- Run `uv`, `python`, `pytest`, `ruff` and `ffmpeg`/`ffprobe`
- Read and write the creator's workspace under `channels/`
- Run git and GitHub CLI commands

### What the agent CANNOT do

- Run `docker` or `docker compose` commands (not available inside the container)
- Access the Docker socket
- Modify the host filesystem (only the workspace is writable)

## Environment Variables

None yet: the CLI calls no external API. If a variable is ever needed, document
it in `.env.example` (committed, placeholders only) and here; `.env` stays
gitignored.

## Key Conventions

- **Assignee**: `fiwon123` — `workflow.md` tells agents to read `ASSIGNEE` from here before assigning issues and PRs
- **GitHub credentials**: `GH_TOKEN` or `GITHUB_TOKEN` — either name works. Do not set either here: values belong in the host environment, and reach a container only through the runtime interpolation in `docker-compose.yml`. `workflow.md` names these variables, so whoever configures the project knows which ones to set.
- **Model assignments**: `opencode.json` assigns `opencode/big-pickle` to `build` and `opencode/mimo-v2.6-flash-free` to `plan`. Change them to whatever your install offers; no prompt depends on which model an agent runs. Verify an id with `opencode models` first: a catalog entry on models.dev does not guarantee your installed build offers it, and an unresolvable id fails at spawn rather than at config load.
- **Repository link**: the README always links to the GitHub repository (`https://github.com/fiwon123/ai-youtube-video-workflow`, from `PROJECT_CONTEXT.md`), so a reader is always one click from the source.
- Linting and formatting: ruff (`pyproject.toml` → `[tool.ruff]`) for `src/`, `tests/` and `scripts/`
- Testing: pytest for `src/ytflow/`; drive the CLI as a process (`python -m ytflow …`), the path the creator's skills take
- CI: GitHub Actions runs lint + test on `dev` → `main` PRs only — never on feature branch PRs or push to `dev`
- Local testing: run `make check` before pushing feature branches
- **Versioned outputs**: a step never overwrites a previous version; it writes `v<N+1>`
- **File naming**: image prompts and image files are `<enumerate_id>_<part_of_phrase>` — a zero-padded id (`001`) and a lowercase hyphenated slug — so they sort into timeline order
- **Creator content stays local**: `channels/` is gitignored. Reference transcripts, scripts, images and audio are the creator's, never committed

## Environment and Secret-File Rules

- The environment file, if one is ever added, is `.env` at the repository root.
- Never access it without explicit permission.
- Never open, read, print, summarize, quote, or send the contents of `.env`, `.env.*`, `.envrc`, or any other environment/secret file unless the user explicitly gives permission in the current conversation. `.env.example` is the one exception: it holds placeholders and is safe to read.
- Read `.env.example` with the **Read tool**, not with `cat`. Bash denies cover every `.env*` path on purpose — see the note below on why the example file is not carved out of them.
- Never run commands that reveal environment values (e.g., `printenv`, `env`, `docker compose exec <service> env`). `docker compose config` looks like harmless inspection but renders the *interpolated* values, keys included, so it is on the deny list for the same reason.
- Never display, repeat, log, store, or include secret values in responses, code changes, or commits.
- To confirm a variable is set, check for presence, never print it:
  `test -n "$VAR_NAME" && echo set`, substituting the variable's real name.

### Enforcement and its limits

`opencode.json` enforces the above at the tool level. The top-level `permission`
block denies `read` and `edit` of `*.env`, `*.env.*`, and `*.envrc` while
allowing `*.env.example`, and denies `bash` commands matching those paths or
dumping the environment (`printenv`, `env`, `docker compose config`, `docker
inspect`, `docker compose exec … env`). Every agent inherits it, and each agent
repeats the deny list locally so the project stays guarded when one file is
edited in isolation.

Treat it as a backstop, not as the permission. The rules match **command
strings and file paths**, not intent, so they have known gaps you must not rely
on your way past:

- An allowed interpreter can still reach a file. `uv run python -c "print(open('.env').read())"`
  matches no deny pattern, because the pattern is matched against the command
  string, not what the command does.
- A repo-wide `grep -rn <SECRET_NAME> .` ignores `.gitignore`, so it will read a
  `.env` that is correctly excluded from version control. Prefer the Grep tool,
  which is gitignore-aware.
- The Grep **tool** has its own `permission.grep` namespace whose patterns match
  the search regex, not the file path, so a `*.env` deny cannot cover it. What
  protects it is `.gitignore` listing `.env` and `.envrc`. Keep those lines.

Two consequences of last-match-wins to understand before you edit these lists, so
you do not "tidy" them away:

- Rules resolve **last match wins**, and agent-level rules take precedence over
  global ones. A broad allow placed *after* a narrow deny silently reinstates the
  leak — so every agent that allows `grep *` also denies `grep *.env`,
  `grep *.env.*`, and `grep *.envrc` explicitly, positioned after the allow.
- A `bash` pattern matches the **whole command string**, and one command can name
  several files. So there is no way to allow `.env.example` while denying `.env`
  in the same namespace — `cat .env .env.example` would match an example allow
  and print the secret. That is why the example file is carved out of `read` and
  `edit`, which match one path per call, but not out of `bash`.

If the user explicitly permits reading environment configuration:

1. Read only non-secret variables.
2. Do not read or reveal variables whose names contain: `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASS`, `CREDENTIAL`, `AUTH`, `PRIVATE`, `CERT`, `COOKIE`, `WEBHOOK`, `DATABASE_URL`, `CONNECTION_STRING`.
3. Do not reveal the values of ambiguous variables. Ask for permission before reading them.
4. You may read safe configuration variables such as: `NODE_ENV`, `ENVIRONMENT`, `PORT`, `HOST`, `API_URL`, `DEBUG`.
5. If a file contains both safe and secret variables, read only the explicitly approved safe variables.
6. Never include secret values in the final answer. Refer to them only by variable name.
7. Prefer checking whether a variable exists rather than printing its value.

## Development Workflow

### Git Workflow

- Branch from `dev` (not `main`)
- Never push directly to `dev` or `main`
- Branch naming: `<type>/<issue-number>-<slug>` (e.g., `feat/42-skill-timeout`)
- Branch types: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `ci/`
- Use conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `ci:`
- All testing is local for feature branches — CI only runs on `dev` → `main` PRs
- Do NOT merge pull requests unless explicitly instructed
- Do NOT automatically create release PRs or merge to main — user must explicitly request
- Always return to `dev` branch after completing any merge
- Every change is tracked on GitHub: **issue → branch → PR → merge**

### Linking

- Every branch includes the issue number: `feat/42-skill-timeout`
- Every PR references its issue: `Closes #<number>`
- Every issue is assigned to a milestone before work begins
- Every PR is assigned to a milestone when created
- No orphaned branches, PRs, or issues

### Branch Strategy

```text
main          ← release merges (CI runs here — dev→main PRs only)
  └── dev     ← integration branch (all feature branches merge here)
        ├── feat/42-skill-timeout
        ├── fix/17-voice-error
        └── refactor/31-schema-validation
```

- Feature branches: `feat/<issue>-<slug>` → merge to `dev`
- Release: `dev` → `main` (PR triggers CI — user must explicitly request)
- Hotfixes: `fix/<issue>-<slug>` → merge to `dev`, cherry-pick to `main` if urgent

### Branch gate

`branch-gate.yml` fails a pull request whose branch does not follow the model
above, so the author finds out before a reviewer does. It is a
**guard rail, not a lock**: an administrator can override a failed required
check, and a check nobody blocks on is noise. Branch protection (below) is the
control; the gate is the feedback.

### Repository settings (configure by hand)

These live in the repository settings, not in a file, so no template can set
them for you. Configure them once when the project is created, and re-check
them whenever the repository is transferred.

**Branch protection** (Settings → Branches → Rules):

- `dev`: require a pull request, and require the **Branch gate** check. Do
  *not* require the CI check here — CI runs on release pull requests only, so
  a required check that never runs leaves every pull request waiting forever.
- `main`: require a pull request, and require both the **CI (Python)** check
  and the **Branch gate**. Do not allow deletions: `dev` is the head of the release
  pull request, so deleting it with `--delete-branch` breaks every future
  pull request's base.
- Leave "Allow force pushes" and "Allow deletions" off on both branches.

**Other settings worth turning on:**

- Secret scanning and push protection (Settings → Code security). A pushed
  token stays in the history even after it is deleted.
- Tag protection for `v*`, so a published release tag cannot be moved.
- Dependabot targeting `dev` — see `.github/dependabot.yml`.

**Licensing:** `LICENSE` is **proprietary — all rights reserved** on purpose:
the project starts closed, and the maintainer opens it when there is a stable
release worth publishing. To open-source it, replace `LICENSE` with the MIT
text, update the README badge, and commit that change on its own.

### Milestones

- Every issue MUST be assigned to a milestone before work begins
- Milestones represent releases or sprint iterations
- Use `gh issue edit <number> --milestone "<milestone-name>"`
- Track milestone progress on the GitHub Milestones page

### Project board

- Use GitHub Projects (classic or Projects v2) to visualize work across the board (Backlog → Todo → In Progress → Review → Done).
- **Issues are the source of truth; the board is a view of them.**
- Link issues and PRs to the project board; keep cards moving with the workflow steps above.
- Use board fields/statuses to reflect `issue → branch → PR → merge` state rather than duplicating it in comments.
- For automation, prefer built-in workflows or `gh project` commands — document any project-specific board in `PROJECT_CONTEXT.md`.

### Agents

Agent definitions live in `opencode.json` and `.opencode/agents/`:

- **build** (primary): Full development work with all tools enabled
- **plan** (primary): Analysis and planning without making changes — restricted to read-only subagents (explore, reviewer only)
- **reviewer** (subagent): Reviews code for bugs, security, and regressions
- **visual** (`mode: all`): Read-only image inspection — frames extracted from a rendered video, contact sheets. It checks what a test cannot: is the subtitle readable on its box, does the chapter title sit in the top-left, does the camera motion look professional
- **tester** (subagent): Writes and runs the pytest suite — edit scoped to test files, config, and fixtures

Each agent's instructions live in exactly one place: the body of
`.opencode/agents/<name>.md`. Model, mode, and permissions live in
`opencode.json`. Do not add a `prompt` key to `opencode.json` — it creates a
second prompt source that drifts from the markdown and leaves it undefined which
one wins.

An agent named in `opencode.json` without a matching markdown file has no
instructions at all. If you add an agent, add its `.md` in the same commit.

Subagent permissions must match what the markdown tells the agent to do. If
`plan.md` lists `reviewer` but `task` denies it, the agent is instructed to use a
tool it cannot reach; keep the two in sync.

### Skills

- Load relevant skills when working on specific domains (e.g., GitHub workflow)
- **The product is skills too.** Each workflow step (branding, style references, script, image prompts, voiceover, edit, publish) ships as a skill under `.agents/skills/<step>/SKILL.md`, copied byte for byte to `.claude/skills/<step>/SKILL.md`. A skill does the writing and calls `ytflow` for anything that must be exact
- `github-workflow` ships in `.agents/skills/github-workflow/SKILL.md` (Codex) and, byte for byte, `.claude/skills/github-workflow/SKILL.md` (Claude Code and opencode) — edit the first, copy it to the second — the command cookbook for git, issues, and PRs. `workflow.md` remains the policy authority; the skill is the quick reference.

### Session Memory (4-tier)

- At the START of every new chat: read `.opencode/memory/global.md` then
  `.opencode/memory/current.md` and resume from "Next action" — this is how
  long-running work survives between sessions. If the state references an
  issue/branch/PR, continue that work unless the user says otherwise.
- At meaningful milestones (issue created, branch renamed, code done, tests
  run, PR opened, merged) update `global.md`; update `current.md` after each
  step and at session end rotate the oldest archive out so only 3 remain.
- Durable, reusable lessons (a footgun, the command that works, a decision's
  rationale) go to `lessons.md`; offload them there when `global.md` approaches
  its cap rather than letting tracked work and lessons share one file.
- Keep sizes bounded: `global.md` ≤ ~200 lines, `lessons.md` ≤ ~100 lines,
  `current.md` ≤ ~100 lines, archive files ≤ ~50 lines each; never store
  secrets/tokens/credentials.
- The whole `.opencode/memory/` directory is gitignored and must never be
  committed. Full rules: `.opencode/instructions/memory.md`.

### Rules for Agents

All workflow rules that agents must follow are documented in this file. When configuring a project, ensure AGENTS.md contains:

- branch strategy and naming conventions;
- CI strategy (which PRs trigger CI, local testing requirements);
- milestone and issue conventions;
- development commands (test, lint, build, format);
- environment and secret-file rules;
- any project-specific constraints or permissions.

### CI triggers (read this before claiming a change is verified)

CI runs on release PRs (`dev` → `main`) and manual dispatch — never on a
feature-branch push. Two things can make a run verify nothing:

- a `paths:` filter that the change does not touch means the workflow does not
  trigger at all; and
- a job gated behind a label or `if:` condition comes back `skipped`, not
  `passed`.

**Skipped is not passed.** A triggered run whose jobs were all gated out, or a
run that never happened, is not coverage. Do not describe a change as "CI
passed" unless a run actually executed the job that covers it; if it did not,
say the change is unverified and test it locally.

The same rule applies locally: a test runner reporting `[no test files]` — or
`0 tests collected` — for a package is **not** a pass for that package. It was
compiled, not exercised. Say which packages ran nothing rather than describing
the suite as green.
