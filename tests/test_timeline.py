"""The editor-neutral timeline, its ASS subtitles and the ffmpeg preview — driven through the CLI process."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ytflow.timeline import transition_types, wrap

STYLE = """+++
words_per_minute = 150
phrase_words_target = 8
phrase_words_max = 20
+++
"""

VOICE = """+++
voice = "Adam"
model = "eleven_multilingual_v2"
stability = 0.5
similarity = 0.75
style = 0.0
speed = 1.0
chapter_break = 1.0
+++
"""

SCRIPT = """# T
## The Silver Age
- Alpha beta gamma delta.
- Epsilon zeta eta.
- Theta iota kappa lambda mu.
## Soldiers
- Nu xi omicron pi rho sigma.
- Tau upsilon phi.
"""

# chapter audio lengths in seconds (silence: the character-count method times it)
CHAPTER_AUDIO = {"01_the-silver-age.wav": 6.0, "02_soldiers.wav": 4.0}


def ytflow(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ytflow", "--root", str(root), *args], capture_output=True, text=True, check=False
    )


def ok(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = ytflow(root, *args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def ffmpeg(*args: str) -> None:
    assert shutil.which("ffmpeg"), "ffmpeg is required for these tests (it is in the dev image)"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def kit_dir(root: Path) -> Path:
    return root / "channels" / "c" / "kit" / "v1"


def setup(root: Path, script: str = SCRIPT, audio: dict[str, float] = CHAPTER_AUDIO, images: bool = True) -> Path:
    ok(root, "channel", "new", "c")
    kit = kit_dir(root)
    (kit / "style-guide.md").write_text(STYLE)
    (kit / "voice.md").write_text(VOICE)
    preset = kit / "edit-preset.toml"
    preset.write_text("\n".join(line for line in preset.read_text().splitlines() if "TODO(ytflow)" not in line))
    ok(root, "video", "new", "c", "v")
    video = root / "channels" / "c" / "videos" / "v"
    version = Path(ok(root, "version", "new", str(video / "script")).stdout.strip())
    (version / "script.md").write_text(script)
    ok(root, "script", "build", "c", "v")
    ok(root, "voiceover", "text", "c", "v")
    for name, seconds in audio.items():
        ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", str(seconds), str(video / "audio" / name))
    ok(root, "align", "c", "v", "--method", "chapters")
    if images:
        phrases = json.loads((version / "script.json").read_text())["phrases"]
        for i, phrase in enumerate(phrases):
            colour = "0xF4EEDC" if i % 2 == 0 else "0x0E1626"
            ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"color=c={colour}:s=320x180",
                "-frames:v",
                "1",
                str(video / "images" / f"{phrase['name']}.png"),
            )
    return video


def on_frame(seconds: float, fps: int = 30) -> bool:
    return abs(seconds * fps - round(seconds * fps)) < 0.01  # times are stored to 4 decimals


def test_timeline_build_lays_out_clips_transitions_subtitles_and_chapters(tmp_path: Path) -> None:
    video = setup(tmp_path)
    result = ok(tmp_path, "timeline", "build", "c", "v")
    version = video / "timeline" / "v1"
    assert result.stdout.splitlines()[0] == str(version / "timeline.json")
    assert "timeline v1: 5 clips, 0:13, 2 chapter titles" in result.stdout
    data = json.loads((version / "timeline.json").read_text())
    timing = json.loads((video / "timing" / "v1" / "timing.json").read_text())

    assert data["sources"] == {
        "script_version": "v1",
        "voiceover_version": "v1",
        "timing_version": "v1",
        "kit_version": "v1",
    }
    lead = 0.5
    # narration 6 s + 1 s chapter break + 4 s, after a 0.5 s lead and before a 1.5 s tail
    assert data["video"] == {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration": 13.0,
        "fade_in": 1.0,
        "fade_out": 1.5,
    }
    assert [a["start"] for a in data["audio"]] == [0.5, 7.5]

    clips, transitions = data["clips"], data["transitions"]
    assert [c["image"] for c in clips] == [f"images/{p['name']}.png" for p in timing["phrases"]]
    assert clips[0]["start"] == 0.0 and clips[-1]["end"] == 13.0
    for i, transition in enumerate(transitions):
        phrase = timing["phrases"][i + 1]
        assert transition["at"] == round(round((lead + phrase["start"]) * 30) / 30, 4)  # the cut is where it is spoken
        assert transition["seconds"] == 0.6
        assert clips[i]["end"] == pytest.approx(transition["at"] + 0.3, abs=1e-3)  # overlap centred on the cut
        assert clips[i + 1]["start"] == pytest.approx(transition["at"] - 0.3, abs=1e-3)
    # the chapter change (between clips 3 and 4) is the calm type; inside a chapter, varied and calm alternate
    assert [t["type"] for t in transitions] == ["wipe-left", "dissolve", "dissolve", "wipe-right"]

    moves = [c["camera"] for c in clips]
    assert [m["type"] for m in moves] == ["zoom-in", "zoom-out", "pan-left", "pan-right", "zoom-in"]
    for clip, move in zip(clips, moves, strict=True):
        assert 1 < move["zoom"] <= 1.12
        assert move["zoom"] == pytest.approx(1 + min(0.12, 0.03 * (clip["end"] - clip["start"])), abs=1e-3)
        for end in (move["from"], move["to"]):
            assert 0 <= end["x"] and end["x"] + end["w"] <= 1.0001 and 0 <= end["y"] and end["y"] + end["h"] <= 1.0001
    assert moves[0]["from"] == {"x": 0, "y": 0, "w": 1, "h": 1}  # zoom-in starts on the whole image
    assert moves[2]["from"]["x"] > moves[2]["to"]["x"]  # pan-left: the view travels left

    subtitles = data["subtitles"]
    assert [s["text"] for s in subtitles] == [p["text"] for p in timing["phrases"]]
    for current, following in zip(subtitles, subtitles[1:], strict=False):
        assert current["end"] - current["start"] >= 1.0
        assert current["end"] < following["start"]  # never overlapping
    chapters = data["chapters"]
    assert [(c["title"], c["start"]) for c in chapters] == [("The Silver Age", 1.0), ("Soldiers", 7.5)]
    assert chapters[1]["end"] == 11.5  # 5 s, or the chapter's end (7.5 + 4 s) if sooner

    times = [c["start"] for c in clips] + [c["end"] for c in clips] + [s["start"] for s in subtitles]
    assert all(on_frame(t) for t in times)


def test_subtitles_ass_has_a_box_style_and_top_left_chapters(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "timeline", "build", "c", "v")
    ass = (video / "timeline" / "v1" / "subtitles.ass").read_text()
    assert "PlayResX: 1920\nPlayResY: 1080" in ass
    fields = ass.split("[V4+ Styles]\nFormat: ")[1].splitlines()[0].split(", ")
    styles = {}
    for line in re.findall(r"^Style: (.*)$", ass, re.M):
        values = dict(zip(fields, line.split(","), strict=True))
        styles[values["Name"]] = values
    subtitle, chapter = styles["Subtitle"], styles["Chapter"]
    assert subtitle["BorderStyle"] == "3" and chapter["BorderStyle"] == "3"  # a box behind the text
    assert subtitle["OutlineColour"] == "&H66000000"  # black at 60% opacity
    assert subtitle["Alignment"] == "2" and chapter["Alignment"] == "7"  # bottom centre; top left
    assert subtitle["Fontsize"] == "48" and chapter["MarginL"] == "48"
    dialogues = re.findall(r"^Dialogue: (\d),([^,]+),([^,]+),(\w+),,0,0,0,,(.*)$", ass, re.M)
    assert [d[3] for d in dialogues].count("Chapter") == 2 and [d[3] for d in dialogues].count("Subtitle") == 5
    assert ("1", "0:00:01.00", "0:00:06.00", "Chapter", "{\\fad(400,400)}The Silver Age") in dialogues


def test_long_phrases_wrap_and_warn(tmp_path: Path) -> None:
    long = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
    script = f"# T\n## A\n- {long}.\n- Short one here.\n## B\n- Another phrase.\n"
    setup(tmp_path, script, {"01_a.wav": 3.0, "02_b.wav": 2.0})
    out = ok(tmp_path, "timeline", "build", "c", "v").stdout
    assert "warning: 001_one-two-three-four-five: 3 subtitle lines (the preset allows 2)" in out
    assert "characters per second is fast to read" in out


def test_wrap_balances_two_lines() -> None:
    assert wrap("A Roman coin rests on a merchant's table, bright under the afternoon sun.", 42) == [
        "A Roman coin rests on a merchant's",
        "table, bright under the afternoon sun.",
    ]
    assert wrap("Short line.", 42) == ["Short line."]


def test_transition_types_rotate_and_stay_calm_at_chapter_changes() -> None:
    types = ["dissolve", "wipe-left", "slide-up"]
    assert transition_types(types, 7, {3}) == [
        "wipe-left",
        "dissolve",
        "slide-up",
        "dissolve",  # chapter change
        "wipe-left",
        "dissolve",
        "slide-up",
    ]
    assert transition_types(["dissolve"], 3, set()) == ["dissolve"] * 3


def test_timeline_build_needs_images_and_a_ready_preset(tmp_path: Path) -> None:
    setup(tmp_path, images=False)
    missing = ytflow(tmp_path, "timeline", "build", "c", "v")
    assert (
        missing.returncode == 1 and "5 image(s) missing" in missing.stderr and "ytflow images check" in missing.stderr
    )
    preset = kit_dir(tmp_path) / "edit-preset.toml"
    preset.write_text(preset.read_text().replace('"slide-up"]', '"spin"]').replace("max_zoom = 1.12", "max_zoom = 2"))
    out = ytflow(tmp_path, "kit", "check", "c", "--file", "edit-preset.toml").stdout
    assert "unknown types: spin" in out and "[camera] max_zoom = 2 is outside 1–1.5" in out
    bad = ytflow(tmp_path, "timeline", "build", "c", "v")
    assert bad.returncode == 1 and "edit-preset.toml in kit v1 is not ready" in bad.stderr


def test_preview_renders_the_timeline(tmp_path: Path) -> None:
    video = setup(tmp_path, "# T\n## A\n- One two three.\n## B\n- Four five six.\n", {"01_a.wav": 1.5, "02_b.wav": 1.5})
    early = ytflow(tmp_path, "timeline", "preview", "c", "v")
    assert early.returncode == 1 and "ytflow timeline build c v" in early.stderr
    ok(tmp_path, "timeline", "build", "c", "v")
    result = ok(tmp_path, "timeline", "preview", "c", "v", "--scale", "0.2")
    output = video / "timeline" / "v1" / "preview.mp4"
    assert result.stdout.strip() == str(output)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height:format=duration",
            "-of",
            "json",
            output,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    duration = json.loads((video / "timeline" / "v1" / "timeline.json").read_text())["video"]["duration"]
    assert float(info["format"]["duration"]) == pytest.approx(duration, abs=0.1)
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video_stream["width"], video_stream["height"]) == (384, 216)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert not list((video / "timeline" / "v1").glob("*.filters.txt"))


def test_status_marks_the_timeline_done(tmp_path: Path) -> None:
    setup(tmp_path)
    ok(tmp_path, "timeline", "build", "c", "v")
    assert "timeline   v1" in ok(tmp_path, "status", "c", "v").stdout


def track_positions(playlist) -> list[tuple[int, int, object]]:
    """(start frame, length, entry element) for each entry of a playlist, blanks counted."""
    clock, out = 0, []
    for child in playlist:
        if child.tag == "blank":
            clock += int(child.get("length"))
        elif child.tag == "entry":
            length = int(child.get("out")) - int(child.get("in")) + 1
            out.append((clock, length, child))
            clock += length
    return out


def prop(element, name: str) -> str | None:
    found = element.find(f"property[@name='{name}']")
    return None if found is None else found.text


def test_export_kdenlive_writes_the_timeline_as_an_mlt_project(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    video = setup(tmp_path)
    early = ytflow(tmp_path, "export", "kdenlive", "c", "v")
    assert early.returncode == 1 and "ytflow timeline build c v" in early.stderr
    ok(tmp_path, "timeline", "build", "c", "v")
    version = video / "timeline" / "v1"
    project = Path(ok(tmp_path, "export", "kdenlive", "c", "v").stdout.strip())
    assert project == version / "v.kdenlive"
    data = json.loads((version / "timeline.json").read_text())
    fps = 30

    def f(seconds: float) -> int:
        return round(seconds * fps)

    root = ET.parse(project).getroot()
    assert root.tag == "mlt" and root.get("producer") == "main_bin"
    profile = root.find("profile")
    assert (profile.get("width"), profile.get("height"), profile.get("frame_rate_num")) == ("1920", "1080", "30")
    assert (profile.get("display_aspect_num"), profile.get("display_aspect_den")) == ("16", "9")
    main_bin = root.find("playlist[@id='main_bin']")
    assert prop(main_bin, "kdenlive:docproperties.version") == "1.04"
    # Kdenlive names the sequence it upgrades the timeline into after the document uuid:
    # a missing one becomes the null uuid, an "invalid sequence clip in bin"
    document_uuid = prop(main_bin, "kdenlive:docproperties.uuid")
    assert re.fullmatch(r"\{[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}\}", document_uuid)
    assert prop(main_bin, "kdenlive:docproperties.documentid").isdigit()
    again = ET.parse(Path(ok(tmp_path, "export", "kdenlive", "c", "v").stdout.strip())).getroot()
    assert (
        prop(again.find("playlist[@id='main_bin']"), "kdenlive:docproperties.uuid") != document_uuid
    )  # one per export
    producers = {p.get("id"): p for p in root.iter("producer")}
    for producer in producers.values():  # every media path resolves from the project's folder
        resource = prop(producer, "resource")
        if resource != "black":
            assert (project.parent / resource).is_file(), resource

    # V1/V2 alternate the clips at their timeline positions, each with its camera move
    v1 = track_positions(root.find("playlist[@id='playlist_v1']"))
    v2 = track_positions(root.find("playlist[@id='playlist_v2']"))
    placed = sorted(v1 + v2, key=lambda item: item[0])
    assert len(v1) == 3 and len(v2) == 2
    for (start, length, entry), clip in zip(placed, data["clips"], strict=True):
        assert start == f(clip["start"]) and length == f(clip["end"]) - f(clip["start"])
        producer = producers[entry.get("producer")]
        assert prop(producer, "resource") == f"../../{clip['image']}"
        transform = next(x for x in entry.findall("filter") if prop(x, "mlt_service") == "qtblend")
        first, last = prop(transform, "rect").split(";")
        view = clip["camera"]["from"]
        x, y, w, h, _ = (float(v) for v in first.split("=")[1].split())
        assert w == pytest.approx(1920 / view["w"], abs=0.01) and x == pytest.approx(-view["x"] * w, abs=0.01)
        assert last.startswith("00:00:")  # Kdenlive keyframe timecodes
    fades = [prop(x, "kdenlive_id") for _, _, e in placed for x in e.findall("filter")]
    assert fades.count("fade_from_black") == 1 and fades.count("fade_to_black") == 1
    assert prop(placed[0][2].findall("filter")[1], "kdenlive_id") == "fade_from_black"

    # one composition per cut over the clips' overlap, of the timeline's type
    tractor = root.find("tractor[@id='maintractor']")
    user = [t for t in tractor.findall("transition") if prop(t, "internal_added") is None]
    assert [prop(t, "kdenlive:transition_type") for t in user] == [t["type"] for t in data["transitions"]]
    for composition, transition in zip(user, data["transitions"], strict=True):
        start = f(transition["at"] - transition["seconds"] / 2)
        assert int(composition.get("in")) == start
        assert int(composition.get("out")) == start + f(transition["seconds"]) - 1
        assert (prop(composition, "a_track"), prop(composition, "b_track")) == ("2", "3")
    services = {prop(t, "kdenlive:transition_type"): prop(t, "mlt_service") for t in user}
    assert services == {"wipe-left": "luma", "dissolve": "luma", "wipe-right": "luma"}
    # the first cut brings clip 2 in on V2; the second brings clip 3 in on V1, so it runs backwards
    assert [prop(t, "reverse") for t in user[:2]] == ["0", "1"]
    # each wipe uses a luma map written next to the project — never a file inside MLT or Kdenlive,
    # which Kdenlive reports as a missing clip; run backwards, it uses the opposite direction's map
    opposite = {"wipe-left": "wipe-right", "wipe-right": "wipe-left"}
    wipes = [t for t in user if prop(t, "kdenlive_id") == "wipe"]
    assert wipes
    for wipe in wipes:
        kind = prop(wipe, "kdenlive:transition_type")
        expected = kind if prop(wipe, "reverse") == "0" else opposite[kind]
        assert prop(wipe, "resource") == f"lumas/{expected}.pgm"
    left = (project.parent / "lumas" / "wipe-left.pgm").read_bytes()
    header = b"P5\n640 360\n65535\n"
    assert left.startswith(header)
    row = left[len(header) : len(header) + 640 * 2]
    # wipe-left reveals from the right edge: the darkest values (first to change) on the right
    assert int.from_bytes(row[:2], "big") == 65535 and int.from_bytes(row[-2:], "big") == 0
    assert len(left) == len(header) + 640 * 360 * 2
    resources = [prop(t, "resource") or "" for t in root.iter("transition")]
    assert not any(r.startswith("%") for r in resources)

    # narration on A1 at its start; subtitles from the timeline's ASS file
    a1 = track_positions(root.find("playlist[@id='playlist_a1']"))
    assert [(start, prop(producers[e.get("producer")], "resource")) for start, _, e in a1] == [
        (f(a["start"]), f"../../{a['file']}") for a in data["audio"]
    ]
    subtitle = next(x for x in tractor.findall("filter") if prop(x, "mlt_service") == "avfilter.subtitles")
    assert prop(subtitle, "av.filename") == "subtitles.ass"
    tracks = [t.get("producer") for t in tractor.findall("track")]
    assert tracks == ["black_track", "tractor_a1", "tractor_v1", "tractor_v2"]


def test_export_kdenlive_slides(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    video = setup(tmp_path)
    preset = kit_dir(tmp_path) / "edit-preset.toml"
    preset.write_text(
        preset.read_text().replace(
            'types = ["dissolve", "wipe-left", "wipe-right", "slide-up"]', 'types = ["dissolve", "slide-up"]'
        )
    )
    ok(tmp_path, "timeline", "build", "c", "v")
    root = ET.parse(Path(ok(tmp_path, "export", "kdenlive", "c", "v").stdout.strip())).getroot()
    slides = [t for t in root.iter("transition") if prop(t, "kdenlive:transition_type") == "slide-up"]
    assert slides and all(prop(t, "mlt_service") == "composite" for t in slides)
    # clip 2 comes in on V2 (b): it starts one frame-height below and ends in place
    assert prop(slides[0], "geometry") == "0=0 1080 1920 1080 1;17=0 0 1920 1080 1"
    assert (video / "timeline" / "v1" / "v.kdenlive").is_file()
