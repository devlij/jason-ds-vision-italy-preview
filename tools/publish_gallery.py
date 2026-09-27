#!/usr/bin/env python3
"""Durable Italy gallery publisher.

Rewrites index.html from the scene catalogue already in the page plus
tools/phase1_mood.json. Phase-1 (search + region, day/night, mood,
live count, clear-all, four related thumbs, copy-link, entry-id deep
links, and no controls for missing masters) is applied here, so a
rebuild cannot drop the Cosmo one-off patch.

Italy standing order: there is no 9:16 option. This publisher never
emits a 9:16 tab or download, and it re-applies the A7 head (canonical
OG/Twitter image, ImageGallery JSON-LD, title without
"(preview)") so a rebuild cannot drop them. Scene catalogues, word-of-day
entries, and approval fields are copied through unchanged.

Usage:
  python3 tools/publish_gallery.py          # write index.html
  python3 tools/publish_gallery.py --prove  # clobber + regenerate check
"""

from __future__ import annotations

import json
import re
import sys
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
              return '<a class="related-link" href="#' + rid + '">'
                + '<img loading="lazy" src="' + m[3] + '" alt="' + escapeHtml(m[4]) + '">'
                + '<span>' + escapeHtml(m[4]) + '</span></a>';
            }).join("")
          + '</div></div>'
        : "";
      /* PHASE1-ITALY-RELATED-END */
"""

F_LINES_BASE = """      const f16 = escapeHtml(scene.file_16x9);
      const f45 = escapeHtml(scene.file_4x5);
"""

F_LINES = """      const f16 = masterOk(scene.file_16x9) ? escapeHtml(scene.file_16x9) : "";
      const f45 = masterOk(scene.file_4x5) ? escapeHtml(scene.file_4x5) : "";
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

PREVIEW = """        <div class="preview">
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

DOWNLOADS_BASE = """            <a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>
            <a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>
"""

DOWNLOADS = """            ${f16 ? `<a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>` : ""}
            ${f45 ? `<a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>` : ""}
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


def meta_script(meta: dict, missing: dict[str, int]) -> str:
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    missing_js = json.dumps(missing, ensure_ascii=False, separators=(",", ":"))
    return f"""<script>
/* PHASE1-ITALY */
/* Phase-1 feature data. Emitted by tools/publish_gallery.py.
   per-scene [region, day|night, mood tags, 16:9 thumb, display name].
   A blank thumb means the 16:9 master is missing and must not be rendered. */
const ITALY_META = {payload};
window.ITALY_MISSING = {missing_js};
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


def remove_916_ui(html: str) -> str:
    """Italy standing order: no 9:16 tab, download, or format branch."""
    replacements = (
        ('${f916 ? ` data-src-916="${f916}"` : ""}', ""),
        (
            '${scene.file_9x16_day ? ` data-src-916-day="${escapeHtml(scene.file_9x16_day)}"` : ""}',
            "",
        ),
        (
            '${scene.file_9x16_day && masterOk(scene.file_9x16_day) ? ` data-src-916-day="${escapeHtml(scene.file_9x16_day)}"` : ""}',
            "",
        ),
        (
            '            ${f916 ? `<button type="button" class="fmt-tab" data-format="9x16">9:16</button>` : ""}\n',
            "",
        ),
        (
            '            <button type="button" class="fmt-tab" data-format="4x5">4:5</button>\n'
            '            ${f916 ? `<button type="button" class="fmt-tab" data-format="9x16">9:16</button>` : ""}\n',
            '            <button type="button" class="fmt-tab" data-format="4x5">4:5</button>\n',
        ),
        ('      const f916 = scene.file_9x16 ? escapeHtml(scene.file_9x16) : "";\n', ""),
        ('      const f916 = masterOk(scene.file_9x16) ? escapeHtml(scene.file_9x16) : "";\n', ""),
        (
            '            ${f916 ? `<a class="download" data-dl="9x16" href="${f916}" download="${basename(scene.file_9x16)}">Download 9:16</a>` : ""}\n',
            "",
        ),
        ("    .thumb.tall916 { aspect-ratio: 9 / 16; }\n", ""),
        ('      const fmt = tab.dataset.format;\n', '      const fmt = tab.getAttribute("data-format");\n'),
        (
            ' : dfmt === "9x16" ? (isDay ? "data-src-916-day" : "data-src-916")',
            "",
        ),
        (
            ' : f === "9x16" ? (isDay ? "data-src-916-day" : "data-src-916")',
            "",
        ),
        (
            '        : fmt === "9x16"\n'
            '        ? (useDay && img.getAttribute("data-src-916-day")) || img.getAttribute("data-src-916")\n',
            "",
        ),
        (' link.classList.toggle("tall916", fmt === "9x16");', ""),
        (
            "lbFormat==='4x5'?'data-src-45':lbFormat==='9x16'?'data-src-916':'data-src-16'",
            "lbFormat==='4x5'?'data-src-45':'data-src-16'",
        ),
        (
            "lbFormat==='4x5'?'data-src-45-day':lbFormat==='9x16'?'data-src-916-day':'data-src-16-day'",
            "lbFormat==='4x5'?'data-src-45-day':'data-src-16-day'",
        ),
        (
            "(tab&&tab.getAttribute('data-format')==='9x16')?'9x16':(tab&&tab.getAttribute('data-format')==='4x5')?'4x5':'16x9'",
            "(tab&&tab.getAttribute('data-format')==='4x5')?'4x5':'16x9'",
        ),
    )
    for old, new in replacements:
        html = html.replace(old, new)
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
    html = html.replace(F_LINES, F_LINES_BASE)
    html = html.replace(PREVIEW, PREVIEW_BASE)
    html = html.replace(DOWNLOADS, DOWNLOADS_BASE)
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


def insert_phase1(html: str, meta: dict, missing: dict[str, int]) -> str:
    if "PHASE1-ITALY-CSS-START" not in html:
        html = _replace_once(html, "</head>", CSS + "</head>", "css anchor")
    if "PHASE1-ITALY-FILTERS-START" not in html:
        html = _replace_once(html, REGION_SELECT, REGION_SELECT + FILTERS, "region select")
    if "const ITALY_META" not in html:
        anchor = "  <script>\n    // Approved scenes only"
        html = _replace_once(html, anchor, meta_script(meta, missing) + anchor, "scenes script")
    else:
        html = re.sub(
            r"<script>\n/\* PHASE1-ITALY \*/[\s\S]*?</script>\n",
            meta_script(meta, missing),
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


def publish(html: str, moods: dict | None = None) -> str:
    moods = moods if moods is not None else load_moods()
    scenes_blob = _between(html, "const SCENES = [", "\n    ];")
    wotd_blob = _between(html, 'id="wotd-data">', "</script>")
    base = strip_phase1(html)
    scenes = parse_scenes(base)
    missing = missing_masters(scenes)
    meta = build_meta(scenes, moods, missing)
    unknown = [s["entry_id"] for s in scenes if s["entry_id"] not in moods]
    if unknown:
        print(f"warning: {len(unknown)} scenes have no mood row; filters will not match them", file=sys.stderr)
    out = apply_a7(insert_phase1(base, meta, missing))
    if _between(out, "const SCENES = [", "\n    ];") != scenes_blob:
        raise SystemExit("publisher changed the SCENES catalogue")
    if _between(out, 'id="wotd-data">', "</script>") != wotd_blob:
        raise SystemExit("publisher changed the word-of-day dataset")
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
        "Day '+doy+' of 365",
    ]
    for needle in identity:
        if needle not in second:
            raise SystemExit(f"regenerated index lost {needle}")
    banned = (
        ">9:16<",
        "Download 9:16",
        "data-src-916",
        "data-format=\"9x16\"",
        "tall916",
        "(preview)</title>",
        "dataset.format",
        "dataset.src45",
    )
    for needle in banned:
        if needle in second:
            raise SystemExit(f"regenerated index still has {needle}")
    ga = set(re.findall(r"G-[A-Z0-9]+", second))
    if ga != {"G-PDJ4WSS725"}:
        raise SystemExit(f"GA4 ids {ga}")
    if "https://devlij.github.io/" in re.search(r'property="og:image"[^>]*>', second).group(0):
        raise SystemExit("og:image is not the canonical host")
    print("prove ok")
    print(f"scenes {len(scenes)}")
    print(f"missing masters in live catalogue {len(missing)}")
    print(f"sample {sample} related {related_ids(meta, sample)}")
    print(f"missing thumb {top} replaced by {filled}")
    print(f"idempotent bytes {len(second)}")


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
