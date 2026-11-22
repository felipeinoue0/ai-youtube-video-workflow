---
name: voiceover
description: Choose and record the channel's ElevenLabs voice in the kit, export the video's narration text (chapter pauses, pronunciation spellings), and guide the creator through generating the audio in ElevenLabs and saving it where the edit step finds it. Use after the script is approved, or when the narration audio is missing or wrong.
---

# Voiceover

Per-video step 3 of the ai-youtube-video-workflow. The script becomes the
narration: `ytflow` exports the exact text to paste into ElevenLabs, with the
kit's voice settings beside it, and checks the audio the creator brings back.
The **same voice and settings** on every video is what makes video 2, 3, 4
sound like video 1, so they live in the channel kit (`voice.md`), not in the
video.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH).

## 0. Where are we

```bash
ytflow status <channel> <video>
```

You need a built and **approved** script (`script.json`). Narration made from
a script that later changes has to be generated again, so finish the script
first. Images can be generated before or after this step.

If status says `fill voice.md in kit v<N>`, this is the channel's first video:
do step 1. Otherwise the voice is settled: skip to step 2.

## 1. Choose the voice (first video only)

Get the path to write to:

```bash
ytflow kit edit <channel> <video> --file voice.md   # prints the kit directory
```

Then, with the creator:

1. **Pick the voice.** Read the style guide's tone section, then suggest two
   or three voices from the ElevenLabs Voice Library that fit it (gender, age,
   accent, energy). The creator listens. Have them generate the **same three
   phrases** of the script with each candidate: the hook, a phrase with a
   name or number, and a chapter's last line. Comparing different text hides
   the difference between voices.
2. **Settle the settings** on the chosen voice, the same three phrases again:
   - *Stability* — lower is more expressive and less predictable; documentary
     narration usually sits around 0.4–0.6.
   - *Similarity* — how closely it keeps to the original voice; 0.7–0.8.
   - *Style* — exaggeration; keep it at 0 unless the voice sounds flat, since
     it makes takes less consistent.
   - *Speed* — 0.7–1.2. Match the kit's `words_per_minute` (the script's
     timing estimates assume it).
   - *Model* — `eleven_multilingual_v2` is the safe default. `eleven_v3` is
     more expressive but ignores the pause tag between chapters.
3. **Write `voice.md`**: fill the front matter (voice name **and** voice id, so
   the same voice is found again if it is renamed), then replace the
   `TODO(ytflow)` lines with why this voice was chosen and delivery notes.
4. **Pronunciations.** Look through the script for names, foreign words,
   abbreviations and numbers the voice may say wrong; listen for them in the
   test phrases. Add each one as a spoken spelling:

   ```toml
   [pronunciations]
   "Nero" = "Neer-oh"
   "SPQR" = "S P Q R"
   "1453" = "fourteen fifty-three"
   ```

   Matching is whole words, case-sensitive: `"Nero"` does not touch
   `"Neronian"`. The spellings go into the exported text only; the script and
   the subtitles keep the real word. This list grows with every video: a
   channel about Rome meets the same names again.

```bash
ytflow kit check <channel> <video> --file voice.md
```

Fix what it reports before going on.

**Later videos:** the voice is already in the kit, so do not change it. If a
pronunciation must be added, `ytflow kit edit <channel> <video> --file voice.md`
says whether the file can be edited in place or a new kit version was started
(a filled `voice.md` that other videos use is never rewritten under them).

## 2. Export the narration text

```bash
ytflow voiceover text <channel> <video>
```

It prints the path of `voiceover/v<N>/narration.txt` and writes next to it:

- `narration.txt` — the whole narration, one paragraph per chapter, with a
  `<break time="1s" />` pause between chapters (the kit's `chapter_break`);
- `chapters/<NN>_<chapter>.txt` — the same text one chapter per file;
- `voiceover.json` — the settings to use and which phrases each chapter holds.

It warns about a pronunciation that never appears in this script, which is
usually a typo in the word. Running it again without changes writes nothing
new. A new script version or a kit change gives a new voiceover version.

Show the creator the text and the settings from `voiceover.json`.

## 3. Generate the audio in ElevenLabs

Tell the creator, in this order:

1. Open Text to Speech, pick the voice from `voiceover.json` (`voice`,
   `voice_id`), choose the `model`, and set stability, similarity, style and
   speed to the values in `settings`. Check them on every visit: the website
   keeps the last values used, which may come from another project.
2. Choose how to generate:
   - **One file** — paste all of `narration.txt`. Fine for a short video; the
     text box takes about 5,000 characters on most plans, and `voiceover
     text` says when the narration is longer.
   - **Chapter by chapter** — paste each `chapters/<NN>_<chapter>.txt` in turn.
     Use this for long videos, and whenever one chapter needs re-recording: only
     that chapter is generated again.
3. Listen to each take before downloading it. Re-generate a take with a
   mispronounced word (add it to `[pronunciations]`, then re-export), a
   skipped or repeated phrase, or a sudden change of tone.
4. Download as MP3 and save it in the video's `audio/` folder:
   - one file: `audio/narration.mp3`;
   - per chapter: `audio/<NN>_<chapter>.mp3`, named exactly like the chapter's
     text file (`01_rome-burns.mp3`).

   ElevenLabs names its downloads after the voice and the date; rename them.
   Use one layout, not both.

## 4. Check the audio

```bash
ytflow audio check <channel> <video>
```

It reports:

- **missing** chapter files, with the text file each one comes from;
- files that match neither layout (an un-renamed download), or the same
  chapter saved twice, or both layouts at once;
- each file's length, and a warning when a chapter or the whole narration is
  more than 25% off the script's estimate — usually a missing or repeated
  paragraph, or the wrong speed;
- a warning when a newer script version exists than the one exported.

Listen to anything it warns about. When it ends with `ok`, run
`ytflow status <channel> <video>`: the next step aligns the narration to the
script for the real timings.

## Rules

- Never change `voice.md` to suit one video. A different voice is a decision
  for the channel: a new kit version, and the creator says so.
- The narration is the script's text. Do not rephrase it for the voice; change
  the script and rebuild it, so subtitles and narration stay the same words.
- Spoken spellings belong in `[pronunciations]`, never in the script.
