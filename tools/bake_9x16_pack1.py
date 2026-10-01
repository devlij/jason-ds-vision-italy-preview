#!/usr/bin/env python3
"""Bake Italy 9:16 pack1 portraits from the final 16:9 masters.

Photo geometry matches the Netherlands / Italy 9:16 standard already on the
FLAG recreates (IT-01-012 and the other pixel-identical center crops):

  finished 16:9 is 1920×1270 = photo 1920×1080 + 190px label bar
  9:16 photo is a full-height crop of that photo, Lanczos to 1080×1920
  finished 9:16 is 1080×2110 (photo + the same 190px bar)

Default crop is centered (`(width - crop_w) // 2`), the same `fit()` the
existing Italy 9:16 masters match at MAD 0. A scene is shifted only when that
center window drops the subject (open water, cliff, or a landmark sitting on
the edge). Offsets below are pixels from the left of the 1920-wide photo.

Art. 50 chunks are copied byte-for-byte from the source 16:9 (or the daylight
16:9 for a daylight portrait). The Comment date is that file's own finish
date. Nothing here writes approval_status.
"""

from __future__ import annotations

import json
import struct
import sys
import types
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# Import the label-bar painter without pulling OpenCV (only the scrim wipe uses it).
sys.modules.setdefault("cv2", types.ModuleType("cv2"))
sys.path.insert(0, str(ROOT / "tools"))
from label_bar_refinish import (  # noqa: E402
    ART50_KEYS,
    BAR_BG,
    HAIR,
    PNG_SIG,
    draw_label_bar,
    load_scenes,
    middle_line,
)

PACK = (
    "001", "002", "004", "005", "006", "007", "008", "009", "010",
    "014", "015", "016", "018", "019", "020", "021", "022", "023",
    "024", "025", "026", "027", "028", "029", "030", "031", "032",
    "033", "034", "035",
)

# Left edge of the 608px-wide source window. Absent → center.
# Chosen so the landmark, not the empty side of the frame, fills the portrait.
SHIFTS = {
    ("016", False): 440,  # Manarola town sits left; center is open water
    ("016", True): 211,
    ("018", False): 980,  # Temple of Concordia sits right of center
    ("018", True): 930,
    ("020", True): 981,  # Ortigia daylight houses sit on the right
    ("022", False): 192,  # Alghero curtain wall is on the left; center is sea
    ("024", False): 375,  # Costa Smeralda landmass is left of center
    ("024", True): 335,
    ("025", False): 994,  # La Maddalena harbor town is right of center
    ("028", False): 231,  # Stromboli / Sciara del Fuoco is left; center is sea
    ("034", False): 902,  # Miramare castle body extends right of the center window
    ("035", False): 411,  # Sassi mass is a compact block left of center
}

PHOTO_16 = (1920, 1080)
PHOTO_916 = (1080, 1920)
CANVAS_916 = (1080, 2110)
BAR_H = 190


def _crop_width(height: int) -> int:
    return int(round(height * (PHOTO_916[0] / PHOTO_916[1])))


def crop_photo(photo: Image.Image, left: int | None) -> Image.Image:
    """Full-height 9:16 window, then Lanczos to 1080×1920."""
    photo = photo.convert("RGB")
    width, height = photo.size
    if (width, height) != PHOTO_16:
        raise SystemExit(f"photo {width}x{height}, expected {PHOTO_16[0]}x{PHOTO_16[1]}")
    crop_w = _crop_width(height)
    max_left = width - crop_w
    if left is None:
        left = max_left // 2
    if not 0 <= left <= max_left:
        raise SystemExit(f"crop left {left} outside 0..{max_left}")
    window = photo.crop((left, 0, left + crop_w, height))
    return window.resize(PHOTO_916, Image.Resampling.LANCZOS)


def art50_chunks(data: bytes) -> list[bytes]:
    """Raw PNG chunks for the five Art. 50 keys, in file order."""
    if data[:8] != PNG_SIG:
        raise SystemExit("not a png")
    found: list[bytes] = []
    keys: list[str] = []
    i = 8
    while i + 12 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        end = i + 12 + length
        payload = data[i + 8 : i + 8 + length]
        if ctype in (b"tEXt", b"iTXt", b"zTXt"):
            key = payload.split(b"\x00", 1)[0].decode("latin-1")
            if key in ART50_KEYS:
                found.append(data[i:end])
                keys.append(key)
        i = end
        if ctype == b"IEND":
            break
    if keys != list(ART50_KEYS):
        raise SystemExit(f"Art. 50 keys {keys}, expected {list(ART50_KEYS)}")
    return found


def comment_of(chunks: list[bytes]) -> str:
    for chunk in chunks:
        length = struct.unpack(">I", chunk[:4])[0]
        ctype = chunk[4:8]
        payload = chunk[8 : 8 + length]
        if ctype != b"tEXt":
            continue
        key, value = payload.split(b"\x00", 1)
        if key == b"Comment":
            return value.decode("latin-1")
    raise SystemExit("Comment chunk missing")


def write_with_chunks(path: Path, chunks: list[bytes]) -> None:
    data = path.read_bytes()
    if data[:8] != PNG_SIG:
        raise SystemExit(f"not a png: {path}")
    out = [data[:8]]
    i = 8
    inserted = False
    while i + 12 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        end = i + 12 + length
        payload = data[i + 8 : i + 8 + length]
        if ctype in (b"tEXt", b"iTXt", b"zTXt"):
            key = payload.split(b"\x00", 1)[0].decode("latin-1")
            if key in ART50_KEYS:
                i = end
                continue
        if ctype == b"IEND":
            out.extend(chunks)
            out.append(data[i:end])
            inserted = True
            i = end
            break
        out.append(data[i:end])
        i = end
    if not inserted:
        raise SystemExit(f"IEND missing: {path}")
    path.write_bytes(b"".join(out))


def bake_one(src: Path, dest: Path, caption: str, scenario: str, daylight: bool, left: int | None) -> dict:
    raw = src.read_bytes()
    chunks = art50_chunks(raw)
    with Image.open(src) as im:
        if im.size != (1920, 1270):
            raise SystemExit(f"{src.name} size {im.size}")
        photo = im.convert("RGB").crop((0, 0, 1920, 1080))
    portrait = crop_photo(photo, left)
    if portrait.size != PHOTO_916:
        raise SystemExit(f"portrait {portrait.size}")
    finished = draw_label_bar(portrait, caption, middle_line(scenario, daylight))
    if finished.size != CANVAS_916:
        raise SystemExit(f"canvas {finished.size}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    finished.save(dest, format="PNG", compress_level=9)
    write_with_chunks(dest, chunks)
    written = art50_chunks(dest.read_bytes())
    if written != chunks:
        raise SystemExit(f"{dest.name} Art. 50 chunks do not match {src.name}")
    with Image.open(dest) as saved:
        saved.load()
        if saved.size != CANVAS_916:
            raise SystemExit(f"{dest.name} saved {saved.size}")
        top = saved.crop((0, 0, 1080, 1920)).convert("RGB")
        if list(top.getdata()) != list(portrait.getdata()):
            raise SystemExit(f"{dest.name} photo pixels changed on save")
        if saved.getpixel((2, saved.height - 1))[:3] != BAR_BG:
            raise SystemExit(f"{dest.name} bar")
        if saved.getpixel((2, 1920))[:3] != HAIR:
            raise SystemExit(f"{dest.name} hairline")
    return {
        "file": dest.name,
        "source": src.name,
        "left": left if left is not None else (1920 - _crop_width(1080)) // 2,
        "shifted": left is not None,
        "comment": comment_of(chunks),
        "size": "1080x2110",
    }


def main() -> None:
    scenes = load_scenes()
    reports = []
    for num in PACK:
        entry = f"IT-01-{num}"
        scene = scenes[entry]
        for daylight in (False, True):
            src_name = f"it-01-{num}-daylight-16x9.png" if daylight else f"it-01-{num}-16x9.png"
            src = ASSETS / src_name
            if daylight and not src.is_file():
                continue
            if not src.is_file():
                raise SystemExit(f"missing {src}")
            dest_name = f"it-01-{num}-daylight-9x16.png" if daylight else f"it-01-{num}-9x16.png"
            left = SHIFTS.get((num, daylight))
            report = bake_one(src, ASSETS / dest_name, scene["caption"], scene["scenario_label"], daylight, left)
            reports.append(report)
            print(f"{report['file']} left={report['left']} {report['comment'][-10:]}", flush=True)
    summary = {
        "masters": len(reports),
        "shifted": sum(1 for row in reports if row["shifted"]),
        "center": sum(1 for row in reports if not row["shifted"]),
        "dates": sorted({row["comment"][-10:] for row in reports}),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
