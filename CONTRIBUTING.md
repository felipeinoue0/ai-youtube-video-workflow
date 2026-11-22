# Contributing

Thanks for wanting to help with ai-youtube-video-workflow.

## Report an issue

Open an [issue](https://github.com/fiwon123/ai-youtube-video-workflow/issues/new) with:

- **the version** — `uv run ytflow --version`
- **the platform** — OS, runtime version
- **what you expected, and what happened** — include logs/stack traces if relevant
- **steps to reproduce** — a minimal sequence that hits it

## Discuss

- **Issues** are for bugs and concrete proposals.
- **Discussions** are for questions, ideas not yet a plan, and "would this be useful?".

## Help without writing code

Running the app and reporting exactly what happened — including "it worked" —
turns an unproven claim into a proven one. See the "What is not proven"
section in the README and the wiki for open verification tasks.

## Send code

- Open an issue first, so the change and the reason are recorded together.
- Branch from `dev` as `<type>/<issue>-<slug>` (`fix/42-scan-timeout`), and use
  conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`).
- Run `make check` before pushing.
- One feature per pull request. Say in the body what ran and what did not, and
  do not describe a skipped check as a pass.
- Follow `AGENTS.md` for the full workflow rules.

## About the AI

If this project is developed with an AI agent, the review bar is the same: judge
by tests and evidence, not by who wrote it. Say what was verified and what was
not.
