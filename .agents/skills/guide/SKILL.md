---
name: guide
description: The entry point of the ai-youtube-video-workflow. Finds where a channel or video stands with `ytflow status` and hands over to the skill for the next step — branding, style, script, image-prompts, voiceover, edit or publish. Use when the creator starts, returns after a break, asks "what's next?", or starts another video.
---

# Guide

The workflow takes a creator from an empty folder to a Kdenlive project and the
words to publish it with, one reviewable step at a time. You do not do the
steps here: you find the next one and load its skill. `ytflow status` is the
single source of truth for where things stand: read it, never guess from
memory.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH). The workspace is `channels/` there (or `--root` / `YTFLOW_ROOT`).

## 1. Which channel and video

```bash
ls channels/ 2>/dev/null                 # existing channels
ls channels/<channel>/videos/ 2>/dev/null # its videos
```

- **No channel yet**: ask for a short lowercase name (letters, digits, `-`),
  then `ytflow channel new <channel>`.
- **One channel**: use it. Several: ask which.
- **A video**: ask whether the creator continues one (name it) or starts a new
  one; for a new one, a short lowercase name for the topic, then
  `ytflow video new <channel> <video>`.

## 2. Ask status

```bash
ytflow status <channel>            # channel setup only
ytflow status <channel> <video>    # channel and the video
```

Show the creator the table, in a sentence: what is done, what comes next. The
last line is the next action:

```text
next: <what to do> (skill: <name>)
```

## 3. Hand over

Load the skill named in brackets and follow it. The order, and what each
needs from the creator:

| Step | Skill | Creator brings | Done when |
|---|---|---|---|
| Channel, once | `branding` | answers to a short interview; logo and banner made in Canva | `ytflow branding check` ok; `publish.md` filled |
| Channel, once | `style` | 2–5 transcripts of videos they like | `style-guide.md`, `visual-style.md` pass `ytflow kit check` |
| Video | `script` | the topic; approval of the outline and script | `script.json` built |
| Video | `image-prompts` | the images, generated in Google Flow | `ytflow images check` ok |
| Video | `voiceover` | the voice choice (first video); the audio from ElevenLabs | `ytflow audio check` ok, then `ytflow align` |
| Video | `edit` | approval of the preview; the render from Kdenlive | `timeline.json` built, project exported |
| Video | `publish` | the chosen title | `ytflow publish build` ok |

When the script, the prompts and the narration text are ready, `ytflow
package <channel> <video>` puts the timed script, the ElevenLabs text, the
Flow prompts and the scene list in one folder, `package/v<N>/`: the place to
send the creator to.

`fill <file> in kit v<N> (skill: <name>)` means a channel-kit file that step
needs is still a template: that skill fills it as part of its step.
`voice.md` and `edit-preset.toml` are filled during the **first** video only.

When a skill finishes, run `ytflow status` again and hand over to the next one.
`next: done` means the video is ready to upload: the creator renders in
Kdenlive and uses the publish files.

## 4. Video 2, 3, 4…

Every video reads the **channel kit** its `video.toml` pins: style guide,
visual anchor, voice, edit preset, publish template. That is what makes video
2 look, sound and read like video 1. So for the next video:

- `ytflow video new <channel> <video>` pins the latest kit; status goes
  straight to the script — nothing to set up again.
- Never change a kit file to suit one video. If the creator wants a change for
  the channel from now on, the step's skill runs `ytflow kit edit`, which starts
  a new kit version when other videos use the current one; finished videos keep
  theirs. `ytflow kit path <channel> <video>` shows which kit a video uses.

## Coming back to a version

Each step writes versions (`<step>/v1`, `v2`, …) and never overwrites one. If
the creator wants to redo a step, its skill starts a new version; later steps
built from the old one warn that they are out of date (for example
`made from script v1, but v2 exists`). Redo the steps after it in order:
status shows which.

## Rules

- Trust `ytflow status`, not the conversation, for what is done.
- One step at a time, with the creator's review in between; do not run ahead
  through several steps on your own.
- Creator content stays in `channels/`, which is never committed.
