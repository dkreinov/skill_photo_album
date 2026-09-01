#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D-065 -- cut generated "decoration kit" sheets into individual assets.

Input: assets/generated/decor_sheets/decor_<set>_<n>.png -- grids of separate hand-drawn
objects on a plain white background (from ChatGPT), one grid per "set" (landmarks, trip,
connectors, furniture, patterns).

Two cutting strategies:
  * grid sets (landmarks, trip, connectors, furniture): threshold the white background, find
    connected components, despeckle, and export each component as its own RGBA PNG with a
    transparent background and a small margin. This is deterministic, local, and touches no
    pixel of the source art beyond alpha authoring (same spirit as make_sticker.py).
  * patterns set: the sheet is 4 seamless tile swatches with NO reliable white gutter between
    them (confirmed after 2 generation attempts), so connected-component matting would merge
    them into one blob. Instead it is cut with a fixed 2x2 grid crop and kept as OPAQUE tiles
    (they're meant to be used as background fill, not cut-out stickers).

Usage:
    python scripts/cut_decor_sheets.py --run
    python scripts/cut_decor_sheets.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SHEETS_DIR = ROOT / "assets" / "generated" / "decor_sheets"
OUT_DIR = ROOT / "assets" / "generated" / "decor"
RECORDS = ROOT / "records"
MANIFEST = RECORDS / "decor_manifest.json"
PREVIEW = RECORDS / "decor_preview.png"
PREVIEW2 = RECORDS / "decor_preview2.png"

WHITE_THRESH = 246          # pixel value (all channels) at/above this counts as "background"
MARGIN_PX = 10              # transparent margin kept around each cut item
MIN_AREA_FRAC = 0.005       # components under 0.5% of sheet area are specks -> dropped
FEATHER_PX = 1.0            # soft the alpha edge a touch so cut lines don't look jagged
COVER_MIN, COVER_MAX = 2.0, 90.0

SHEETS = [
    ("landmarks", SHEETS_DIR / "decor_landmarks_01.png", "cellgrid"),
    ("trip", SHEETS_DIR / "decor_trip_01.png", "cellgrid"),
    ("connectors", SHEETS_DIR / "decor_connectors_01.png", "cellgrid"),
    # furniture items (washi-tape strips especially) don't leave a full-width/height white
    # band between every row, so cellgrid under-segments them into one blob -- connected
    # components (with despeckling) separates them correctly instead.
    ("furniture", SHEETS_DIR / "decor_furniture_01.png", "components"),
    ("patterns", SHEETS_DIR / "decor_patterns_01.png", "quad"),
]


# --------------------------------------------------------------------------- grid cutting
def _bg_mask(rgb: np.ndarray) -> np.ndarray:
    """True where a pixel is (near-)white background."""
    return np.all(rgb >= WHITE_THRESH, axis=-1)


def _feather(alpha: np.ndarray, px: float) -> np.ndarray:
    if px <= 0:
        return alpha
    from scipy.ndimage import gaussian_filter
    return np.clip(gaussian_filter(alpha.astype(np.float32), sigma=px), 0, 255).astype(np.uint8)


def _segments_from_profile(profile: np.ndarray, min_run: int) -> list[tuple[int, int]]:
    """Contiguous non-zero runs in a 1D profile, each at least min_run long."""
    active = profile > 0
    segs, start = [], None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        if not a and start is not None:
            if i - start >= min_run:
                segs.append((start, i))
            start = None
    if start is not None and len(active) - start >= min_run:
        segs.append((start, len(active)))
    return segs


def _detect_cells(fg: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Grid-cell segmentation via row/column projection profiles.

    Sheets were requested as grids of separate items with "generous spacing" -- a full-width
    or full-height run of background pixels reliably separates rows and columns even when an
    item itself (e.g. a dashed line, a sparse dotted path) is internally disconnected and
    would otherwise be split or dropped by connected-component area filtering.
    """
    h, w = fg.shape
    row_profile = fg.sum(axis=1)
    row_bands = _segments_from_profile(row_profile, min_run=max(4, h // 200))
    cells = []
    for (y0, y1) in row_bands:
        band = fg[y0:y1]
        col_profile = band.sum(axis=0)
        col_bands = _segments_from_profile(col_profile, min_run=max(4, w // 200))
        for (x0, x1) in col_bands:
            cells.append((x0, y0, x1, y1))
    return cells


def cut_components_sheet(path: Path) -> list[dict]:
    """Connected-component matting -- for sheets whose items aren't cleanly grid-separated."""
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    fg = ~_bg_mask(arr)
    sheet_area = h * w

    fg_closed = ndimage.binary_closing(fg, structure=np.ones((3, 3)), iterations=2)
    labels, n = ndimage.label(fg_closed, structure=np.ones((3, 3)))
    min_area = MIN_AREA_FRAC * sheet_area

    items = []
    for lbl in range(1, n + 1):
        ys, xs = np.where(labels == lbl)
        area = len(ys)
        if area < min_area:
            continue
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        y0m, x0m = max(0, y0 - MARGIN_PX), max(0, x0 - MARGIN_PX)
        y1m, x1m = min(h, y1 + 1 + MARGIN_PX), min(w, x1 + 1 + MARGIN_PX)

        crop_rgb = arr[y0m:y1m, x0m:x1m]
        crop_fg = (labels[y0m:y1m, x0m:x1m] == lbl)
        crop_bg = _bg_mask(crop_rgb)
        alpha = np.where(crop_bg, 0, 255).astype(np.uint8)
        alpha = np.maximum(alpha * crop_fg.astype(np.uint8), 0)
        alpha = _feather(alpha, FEATHER_PX)

        rgba = np.dstack([crop_rgb, alpha])
        items.append({"bbox": (int(x0m), int(y0m), int(x1m), int(y1m)),
                      "image": Image.fromarray(rgba, "RGBA"),
                      "area_frac": area / sheet_area})

    items.sort(key=lambda it: (it["bbox"][1], it["bbox"][0]))
    return items


def cut_cellgrid_sheet(path: Path) -> list[dict]:
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    fg = ~_bg_mask(arr)
    sheet_area = h * w

    cells = _detect_cells(fg)
    items = []
    for (x0, y0, x1, y1) in cells:
        area = int(fg[y0:y1, x0:x1].sum())
        if area < 0.0005 * sheet_area:   # true empty/speck cell
            continue
        y0m, x0m = max(0, y0 - MARGIN_PX), max(0, x0 - MARGIN_PX)
        y1m, x1m = min(h, y1 + MARGIN_PX), min(w, x1 + MARGIN_PX)

        crop_rgb = arr[y0m:y1m, x0m:x1m]
        crop_bg = _bg_mask(crop_rgb)
        alpha = np.where(crop_bg, 0, 255).astype(np.uint8)
        alpha = _feather(alpha, FEATHER_PX)

        rgba = np.dstack([crop_rgb, alpha])
        items.append({"bbox": (int(x0m), int(y0m), int(x1m), int(y1m)),
                      "image": Image.fromarray(rgba, "RGBA"),
                      "area_frac": area / sheet_area})

    items.sort(key=lambda it: (it["bbox"][1], it["bbox"][0]))
    return items


def cut_quad_sheet(path: Path) -> list[dict]:
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    hh, hw = h // 2, w // 2
    quads = [(0, 0, hw, hh), (hw, 0, w, hh), (0, hh, hw, hh + hh if hh + hh <= h else h),
             (hw, hh, w, hh + hh if hh + hh <= h else h)]
    out = []
    for (x0, y0, x1, y1) in quads:
        crop = arr[y0:y1, x0:x1]
        # opaque tile -- add a full-alpha channel so downstream tooling can treat every
        # decor asset uniformly as RGBA, even though this one has no transparency
        alpha = np.full(crop.shape[:2], 255, dtype=np.uint8)
        rgba = np.dstack([crop, alpha])
        out.append({"bbox": (x0, y0, x1, y1), "image": Image.fromarray(rgba, "RGBA"),
                    "area_frac": 1.0})
    return out


SLUGS = {
    "landmarks": ["dragon", "basilica", "tram", "pretzel", "pigeon", "carriage"],
    "trip": ["coaster", "flume", "ferris", "salt", "lantern", "beer", "icecream"],
    "connectors": ["route", "arrow", "plane", "flourish", "vine"],
    "furniture": ["washi", "corner", "stamp", "splat", "frame"],
    "patterns": ["dragons", "suns", "dots", "florals"],
}


def slug_for(set_name: str, idx: int) -> str:
    names = SLUGS.get(set_name, [set_name])
    base = names[idx] if idx < len(names) else f"item{idx+1}"
    return base


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for set_name, sheet_path, mode in SHEETS:
        if not sheet_path.exists():
            print(f"!! missing sheet {sheet_path}", file=sys.stderr)
            continue
        if mode == "cellgrid":
            items = cut_cellgrid_sheet(sheet_path)
        elif mode == "components":
            items = cut_components_sheet(sheet_path)
        else:
            items = cut_quad_sheet(sheet_path)
        used_slugs = {}
        for i, it in enumerate(items):
            slug = slug_for(set_name, i)
            n = used_slugs.get(slug, 0) + 1
            used_slugs[slug] = n
            fname = f"{set_name}_{slug}_{n:02d}.png"
            out_path = OUT_DIR / fname
            it["image"].save(out_path)

            rgba = np.asarray(it["image"])
            alpha = rgba[..., 3]
            cover = 100.0 * float((alpha > 10).sum()) / alpha.size
            manifest.append({
                "id": f"{set_name}_{slug}_{n:02d}",
                "set": set_name,
                "source_sheet": sheet_path.relative_to(ROOT).as_posix(),
                "file": out_path.relative_to(ROOT).as_posix(),
                "px": [int(it["image"].width), int(it["image"].height)],
                "alpha_coverage_pct": round(cover, 2),
                "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        print(f"{set_name}: cut {len(items)} items from {sheet_path.name}")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {MANIFEST} ({len(manifest)} assets)")
    build_preview(manifest)


# --------------------------------------------------------------------------- preview
def build_preview(manifest: list[dict], target_w: int = 2000):
    if not manifest:
        return
    cols = 8
    rows = (len(manifest) + cols - 1) // cols
    cell = target_w // cols
    pad = 8
    canvas_w = cell * cols
    canvas_h = (cell + 28) * rows + pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), (120, 120, 120))
    # checkerboard
    cb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    sq = 16
    for y in range(0, canvas_h, sq):
        for x in range(0, canvas_w, sq):
            c = 170 if ((x // sq) + (y // sq)) % 2 == 0 else 130
            cb[y:y + sq, x:x + sq] = c
    canvas = Image.fromarray(cb, "RGB")

    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()

    for i, m in enumerate(manifest):
        r, c = divmod(i, cols)
        x0, y0 = c * cell, r * (cell + 28)
        im = Image.open(ROOT / m["file"]).convert("RGBA")
        im.thumbnail((cell - pad * 2, cell - pad * 2))
        canvas.paste(im, (x0 + pad, y0 + pad), im)
        label = m["id"]
        if len(label) > 22:
            label = label[:22] + "…"
        draw.text((x0 + pad, y0 + cell - 4), label, fill=(20, 20, 20), font=font)

    canvas.save(PREVIEW)
    print(f"wrote {PREVIEW}")


# --------------------------------------------------------------------------- verify
def verify():
    ok = True
    if not MANIFEST.exists():
        print("!! manifest missing"); return False
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest:
        print("!! manifest empty"); return False

    by_set = {}
    for m in manifest:
        by_set.setdefault(m["set"], []).append(m)

    for m in manifest:
        p = ROOT / m["file"]
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"!! {m['id']}: cannot decode ({e})"); ok = False; continue
        if im.mode != "RGBA":
            print(f"!! {m['id']}: mode is {im.mode}, expected RGBA"); ok = False; continue

        arr = np.asarray(im)
        alpha = arr[..., 3]
        cover = 100.0 * float((alpha > 10).sum()) / alpha.size

        if m["set"] not in ("patterns", "patterns2"):
            corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
            # allow one corner to be grazed by a thin protruding detail (e.g. a lantern's
            # handle loop reaching the crop edge) -- a real matting failure hits more than one
            if sum(c < 20 for c in corners) < 3:
                print(f"!! {m['id']}: corners not transparent ({corners})"); ok = False
            if not (COVER_MIN <= cover <= COVER_MAX):
                print(f"!! {m['id']}: alpha coverage {cover:.1f}% out of [{COVER_MIN},{COVER_MAX}]")
                ok = False
        # patterns sheets are intentionally opaque full-bleed tiles -- skip corner/coverage check

    if not PREVIEW.exists():
        print("!! preview missing"); ok = False

    print(f"verify: {len(manifest)} assets across {len(by_set)} sets "
          f"({', '.join(f'{k}={len(v)}' for k, v in by_set.items())})")
    covs = [m["alpha_coverage_pct"] for m in manifest if m["set"] not in ("patterns", "patterns2")]
    if covs:
        print(f"coverage range (non-pattern sets): {min(covs):.1f}% - {max(covs):.1f}%")
    print("PASS" if ok else "FAIL")
    return ok


# --------------------------------------------------------------------------- decoration kit 2
SHEETS2 = [
    ("castle", SHEETS_DIR / "decor2_castle_01.png", "components",
     ["castle", "clothhall", "towers", "cobblestones", "streetlamp", "window", "walls"]),
    ("dragon2", SHEETS_DIR / "decor2_dragon_01.png", "components",
     ["footprints", "egg", "flame", "scales", "sleeping", "tail"]),
    ("themepark", SHEETS_DIR / "decor2_themepark_01.png", "cellgrid",
     ["loop", "car", "splash", "harness", "wristband", "balloons", "carousel", "cottoncandy"]),
    ("science", SHEETS_DIR / "decor2_science_01.png", "components",
     ["gears", "lightbulb", "rocket", "planets", "magnet", "paperplane", "lever", "bubbles"]),
    ("saltmine", SHEETS_DIR / "decor2_saltmine_01.png", "cellgrid",
     ["crystalcluster", "crystalcube", "crystalgeode", "cart", "wheel", "chandelier", "lantern", "beams", "ripple"]),
    ("river", SHEETS_DIR / "decor2_river_01.png", "components",
     ["bend", "ferry", "ducks", "swan", "willow", "blanket", "bicycle", "bench", "kite"]),
    ("food", SHEETS_DIR / "decor2_food_01.png", "components",
     ["pretzel", "pierogi", "zapiekanka", "icecream", "beer", "coffee", "soup", "cherries"]),
    ("travel", SHEETS_DIR / "decor2_travel_01.png", "cellgrid",
     ["planeside", "planetop", "suitcase", "passport", "compass", "mappin", "flightpath", "cloud", "car"]),
    ("scrapA", SHEETS_DIR / "decor2_scrapA_01.png", "cellgrid",
     ["heart1", "heart2", "heart3", "stars", "sun", "arrow1", "arrow2", "speechbubble", "wreath", "confetti"]),
    ("scrapB", SHEETS_DIR / "decor2_scrapB_01.png", "cellgrid",
     ["paperclip", "pushpin", "stitchedstrip", "tornpaper", "filmstrip", "photocorner", "pennants", "bow"]),
    ("frames2", SHEETS_DIR / "decor2_frames_01.png", "components",
     ["thin", "wood", "circle", "brush", "dashed", "scalloped", "double"]),
    ("patterns2", SHEETS_DIR / "decor2_patterns2_01.png", "quad",
     ["coastertrack", "saltcrystals", "dragonscales2", "dotsgrid"]),
    ("rides", SHEETS_DIR / "decor2_rides_01.png", "components",
     ["flumeside", "flumeangle", "splash", "snake", "vines", "flumedrop",
      "coastercar", "pyramid", "trackclimb", "droptower", "trackloop", "queuepost"]),
]


def run2():
    """Cut the "decoration kit 2" sheets and append to the existing manifest (never rewriting
    prior entries). Writes a second preview, records/decor_preview2.png, with only the new
    assets so the human reviewer can judge this batch on its own.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    v2_sets = {s[0] for s in SHEETS2}
    existing_all = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    # re-runnable: drop any prior decoration-kit-2 entries (and their files) before re-cutting,
    # so a corrected cutting-mode pass doesn't leave stale/duplicate assets behind.
    existing = [m for m in existing_all if m["set"] not in v2_sets]
    for stale in existing_all:
        if stale["set"] in v2_sets:
            stale_path = ROOT / stale["file"]
            if stale_path.exists():
                stale_path.unlink()
    existing_ids = {m["id"] for m in existing}
    new_entries = []

    for set_name, sheet_path, mode, slugs in SHEETS2:
        if not sheet_path.exists():
            print(f"!! missing sheet {sheet_path}", file=sys.stderr)
            continue
        if mode == "cellgrid":
            items = cut_cellgrid_sheet(sheet_path)
        elif mode == "components":
            items = cut_components_sheet(sheet_path)
        else:
            items = cut_quad_sheet(sheet_path)

        used_slugs = {}
        for i, it in enumerate(items):
            slug = slugs[i] if i < len(slugs) else f"item{i+1}"
            n = used_slugs.get(slug, 0) + 1
            used_slugs[slug] = n
            asset_id = f"{set_name}_{slug}_{n:02d}"
            fname = f"{asset_id}.png"
            out_path = OUT_DIR / fname
            it["image"].save(out_path)

            rgba = np.asarray(it["image"])
            alpha = rgba[..., 3]
            cover = 100.0 * float((alpha > 10).sum()) / alpha.size
            entry = {
                "id": asset_id,
                "set": set_name,
                "source_sheet": sheet_path.relative_to(ROOT).as_posix(),
                "file": out_path.relative_to(ROOT).as_posix(),
                "px": [int(it["image"].width), int(it["image"].height)],
                "alpha_coverage_pct": round(cover, 2),
                "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            if asset_id in existing_ids:
                print(f"!! duplicate id {asset_id}, skipping to avoid clobbering", file=sys.stderr)
                continue
            new_entries.append(entry)
        print(f"{set_name}: cut {len(items)} items from {sheet_path.name} (expected {len(slugs)})")

    MANIFEST.write_text(json.dumps(existing + new_entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"appended {len(new_entries)} assets to {MANIFEST} (total {len(existing) + len(new_entries)})")
    build_preview2(new_entries)
    return new_entries


def build_preview2(new_entries: list[dict], target_w: int = 2000):
    if not new_entries:
        return
    cols = 8
    rows = (len(new_entries) + cols - 1) // cols
    cell = target_w // cols
    pad = 8
    canvas_w = cell * cols
    canvas_h = (cell + 28) * rows + pad
    cb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    sq = 16
    for y in range(0, canvas_h, sq):
        for x in range(0, canvas_w, sq):
            c = 170 if ((x // sq) + (y // sq)) % 2 == 0 else 130
            cb[y:y + sq, x:x + sq] = c
    canvas = Image.fromarray(cb, "RGB")

    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()

    for i, m in enumerate(new_entries):
        r, c = divmod(i, cols)
        x0, y0 = c * cell, r * (cell + 28)
        im = Image.open(ROOT / m["file"]).convert("RGBA")
        im.thumbnail((cell - pad * 2, cell - pad * 2))
        canvas.paste(im, (x0 + pad, y0 + pad), im)
        label = m["id"]
        if len(label) > 22:
            label = label[:22] + "…"
        draw.text((x0 + pad, y0 + cell - 4), label, fill=(20, 20, 20), font=font)

    canvas.save(PREVIEW2)
    print(f"wrote {PREVIEW2}")


def verify2():
    """Same checks as verify(), scoped to only the decoration-kit-2 sets."""
    ok = True
    if not MANIFEST.exists():
        print("!! manifest missing"); return False
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    v2_sets = {s[0] for s in SHEETS2}
    manifest2 = [m for m in manifest if m["set"] in v2_sets]
    if not manifest2:
        print("!! no decoration-kit-2 assets in manifest"); return False

    by_set = {}
    for m in manifest2:
        by_set.setdefault(m["set"], []).append(m)

    for m in manifest2:
        p = ROOT / m["file"]
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"!! {m['id']}: cannot decode ({e})"); ok = False; continue
        if im.mode != "RGBA":
            print(f"!! {m['id']}: mode is {im.mode}, expected RGBA"); ok = False; continue

        arr = np.asarray(im)
        alpha = arr[..., 3]
        cover = 100.0 * float((alpha > 10).sum()) / alpha.size

        if m["set"] != "patterns2":
            corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
            if sum(c < 20 for c in corners) < 3:
                print(f"!! {m['id']}: corners not transparent ({corners})"); ok = False
            if not (COVER_MIN <= cover <= COVER_MAX):
                print(f"!! {m['id']}: alpha coverage {cover:.1f}% out of [{COVER_MIN},{COVER_MAX}]")
                ok = False

    if not PREVIEW2.exists():
        print("!! preview2 missing"); ok = False

    print(f"verify2: {len(manifest2)} assets across {len(by_set)} sets "
          f"({', '.join(f'{k}={len(v)}' for k, v in by_set.items())})")
    covs = [m["alpha_coverage_pct"] for m in manifest2 if m["set"] != "patterns2"]
    if covs:
        print(f"coverage range (non-pattern sets): {min(covs):.1f}% - {max(covs):.1f}%")
    print("PASS" if ok else "FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--run2", action="store_true", help="cut decoration-kit-2 sheets, append to manifest")
    ap.add_argument("--verify2", action="store_true", help="verify only decoration-kit-2 assets")
    args = ap.parse_args()
    if args.run:
        run()
    if args.run2:
        run2()
    if args.verify:
        sys.exit(0 if verify() else 1)
    if args.verify2:
        sys.exit(0 if verify2() else 1)
    if not any([args.run, args.verify, args.run2, args.verify2]):
        ap.print_help()


if __name__ == "__main__":
    main()
