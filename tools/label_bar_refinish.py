#!/usr/bin/env python3
"""Re-finish Italy scrim masters onto the label-bar standard.

The photograph is the existing master with baked on-image type removed by
per-master glyph localization + inpaint (France-style). Scrim darkening outside
glyphs is left in place so non-text pixels stay faithful. A 190px #0e0e12 bar is
appended under that photo. Rows above the scrim start are copied unchanged.

16:9 becomes 1920×1270. 4:5 becomes 864×1270. Italy has no 9:16 masters.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
MANIFESTS = ROOT / "manifests"
INDEX = ROOT / "index.html"

SANS = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
SANS_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
ALLURA = Path(__file__).resolve().parent / "fonts" / "Allura-Regular.ttf"

BRAND = "Jason D\u2019s Vision"
SIGNATURE_NAME = "Jason A. Devlin"
DISCLOSURE = "AI-generated artistic interpretation \u00b7 Not a photograph."
DAYLIGHT_LINE = "\u2600 Daylight variant \u00b7 derived from the night interpretation"
ON_IMAGE_SIGNATURE = "Jason D\u2019s Vision"

BAR_H = 190
HAIRLINE = 2
BAR_BG = (0x0E, 0x0E, 0x12)
HAIR = (0xE4, 0xE4, 0xEA)
INK = (255, 255, 255)
INK_SCENARIO = (214, 214, 222)
INK_DISCLOSURE = (176, 176, 186)

TITLE = "Jason D's Vision \u2014 AI-generated artistic interpretation"
DESCRIPTION = (
    "AI-generated artistic interpretation from the Jason D's Vision Italy gallery. "
    "Created with generative AI; not a photograph."
)
COPYRIGHT = "Jason D's Vision \u2014 AI-generated content"
SOFTWARE = "Jason D's Vision library pipeline"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
ART50_KEYS = ("Title", "Description", "Copyright", "Software", "Comment")

# Scrim baked on the old masters: black overlay from y = int(h * 0.68),
# alpha = int(190 * t ** 1.2). Verified by exact recomposite of every
# invertible pixel.
SCRIM_START = 0.68
SCRIM_ALPHA = 190
SCRIM_GAMMA = 1.2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _chunk(ctype: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def _text_chunk(key: str, value: str) -> bytes:
    return _chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1"))


def _itxt_chunk(key: str, value: str) -> bytes:
    data = (
        key.encode("latin-1")
        + b"\x00"
        + b"\x00"
        + b"\x00"
        + b"\x00"
        + b"\x00"
        + value.encode("utf-8")
    )
    return _chunk(b"iTXt", data)


def comment_for(finish_date: str) -> str:
    return (
        "EU AI Act Art. 50 transparency note: this image is AI-generated content. "
        f"Machine-readable disclosure embedded {finish_date}."
    )


def art50_chunks(finish_date: str) -> list[bytes]:
    return [
        _itxt_chunk("Title", TITLE),
        _text_chunk("Description", DESCRIPTION),
        _itxt_chunk("Copyright", COPYRIGHT),
        _text_chunk("Software", SOFTWARE),
        _text_chunk("Comment", comment_for(finish_date)),
    ]


def inject_art50(path: Path, finish_date: str) -> None:
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
            out.extend(art50_chunks(finish_date))
            out.append(data[i:end])
            inserted = True
            i = end
            break
        out.append(data[i:end])
        i = end
    if not inserted:
        raise SystemExit(f"IEND missing: {path}")
    path.write_bytes(b"".join(out))


def read_comment(path: Path) -> str:
    data = path.read_bytes()
    i = 8
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype = data[i + 4 : i + 8]
        chunk = data[i + 8 : i + 8 + length]
        if ctype == b"tEXt":
            key, value = chunk.split(b"\x00", 1)
            if key == b"Comment":
                return value.decode("latin-1")
        i += 12 + length
        if ctype == b"IEND":
            break
    raise SystemExit(f"Comment missing: {path}")


def build_scrim_luts() -> np.ndarray:
    tables = np.full((SCRIM_ALPHA + 1, 256), -1, dtype=np.int16)
    for alpha in range(SCRIM_ALPHA + 1):
        dest = Image.new("RGBA", (256, 1))
        dest.putdata([(i, i, i, 255) for i in range(256)])
        overlay = Image.new("RGBA", (256, 1), (0, 0, 0, alpha))
        observed = np.asarray(Image.alpha_composite(dest, overlay))[0, :, 0]
        buckets: list[list[int]] = [[] for _ in range(256)]
        for src, value in enumerate(observed.tolist()):
            buckets[value].append(src)
        for value, opts in enumerate(buckets):
            if opts:
                tables[alpha, value] = opts[len(opts) // 2]
    return tables


LUTS = build_scrim_luts()


def _js_unescape(raw: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    text = re.sub(r"\\u([0-9a-fA-F]{4})", repl, raw)
    return text.replace(r"\'", "'").replace(r"\"", '"').replace(r"\\", "\\")


def load_scenes() -> dict[str, dict[str, str]]:
    html = INDEX.read_text()
    scenes: dict[str, dict[str, str]] = {}
    for part in html.split("entry_id:")[1:]:
        eid_m = re.search(r'"(IT-01-\d+)"', part)
        cap_m = re.search(r'caption:\s*"((?:\\.|[^"\\])*)"', part)
        sc_m = re.search(r'scenario_label:\s*"((?:\\.|[^"\\])*)"', part)
        if not eid_m or not cap_m or not sc_m:
            continue
        scenes[eid_m.group(1)] = {
            "caption": _js_unescape(cap_m.group(1)),
            "scenario_label": _js_unescape(sc_m.group(1)),
        }
    if len(scenes) != 375:
        raise SystemExit(f"expected 375 scenes, parsed {len(scenes)}")
    return scenes


def finish_dates() -> dict[str, str]:
    """Latest non-metadata commit date for each master. Artwork finish, not the embed backfill."""
    log = subprocess.check_output(
        [
            "git",
            "log",
            "--pretty=format:COMMIT %ad %s",
            "--date=short",
            "--name-only",
            "--",
            "assets",
        ],
        cwd=ROOT,
        text=True,
    )
    dates: dict[str, str] = {}
    current: str | None = None
    skip = False
    for line in log.splitlines():
        if line.startswith("COMMIT "):
            rest = line[len("COMMIT ") :]
            day, _, subject = rest.partition(" ")
            subject_l = subject.lower()
            skip = (
                "pixels unchanged" in subject_l
                or subject.startswith("Art. 50")
                or "re-finish" in subject_l
                or "label bar" in subject_l
                or "label-bar" in subject_l
            )
            current = None if skip else day
            continue
        if not line.strip() or current is None:
            continue
        name = line.strip()
        if name.startswith("assets/") and name.endswith(".png") and name not in dates:
            # git log is newest first; the first kept commit is the latest real finish.
            dates[name] = current
    return dates


def _bbox_h(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    box = font.getbbox(text)
    return box[2] - box[0], box[3] - box[1]


def baked_layout(width: int, height: int, caption: str, middle: str) -> dict:
    """Positions of the type baked into the old scrim masters.

    Italy bake used round(width * {0.016,0.012,0.010,0.018}) DejaVu sizes, a fixed
    30px bottom margin, 8px gaps, and a signature bottom-aligned with the disclosure.
    """
    sizes = (
        int(round(width * 0.016)),
        int(round(width * 0.012)),
        int(round(width * 0.010)),
        int(round(width * 0.018)),
    )
    margin_x = int(width * 0.025) if width >= 1600 else int(width * 20 / 864)
    margin_b = 30
    fonts = {
        "cap": ImageFont.truetype(str(SANS_BOLD), sizes[0]),
        "sc": ImageFont.truetype(str(SANS), sizes[1]),
        "disc": ImageFont.truetype(str(SANS), sizes[2]),
        "sig": ImageFont.truetype(str(SANS_BOLD), sizes[3]),
    }
    _cap_w, cap_h = _bbox_h(fonts["cap"], caption)
    _sc_w, sc_h = _bbox_h(fonts["sc"], middle)
    _disc_w, disc_h = _bbox_h(fonts["disc"], DISCLOSURE)
    sig_w, sig_h = _bbox_h(fonts["sig"], ON_IMAGE_SIGNATURE)
    gap = 8
    y_disc = height - margin_b - disc_h
    y_sc = y_disc - gap - sc_h
    y_cap = y_sc - gap - cap_h
    # Signature shares the disclosure baseline (bottom-aligned).
    sig_y = y_disc + disc_h - sig_h
    return {
        "fonts": fonts,
        "margin_x": margin_x,
        "y_cap": y_cap,
        "sig_x": width - margin_x - sig_w,
        "rows": (
            (margin_x, y_cap, caption, fonts["cap"]),
            (margin_x, y_sc, middle, fonts["sc"]),
            (margin_x, y_disc, DISCLOSURE, fonts["disc"]),
            (width - margin_x - sig_w, sig_y, ON_IMAGE_SIGNATURE, fonts["sig"]),
        ),
    }


def text_mask(width: int, height: int, caption: str, middle: str) -> np.ndarray:
    lay = baked_layout(width, height, caption, middle)
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for x, y, text, font in lay["rows"]:
        draw.text((x + 1, y + 1), text, font=font, fill=255)
        draw.text((x, y), text, font=font, fill=255)
    # Dilate enough to cover anti-alias fringes and the 1px shadow.
    return np.asarray(mask.filter(ImageFilter.MaxFilter(7))) > 0


def inverse_scrim(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    height, width = arr.shape[:2]
    start = int(height * SCRIM_START)
    cleaned = arr.copy()
    unreachable = np.zeros((height, width), dtype=bool)
    for y in range(start, height):
        t = (y - start) / max(1, (height - start))
        alpha = int(SCRIM_ALPHA * (t ** SCRIM_GAMMA))
        mapped = LUTS[alpha][arr[y]]
        bad = (mapped < 0).any(axis=1)
        unreachable[y] = bad
        mapped = mapped.copy()
        mapped[mapped < 0] = 255
        cleaned[y] = mapped.astype(np.uint8)
    return cleaned, unreachable, start


def inpaint(image: np.ndarray, hole: np.ndarray) -> np.ndarray:
    acc = image.astype(np.float32)
    filled = ~hole
    remain = hole.copy()
    height, width = hole.shape
    shifts = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
    for _ in range(64):
        if not remain.any():
            break
        total = np.zeros_like(acc)
        count = np.zeros((height, width), np.float32)
        for dy, dx in shifts:
            ys = slice(max(0, -dy), height - max(0, dy))
            xs = slice(max(0, -dx), width - max(0, dx))
            ysrc = slice(max(0, dy), height - max(0, -dy))
            xsrc = slice(max(0, dx), width - max(0, -dx))
            known = np.zeros((height, width), dtype=bool)
            known[ys, xs] = filled[ysrc, xsrc]
            vals = np.zeros_like(acc)
            vals[ys, xs] = acc[ysrc, xsrc]
            total += vals * known[..., None]
            count += known
        newly = remain & (count > 0)
        if not newly.any():
            break
        acc[newly] = total[newly] / count[newly, None]
        filled[newly] = True
        remain[newly] = False
    if remain.any():
        raise SystemExit(f"inpaint left {int(remain.sum())} pixels")
    return np.clip(np.rint(acc), 0, 255).astype(np.uint8)


def _render_glyph(font_path: Path, size: int, text: str) -> tuple[np.ndarray, ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    font = ImageFont.truetype(str(font_path), size)
    box = font.getbbox(text)
    tw = max(1, box[2] - box[0] + 4)
    th = max(1, box[3] - box[1] + 4)
    img = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(img).text((2 - box[0], 2 - box[1]), text, font=font, fill=255)
    return np.asarray(img), font, box


def _locate_line(
    gray: np.ndarray, font_path: Path, text: str, sizes: range, y0: int = 750
) -> tuple[float, tuple[int, int, int, ImageFont.FreeTypeFont, str] | None]:
    search = gray[y0:]
    best: tuple[float, tuple[int, int, int, ImageFont.FreeTypeFont, str] | None] = (-1.0, None)
    for size in sizes:
        tmpl, font, box = _render_glyph(font_path, size, text)
        if tmpl.shape[0] >= search.shape[0] or tmpl.shape[1] >= search.shape[1]:
            continue
        res = cv2.matchTemplate(
            search.astype(np.float32), tmpl.astype(np.float32), cv2.TM_CCOEFF_NORMED
        )
        _minv, maxv, _minl, maxl = cv2.minMaxLoc(res)
        if maxv > best[0]:
            mx, my = maxl[0], maxl[1] + y0
            dx, dy = mx + 2 - box[0], my + 2 - box[1]
            best = (float(maxv), (size, dx, dy, font, text))
    return best


def clean_photo(arr: np.ndarray, caption: str, middle: str) -> tuple[np.ndarray, dict]:
    """Remove baked on-image type; leave non-glyph pixels (incl. scrim) untouched.

    Italy masters were baked across batches with slightly different type sizes, so
    each master is localized by template match before inpainting. Matches the
    France label-bar approach Cosmo already accepted: glyph wipe only, then bar.
    """
    height, width = arr.shape[:2]
    if (width, height) not in ((1920, 1080), (864, 1080)):
        raise SystemExit(f"unexpected master size {width}x{height}")
    start = int(height * SCRIM_START)
    gray = np.asarray(Image.fromarray(arr, "RGB").convert("L"))
    if width >= 1600:
        size_sets = {
            "cap": range(28, 36),
            "sc": range(20, 28),
            "disc": range(16, 24),
            "sig": range(32, 40),
        }
        min_scores = {"cap": 0.35, "sc": 0.30, "disc": 0.30, "sig": 0.35}
    else:
        size_sets = {
            "cap": range(12, 20),
            "sc": range(8, 16),
            "disc": range(7, 14),
            "sig": range(12, 22),
        }
        min_scores = {"cap": 0.30, "sc": 0.28, "disc": 0.28, "sig": 0.30}

    candidates: list[tuple[float, tuple]] = []
    for key, text, font_path in (
        ("cap", caption, SANS_BOLD),
        ("sc", middle, SANS),
        ("disc", DISCLOSURE, SANS),
        ("sig", ON_IMAGE_SIGNATURE, SANS_BOLD),
        ("sig", "Jason D's Vision", SANS_BOLD),
    ):
        score, info = _locate_line(gray, font_path, text, size_sets[key if key != "sig" else "sig"])
        if info is not None and score >= min_scores[key if key != "sig" else "sig"]:
            candidates.append((score, info))

    stamp = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(stamp)
    used_sig = False
    located = 0
    for score, (size, dx, dy, font, text) in sorted(candidates, reverse=True):
        if text in (ON_IMAGE_SIGNATURE, "Jason D's Vision"):
            if used_sig:
                continue
            used_sig = True
        draw.text((dx + 1, dy + 1), text, font=font, fill=255)
        draw.text((dx, dy), text, font=font, fill=255)
        located += 1

    if located < 2:
        # Formula fallback when template match is weak (busy water, etc.).
        lay = baked_layout(width, height, caption, middle)
        for x, y, text, font in lay["rows"]:
            draw.text((x + 1, y + 1), text, font=font, fill=255)
            draw.text((x, y), text, font=font, fill=255)
        located = 4

    mask = np.asarray(stamp.filter(ImageFilter.MaxFilter(5))) > 0
    near = np.asarray(stamp.filter(ImageFilter.MaxFilter(9))) > 0
    chroma = arr.max(axis=2).astype(np.int16) - arr.min(axis=2).astype(np.int16)
    white = (arr.max(axis=2) > 185) & (chroma < 40)
    mask = mask | (white & near)
    mask[:start] = False

    hole = (mask.astype(np.uint8) * 255)
    photo = cv2.inpaint(arr, hole, 3, cv2.INPAINT_TELEA)
    photo[:start] = arr[:start]
    above_changed = int(np.any(photo[:start] != arr[:start], axis=2).sum()) if start else 0
    if above_changed:
        raise SystemExit("rows above the scrim changed")

    # Residual gate: localized caption/signature templates must no longer match strongly.
    post_gray = np.asarray(Image.fromarray(photo, "RGB").convert("L"))
    post_cap, _ = _locate_line(post_gray, SANS_BOLD, caption, size_sets["cap"])
    post_sig, _ = _locate_line(post_gray, SANS_BOLD, ON_IMAGE_SIGNATURE, size_sets["sig"])
    if post_cap > 0.55 or post_sig > 0.55:
        raise SystemExit(
            f"glyph residue still matches (cap={post_cap:.3f}, sig={post_sig:.3f})"
        )

    stats = {
        "scrim_start": start,
        "text_pixels": int(mask.sum()),
        "unreachable": 0,
        "above_changed": above_changed,
        "located_lines": located,
        "post_cap_score": round(post_cap, 4),
        "post_sig_score": round(post_sig, 4),
    }
    return photo, stats


def _measure(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text, anchor="lt")
    return right - left, bottom - top


def _bbox(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int, int, int]:
    return font.getbbox(text, anchor="lt")


def _bar_fonts(scale: float) -> dict[str, ImageFont.FreeTypeFont]:
    def px(size: float, floor: int) -> int:
        return max(floor, int(round(size * scale)))

    return {
        "cap": ImageFont.truetype(str(SANS_BOLD), px(28, 15)),
        "sc": ImageFont.truetype(str(SANS), px(18, 12)),
        "disc": ImageFont.truetype(str(SANS), px(16, 11)),
        "brand": ImageFont.truetype(str(SANS), px(20, 13)),
        "name": ImageFont.truetype(str(ALLURA), px(46, 28)),
    }


def _stack_size(lines: list[tuple[str, ImageFont.FreeTypeFont]], gap: int) -> tuple[int, int]:
    width = 0
    height = 0
    for index, (text, font) in enumerate(lines):
        text_w, text_h = _measure(font, text)
        width = max(width, text_w)
        height += text_h
        if index:
            height += gap
    return width, height


def layout_fonts(width: int, caption: str, middle: str):
    if not ALLURA.exists():
        raise SystemExit(f"Allura font missing: {ALLURA}")
    scale = 1.0 if width >= 1600 else (0.9 if width >= 1000 else 0.78)
    for _ in range(18):
        fonts = _bar_fonts(scale)
        gap = max(4, int(round(6 * scale)))
        margin = max(20, int(round(width * 0.028)))
        col_gap = max(16, int(round(width * 0.018)))
        left_w, left_h = _stack_size(
            [(caption, fonts["cap"]), (middle, fonts["sc"]), (DISCLOSURE, fonts["disc"])],
            gap,
        )
        right_w, right_h = _stack_size(
            [(BRAND, fonts["brand"]), (SIGNATURE_NAME, fonts["name"])],
            gap,
        )
        content_h = BAR_H - HAIRLINE
        if (
            margin * 2 + col_gap + left_w + right_w <= width
            and left_h <= content_h - 16
            and right_h <= content_h - 12
        ):
            return fonts, gap
        scale *= 0.94
    raise SystemExit(f"label text does not fit a {width}px bar for {caption!r}")


def draw_label_bar(photo: Image.Image, caption: str, middle: str) -> Image.Image:
    photo = photo.convert("RGB")
    pw, ph = photo.size
    canvas = Image.new("RGB", (pw, ph + BAR_H), BAR_BG)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, ph, pw - 1, ph + HAIRLINE - 1), fill=HAIR)
    fonts, gap = layout_fonts(pw, caption, middle)
    margin = max(20, int(round(pw * 0.028)))
    left = [
        (caption, fonts["cap"], INK),
        (middle, fonts["sc"], INK_SCENARIO),
        (DISCLOSURE, fonts["disc"], INK_DISCLOSURE),
    ]
    right = [
        (BRAND, fonts["brand"], INK),
        (SIGNATURE_NAME, fonts["name"], INK),
    ]

    def stack_height(rows):
        total = 0
        for index, (text, font, _ink) in enumerate(rows):
            total += _measure(font, text)[1]
            if index:
                total += gap
        return total

    def stack_width(rows):
        return max(_measure(font, text)[0] for text, font, _ink in rows)

    content_top = ph + HAIRLINE
    content_h = BAR_H - HAIRLINE

    def draw_stack(rows, align: str) -> None:
        block_h = stack_height(rows)
        block_w = stack_width(rows)
        y = content_top + max(0, (content_h - block_h) // 2)
        for text, font, ink in rows:
            text_w, text_h = _measure(font, text)
            left_edge, top_edge, _right, _bottom = _bbox(font, text)
            x = margin if align == "left" else pw - margin - block_w + (block_w - text_w)
            draw.text((x - left_edge, y - top_edge), text, font=font, fill=ink)
            y += text_h + gap

    draw_stack(left, "left")
    draw_stack(right, "right")
    return canvas


def middle_line(scenario_label: str, daylight: bool) -> str:
    if daylight:
        return DAYLIGHT_LINE
    if scenario_label.startswith("Scenario:"):
        raise SystemExit(f"scenario already prefixed: {scenario_label}")
    return f"Scenario: {scenario_label}"


def entry_of(path: Path) -> tuple[str, bool, str]:
    stem = path.stem  # it-01-003-16x9 or it-01-003-daylight-16x9
    daylight = "-daylight-" in stem
    parts = stem.split("-")
    entry_id = "-".join(parts[:3]).upper()
    if stem.endswith("16x9"):
        fmt = "16x9"
    elif stem.endswith("4x5"):
        fmt = "4x5"
    else:
        raise SystemExit(f"unknown format {path.name}")
    return entry_id, daylight, fmt


def refinish_file(path: Path, caption: str, scenario_label: str, finish_date: str) -> dict:
    entry_id, daylight, fmt = entry_of(path)
    middle = middle_line(scenario_label, daylight)
    with Image.open(path) as im:
        original = np.asarray(im.convert("RGB")).copy()
        width, height = im.size
    photo, stats = clean_photo(original, caption, middle)
    if not np.array_equal(photo[: stats["scrim_start"]], original[: stats["scrim_start"]]):
        raise SystemExit(f"{path.name} clock region drifted")
    finished = draw_label_bar(Image.fromarray(photo, "RGB"), caption, middle)
    expect = (width, height + BAR_H)
    if finished.size != expect:
        raise SystemExit(f"{path.name} canvas {finished.size} != {expect}")
    finished.save(path, format="PNG", compress_level=9)
    inject_art50(path, finish_date)
    with Image.open(path) as saved:
        saved.load()
        if saved.size != expect:
            raise SystemExit(f"{path.name} saved size {saved.size}")
        top = np.asarray(saved.crop((0, 0, width, height)).convert("RGB"))
        if not np.array_equal(top, photo):
            raise SystemExit(f"{path.name} photo pixels changed on save")
        if saved.getpixel((2, saved.height - 1))[:3] != BAR_BG:
            raise SystemExit(f"{path.name} bar")
        if saved.getpixel((2, height))[:3] != HAIR:
            raise SystemExit(f"{path.name} hairline")
    if read_comment(path) != comment_for(finish_date):
        raise SystemExit(f"{path.name} Art. 50 comment")
    return {
        "file": path.name,
        "entry_id": entry_id,
        "format": fmt,
        "daylight": daylight,
        "size": f"{expect[0]}x{expect[1]}",
        "finish_date": finish_date,
        "sha256": sha256_file(path),
        **stats,
    }


def update_manifests(hashes: dict[str, str]) -> int:
    """Rewrite current file hashes from bytes. Leave source_night anchors untouched."""
    updated = 0
    for path in sorted(MANIFESTS.glob("IT-01-*.json")):
        data = json.loads(path.read_text())
        changed = False
        for key, filename in (
            ("sha256_16x9", f"{path.stem.lower()}-16x9.png"),
            ("sha256_4x5", f"{path.stem.lower()}-4x5.png"),
        ):
            digest = hashes.get(filename)
            if digest and data.get(key) != digest:
                data[key] = digest
                changed = True
        variant = data.get("daylight_variant")
        if isinstance(variant, dict):
            sha = variant.get("sha256")
            if isinstance(sha, dict):
                for fmt in ("16x9", "4x5"):
                    filename = f"{path.stem.lower()}-daylight-{fmt}.png"
                    digest = hashes.get(filename)
                    if digest and sha.get(fmt) != digest:
                        sha[fmt] = digest
                        changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            updated += 1
    return updated


def _job(item: tuple[str, str, str, str]) -> dict:
    path, caption, scenario_label, finish_date = item
    return refinish_file(Path(path), caption, scenario_label, finish_date)


def main() -> None:
    scenes = load_scenes()
    dates = finish_dates()
    files = sorted(ASSETS.glob("*.png"))
    if len(files) != 810:
        raise SystemExit(f"expected 810 masters, found {len(files)}")
    jobs = []
    for path in files:
        entry_id, _daylight, _fmt = entry_of(path)
        scene = scenes.get(entry_id)
        if scene is None:
            raise SystemExit(f"no catalogue row for {path.name}")
        rel = f"assets/{path.name}"
        finish_date = dates.get(rel)
        if not finish_date:
            raise SystemExit(f"no finish date for {rel}")
        jobs.append((str(path), scene["caption"], scene["scenario_label"], finish_date))
    workers = min(8, os.cpu_count() or 4)
    reports = []
    date_counts: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, report in enumerate(pool.map(_job, jobs, chunksize=4), start=1):
            reports.append(report)
            date_counts[report["finish_date"]] = date_counts.get(report["finish_date"], 0) + 1
            if index % 50 == 0 or index == len(jobs):
                print(f"refinished {index}/{len(jobs)}", flush=True)
    hashes = {row["file"]: row["sha256"] for row in reports}
    manifests = update_manifests(hashes)
    summary = {
        "masters": len(reports),
        "scenes": len({row["entry_id"] for row in reports}),
        "16x9": sum(1 for row in reports if row["format"] == "16x9"),
        "4x5": sum(1 for row in reports if row["format"] == "4x5"),
        "9x16": 0,
        "daylight": sum(1 for row in reports if row["daylight"]),
        "night": sum(1 for row in reports if not row["daylight"]),
        "sizes": sorted({row["size"] for row in reports}),
        "finish_dates": date_counts,
        "manifests_updated": manifests,
        "above_scrim_changed": sum(row["above_changed"] for row in reports),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
