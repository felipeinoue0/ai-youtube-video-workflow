---
name: edit
description: Turn the aligned narration, the images and the channel's edit preset into the video's edit — timeline.json, subtitles, an ffmpeg preview and a Kdenlive project — and guide the creator through reviewing it and rendering in Kdenlive. Use after `ytflow align`, or when the edit, subtitles or transitions need changing.
---

# Edit

Per-video step 4 of the ai-youtube-video-workflow. Every decision in the edit
comes from the channel kit's `edit-preset.toml`, so video 2, 3, 4 are cut like
video 1: one image per phrase, cut where the phrase is spoken; a transition on
every cut (calm at chapter changes, varied inside a chapter); a slow pan or
zoom on every image; subtitles on a box; the chapter title top-left; a fade in
and out.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH).

## 0. Where are we

```bash
ytflow status <channel> <video>
```

You need `timing.json` (`ytflow align`) and every image
(`ytflow images check` ends with ok). If status says `fill edit-preset.toml in kit v<N>`, this
is the channel's first video: do step 1. Otherwise go to step 2.

## 1. Review the edit preset (first video only)

```bash
ytflow kit edit <channel> <video> --file edit-preset.toml   # prints the kit directory
```

Walk the creator through the defaults, one section at a time, and change only
what they ask for:

- `[subtitles]` — font, size and box opacity. 48 px on 1080p with a 60% black
  box reads on bright and dark images; raise the opacity if the images are busy.
  `max_chars_per_line` 42 and `max_lines` 2 are the usual readability limits.
- `[chapters]` — how long the title shows (`seconds`) and its margin.
- `[video]` — size, frame rate, fade lengths.
- `[audio]` — `lead_seconds` of image before the narration, `tail_seconds`
  after it.
- `[transitions]` — `types`: the **first** is the calm one used at chapter
  changes and every other cut; the others take turns in between. Known types:
  dissolve, wipe-left/right/up/down, slide-left/right/up/down.
- `[camera]` — `moves` taken in turn (zoom-in, zoom-out, pan-left/right/up/
  down); `max_zoom` and `zoom_per_second` keep the motion slow.

Delete the `TODO(ytflow)` line, then:

```bash
ytflow kit check <channel> <video> --file edit-preset.toml
```

## 2. Build the timeline

```bash
ytflow timeline build <channel> <video>
```

It writes `timeline/v<N>/timeline.json` and `subtitles.ass` and prints the
clip count, length, chapter titles and the transition mix. Each run is a new
version. Act on its warnings:

- `N subtitle lines` — the phrase is too long for the screen: split it in the
  script (then script build, voiceover text, audio for that chapter, align).
- `characters per second is fast to read` — the voice is fast there; a
  shorter phrase or a slower `speed` in `voice.md` helps.
- `timed from script vN, but vM exists` — the narration is older than the
  script; regenerate it first.

## 3. Preview

```bash
ytflow timeline preview <channel> <video>            # half size, quicker
ytflow timeline preview <channel> <video> --scale 1  # full size
```

The creator watches `timeline/v<N>/preview.mp4` and checks: subtitles readable
on the brightest and darkest images, chapter titles not covering anything
important, no image that clashes with its phrase, motion slow and calm. If an
image is wrong, regenerate it in Google Flow under the same name and build
again. The preview uses the same `subtitles.ass` as the project, so the text
looks the same in Kdenlive.

## 4. Export to Kdenlive

```bash
ytflow export kdenlive <channel> <video> --host-root <workspace on the creator's machine>
```

It writes `timeline/v<N>/<video>.kdenlive` in Kdenlive's own 1.1 layout
(modeled on a project saved by Kdenlive 26.08) and, next to it,
`<video>.kdenlive.ass`, the subtitle file Kdenlive expects.

`--host-root` (or `YTFLOW_HOST_ROOT`) is where the workspace root is on the
machine that runs Kdenlive — Kdenlive saves absolute paths, and its subtitle
list needs one. When the agent runs in a container, the workspace is mounted
from that folder; ask the creator if you cannot tell. Without it, paths are
relative to the project file.

Tell the creator to open that file in Kdenlive. What they will find:

- one sequence, named after the video, with **Narração** (A1) and two image
  tracks, **Imagens 1 · dissoluções** and **Imagens 2 · dissoluções**: the
  images alternate between them, and each dissolve is the upper image fading
  its transparency in and out over the lower one (clip effects, no transition
  compositions);
- each image has a **Transform** effect with two keyframes: the pan or zoom;
- the first image fades from black, the last fades to black;
- the **subtitle track**: subtitles and chapter titles;
- a **guide** at the start of each chapter.

Kdenlive transitions are dissolves only: a preset with wipes or slides is
exported with dissolves, and the export says so. Keep the preset's `types` to
`["dissolve"]` so the preview shows the same.

The project file is generated: changes the creator makes in Kdenlive are theirs
to keep, but a new `ytflow export kdenlive` writes a new file in the latest
timeline version and does not carry them over. Make content changes (script,
images, preset) before exporting; polish in Kdenlive last.

## 5. Render

In Kdenlive: Project → Render, a YouTube-friendly preset (H.264/AAC MP4 at the
project's size and frame rate), and render to the video folder. Then:

```bash
ytflow status <channel> <video>
```

Next is publishing: title, description with chapters, tags.

## Rules

- Never hand-edit `timeline.json` or the `.kdenlive` file to change the edit.
  Change the preset (for the channel) or the script and images (for the video)
  and build again, so the next video gets the same treatment.
- A preset change made for one video is a channel decision: `ytflow kit edit`
  starts a new kit version when other videos use the current one.
