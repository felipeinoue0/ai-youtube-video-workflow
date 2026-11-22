"""Media probing through ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class MediaError(Exception):
    """ffprobe is missing or could not read a file."""


def ffprobe() -> str:
    path = shutil.which("ffprobe")
    if path is None:
        raise MediaError("ffprobe not found on PATH — install ffmpeg (it is in the dev image)")
    return path


def image_size(path: Path) -> tuple[int, int]:
    """(width, height) of an image file."""
    result = subprocess.run(
        [
            ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        stream = json.loads(result.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        if width <= 0 or height <= 0:  # ffprobe "reads" a text file as a 0x0 stream
            raise ValueError
        return width, height
    except (json.JSONDecodeError, KeyError, IndexError, ValueError):
        raise MediaError(f"cannot read image {path}: {result.stderr.strip() or 'not an image'}") from None
