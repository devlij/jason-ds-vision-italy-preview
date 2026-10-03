#!/usr/bin/env python3
"""Build image-sitemap.xml from the live Italy gallery.

Regenerate (do not hand-edit the sitemap):

  python3 tools/image_sitemap.py
  python3 tools/image_sitemap.py --check

Source
------
Card copy, city, country, master paths, and the copy-link anchor come
from the SCENES catalogue in index.html. The page anchor is the entry
id already used by Copy link (`#IT-01-###` on the gallery canonical URL).

Approval — re-read on every run
--------------------------------
A scene is written only when its live status is exactly "Approved".
Candidate, unapproved, blank, or any other value is left out.

Status resolution, first match wins:

1. `approval_status` on the SCENES object, when that field is present.
2. Else `approval_status` in manifests/<ENTRY>.json, when a manifest exists.
3. Else Approved, because index.html publishes approved scenes only
   ("Approved scenes only — add each newly approved scene here immediately").

If a manifest (or a future catalogue field) is flipped from Approved to
Candidate, the next regen drops that scene. Nothing in this sitemap is
a hand-maintained scene list.

Italy masters
-------------
16:9 and 4:5 only. 9:16 is a standing exclusion: file_9x16 is never
emitted, even if a path is added later. Daylight derivatives
(`*-daylight-*`) are not masters and are not listed. A format is listed
only when the master file exists on disk.

Canonical host
--------------
Taken from the existing robots.txt Sitemap line, and checked against
CNAME and <link rel="canonical">. Page URLs stay on that host. Image
URLs are absolute on the assets CDN
(https://devlij.github.io/jason-ds-vision-italy-assets/assets/...).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
# Keep in step with tools/publish_gallery.py ASSET_CDN.
ASSET_CDN = "https://devlij.github.io/jason-ds-vision-italy-assets"
_ASSET_PREFIXES = (
    ASSET_CDN + "/",
    "https://italy.jdvision.org/",
    "http://italy.jdvision.org/",
)
ROBOTS = ROOT / "robots.txt"
CNAME = ROOT / "CNAME"
MANIFESTS = ROOT / "manifests"
SITEMAP = ROOT / "image-sitemap.xml"

# Standing order: Italy has no 9:16 master. Do not add it here.
MASTER_FORMATS = ("16x9", "4x5")
APPROVED = "Approved"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"


def js_string(raw: str) -> str:
    return json.loads('"' + raw + '"')


def bare(path: str) -> str:
    return path.split("?", 1)[0]


def local_asset(path: str) -> str:
    """On-disk assets/ path for a relative or absolute asset URL."""
    if not path:
        return ""
    bare_path = path.split("?", 1)[0]
    for prefix in _ASSET_PREFIXES:
        if bare_path.startswith(prefix):
            bare_path = bare_path[len(prefix):]
            break
    while bare_path.startswith("../"):
        bare_path = bare_path[3:]
    if bare_path.startswith("./"):
        bare_path = bare_path[2:]
    return bare_path.lstrip("/")


def public_asset(path: str) -> str:
    """Absolute CDN URL. Paths outside assets/ are returned unchanged."""
    if not path:
        return ""
    query = ""
    raw = path
    if "?" in raw:
        raw, query = raw.split("?", 1)
        query = "?" + query
    rel = local_asset(raw)
    if not rel.startswith("assets/"):
        return path
    return f"{ASSET_CDN}/{rel}{query}"


def parse_scenes(html: str) -> list[dict]:
    start = html.find("const SCENES")
    if start < 0:
        raise SystemExit("index.html has no SCENES catalogue")
    end = html.find("\n    ];", start)
    if end < 0:
        raise SystemExit("SCENES catalogue is not closed")
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
                "country": field("country"),
                "city": field("city"),
                "caption": field("caption"),
                "description": field("description"),
                "file_16x9": field("file_16x9"),
                "file_4x5": field("file_4x5"),
                "file_9x16": field("file_9x16", False),
                "approval_status": field("approval_status", False),
            }
        )
    if len(scenes) != len({s["entry_id"] for s in scenes}):
        raise SystemExit("duplicate entry ids in SCENES")
    return scenes


def load_manifest_status() -> dict[str, str | None]:
    status: dict[str, str | None] = {}
    if not MANIFESTS.is_dir():
        return status
    for path in sorted(MANIFESTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        eid = str(data.get("entry_id") or path.stem)
        # Key absent vs explicit null both count as an explicit manifest
        # record: only the exact string Approved is eligible.
        if "approval_status" not in data:
            status[eid] = None
        else:
            value = data.get("approval_status")
            status[eid] = value if isinstance(value, str) else None
    return status


def live_approval(scene: dict, manifests: dict[str, str | None]) -> str | None:
    """Return "Approved", or the explicit non-approved status, or None.

    None means "no explicit status" (catalogue contract: approved-only).
    A returned string other than Approved excludes the scene.
    """
    explicit: list[str | None] = []
    if scene.get("approval_status"):
        explicit.append(scene["approval_status"])
    eid = scene["entry_id"]
    if eid in manifests:
        explicit.append(manifests[eid])
    if not explicit:
        return None
    if all(value == APPROVED for value in explicit):
        return APPROVED
    for value in explicit:
        if value != APPROVED:
            return value if value else ""
    return ""


def is_included(status: str | None) -> bool:
    """Include only live Approved scenes.

    No explicit status (None) follows the approved-only SCENES catalogue.
    Candidate and every other explicit value drop out on the next regen.
    """
    if status is None:
        return True
    return status == APPROVED


def discover_canonical() -> tuple[str, str]:
    """Return (origin, canonical page URL) from robots.txt, CNAME, and index."""
    cname = CNAME.read_text(encoding="utf-8").strip()
    robots = ROBOTS.read_text(encoding="utf-8")
    sitemaps = re.findall(r"^Sitemap:\s*(\S+)\s*$", robots, re.M)
    page_maps = [
        url for url in sitemaps if not url.rstrip("/").endswith("/image-sitemap.xml")
    ]
    if len(page_maps) != 1:
        raise SystemExit(f"robots.txt must keep exactly one page sitemap, found {sitemaps}")
    page_map = page_maps[0]
    if not page_map.startswith("https://"):
        raise SystemExit(f"page sitemap is not https: {page_map}")
    host = page_map[len("https://") :].split("/", 1)[0]
    if host != cname:
        raise SystemExit(f"CNAME {cname!r} does not match sitemap host {host!r}")
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    if not match:
        raise SystemExit("index.html has no canonical link")
    canonical = match.group(1).split("#", 1)[0]
    canon_host = canonical.split("://", 1)[-1].split("/", 1)[0]
    if canon_host != host:
        raise SystemExit(f"canonical host {canon_host!r} does not match {host!r}")
    if not canonical.startswith("https://"):
        raise SystemExit(f"canonical URL is not https: {canonical}")
    return "https://" + host, canonical


def master_path(scene: dict, fmt: str) -> str:
    if fmt == "9x16":
        raise SystemExit("9:16 is excluded for Italy")
    key = "file_16x9" if fmt == "16x9" else "file_4x5"
    return scene.get(key) or ""


def xml_text(value: str) -> str:
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value):
        raise SystemExit("refusing a control character in sitemap text")
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def page_loc(canonical: str, entry_id: str) -> str:
    """Canonical gallery URL plus the copy-link fragment."""
    base = canonical if canonical.endswith("/") else canonical + "/"
    return f"{base}#{entry_id}"


def image_loc(path: str) -> str:
    return public_asset(path)


def build_entries(scenes: list[dict], manifests: dict[str, str | None], origin: str, canonical: str) -> tuple[list[dict], list[str]]:
    # Page locs use `canonical`. Image locs use the assets CDN, not `origin`.
    del origin
    entries = []
    problems: list[str] = []
    for scene in scenes:
        eid = scene["entry_id"]
        status = live_approval(scene, manifests)
        if not is_included(status):
            shown = status if status else "(blank)"
            problems.append(f"{eid} excluded: approval status {shown!r} is not Approved")
            continue
        if scene.get("file_9x16"):
            problems.append(f"{eid} ignored file_9x16 (Italy standing order: no 9:16)")
        images = []
        for fmt in MASTER_FORMATS:
            path = master_path(scene, fmt)
            if not path:
                problems.append(f"{eid} missing {fmt} path")
                continue
            rel = local_asset(path)
            if "9x16" in rel or "daylight" in rel:
                problems.append(f"{eid} refused non-master path {path}")
                continue
            if not (ROOT / rel).is_file():
                problems.append(f"{eid} {fmt} file not on disk: {rel}")
                continue
            images.append(
                {
                    "format": fmt,
                    "loc": image_loc(path),
                    "caption": scene["description"],
                    "title": scene["caption"],
                    "geo": f"{scene['city']}, {scene['country']}",
                }
            )
        if not images:
            problems.append(f"{eid} excluded: no existing 16:9 or 4:5 master")
            continue
        if not scene["description"].strip() or not scene["caption"].strip():
            problems.append(f"{eid} missing description or caption")
            continue
        entries.append(
            {
                "entry_id": eid,
                "loc": page_loc(canonical, eid),
                "images": images,
            }
        )
    return entries, problems


def render_xml(entries: list[dict]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for entry in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_text(entry['loc'])}</loc>")
        for image in entry["images"]:
            lines.append("    <image:image>")
            lines.append(f"      <image:loc>{xml_text(image['loc'])}</image:loc>")
            lines.append(f"      <image:caption>{xml_text(image['caption'])}</image:caption>")
            lines.append(f"      <image:title>{xml_text(image['title'])}</image:title>")
            lines.append(f"      <image:geo_location>{xml_text(image['geo'])}</image:geo_location>")
            lines.append("    </image:image>")
        lines.append("  </url>")
    lines.append("</urlset>")
    lines.append("")
    return "\n".join(lines)


def write_robots(origin: str) -> None:
    line = f"Sitemap: {origin}/image-sitemap.xml"
    text = ROBOTS.read_text(encoding="utf-8")
    if not re.search(r"^Sitemap:\s+\S*sitemap\.xml\s*$", text, re.M):
        raise SystemExit("robots.txt is missing the existing page sitemap line")
    if line in text.splitlines():
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
    ROBOTS.write_text(text, encoding="utf-8")


def local_counts(entries: list[dict]) -> dict[str, int]:
    counts = {fmt: 0 for fmt in MASTER_FORMATS}
    for entry in entries:
        for image in entry["images"]:
            counts[image["format"]] += 1
    return counts


def validate_xml(path: Path, origin: str, canonical: str) -> dict[str, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != f"{{{NS}}}urlset":
        raise SystemExit(f"unexpected root {root.tag}")
    urls = list(root.findall(f"{{{NS}}}url"))
    counts = {fmt: 0 for fmt in MASTER_FORMATS}
    image_locs = []
    for url in urls:
        loc = url.find(f"{{{NS}}}loc")
        if loc is None or not (loc.text or "").startswith(canonical.split("#", 1)[0]):
            raise SystemExit(f"page loc is not on the gallery canonical URL: {loc.text if loc is not None else None}")
        images = list(url.findall(f"{{{IMAGE_NS}}}image"))
        if not images:
            raise SystemExit(f"url without images: {loc.text}")
        for image in images:
            iloc = image.find(f"{{{IMAGE_NS}}}loc")
            caption = image.find(f"{{{IMAGE_NS}}}caption")
            title = image.find(f"{{{IMAGE_NS}}}title")
            geo = image.find(f"{{{IMAGE_NS}}}geo_location")
            if iloc is None or not (iloc.text or "").startswith(ASSET_CDN + "/assets/"):
                raise SystemExit(f"image loc is not an absolute CDN master URL: {iloc.text if iloc is not None else None}")
            text = iloc.text or ""
            if "9x16" in text or "daylight" in text:
                raise SystemExit(f"non-master image loc: {text}")
            if text.endswith("-16x9.png") or "-16x9.png?" in text:
                counts["16x9"] += 1
            elif text.endswith("-4x5.png") or "-4x5.png?" in text:
                counts["4x5"] += 1
            else:
                raise SystemExit(f"image loc is not 16:9 or 4:5: {text}")
            for node, label in ((caption, "caption"), (title, "title"), (geo, "geo_location")):
                if node is None or not (node.text or "").strip():
                    raise SystemExit(f"missing image:{label} for {text}")
            image_locs.append(text)
    if len(image_locs) != len(set(image_locs)):
        raise SystemExit("duplicate image:loc values")
    return counts


def head_status(url: str) -> tuple[str, int | str]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return url, response.status
    except urllib.error.HTTPError as exc:
        return url, exc.code
    except Exception as exc:  # noqa: BLE001 — report the failure, do not invent a code
        return url, f"{type(exc).__name__}: {exc}"


def check_urls(path: Path) -> list[str]:
    tree = ET.parse(path)
    root = tree.getroot()
    locs = []
    for image in root.findall(f".//{{{IMAGE_NS}}}loc"):
        if image.text:
            locs.append(image.text)
    failures = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(head_status, url) for url in locs]
        for future in as_completed(futures):
            url, status = future.result()
            if status != 200:
                failures.append(f"{status} {url}")
    failures.sort()
    return failures


def self_test() -> None:
    """Candidate and any non-Approved explicit status must drop out."""
    if is_included(None) is not True:
        raise SystemExit("approved-only catalogue scenes must be included")
    for blocked in ("Candidate", "candidate", "Unapproved", "Pending", "", "Rejected"):
        if is_included(blocked):
            raise SystemExit(f"{blocked!r} must be excluded")
    if not is_included(APPROVED):
        raise SystemExit("Approved must be included")
    sample = {"entry_id": "IT-01-000", "approval_status": ""}
    if live_approval(sample, {"IT-01-000": "Candidate"}) != "Candidate":
        raise SystemExit("manifest Candidate must override the catalogue")
    if live_approval({"entry_id": "IT-01-000", "approval_status": "Candidate"}, {}) != "Candidate":
        raise SystemExit("catalogue Candidate must be excluded")
    if live_approval({"entry_id": "IT-01-000", "approval_status": ""}, {"IT-01-000": "Approved"}) != APPROVED:
        raise SystemExit("manifest Approved must include a scene with no catalogue status")
    if live_approval({"entry_id": "IT-01-000", "approval_status": ""}, {}) is not None:
        raise SystemExit("missing manifest must use the approved-only catalogue rule")


def generate() -> tuple[list[dict], list[str], dict[str, int]]:
    self_test()
    origin, canonical = discover_canonical()
    html = INDEX.read_text(encoding="utf-8")
    scenes = parse_scenes(html)
    manifests = load_manifest_status()
    entries, problems = build_entries(scenes, manifests, origin, canonical)
    xml = render_xml(entries)
    SITEMAP.write_text(xml, encoding="utf-8")
    write_robots(origin)
    counts = validate_xml(SITEMAP, origin, canonical)
    expected = local_counts(entries)
    if counts != expected:
        raise SystemExit(f"written sitemap counts {counts} != built {expected}")
    return entries, problems, counts


def main() -> None:
    entries, problems, counts = generate()
    print(f"approved scenes in sitemap: {len(entries)}")
    print(f"16:9 images: {counts['16x9']}")
    print(f"4:5 images: {counts['4x5']}")
    print(f"wrote {SITEMAP}")
    if problems:
        print(f"problems: {len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("problems: none")
    if "--check" in sys.argv:
        failures = check_urls(SITEMAP)
        if failures:
            print(f"HEAD failures: {len(failures)}")
            for failure in failures:
                print(f"  - {failure}")
            raise SystemExit(1)
        image_count = counts["16x9"] + counts["4x5"]
        print(f"HEAD 200 for {image_count} image:loc URLs")


if __name__ == "__main__":
    main()
