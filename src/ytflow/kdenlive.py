"""Export the timeline as a Kdenlive project (MLT XML).

The project is written in the plain pre-sequence layout (document version
1.04): Kdenlive upgrades it on open, which is steadier across Kdenlive releases
than imitating the newest format. The layout:

- **V1 and V2** take the clips in turn (A/B), so each transition is a
  composition over the clips' overlap: ``dissolve`` and ``wipe-*`` are luma
  compositions (each wipe's greyscale map is written to ``lumas/`` next to the
  project), ``slide-*`` a composite with an animated geometry.
- Each clip carries a **Transform** (``qtblend``) effect whose ``rect`` moves
  from the camera's start view to its end view: the slow pan or zoom.
- The first clip fades from black and the last one fades to black (the
  narration starts after the lead-in and ends before the tail, so it needs no fade).
- **A1** holds the narration, each file at its timeline start.
- The subtitles and chapter titles are the timeline's ``subtitles.ass``, on the
  project's subtitle filter.

Paths are relative to the project file, so the video folder can move.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path

DOCUMENT_VERSION = "1.04"
INTERNAL = "237"  # Kdenlive's marker for compositions it manages itself

LUMA_DIR = "lumas"
LUMA_SIZE = (640, 360)  # the luma transition scales its map to the frame
# A luma map is a greyscale picture: the darkest pixels change to the incoming
# image first. Each wipe gets its own map, written next to the project, so the
# project depends on no file inside MLT's or Kdenlive's installation.
WIPES = ("wipe-left", "wipe-right", "wipe-up", "wipe-down")
OPPOSITE = {"wipe-left": "wipe-right", "wipe-right": "wipe-left", "wipe-up": "wipe-down", "wipe-down": "wipe-up"}


def luma_map(kind: str, width: int = LUMA_SIZE[0], height: int = LUMA_SIZE[1]) -> bytes:
    """A 16-bit PGM gradient for a wipe: wipe-left reveals from the right edge, wipe-up from the bottom."""
    top = 65535

    def value(x: int, y: int) -> int:
        fx, fy = x / (width - 1), y / (height - 1)
        share = {"wipe-left": 1 - fx, "wipe-right": fx, "wipe-up": 1 - fy, "wipe-down": fy}[kind]
        return round(share * top)

    rows = bytearray()
    for y in range(height):
        if kind in ("wipe-left", "wipe-right"):
            row = b"".join(value(x, 0).to_bytes(2, "big") for x in range(width))
        else:
            row = value(0, y).to_bytes(2, "big") * width
        rows += row
    return f"P5\n{width} {height}\n{top}\n".encode() + bytes(rows)


SLIDE_FROM = {  # where the incoming image starts, as an x y offset in frames of the picture size
    "slide-left": (1, 0),
    "slide-right": (-1, 0),
    "slide-up": (0, 1),
    "slide-down": (0, -1),
}


def frames(seconds: float, fps: int) -> int:
    return round(seconds * fps)


def timecode(frame: int, fps: int) -> str:
    total_ms = round(frame * 1000 / fps)
    h, rest = divmod(total_ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def props(element: ET.Element, values: dict[str, object]) -> ET.Element:
    for name, value in values.items():
        prop = ET.SubElement(element, "property", name=name)
        prop.text = "" if value is None else str(value)
    return element


def view_rect(view: dict, width: int, height: int) -> str:
    """The qtblend rect that shows ``view`` (fractions of the image) across the whole frame."""
    w, h = width / view["w"], height / view["h"]
    x, y = -view["x"] * w, -view["y"] * h
    return f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} 1"


def relative(path: str, project_dir: Path, video_dir: Path) -> str:
    return os.path.relpath(video_dir / path, project_dir)


class Builder:
    def __init__(self, timeline: dict, project_dir: Path, video_dir: Path) -> None:
        self.t = timeline
        self.v = timeline["video"]
        self.fps = self.v["fps"]
        self.project_dir, self.video_dir = project_dir, video_dir
        self.total = frames(self.v["duration"], self.fps)
        self.root = ET.Element("mlt", LC_NUMERIC="C", producer="main_bin", version="7.0.0")
        self.next_id = 2
        self.bin: list[tuple[str, int]] = []  # (producer id, length)
        self.lumas: set[str] = set()  # luma map files the compositions use, relative to the project

    def fr(self, seconds: float) -> int:
        return frames(seconds, self.fps)

    def profile(self) -> None:
        ET.SubElement(
            self.root,
            "profile",
            description=f"{self.v['width']}x{self.v['height']} {self.fps} fps",
            width=str(self.v["width"]),
            height=str(self.v["height"]),
            progressive="1",
            sample_aspect_num="1",
            sample_aspect_den="1",
            display_aspect_num=str(self.v["width"] // gcd(self.v["width"], self.v["height"])),
            display_aspect_den=str(self.v["height"] // gcd(self.v["width"], self.v["height"])),
            frame_rate_num=str(self.fps),
            frame_rate_den="1",
            colorspace="709",
        )

    def producer(self, pid: str, resource: str, service: str, length: int, kid: int, extra: dict) -> ET.Element:
        element = ET.SubElement(self.root, "producer", id=pid, attrib={"in": "0", "out": str(length - 1)})
        return props(
            element,
            {
                "length": length,
                "eof": "pause",
                "resource": resource,
                "mlt_service": service,
                "kdenlive:id": kid,
                "kdenlive:clipname": Path(resource).stem,
                "kdenlive:folderid": -1,
                **extra,
            },
        )

    def media(self) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
        """Bin and timeline producers for every image and audio file."""
        image_ids: dict[str, int] = {}
        clips = []
        for n, clip in enumerate(self.t["clips"]):
            resource = relative(clip["image"], self.project_dir, self.video_dir)
            if clip["image"] not in image_ids:
                image_ids[clip["image"]] = self.next_id
                self.next_id += 1
                pid = f"bin{image_ids[clip['image']]}"
                image = {"ttl": 25, "aspect_ratio": 1, "progressive": 1, "seekable": 1}
                self.producer(pid, resource, "qimage", 15000, image_ids[clip["image"]], image)
                self.bin.append((pid, 15000))
            length = self.fr(clip["end"]) - self.fr(clip["start"])
            pid = f"clip{n}"
            self.producer(
                pid,
                resource,
                "qimage",
                length,
                image_ids[clip["image"]],
                {"ttl": 25, "aspect_ratio": 1, "progressive": 1, "seekable": 1},
            )
            clips.append((pid, clip))
        sounds = []
        for n, audio in enumerate(self.t["audio"]):
            resource = relative(audio["file"], self.project_dir, self.video_dir)
            length = self.fr(audio["duration"])
            kid = self.next_id
            self.next_id += 1
            self.producer(f"bin{kid}", resource, "avformat", length, kid, {"seekable": 1, "audio_index": 0})
            self.bin.append((f"bin{kid}", length))
            self.producer(f"audio{n}", resource, "avformat", length, kid, {"seekable": 1, "audio_index": 0})
            sounds.append((f"audio{n}", audio))
        return clips, sounds

    def clip_filters(self, entry: ET.Element, clip: dict, index: int, last: int) -> None:
        length = self.fr(clip["end"]) - self.fr(clip["start"])
        move = clip["camera"]
        width, height = self.v["width"], self.v["height"]
        rect = (
            f"{timecode(0, self.fps)}={view_rect(move['from'], width, height)};"
            f"{timecode(length - 1, self.fps)}={view_rect(move['to'], width, height)}"
        )
        transform = ET.SubElement(entry, "filter")
        props(
            transform,
            {
                "mlt_service": "qtblend",
                "kdenlive_id": "qtblend",
                "rect": rect,
                "rotation": "0",
                "compositing": 0,
                "distort": 0,
                "rotate_center": 1,
                "kdenlive:camera_move": move["type"],
            },
        )
        if index == 0 and self.v["fade_in"] > 0:
            fade = self.fr(self.v["fade_in"])
            props(
                ET.SubElement(entry, "filter", attrib={"in": "0", "out": str(fade - 1)}),
                {
                    "mlt_service": "brightness",
                    "kdenlive_id": "fade_from_black",
                    "start": 0,
                    "level": f"{timecode(0, self.fps)}=0;{timecode(fade - 1, self.fps)}=1",
                    "alpha": 1,
                },
            )
        if index == last and self.v["fade_out"] > 0:
            fade = self.fr(self.v["fade_out"])
            props(
                ET.SubElement(entry, "filter", attrib={"in": str(length - fade), "out": str(length - 1)}),
                {
                    "mlt_service": "brightness",
                    "kdenlive_id": "fade_to_black",
                    "level": f"{timecode(0, self.fps)}=1;{timecode(fade - 1, self.fps)}=0",
                    "alpha": 1,
                },
            )

    def playlist(self, pid: str, items: list[tuple[int, int, str]], audio: bool) -> ET.Element:
        """A track playlist from (start frame, length, producer id), with blanks between."""
        element = ET.SubElement(self.root, "playlist", id=pid)
        if audio:
            props(element, {"kdenlive:audio_track": 1})
        clock = 0
        for start, length, producer in sorted(items):
            if start > clock:
                ET.SubElement(element, "blank", length=str(start - clock))
            ET.SubElement(element, "entry", producer=producer, attrib={"in": "0", "out": str(length - 1)})
            clock = start + length
        return element

    def track(self, tid: str, playlist: str, audio: bool, name: str) -> None:
        empty = ET.SubElement(self.root, "playlist", id=f"{playlist}_b")
        if audio:
            props(empty, {"kdenlive:audio_track": 1})
        tractor = ET.SubElement(self.root, "tractor", id=tid, attrib={"in": "0", "out": str(self.total - 1)})
        extra = {"kdenlive:audio_track": 1} if audio else {}
        props(tractor, {**extra, "kdenlive:track_name": name, "kdenlive:trackheight": 69, "kdenlive:collapsed": 0})
        hide = "video" if audio else "audio"
        ET.SubElement(tractor, "track", hide=hide, producer=playlist)
        ET.SubElement(tractor, "track", hide=hide, producer=f"{playlist}_b")

    def composition(self, tractor: ET.Element, transition: dict, a: int, b: int, incoming_on_b: bool) -> None:
        start = self.fr(transition["at"] - transition["seconds"] / 2)
        end = start + self.fr(transition["seconds"]) - 1
        kind = transition["type"]
        element = ET.SubElement(tractor, "transition", attrib={"in": str(start), "out": str(end)})
        common = {"a_track": a, "b_track": b, "kdenlive:transition_type": kind}
        if kind == "dissolve" or kind in WIPES:
            resource = ""
            if kind in WIPES:
                # luma goes from a to b; run backwards (incoming clip on a), the map's order flips
                # too, so the opposite map keeps the wipe travelling the way its name says
                resource = f"{LUMA_DIR}/{kind if incoming_on_b else OPPOSITE[kind]}.pgm"
                self.lumas.add(resource)
            props(
                element,
                {
                    **common,
                    "mlt_service": "luma",
                    "kdenlive_id": "dissolve" if kind == "dissolve" else "wipe",
                    "resource": resource,
                    "softness": 0.05 if resource else 0,
                    "reverse": int(not incoming_on_b),
                },
            )
        else:
            dx, dy = SLIDE_FROM[kind]
            w, h = self.v["width"], self.v["height"]
            length = end - start
            if incoming_on_b:  # the incoming clip slides in over the outgoing one
                geometry = f"0={dx * w} {dy * h} {w} {h} 1;{length}=0 0 {w} {h} 1"
            else:  # the outgoing clip (on b) slides out the other way
                geometry = f"0=0 0 {w} {h} 1;{length}={-dx * w} {-dy * h} {w} {h} 1"
            props(
                element,
                {
                    **common,
                    "mlt_service": "composite",
                    "kdenlive_id": "slide",
                    "geometry": geometry,
                    "progressive": 1,
                    "distort": 0,
                    "fill": 1,
                },
            )

    def build(self, subtitles_file: str) -> ET.Element:
        self.profile()
        black = ET.SubElement(self.root, "producer", id="black_track", attrib={"in": "0", "out": str(self.total - 1)})
        props(
            black,
            {
                "length": self.total,
                "eof": "continue",
                "resource": "black",
                "aspect_ratio": 1,
                "mlt_service": "color",
                "kdenlive:playlistid": "black_track",
                "mlt_image_format": "rgba",
                "set.test_audio": 0,
            },
        )
        clips, sounds = self.media()

        # A1: narration; V1/V2: clips in turn
        audio_items = [(self.fr(a["start"]), self.fr(a["duration"]), pid) for pid, a in sounds]
        self.playlist("playlist_a1", audio_items, audio=True)
        for track_no in (0, 1):
            element = ET.SubElement(self.root, "playlist", id=f"playlist_v{track_no + 1}")
            clock = 0
            for index, (pid, clip) in enumerate(clips):
                if index % 2 != track_no:
                    continue
                start, end = self.fr(clip["start"]), self.fr(clip["end"])
                if start > clock:
                    ET.SubElement(element, "blank", length=str(start - clock))
                entry = ET.SubElement(element, "entry", producer=pid, attrib={"in": "0", "out": str(end - start - 1)})
                self.clip_filters(entry, clip, index, len(clips) - 1)
                clock = end
        self.track("tractor_a1", "playlist_a1", True, "Narration")
        self.track("tractor_v1", "playlist_v1", False, "Images A")
        self.track("tractor_v2", "playlist_v2", False, "Images B")

        # the bin, with the document properties
        main_bin = ET.SubElement(self.root, "playlist", id="main_bin")
        props(
            main_bin,
            {
                "kdenlive:docproperties.version": DOCUMENT_VERSION,
                "kdenlive:docproperties.profile": "",
                "kdenlive:docproperties.audioChannels": 2,
                "kdenlive:docproperties.enableproxy": 0,
                "kdenlive:docproperties.generator": "ytflow",
                "xml_retain": 1,
            },
        )
        for pid, length in self.bin:
            ET.SubElement(main_bin, "entry", producer=pid, attrib={"in": "0", "out": str(length - 1)})

        # main tractor: black, A1, V1, V2 (track indexes 0–3)
        tractor = ET.SubElement(
            self.root, "tractor", id="maintractor", global_feed="1", attrib={"in": "0", "out": str(self.total - 1)}
        )
        props(tractor, {"kdenlive:projectTractor": 1})
        for producer in ("black_track", "tractor_a1", "tractor_v1", "tractor_v2"):
            ET.SubElement(tractor, "track", producer=producer)
        props(
            ET.SubElement(tractor, "transition"),
            {
                "a_track": 0,
                "b_track": 1,
                "mlt_service": "mix",
                "kdenlive_id": "mix",
                "internal_added": INTERNAL,
                "always_active": 1,
                "accepts_blanks": 1,
                "sum": 1,
            },
        )
        for b in (2, 3):
            props(
                ET.SubElement(tractor, "transition"),
                {
                    "a_track": 0,
                    "b_track": b,
                    "mlt_service": "qtblend",
                    "kdenlive_id": "qtblend",
                    "internal_added": INTERNAL,
                    "always_active": 1,
                    "compositing": 0,
                    "distort": 0,
                },
            )
        for index, transition in enumerate(self.t["transitions"]):
            if transition["type"] != "cut":
                # clip index+1 comes in; it is on V2 (track 3) when its index is odd
                self.composition(tractor, transition, 2, 3, incoming_on_b=(index + 1) % 2 == 1)
        props(
            ET.SubElement(tractor, "filter"),
            {
                "mlt_service": "avfilter.subtitles",
                "internal_added": INTERNAL,
                "av.filename": subtitles_file,
                "disable": 0,
            },
        )
        return self.root


def export(timeline: dict, project: Path, video_dir: Path, subtitles: Path) -> Path:
    """Write the project file; returns its path."""
    builder = Builder(timeline, project.parent, video_dir)
    root = builder.build(os.path.relpath(subtitles, project.parent))
    for resource in sorted(builder.lumas):
        path = project.parent / resource
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(luma_map(Path(resource).stem))
    ET.indent(root)
    project.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
    return project
