---
name: image-prompts
description: Write one Google Flow background-image prompt per script phrase, built on the channel's visual anchor and named <enumerate_id>_<part_of_phrase>, then guide the creator through generating, importing and checking the images. Use after the script is approved, or when images are missing or wrong.
---

# Image prompts

Per-video step 2 of the ai-youtube-video-workflow. Every phrase of the script
gets one background image. You write the **scene** for each one. `ytflow`
appends the kit's anchor and avoid list to every scene word for word, which is
why all the images of all the videos share one look. Each prompt and its image
file carry the phrase's name (`012_the-river-at-dawn`), so they sort into
timeline order and the edit step finds them without help.

Run commands from the workspace root (`uv run ytflow` if `ytflow` is not on the
PATH).

## 0. Where are we

```bash
ytflow status <channel> <video>
```

You need a built and **approved** script (`script.json`) and a ready
`visual-style.md`. If the creator is still changing the script, finish that
first: phrase names come from the script, so editing it later renames the
images.

Read `visual-style.md` in the video's kit (`ytflow kit path <channel> <video>`)
in full: the composition rules, the shot variety, and the recurring elements
with their fixed descriptions.

## 1. Start a prompts version

```bash
ytflow prompts init <channel> <video>        # prints .../prompts/v<N>/prompts.md
```

It has one section per phrase:

```markdown
## 001_what-if-the-greatest-empire
> What if the greatest empire in history was never conquered at all?
scene: TODO(ytflow)
```

If an earlier prompts version exists, scenes whose phrase did not change are
carried over; only the new or changed phrases are `TODO`.

## 2. Write the scenes

Replace each `TODO(ytflow)` with a scene. Edit only the `scene:` lines.

A scene says **what is in the picture**, in 15–45 words:

- **Subject and action**: one clear focus. Prefer something concrete from the
  phrase (an object, a place, a person doing something) over a literal picture
  of an abstract idea.
- **Setting**: where and when, accurate for the topic (era, region, clothing,
  technology).
- **Framing**: the shot type. Rotate through the visual style's shot variety;
  never use the same framing three phrases in a row.
- **Composition**: keep the lower fifth calm (subtitles go there) and the
  top-left clear (chapter titles go there). Say it in the scene when it
  matters: "subject on the right, open sky at the top left".
- **Recurring elements**: copy their fixed descriptions from
  `visual-style.md` word for word.
- **People**: follow the audience in the style guide. When it is everyone,
  vary age and gender across the images (a young man, a woman in her sixties,
  a middle-aged father…), one person per image, so every viewer can see
  themselves; do not make one gender or age the face of the whole video
  unless the visual style names a recurring character.

Never put these in a scene:

- **Style words** (medium, lighting, palette, "cinematic", "4k"): the anchor
  adds them. Adding your own makes the images drift apart.
- **Text, signs, captions or speech bubbles**: they would clash with the
  subtitles.
- **Real living people, brands or logos.** Google Flow may refuse them, and
  they cause rights problems.

Neighboring phrases about the same thing should feel connected: same place,
new angle.

## 3. Build

```bash
ytflow prompts build <channel> <video>
```

It reports every problem with its line: a missing scene, a scene too short or
too long, a scene that repeats the anchor, sections that do not match the
script. Fix them and build again. When it prints `ok`, `prompts.txt` holds
every prompt under its name, ready to paste.

If it warns that a newer script version exists, run `ytflow prompts init`
again; it carries over the scenes that still match.

## 4. Test batch first

Before the creator generates everything, have them make the **first 5**
images. Look at them together, or ask the creator to compare them if you
cannot view images:

- Do they look like one channel, and like the style test images?
- Is there any text in an image? Then strengthen the scene, or the kit's
  `avoid` (through the style skill, which starts a new kit version if a video
  already uses the current one).
- Is the lower fifth calm, and the top-left clear?

Rewrite scenes that miss, build again, and only then go on.

## 5. Generate in Google Flow

Give the creator these steps:

1. Open Google Flow and start a project named after the video.
2. Choose image generation and set the aspect ratio to **landscape 16:9**
   (the kit's `aspect_ratio`).
3. Make a **new, empty download folder** for this batch, e.g.
   `~/Downloads/<video>-batch1`.
4. Work through `prompts.txt` **in order**: paste a prompt, pick the best
   variation, and download it into that folder before moving to the next
   prompt.

Google Flow usually names a download after the start of its prompt plus a
hash (`002_parece-exagero-mas-hoje-isso_314562ba.jpg`): those are paired **by
name**, whatever the order. Some downloads get Flow's own caption instead
(`Runner_on_empty_street_dawn_d2720777.jpg`); those pair by **download order**
— the oldest with the first image still missing — so keep the order, and do a
skipped prompt in its own batch later. The creator may also save the downloads
straight into the video's `images/` folder.

## 6. Import and check

```bash
ytflow images import <channel> <video> --from ~/Downloads/<video>-batch1
```

That is a dry run: it prints `download -> name  (by name | download order)`
pairs. `--from` may be the video's own `images/` folder: the files are then
renamed in place instead of copied.

When the downloads all share one file time (copied out of a zip, or moved
together), the order is lost and the import does not guess: it lists them as
`unmatched` with the names still missing. Look at each unmatched image, find
its scene in the prompts, and pair it:

```bash
ytflow images import <channel> <video> --from <folder> \
  --pair Runner_on_empty_street_dawn_d2720777.jpg=061_a-ia-acelera-quem-faz
```

If you can view images, open a few pairs and compare each one with its prompt;
otherwise ask the creator to spot-check them. Only when the pairs are right:

```bash
ytflow images import <channel> <video> --from ~/Downloads/<video>-batch1 --apply
ytflow images check <channel> <video>
```

`images check` lists missing images, extra files (and the name a stale file
should probably get after a script change), the same name saved twice, and
images in the wrong aspect ratio. To redo one image, the creator saves the new
one over the old file with the **same name**. Repeat until it prints `ok`.

## Iterating

- To change a few scenes: `ytflow version new --copy
  channels/<channel>/videos/<video>/prompts`, edit the new version, then build.
- After a script change: `ytflow prompts init <channel> <video>`, write the new
  `TODO` scenes, build, then run `images check` to see which images to redo.

## Done when

- `ytflow prompts build <channel> <video>` prints `ok`
- `ytflow images check <channel> <video>` prints `ok`
- the creator is happy with the images

Then run `ytflow status <channel> <video>`. Next comes the voiceover step.
