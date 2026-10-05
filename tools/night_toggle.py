#!/usr/bin/env python3
"""Italy gallery Night button (moon), format by format.

Same gate as the Spain and France night toggles, adapted to this catalogue:

  A format is a night master only when the manifest records that exact
  path as the scene's own master and the file is already on disk in this
  repo or in the Italy assets CDN repo.

  * ``daylight_variant.source_night`` names that path, or
  * the manifest lighting label is Night and ``file_16x9`` / ``file_4x5``
    / ``file_9x16`` is that master.

Italy does not use a bare ``time_of_day: Night`` token. The lighting label
is Night when ``time_of_day`` is exactly Night, the composition head is
exactly Night, or that head (the text before ``·``) contains the whole
word "night" ("Floodlit portico and piazza at night", "Night view along
the Grand Canal"). Scenario hour is not used, so dawn, twilight, dusk,
blue hour, and moonlight plates stay without a Night button.

A missing 9:16 stays empty. A 16:9 file, a daylight plate, and a postcard
plate are never copied into a night slot. The card still opens on its
current hero (Postcard, where that button exists). Daylight, Postcard,
and 360 turn Night off, and Night turns those off.

    python3 tools/night_toggle.py
    python3 tools/night_toggle.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PUBLISHER = Path(__file__).resolve().parent / "publish_gallery.py"
MANIFESTS = ROOT / "manifests"
ASSET_CDN = "https://devlij.github.io/jason-ds-vision-italy-assets"
ASSETS_REPO = "devlij/jason-ds-vision-italy-assets"

FORMATS = (("16x9", "file_16x9"), ("4x5", "file_4x5"), ("9x16", "file_9x16"))
NIGHT_WORD = re.compile(r"\bnight\b", re.I)

NIGHT_CONSTS = """      const nightRec = (typeof ITALY_NIGHT !== "undefined") ? ITALY_NIGHT[scene.entry_id] : null;
      const night16 = (nightRec && nightRec[0]) || "";
      const night45 = (nightRec && nightRec[1]) || "";
      const night916 = (nightRec && nightRec[2]) || "";
      const hasNight = !!(night16 || night45 || night916);
"""

IMG_OLD = (
    '${f916 ? ` data-src-916="${f916}"` : ""}'
    '${f916day ? ` data-src-916-day="${f916day}"` : ""}'
)
IMG_NEW = (
    IMG_OLD
    + '${night16 ? ` data-src-16-night="${night16}"` : ""}'
    + '${night45 ? ` data-src-45-night="${night45}"` : ""}'
    + '${night916 ? ` data-src-916-night="${night916}"` : ""}'
)

ROW_COND_OLD = "${(scene.file_16x9_day && masterOk(scene.file_16x9_day)) || motion ?"
ROW_COND_NEW = "${(hasNight || (scene.file_16x9_day && masterOk(scene.file_16x9_day)) || motion) ?"
ROW_BTN_OLD = (
    '|| motion ? `<div class="day-row">'
    '${scene.file_16x9_day && masterOk(scene.file_16x9_day) ? `'
)
ROW_BTN_NEW = (
    '|| motion ? `<div class="day-row">'
    '${hasNight ? `<button type="button" class="night-tab" aria-pressed="false" '
    'title="Show the night image">\\uD83C\\uDF19 Night</button>` : ""}'
    '${(scene.file_16x9_day && masterOk(scene.file_16x9_day)) ? `'
)

DL_OLD_BLOCK = """${f16 ? `<a class="download" data-dl="16x9" href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>` : ""}
            ${f45 ? `<a class="download" data-dl="4x5" href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>` : ""}
            ${f916 ? `<a class="download" data-dl="9x16" href="${f916}" download="${f916.split("/").pop()}">Download 9:16</a>` : ""}"""
DL_NEW_BLOCK = """${f16 ? `<a class="download" data-dl="16x9"${night16 ? ` data-dl-night="${night16}"` : ""} href="${f16}" download="${basename(scene.file_16x9)}">Download 16:9</a>` : ""}
            ${f45 ? `<a class="download" data-dl="4x5"${night45 ? ` data-dl-night="${night45}"` : ""} href="${f45}" download="${basename(scene.file_4x5)}">Download 4:5</a>` : ""}
            ${f916 ? `<a class="download" data-dl="9x16"${night916 ? ` data-dl-night="${night916}"` : ""} href="${f916}" download="${f916.split("/").pop()}">Download 9:16</a>` : ""}"""

CSS_ANCHOR = ".day-tab + .motion-tab{margin-left:0.35rem}\n"
CSS_INSERT = (
    ".night-tab{display:inline-block;background:#243049;color:var(--text);"
    "border-radius:8px;padding:0.4rem 0.7rem;font-size:0.85rem;border:1px solid var(--line);"
    "cursor:pointer;font:inherit}\n"
    ".night-tab:hover{border-color:var(--accent)}\n"
    ".night-tab.is-active{background:#1b2744;border-color:#9eb6e0;color:#e7eefc;font-weight:700}\n"
    ".night-tab + .day-tab,.night-tab + .motion-tab{margin-left:0.35rem}\n"
    ".fmt-tab:disabled,.fmt-tab.is-disabled{opacity:0.4;cursor:default}\n"
)

MOTION_CONST_ANCHOR = (
    '      const motion = (typeof ITALY_MOTION !== "undefined" && '
    'ITALY_MOTION[scene.entry_id]) ? escapeHtml(ITALY_MOTION[scene.entry_id]) : "";\n'
)

HELPERS = r"""    /* ITALY_NIGHT_HELPERS START */
    function clearNight(cardEl) {
      if (!cardEl) return;
      var night = cardEl.querySelector(".night-tab");
      if (night) {
        night.classList.remove("is-active");
        night.setAttribute("aria-pressed", "false");
      }
    }
    function clearPostcard(cardEl) {
      if (!cardEl) return;
      var pc = cardEl.querySelector(".pc-tab");
      if (pc) {
        pc.classList.remove("is-active");
        pc.setAttribute("aria-pressed", "false");
        pc.setAttribute("data-postcard", "off");
      }
    }
    function clearDaylight(cardEl) {
      if (!cardEl) return;
      var sun = cardEl.querySelector(".day-tab:not(.pc-tab)");
      if (!sun) return;
      sun.classList.remove("is-active");
      sun.setAttribute("aria-pressed", "false");
      sun.setAttribute("data-daynight", "night");
    }
    function enable916(cardEl) {
      var t916 = cardEl && cardEl.querySelector('.fmt-tab[data-format="9x16"]');
      if (!t916) return;
      t916.disabled = false;
      t916.classList.remove("is-disabled");
    }
    function nightSrc(img, fmt) {
      if (!img) return "";
      var key = fmt === "4x5" ? "data-src-45-night" : fmt === "9x16" ? "data-src-916-night" : "data-src-16-night";
      return img.getAttribute(key) || "";
    }
    function applyNightDownloads(cardEl, img) {
      cardEl.querySelectorAll("a.download").forEach(function(a) {
        var f = a.getAttribute("data-dl");
        var fmt = f === "4x5" ? "4x5" : f === "9x16" ? "9x16" : "16x9";
        var u = nightSrc(img, fmt);
        if (u) {
          a.hidden = false;
          a.href = u;
          a.setAttribute("download", u.split("/").pop());
        } else {
          a.hidden = true;
        }
      });
    }
    function showRecordedScenario(cardEl) {
      var sc = cardEl.querySelector("p.scenario");
      if (sc && sc.getAttribute("data-scenario")) sc.textContent = sc.getAttribute("data-scenario");
    }
    function syncNight916(cardEl, img) {
      var t916 = cardEl.querySelector('.fmt-tab[data-format="9x16"]');
      if (!t916) return;
      var ok = !!(img && img.getAttribute("data-src-916-night"));
      t916.disabled = !ok;
      t916.classList.toggle("is-disabled", !ok);
      if (!ok && t916.classList.contains("is-active")) {
        var t16 = cardEl.querySelector('.fmt-tab[data-format="16x9"]') || cardEl.querySelector('.fmt-tab[data-format="4x5"]');
        if (!t16) return;
        cardEl.querySelectorAll(".fmt-tab").forEach(function(t) {
          t.classList.toggle("is-active", t === t16);
        });
        var link = cardEl.querySelector("a.thumb");
        var fmt = t16.getAttribute("data-format");
        if (link) {
          link.classList.toggle("tall", fmt === "4x5");
          link.classList.remove("tall916");
        }
      }
    }
    /* ITALY_NIGHT_HELPERS END */

"""

NIGHT_CLICK = r"""      /* ITALY_NIGHT_CLICK START */
      const ntab = e.target.closest(".night-tab");
      if (ntab && gallery.contains(ntab)) {
        e.preventDefault();
        const ncard = ntab.closest(".card");
        if (!ncard) return;
        stopMotion(ncard);
        clearDaylight(ncard);
        clearPostcard(ncard);
        ntab.classList.add("is-active");
        ntab.setAttribute("aria-pressed", "true");
        const nlink = ncard.querySelector("a.thumb");
        const nimg = nlink && nlink.querySelector("img");
        syncNight916(ncard, nimg);
        const nftab = ncard.querySelector(".fmt-tab.is-active");
        const nfmt = nftab ? nftab.getAttribute("data-format") : "16x9";
        const nnext = nightSrc(nimg, nfmt);
        if (nnext && nimg && nlink) { nimg.src = nnext; nlink.href = nnext; }
        applyNightDownloads(ncard, nimg);
        showRecordedScenario(ncard);
        return;
      }
      const ptab = e.target.closest(".pc-tab");
      if (ptab && gallery.contains(ptab) && !ptab.classList.contains("day-tab")) {
        e.preventDefault();
        const pcard = ptab.closest(".card");
        if (!pcard) return;
        stopMotion(pcard);
        clearNight(pcard);
        enable916(pcard);
        return;
      }
      /* ITALY_NIGHT_CLICK END */

"""

_CDN_PATHS: set[str] | None = None


def clean_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.split("?", 1)[0].strip()
    if text.startswith(ASSET_CDN + "/"):
        text = text[len(ASSET_CDN) + 1 :]
    if not text or text.startswith(("/", "\\")) or ".." in text.replace("\\", "/"):
        return ""
    return text


def lighting_is_night(scene: dict) -> bool:
    """Manifest lighting label, not the scenario clock."""
    if str(scene.get("time_of_day") or "").strip() == "Night":
        return True
    head = str(scene.get("composition") or "").split("·", 1)[0].strip()
    if head in {"Night", "NIGHT"}:
        return True
    return bool(NIGHT_WORD.search(head))


def public_asset(rel: str) -> str:
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    return f"{ASSET_CDN}/{rel.lstrip('/')}"


def load_cdn_paths() -> set[str]:
    global _CDN_PATHS
    if _CDN_PATHS is not None:
        return _CDN_PATHS
    raw = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/{ASSETS_REPO}/git/trees/main?recursive=1",
            "--jq",
            "[.tree[].path]",
        ],
        text=True,
    )
    paths = json.loads(raw)
    if not isinstance(paths, list) or not paths:
        raise SystemExit("Italy assets CDN tree was empty")
    _CDN_PATHS = {str(item) for item in paths}
    return _CDN_PATHS


def master_exists(rel: str, cdn: set[str] | None = None) -> bool:
    if not rel:
        return False
    path = (ROOT / rel).resolve()
    root = ROOT.resolve()
    if path != root and root in path.parents and path.is_file():
        return True
    if cdn is not None and rel in cdn:
        return True
    return False


def night_urls(scene: dict, exists) -> list[str]:
    """Return [16:9, 4:5, 9:16] public URLs. Empty string means no night master."""
    variant = scene.get("daylight_variant")
    source = variant.get("source_night") if isinstance(variant, dict) else None
    if not isinstance(source, dict):
        source = {}
    scene_night = lighting_is_night(scene)
    found: list[str] = []
    for fmt, key in FORMATS:
        own = clean_path(scene.get(key))
        info = source.get(fmt)
        recorded = clean_path(info.get("path")) if isinstance(info, dict) else ""
        qualified = ""
        # A foreign source_night path is never shown. Night lighting uses
        # the scene's own master; a matching source_night record does too.
        if own and exists(own) and "daylight" not in Path(own).name:
            if (recorded and recorded == own) or scene_night:
                qualified = own
        found.append(public_asset(qualified) if qualified else "")
    return found


def load_manifests() -> list[dict]:
    scenes = []
    for path in sorted(MANIFESTS.glob("IT-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("entry_id"):
            scenes.append(data)
    return scenes


def load_night_masters(scenes: list[dict] | None = None, cdn: set[str] | None = None) -> dict[str, list[str]]:
    rows = scenes if scenes is not None else load_manifests()
    files = cdn if cdn is not None else load_cdn_paths()

    def exists(rel: str) -> bool:
        return master_exists(rel, files)

    found: dict[str, list[str]] = {}
    for scene in rows:
        urls = night_urls(scene, exists)
        if any(urls):
            found[str(scene["entry_id"])] = urls
    return found


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def _publisher_button() -> str:
    """Night-button snippet as it must be stored in publish_gallery.py source.

    The publisher file keeps a regular Python string, so the JS unicode
    escape is written with a doubled backslash.
    """
    return (
        '|| motion ? `<div class="day-row">'
        '${hasNight ? `<button type="button" class="night-tab" aria-pressed="false" '
        'title="Show the night image">\\\\uD83C\\\\uDF19 Night</button>` : ""}'
        '${(scene.file_16x9_day && masterOk(scene.file_16x9_day)) ? `'
    )


def upgrade_templates(text: str, python_source: bool = False) -> str:
    """Add the Night button markup. Idempotent. Does not touch SCENES."""
    if "const nightRec" not in text:
        text = _replace_once(text, MOTION_CONST_ANCHOR, MOTION_CONST_ANCHOR + NIGHT_CONSTS, "night consts")
    if "data-src-16-night" not in text:
        text = _replace_once(text, IMG_OLD, IMG_NEW, "night image attrs")
    if 'class="night-tab"' not in text:
        button = _publisher_button() if python_source else ROW_BTN_NEW
        text = _replace_once(text, ROW_BTN_OLD, button, "night button")
        text = _replace_once(text, ROW_COND_OLD, ROW_COND_NEW, "night row condition")
    if 'data-dl-night="${night16}"' not in text:
        text = _replace_once(text, DL_OLD_BLOCK, DL_NEW_BLOCK, "night downloads")
    if ".night-tab.is-active" not in text:
        text = _replace_once(text, CSS_ANCHOR, CSS_ANCHOR + CSS_INSERT, "night css")
    return text


def _night_payload(night: dict[str, list[str]]) -> str:
    return json.dumps(night, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def install_night_map(html: str, night: dict[str, list[str]]) -> str:
    payload = _night_payload(night)
    line = f"const ITALY_NIGHT = {payload};\n"
    existing = re.search(r"const ITALY_NIGHT = \{.*?\};\n", html)
    if existing:
        return html[: existing.start()] + line + html[existing.end() :]
    anchor = re.search(r"const ITALY_VALID_916 = \{.*?\};\n", html)
    if not anchor:
        raise SystemExit("ITALY_VALID_916 anchor missing; refusing to publish")
    comment = (
        "/* ITALY_NIGHT: [16:9, 4:5, 9:16] night-master URLs. "
        "Empty slot = that format has no night master. */\n"
    )
    return html[: anchor.end()] + comment + line + html[anchor.end() :]


def install_behavior(html: str) -> str:
    if "ITALY_NIGHT_HELPERS START" not in html:
        anchor = "    /* MOTION360-END */\n\n"
        html = _replace_once(html, anchor, anchor + HELPERS, "night helpers")
    if "ITALY_NIGHT_CLICK START" not in html:
        anchor = '      const dtab = e.target.closest(".day-tab");\n'
        html = _replace_once(html, anchor, NIGHT_CLICK + anchor, "night click")
    motion_old = (
        '        if (cardEl.querySelector("video.motion-clip")) { stopMotion(cardEl); return; }\n'
        '        const link = cardEl.querySelector("a.thumb");\n'
    )
    motion_new = (
        '        if (cardEl.querySelector("video.motion-clip")) { stopMotion(cardEl); return; }\n'
        "        clearNight(cardEl);\n"
        "        clearPostcard(cardEl);\n"
        "        enable916(cardEl);\n"
        '        const link = cardEl.querySelector("a.thumb");\n'
    )
    if "clearNight(cardEl);" not in html:
        html = _replace_once(html, motion_old, motion_new, "360 clears night")
    day_old = (
        '        const isDay = !dtab.classList.contains("is-active");\n'
        '        dtab.classList.toggle("is-active", isDay);\n'
    )
    day_new = (
        '        const isDay = !dtab.classList.contains("is-active");\n'
        "        clearNight(dcard);\n"
        "        if (isDay) clearPostcard(dcard);\n"
        "        enable916(dcard);\n"
        '        dtab.classList.toggle("is-active", isDay);\n'
    )
    if "clearNight(dcard);" not in html:
        html = _replace_once(html, day_old, day_new, "daylight clears night")
    hide_old = "          if (u) a.href = u;\n"
    hide_new = "          if (u) { a.hidden = false; a.href = u; }\n"
    if hide_old in html:
        html = _replace_once(html, hide_old, hide_new, "daylight download unhide")
    fmt_old = (
        '      const tab = e.target.closest(".fmt-tab");\n'
        '      if (!tab || !gallery.contains(tab)) return;\n'
        "      e.preventDefault();\n"
    )
    fmt_new = (
        '      const tab = e.target.closest(".fmt-tab");\n'
        '      if (!tab || !gallery.contains(tab)) return;\n'
        "      e.preventDefault();\n"
        '      if (tab.disabled || tab.classList.contains("is-disabled")) return;\n'
    )
    if 'tab.classList.contains("is-disabled")' not in html:
        html = _replace_once(html, fmt_old, fmt_new, "disabled format tab")
    src_old = """      if (img) {
        const dayOn = cardEl.querySelector(".day-tab.is-active");
      const useDay = dayOn && dayOn.getAttribute("data-daynight") === "day";
      const next = fmt === "4x5"
        ? (useDay && img.getAttribute("data-src-45-day")) || img.getAttribute("data-src-45")
        : fmt === "9x16"
        ? (useDay && img.getAttribute("data-src-916-day")) || img.getAttribute("data-src-916")
        : (useDay && img.getAttribute("data-src-16-day")) || img.getAttribute("data-src-16");
        if (next) { img.src = next; link.href = next; }
      }"""
    src_new = """      if (img) {
        const nightOn = cardEl.querySelector(".night-tab.is-active");
        const dayOn = cardEl.querySelector(".day-tab:not(.pc-tab).is-active");
      const useDay = !nightOn && dayOn && dayOn.getAttribute("data-daynight") === "day";
      const next = nightOn
        ? nightSrc(img, fmt)
        : fmt === "4x5"
        ? (useDay && img.getAttribute("data-src-45-day")) || img.getAttribute("data-src-45")
        : fmt === "9x16"
        ? (useDay && img.getAttribute("data-src-916-day")) || img.getAttribute("data-src-916")
        : (useDay && img.getAttribute("data-src-16-day")) || img.getAttribute("data-src-16");
        if (next) { img.src = next; link.href = next; }
        if (nightOn) applyNightDownloads(cardEl, img);
      }"""
    if 'const nightOn = cardEl.querySelector(".night-tab.is-active")' not in html:
        html = _replace_once(html, src_old, src_new, "format night swap")
    return html


def apply_gallery(html: str, night: dict[str, list[str]] | None = None) -> str:
    """Insert the Night button, night-master map, and click handler. Idempotent."""
    before_cosmo = len(re.findall(r"Cosmo QC", html))
    before_status = html.count('class="status')
    masters = night if night is not None else load_night_masters()
    updated = upgrade_templates(html, python_source=False)
    updated = install_night_map(updated, masters)
    updated = install_behavior(updated)
    if len(re.findall(r"Cosmo QC", updated)) != before_cosmo:
        raise SystemExit("night toggle changed a Cosmo QC claim")
    if updated.count('class="status') != before_status:
        raise SystemExit("night toggle rewrote a status line")
    if "IT-01-368" in updated and "entry_id: \"IT-01-368\"" in updated:
        raise SystemExit("night toggle restored removed scene IT-01-368")
    return updated


def patch_publisher() -> None:
    """Keep a later publish_gallery.py rebuild from dropping the Night button."""
    text = PUBLISHER.read_text(encoding="utf-8")
    updated = upgrade_templates(text, python_source=True)
    hook = "    out = inject_motion(apply_a7(insert_phase1(base, meta, missing, motion, valid916)))\n"
    hooked = (
        hook
        + "    from night_toggle import apply_gallery\n"
        + "    out = apply_gallery(out)\n"
    )
    if "apply_gallery(out)" not in updated:
        updated = _replace_once(updated, hook, hooked, "publisher night hook")
    if updated != text:
        PUBLISHER.write_text(updated, encoding="utf-8")


def _self_test() -> None:
    files = {
        "assets/it-01-004-16x9.png",
        "assets/it-01-004-4x5.png",
        "assets/it-01-004-9x16.png",
        "assets/it-01-001-16x9.png",
        "assets/it-01-001-4x5.png",
        "assets/it-01-366-16x9.png",
        "assets/it-01-366-4x5.png",
        "assets/it-01-024-16x9.png",
        "assets/it-01-024-4x5.png",
    }

    def exists(rel: str) -> bool:
        return rel in files

    pantheon = {
        "entry_id": "IT-01-004",
        "composition": "Floodlit portico and piazza at night · AI-generated artistic interpretation",
        "file_16x9": "assets/it-01-004-16x9.png",
        "file_4x5": "assets/it-01-004-4x5.png",
        "file_9x16_day": "assets/it-01-004-daylight-9x16.png",
    }
    got = night_urls(pantheon, exists)
    if got[2] or not got[0].endswith("/assets/it-01-004-16x9.png") or not got[1].endswith("/assets/it-01-004-4x5.png"):
        raise SystemExit(f"self-test invented a 9:16 night plate: {got}")
    colosseum = {
        "composition": "Ancient amphitheatre exterior · AI-generated artistic interpretation",
        "scenario_label": "23 September 2026 · 14:30 Europe/Rome",
        "file_16x9": "assets/it-01-001-16x9.png",
        "file_4x5": "assets/it-01-001-4x5.png",
    }
    if any(night_urls(colosseum, exists)):
        raise SystemExit("self-test gave a daylight plate a Night button")
    moon = {
        "composition": "Granite cove under moonlight · AI-generated artistic interpretation",
        "scenario_label": "23 September 2026 · 06:03 Europe/Rome",
        "file_16x9": "assets/it-01-024-16x9.png",
        "file_4x5": "assets/it-01-024-4x5.png",
    }
    if any(night_urls(moon, exists)):
        raise SystemExit("self-test used the scenario clock for a moonlight plate")
    other = {
        "time_of_day": "Night",
        "composition": "Night · church",
        "file_16x9": "assets/it-01-366-16x9.png",
        "file_4x5": "assets/it-01-366-4x5.png",
        "daylight_variant": {"source_night": {"16x9": {"path": "assets/it-01-004-16x9.png"}}},
    }
    borrowed = night_urls(other, exists)
    if "it-01-004" in borrowed[0] or not borrowed[0].endswith("/assets/it-01-366-16x9.png"):
        raise SystemExit("self-test used a source_night path that is not the scene master")
    missing = dict(pantheon)
    missing["file_16x9"] = "assets/it-01-004-missing-16x9.png"
    if night_urls(missing, exists)[0]:
        raise SystemExit("self-test accepted a night master that is not on disk")
    escaped = dict(pantheon)
    escaped["file_16x9"] = "../assets/it-01-004-16x9.png"
    if night_urls(escaped, exists)[0]:
        raise SystemExit("self-test accepted a path outside the repository")


def check_gallery(html: str, night: dict[str, list[str]]) -> dict:
    _self_test()
    ids = re.findall(r'entry_id:\s*"(IT-[^"]+)"', html)
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate scene ids")
    if "IT-01-368" in ids:
        raise SystemExit("IT-01-368 must stay removed")
    errors: list[str] = []
    if html.count('class="night-tab"') != 1:
        errors.append(f"night-tab markup count {html.count('class=\"night-tab\"')}")
    if "closest(\".night-tab\")" not in html and "closest('.night-tab')" not in html:
        errors.append("night click handler missing")
    if re.search(r"nightSrc\([^)]*\)\s*\|\|", html) or 'data-src-916-night") ||' in html:
        errors.append("night click handler falls back to another format")
    if 'src="${f16}"' not in html and "src=\"${f16}\"" not in html:
        errors.append("hero image is no longer the current plate")
    if "is-active" in html.split('class="night-tab"', 1)[-1][:80]:
        errors.append("Night button is active in the card template")
    embedded = re.search(r"const ITALY_NIGHT = (\{.*?\});\n", html)
    if not embedded:
        errors.append("ITALY_NIGHT map missing")
    else:
        parsed = json.loads(embedded.group(1))
        if parsed != night:
            errors.append("ITALY_NIGHT does not match the night-master gate")
    portrait = 0
    for entry_id, urls in night.items():
        if len(urls) != 3:
            errors.append(f"{entry_id} night record is not three formats")
            continue
        for url in urls:
            if url and "daylight" in url:
                errors.append(f"{entry_id} night URL is a daylight plate {url}")
            if url and "postcard" in url:
                errors.append(f"{entry_id} night URL is a postcard plate {url}")
        if urls[2]:
            portrait += 1
            if "9x16" not in urls[2] or urls[2] == urls[0]:
                errors.append(f"{entry_id} 9:16 night plate repeats another format")
    if errors:
        raise SystemExit("\n".join(errors[:30]))
    return {
        "cards": len(ids),
        "night_buttons": len(night),
        "without_night": len(ids) - len(night),
        "night_16x9": sum(1 for urls in night.values() if urls[0]),
        "night_4x5": sum(1 for urls in night.values() if urls[1]),
        "night_9x16": portrait,
    }


def rebuild() -> dict:
    _self_test()
    night = load_night_masters()
    original = INDEX.read_text(encoding="utf-8")
    updated = apply_gallery(original, night)
    if apply_gallery(updated, night) != updated:
        raise SystemExit("night toggle rebuild is not idempotent")
    if updated != original:
        INDEX.write_text(updated, encoding="utf-8")
    patch_publisher()
    fresh = apply_gallery(INDEX.read_text(encoding="utf-8"), night)
    if fresh != INDEX.read_text(encoding="utf-8"):
        INDEX.write_text(fresh, encoding="utf-8")
    return check_gallery(INDEX.read_text(encoding="utf-8"), night)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when the built page disagrees with the night-master gate.",
    )
    args = parser.parse_args()
    if args.check:
        census = check_gallery(INDEX.read_text(encoding="utf-8"), load_night_masters())
    else:
        census = rebuild()
    print(
        "cards {cards}, night buttons {night_buttons}, without night {without_night}, "
        "night 16:9 {night_16x9}, night 4:5 {night_4x5}, night 9:16 {night_9x16}".format(
            **census
        )
    )


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
