#!/usr/bin/env python3
"""
Step 1.6 -- Inventory contact sheet.

Reads records/ledger.json + records/pairs_draft.json (and best-effort
records/chatgpt_notes.md) and writes a single self-contained offline HTML
page at records/inventory.html for a human to scroll through and review
the full 430-asset inventory.

Usage:
    python scripts/inventory_sheet.py            # build records/inventory.html
    python scripts/inventory_sheet.py --verify    # verify the generated HTML
"""
from __future__ import annotations

import html
import json
import os
import posixpath
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS_DIR = os.path.join(REPO_ROOT, "records")
LEDGER_PATH = os.path.join(RECORDS_DIR, "ledger.json")
PAIRS_PATH = os.path.join(RECORDS_DIR, "pairs_draft.json")
NOTES_PATH = os.path.join(RECORDS_DIR, "chatgpt_notes.md")
OUTPUT_PATH = os.path.join(RECORDS_DIR, "inventory.html")

STATUS_COLORS = {
    "fantasy": "#7c3aed",   # purple
    "real-dup": "#16a34a",  # green
    "unknown": "#dc2626",   # red
}

NOTE_LINE_RE = re.compile(r"^\s*(\d{3})\s*-\s*convo([AB])\s*-\s*(.+?)\s*$")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_notes(path):
    """Best-effort parse of records/chatgpt_notes.md.

    Returns dict {(convo_letter, 'NNN'): note_text}. Any line that does not
    match the expected 'NNN - convoX - ...' shape is silently skipped, and
    if the file is missing/unreadable entirely, an empty dict is returned.
    """
    notes = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = NOTE_LINE_RE.match(line)
                if not m:
                    continue
                idx, convo, rest = m.group(1), m.group(2), m.group(3)
                notes[(convo, idx)] = rest
    except Exception:
        return {}
    return notes


def note_key_for_id(asset_id: str):
    """Extract (convo_letter, 'NNN') from a chatgpt ledger id, or None."""
    parts = asset_id.split("/")
    convo = None
    for p in parts:
        if p.startswith("convo") and len(p) == len("convoA"):
            convo = p[-1]
            break
    if convo not in ("A", "B"):
        return None
    basename = os.path.basename(asset_id)
    idx = basename.split("_", 1)[0]
    if len(idx) == 3 and idx.isdigit():
        return (convo, idx)
    return None


def rel_img_path(asset_id: str) -> str:
    """Relative path from records/ to an asset, given a repo-root-relative id."""
    return "../" + asset_id


def img_tag(asset_id: str, extra_class: str = "") -> str:
    src = html.escape(rel_img_path(asset_id), quote=True)
    alt = html.escape(os.path.basename(asset_id), quote=True)
    cls = ("thumb " + extra_class).strip()
    return f'<img class="{html.escape(cls, quote=True)}" src="{src}" alt="{alt}" loading="lazy">'


def esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def build_html() -> str:
    ledger = load_json(LEDGER_PATH)
    pairs = load_json(PAIRS_PATH)
    notes = load_notes(NOTES_PATH)

    ledger_by_id = {item["id"]: item for item in ledger}
    pairs_by_id = {p["id"]: p for p in pairs}

    chatgpt_items = sorted(
        (item for item in ledger if item["source"] in ("chatgptA", "chatgptB")),
        key=lambda x: x["id"],
    )
    real_items = sorted(
        (item for item in ledger if item["source"] == "gphotos"),
        key=lambda x: x["id"],
    )
    v1_items = sorted(
        (item for item in ledger if item["source"] == "v1"),
        key=lambda x: x["id"],
    )

    status_counts = defaultdict(int)
    for p in pairs:
        status_counts[p.get("status", "unknown")] += 1

    # ---------- Section 1: ChatGPT images ----------
    chatgpt_rows = []
    for item in chatgpt_items:
        asset_id = item["id"]
        pair = pairs_by_id.get(asset_id)
        status = pair.get("status") if pair else "unknown"
        distance = pair.get("distance") if pair else None
        anchor_id = pair.get("anchor_id") if pair else None
        duplicate_of = pair.get("duplicate_of") if pair else None
        color = STATUS_COLORS.get(status, "#dc2626")

        note_key = note_key_for_id(asset_id)
        note_text = notes.get(note_key) if note_key else None

        anchor_html = ""
        if status in ("fantasy", "real-dup") and anchor_id and anchor_id in ledger_by_id:
            anchor_html = f'''
          <div class="pair-anchor">
            <div class="pair-arrow">&harr;</div>
            {img_tag(anchor_id)}
            <div class="cap">anchor: {esc(os.path.basename(anchor_id))}</div>
          </div>'''

        dup_html = ""
        if duplicate_of:
            dup_html = f'<div class="dup-note">duplicate_of: {esc(os.path.basename(duplicate_of))}</div>'

        note_html = ""
        if note_text:
            note_html = f'<div class="note">{esc(note_text)}</div>'

        dist_html = f'<div class="dist">distance: {esc(distance)}</div>' if distance is not None else ""

        chatgpt_rows.append(f'''
      <div class="item chatgpt-item">
        <div class="pair-main">
          {img_tag(asset_id)}
          <div class="cap">{esc(os.path.basename(asset_id))}</div>
          <span class="badge" style="background:{color}">{esc(status)}</span>
          {dist_html}
          {dup_html}
          {note_html}
        </div>{anchor_html}
      </div>''')

    chatgpt_section = f'''
    <section id="sec-chatgpt">
      <h2>ChatGPT images ({len(chatgpt_items)})</h2>
      <div class="grid">{''.join(chatgpt_rows)}
      </div>
    </section>'''

    # ---------- Section 2: Real pool grouped by capture hour ----------
    hour_groups = defaultdict(list)
    no_ts_group = []
    for item in real_items:
        exif_time = item.get("exif_time")
        if exif_time:
            hour_key = exif_time[:13]  # 'YYYY-MM-DDTHH'
            hour_groups[hour_key].append(item)
        else:
            no_ts_group.append(item)

    real_group_blocks = []
    for hour_key in sorted(hour_groups.keys()):
        items = hour_groups[hour_key]
        label = hour_key.replace("T", " ") + ":00"
        thumbs = "".join(
            f'''
          <div class="item real-item">
            {img_tag(it["id"])}
            <div class="cap">{esc(os.path.basename(it["id"]))}</div>
            <div class="sub">{esc(it.get("exif_time") or "")}</div>
          </div>'''
            for it in items
        )
        real_group_blocks.append(f'''
      <div class="hour-group">
        <h3>{esc(label)} ({len(items)})</h3>
        <div class="grid">{thumbs}
        </div>
      </div>''')

    if no_ts_group:
        thumbs = "".join(
            f'''
          <div class="item real-item">
            {img_tag(it["id"])}
            <div class="cap">{esc(os.path.basename(it["id"]))}</div>
          </div>'''
            for it in no_ts_group
        )
        real_group_blocks.append(f'''
      <div class="hour-group">
        <h3>no timestamp ({len(no_ts_group)})</h3>
        <div class="grid">{thumbs}
        </div>
      </div>''')

    real_section = f'''
    <section id="sec-real">
      <h2>Real pool -- Google Photos ({len(real_items)})</h2>
      {''.join(real_group_blocks)}
    </section>'''

    # ---------- Section 3: GPT v1 pages ----------
    v1_rows = "".join(
        f'''
      <div class="item v1-item">
        {img_tag(it["id"])}
        <div class="cap">{esc(os.path.basename(it["id"]))}</div>
      </div>'''
        for it in v1_items
    )
    v1_section = f'''
    <section id="sec-v1">
      <h2>GPT v1 pages ({len(v1_items)})</h2>
      <div class="grid">{v1_rows}
      </div>
    </section>'''

    # ---------- Nav ----------
    nav = f'''
    <nav class="mininav">
      <a href="#sec-chatgpt">ChatGPT images ({len(chatgpt_items)})</a>
      <a href="#sec-real">Real pool ({len(real_items)})</a>
      <a href="#sec-v1">GPT v1 pages ({len(v1_items)})</a>
      <span class="nav-sep">|</span>
      <span class="badge" style="background:{STATUS_COLORS['fantasy']}">fantasy: {status_counts.get('fantasy', 0)}</span>
      <span class="badge" style="background:{STATUS_COLORS['real-dup']}">real-dup: {status_counts.get('real-dup', 0)}</span>
      <span class="badge" style="background:{STATUS_COLORS['unknown']}">unknown: {status_counts.get('unknown', 0)}</span>
    </nav>'''

    css = '''
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, Segoe UI, Arial, sans-serif;
      margin: 0;
      background: #111318;
      color: #e6e6e6;
    }
    .mininav {
      position: sticky;
      top: 0;
      z-index: 10;
      background: #1b1e26;
      border-bottom: 1px solid #333;
      padding: 10px 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
      font-size: 14px;
    }
    .mininav a {
      color: #9ecbff;
      text-decoration: none;
      font-weight: 600;
    }
    .mininav a:hover { text-decoration: underline; }
    .nav-sep { color: #555; }
    main { padding: 16px; max-width: 1400px; margin: 0 auto; }
    section { margin-bottom: 40px; }
    h2 {
      border-bottom: 2px solid #333;
      padding-bottom: 6px;
    }
    h3 { margin-top: 24px; color: #ccc; }
    .grid {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }
    .item {
      background: #1b1e26;
      border: 1px solid #2a2d36;
      border-radius: 6px;
      padding: 8px;
      width: 200px;
    }
    .chatgpt-item {
      display: flex;
      flex-direction: row;
      gap: 8px;
      width: auto;
      align-items: flex-start;
    }
    .pair-main, .pair-anchor {
      width: 200px;
    }
    .pair-anchor {
      display: flex;
      flex-direction: column;
      align-items: center;
      border-left: 1px dashed #444;
      padding-left: 8px;
    }
    .pair-arrow {
      color: #888;
      font-size: 12px;
      margin-bottom: 4px;
    }
    img.thumb {
      max-width: 100%;
      max-height: 180px;
      display: block;
      margin: 0 auto;
      border-radius: 4px;
      background: #000;
    }
    .cap {
      font-size: 11px;
      color: #ccc;
      word-break: break-all;
      margin-top: 4px;
      text-align: center;
    }
    .sub {
      font-size: 10px;
      color: #888;
      text-align: center;
    }
    .badge {
      display: inline-block;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 10px;
      margin-top: 4px;
    }
    .dist { font-size: 11px; color: #aaa; margin-top: 2px; }
    .dup-note { font-size: 11px; color: #f0ad4e; margin-top: 2px; }
    .note {
      font-size: 11px;
      color: #bbb;
      margin-top: 4px;
      font-style: italic;
    }
    .hour-group { margin-bottom: 24px; }
    '''

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{PROJECT}} album -- inventory contact sheet</title>
<style>{css}</style>
</head>
<body>
{nav}
<main>
  <h1>Inventory contact sheet</h1>
  <p>430 assets total -- {len(chatgpt_items)} ChatGPT images, {len(real_items)} real Google Photos, {len(v1_items)} GPT v1 pages.</p>
  {chatgpt_section}
  {real_section}
  {v1_section}
</main>
</body>
</html>
'''


def build():
    out = build_html()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {OUTPUT_PATH} ({len(out)} bytes)")


IMG_SRC_RE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.IGNORECASE)


def verify() -> int:
    if not os.path.isfile(OUTPUT_PATH):
        print(f"SHEET VERIFY FAIL: missing {OUTPUT_PATH}")
        return 1

    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    ledger = load_json(LEDGER_PATH)
    ledger_ids = {item["id"] for item in ledger}

    srcs = IMG_SRC_RE.findall(text)
    if not srcs:
        print("SHEET VERIFY FAIL: no <img src=...> tags found")
        return 1

    missing_files = []
    referenced_ids = set()
    for src in srcs:
        # Resolve relative to records/, mirroring how a browser would.
        abs_path = os.path.normpath(os.path.join(RECORDS_DIR, src))
        if not os.path.isfile(abs_path):
            missing_files.append(src)
        # Compute repo-root-relative id form ("assets/...") for comparison.
        asset_id = posixpath.normpath(posixpath.join("records", src.replace("\\", "/")))
        referenced_ids.add(asset_id)

    if missing_files:
        print(f"SHEET VERIFY FAIL: {len(missing_files)} referenced path(s) do not resolve to existing files")
        for m in missing_files[:10]:
            print(f"  missing: {m}")
        return 1

    if referenced_ids != ledger_ids:
        extra = referenced_ids - ledger_ids
        missing = ledger_ids - referenced_ids
        print("SHEET VERIFY FAIL: referenced image id set != ledger id set")
        if missing:
            print(f"  {len(missing)} ledger id(s) never referenced, e.g. {sorted(missing)[:5]}")
        if extra:
            print(f"  {len(extra)} referenced id(s) not in ledger, e.g. {sorted(extra)[:5]}")
        return 1

    print(f"SHEET VERIFY OK: {len(referenced_ids)} unique images")
    return 0


def main():
    if "--verify" in sys.argv:
        sys.exit(verify())
    build()
    sys.exit(0)


if __name__ == "__main__":
    main()
