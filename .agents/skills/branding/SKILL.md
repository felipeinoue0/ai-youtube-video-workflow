---
name: branding
description: Guide a creator through a YouTube channel's branding — brand brief, logo and banner in Canva, channel name, handle, description and keywords — and seed the channel kit's publish template. Use when a channel is new or its branding is being redone.
---

# Branding

Per-channel step 1 of the ai-youtube-video-workflow. You do the thinking and
writing; `ytflow` does the exact parts: folders, versions, and checking every
limit YouTube enforces. The creator makes the images in Canva; you never call
Canva or any other API.

Run every command from the workspace root. `ytflow` is `uv run ytflow` when the
CLI is not installed globally.

## 0. Where are we

```bash
ytflow status <channel>
```

- `no channel` → ask for a channel slug (lowercase, hyphens, e.g.
  `history-explained`) and run `ytflow channel new <channel>`.
- Branding already has a version → read it (`ytflow version latest
  channels/<channel>/branding`) and ask what the creator wants to change. You
  iterate on a new version; you never edit an old one (see step 6).

## 1. Interview (short)

Ask in one message, and accept "you decide" for any of them:

1. Topic / niche, and what the channel will **not** cover.
2. Who watches: age range, what they already know, language.
3. The promise: what a viewer gets from every video, in one sentence.
4. Two or three channels they admire, and what they like about each one.
5. Tone: e.g. calm documentary, energetic explainer, dry humor.
6. A name they already have in mind, if any.
7. Links that belong in every description (site, socials, Patreon).

If `channels/<channel>/references/` already holds transcripts, skim them; they
show the tone better than the answers do.

## 2. Write the brief and identity

```bash
ytflow version new channels/<channel>/branding        # prints .../branding/v<N>
```

Write into that directory:

**`brief.md`**, the brand brief later steps read:

- niche, audience, promise, tone (from the interview)
- **name options**: 3–5 names with a one-line reason each; mark the chosen one
- **palette**: 3–4 colors as hex, with a role each (background, primary,
  accent, text) and enough contrast between text and background
- **fonts**: one heading and one body font that Canva has (e.g. Montserrat,
  Poppins, Bebas Neue, Inter, Lora); the subtitle font in the kit's
  `edit-preset.toml` should match the body font
- **logo concept**: one simple symbol or monogram, readable at 98 px
- **banner concept**: the background image idea plus the one line of text

**`identity.toml`**, the exact values YouTube takes:

```toml
name = "History Explained"            # ≤ 50 characters
handle = "@historyexplained"          # @ + 3–30 letters, digits, . _ -
language = "en"
description = """
First line says what the channel is and who it is for; YouTube shows it in search.
Then what a viewer gets, how often videos come out, and one call to action.
"""                                   # ≤ 1000 characters
keywords = ["roman history", "ancient history", "history documentary"]
```

Description: the first ~120 characters carry the search snippet. Put the real
search terms in it naturally, with no keyword lists, no emoji walls and no
"subscribe" in the first line.

Keywords: 8–15 phrases from broad to specific, the ones viewers actually type.
Leave out other channels' names. Multi-word keywords count with quotes, and
`ytflow` checks the total.

Then check it (logo and banner will still be reported missing at this point):

```bash
ytflow branding check <channel>
```

Fix every identity problem it lists before going on.

## 3. Canva guide

Write **`canva.md`** in the same version directory: a step-by-step guide for
*this* channel, using the palette, fonts and concepts from `brief.md`. It must
cover:

**Logo / profile picture**: Canva → *Create a design* → *Custom size*
**800 × 800 px**.
- YouTube shows it as a **circle** as small as 98 px: keep everything inside
  the central circle, with no thin lines and no small text (at most 1–3
  letters).
- Solid background in a palette color; a symbol or monogram in high contrast.
- Optional: Canva's *Magic Media* to draft the symbol, then simplify it.
- Export: *Share → Download → PNG*, saved as
  `channels/<channel>/branding/v<N>/logo.png`.

**Banner**: Canva → search the **YouTube Banner** template (2560 × 1440 px).
- **Safe area**: only the centered **1546 × 423 px** box shows on every device.
  Draw a temporary rectangle of exactly that size, center it (*Position → align
  center + middle*), keep the channel name, tagline and any face inside it, then
  delete the rectangle before export.
- The background fills the whole 2560 × 1440, because TVs show all of it.
- At most one line of text plus the channel name. Say the promise, not
  "subscribe".
- Export as PNG (or JPG if the PNG is over 6 MB), saved as
  `channels/<channel>/branding/v<N>/banner.png`.

**Optional watermark**: 150 × 150 px, a simplified logo on a transparent
background (PNG). It is used as the video watermark in YouTube Studio.

**Upload**: YouTube Studio → *Customization*:
- *Branding*: picture, banner, watermark.
- *Basic info*: name, handle, description, links.
- *Settings → Channel → Basic info*: keywords. Paste the keywords from
  `identity.toml`, quoting the multi-word ones.

Show the creator the brief and `canva.md` and wait for them to make the images.

## 4. Check the images

When the creator says the files are saved:

```bash
ytflow branding check <channel>
```

It reads the real image sizes. A failure means re-exporting from Canva at the
size it names; do not resize images yourself. Report the result exactly as the
CLI printed it.

If you can view images, look at `logo.png` and `banner.png` and judge them:
readable at a small size, text inside the safe area, palette respected.
Otherwise, ask the creator to confirm that.

## 5. Seed the channel kit

```bash
ytflow kit edit <channel> --file publish.md --file edit-preset.toml
```

It prints the kit directory you may write to; use only that one. A file that
still has its `TODO(ytflow)` placeholder is filled in place. Changing a file
that is already filled, in a kit some video uses, starts a new kit version
instead, so finished videos keep the kit they were made with. Tell the creator
when that happens (the CLI says so on stderr).

In that kit, rewrite **`publish.md`** with no `TODO(ytflow)` lines left in it.
It is the description template every video gets:

- the front matter's `base_tags`: 3–6 tags every video gets, taken from the
  channel keywords
- below it, the description itself: `{summary}` where each video's opening
  lines go and `{chapters}` where its chapter list goes (each exactly once;
  `{title}` may appear too), then the links from the interview, one per line,
  and a short call to action in the channel's tone. No `<` or `>`: YouTube
  rejects them.

```text
+++
base_tags = ["roman history", "ancient rome", "history documentary"]
+++
{summary}

Chapters:
{chapters}

Sources and further reading: (the links from the interview)

New story from Rome every week: subscribe so you do not miss it.
```

`ytflow kit check <channel> --file publish.md` must print `ok`.

If `edit-preset.toml` still has its `TODO(ytflow)` line, set the `[subtitles]`
and `[chapters]` fonts to the brief's body and heading fonts, and the subtitle
`box_color` to the palette's darkest color. Leave the rest to the edit step.

## 6. Iterate

The creator reviews the brief, the identity and the images. For a change:

```bash
ytflow version new --copy channels/<channel>/branding    # v<N+1>, starting from v<N>
```

Edit only the new version, re-run `ytflow branding check <channel>`, and tell
the creator which version is current. Never edit or delete an older version.

## Done when

- `ytflow branding check <channel>` prints `ok`
- the creator approved the name, logo and banner
- `publish.md` in the kit has no `TODO(ytflow)` line

Then run `ytflow status <channel>` and tell the creator the next step it names.
Normally that is the style skill, which builds the style guide and the visual
anchor from reference transcripts. `voice.md` and the rest of `edit-preset.toml`
are filled during the first video.
