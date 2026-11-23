---
name: publish
description: Write a finished video's YouTube title, description (from the channel's template, with chapter timestamps from the timeline) and tags, check them against YouTube's limits, and guide the creator through the upload with captions. Use after the edit is rendered, or when the title, description or tags need changing.
---

# Publish

Per-video step 5, the last one in the ai-youtube-video-workflow. You write the
words that sell the video — title options and a summary — in the channel's
tone. `ytflow` fills the channel's description template from the kit's
`publish.md`, adds the chapter list from the timeline, merges the tags and
checks YouTube's limits, so every video's description has the same shape.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH).

## 0. Where are we

```bash
ytflow status <channel> <video>
```

You need a built timeline (`timeline.json`): the chapter times come from it.
Build publish from the timeline the creator actually rendered.

Read, before writing:

- the kit's `publish.md` (`ytflow kit path <channel> <video>`): the template
  and the base tags;
- the kit's `style-guide.md`: the hook and the tone;
- the video's `script.md` (latest script version): what the video promises.

## 1. Start a publish version

```bash
ytflow publish init <channel> <video>    # prints .../publish/v<N>/publish.md
```

It starts from the previous version's title, summary and tags, if there is one.

## 2. Title

Write **5 title options** as `>` lines under the title, different in angle:
a question, a bold claim, a number, a "how", a mystery. For each:

- under 70 characters (YouTube allows 100, but cuts it off in search near 70);
- the most searched words early;
- it promises what the video delivers, no more: the hook of the script, not a
  twist the video does not have;
- the channel's tone; no all-caps words, no emoji unless the channel uses them.

The creator picks one (or edits it). Put the chosen one on the `# ` line,
replacing the TODO. Keep the options as `>` notes; they are ignored.

## 3. Summary

Two or three sentences under `## Summary`: the first ~150 characters show
above "more", so the first sentence carries the promise and the main search
words. Plain text; YouTube rejects `<` and `>`.

### Other parts of the description

The kit's template may have more slots than `{summary}` and `{chapters}`:
`{ferramentas}`, `{pergunta}`, `{continue_assistindo}`, `{recursos}`,
`{hashtags}`… Each is filled by the section of the same name in `publish.md`
(`## Continue assistindo` fills `{continue_assistindo}`: lowercase, accents
dropped, spaces as `_`), with its line breaks kept. Fill every one: a slot
without its section stops the build, and a section the template does not use
is left out with a warning. The summary keeps its paragraphs (blank line
between them).

Typical parts, and how to fill them:

- **Tools shown in the video**: one per line, `Name: official link`. Check
  each link opens the tool's own site; the creator swaps in an affiliate link
  where they have one.
- **Question**: one question tied to the video, to open the comments.
- **Continue watching**: the creator's previous video or playlist, title and
  link (ask them).
- **Resources**: only what helps with this video's topic, each with one line
  on what it is for; never an income promise. Keep the affiliate notice the
  template has.
- **Hashtags**: two or three for the topic (the first three show above the
  title).

## 4. Tags

Under `## Tags`, 5–12 tags for **this** video only (one `- ` per line): the
subject, names, places, the period, and two or three phrasings a viewer would
search. The kit's base tags are added first; duplicates (ignoring case and
spaces) are dropped.

## 5. Build

```bash
ytflow publish build <channel> <video>
```

On problems it prints them and writes nothing: fix `publish.md` and run it
again. When it is ok, the version holds:

- `title.txt`, `description.txt`, `tags.txt` — paste these into YouTube Studio;
- `captions.srt` — the subtitles, timed to the video (the lead-in included);
- `publish.json` — all of it, with the timeline and kit versions used.

Warnings to act on:

- `chapter ... is Ns; YouTube needs 10s`, or fewer than 3 chapters — YouTube
  would not show the chapters, so the list (and a label line just above it,
  like `Chapters:`) is left out. Fine for a short video; for a long one, merge
  the short chapter into its neighbour in the script.
- `title is N characters; past 70 it is cut off` — offer a shorter option.
- `made from timeline vN, but vM exists` — the description's chapter times are
  from an older edit; run `ytflow publish init` again.

Show the creator `description.txt` as it will appear.

## 6. Upload (the creator, in YouTube Studio)

1. Upload the video rendered from Kdenlive.
2. Paste `title.txt`, `description.txt`, and `tags.txt` (under "Show more").
3. Thumbnail: a frame or an image made in Canva with the channel's branding.
4. Captions (the creator decides): the video already shows its subtitles.
   Uploading `captions.srt` (Subtitles → Add language → Upload file → With
   timing) helps search and auto-translation, but a viewer who turns on CC
   sees the text twice.
5. Check that the chapters appear on the progress bar after processing.

## Rules

- Never change `publish.md` in the kit to suit one video; the template is the
  channel's. A change for every video goes through `ytflow kit edit`.
- Never promise in the title or summary what the video does not show.
