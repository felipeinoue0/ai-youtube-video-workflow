"""Checks for the branding step: the channel identity and the logo and banner files.

A branding version holds::

    brief.md         # niche, audience, promise, tone, palette, fonts (written by the skill)
    canva.md         # the step-by-step Canva guide for this channel (written by the skill)
    identity.toml    # name, handle, description, keywords — checked here
    logo.png|jpg     # saved by the creator from Canva — checked here
    banner.png|jpg   # saved by the creator from Canva — checked here

The limits are YouTube's published ones for channel branding.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ytflow.media import MediaError, image_size

NAME_MAX = 50
HANDLE_RE = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
DESCRIPTION_MAX = 1000
KEYWORDS_MAX = 500

LOGO_MIN = 98
LOGO_RECOMMENDED = 800
LOGO_MAX_BYTES = 4 * 1024 * 1024
BANNER_MIN = (2048, 1152)
BANNER_MAX_BYTES = 6 * 1024 * 1024
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


def keywords_field(keywords: list[str]) -> str:
    """The keywords as YouTube stores them: space-separated, multi-word ones quoted."""
    return " ".join(f'"{k}"' if " " in k else k for k in keywords)


def check_identity(path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing {path.name}"]
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as err:
        return [f"{path.name} is not valid TOML: {err}"]
    problems: list[str] = []
    name = data.get("name", "")
    if not isinstance(name, str) or not name.strip():
        problems.append("name is missing")
    elif len(name) > NAME_MAX:
        problems.append(f"name is {len(name)} characters; YouTube allows {NAME_MAX}")
    handle = data.get("handle", "")
    if not isinstance(handle, str) or not HANDLE_RE.match(handle):
        problems.append(f"handle {handle!r} must be @ plus 3-30 letters, digits, '.', '_' or '-'")
    description = data.get("description", "")
    if not isinstance(description, str) or not description.strip():
        problems.append("description is missing")
    elif len(description) > DESCRIPTION_MAX:
        problems.append(f"description is {len(description)} characters; YouTube allows {DESCRIPTION_MAX}")
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
        problems.append("keywords must be a non-empty list of strings")
    else:
        field = keywords_field(keywords)
        if len(field) > KEYWORDS_MAX:
            problems.append(f"keywords take {len(field)} characters; YouTube allows {KEYWORDS_MAX} — drop some")
        lowered = [k.lower() for k in keywords]
        if len(set(lowered)) != len(lowered):
            problems.append("keywords contain duplicates")
    return problems


def find_image(version_dir: Path, stem: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        if (version_dir / f"{stem}{suffix}").is_file():
            return version_dir / f"{stem}{suffix}"
    return None


def check_logo(version_dir: Path) -> list[str]:
    path = find_image(version_dir, "logo")
    if path is None:
        return [
            f"missing logo — export it from Canva as {LOGO_RECOMMENDED}x{LOGO_RECOMMENDED} PNG "
            f"to {version_dir}/logo.png"
        ]
    try:
        width, height = image_size(path)
    except MediaError as err:
        return [str(err)]
    problems = []
    if width != height:
        problems.append(f"logo is {width}x{height}; it must be square (YouTube crops it to a circle)")
    if min(width, height) < LOGO_MIN:
        problems.append(f"logo is {width}x{height}; YouTube needs at least {LOGO_MIN}x{LOGO_MIN}")
    if path.stat().st_size > LOGO_MAX_BYTES:
        problems.append(f"logo is {path.stat().st_size // 1024} KB; YouTube allows 4 MB")
    return problems


def check_banner(version_dir: Path) -> list[str]:
    path = find_image(version_dir, "banner")
    if path is None:
        return [f"missing banner — export it from Canva as 2560x1440 PNG to {version_dir}/banner.png"]
    try:
        width, height = image_size(path)
    except MediaError as err:
        return [str(err)]
    problems = []
    if width < BANNER_MIN[0] or height < BANNER_MIN[1]:
        problems.append(f"banner is {width}x{height}; YouTube needs at least {BANNER_MIN[0]}x{BANNER_MIN[1]}")
    if width * 9 != height * 16:
        problems.append(f"banner is {width}x{height}; it must be 16:9 (e.g. 2560x1440)")
    if path.stat().st_size > BANNER_MAX_BYTES:
        problems.append(f"banner is {path.stat().st_size // 1024} KB; YouTube allows 6 MB")
    return problems


def check_branding(version_dir: Path) -> list[str]:
    return check_identity(version_dir / "identity.toml") + check_logo(version_dir) + check_banner(version_dir)
