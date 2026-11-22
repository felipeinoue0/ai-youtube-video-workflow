"""Image prompts and image files — driven through the CLI process, images made with ffmpeg."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 12
+++
"""

ANCHOR = "cinematic digital painting, warm low sun, muted ochre and teal palette, soft film grain"
VISUAL = f"""+++
aspect_ratio = "16:9"
anchor = "{ANCHOR}"
avoid = "text, letters, watermarks"
+++
"""

SCRIPT = """# The Coin
## Silver
- A Roman coin rests on a merchant's table.
- The silver slowly turns to bronze.
## Soldiers
- Legionaries count their pay at dusk.
"""

NAMES = ["001_a-roman-coin-rests-on", "002_the-silver-slowly-turns-to", "003_legionaries-count-their-pay-at"]
SCENES = [
    "close-up of a worn silver denarius on a wooden merchant table, coins and scales around it",
    "the same coin seen in profile as its silver surface dulls into bronze, dark background",
    "wide shot of Roman legionaries in a camp counting coins by torchlight at dusk",
]


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> str:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def image(path: Path, width: int, height: int) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=teal:s={width}x{height}", "-frames:v", "1", path],
        check=True,
    )


@pytest.fixture
def video(tmp_path: Path) -> Path:
    ok(tmp_path, "channel", "new", "c")
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit / "style-guide.md").write_text(STYLE)
    (kit / "visual-style.md").write_text(VISUAL)
    ok(tmp_path, "video", "new", "c", "v")
    script = Path(ok(tmp_path, "version", "new", "channels/c/videos/v/script"))
    (script / "script.md").write_text(SCRIPT)
    ok(tmp_path, "script", "build", "c", "v")
    return tmp_path / "channels" / "c" / "videos" / "v"


def fill(prompts_md: Path, scenes: list[str]) -> None:
    text = prompts_md.read_text()
    for scene in scenes:
        text = text.replace("scene: TODO(ytflow)", f"scene: {scene}", 1)
    prompts_md.write_text(text)


def built(root: Path) -> Path:
    prompts_md = Path(ok(root, "prompts", "init", "c", "v"))
    fill(prompts_md, SCENES)
    ok(root, "prompts", "build", "c", "v")
    return prompts_md.parent


def test_init_writes_one_section_per_phrase(tmp_path: Path, video: Path) -> None:
    prompts_md = Path(ok(tmp_path, "prompts", "init", "c", "v"))
    assert prompts_md == video / "prompts" / "v1" / "prompts.md"
    text = prompts_md.read_text()
    assert text.startswith("<!-- script v1 · kit v1 -->")
    for name in NAMES:
        assert f"## {name}\n> " in text
    assert text.count("scene: TODO(ytflow)") == 3
    result = ytflow(tmp_path, "prompts", "build", "c", "v")
    assert result.returncode == 1 and f"{NAMES[0]} has no scene yet" in result.stdout


def test_build_appends_the_anchor_verbatim(tmp_path: Path, video: Path) -> None:
    version = built(tmp_path)
    data = json.loads((version / "prompts.json").read_text())
    assert data["script_version"] == "v1" and data["kit_version"] == "v1"
    assert [p["name"] for p in data["prompts"]] == NAMES
    first = data["prompts"][0]
    assert first["phrase"] == "A Roman coin rests on a merchant's table."
    assert first["prompt"] == f"{SCENES[0]}. {ANCHOR}. No text, letters, watermarks."
    assert all(ANCHOR in p["prompt"] for p in data["prompts"])
    text = (version / "prompts.txt").read_text()
    assert text.startswith(f"{NAMES[0]}\n{first['prompt']}\n\n{NAMES[1]}\n")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda t: t.replace(SCENES[1], "a coin"), "scene is 2 words; keep it 5–60"),
        (lambda t: t.replace(SCENES[1], f"a coin on a table, {ANCHOR}"), "repeats the anchor"),
        (lambda t: t.replace(f"## {NAMES[2]}", "## 003_something-else"), "sections not in the script: 003_something"),
        (lambda t: t.replace(f"## {NAMES[2]}", "## 003_something-else"), f"sections missing for: {NAMES[2]}"),
        (lambda t: t.replace(f"scene: {SCENES[2]}", f"scene: {SCENES[2]}\n\n- stray"), None),
    ],
)
def test_build_names_each_problem(tmp_path: Path, video: Path, change, expected: str | None) -> None:
    version = built(tmp_path)
    (version / "prompts.json").unlink()
    prompts_md = version / "prompts.md"
    prompts_md.write_text(change(prompts_md.read_text()))
    result = ytflow(tmp_path, "prompts", "build", "c", "v")
    if expected is None:  # a wrapped scene line is joined, not rejected
        assert result.returncode == 0
        assert json.loads((version / "prompts.json").read_text())["prompts"][2]["scene"].endswith("dusk - stray")
        return
    assert result.returncode == 1 and expected in result.stdout, result.stdout
    assert not (version / "prompts.json").exists()


def test_sections_out_of_order_are_rejected(tmp_path: Path, video: Path) -> None:
    version = built(tmp_path)
    text = (version / "prompts.md").read_text()
    first, second = text.split(f"## {NAMES[1]}")
    second, third = second.split(f"## {NAMES[2]}")
    (version / "prompts.md").write_text(f"{first}## {NAMES[2]}{third}## {NAMES[1]}{second}")
    result = ytflow(tmp_path, "prompts", "build", "c", "v")
    assert result.returncode == 1 and "not in script order" in result.stdout


def test_new_script_version_carries_unchanged_scenes(tmp_path: Path, video: Path) -> None:
    built(tmp_path)
    script2 = Path(ok(tmp_path, "version", "new", "--copy", "channels/c/videos/v/script"))
    (script2 / "script.md").write_text(SCRIPT.replace("slowly turns to bronze", "slowly turns to copper"))
    ok(tmp_path, "script", "build", "c", "v")
    # the old prompts still build, but say a newer script exists
    assert "but v2 exists" in ok(tmp_path, "prompts", "build", "c", "v")
    result = ytflow(tmp_path, "prompts", "init", "c", "v")
    assert "2 scene(s) carried over from v1" in result.stderr
    text = Path(result.stdout.strip()).read_text()
    assert text.startswith("<!-- script v2") and SCENES[0] in text and SCENES[2] in text
    assert text.count("scene: TODO(ytflow)") == 1  # the changed phrase needs a new scene


def test_prompts_need_a_ready_visual_style_and_a_built_script(tmp_path: Path, video: Path) -> None:
    (video / "script" / "v1" / "script.json").unlink()
    result = ytflow(tmp_path, "prompts", "init", "c", "v")
    assert result.returncode == 1 and "run: ytflow script build c v" in result.stderr
    kit = tmp_path / "channels" / "c" / "kit" / "v1"
    (kit / "visual-style.md").write_text(VISUAL.replace(ANCHOR, "short"))
    result = ytflow(tmp_path, "prompts", "init", "c", "v")
    assert result.returncode == 1 and "visual-style.md in kit v1 is not ready" in result.stderr


def test_images_check_reports_every_mismatch(tmp_path: Path, video: Path) -> None:
    built(tmp_path)
    images = video / "images"
    image(images / f"{NAMES[0]}.png", 64, 36)
    image(images / f"{NAMES[0]}.jpg", 64, 36)  # same name twice
    image(images / "002_the-silver-slowly-turns-to-bronze.png", 64, 36)  # stale name
    image(images / f"{NAMES[2]}.png", 64, 64)  # square, not 16:9
    result = ytflow(tmp_path, "images", "check", "c", "v")
    assert result.returncode == 1
    out = result.stdout
    assert f"missing: {NAMES[1]}" in out
    assert f"extra: 002_the-silver-slowly-turns-to-bronze.png (rename to {NAMES[1]}.png?)" in out
    assert f"duplicate: {NAMES[0]}.jpg, {NAMES[0]}.png" in out
    assert f"wrong aspect: {NAMES[2]}.png is 64x64, not 16:9" in out
    assert "images: 2/3 present" in out


def test_images_check_passes_and_status_moves_on(tmp_path: Path, video: Path) -> None:
    built(tmp_path)
    for name in NAMES:
        image(video / "images" / f"{name}.png", 1376, 768)  # 1.79: within the 2% tolerance
    assert ok(tmp_path, "images", "check", "c", "v").endswith("images: 3/3 present, smallest 1376x768 — ok")
    assert "images     3/3 images" in ok(tmp_path, "status", "c", "v")


def test_images_import_pairs_downloads_oldest_first(tmp_path: Path, video: Path) -> None:
    built(tmp_path)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    image(video / "images" / f"{NAMES[0]}.png", 64, 36)  # already there: not re-filled
    for i, name in enumerate(["zeta.png", "alpha.jpeg", "notes.txt"]):
        path = downloads / name
        image(path, 64, 36) if name != "notes.txt" else path.write_text("x")
        os.utime(path, (1_000_000 + i, 1_000_000 + i))
    plan = ok(tmp_path, "images", "import", "c", "v", "--from", str(downloads))
    assert plan.splitlines()[:2] == [f"zeta.png -> {NAMES[1]}.png", f"alpha.jpeg -> {NAMES[2]}.jpeg"]
    assert "add --apply" in plan and not (video / "images" / f"{NAMES[1]}.png").exists()
    ok(tmp_path, "images", "import", "c", "v", "--from", str(downloads), "--apply")
    assert (video / "images" / f"{NAMES[1]}.png").is_file() and (downloads / "zeta.png").is_file()
    assert ok(tmp_path, "images", "check", "c", "v").endswith("ok")
    same = ytflow(tmp_path, "images", "import", "c", "v", "--from", str(video / "images"))
    assert same.returncode == 1 and "not the video's images/ folder" in same.stderr
