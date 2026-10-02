#!/usr/bin/env python3
"""Bake Italy 9:16 portraits from the finished 16:9 masters.

True 9:16 at 1080 wide is 1080×1920. The label bar is 190px, so the photo
region is 1080×1730 and the bar is appended under it:

  finished 16:9 is 1920×1270 = photo 1920×1080 + 190px label bar
  9:16 photo is a full-height crop of that photo, Lanczos to 1080×1730
  finished 9:16 is 1080×1920 (1080×1730 photo + the same 190px bar)

Scaling the photo to 1080×1920 and then adding the bar produces 1080×2110,
which is not 9:16. This module refuses that canvas.

Default crop is centered (`(width - crop_w) // 2`). A scene is shifted only
when that center window drops the subject. Offsets are pixels from the left
of the 1920-wide photo. Nothing here writes approval_status or gallery index.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import types
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
TOOLS = Path(__file__).resolve().parent

sys.modules.setdefault("cv2", types.ModuleType("cv2"))
sys.path.insert(0, str(TOOLS))
from label_bar_refinish import (  # noqa: E402
    ART50_KEYS,
    BAR_BG,
    HAIR,
    PNG_SIG,
    draw_label_bar,
    load_scenes,
    middle_line,
)

PHOTO_16 = (1920, 1080)
PHOTO_916 = (1080, 1730)
BAR_H = 190
CANVAS_916 = (PHOTO_916[0], PHOTO_916[1] + BAR_H)
# Source window that scales to the 1080×1730 photo. Full photo height, so the
# width is 1080 * 1080/1730, rounded.
CROP_W = int(round(PHOTO_16[1] * (PHOTO_916[0] / PHOTO_916[1])))
CENTER_LEFT = (PHOTO_16[0] - CROP_W) // 2

if CANVAS_916 != (1080, 1920) or PHOTO_916 != (1080, 1730) or BAR_H != 190:
    raise SystemExit("9:16 canvas must be 1080x1920 = photo 1080x1730 + 190px bar")
if CANVAS_916[0] * 16 != CANVAS_916[1] * 9:
    raise SystemExit(f"{CANVAS_916[0]}x{CANVAS_916[1]} is not exact 9:16")


def _crop_width(height: int) -> int:
    return int(round(height * (PHOTO_916[0] / PHOTO_916[1])))


def crop_photo(photo: Image.Image, left: int | None) -> Image.Image:
    """Full-height 1080:1730 window, then Lanczos to 1080×1730."""
    photo = photo.convert("RGB")
    width, height = photo.size
    if (width, height) != PHOTO_16:
        raise SystemExit(f"photo {width}x{height}, expected {PHOTO_16[0]}x{PHOTO_16[1]}")
    crop_w = _crop_width(height)
    if crop_w != CROP_W:
        raise SystemExit(f"crop width {crop_w}, expected {CROP_W}")
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


def bake_one(
    src: Path,
    dest: Path,
    caption: str,
    scenario: str,
    daylight: bool,
    left: int | None,
) -> dict:
    if CANVAS_916 != (1080, 1920):
        raise SystemExit("refusing to emit a 9:16 canvas other than 1080x1920")
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
        top = saved.crop((0, 0, PHOTO_916[0], PHOTO_916[1])).convert("RGB")
        if list(top.getdata()) != list(portrait.getdata()):
            raise SystemExit(f"{dest.name} photo pixels changed on save")
        if saved.getpixel((2, saved.height - 1))[:3] != BAR_BG:
            raise SystemExit(f"{dest.name} bar")
        if saved.getpixel((2, PHOTO_916[1]))[:3] != HAIR:
            raise SystemExit(f"{dest.name} hairline")
    resolved = left if left is not None else CENTER_LEFT
    return {
        "file": dest.name,
        "source": src.name,
        "left": resolved,
        "shifted": left is not None,
        "comment": comment_of(chunks),
        "size": f"{CANVAS_916[0]}x{CANVAS_916[1]}",
    }


def bake_pack(pack: tuple[str, ...], shifts: dict[tuple[str, bool], int]) -> None:
    scenes = load_scenes()
    reports = []
    for num in pack:
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
            left = shifts.get((num, daylight))
            report = bake_one(src, ASSETS / dest_name, scene["caption"], scene["scenario_label"], daylight, left)
            reports.append(report)
            print(f"{report['file']} left={report['left']} {report['size']}", flush=True)
    summary = {
        "masters": len(reports),
        "shifted": sum(1 for row in reports if row["shifted"]),
        "center": sum(1 for row in reports if not row["shifted"]),
        "size": f"{CANVAS_916[0]}x{CANVAS_916[1]}",
    }
    print(json.dumps(summary, indent=2))


def load_shift_tables() -> dict[tuple[str, bool], int]:
    """Shift tables live on the pack scripts so a pack re-run uses the same crop."""
    merged: dict[tuple[str, bool], int] = {}
    for index in range(1, 10):
        name = f"bake_9x16_pack{index}"
        module = __import__(name)
        for key, left in module.SHIFTS.items():
            if key in merged and merged[key] != left:
                raise SystemExit(f"conflicting shift for {key}")
            if not 0 <= left <= PHOTO_16[0] - CROP_W:
                raise SystemExit(f"shift {key} left {left} outside 0..{PHOTO_16[0] - CROP_W}")
            merged[key] = left
    return merged


def _jobs(shifts: dict[tuple[str, bool], int]) -> list[dict]:
    scenes = load_scenes()
    jobs = []
    for number in range(1, 376):
        num = f"{number:03d}"
        entry = f"IT-01-{num}"
        if entry not in scenes:
            raise SystemExit(f"missing scene metadata {entry}")
        scene = scenes[entry]
        for daylight in (False, True):
            src_name = f"it-01-{num}-daylight-16x9.png" if daylight else f"it-01-{num}-16x9.png"
            src = ASSETS / src_name
            if daylight and not src.is_file():
                continue
            if not src.is_file():
                raise SystemExit(f"missing {src}")
            dest_name = f"it-01-{num}-daylight-9x16.png" if daylight else f"it-01-{num}-9x16.png"
            dest = ASSETS / dest_name
            jobs.append(
                {
                    "num": num,
                    "entry": entry,
                    "daylight": daylight,
                    "src": str(src),
                    "dest": str(dest),
                    "existed": dest.is_file(),
                    "caption": scene["caption"],
                    "scenario": scene["scenario_label"],
                    "left": shifts.get((num, daylight)),
                }
            )
    return jobs


def _bake_job(job: dict) -> dict:
    report = bake_one(
        Path(job["src"]),
        Path(job["dest"]),
        job["caption"],
        job["scenario"],
        job["daylight"],
        job["left"],
    )
    report["num"] = job["num"]
    report["entry"] = job["entry"]
    report["daylight"] = job["daylight"]
    report["existed"] = job["existed"]
    return report


def bake_all(workers: int) -> list[dict]:
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    shifts = load_shift_tables()
    jobs = _jobs(shifts)
    reports: list[dict] = []
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        futures = [pool.submit(_bake_job, job) for job in jobs]
        done = 0
        for future in as_completed(futures):
            report = future.result()
            reports.append(report)
            done += 1
            print(
                f"[{done}/{len(jobs)}] {report['file']} left={report['left']} shifted={report['shifted']}",
                flush=True,
            )
    reports.sort(key=lambda row: row["file"])
    return reports


def verify_primary() -> dict:
    """Open every primary assets/it-01-NNN-9x16.png for NNN=001..375."""
    ok = []
    fail = []
    for number in range(1, 376):
        num = f"{number:03d}"
        path = ASSETS / f"it-01-{num}-9x16.png"
        if not path.is_file():
            fail.append({"scene_id": f"IT-01-{num}", "path": str(path.relative_to(ROOT)), "error": "missing"})
            continue
        try:
            with Image.open(path) as im:
                im.load()
                size = im.size
        except Exception as exc:  # noqa: BLE001 — verification must record the failure
            fail.append({"scene_id": f"IT-01-{num}", "path": str(path.relative_to(ROOT)), "error": str(exc)})
            continue
        if size != CANVAS_916:
            fail.append(
                {
                    "scene_id": f"IT-01-{num}",
                    "path": str(path.relative_to(ROOT)),
                    "width": size[0],
                    "height": size[1],
                    "error": f"size {size[0]}x{size[1]}",
                }
            )
        else:
            ok.append(f"IT-01-{num}")
    return {"verified_ok": len(ok), "verified_fail": len(fail), "failures": fail}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bake every Italy 9:16 master at 1080x1920.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--result", type=Path, default=ROOT / "results" / "wo-ia-italy-916-rework-2026-10-01-result.json")
    args = parser.parse_args()
    reports = bake_all(args.workers)
    primary = [row for row in reports if not row["daylight"]]
    daylight = [row for row in reports if row["daylight"]]
    rebuilt = [row["entry"] for row in primary if row["existed"]]
    generated = [row["entry"] for row in primary if not row["existed"]]
    shifts = [
        {"scene_id": row["entry"], "file": row["file"], "left": row["left"], "daylight": row["daylight"]}
        for row in reports
        if row["shifted"]
    ]
    verification = verify_primary()
    daylight_bad = []
    for row in daylight:
        path = ASSETS / row["file"]
        with Image.open(path) as im:
            im.load()
            if im.size != CANVAS_916:
                daylight_bad.append({"file": row["file"], "size": list(im.size)})
    payload = {
        "work_order_id": "wo-ia-italy-916-rework-2026-10-01",
        "canvas": "1080x1920",
        "photo": "1080x1730",
        "label_bar_px": BAR_H,
        "crop_width_px": CROP_W,
        "center_left": CENTER_LEFT,
        "rebuilt_wrong": len(rebuilt),
        "generated_missing": len(generated),
        "verified_ok": verification["verified_ok"],
        "verified_fail": verification["verified_fail"],
        "failures": verification["failures"],
        "daylight_baked": len(daylight),
        "daylight_fail": daylight_bad,
        "shifted": shifts,
        "primary_ids_rebuilt": rebuilt,
        "primary_ids_generated": generated,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in (
        "rebuilt_wrong", "generated_missing", "verified_ok", "verified_fail", "daylight_baked"
    )}, indent=2))
    if verification["verified_fail"] or daylight_bad:
        raise SystemExit("verification failed")


if __name__ == "__main__":
    main()
