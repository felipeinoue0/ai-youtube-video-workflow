"""The timeline's text as one ASS file: subtitles in a box, chapter titles top-left.

One file, rendered by libass, is what both the ffmpeg preview and the editor's
subtitle track show, so the look checked in the preview is the look in the edit.

The subtitle style is named ``Default`` and the file carries a ``[Kdenlive
Extradata]`` section, as Kdenlive writes them. With ``box_style = "block"`` the
box is libass's ``BorderStyle=4``: one box around the whole subtitle, however
many lines and colours it has (``BorderStyle=3`` draws one box per line and per
colour run). Highlighted words switch colour inside the line.
"""

from __future__ import annotations

from pathlib import Path

FILE = "subtitles.ass"
SUBTITLE_STYLE = "Default"
CHAPTER_FADE_MS = (180, 220)
CHAPTER_SLIDE_PX = 18
CHAPTER_SLIDE_MS = 300


def ass_colour(hex_colour: str, opacity: float = 1.0) -> str:
    """#rrggbb and an opacity as ASS &HAABBGGRR (alpha 00 is opaque)."""
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    alpha = round((1 - opacity) * 255)
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def inline_colour(hex_colour: str) -> str:
    """#rrggbb as an inline \\c override value: &HBBGGRR&."""
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    return f"&H{b}{g}{r}&".upper()


def ass_time(seconds: float) -> str:
    cs = round(seconds * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def event_text(item: dict, text_colour: str, highlight_colour: str) -> str:
    """The block's lines joined by \\N, with colour switches around its highlights."""
    text, highlights = item["text"], item.get("highlights", [])
    breaks, at = set(), 0
    for line in item["lines"][:-1]:  # the lines are the text's words split at single spaces
        at += len(line)
        breaks.add(at)
        at += 1
    starts, ends = {a for a, _ in highlights}, {b for _, b in highlights}
    out = []
    for i, char in enumerate(text):
        if i in starts:
            out.append(f"{{\\c{highlight_colour}}}")
        out.append("\\N" if i in breaks else escape(char))
        if i + 1 in ends:
            out.append(f"{{\\c{text_colour}}}")
    return "".join(out)


def style_line(
    name: str,
    look: dict,
    block: bool,
    padding: int,
    alignment: int,
    margins: tuple[int, int, int],
) -> str:
    """One [V4+ Styles] line; ``look`` has font, size, colour, box, bold and underline."""
    outline = "&HFF000000" if block else look["box"]  # block: no outline on the glyphs, only the one box
    left, right, vertical = margins
    return (
        f"Style: {name},{look['font']},{look['size']},{look['colour']},{look['colour']},{outline},{look['box']},"
        f"{-1 if look['bold'] else 0},0,{-1 if look['underline'] else 0},0,100,100,0,0,{4 if block else 3},"
        f"{padding},0,{alignment},{left},{right},{vertical},1"
    )


def render(timeline: dict) -> str:
    video = timeline["video"]
    sub, chapter = timeline["style"]["subtitles"], timeline["style"]["chapters"]
    block = sub.get("box_style", "block") == "block"
    side = round(video["width"] * 0.08)
    margin = chapter["margin"]
    subtitle_look = {
        "font": sub["font"],
        "size": sub["size"],
        "colour": ass_colour(sub["color"]),
        "box": ass_colour(sub["box_color"], sub["box_opacity"]),
        "bold": sub.get("bold", False),
        "underline": False,
    }
    chapter_look = {
        "font": chapter["font"],
        "size": chapter["size"],
        "colour": ass_colour(chapter.get("color", sub["color"])),
        "box": ass_colour(sub["box_color"], chapter.get("box_opacity", sub["box_opacity"])),
        "bold": chapter.get("bold", True),
        "underline": chapter.get("underline", False),
    }
    padding = int(sub.get("box_padding", max(4, round(sub["size"] * 0.25))))
    styles = [
        style_line(SUBTITLE_STYLE, subtitle_look, block, padding, 2, (side, side, sub["margin_bottom"])),
        style_line("Chapter", chapter_look, block, max(4, round(chapter["size"] * 0.3)), 7, (margin, margin, margin)),
    ]
    fields = (
        "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding"
    )
    events = []
    fade_in, fade_out = CHAPTER_FADE_MS
    for item in timeline["chapters"]:
        tags = f"\\an7\\fad({fade_in},{fade_out})"
        if chapter.get("slide"):
            tags += f"\\move({margin + CHAPTER_SLIDE_PX},{margin},{margin},{margin},0,{CHAPTER_SLIDE_MS})"
        span = f"{ass_time(item['start'])},{ass_time(item['end'])}"
        events.append(f"Dialogue: 1,{span},Chapter,,0,0,0,,{{{tags}}}{escape(item['title'])}")
    fade = int(sub.get("fade_ms", 0))
    text_inline = inline_colour(sub["color"])
    highlight_inline = inline_colour(sub.get("highlight_color", "#ffd166"))
    for item in timeline["subtitles"]:
        tags = f"{{\\fad({fade},{fade})}}" if fade else ""
        span = f"{ass_time(item['start'])},{ass_time(item['end'])}"
        text = event_text(item, text_inline, highlight_inline)
        events.append(f"Dialogue: 0,{span},{SUBTITLE_STYLE},,0,0,0,,{tags}{text}")
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {video['width']}",
            f"PlayResY: {video['height']}",
            f"LayoutResX: {video['width']}",
            f"LayoutResY: {video['height']}",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[Kdenlive Extradata]",
            "MaxLayer: 1",
            f"DefaultStyles: {SUBTITLE_STYLE},Chapter",
            "",
            "[V4+ Styles]",
            f"Format: {fields}",
            *styles,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )


def write(directory: Path, timeline: dict) -> Path:
    path = directory / FILE
    path.write_text(render(timeline))
    return path
