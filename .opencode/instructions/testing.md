## Testing Requirements

### General

- Tests are mandatory for new features and bug fixes
- Write tests before or alongside implementation
- Mock external services when possible — never call third-party production APIs in tests
- A *local* service the project starts itself (Postgres, Redis via compose) is not a third-party API — start it and let an integration suite use it
- Aim for critical path coverage, not 100% line coverage

### Gates and baselines

A gate is only worth having if it can fail.

- **Do not fix pre-existing failures inside an unrelated PR.** If the suite (or
  `make check`) is already red when you start, your change is not the cause and
  the fix is not the change you set out to make. Say so, and either fix it
  forward on its own issue/branch or record it as a baseline below. Bundling an
  unrelated repair into your PR makes "is my change correct?" unanswerable from
  the diff.
- **Record a known-failing baseline.** When you inherit a red suite, write down
  which tests fail and why (a tracked issue, a TODO, the failing assertion) so
  the next person does not re-investigate the same failures. A baseline turns
  "the suite is red, I don't know why" into "these N are known-red".
- **A gate that cannot fail is worse than no gate.** A test target that collects
  zero tests, a CI job that always skips, or an assertion with no possible
  failure manufactures false confidence: it reads green and proves nothing. If a
  gate reports success without executing anything, treat it as **unverified**,
  not as passed — a skipped run is not a passed run.
- **A package with no tests is not a covered package.** A runner that prints
  `[no test files]` or `0 tests collected` for a package only compiled it. A
  green run that lists such packages is green for the packages that ran; say
  which ones did not.

### Proving a change

Learned the hard way across several projects built from this workflow; each
rule below is a defect that shipped at least once.

- **Reproduce the premise before implementing.** An issue's claim ("format X
  has a header", "tool Y supports platform Z") can be wrong. Check it first —
  a throwaway test or command — and say on the issue what you found.
- **Put the bug back.** A new regression test is only proven when it fails
  with the fix reverted and passes with it restored. A test written after the
  fix and never seen failing may be testing nothing.
- **Test through the path the user takes.** A test that calls a handler or
  widget method directly proves the handler, not the wiring: it passes when the
  click, route or flag that should reach it is broken. Drive the real entry
  point (the event, the HTTP route, the CLI through a pty).
- **A fake proves rules, not schema.** An in-memory repository cannot see SQL,
  a column the struct cannot hold, or a missing migration. Pair it with a test
  against the real database (see "Destructive tests must assert the target
  database").
- **Prove build-time behaviour on the artifact.** A linker flag that names a
  missing symbol (`-X pkg.Var=…`), an embedded resource, a version stamp — a unit
  test cannot see any of them. Inspect the built binary (`go version -m`,
  `--version`, the archive listing).
- **A test's completion signal must be the last thing the work does.** Waiting
  on a flag the work clears *before* it finishes lets the test tear down under a
  goroutine that is still running, and the failure is reported against the next
  test.
- **A workflow edit is unverified until a run executes it.** A feature PR never
  parses a workflow that triggers only on release PRs or tags. Lint it
  (`actionlint`) and dispatch it (`workflow_dispatch`) before calling it done.
  GitHub dispatches only a workflow that is already on the default branch, so
  a *new* workflow cannot be dispatched before its first release: run its
  steps locally, and say the first real run is the release PR.
- **Say what you checked.** "The port answers" is not "the service can use this
  database"; "it builds" is not "it runs". State the exact command and what it
  showed, and name what you did not check.
- **Grep for the old wording after a fix.** A comment or doc describing the old
  behaviour outlives the code; no compiler or test reads prose.

### Prerequisites / Services

None. The suite needs no running service and no network: the CLI calls no
external API. Tests that probe media need `ffmpeg`/`ffprobe` on the PATH (it is
in the dev image); such a test must fail with a clear message when it is
missing, not skip silently.

### Python (`src/ytflow/`)

- **Framework**: pytest
- **Location**: `tests/`
- **Run**: `uv run pytest` (or `make check` for everything)

#### Test Structure

```
tests/
├── conftest.py          # Shared fixtures (add when the first one is shared)
├── test_<module>.py     # Module-specific tests
```

#### Conventions

- Test files: `test_<module>.py`
- Test functions: `test_<description>`
- Use fixtures from `conftest.py`; write workspace files under pytest's `tmp_path`, never under the real `channels/`
- Drive the CLI as a process (`python -m ytflow …`) for behaviour a skill relies on — that is the path the creator takes
- Generated files (the timed script, the prompt list, the ElevenLabs text, the Kdenlive XML) are tested by **parsing what was written**: the XML elements, the timings, the file names and their order

### Linting

```bash
uv run ruff check .
uv run ruff format --check src tests
```

### Before Committing

1. Run `make check` — locked install, tests, lint, format
2. For a change to the generated video project, run the visual check below
3. Verify no regressions

## Visual checks

Numbers are not enough to tell you a video is right. The Kdenlive XML can be
valid, every timing test green, and the rendered video still wrong — a subtitle
unreadable against a bright image, a chapter title clipped at the top-left, a
transition that jumps, a camera move that is too fast to look professional.

Looking is a real step, but the main agent may have no image input at all, so
delegate it to the **`visual` subagent**. The rule is: **the main agent
captures, the `visual` subagent looks, the main agent acts on the findings.**
Never report a visual conclusion the `visual` subagent has not actually
returned; if a review fails or is rate-limited, say the state is unverified and
retry in a smaller batch rather than carrying the claim forward.

### What to capture

Render a short sample with fixture images and audio (a few seconds per image is
enough), then extract frames with ffmpeg:

- **Static checks** (subtitle box, chapter title position, text size): one
  frame from the middle of a few images.
- **Motion** (transitions, fades, camera moves): a GIF of the sequence, or a
  contact sheet of frames at a fixed interval. The Read tool renders images and
  GIFs, not video, so motion recorded only as video is unreviewable. One GIF is
  one attachment — the difference between a review that completes and one cut
  off by a rate limit.

### Cadence: targeted while you work, full once at the end

| When | What |
|---|---|
| **While you work** | Targeted: only the effect you changed, on a short sample. |
| **Before the PR** | One full sample render covering every effect: subtitle box, chapter titles, fade in/out, each transition type, each camera move. |

If a targeted capture shows a problem, fix it and re-capture **the same
targeted set**.

### Rules

- **Check on a bright and a dark background.** A subtitle box verified only on
  a dark image is unverified.
- **Re-capture after fixing.** A fix is not verified until it has been looked at again.
- Report what you *see*. If you have not looked, say so.
- Capture files are throwaway: write them under a temporary directory, never commit them.
