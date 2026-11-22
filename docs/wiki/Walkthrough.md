# Walkthrough: from an empty folder to a video, then the next one

This page follows one sample channel, **History Explained**, through the whole
workflow: branding, style, then video 1 from script to the Kdenlive project and
the words to publish it with, and finally how video 2 starts with everything
already set.

You do not type these commands yourself: you talk to your AI agent, and its
skills run them. Start any session with **"let's continue"** (the `guide`
skill): it runs `ytflow status` and picks the next step. The commands are shown
so you know what happens and where the files go.

Every output below is real: this run was made in a fresh workspace, with the
external tools stood in for (generated images instead of Canva and Google
Flow, a synthetic voice instead of ElevenLabs). Long paths are shortened to
`channels/…`.

## 0. A channel

```text
$ ytflow channel new history-explained
channels/history-explained

$ ytflow status history-explained
channel history-explained
  branding   not started
  kit        v1, still TODO: edit-preset.toml, publish.md, style-guide.md, visual-style.md, voice.md
  videos     none
next: create the logo and banner in Canva and write the channel description and tags (skill: branding)
```

The **kit** (`channels/history-explained/kit/v1/`) is what every video of the
channel reads. Each step fills its part the first time:

| Kit file | Filled by | What it holds |
|---|---|---|
| `publish.md` | branding | the description template and base tags |
| `style-guide.md` | style | pace, phrase length, hook, structure, tone |
| `visual-style.md` | style | the sentence added to every image prompt |
| `voice.md` | voiceover, first video | the ElevenLabs voice, settings, pronunciations |
| `edit-preset.toml` | edit, first video | subtitles, chapter titles, transitions, camera |

## 1. Branding (once per channel)

**You:** answer a short interview, then make the logo and banner in Canva with
the sizes and safe areas the agent gives you, and save them into the branding
version folder.
**The agent:** writes `identity.toml` (name, handle, description, keywords)
and the kit's `publish.md`, then checks everything against YouTube's limits.

```text
$ ytflow branding check history-explained
branding v1: ok
```

The `publish.md` template it wrote:

```text
+++
base_tags = ["roman history", "ancient rome", "history documentary"]
+++
{summary}

Chapters:
{chapters}

New story from Rome every week: subscribe so you do not miss it.
```

## 2. Style (once per channel)

**You:** put 2–5 transcripts of videos you like in
`channels/history-explained/references/` (subtitle files or copied
transcripts).
**The agent:** measures them, then writes the style guide and the visual
anchor.

```text
$ ytflow references stats history-explained
rome-1.txt (plain): 110 words, 12 sentences, no timing
  sentence words: median 9.5, p90 13
  questions: 17% of sentences; 'you': 0.91 per 100 words
  hook: What if the greatest empire in history was undone by a coin? …
recommended front matter for style-guide.md:
  words_per_minute = (no timed transcript: choose, e.g. 150)
  phrase_words_target = 9
  phrase_words_max = 13

$ ytflow kit check history-explained --file style-guide.md --file visual-style.md --file publish.md
kit v1: ok

$ ytflow status history-explained
  kit        v1, still TODO: edit-preset.toml, voice.md
next: start the first video: ytflow video new history-explained <video>
```

`voice.md` and `edit-preset.toml` stay TODO: they are settled during the first
video, when there is something to listen to and look at.

## 3. Video 1: the script

```text
$ ytflow video new history-explained the-silver-coin
$ ytflow status history-explained the-silver-coin
next: write script.md from the kit's style guide and run ytflow script build (skill: script)
```

**You:** give the topic, approve an outline, then the script.
**The agent:** writes `script.md` in the channel's style, one phrase per line,
grouped into chapters:

```text
# How a Silver Coin Broke Rome

## A Lighter Coin
- What if the greatest empire was undone by a coin?
- In the year 64, Nero made the silver coin lighter.
…
```

```text
$ ytflow script build history-explained the-silver-coin
How a Silver Coin Broke Rome
  0:00 A Lighter Coin (4 phrases)
  0:16 Soldiers and Pay (3 phrases)
  0:29 The Crisis (4 phrases)
11 phrases, 9.5 words on average (kit target 9), about 0:44 at 150 wpm
script v1: ok
```

Every phrase now has a name, `001_what-if-the-greatest-empire`, that its
image, its subtitle and its place in the edit share.

## 4. Video 1: images

**The agent:** writes one scene per phrase; `ytflow` appends the kit's visual
anchor to each, word for word:

```text
001_what-if-the-greatest-empire
a single worn silver coin resting on a dark wooden table, close-up, empty space below. cinematic digital painting, warm low sun, muted ochre and teal palette, soft film grain. No text, letters, watermarks, modern objects.
```

**You:** paste the prompts from `prompts/v1/prompts.txt` into Google Flow one
by one, and download each image in order. Generate the first few, check they
look alike, then the rest.

The downloads have Flow's names; `ytflow` renames copies in download order
(it shows the pairs first, and copies only with `--apply`):

```text
$ ytflow images import history-explained the-silver-coin --from ~/Downloads/flow --apply
flow_2508830553.png -> 001_what-if-the-greatest-empire.png
flow_207345751.png -> 002_in-the-year-64-nero.png
…
copied 11 file(s) into channels/history-explained/videos/the-silver-coin/images

$ ytflow images check history-explained the-silver-coin
images: 11/11 present, smallest 1920x1080 — ok
```

## 5. Video 1: the narration

```text
next: fill voice.md in kit v1 (skill: voiceover)
```

**First video only:** you listen to two or three ElevenLabs voices reading the
same three phrases, pick one, and settle the settings. The agent records them
in the kit's `voice.md`, with spellings for names the voice says wrong
(`"Nero" = "Neer-oh"`). Every later video uses the same voice.

```text
$ ytflow voiceover text history-explained the-silver-coin
voiceover v1: 599 characters, 3 chapter(s), about 0:44 from script v1
channels/…/voiceover/v1/narration.txt
```

```text
What if the greatest empire was undone by a coin? In the year 64, Neer-oh made the silver coin lighter. …

<break time="1s" />

Every emperor after him took a little more silver out. …
```

**You:** generate it in ElevenLabs with the settings from `voiceover.json`
(the whole text, or chapter by chapter from `chapters/`), and save it in the
video's `audio/` folder as `narration.mp3` or `01_a-lighter-coin.mp3`, … .

```text
$ ytflow audio check history-explained the-silver-coin
  01_a-lighter-coin.wav                    0:12
  02_soldiers-and-pay.wav                  0:09
  03_the-crisis.wav                        0:11
audio: 3/3 chapter files, 0:34 — ok

$ ytflow align history-explained the-silver-coin
timing v1: chapters, 11 phrases, 0:36
  0:00 A Lighter Coin
  0:13 Soldiers and Pay
  0:24 The Crisis
```

The real timings replace the script's estimates. With the optional
faster-whisper extra (`uv sync --extra align`) `align` listens to the audio
and matches every word; without it, as here, it needs one file per chapter and
shares each chapter's length among its phrases.

## 6. Video 1: the edit

```text
next: fill edit-preset.toml in kit v1 (skill: edit)
```

**First video only:** the agent walks you through the edit preset — subtitle
size and box, how long chapter titles show, the transitions, how far the
camera moves — and you keep or change each.

```text
$ ytflow timeline build history-explained the-silver-coin
timeline v1: 11 clips, 0:38, 3 chapter titles; transitions: 5 dissolve, 2 wipe-left, 2 wipe-right, 1 slide-up

$ ytflow timeline preview history-explained the-silver-coin
channels/…/timeline/v1/preview.mp4

$ ytflow export kdenlive history-explained the-silver-coin
channels/…/timeline/v1/the-silver-coin.kdenlive
```

**You:** watch `preview.mp4` (a quick ffmpeg draft), then open the `.kdenlive`
project: the images on V1/V2 with a transition at every cut and a slow pan or
zoom on each, the narration on A1, the subtitles on a box at the bottom and
the chapter title top-left. Polish if you like, then render from Kdenlive.

## 7. Video 1: publish

**The agent:** offers five titles; you pick one. It writes a two-sentence
summary and the video's tags.

```text
$ ytflow publish build history-explained the-silver-coin
publish v1: ok — 28-character title, 283-character description, 7 tags
```

`description.txt`, the kit's template with the video filled in:

```text
Rome did not fall in a day: it fell one coin at a time. This is how a lighter silver coin emptied the soldiers' pay and broke the empire's promise.

Chapters:
0:00 A Lighter Coin
0:14 Soldiers and Pay
0:25 The Crisis

New story from Rome every week: subscribe so you do not miss it.
```

`tags.txt`: `roman history, ancient rome, history documentary, roman coins,
denarius, Nero, roman inflation` — the kit's base tags first. Paste
`title.txt`, `description.txt` and `tags.txt` into YouTube Studio with the
rendered video.

```text
$ ytflow status history-explained the-silver-coin
video history-explained/the-silver-coin (kit v1)
  script     v1
  prompts    v1
  images     11/11 images
  voiceover  v1
  audio      3/3 chapter files
  timing     v1
  timeline   v1
  publish    v1
next: done — every step has an output
```

## 8. Video 2: everything is already set

```text
$ ytflow video new history-explained the-roman-roads
$ ytflow status history-explained the-roman-roads
  kit        v1, complete
video history-explained/the-roman-roads (kit v1)
  script     not started
  …
next: write script.md from the kit's style guide and run ytflow script build (skill: script)
```

No branding, no style, no voice choice, no edit preset: video 2 reads the
same kit v1, so its script follows the same style guide, its images get the
same anchor sentence, its narration the same voice and settings, its edit the
same subtitles, transitions and camera, and its description the same
template. From here it is steps 3–7 again.

If you later want to change something for the channel — a slower voice, a
bigger subtitle — the step's skill runs `ytflow kit edit`, which starts kit
**v2** for the videos to come; finished videos keep v1.

## Where everything is

```text
channels/history-explained/
  branding/v1/            identity.toml, logo.png, banner.png
  references/             the transcripts you liked
  kit/v1/                 style-guide.md, visual-style.md, voice.md, edit-preset.toml, publish.md
  videos/the-silver-coin/
    video.toml            which kit version the video uses
    script/v1/            script.md, script.json
    prompts/v1/           prompts.md, prompts.txt, prompts.json
    images/               001_what-if-the-greatest-empire.png, …
    voiceover/v1/         narration.txt, chapters/, voiceover.json
    audio/                01_a-lighter-coin.mp3, …
    timing/v1/            timing.json, subtitles.srt
    timeline/v1/          timeline.json, subtitles.ass, preview.mp4, the-silver-coin.kdenlive
    publish/v1/           title.txt, description.txt, tags.txt, captions.srt, publish.json
```

Every step writes a new version (`v2`, `v3`, …) instead of overwriting, so
you can always compare with, or go back to, an earlier one. `channels/` is
never committed: it is your content.
