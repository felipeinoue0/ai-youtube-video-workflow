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


def ass_styles(ass: str) -> dict[str, dict[str, str]]:
    fields = ass.split("[V4+ Styles]\nFormat: ")[1].splitlines()[0].split(", ")
    styles = {}
    for line in re.findall(r"^Style: (.*)$", ass, re.M):
        values = dict(zip(fields, line.split(","), strict=True))
        styles[values["Name"]] = values
    return styles


def dialogues(ass: str) -> list[tuple[str, ...]]:
    return re.findall(r"^Dialogue: (\d),([^,]+),([^,]+),(\w+),,0,0,0,,(.*)$", ass, re.M)


def test_subtitles_ass_has_one_box_per_subtitle_and_top_left_chapters(tmp_path: Path) -> None:
    video = setup(tmp_path)
    ok(tmp_path, "timeline", "build", "c", "v")
    ass = (video / "timeline" / "v1" / "subtitles.ass").read_text()
    assert "PlayResX: 1920\nPlayResY: 1080" in ass
    assert "[Kdenlive Extradata]\nMaxLayer: 1\nDefaultStyles: Default,Chapter" in ass  # as Kdenlive writes it
    styles = ass_styles(ass)
    subtitle, chapter = styles["Default"], styles["Chapter"]
    assert subtitle["BorderStyle"] == "4" and chapter["BorderStyle"] == "4"  # one box around the whole text
    assert subtitle["BackColour"] == "&H66000000" and subtitle["OutlineColour"] == "&HFF000000"  # no glyph outline
    assert subtitle["Outline"] == "12"  # the box's padding
    assert subtitle["Alignment"] == "2" and chapter["Alignment"] == "7"  # bottom centre; top left
    assert subtitle["Fontsize"] == "48" and chapter["MarginL"] == "48"
    found = dialogues(ass)
    assert [d[3] for d in found].count("Chapter") == 2 and [d[3] for d in found].count("Default") == 5
    assert ("1", "0:00:01.00", "0:00:06.00", "Chapter", "{\\an7\\fad(180,220)}The Silver Age") in found


CHANNEL_PRESET = """
[subtitles]
font = "Noto Sans"
size = 100
bold = true
color = "#ffffff"
box_color = "#20150d"
box_opacity = 0.56
box_padding = 15
box_style = "lines"
max_chars_per_line = 26
highlight_color = "#ffd166"
fade_ms = 65

[chapters]
size = 54
color = "#ffefdc"
box_opacity = 0.75
underline = true
slide = true
margin = 90
"""


def test_long_phrases_become_short_blocks_with_highlights_and_the_channel_style(tmp_path: Path) -> None:
    long = "one two three four **five six** seven eight nine ten eleven twelve thirteen fourteen fifteen **sixteen**"
    script = f"# T\n## A\n- {long}.\n- Short one here.\n## B\n- Another phrase.\n"
    video = setup(tmp_path, script, {"01_a.wav": 4.0, "02_b.wav": 2.0})
    preset = kit_dir(tmp_path) / "edit-preset.toml"
    preset.write_text(
        preset.read_text().split("[subtitles]")[0]
        + CHANNEL_PRESET
        + "\n[video]\n"
        + preset.read_text().split("[video]")[1]
    )
    assert "edit-preset.toml: ok" in ok(tmp_path, "kit", "check", "c", "--file", "edit-preset.toml").stdout
    out = ok(tmp_path, "timeline", "build", "c", "v").stdout
    assert "subtitle lines" not in out  # no more "split the phrase" warnings: it is split into blocks
    data = json.loads((video / "timeline" / "v1" / "timeline.json").read_text())
    first = [s for s in data["subtitles"] if s["name"].startswith("001_")]
    assert len(first) >= 2 and all(len(s["lines"]) <= 2 and max(map(len, s["lines"])) <= 26 for s in first)
    assert " ".join(s["text"] for s in first) == long.replace("**", "") + "."
    for a, b in zip(first, first[1:], strict=False):
        assert a["end"] == b["start"]  # consecutive blocks inside the phrase's time
    highlighted = [s["text"][x:y] for s in first for x, y in s["highlights"]]
    assert highlighted == ["five six", "sixteen"]

    ass = (video / "timeline" / "v1" / "subtitles.ass").read_text()
    styles = ass_styles(ass)
    assert styles["Default"]["Fontsize"] == "100" and styles["Default"]["Bold"] == "-1"
    assert styles["Default"]["BackColour"] == "&H700D1520" and styles["Default"]["BorderStyle"] == "3"
    assert styles["Chapter"]["PrimaryColour"] == "&H00DCEFFF" and styles["Chapter"]["Underline"] == "-1"
    texts = [d[4] for d in dialogues(ass) if d[3] == "Default"]
    assert texts[0].startswith("{\\fad(65,65)}") and "\\N" in texts[0]
    # the colour opens before the highlight and closes after it, across a line break if there is one
    assert re.search(r"\{\\c&H66D1FF&\}five(\\N| )six\{\\c&HFFFFFF&\}", "".join(texts))
    assert "{\\c&H66D1FF&}sixteen{\\c&HFFFFFF&}" in "".join(texts)
    chapter = next(d[4] for d in dialogues(ass) if d[3] == "Chapter")
    assert chapter.startswith("{\\an7\\fad(180,220)\\move(108,90,90,90,0,300)}")


def test_highlight_marks_stay_out_of_names_words_and_narration(tmp_path: Path) -> None:
    script = "# T\n## A\n- Ganhar uma **renda extra** hoje.\n## B\n- Outra **frase** aqui.\n"
    video = setup(tmp_path, script, {"01_a.wav": 2.0, "02_b.wav": 2.0})
    data = json.loads((video / "script" / "v1" / "script.json").read_text())
    phrase = data["phrases"][0]
    assert phrase["text"] == "Ganhar uma renda extra hoje." and phrase["highlights"] == [[11, 22]]
    assert phrase["name"] == "001_ganhar-uma-renda-extra-hoje" and phrase["words"] == 5
    assert "**" not in (video / "voiceover" / "v1" / "narration.txt").read_text()
    assert "| Ganhar uma **renda extra** hoje. |" in (video / "script" / "v1" / "transcript.md").read_text()
    version = video / "script" / "v1"
    (version / "script.md").write_text("# T\n## A\n- Aberto **sem fechar.\n")
    bad = ytflow(tmp_path, "script", "build", "c", "v")
    assert bad.returncode == 1 and "highlight is never closed" in bad.stdout


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


def tc_frames(value: str, fps: int = 30) -> int:
    """An MLT timecode (00:00:03.067) as a frame number."""
    h, m, s = value.split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * fps)


def track_positions(playlist) -> list[tuple[int, int, object]]:
    """(start frame, length, entry element) for each entry of a playlist, blanks counted."""
    clock, out = 0, []
    for child in playlist:
        if child.tag == "blank":
            clock += tc_frames(child.get("length"))
        elif child.tag == "entry":
            length = tc_frames(child.get("out")) - tc_frames(child.get("in")) + 1
            out.append((clock, length, child))
            clock += length
    return out


def prop(element, name: str) -> str | None:
    found = element.find(f"property[@name='{name}']")
    return None if found is None else found.text


def fades(entry) -> dict[str, dict]:
    return {
        prop(f, "kdenlive_id"): {**f.attrib, "alpha": prop(f, "alpha"), "level": prop(f, "level")}
        for f in entry.findall("filter")
        if prop(f, "mlt_service") == "brightness"
    }


def export(tmp_path: Path, *extra: str):
    import xml.etree.ElementTree as ET

    result = ok(tmp_path, "export", "kdenlive", "c", "v", *extra)
    project = Path(result.stdout.splitlines()[0])
    return result, project, ET.parse(project).getroot()


def test_export_kdenlive_writes_a_native_sequence_project(tmp_path: Path) -> None:
    video = setup(tmp_path)
    early = ytflow(tmp_path, "export", "kdenlive", "c", "v")
    assert early.returncode == 1 and "ytflow timeline build c v" in early.stderr
    ok(tmp_path, "timeline", "build", "c", "v")
    version = video / "timeline" / "v1"
    result, project, root = export(tmp_path)
    assert project == version / "v.kdenlive"
    assert "paths relative" in result.stdout
    assert "note: exported as dissolves in Kdenlive: wipe-left, wipe-right" in result.stdout
    data = json.loads((version / "timeline.json").read_text())

    def f(seconds: float) -> int:
        return round(seconds * 30)

    # the 1.1 document: one sequence (uuid everywhere it is named) inside the project tractor
    assert root.tag == "mlt" and root.get("producer") == "main_bin" and root.get("root") is None
    main_bin = root.find("playlist[@id='main_bin']")
    assert prop(main_bin, "kdenlive:docproperties.version") == "1.1"
    sequence = root.find("tractor[@id='tractor3']")
    document_uuid = prop(main_bin, "kdenlive:docproperties.uuid")
    assert re.fullmatch(r"\{[0-9a-f-]{36}\}", document_uuid)
    for value in (
        prop(main_bin, "kdenlive:docproperties.opensequences"),
        prop(main_bin, "kdenlive:docproperties.activetimeline"),
        prop(sequence, "kdenlive:uuid"),
        prop(sequence, "kdenlive:sequenceproperties.documentuuid"),
    ):
        assert value == document_uuid
    assert prop(sequence, "kdenlive:producer_type") == "17" and prop(sequence, "kdenlive:clipname") == "T"
    assert [t.get("producer") for t in sequence.findall("track")] == ["producer0", "tractor0", "tractor1", "tractor2"]
    project_tractor = root.find("tractor[@id='tractor4']")
    assert prop(project_tractor, "kdenlive:projectTractor") == "1"
    assert [t.get("producer") for t in project_tractor.findall("track")] == ["tractor3"]
    assert [c.get("id") for c in root][-3:] == ["tractor3", "main_bin", "tractor4"]
    assert main_bin.findall("entry")[-1].get("producer") == "tractor3"
    for element in [*root.iter("producer"), *root.iter("chain")]:  # every media path resolves from the project
        resource = prop(element, "resource")
        if resource != "black":
            assert (project.parent / resource).is_file(), resource

    # images alternate: lower track even clips, upper track odd clips, at their timeline positions
    lower = track_positions(root.find("playlist[@id='playlist2']"))
    upper = track_positions(root.find("playlist[@id='playlist4']"))
    assert len(lower) == 3 and len(upper) == 2
    placed = sorted(lower + upper, key=lambda item: item[0])
    producers = {p.get("id"): p for p in root.iter("producer")}
    for index, ((start, length, entry), clip) in enumerate(zip(placed, data["clips"], strict=True)):
        assert start == f(clip["start"]) and length == f(clip["end"]) - f(clip["start"])
        assert prop(producers[entry.get("producer")], "resource") == f"../../{clip['image']}"
        transform = next(x for x in entry.findall("filter") if prop(x, "mlt_service") == "qtblend")
        first = prop(transform, "rect").split(";")[0]
        view = clip["camera"]["from"]
        x, y, w, h, _ = (float(v) for v in first.split("=")[1].split())
        assert w == pytest.approx(1920 / view["w"], abs=0.01) and x == pytest.approx(-view["x"] * w, abs=0.01)
        assert (entry in [e for _, _, e in upper]) == (index % 2 == 1)

    # a dissolve is the upper clip fading its alpha in and out; the lower clips carry no dissolve
    n = f(0.6)
    for _, length, entry in upper:
        fade_in, fade_out = fades(entry)["fade_from_black"], fades(entry)["fade_to_black"]
        assert fade_in["alpha"] == f"00:00:00.000=0;{tc(n - 1)}=1" and fade_in["level"] == "1"
        assert fade_out["alpha"] == f"00:00:00.000=1;{tc(n - 1)}=0" and tc_frames(fade_out["in"]) == length - n
    first_lower, last_lower = lower[0][2], lower[-1][2]
    assert fades(first_lower)["fade_from_black"]["level"] == f"00:00:00.000=0;{tc(f(1.0) - 1)}=1"  # video fade in
    assert fades(last_lower)["fade_to_black"]["level"].endswith("=0")  # the last clip fades to black
    assert not fades(lower[1][2])
    assert not [t for t in root.iter("transition") if prop(t, "internal_added") is None]  # no compositions

    # narration on A1 at its start
    a1 = track_positions(root.find("playlist[@id='playlist0']"))
    chains = {c.get("id"): c for c in root.iter("chain")}
    assert [(start, prop(chains[e.get("producer")], "resource")) for start, _, e in a1] == [
        (f(a["start"]), f"../../{a['file']}") for a in data["audio"]
    ]

    # subtitles: Kdenlive's own file name next to the project, listed in the sequence and filtered
    subtitle_file = version / "v.kdenlive.ass"
    assert subtitle_file.read_text() == (version / "subtitles.ass").read_text()
    listed = json.loads(prop(sequence, "kdenlive:sequenceproperties.subtitlesList"))
    assert listed == [{"id": 0, "name": "Legendas", "file": "v.kdenlive.ass"}]
    subtitle_filter = next(x for x in sequence.findall("filter") if prop(x, "mlt_service") == "avfilter.subtitles")
    assert prop(subtitle_filter, "av.filename") == "v.kdenlive.ass"

    # chapters are guides
    guides = json.loads(prop(sequence, "kdenlive:sequenceproperties.guides"))
    assert guides == [
        {"pos": 0, "duration": 0, "comment": "The Silver Age", "type": 0},
        {"pos": f(data["chapters"][1]["start"]), "duration": 0, "comment": "Soldiers", "type": 0},
    ]


def tc(frame: int, fps: int = 30) -> str:
    ms = round(frame * 1000 / fps)
    return f"00:00:{ms // 1000:02d}.{ms % 1000:03d}"


def test_export_kdenlive_writes_absolute_paths_under_the_host_root(tmp_path: Path) -> None:
    setup(tmp_path)
    ok(tmp_path, "timeline", "build", "c", "v")
    result, project, root = export(tmp_path, "--host-root", "/home/someone/ws")
    folder = "/home/someone/ws/channels/c/videos/v"
    assert "paths absolute under /home/someone/ws" in result.stdout
    assert root.get("root") == f"{folder}/timeline/v1"
    resources = [prop(p, "resource") for p in root.iter("producer") if prop(p, "resource") != "black"]
    assert resources and all(r.startswith(f"{folder}/images/") for r in resources)
    sequence = root.find("tractor[@id='tractor3']")
    listed = json.loads(prop(sequence, "kdenlive:sequenceproperties.subtitlesList"))
    assert listed[0]["file"] == f"{folder}/timeline/v1/v.kdenlive.ass"
