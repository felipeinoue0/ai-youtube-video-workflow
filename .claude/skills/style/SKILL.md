---
name: style
description: Build a YouTube channel's style guide and visual anchor from reference transcripts of videos the creator likes — measured pace and phrase length, hook, structure, tone, and the image-prompt anchor that keeps every video looking the same. Use after branding, or when the channel's writing or visual style is being redone.
---

# Style

Per-channel step 2 of the ai-youtube-video-workflow. It fills two kit files that
every video reads:

- `style-guide.md`: how scripts read. The script step follows it.
- `visual-style.md`: how images look. Every Google Flow prompt ends with its
  anchor.

These two files are what make video 2, 3, 4 feel like the same channel as
video 1, so take the time to get them right. `ytflow` measures and checks; you
analyze and write. Run commands from the workspace root (`uv run ytflow` if
`ytflow` is not on the PATH).

## 0. Where are we

```bash
ytflow status <channel>
```

Read `channels/<channel>/branding/` (latest version): `brief.md` gives you the
niche, audience, promise, tone and palette. If there is no branding yet, say so
and suggest the branding skill first. You can continue if the creator insists.

## 1. Collect references

Ask the creator for **3–5 transcripts** of long-form videos they want to sound
like: same kind of video, ideally from more than one channel. Each one goes in
`channels/<channel>/references/` as its own file:

- **Copy from YouTube** (timing included): under the video, *...more → Show
  transcript*. Select the whole panel, copy, and save as `<name>.txt`.
- **Subtitle file**: an `.srt` or `.vtt` the creator already has, e.g. from
  `yt-dlp --skip-download --write-auto-subs --sub-format vtt <url>` if they use
  it.
- **Plain text** works, but then the pace cannot be measured.

The transcripts are for analysis only. Never copy their sentences into this
channel's style guide or scripts.

## 2. Measure

```bash
ytflow references stats <channel>
```

For each transcript it reports words, sentences, words per minute, median and
p90 words per sentence, share of questions, use of "you", and the hook (the
first 15 seconds). At the end it recommends front-matter values. Keep the
output; the numbers go in the guide.

## 3. Read and analyze

Read every transcript in full. For each one, note:

- **Hook**: what happens in the first 15 seconds: a question, a surprising
  fact, a promise, or starting mid-scene? How soon is the topic clear?
- **Structure**: number of sections, their rough length, and how each one opens
  (a question, a date, a scene) and closes (a cliffhanger, a summary, an open
  loop).
- **Pacing**: where it speeds up or slows down, and where the long and short
  sentences go.
- **Voice**: first, second or third person; vocabulary level; humor; how
  certain it sounds.
- **Devices**: open loops, callbacks, rhetorical questions, lists of three,
  concrete numbers, sensory detail.
- **Ending**: recap, final twist, call to action, and where the "subscribe"
  ask sits, if there is one.

Then compare them. Adopt only what **most** references share and what fits the
brief. A device only one channel uses is that channel's signature, not a
pattern to follow.

## 4. Write the kit

```bash
ytflow kit edit <channel> --file style-guide.md --file visual-style.md
```

Write into the directory it prints, and only there. Replace each file's whole
content; no `TODO(ytflow)` line may remain.

### `style-guide.md`

Start with the front matter, which the script step reads:

```toml
+++
words_per_minute = 150     # from the references; narration usually 130–170
phrase_words_target = 12   # typical words per phrase: one subtitle, one image
phrase_words_max = 22      # longest phrase allowed
+++
```

Start from the recommended values. Adjust them only for a reason you write
down: a calm channel can be slower than its references, and subtitles read
badly past ~25 words. If no transcript had timing, ask the creator; 150 is a
safe default.

Then the guide, written as **rules for a writer**, not as a description of the
references:

1. **Promise**: one sentence from the brief. Every video delivers it.
2. **Hook**: the formula in steps, plus two example openings for *invented*
   topics. Write them yourself; never quote a reference.
3. **Structure**: the chapter template (how many, rough length, how a chapter
   opens and closes), and how long a typical video is.
4. **Phrases**: length rules (in line with the front matter), how to mix short
   and long, one idea per phrase.
5. **Voice and vocabulary**: person, register, words to prefer and to avoid.
6. **Devices to use**: with a short example of each.
7. **Avoid**: filler, clichés, anything that breaks the tone.
8. **Ending**: recap or twist, the call to action and where it sits.
9. **Review checklist**: 6–10 yes/no questions the script step answers before
   showing the creator a script.

### `visual-style.md`

The front matter, which the image-prompt step reads:

```toml
+++
aspect_ratio = "16:9"
anchor = "cinematic digital painting, warm low sun, muted ochre and teal palette, soft film grain, shallow depth of field"
avoid = "text, letters, watermarks, logos, modern objects, distorted hands"
+++
```

- **anchor**: one sentence of 8–40 words. It covers medium (photo, painting,
  3D, illustration), lighting, palette (from the brief), texture, lens and
  mood. It is appended **verbatim** to every prompt, so it must not name a
  subject.
- **avoid**: what no image may contain. Always include text, letters,
  watermarks and logos; images with text in them clash with the subtitles.

Then the body:

- **Composition rules**: keep the **lower fifth** calm (the subtitles sit there)
  and the **top-left** corner free of key detail (the chapter title sits
  there). Leave the subject room for a slow pan or zoom.
- **Shot variety**: the mix to rotate through (wide establishing, medium,
  close detail, map or diagram-like, symbolic), so a long video does not
  repeat itself.
- **Recurring elements**: characters, places or objects that appear across
  videos, each with a fixed description to reuse word for word.
- **Google Flow settings**: landscape 16:9, the model the creator settled on,
  and how many variations to generate per prompt.

## 5. Check

```bash
ytflow kit check <channel> --file style-guide.md --file visual-style.md
```

Fix everything it reports, then run it again until it prints `ok`. Report its
result as printed.

## 6. Try the anchor before the first video

Write **three test prompts** for subjects typical of the channel (a wide shot,
a close detail, a person), each ending with the anchor. Ask the creator to
generate them in Google Flow and look at the three side by side:

- Do they look like **one** channel? If not, make the anchor more specific
  (medium, palette, lighting).
- Is there text in the images? Then strengthen `avoid`.
- Do they match the logo and banner palette?

If you can view images, look at them too and say what you see. Change the
anchor, run `kit check` again, and repeat until the creator is happy.

## Iterating later

Run the same `ytflow kit edit` command. If a video already uses the kit, it
starts a new kit version and says so; tell the creator that the earlier videos
keep the old style and the next ones get the new one.

## Done when

- `ytflow kit check <channel> --file style-guide.md --file visual-style.md`
  prints `ok`
- the creator approved the guide and the three test images

Then run `ytflow status <channel>`. The next step is usually to start the first
video: `ytflow video new <channel> <video>`.
