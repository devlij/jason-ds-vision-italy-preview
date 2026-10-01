#!/usr/bin/env python3
"""Durable Italy gallery publisher.

Rewrites index.html from the scene catalogue already in the page plus
tools/phase1_mood.json. Phase-1 (search + region, day/night, mood,
live count, clear-all, four related thumbs, copy-link, entry-id deep
links, and no controls for missing masters) is applied here, so a
rebuild cannot drop the Cosmo one-off patch.

360° motion buttons are file-gated. A scene gets a custom player
button only when assets/<scene>-motion-10s-4x5.mp4 exists. IT-01-024,
IT-01-032, and IT-01-248 never get a button, even if a clip file is
present. The player is custom controls only: autoplay, muted, loop,
playsinline, controls=false, disablePictureInPicture=true. Play switches
the card frame to the clip's native 4:5 aspect; close restores the
active format tab. The button stays on every format tab.

9:16 tabs are build-gated, not probe-gated. A 9:16 tab and an
always-visible Download 9:16 are emitted only when the master exists
on disk and opens at exactly 1080x1920. Missing files and invalid
1080x2110 masters get neither a tab nor a download. Tab switching
reads getAttribute("data-src-916"). This publisher removes the old
HEAD-probe mounter and re-applies the A7 head (canonical OG/Twitter
image, ImageGallery JSON-LD, title without "(preview)") so a rebuild
cannot drop them. Scene catalogues, word-of-day entries, and approval
fields are copied through unchanged. The image sitemap still lists
16:9 and 4:5 only.

Usage:
  python3 tools/publish_gallery.py          # write index.html
  python3 tools/publish_gallery.py --prove  # clobber + regenerate check
"""

from __future__ import annotations

import json
import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
MOODS = Path(__file__).resolve().parent / "phase1_mood.json"
MOOD_NAMES = ("coastal", "mountain", "urban", "historic")
IMAGE_FIELDS = (
    "file_16x9",
    "file_4x5",
    "file_16x9_day",
    "file_4x5_day",
)

CSS = """<!-- PHASE1-ITALY-CSS-START -->
<style>
/* PHASE1-ITALY */
/* Phase-1 competitive features (Spain pilot, emitted by tools/publish_gallery.py).
   Palette: Italy :root vars (--line #26402f, --muted #9db3a6, --text #eef4f0, --accent #35b577). */
.related{border-top:1px solid var(--line);margin:0 1rem 1.15rem;padding-top:12px}
.related-h{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.related-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.related-link{display:block;text-decoration:none}
.related-link img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;border:1px solid var(--line);border-radius:6px}
.related-link span{display:block;font-size:12px;color:var(--muted);padding:6px 0}
.related-link:hover span{color:var(--text)}
.actions button.copy-link{display:inline-block;background:#243049;color:var(--text);border-radius:8px;padding:0.4rem 0.7rem;font-size:0.85rem;border:1px solid var(--line);cursor:pointer}
.actions button.copy-link:hover{border-color:var(--accent)}
.motion-tab{display:inline-block;background:#243049;color:var(--text);border-radius:8px;padding:0.4rem 0.7rem;font-size:0.85rem;border:1px solid var(--line);cursor:pointer}
.motion-tab:hover{border-color:var(--accent)}
.motion-tab.is-active{border-color:var(--accent);color:var(--accent)}
.day-tab + .motion-tab{margin-left:0.35rem}
video.motion-clip{width:100%;height:100%;display:block;object-fit:cover;background:#000}
video.motion-clip::-webkit-media-controls{display:none!important}
@media(max-width:760px){.related-row{grid-template-columns:repeat(2,1fr)}}
</style>
<!-- PHASE1-ITALY-CSS-END -->
"""

FILTERS = """<!-- PHASE1-ITALY-FILTERS-START -->
      <select id="f-daynight" aria-label="Filter by time of day">
        <option value="">Day or night</option><option value="day">Day</option><option value="night">Night</option>
      </select>
      <select id="f-mood" aria-label="Filter by scene mood">
        <option value="">All moods</option><option value="coastal">Coastal</option><option value="mountain">Mountain</option><option value="urban">Urban</option><option value="historic">Historic</option>
      </select>
      <!-- PHASE1-ITALY-FILTERS-END -->
"""

REGION_SELECT = """      <select id="region" aria-label="Filter by region">
        <option value="">All regions</option>
      </select>
"""

MASTER_FN = """    function masterOk(path) {
      if (!path) return false;
      var bare = String(path).split("?")[0];
      return !(window.ITALY_MISSING && window.ITALY_MISSING[bare]);
    }

"""

RELATED_JS = """      /* PHASE1-ITALY-RELATED-START */
      const p1rids = (typeof relatedFor === "function") ? relatedFor(scene.entry_id) : [];
      const p1rel = p1rids.length
        ? '<div class="related"><p class="related-h">Related scenes</p><div class="related-row">'
          + p1rids.map(function(rid){
              var m = ITALY_META[rid];
              if (!m || !m[3] || (typeof masterOk === "function" && !masterOk(m[3]))) return "";
              var relScene = null;
              if (typeof SCENES !== "undefined") {
                for (var si = 0; si < SCENES.length; si++) {
                  if (SCENES[si].entry_id === rid) { relScene = SCENES[si]; break; }
                }
              }
              var relAlt = (relScene && typeof sceneAlt === "function") ? sceneAlt(relScene) : (m[4] + "");
              return '<a class="related-link" href="#' + rid + '">'
                + '<img loading="lazy" src="' + m[3] + '" alt="' + escapeHtml(relAlt) + '">'
                + '<span>' + escapeHtml(m[4]) + '</span></a>';
            }).join("")
          + '</div></div>'
        : "";
      /* PHASE1-ITALY-RELATED-END */
"""

F_LINES_BASE = """      const f16 = escapeHtml(scene.file_16x9);
      const f45 = escapeHtml(scene.file_4x5);
"""

LEGACY_F_LINES = """      const f16 = masterOk(scene.file_16x9) ? escapeHtml(scene.file_16x9) : "";
      const f45 = masterOk(scene.file_4x5) ? escapeHtml(scene.file_4x5) : "";
"""

F_LINES = """      const f16 = masterOk(scene.file_16x9) ? escapeHtml(scene.file_16x9) : "";
      const f45 = masterOk(scene.file_4x5) ? escapeHtml(scene.file_4x5) : "";
      const valid916 = (typeof ITALY_VALID_916 !== "undefined") ? ITALY_VALID_916[scene.entry_id] : null;
      const f916 = valid916 && valid916[0] ? escapeHtml(valid916[0]) : "";
      const f916day = valid916 && valid916[1] ? escapeHtml(valid916[1]) : "";
      const motion = (typeof ITALY_MOTION !== "undefined" && ITALY_MOTION[scene.entry_id]) ? escapeHtml(ITALY_MOTION[scene.entry_id]) : "";
"""

PREVIEW_BASE = """        <div class="preview">
            <a class="thumb" href="${f16}" target="_blank" rel="noopener">
            <img src="${f16}" data-src-16="${f16}" data-src-45="${f45}"${scene.file_16x9_day ? ` data-src-16-day="${escapeHtml(scene.file_16x9_day)}" data-src-45-day="${escapeHtml(scene.file_4x5_day)}"` : ""} alt="${alt}" loading="lazy" />
          </a>
        </div>
        <div class="fmt-tabs" role="group" aria-label="Image size">
            <button type="button" class="fmt-tab is-active" data-format="16x9">16:9</button>
            <button type="button" class="fmt-tab" data-format="4x5">4:5</button>
          </div>
        ${scene.file_16x9_day ? `<div class="day-row"><button type="button" class="day-tab" data-daynight="night" aria-pressed="false" title="Toggle the daylight variant">\\u2600 Daylight</button></div>` : ""}
"""

LEGACY_PREVIEW = """        <div class="preview">
            ${f16 ? `<a class="thumb" href="${f16}" target="_blank" rel="noopener">
            <img src="${f16}" data-src-16="${f16}" data-src-45="${f45}"${scene.file_16x9_day && masterOk(scene.file_16x9_day) ? ` data-src-16-day="${escapeHtml(scene.file_16x9_day)}" data-src-45-day="${escapeHtml(scene.file_4x5_day)}"` : ""} alt="${alt}" loading="lazy" />
          </a>` : ""}
        </div>
        <div class="fmt-tabs" role="group" aria-label="Image size">
            ${f16 ? `<button type="button" class="fmt-tab is-active" data-format="16x9">16:9</button>` : ""}
            ${f45 ? `<button type="button" class="fmt-tab" data-format="4x5">4:5</button>` : ""}
          </div>
        ${scene.file_16x9_day && masterOk(scene.file_16x9_day) ? `<div class="day-row"><button type="button" class="day-tab" data-daynight="night" aria-pressed="false" title="Toggle the daylight variant">\\u2600 Daylight</button></div>` : ""}
"""

PREVIEW = """        <div class="preview">
            ${f16 ? `<a class="thumb" href="${f16}" target="_blank" rel="noopener">
            <img src="${f16}" data-src-16="${f16}" data-src-45="${f45}"${f916 ? ` data-src-916="${f916}"` : ""}${f916day ? ` data-src-916-day="${f916day}"` : ""}${scene.file_16x9_day && masterOk(scene.file_16x9_day) ? ` data-src-16-day="${escapeHtml(scene.file_16x9_day)}" data-src-45-day="${escapeHtml(scene.file_4x5_day)}"` : ""} alt="${alt}" loading="lazy" />
          </a>` : ""}
        </div>
        <div class="fmt-tabs" role="group" aria-label="Image size">
            ${f16 ? `<button type="button" class="fmt-tab is-active" data-format="16x9">16:9</button>` : ""}
            ${f45 ? `<button type="button" class="fmt-tab" data-format="4x5">4:5</button>` : ""}
            ${f916 ? `<button type="button" class="fmt-tab" data-format="9x16">9:16</button>` : ""}
          </div>
        ${(scene.file_16x9_day && masterOk(scene.file_16x9_day)) || motion ? `<div class="day-row">${scene.file_16x9_day && masterOk(scene.file_16x9_day) ? `<button type="button" class="day-tab" data-daynight="night" aria-pressed="false" title="Toggle the daylight variant">\\u2600 Daylight</button>` : ""}${motion ? `<button type="button" class="motion-tab" data-motion="${motion}" title="Play the 360\\u00B0 motion clip">\\u25B6 360\\u00B0</button>` : ""}</div>` : ""}
"""

DOWNLOADS_BASE = """            <a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>
            <a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>
"""

LEGACY_DOWNLOADS = """            ${f16 ? `<a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>` : ""}
            ${f45 ? `<a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>` : ""}
"""

DOWNLOADS = """            ${f16 ? `<a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>` : ""}
            ${f45 ? `<a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>` : ""}
            ${f916 ? `<a class="download" data-dl="9x16" href="${f916}" download="${f916.split("/").pop()}">Download 9:16</a>` : ""}
"""

COPY_BTN = """            <button type="button" class="copy-link" data-scene="${id}" aria-label="Copy link to this scene">Copy link</button>
"""

BADGE = """            <a class="badge" href="#license">Free · no credit needed</a>
"""

FILTER_BASE = """    function filter() {
      const term = q.value.trim().toLowerCase();
      const reg = region.value.toLowerCase();
      const list = SCENES.filter(s => {
        if (reg && s.region.toLowerCase() !== reg) return false;
        if (!term) return true;
        const hay = [s.city, s.caption, s.region, s.entry_id, s.composition, s.description].join(" ").toLowerCase();
        return hay.includes(term);
      });
      render(list);
    }

    q.addEventListener("input", filter);
    region.addEventListener("change", filter);
    clearBtn.addEventListener("click", () => {
      q.value = "";
      region.value = "";
      filter();
    });
"""

FILTER = """    function filter() {
      const term = q.value.trim().toLowerCase();
      const reg = region.value.toLowerCase();
      const dn = daynightSel ? daynightSel.value : "";
      const mood = moodSel ? moodSel.value : "";
      const list = SCENES.filter(s => {
        if (reg && s.region.toLowerCase() !== reg) return false;
        const m = (typeof ITALY_META !== "undefined") ? ITALY_META[s.entry_id] : null;
        if (m) {
          if (dn && m[1] !== dn) return false;
          if (mood && ("," + (m[2] || "") + ",").indexOf("," + mood + ",") < 0) return false;
        }
        if (!term) return true;
        const hay = [s.city, s.caption, s.region, s.entry_id, s.composition, s.description].join(" ").toLowerCase();
        return hay.includes(term);
      });
      render(list);
    }

    q.addEventListener("input", filter);
    region.addEventListener("change", filter);
    if (daynightSel) daynightSel.addEventListener("change", filter);
    if (moodSel) moodSel.addEventListener("change", filter);
    clearBtn.addEventListener("click", () => {
      q.value = "";
      region.value = "";
      if (daynightSel) daynightSel.value = "";
      if (moodSel) moodSel.value = "";
      filter();
    });
"""

DEEP = """      render(SCENES);
      /* PHASE1-ITALY-DEEP */
      if (location.hash.length > 1) {
        var deep = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        if (deep && deep.scrollIntoView) deep.scrollIntoView();
      }
"""

CLICK = """<script>
/* PHASE1-ITALY-CLICK */
/* Phase-1: related-scene clicks clear filters first (survives re-renders);
   per-card copy-link buttons report Copied, then restore the label. */
(function(){
  var gal = document.getElementById('gallery');
  if (!gal) return;
  gal.addEventListener('click', function(e){
    if (!e.target || !e.target.closest) return;
    var rel = e.target.closest('.related-link');
    if (rel){
      var c = document.getElementById('clear');
      if (c) c.click();
      return;
    }
    var b = e.target.closest('.copy-link');
    if (!b) return;
    var url = location.origin + location.pathname + '#' + b.getAttribute('data-scene');
    var done = function(){ b.textContent = 'Copied \\u2713'; setTimeout(function(){ b.textContent = 'Copy link'; }, 1600); };
    function fb(){
      var ta = document.createElement('textarea'); ta.value = url;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch(err){}
      ta.remove();
    }
    if (navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(url).then(done, fb); }
    else { fb(); }
  });
})();
</script>
"""


# Night/twilight scenes that must never grow a 360 button, even when a
# clip file is sitting in assets/.
NO_MOTION = frozenset({"IT-01-024", "IT-01-032", "IT-01-248"})
TRUE_916 = (1080, 1920)

MOTION_FN = """    /* MOTION360-START */
    function stopMotion(cardEl) {
      if (!cardEl) return;
      var v = cardEl.querySelector("video.motion-clip");
      var link = cardEl.querySelector("a.thumb");
      var img = link && link.querySelector("img");
      var mtab = cardEl.querySelector(".motion-tab");
      if (v) v.remove();
      if (img) img.style.display = "";
      var ftab = cardEl.querySelector(".fmt-tab.is-active");
      var dfmt = ftab ? ftab.getAttribute("data-format") : "16x9";
      if (link) {
        link.classList.toggle("tall", dfmt === "4x5");
        link.classList.toggle("tall916", dfmt === "9x16");
      }
      if (mtab) {
        mtab.classList.remove("is-active");
        mtab.textContent = "\\u25B6 360\\u00B0";
      }
    }
    /* MOTION360-END */

"""

MOTION_CLICK = """      /* MOTION360-CLICK */
      const mtab = e.target.closest(".motion-tab");
      if (mtab && gallery.contains(mtab)) {
        e.preventDefault();
        const cardEl = mtab.closest(".card");
        if (!cardEl) return;
        if (cardEl.querySelector("video.motion-clip")) { stopMotion(cardEl); return; }
        const link = cardEl.querySelector("a.thumb");
        const img = link && link.querySelector("img");
        const src = mtab.getAttribute("data-motion");
        if (!link || !src) return;
        const vid = document.createElement("video");
        vid.className = "motion-clip";
        vid.src = src;
        vid.autoplay = true;
        vid.loop = true;
        vid.muted = true;
        vid.playsInline = true;
        vid.controls = false;
        vid.disablePictureInPicture = true;
        vid.setAttribute("autoplay", "");
        vid.setAttribute("muted", "");
        vid.setAttribute("loop", "");
        vid.setAttribute("playsinline", "");
        vid.removeAttribute("controls");
        if (img) img.style.display = "none";
        link.classList.add("tall");
        link.classList.remove("tall916");
        link.appendChild(vid);
        mtab.classList.add("is-active");
        mtab.textContent = "\\u2715 Close";
        return;
      }
      /* MOTION360-CLICK-END */

"""


def js_string(raw: str) -> str:
    return json.loads('"' + raw + '"')


def bare(path: str) -> str:
    return path.split("?", 1)[0]


def parse_scenes(html: str) -> list[dict]:
    start = html.find("const SCENES")
    if start < 0:
        raise SystemExit("index.html has no SCENES catalogue")
    end = html.find("\n    ];", start)
    body = html[start:end]
    chunks = re.split(r"\n\s*entry_id:\s*", body)[1:]
    scenes = []
    for ch in chunks:
        match = re.match(r'"(IT-[^"]+)"', ch)
        if not match:
            raise SystemExit("scene chunk missing entry_id")
        eid = match.group(1)

        def field(name: str, required: bool = True) -> str:
            found = re.search(rf'{name}:\s*"((?:\\.|[^"\\])*)"', ch)
            if not found:
                if required:
                    raise SystemExit(f"{eid} missing {name}")
                return ""
            return js_string(found.group(1))

        scenes.append(
            {
                "entry_id": eid,
                "region": field("region"),
                "caption": field("caption"),
                "file_16x9": field("file_16x9"),
                "file_4x5": field("file_4x5"),
                "file_9x16": field("file_9x16", False),
                "file_16x9_day": field("file_16x9_day", False),
                "file_4x5_day": field("file_4x5_day", False),
                "file_9x16_day": field("file_9x16_day", False),
            }
        )
    if len(scenes) != len({s["entry_id"] for s in scenes}):
        raise SystemExit("duplicate entry ids in SCENES")
    return scenes


def load_moods() -> dict:
    if not MOODS.is_file():
        raise SystemExit(f"missing {MOODS}")
    data = json.loads(MOODS.read_text(encoding="utf-8"))
    for eid, row in data.items():
        if row.get("daynight") not in ("day", "night", ""):
            raise SystemExit(f"{eid} daynight {row.get('daynight')!r}")
        moods = row.get("moods") or []
        bad = [m for m in moods if m not in MOOD_NAMES]
        if bad:
            raise SystemExit(f"{eid} mood tags {bad}")
    return data


def missing_masters(scenes: list[dict]) -> dict[str, int]:
    missing: dict[str, int] = {}
    for scene in scenes:
        for key in IMAGE_FIELDS:
            path = scene.get(key) or ""
            if not path:
                continue
            rel = bare(path)
            if not (ROOT / rel).is_file():
                missing[rel] = 1
    return missing


def build_meta(scenes: list[dict], moods: dict, missing: dict[str, int]) -> dict:
    meta = {}
    for scene in scenes:
        eid = scene["entry_id"]
        row = moods.get(eid) or {"daynight": "", "moods": []}
        thumb = scene["file_16x9"]
        if not thumb or bare(thumb) in missing:
            thumb = ""
        meta[eid] = [
            scene["region"],
            row.get("daynight") or "",
            ",".join(row.get("moods") or []),
            thumb,
            scene["caption"],
        ]
    return meta


def clip_exists(rel: str) -> bool:
    path = ROOT / rel
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def motion_rel(entry_id: str) -> str:
    return f"assets/{entry_id.lower()}-motion-10s-4x5.mp4"


def build_motion(scenes: list[dict]) -> dict[str, str]:
    """Clip path for every scene whose mp4 exists, minus the night exclusions."""
    found: dict[str, str] = {}
    for scene in scenes:
        eid = scene["entry_id"]
        if eid in NO_MOTION:
            continue
        rel = motion_rel(eid)
        if clip_exists(rel):
            found[eid] = rel
    return found


def derive_916(path: str) -> str:
    rel = bare(path)
    if rel.endswith("-16x9.png"):
        return rel[: -len("-16x9.png")] + "-9x16.png"
    return ""


def day_916_rel(scene: dict) -> str:
    explicit = bare(scene.get("file_9x16_day") or "")
    if explicit:
        return explicit
    day = scene.get("file_16x9_day") or ""
    derived = derive_916(day) if day else ""
    if derived:
        return derived
    night = bare(scene.get("file_16x9") or "")
    if night.endswith("-16x9.png"):
        return night[: -len("-16x9.png")] + "-daylight-9x16.png"
    return ""


def png_ihdr(path: Path) -> tuple[int, int] | None:
    """Return width, height when the file is a PNG with a readable IHDR."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    length = struct.unpack(">I", data[8:12])[0]
    if data[12:16] != b"IHDR" or length < 13 or len(data) < 24 + 4:
        return None
    chunk = data[16:16 + length]
    crc = struct.unpack(">I", data[16 + length:20 + length])[0]
    if (zlib.crc32(b"IHDR" + chunk) & 0xFFFFFFFF) != crc:
        return None
    width, height = struct.unpack(">II", chunk[:8])
    return width, height


def png_opens_at(path: Path, size: tuple[int, int]) -> bool:
    """True when the PNG opens and its IHDR is exactly size.

    Files that are not that size are rejected from the header. A file that
    claims the size must decompress cleanly, so a truncated or corrupt
    master is not wired.
    """
    ihdr = png_ihdr(path)
    if ihdr != size:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    pos = 8
    bit_depth = color_type = None
    idat: list[bytes] = []
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        pos += 8
        if pos + length + 4 > len(data):
            return False
        chunk = data[pos:pos + length]
        crc = struct.unpack(">I", data[pos + length:pos + length + 4])[0]
        if (zlib.crc32(ctype + chunk) & 0xFFFFFFFF) != crc:
            return False
        pos += length + 4
        if ctype == b"IHDR":
            bit_depth = chunk[8]
            color_type = chunk[9]
        elif ctype == b"IDAT":
            idat.append(chunk)
        elif ctype == b"IEND":
            break
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if bit_depth != 8 or not channels or not idat:
        return False
    width, height = size
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error:
        return False
    return len(raw) == height * (1 + width * channels)


def build_valid_916(scenes: list[dict]) -> dict[str, list[str]]:
    """Scenes whose 9:16 master exists and opens at exactly 1080x1920."""
    found: dict[str, list[str]] = {}
    for scene in scenes:
        rel = bare(scene.get("file_9x16") or "") or derive_916(scene.get("file_16x9") or "")
        if not rel or not png_opens_at(ROOT / rel, TRUE_916):
            continue
        day_rel = day_916_rel(scene)
        day = day_rel if day_rel and png_opens_at(ROOT / day_rel, TRUE_916) else ""
        found[scene["entry_id"]] = [rel, day]
    return found


def meta_script(
    meta: dict,
    missing: dict[str, int],
    motion: dict[str, str],
    valid916: dict[str, list[str]],
) -> str:
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    missing_js = json.dumps(missing, ensure_ascii=False, separators=(",", ":"))
    motion_js = json.dumps(motion, ensure_ascii=False, separators=(",", ":"))
    valid_js = json.dumps(valid916, ensure_ascii=False, separators=(",", ":"))
    return f"""<script>
/* PHASE1-ITALY */
/* Phase-1 feature data. Emitted by tools/publish_gallery.py.
   per-scene [region, day|night, mood tags, 16:9 thumb, display name].
   A blank thumb means the 16:9 master is missing and must not be rendered.
   ITALY_MOTION maps a scene to its 10s 4:5 clip. IT-01-024, IT-01-032, and
   IT-01-248 are never present. ITALY_VALID_916 maps a scene to
   [1080x1920 master, daylight master or ""]. */
const ITALY_META = {payload};
window.ITALY_MISSING = {missing_js};
const ITALY_MOTION = {motion_js};
const ITALY_VALID_916 = {valid_js};
function relatedFor(id){{
  var me = ITALY_META[id]; if(!me) return [];
  var mm = (me[2]||'').split(',').filter(Boolean); var out=[];
  for (var oid in ITALY_META){{
    if (oid===id) continue;
    var o = ITALY_META[oid];
    if (!o[3]) continue;
    var bare = String(o[3]).split('?')[0];
    if (window.ITALY_MISSING && window.ITALY_MISSING[bare]) continue;
    var om=','+(o[2]||'')+',', shared=0;
    for (var i=0;i<mm.length;i++){{ if (om.indexOf(','+mm[i]+',')>=0) shared++; }}
    if (o[0]===me[0] || shared>0) out.push([(o[0]===me[0]?0:1), -shared, oid]);
  }}
  out.sort(function(a,b){{ return a[0]-b[0] || a[1]-b[1] || (a[2]<b[2]?-1:1); }});
  return out.slice(0,4).map(function(x){{ return x[2]; }});
}}
</script>
"""


CANONICAL = "https://italy.jdvision.org/"
# First published scene (IT-01-001). Confirmed on disk and on the live host.
OG_IMAGE = CANONICAL + "assets/it-01-001-16x9.png"


def _between(html: str, start: str, end: str) -> str:
    s = html.find(start)
    if s < 0:
        raise SystemExit(f"missing {start!r}")
    e = html.find(end, s + len(start))
    if e < 0:
        raise SystemExit(f"missing {end!r} after {start!r}")
    return html[s:e]


def remove_probe916(html: str) -> str:
    """Drop the browser HEAD probe that mounted 9:16 for any 200 response.

    A 200 from an invalid 1080x2110 master reads as a broken tab. Tabs are
    emitted at build time only, so this mounter must not survive a rebuild.
    """
    pattern = re.compile(
        r"\n    /\* 9:16 tab and Download 9:16 are mounted only after a HEAD probe returns 200\."
        r"[\s\S]*?\n    function queue916\(cardEl, scene\) \{\n"
        r"(?:.*\n)*?    \}\n"
    )
    html = pattern.sub("\n", html)
    html = html.replace("      queue916(el, scene);\n", "")
    return html


def remove_916_ui(html: str) -> str:
    return remove_probe916(html)


def _restore_base(html: str, current: str, legacy: str, base: str) -> str:
    """Put a card snippet back to the pre-rollout shell.

    The current snippet is replaced whole. The legacy snippet is only
    replaced when the current one is absent, because the legacy text can
    be a prefix of the current text.
    """
    if current in html:
        return html.replace(current, base)
    if legacy in html:
        return html.replace(legacy, base)
    return html


def apply_a7(html: str) -> str:
    """Lock the A7 head onto the Italy canonical URL. Idempotent."""
    html = remove_916_ui(html)
    html = re.sub(
        r"(<title>Jason D\u2019s Vision \u2014 Italy) \(preview\)(</title>)",
        r"\1\2",
        html,
        count=1,
    )
    html = re.sub(
        r'<link rel="canonical" href="[^"]*"\s*/>',
        f'<link rel="canonical" href="{CANONICAL}" />',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta property="og:image" content="[^"]*"/>',
        f'<meta property="og:image" content="{OG_IMAGE}"/>',
        html,
        count=1,
    )
    html = re.sub(
        r'<meta property="og:url" content="[^"]*"/>',
        f'<meta property="og:url" content="{CANONICAL}"/>',
        html,
        count=1,
    )
    og_title = "Jason D's Vision — Italy"
    og_desc = "AI-generated artistic interpretations of Italy. Free to use, no credit required."
    found_title = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    found_desc = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    if found_title:
        og_title = found_title.group(1)
    if found_desc:
        og_desc = found_desc.group(1)
    twitter = (
        '<meta name="twitter:card" content="summary_large_image"/>\n'
        f'<meta name="twitter:title" content="{og_title}"/>\n'
        f'<meta name="twitter:description" content="{og_desc}"/>\n'
        f'<meta name="twitter:image" content="{OG_IMAGE}"/>'
    )
    if 'name="twitter:title"' not in html:
        html = html.replace(
            '<meta name="twitter:card" content="summary_large_image"/>',
            twitter,
            1,
        )
    else:
        html = re.sub(
            r'<meta name="twitter:title" content="[^"]*"/>',
            f'<meta name="twitter:title" content="{og_title}"/>',
            html,
            count=1,
        )
        html = re.sub(
            r'<meta name="twitter:description" content="[^"]*"/>',
            f'<meta name="twitter:description" content="{og_desc}"/>',
            html,
            count=1,
        )
        html = re.sub(
            r'<meta name="twitter:image" content="[^"]*"/>',
            f'<meta name="twitter:image" content="{OG_IMAGE}"/>',
            html,
            count=1,
        )
    meta_desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    description = (
        meta_desc.group(1)
        if meta_desc
        else "AI-generated artistic interpretations of Italy. Free to use, no credit required."
    )
    payload = {
        "@context": "https://schema.org",
        "@type": "ImageGallery",
        "name": "Jason D's Vision \u2014 Italy",
        "url": CANONICAL,
        "description": description,
        "inLanguage": "en",
        "creator": {
            "@type": "Organization",
            "name": "Jason D's Vision",
        },
    }
    block = (
        '<script type="application/ld+json">\n'
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n</script>"
    )
    html, n = re.subn(
        r'<script type="application/ld\+json">.*?</script>',
        lambda _m: block,
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit(f"JSON-LD block: expected 1, found {n}")
    if not (ROOT / "assets/it-01-001-16x9.png").is_file():
        raise SystemExit("first-scene 16:9 master missing: assets/it-01-001-16x9.png")
    return html


def _replace_once(html: str, old: str, new: str, label: str) -> str:
    count = html.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return html.replace(old, new, 1)


def strip_phase1(html: str) -> str:
    """Return the gallery page without Phase-1, matching the pre-rollout shell."""
    html = remove_916_ui(html)
    html = re.sub(
        r"<!-- PHASE1-ITALY-CSS-START -->.*?<!-- PHASE1-ITALY-CSS-END -->\n",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"<style>\n/\* PHASE1-ITALY \*/.*?</style>\n",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"<!-- PHASE1-ITALY-FILTERS-START -->.*?<!-- PHASE1-ITALY-FILTERS-END -->\n",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"\n      <select id=\"f-daynight\"[\s\S]*?</select>\n      <select id=\"f-mood\"[\s\S]*?</select>",
        "",
        html,
        count=1,
    )
    html = re.sub(
        r"<script>\n/\* PHASE1-ITALY \*/[\s\S]*?</script>\n",
        "",
        html,
        count=1,
    )
    html = re.sub(
        r"<script>\n/\* PHASE1-ITALY-CLICK \*/[\s\S]*?</script>\n",
        "",
        html,
    )
    # Cosmo click script has no CLICK marker.
    html = re.sub(
        r"<script>\n/\* PHASE1-ITALY \*/\n/\* Phase-1 competitive features[\s\S]*?</script>\n",
        "",
        html,
    )
    html = html.replace("      el.id = scene.entry_id;\n", "")
    html = html.replace("      el.id = scene.entry_id; /* PHASE1-ITALY-ID */\n", "")
    html = re.sub(
        r"      /\* PHASE1-ITALY-RELATED-START \*/.*?/\* PHASE1-ITALY-RELATED-END \*/\n",
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        r"      // Phase-1: related-scenes row[\s\S]*?const p1rel = p1rids\.length\n"
        r"        \? '<div class=\"related\">[\s\S]*?: \"\";\n",
        "",
        html,
    )
    html = html.replace("        ${p1rel}\n", "")
    html = html.replace(COPY_BTN, "")
    html = html.replace(MASTER_FN, "")
    html = _restore_base(html, F_LINES, LEGACY_F_LINES, F_LINES_BASE)
    html = _restore_base(html, PREVIEW, LEGACY_PREVIEW, PREVIEW_BASE)
    html = _restore_base(html, DOWNLOADS, LEGACY_DOWNLOADS, DOWNLOADS_BASE)
    html = html.replace(
        "    const daynightSel = document.getElementById(\"f-daynight\");\n"
        "    const moodSel = document.getElementById(\"f-mood\");\n",
        "",
    )
    if FILTER in html:
        html = html.replace(FILTER, FILTER_BASE)
    else:
        html = re.sub(
            r"    function filter\(\) \{\n      const term = q\.value\.trim\(\)\.toLowerCase\(\);\n"
            r"      const reg = region\.value\.toLowerCase\(\);\n"
            r"      const dn = daynightSel\.value;[\s\S]*?      filter\(\);\n    \}\);\n",
            FILTER_BASE,
            html,
            count=1,
        )
    html = html.replace(DEEP, "      render(SCENES);\n")
    return html


def insert_phase1(
    html: str,
    meta: dict,
    missing: dict[str, int],
    motion: dict[str, str],
    valid916: dict[str, list[str]],
) -> str:
    if "PHASE1-ITALY-CSS-START" not in html:
        html = _replace_once(html, "</head>", CSS + "</head>", "css anchor")
    if "PHASE1-ITALY-FILTERS-START" not in html:
        html = _replace_once(html, REGION_SELECT, REGION_SELECT + FILTERS, "region select")
    if "const ITALY_META" not in html:
        anchor = "  <script>\n    // Approved scenes only"
        html = _replace_once(
            html,
            anchor,
            meta_script(meta, missing, motion, valid916) + anchor,
            "scenes script",
        )
    else:
        html = re.sub(
            r"<script>\n/\* PHASE1-ITALY \*/[\s\S]*?</script>\n",
            meta_script(meta, missing, motion, valid916),
            html,
            count=1,
        )
    if "function masterOk(" not in html:
        html = _replace_once(html, "    function card(scene) {", MASTER_FN + "    function card(scene) {", "card fn")
    if "el.id = scene.entry_id" not in html:
        html = _replace_once(
            html,
            '      el.className = "card";\n',
            '      el.className = "card";\n      el.id = scene.entry_id; /* PHASE1-ITALY-ID */\n',
            "card class",
        )
    if F_LINES_BASE in html:
        html = _replace_once(html, F_LINES_BASE, F_LINES, "file consts")
    if "PHASE1-ITALY-RELATED-START" not in html:
        html = _replace_once(html, "el.innerHTML = `", RELATED_JS + "el.innerHTML = `", "related block")
    if PREVIEW_BASE in html:
        html = _replace_once(html, PREVIEW_BASE, PREVIEW, "preview block")
    if DOWNLOADS_BASE in html:
        html = _replace_once(html, DOWNLOADS_BASE, DOWNLOADS, "downloads")
    if 'class="copy-link"' not in html:
        html = _replace_once(html, BADGE, BADGE + COPY_BTN, "badge")
    if "${p1rel}" not in html:
        html = _replace_once(html, "        </div>\n      `;", "        </div>\n        ${p1rel}\n      `;", "card close")
    if 'getElementById("f-daynight")' not in html:
        html = _replace_once(
            html,
            '    const clearBtn = document.getElementById("clear");\n',
            '    const clearBtn = document.getElementById("clear");\n'
            '    const daynightSel = document.getElementById("f-daynight");\n'
            '    const moodSel = document.getElementById("f-mood");\n',
            "clear btn",
        )
    if FILTER_BASE in html:
        html = _replace_once(html, FILTER_BASE, FILTER, "filter")
    if "PHASE1-ITALY-DEEP" not in html:
        html = _replace_once(
            html,
            "      render(SCENES);\n",
            DEEP,
            "initial render",
        )
    if "PHASE1-ITALY-CLICK" not in html:
        html = _replace_once(html, "</body>", CLICK + "</body>", "body close")
    return html


def inject_motion(html: str) -> str:
    """Install the custom 360 player once. Idempotent across rebuilds."""
    listener = '    gallery.addEventListener("click", (e) => {\n'
    if "MOTION360-START" not in html:
        if html.count(listener) != 1:
            raise SystemExit(f"motion anchor: expected 1, found {html.count(listener)}")
        html = html.replace(listener, MOTION_FN + listener, 1)
    click_anchor = listener + '      const nbtn = e.target.closest(".narrate");\n'
    if "MOTION360-CLICK" not in html:
        if html.count(click_anchor) != 1:
            raise SystemExit(f"motion click anchor: expected 1, found {html.count(click_anchor)}")
        html = html.replace(
            click_anchor,
            listener + MOTION_CLICK + '      const nbtn = e.target.closest(".narrate");\n',
            1,
        )
    day_old = '        const dcard = dtab.closest(".card");\n        if (!dcard) return;\n'
    day_new = day_old + "        stopMotion(dcard);\n"
    if "stopMotion(dcard)" not in html:
        html = _replace_once(html, day_old, day_new, "day stopMotion")
    fmt_old = '      const cardEl = tab.closest(".card");\n      const link = cardEl && cardEl.querySelector("a.thumb");\n'
    fmt_new = (
        '      const cardEl = tab.closest(".card");\n'
        '      stopMotion(cardEl); /* MOTION360-FMT */\n'
        '      const link = cardEl && cardEl.querySelector("a.thumb");\n'
    )
    if "MOTION360-FMT" not in html:
        html = _replace_once(html, fmt_old, fmt_new, "fmt stopMotion")
    guard = 'if(e.target.closest&&e.target.closest("video.motion-clip")){e.preventDefault();return;}'
    lb_old = "if(a){e.preventDefault();var cards=visibleCards();"
    lb_new = "if(a){" + guard + "e.preventDefault();var cards=visibleCards();"
    if guard not in html:
        html = _replace_once(html, lb_old, lb_new, "lightbox motion guard")
    html = html.replace("16:9 / 4:5 / probe-gated 9:16 tabs", "16:9 / 4:5 / 9:16 tabs")
    return html


def publish(html: str, moods: dict | None = None) -> str:
    moods = moods if moods is not None else load_moods()
    scenes_blob = _between(html, "const SCENES = [", "\n    ];")
    wotd_blob = _between(html, 'id="wotd-data">', "</script>")
    base = strip_phase1(html)
    scenes = parse_scenes(base)
    missing = missing_masters(scenes)
    meta = build_meta(scenes, moods, missing)
    motion = build_motion(scenes)
    valid916 = build_valid_916(scenes)
    for eid in NO_MOTION:
        if eid in motion:
            raise SystemExit(f"{eid} must not be wired for 360")
    unknown = [s["entry_id"] for s in scenes if s["entry_id"] not in moods]
    if unknown:
        print(f"warning: {len(unknown)} scenes have no mood row; filters will not match them", file=sys.stderr)
    out = inject_motion(apply_a7(insert_phase1(base, meta, missing, motion, valid916)))
    if _between(out, "const SCENES = [", "\n    ];") != scenes_blob:
        raise SystemExit("publisher changed the SCENES catalogue")
    if _between(out, 'id="wotd-data">', "</script>") != wotd_blob:
        raise SystemExit("publisher changed the word-of-day dataset")
    if "function probe916(" in out or "queue916(" in out:
        raise SystemExit("publisher left the 9:16 HEAD probe in place")
    return out


def related_ids(meta: dict, entry_id: str, missing: dict[str, int] | None = None) -> list[str]:
    """Python twin of the emitted relatedFor, for the regenerate proof."""
    missing = missing or {}
    me = meta[entry_id]
    mine = [t for t in me[2].split(",") if t]
    out = []
    for oid, other in meta.items():
        if oid == entry_id or not other[3]:
            continue
        if bare(other[3]) in missing:
            continue
        theirs = "," + (other[2] or "") + ","
        shared = sum(1 for tag in mine if f",{tag}," in theirs)
        if other[0] == me[0] or shared:
            out.append((0 if other[0] == me[0] else 1, -shared, oid))
    out.sort(key=lambda row: (row[0], row[1], row[2]))
    return [row[2] for row in out[:4]]


def prove(html: str) -> None:
    moods = load_moods()
    first = publish(html, moods)
    clobbered = strip_phase1(first)
    for needle in ("f-daynight", "ITALY_META", "copy-link", "PHASE1-ITALY", "relatedFor"):
        if needle in clobbered:
            raise SystemExit(f"strip left {needle}")
    second = publish(clobbered, moods)
    if first != second:
        raise SystemExit("regenerating a clobbered index did not match the publisher output")
    third = publish(second, moods)
    if third != second:
        raise SystemExit("publisher is not idempotent")
    scenes = parse_scenes(second)
    missing = missing_masters(scenes)
    meta = build_meta(scenes, moods, missing)
    if len(scenes) != 375 or len(meta) != 375:
        raise SystemExit(f"scene count {len(scenes)} meta {len(meta)}")
    if missing:
        raise SystemExit(f"live catalogue references missing masters: {sorted(missing)[:8]}")
    for eid in meta:
        got = related_ids(meta, eid)
        if len(got) != 4:
            raise SystemExit(f"{eid} related {got}")
        regions = [meta[rid][0] for rid in got]
        if meta[eid][0] in {meta[k][0] for k in meta if k != eid}:
            if regions[0] != meta[eid][0]:
                raise SystemExit(f"{eid} first related is not same region: {got}")
        if got != sorted(got, key=lambda rid: (
            0 if meta[rid][0] == meta[eid][0] else 1,
            -sum(1 for tag in meta[eid][2].split(",") if tag and tag in meta[rid][2].split(",")),
            rid,
        )):
            raise SystemExit(f"{eid} related order is not deterministic")
    # A missing 16:9 master drops that thumb and the next ranked scene fills the row.
    sample = "IT-01-001"
    top = related_ids(meta, sample)[0]
    robbed = json.loads(json.dumps(meta))
    robbed[top][3] = ""
    filled = related_ids(robbed, sample)
    if top in filled or len(filled) != 4:
        raise SystemExit(f"missing-master related fill failed: {filled}")
    identity = [
        "G-PDJ4WSS725",
        "flag-band",
        "Free · no credit needed",
        "lb-play",
        "fmt-tab",
        "id=\"result-count\"",
        "id=\"clear\"",
        "id=\"q\"",
        "id=\"region\"",
        "el.id = scene.entry_id",
        "Copy link</button>",
        "Copied \\u2713",
        "Coastal",
        "f-daynight",
        "f-mood",
        "masterOk",
        "PHASE1-ITALY-DEEP",
        "How our images are made",
        "https://italy.jdvision.org/assets/it-01-001-16x9.png",
        '"@type": "ImageGallery"',
        '"@type": "Organization"',
        'name="twitter:image"',
        'getAttribute("data-src-45")',
        'getAttribute("data-format")',
        'getAttribute("data-src-916")',
        "Day '+doy+' of 365",
        "disablePictureInPicture = true",
        "vid.controls = false",
        "vid.playsInline = true",
        'class="motion-tab"',
        "ITALY_MOTION",
        "ITALY_VALID_916",
        "Download 9:16",
        'data-format="9x16"',
    ]
    for needle in identity:
        if needle not in second:
            raise SystemExit(f"regenerated index lost {needle}")
    banned = (
        "(preview)</title>",
        "dataset.format",
        "dataset.src45",
        "dataset.src916",
        "function probe916(",
        "function mount916(",
        "function queue916(",
        'method: "HEAD"',
    )
    for needle in banned:
        if needle in second:
            raise SystemExit(f"regenerated index still has {needle}")
    tabs = _between(second, '<div class="fmt-tabs"', "</div>")
    if '${f916 ?' not in tabs or 'data-format="9x16"' not in tabs:
        raise SystemExit("9:16 tab is not build-gated inside fmt-tabs")
    motion_map, valid_map = wiring_maps(second)
    for eid in NO_MOTION:
        if eid in motion_map:
            raise SystemExit(f"{eid} is wired for 360")
        rel = motion_rel(eid)
        if eid in motion_map:
            raise SystemExit(f"{eid} button survived the exclusion")
    for eid, rel in motion_map.items():
        if eid in NO_MOTION or rel != motion_rel(eid) or not clip_exists(rel):
            raise SystemExit(f"bad 360 wiring {eid} {rel}")
    for eid, pair in valid_map.items():
        if len(pair) != 2 or not png_opens_at(ROOT / pair[0], TRUE_916):
            raise SystemExit(f"bad 9:16 wiring {eid} {pair}")
        if pair[1] and not png_opens_at(ROOT / pair[1], TRUE_916):
            raise SystemExit(f"bad daylight 9:16 wiring {eid} {pair}")
    sample_invalid = ROOT / "assets/it-01-001-9x16.png"
    if sample_invalid.is_file() and png_ihdr(sample_invalid) != TRUE_916:
        if any(pair[0].endswith("/it-01-001-9x16.png") or pair[0] == "assets/it-01-001-9x16.png" for pair in valid_map.values()):
            raise SystemExit("invalid it-01-001 9:16 master was wired")
    ga = set(re.findall(r"G-[A-Z0-9]+", second))
    if ga != {"G-PDJ4WSS725"}:
        raise SystemExit(f"GA4 ids {ga}")
    if "https://devlij.github.io/" in re.search(r'property="og:image"[^>]*>', second).group(0):
        raise SystemExit("og:image is not the canonical host")
    print("prove ok")
    print(f"scenes {len(scenes)}")
    print(f"missing masters in live catalogue {len(missing)}")
    print(f"360 buttons {len(motion_map)}")
    print(f"9:16 tabs {len(valid_map)}")
    print(f"360 excluded {', '.join(sorted(NO_MOTION))}")
    print(f"sample {sample} related {related_ids(meta, sample)}")
    print(f"missing thumb {top} replaced by {filled}")
    print(f"idempotent bytes {len(second)}")


def wiring_maps(html: str) -> tuple[dict, dict]:
    motion_match = re.search(r"const ITALY_MOTION = (\{.*?\});\n", html)
    valid_match = re.search(r"const ITALY_VALID_916 = (\{.*?\});\n", html)
    if not motion_match or not valid_match:
        raise SystemExit("publisher did not emit ITALY_MOTION / ITALY_VALID_916")
    return json.loads(motion_match.group(1)), json.loads(valid_match.group(1))


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    if "--prove" in sys.argv:
        prove(html)
        return
    published = publish(html)
    if published != html:
        INDEX.write_text(published, encoding="utf-8")
        print(f"wrote {INDEX}")
    else:
        print("index.html already matches the publisher")
    prove(published)


if __name__ == "__main__":
    main()
