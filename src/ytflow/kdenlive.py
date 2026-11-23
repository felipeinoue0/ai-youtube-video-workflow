"""Export the timeline as a Kdenlive project (MLT XML, document version 1.1).

The layout follows a project saved by Kdenlive 26.08 itself:

- a **sequence** tractor (with its uuid and ``kdenlive:sequenceproperties.*``)
  holding the black track, **A1** (the narration) and two image tracks, inside a
  **project tractor**; the bin keeps the images, the narration and the
  sequence in folders;
- the images alternate between the two image tracks. A **dissolve** is the
  upper clip fading its alpha in over the lower one, and out again to reveal the
  next lower clip — clip effects, no transition compositions, so the layer order
  cannot be wrong;
- each image carries a **Transform** (``qtblend``) effect whose ``rect`` goes
  from the camera's start view to its end view: the slow pan or zoom;
- the first image fades from black and the last one to black;
- the subtitles and chapter titles are the timeline's ASS file, copied next to
  the project as ``<project>.kdenlive.ass``, listed in the sequence's
  subtitles and rendered by its subtitle filter;
- each chapter is also a **guide** on the timeline.

Media paths are relative to the project file, or absolute when ``host_root``
says where the workspace is on the creator's machine (Kdenlive itself saves
absolute paths, and its subtitle list expects one).
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path

DOCUMENT_VERSION = "1.1"
INTERNAL = "237"  # Kdenlive's marker for effects and compositions it manages itself
IMAGE_TYPE, AUDIO_TYPE, SEQUENCE_TYPE = 2, 1, 17
FOLDERS = {"sequences": 2, "images": 3, "narration": 4}
# Kdenlive's profile names for the common sizes; others are described by the <profile> element alone.
PROFILES = {(1920, 1080, 30): "atsc_1080p_30", (1920, 1080, 25): "atsc_1080p_25", (1920, 1080, 60): "atsc_1080p_60"}


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
    return f"{x:.3f} {y:.3f} {w:.3f} {h:.3f} 1"


def new_uuid() -> str:
    return "{" + str(uuid.uuid4()) + "}"


class Builder:
    def __init__(
        self,
        timeline: dict,
        project: Path,
        video_dir: Path,
        title: str,
        host_root: tuple[Path, str] | None,
        image_sizes: dict[str, tuple[int, int]],
    ) -> None:
        self.t = timeline
        self.v = timeline["video"]
        self.fps = self.v["fps"]
        self.project, self.video_dir, self.title = project, video_dir, title
        self.host_root = host_root  # (workspace root here, the same folder on the creator's machine)
        self.image_sizes = image_sizes
        self.total = frames(self.v["duration"], self.fps)
        self.uuid = new_uuid()
        self.next_id = 2
        self.bin: list[tuple[str, int]] = []  # (producer id, length in frames)
        self.notes: list[str] = []
        root_attrs = {"LC_NUMERIC": "C", "producer": "main_bin", "version": "7.0.0"}
        if host_root:
            root_attrs["root"] = self.path(project.parent)
        self.root = ET.Element("mlt", root_attrs)

    def fr(self, seconds: float) -> int:
        return frames(seconds, self.fps)

    def tc(self, frame: int) -> str:
        return timecode(frame, self.fps)

    def path(self, target: Path) -> str:
        """A path as the project should name it: absolute on the creator's machine, or relative to the project."""
        if self.host_root:
            local, host = self.host_root
            return str(Path(host) / target.resolve().relative_to(local.resolve()))
        return os.path.relpath(target, self.project.parent)

    def kid(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    # --- elements -------------------------------------------------------------------------------------

    def profile(self) -> None:
        w, h = self.v["width"], self.v["height"]
        d = gcd(w, h)
        description = "HD 1080p 30 fps" if (w, h, self.fps) == (1920, 1080, 30) else f"{w}x{h} {self.fps} fps"
        ET.SubElement(
            self.root,
            "profile",
            colorspace="709",
            description=description,
            display_aspect_den=str(h // d),
            display_aspect_num=str(w // d),
            frame_rate_den="1",
            frame_rate_num=str(self.fps),
            height=str(h),
            progressive="1",
            sample_aspect_den="1",
            sample_aspect_num="1",
            width=str(w),
        )

    def narration(self) -> list[tuple[str, dict]]:
        out = []
        for n, audio in enumerate(self.t["audio"], 1):
            length = self.fr(audio["duration"])
            pid = f"audio{n}"
            chain = ET.SubElement(self.root, "chain", id=pid, out=self.tc(length - 1))
            props(
                chain,
                {
                    "length": length,
                    "eof": "pause",
                    "resource": self.path(self.video_dir / audio["file"]),
                    "mlt_service": "avformat",
                    "audio_index": 0,
                    "video_index": -1,
                    "kdenlive:id": self.kid(),
                    "kdenlive:clip_type": AUDIO_TYPE,
                    "kdenlive:clipname": f"Narração · {Path(audio['file']).stem}",
                    "kdenlive:folderid": FOLDERS["narration"],
                    "kdenlive:control_uuid": new_uuid(),
                    "seekable": 1,
                },
            )
            self.bin.append((pid, length))
            out.append((pid, audio))
        return out

    def images(self, subtitles: dict[str, str]) -> list[str]:
        """One producer per clip, as Kdenlive does; returns their ids in clip order."""
        ids = []
        for n, clip in enumerate(self.t["clips"], 1):
            pid = f"img{n}"
            width, height = self.image_sizes.get(clip["image"], (self.v["width"], self.v["height"]))
            text = subtitles.get(clip["name"], "")
            name = f"{clip['name'][:3]} · {text[:60]}" if text else clip["name"]
            producer = ET.SubElement(
                self.root, "producer", id=pid, attrib={"in": self.tc(0), "out": self.tc(self.total - 1)}
            )
            props(
                producer,
                {
                    "length": self.total,
                    "eof": "pause",
                    "resource": self.path(self.video_dir / clip["image"]),
                    "ttl": self.total,
                    "aspect_ratio": 1,
                    "meta.media.progressive": 1,
                    "seekable": 1,
                    "format": 1,
                    "meta.media.width": width,
                    "meta.media.height": height,
                    "mlt_service": "qimage",
                    "kdenlive:id": self.kid(),
                    "kdenlive:clip_type": IMAGE_TYPE,
                    "kdenlive:clipname": name,
                    "kdenlive:folderid": FOLDERS["images"],
                    "kdenlive:duration": self.total,
                    "kdenlive:control_uuid": new_uuid(),
                },
            )
            self.bin.append((pid, self.total))
            ids.append(pid)
        return ids

    def transform(self, entry: ET.Element, clip: dict, length: int) -> None:
        move = clip["camera"]
        w, h = self.v["width"], self.v["height"]
        last = self.tc(length - 1)
        props(
            ET.SubElement(entry, "filter", attrib={"in": self.tc(0), "out": last}),
            {
                "mlt_service": "qtblend",
                "kdenlive_id": "qtblend",
                "kdenlive:collapsed": 1,
                "rect": f"{self.tc(0)}={view_rect(move['from'], w, h)};{last}={view_rect(move['to'], w, h)}",
                "distort": 0,
                "compositing": 0,
                "rotate_center": 0,
                "rotation": f"{self.tc(0)}=0;{last}=0",
                "rotate_anchor": f"0=0.5 0.5 0 0;{length - 1}=0.5 0.5 0 0",
                "kdenlive:sync_in_out": 1,
                "kdenlive:camera_move": move["type"],
            },
        )

    def fade(self, entry: ET.Element, kind: str, start: int, length: int, alpha: bool) -> None:
        """fade_from_black / fade_to_black over [start, start + length): of the alpha (a dissolve) or the level."""
        rising = kind == "fade_from_black"
        a, b = ("0", "1") if rising else ("1", "0")
        ramp = f"{self.tc(0)}={a};{self.tc(length - 1)}={b}"
        attrib = (
            {"out": self.tc(start + length - 1)}
            if rising
            else {"in": self.tc(start), "out": self.tc(start + length - 1)}
        )
        values = {"start": 1, "level": 1 if alpha else ramp, "mlt_service": "brightness", "kdenlive_id": kind}
        values.update({"kdenlive:collapsed": 1, "alpha": ramp if alpha else 1})
        props(ET.SubElement(entry, "filter", attrib=attrib), values)

    def playlist(self, pid: str, audio: bool = False) -> ET.Element:
        element = ET.SubElement(self.root, "playlist", id=pid)
        if audio:
            props(element, {"kdenlive:audio_track": 1})
        return element

    def place(self, playlist: ET.Element, clock: int, start: int, producer: str, length: int) -> ET.Element:
        if start > clock:
            ET.SubElement(playlist, "blank", length=self.tc(start - clock))
        return ET.SubElement(
            playlist, "entry", producer=producer, attrib={"in": self.tc(0), "out": self.tc(length - 1)}
        )

    def track(self, tid: str, playlists: tuple[str, str], name: str, audio: bool) -> ET.Element:
        tractor = ET.SubElement(self.root, "tractor", id=tid, attrib={"in": self.tc(0), "out": self.tc(self.total - 1)})
        values: dict[str, object] = {"kdenlive:audio_track": 1} if audio else {}
        values.update({"kdenlive:trackheight": 90 if audio else 100, "kdenlive:timeline_active": 1})
        values.update({"kdenlive:collapsed": 0, "kdenlive:track_name": name})
        props(tractor, values)
        hide = "video" if audio else "audio"
        for playlist in playlists:
            ET.SubElement(tractor, "track", hide=hide, producer=playlist)
        return tractor

    # --- the document ---------------------------------------------------------------------------------

    def build(self, subtitle_file: Path) -> ET.Element:
        self.profile()
        sounds = self.narration()
        line_of = {s["name"]: s["text"] for s in self.t["subtitles"]}
        image_ids = self.images(line_of)
        black = ET.SubElement(
            self.root, "producer", id="producer0", attrib={"in": self.tc(0), "out": self.tc(self.total - 1)}
        )
        props(
            black,
            {
                "length": 2147483647,
                "eof": "continue",
                "resource": "black",
                "aspect_ratio": 1,
                "mlt_service": "color",
                "kdenlive:playlistid": "black_track",
                "mlt_image_format": "rgba",
                "set.test_audio": 0,
            },
        )

        # A1: the narration at its timeline start
        a1 = self.playlist("playlist0", audio=True)
        clock = 0
        for pid, audio in sounds:
            start, length = self.fr(audio["start"]), self.fr(audio["duration"])
            self.place(a1, clock, start, pid, length)
            clock = start + length
        self.playlist("playlist1", audio=True)
        self.track("tractor0", ("playlist0", "playlist1"), "Narração", audio=True)

        # images: even clips on the lower track, odd on the upper one, which fades its alpha for each dissolve
        clips = self.t["clips"]
        transitions = self.t["transitions"]
        kinds = {t["type"] for t in transitions} - {"dissolve", "cut"}
        if kinds:
            self.notes.append(f"exported as dissolves in Kdenlive: {', '.join(sorted(kinds))}")
        lower, upper = self.playlist("playlist2"), None
        self.playlist("playlist3")
        self.track("tractor1", ("playlist2", "playlist3"), "Imagens 1 · dissoluções", audio=False)
        upper = self.playlist("playlist4")
        self.playlist("playlist5")
        clocks = {0: 0, 1: 0}
        for index, clip in enumerate(clips):
            on = index % 2
            start, end = self.fr(clip["start"]), self.fr(clip["end"])
            length = end - start
            entry = self.place(upper if on else lower, clocks[on], start, image_ids[index], length)
            clocks[on] = end
            self.transform(entry, clip, length)
            fade_in = self.fr(transitions[index - 1]["seconds"]) if index else 0
            fade_out = self.fr(transitions[index]["seconds"]) if index < len(transitions) else 0
            if index == 0 and self.v["fade_in"] > 0:
                self.fade(entry, "fade_from_black", 0, self.fr(self.v["fade_in"]), alpha=False)
            elif on and fade_in:
                self.fade(entry, "fade_from_black", 0, fade_in, alpha=True)
            if index == len(clips) - 1 and self.v["fade_out"] > 0:
                n = self.fr(self.v["fade_out"])
                self.fade(entry, "fade_to_black", length - n, n, alpha=False)
            elif on and fade_out:
                self.fade(entry, "fade_to_black", length - fade_out, fade_out, alpha=True)
        self.track("tractor2", ("playlist4", "playlist5"), "Imagens 2 · dissoluções", audio=False)

        # the sequence
        sequence = ET.SubElement(
            self.root, "tractor", id="tractor3", attrib={"in": self.tc(0), "out": self.tc(self.total - 1)}
        )
        guides = [
            {
                "pos": self.fr(c["start"]) if c["index"] > 1 else 0,
                "duration": 0,
                "comment": c["title"],
                "type": 0,
            }
            for c in self.t["chapters"]
        ]
        subtitles = [{"id": 0, "name": "Legendas", "file": self.path(subtitle_file)}]
        sequence_id = self.kid()
        props(
            sequence,
            {
                "kdenlive:duration": self.tc(self.total),
                "kdenlive:maxduration": self.total,
                "kdenlive:clipname": self.title,
                "kdenlive:description": "",
                "kdenlive:uuid": self.uuid,
                "kdenlive:producer_type": SEQUENCE_TYPE,
                "kdenlive:control_uuid": self.uuid,
                "kdenlive:id": sequence_id,
                "kdenlive:clip_type": 0,
                "kdenlive:folderid": FOLDERS["sequences"],
                "kdenlive:sequenceproperties.activeSubtitleIndex": 0,
                "kdenlive:sequenceproperties.activeTrack": 2,
                "kdenlive:sequenceproperties.audioTarget": 0,
                "kdenlive:sequenceproperties.disablepreview": 0,
                "kdenlive:sequenceproperties.globalSubtitleStyles": "[ ] ",
                "kdenlive:sequenceproperties.hasAudio": 1,
                "kdenlive:sequenceproperties.hasVideo": 1,
                "kdenlive:sequenceproperties.hidesubtitle": 0,
                "kdenlive:sequenceproperties.position": 0,
                "kdenlive:sequenceproperties.scrollPos": 0,
                "kdenlive:sequenceproperties.subtitlesList": json.dumps(subtitles, ensure_ascii=False),
                "kdenlive:sequenceproperties.tracks": 3,
                "kdenlive:sequenceproperties.tracksCount": 3,
                "kdenlive:sequenceproperties.videoTarget": 1,
                "kdenlive:sequenceproperties.zonein": 0,
                "kdenlive:sequenceproperties.zoneout": self.total,
                "kdenlive:sequenceproperties.zoom": 7,
                "kdenlive:sequenceproperties.groups": "[ ] ",
                "kdenlive:sequenceproperties.documentuuid": self.uuid,
                "kdenlive:sequenceproperties.guides": json.dumps(guides, ensure_ascii=False),
            },
        )
        for producer in ("producer0", "tractor0", "tractor1", "tractor2"):
            ET.SubElement(sequence, "track", producer=producer)
        props(
            ET.SubElement(sequence, "transition"),
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
                ET.SubElement(sequence, "transition"),
                {
                    "a_track": 0,
                    "b_track": b,
                    "compositing": 0,
                    "distort": 0,
                    "rotate_center": 0,
                    "mlt_service": "qtblend",
                    "kdenlive_id": "qtblend",
                    "internal_added": INTERNAL,
                    "always_active": 1,
                },
            )
        props(
            ET.SubElement(sequence, "filter"),
            {
                "mlt_service": "avfilter.subtitles",
                "av.alpha": 1,
                "internal_added": INTERNAL,
                "av.filename": self.path(subtitle_file),
            },
        )

        # the bin, then the project tractor
        main_bin = self.playlist("main_bin")
        props(
            main_bin,
            {
                "kdenlive:folder.-1.2": "Sequências",
                "kdenlive:folder.-1.3": "Imagens",
                "kdenlive:folder.-1.4": "Narração",
                "kdenlive:sequenceFolder": FOLDERS["sequences"],
                "kdenlive:docproperties.activetimeline": self.uuid,
                "kdenlive:docproperties.audioChannels": 2,
                "kdenlive:docproperties.documentid": str(round(time.time() * 1000)),
                "kdenlive:docproperties.enableproxy": 0,
                "kdenlive:docproperties.generateimageproxy": 0,
                "kdenlive:docproperties.generateproxy": 0,
                "kdenlive:docproperties.opensequences": self.uuid,
                "kdenlive:docproperties.profile": PROFILES.get((self.v["width"], self.v["height"], self.fps), ""),
                "kdenlive:docproperties.uuid": self.uuid,
                "kdenlive:docproperties.version": DOCUMENT_VERSION,
                "kdenlive:docproperties.generator": "ytflow",
                "xml_retain": 1,
            },
        )
        for pid, length in self.bin:
            ET.SubElement(main_bin, "entry", producer=pid, attrib={"in": self.tc(0), "out": self.tc(length - 1)})
        ET.SubElement(main_bin, "entry", producer="tractor3", attrib={"in": self.tc(0), "out": self.tc(self.total)})
        project = ET.SubElement(
            self.root, "tractor", id="tractor4", attrib={"in": self.tc(0), "out": self.tc(self.total - 1)}
        )
        props(project, {"kdenlive:projectTractor": 1})
        ET.SubElement(project, "track", producer="tractor3", attrib={"in": self.tc(0), "out": self.tc(self.total - 1)})
        return self.root


def export(
    timeline: dict,
    project: Path,
    video_dir: Path,
    subtitles: Path,
    title: str,
    host_root: tuple[Path, str] | None = None,
    image_sizes: dict[str, tuple[int, int]] | None = None,
) -> tuple[Path, list[str]]:
    """Write the project file and its subtitle file; returns (project path, notes for the creator)."""
    subtitle_file = project.parent / f"{project.name}.ass"  # Kdenlive's own name: <project>.kdenlive.ass
    shutil.copyfile(subtitles, subtitle_file)
    builder = Builder(timeline, project, video_dir, title, host_root, image_sizes or {})
    root = builder.build(subtitle_file)
    ET.indent(root)
    project.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
    return project, builder.notes
