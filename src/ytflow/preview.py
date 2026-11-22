"""A draft render of the timeline with ffmpeg, no editor needed.

It shows the edit as ``timeline.json`` describes it: each image with its camera
move, the transitions, the subtitle box and chapter titles (from the same ASS
file the editor gets), the fades and the narration. It is for reviewing the edit
quickly; the final video is rendered from the editor's project.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ytflow.media import MediaError, ffmpeg

FILE = "preview.mp4"
XFADE = {
    "dissolve": "fade",
    "wipe-left": "wipeleft",
    "wipe-right": "wiperight",
    "wipe-up": "wipeup",
    "wipe-down": "wipedown",
    "slide-left": "slideleft",
    "slide-right": "slideright",
    "slide-up": "slideup",
    "slide-down": "slidedown",
}
# Images are resampled at this multiple of the output size before the camera
# move, so the move's whole-pixel steps are sub-pixel in the result.
OVERSAMPLE = 3


def even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def camera_filter(clip: dict, width: int, height: int, fps: int) -> str:
    """zoompan expressions for the clip's camera move, eased in and out."""
    frames = max(1, round((clip["end"] - clip["start"]) * fps))
    a, b = clip["camera"]["from"], clip["camera"]["to"]
    p = f"(on/{max(frames - 1, 1)})"
    ease = f"({p}*{p}*(3-2*{p}))"

    def lerp(key: str) -> str:
        return f"({a[key]}+({b[key]}-{a[key]})*{ease})"

    big_w, big_h = width * OVERSAMPLE, height * OVERSAMPLE
    return (
        f"scale={big_w}:{big_h}:flags=lanczos,setsar=1,"
        f"zoompan=z='1/{lerp('w')}':x='{lerp('x')}*iw':y='{lerp('y')}*ih':d=1:s={width}x{height}:fps={fps},"
        f"trim=end_frame={frames},setpts=PTS-STARTPTS,format=yuv420p"
    )


def graph(timeline: dict, scale: float, ass_path: Path) -> tuple[list[str], str]:
    """(ffmpeg input arguments, filter graph) for the whole timeline."""
    video = timeline["video"]
    fps = video["fps"]
    width, height = even(video["width"] * scale), even(video["height"] * scale)
    inputs: list[str] = []
    parts: list[str] = []
    for k, clip in enumerate(timeline["clips"]):
        inputs += [
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-t",
            f"{clip['end'] - clip['start'] + 1:.3f}",
            "-i",
            clip["image"],
        ]
        parts.append(f"[{k}:v]{camera_filter(clip, width, height, fps)}[c{k}]")
    current = "c0"
    for k, transition in enumerate(timeline["transitions"], 1):
        out = f"x{k}"
        if transition["type"] == "cut":
            parts.append(f"[{current}][c{k}]concat=n=2:v=1:a=0[{out}]")
        else:
            offset = transition["at"] - transition["seconds"] / 2
            parts.append(
                f"[{current}][c{k}]xfade=transition={XFADE[transition['type']]}:"
                f"duration={transition['seconds']:.4f}:offset={offset:.4f}[{out}]"
            )
        current = out
    duration = video["duration"]
    ass = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fade_out_start = duration - video["fade_out"]
    parts.append(
        f"[{current}]subtitles=filename='{ass}':original_size={video['width']}x{video['height']},"
        f"fade=t=in:st=0:d={video['fade_in']},fade=t=out:st={fade_out_start:.4f}:d={video['fade_out']},"
        f"trim=duration={duration:.4f}[v]"
    )
    first_audio = len(timeline["clips"])
    labels = []
    for k, audio in enumerate(timeline["audio"]):
        inputs += ["-i", audio["file"]]
        delay = round(audio["start"] * 1000)
        parts.append(f"[{first_audio + k}:a]aresample=48000,adelay={delay}:all=1[a{k}]")
        labels.append(f"[a{k}]")
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad,atrim=duration={duration:.4f},"
        f"afade=t=in:st=0:d={video['fade_in']},afade=t=out:st={fade_out_start:.4f}:d={video['fade_out']}[a]"
    )
    return inputs, ";\n".join(parts)


def render(timeline: dict, base: Path, ass_path: Path, output: Path, scale: float = 0.5) -> None:
    """Render the timeline; image and audio paths in it are relative to ``base``."""
    inputs, filters = graph(timeline, scale, ass_path.resolve())
    script = output.with_suffix(".filters.txt")
    script.write_text(filters)
    command = [
        ffmpeg(),
        "-v",
        "error",
        "-y",
        *inputs,
        "-filter_complex_script",
        str(script.resolve()),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output.resolve()),
    ]
    result = subprocess.run(command, cwd=base, capture_output=True, text=True, check=False)
    script.unlink(missing_ok=True)
    if result.returncode != 0:
        raise MediaError(f"ffmpeg could not render the preview: {result.stderr.strip()[-800:]}")
