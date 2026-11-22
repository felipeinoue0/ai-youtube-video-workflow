---
name: script
description: Write a YouTube video's script in the channel's style — outline first, then one phrase per line grouped into chapters — and build the timed script (script.json) that names every phrase <enumerate_id>_<part_of_phrase> for images, narration and the edit. Use when starting a video or revising its script.
---

# Script

Per-video step 1 of the ai-youtube-video-workflow. The script is the backbone
of the video: each phrase becomes one subtitle and one background image, and
its `<enumerate_id>_<part_of_phrase>` name ties together the image prompt, the
image file and the timeline. You write; `ytflow script build` checks the script
against the channel kit, numbers the phrases and estimates the timing.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH).

## 0. Where are we

```bash
ytflow status <channel> <video>        # no video yet? ytflow video new <channel> <video>
ytflow kit path <channel> <video>      # the kit this video uses
```

Read, before writing a word:

- `style-guide.md` in that kit: the front matter (pace, phrase length) and every
  rule. This is the channel's voice; follow it over your own habits.
- `branding/<latest>/brief.md`: the audience and the promise.
- The scripts of the channel's **earlier videos**
  (`channels/<channel>/videos/*/script/`, latest version of each): keep the
  same voice, do not repeat their hooks or examples, and reuse recurring
  elements the way they did.

If `ytflow status` says the style guide is not filled, stop and suggest the
style skill.

## 1. Video brief

Ask in one message:

1. Topic and **angle**: the one question the video answers.
2. Target length in minutes (target words = minutes × `words_per_minute`).
3. Facts, sources or notes the creator already has.
4. Points that must be included, and points to leave out.
5. Anything for the ending: the next video, a link, a question to the viewers.

## 2. Outline first

```bash
ytflow version new channels/<channel>/videos/<video>/script
```

In that directory, write `outline.md`:

- the hook in 2–3 sentences;
- each chapter: title (≤ 40 characters), its purpose in one line, and its target
  length in seconds;
- the ending.

Follow the style guide's structure. YouTube shows chapters only when there are
**at least 3**, each **at least 10 seconds** long. Show the outline to the
creator and get a yes before writing the script; changing an outline costs
nothing.

## 3. Write `script.md`

In the same version directory:

```markdown
# Working title

> Notes for the creator: lines starting with ">" are not part of the video.
> check: the date of the coin reform (verify before recording)

## Chapter title
- One phrase per line.
- Each phrase is one subtitle and one background image.
```

Rules:

- **One phrase per line**, starting with `- `. A phrase stays within
  `phrase_words_max` words and averages about `phrase_words_target`. Split a
  long sentence into several phrases at natural pauses.
- **Every phrase must be picturable.** It becomes one image, so give it
  something to show: a place, an object, a person, an action. When a phrase is
  abstract, either attach it to a concrete image or merge it with a neighbor.
- **Write for the ear.** Read it aloud in your head: short words, active voice,
  no parentheses, no "see above". Spell out what is said differently from how
  it is written (abbreviations, symbols, units).
- **Chapter titles** are short and specific (≤ 40 characters). They show in the
  top-left corner and become the YouTube chapters.
- **Facts**: anything you are not sure of gets a `> check:` note just above it.
  Never invent quotes, numbers or sources. The creator verifies every
  `> check:` before recording.
- Never reuse sentences from the reference transcripts.

## 4. Build

```bash
ytflow script build <channel> <video>
```

- **Problems** (exit 1, no `script.json` written): fix each line it names, then
  build again.
- **Warnings** about YouTube chapters: lengthen or merge the chapters it names,
  unless the creator decides otherwise.
- It prints the chapter timestamps, the average words per phrase and the
  estimated length. Compare the length with the target from step 1. If it is
  off by more than ~10%, cut or add phrases, not words per phrase.

The timing is an estimate from the kit's pace; the alignment step replaces it
with the real narration times later.

## 5. Review, then show

Go through the style guide's review checklist yourself and fix what fails.
Then show the creator:

- the script (title, chapters, phrases);
- the chapter timestamps and the estimated length, as `ytflow` printed them;
- every `> check:` note, so they can verify it.

## 6. Iterate

```bash
ytflow version new --copy channels/<channel>/videos/<video>/script
```

Edit the new version, run `ytflow script build <channel> <video>` again, and
tell the creator which version is current. Never edit an older version.

**Approve the script before any images are made.** Phrase names come from the
phrase order and wording, so a script change after the images exist renames
them. If that happens anyway, say so clearly; the image-prompt step reports
which images no longer match.

## Done when

- `ytflow script build <channel> <video>` prints `ok`
- every `> check:` note has been resolved by the creator
- the creator approved the script

Then run `ytflow status <channel> <video>`. Next comes the image-prompt step.
