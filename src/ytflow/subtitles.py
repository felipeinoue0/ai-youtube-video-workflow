"""The timeline's text as one ASS file: subtitles on a box, chapter titles top-left.

One file, rendered by libass, is what both the ffmpeg preview and the editor's
subtitle track show, so the look checked in the preview is the look in the edit.
"""

from __future__ import annotations

from pathlib import Path

FILE = "subtitles.ass"
CHAPTER_FADE_MS = 400


def ass_colour(hex_colour: str, opacity: float = 1.0) -> str:
    """#rrggbb and an opacity as ASS &HAABBGGRR (alpha 00 is opaque)."""
    r, g, b = hex_colour[1:3], hex_colour[3:5], hex_colour[5:7]
    alpha = round((1 - opacity) * 255)
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(seconds: float) -> str:
    cs = round(seconds * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def render(timeline: dict) -> str:
    video = timeline["video"]
    sub, chapter = timeline["style"]["subtitles"], timeline["style"]["chapters"]
    box = ass_colour(sub["box_color"], sub["box_opacity"])
    padding = max(4, round(sub["size"] * 0.25))
    fields = (
        "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding"
    )
    text_colour = ass_colour(sub["color"])
    side = round(video["width"] * 0.08)
    margin = chapter["margin"]
    styles = [
        # BorderStyle 3: an opaque box behind each line; libass paints it with OutlineColour
        f"Style: Subtitle,{sub['font']},{sub['size']},{text_colour},{text_colour},{box},{box},0,0,0,0,100,100,0,0,"
        f"3,{padding},0,2,{side},{side},{sub['margin_bottom']},1",
        f"Style: Chapter,{chapter['font']},{chapter['size']},{text_colour},{text_colour},{box},{box},-1,0,0,0,100,100,"
        f"0,0,3,{max(4, round(chapter['size'] * 0.25))},0,7,{margin},{margin},{margin},1",
    ]
    events = []
    for item in timeline["chapters"]:
        fade = f"{{\\fad({CHAPTER_FADE_MS},{CHAPTER_FADE_MS})}}"
        span = f"{ass_time(item['start'])},{ass_time(item['end'])}"
        events.append(f"Dialogue: 1,{span},Chapter,,0,0,0,,{fade}{escape(item['title'])}")
    for item in timeline["subtitles"]:
        text = "\\N".join(escape(line) for line in item["lines"])
        events.append(f"Dialogue: 0,{ass_time(item['start'])},{ass_time(item['end'])},Subtitle,,0,0,0,,{text}")
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {video['width']}",
            f"PlayResY: {video['height']}",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 2",
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
