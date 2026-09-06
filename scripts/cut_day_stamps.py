#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D-073 -- cut the "day stamp" sheets (family badges, per trip day) into
individual transparent stamps.

Input: assets/generated/decor_sheets/daystamp_day<N>_01.png -- a 2x2 grid of
round/oval badge-shaped family emblems on a plain white background, one sheet
per trip day, generated fresh in GPT with the family_character_sheet_v2.png
reference for likeness.

Cutting: each badge's own drawn shape is measured directly (not assumed to be
a circle) -- for every cell in the 2x2 grid we take the tight bounding box of
the non-white content and fit an axis-aligned ELLIPSE to it (a circle is just
the special case where the two semi-axes are equal). The grid itself is found
generically too: the sheet is bisected at its weakest column (the column with
the least foreground pixel coverage in the middle third of the width), then
each half is bisected at its weakest row -- this works whether the cells are
separated by a clean white gutter (days 1/2/3/5) or are drawn close enough to
touch (day 4's bottom row), without hardcoding any sheet by name.

Each badge is then re-matted with a single feathered elliptical alpha (not
the hand-drawn outline's own antialiasing), sized so the *entire* drawn rim
sits inside the ellipse -- never shaving content, at the cost of a possible
sliver of white paper inside the ellipse near the rim of a non-perfect-oval
hand-drawn badge.

Upscale: each cut badge is only ~500-600px, below the >=900px long-edge floor
this deliverable requires for a clean 6-10cm print. Each cut RGBA badge is
upscaled with the same local FSRCNN model this repo already uses
(scripts/upscale_assets.py) at the smallest factor that clears 900px, applied
on the RGB channels with the alpha channel upscaled separately via Lanczos
(FSRCNN has no alpha channel support).

Usage:
    python scripts/cut_day_stamps.py --run
    python scripts/cut_day_stamps.py --verify
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SHEETS_DIR = ROOT / "assets" / "generated" / "decor_sheets"
OUT_DIR = ROOT / "assets" / "generated" / "day_stamps"
RECORDS = ROOT / "records"
MANIFEST = RECORDS / "day_stamps_manifest.json"
PREVIEW = RECORDS / "day_stamps_preview.png"
DAY_MARKERS_MANIFEST = RECORDS / "day_markers_manifest.json"

# --------------------------------------------------------------------------- HQ (one-badge-per-file) path
OUT_DIR_HQ = ROOT / "assets" / "generated" / "day_stamps_hq"
MANIFEST_HQ = RECORDS / "day_stamps_hq_manifest.json"
PREVIEW_HQ = RECORDS / "day_stamps_hq_preview.png"

HQ_DESIGNS = [
    {"day": 1, "date": "2020-01-01", "variant": 1, "theme": "airport + plane"},
    {"day": 1, "date": "2020-01-01", "variant": 2, "theme": "first evening Old Town street"},
    {"day": 1, "date": "2020-01-01", "variant": 3, "theme": "night fountain"},
    {"day": 2, "date": "2020-01-02", "variant": 1, "theme": "log-flume splash"},
    {"day": 2, "date": "2020-01-02", "variant": 2, "theme": "roller coaster"},
    {"day": 2, "date": "2020-01-02", "variant": 3, "theme": "sunset family portrait in park"},
    {"day": 3, "date": "2020-01-03", "variant": 1, "theme": "plasma-ball exhibit"},
    {"day": 3, "date": "2020-01-03", "variant": 2, "theme": "daytime Old Town street"},
    {"day": 3, "date": "2020-01-03", "variant": 3, "theme": "castle from the riverbank"},
    {"day": 4, "date": "2020-01-04", "variant": 1, "theme": "pedal boat"},
    {"day": 4, "date": "2020-01-04", "variant": 2, "theme": "a park sculpture"},
    {"day": 4, "date": "2020-01-04", "variant": 3, "theme": "outdoor games"},
    {"day": 5, "date": "2020-01-05", "variant": 1, "theme": "chandelier chamber"},
    {"day": 5, "date": "2020-01-05", "variant": 2, "theme": "mine tunnel"},
    {"day": 5, "date": "2020-01-05", "variant": 3, "theme": "goodbye at airport"},
]

MODEL_DIR = ROOT / "cache" / "models"
TARGET_LONG_EDGE = 900
COVER_MIN, COVER_MAX = 5.0, 90.0

WHITE_THRESH = 246       # pixel value (all channels) at/above this counts as background
FEATHER_PX = 1.5         # soft the elliptical alpha edge
RIM_EPSILON_PX = 1.0     # tiny outward inflate of the fitted ellipse so the measured rim's
                          # own antialiasing is never shaved
AREA_TOL = 0.03           # opaque-area-vs-pi*a*b tolerance for verify()

DAYS = [
    {"day": 1, "date": "2020-01-01", "chapter_id": "departure",
     "sheet": SHEETS_DIR / "daystamp_day1_01.png"},
    {"day": 2, "date": "2020-01-02", "chapter_id": "themepark",
     "sheet": SHEETS_DIR / "daystamp_day2_01.png"},
    {"day": 3, "date": "2020-01-03", "chapter_id": "sciencecentre+oldtown",
     "sheet": SHEETS_DIR / "daystamp_day3_01.png"},
    {"day": 4, "date": "2020-01-04", "chapter_id": "lake-park",
     "sheet": SHEETS_DIR / "daystamp_day4_01.png"},
    {"day": 5, "date": "2020-01-05", "chapter_id": "saltmine+finale",
     "sheet": SHEETS_DIR / "daystamp_day5_01.png"},
]


def factor_for(longest: int) -> int:
    if longest >= TARGET_LONG_EDGE:
        return 1
    needed = -(-TARGET_LONG_EDGE // longest)  # ceil
    for f in (2, 3, 4):
        if f >= needed:
            return f
    return 4


_sr_cache: dict[int, object] = {}


def get_sr(factor: int):
    import cv2
    if factor not in _sr_cache:
        model_path = MODEL_DIR / f"FSRCNN_x{factor}.pb"
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        sr.readModel(str(model_path))
        sr.setModel("fsrcnn", factor)
        _sr_cache[factor] = sr
    return _sr_cache[factor]


def upscale_rgba(im: Image.Image) -> Image.Image:
    """Upscale an RGBA image to >= TARGET_LONG_EDGE: RGB via FSRCNN, alpha via
    Lanczos (matched to the same output size)."""
    import cv2
    w, h = im.size
    longest = max(w, h)
    factor = factor_for(longest)
    if factor == 1:
        return im

    rgb = im.convert("RGB")
    bgr = np.ascontiguousarray(np.array(rgb)[:, :, ::-1])
    sr = get_sr(factor)
    up_bgr = sr.upsample(bgr)
    up_rgb = np.ascontiguousarray(up_bgr[:, :, ::-1])
    out_h, out_w = up_rgb.shape[:2]

    alpha = im.split()[-1]
    alpha_up = alpha.resize((out_w, out_h), Image.LANCZOS)

    rgba = np.dstack([up_rgb, np.array(alpha_up)])
    return Image.fromarray(rgba, "RGBA")


# --------------------------------------------------------------------------- generic grid split
def _bg_mask(rgb: np.ndarray) -> np.ndarray:
    return np.all(rgb >= WHITE_THRESH, axis=-1)


def _weakest_index(profile: np.ndarray, lo_frac: float, hi_frac: float) -> int:
    """Index of the least-foreground row/column within the middle band of a profile --
    the grid seam, whether it's a clean white gutter or just the thinnest join."""
    n = len(profile)
    lo, hi = int(n * lo_frac), int(n * hi_frac)
    hi = max(hi, lo + 1)
    return lo + int(np.argmin(profile[lo:hi]))


def split_2x2(fg: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Bisect a 2x2 badge grid generically: split at the weakest column, then split
    each half at its own weakest row. Returns 4 (x0, y0, x1, y1) cells in row-major
    (reading) order. Works whether cells are cleanly gutter-separated or touch."""
    h, w = fg.shape
    col_profile = fg.sum(axis=0)
    xsplit = _weakest_index(col_profile, 0.3, 0.7)

    cells = []
    for (x0, x1) in [(0, xsplit), (xsplit, w)]:
        sub = fg[:, x0:x1]
        row_profile = sub.sum(axis=1)
        ysplit = _weakest_index(row_profile, 0.3, 0.7)
        cells.append((x0, 0, x1, ysplit))
        cells.append((x0, ysplit, x1, h))

    cells.sort(key=lambda c: (c[1], c[0]))  # row-major: top row first, left-to-right
    return cells


def fit_ellipse(fg: np.ndarray, cell: tuple[int, int, int, int]) -> dict | None:
    """Tight bbox of the actual drawn content within a cell -> fitted ellipse
    (center, semi-axes) in full-sheet pixel coordinates."""
    x0, y0, x1, y1 = cell
    sub = fg[y0:y1, x0:x1]
    ys, xs = np.where(sub)
    if len(ys) == 0:
        return None
    by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    gx0, gy0, gx1, gy1 = x0 + bx0, y0 + by0, x0 + bx1, y0 + by1
    cx, cy = (gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0
    a = (gx1 - gx0) / 2.0 + RIM_EPSILON_PX
    b = (gy1 - gy0) / 2.0 + RIM_EPSILON_PX
    return {"cx": cx, "cy": cy, "a": a, "b": b, "bbox": (gx0, gy0, gx1, gy1)}


def cut_ellipse_badge(sheet_rgb: np.ndarray, fit: dict) -> tuple[Image.Image, float, float]:
    """Crop a canvas around the fitted ellipse and matte it with a single feathered
    elliptical alpha -- the whole measured rim is guaranteed inside, at the cost of
    (at most) a hairline sliver of paper for a non-perfectly-oval hand-drawn edge.

    Returns (image, local_cx, local_cy) -- the ellipse center in the *returned* image's
    own pixel coordinates (pre-upscale), since the tight final crop can trim the two
    sides of the padded canvas asymmetrically."""
    H, W = sheet_rgb.shape[:2]
    cx, cy, a, b = fit["cx"], fit["cy"], fit["a"], fit["b"]
    pad = int(math.ceil(FEATHER_PX * 4)) + 2
    half_w, half_h = int(math.ceil(a)) + pad, int(math.ceil(b)) + pad

    # canvas local coords: sheet pixel (cx - half_w .. cx + half_w) etc, clipped/padded
    canvas = np.full((2 * half_h, 2 * half_w, 3), 255, dtype=np.uint8)
    sx0, sy0 = int(round(cx - half_w)), int(round(cy - half_h))
    sx1, sy1 = sx0 + 2 * half_w, sy0 + 2 * half_h

    src_x0, src_y0 = max(0, sx0), max(0, sy0)
    src_x1, src_y1 = min(W, sx1), min(H, sy1)
    dst_x0, dst_y0 = src_x0 - sx0, src_y0 - sy0
    dst_x1, dst_y1 = dst_x0 + (src_x1 - src_x0), dst_y0 + (src_y1 - src_y0)
    if src_x1 > src_x0 and src_y1 > src_y0:
        canvas[dst_y0:dst_y1, dst_x0:dst_x1] = sheet_rgb[src_y0:src_y1, src_x0:src_x1]

    # ellipse mask in canvas-local coords
    yy, xx = np.mgrid[0:2 * half_h, 0:2 * half_w]
    local_cx, local_cy = cx - sx0, cy - sy0
    val = ((xx - local_cx) / a) ** 2 + ((yy - local_cy) / b) ** 2
    alpha = np.where(val <= 1.0, 255, 0).astype(np.uint8)

    from scipy.ndimage import gaussian_filter
    alpha = np.clip(gaussian_filter(alpha.astype(np.float32), sigma=FEATHER_PX), 0, 255).astype(np.uint8)

    # tight-crop the canvas to content + small margin so we don't ship huge white borders
    ys, xs = np.where(alpha > 2)
    m = 4
    ty0, ty1 = max(0, ys.min() - m), min(canvas.shape[0], ys.max() + 1 + m)
    tx0, tx1 = max(0, xs.min() - m), min(canvas.shape[1], xs.max() + 1 + m)

    rgba = np.dstack([canvas[ty0:ty1, tx0:tx1], alpha[ty0:ty1, tx0:tx1]])
    out_cx, out_cy = local_cx - tx0, local_cy - ty0
    return Image.fromarray(rgba, "RGBA"), out_cx, out_cy


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    made_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for d in DAYS:
        sheet_path = d["sheet"]
        if not sheet_path.exists():
            print(f"!! missing sheet {sheet_path}", file=sys.stderr)
            continue

        im = Image.open(sheet_path).convert("RGB")
        arr = np.asarray(im)
        fg = ~_bg_mask(arr)
        fg_closed = ndimage.binary_closing(fg, structure=np.ones((3, 3)), iterations=1)

        cells = split_2x2(fg_closed)
        fits = [fit_ellipse(fg_closed, c) for c in cells]
        fits = [f for f in fits if f is not None]
        if len(fits) != 4:
            print(f"!! {sheet_path.name}: expected 4 badges, fit {len(fits)}", file=sys.stderr)

        for i, fit in enumerate(fits, start=1):
            badge, local_cx, local_cy = cut_ellipse_badge(arr, fit)
            badge_up = upscale_rgba(badge)
            fname = f"day{d['day']}_stamp_{i}.png"
            out_path = OUT_DIR / fname
            badge_up.save(out_path)

            up_scale = badge_up.width / badge.width
            arr_up = np.asarray(badge_up)
            alpha = arr_up[..., 3]
            cover = 100.0 * float((alpha > 10).sum()) / alpha.size
            manifest.append({
                "day": d["day"],
                "date": d["date"],
                "chapter_id": d["chapter_id"],
                "variant": i,
                "source_sheet": sheet_path.relative_to(ROOT).as_posix(),
                "file": out_path.relative_to(ROOT).as_posix(),
                "px": [int(badge_up.width), int(badge_up.height)],
                "coverage_pct": round(cover, 2),
                "ellipse_fit_sheet_px": {
                    "center": [round(fit["cx"], 1), round(fit["cy"], 1)],
                    "semi_axis_x": round(fit["a"], 1),
                    "semi_axis_y": round(fit["b"], 1),
                },
                "ellipse_fit_output_px": {
                    "center": [round(local_cx * up_scale, 1), round(local_cy * up_scale, 1)],
                    "semi_axis_x": round(fit["a"] * up_scale, 1),
                    "semi_axis_y": round(fit["b"] * up_scale, 1),
                },
                "made_at": made_at,
            })
        print(f"day {d['day']}: cut {len(fits)} stamps from {sheet_path.name}")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {MANIFEST} ({len(manifest)} stamps)")
    build_preview(manifest)


def build_preview(manifest: list[dict], target_w: int = 2000):
    if not manifest:
        return
    by_day: dict[int, list[dict]] = {}
    for m in manifest:
        by_day.setdefault(m["day"], []).append(m)

    max_per_row = max(len(v) for v in by_day.values())
    cols = max_per_row
    rows = len(by_day)
    cell = target_w // cols
    pad = 8
    label_h = 24
    canvas_w = cell * cols
    canvas_h = (cell + label_h) * rows

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
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for r, day in enumerate(sorted(by_day)):
        items = sorted(by_day[day], key=lambda m: m["variant"])
        y0 = r * (cell + label_h)
        draw.text((pad, y0 + 2), f"Day {day} ({by_day[day][0]['date']})", fill=(20, 20, 20), font=font)
        for c, m in enumerate(items):
            x0 = c * cell
            y1 = y0 + label_h
            im = Image.open(ROOT / m["file"]).convert("RGBA")
            im.thumbnail((cell - pad * 2, cell - pad * 2))
            canvas.paste(im, (x0 + pad, y1 + pad), im)

    canvas.save(PREVIEW)
    print(f"wrote {PREVIEW}")


def verify():
    ok = True
    if not MANIFEST.exists():
        print("!! manifest missing"); return False
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest:
        print("!! manifest empty"); return False

    by_day: dict[int, int] = {}
    for m in manifest:
        by_day[m["day"]] = by_day.get(m["day"], 0) + 1
        p = ROOT / m["file"]
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"!! {m['file']}: cannot decode ({e})"); ok = False; continue
        if im.mode != "RGBA":
            print(f"!! {m['file']}: mode is {im.mode}, expected RGBA"); ok = False; continue

        arr = np.asarray(im)
        alpha = arr[..., 3]
        cover = 100.0 * float((alpha > 10).sum()) / alpha.size
        corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
        if sum(c < 20 for c in corners) < 4:
            print(f"!! {m['file']}: corners not fully transparent ({corners})"); ok = False
        if not (COVER_MIN <= cover <= COVER_MAX):
            print(f"!! {m['file']}: coverage {cover:.1f}% out of [{COVER_MIN},{COVER_MAX}]"); ok = False
        long_edge = max(im.width, im.height)
        if long_edge < TARGET_LONG_EDGE:
            print(f"!! {m['file']}: long edge {long_edge} < {TARGET_LONG_EDGE}"); ok = False

        # ellipse-shape checks, generalised from the fitted axes (a circle is the a==b case)
        fit = m.get("ellipse_fit_output_px")
        if fit is None:
            print(f"!! {m['file']}: missing ellipse_fit_output_px"); ok = False
        else:
            cx, cy = fit["center"]
            a, b = fit["semi_axis_x"], fit["semi_axis_y"]
            h, w = alpha.shape
            yy, xx = np.mgrid[0:h, 0:w]
            val = ((xx - cx) / a) ** 2 + ((yy - cy) / b) ** 2

            inner = val <= (0.95 ** 2)
            if inner.any() and not np.all(alpha[inner] == 255):
                bad = int((alpha[inner] != 255).sum())
                print(f"!! {m['file']}: {bad} pixels inside 0.95*ellipse are not fully opaque"); ok = False

            opaque_area = int((alpha > 127).sum())
            expected_area = math.pi * a * b
            rel_err = abs(opaque_area - expected_area) / expected_area if expected_area else 1.0
            if rel_err > AREA_TOL:
                print(f"!! {m['file']}: opaque area {opaque_area} vs pi*a*b {expected_area:.0f} "
                      f"(off by {rel_err*100:.1f}%, tol {AREA_TOL*100:.0f}%)"); ok = False

    if not PREVIEW.exists():
        print("!! preview missing"); ok = False

    print(f"verify: {len(manifest)} stamps across {len(by_day)} days "
          f"({', '.join(f'day{k}={v}' for k, v in sorted(by_day.items()))})")
    covs = [m["coverage_pct"] for m in manifest]
    if covs:
        print(f"coverage range: {min(covs):.1f}% - {max(covs):.1f}%")
    axes = [(m["ellipse_fit_output_px"]["semi_axis_x"], m["ellipse_fit_output_px"]["semi_axis_y"])
            for m in manifest if "ellipse_fit_output_px" in m]
    if axes:
        ratios = [round(a / b, 3) for a, b in axes]
        print(f"axis ratio (a/b) range: {min(ratios)} - {max(ratios)}")
    print("PASS" if ok else "FAIL")
    return ok


def fit_ellipse_single(fg: np.ndarray) -> dict | None:
    """Tight bbox of the actual drawn content over the WHOLE image -> fitted ellipse
    (center, semi-axes), for the one-badge-per-file HQ inputs (no grid to split)."""
    ys, xs = np.where(fg)
    if len(ys) == 0:
        return None
    gy0, gy1, gx0, gx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    cx, cy = (gx0 + gx1) / 2.0, (gy0 + gy1) / 2.0
    a = (gx1 - gx0) / 2.0 + RIM_EPSILON_PX
    b = (gy1 - gy0) / 2.0 + RIM_EPSILON_PX
    return {"cx": cx, "cy": cy, "a": a, "b": b, "bbox": (gx0, gy0, gx1, gy1)}


def estimate_daughter_face_px(badge_rgba: Image.Image, ellipse: dict) -> int:
    """Rough face-height estimate (px) for a representative figure in the badge. These HQ
    badges consistently compose the group shoulder-up to full-body inside the fitted
    ellipse with faces in the upper ~55-75% band of the badge; the reference figure is
    usually second from the left/center. We don't run a face detector (no such dependency in this
    repo) -- instead take the well-established portrait-badge proportion: face height
    is about 11-13% of the badge's vertical diameter (2*b) for this composition style.
    That proportion was checked by eye against several cut crops during this run."""
    diameter_y = 2.0 * ellipse["b"]
    return int(round(diameter_y * 0.12))


def run_hq():
    OUT_DIR_HQ.mkdir(parents=True, exist_ok=True)
    manifest = []
    made_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for spec in HQ_DESIGNS:
        src_name = f"daystampHQ_day{spec['day']}_{spec['variant']}.png"
        src_path = SHEETS_DIR / src_name
        if not src_path.exists():
            print(f"!! missing HQ source {src_path}", file=sys.stderr)
            continue

        im = Image.open(src_path).convert("RGB")
        arr = np.asarray(im)
        fg = ~_bg_mask(arr)
        fg_closed = ndimage.binary_closing(fg, structure=np.ones((3, 3)), iterations=1)

        fit = fit_ellipse_single(fg_closed)
        if fit is None:
            print(f"!! {src_name}: no foreground content found", file=sys.stderr)
            continue

        badge, local_cx, local_cy = cut_ellipse_badge(arr, fit)

        # only upscale if below the long-edge floor (HQ sources are already ~1254px)
        long_edge = max(badge.width, badge.height)
        if long_edge < TARGET_LONG_EDGE:
            badge_out = upscale_rgba(badge)
        else:
            badge_out = badge
        up_scale = badge_out.width / badge.width

        fname = f"day{spec['day']}_hq_{spec['variant']}.png"
        out_path = OUT_DIR_HQ / fname
        badge_out.save(out_path)

        ellipse_out = {
            "center": [round(local_cx * up_scale, 1), round(local_cy * up_scale, 1)],
            "semi_axis_x": round(fit["a"] * up_scale, 1),
            "semi_axis_y": round(fit["b"] * up_scale, 1),
        }
        face_px = estimate_daughter_face_px(badge_out, {
            "cx": ellipse_out["center"][0], "cy": ellipse_out["center"][1],
            "a": ellipse_out["semi_axis_x"], "b": ellipse_out["semi_axis_y"],
        })

        manifest.append({
            "day": spec["day"],
            "date": spec["date"],
            "variant": spec["variant"],
            "theme": spec["theme"],
            "source_file": src_path.relative_to(ROOT).as_posix(),
            "file": out_path.relative_to(ROOT).as_posix(),
            "px": [int(badge_out.width), int(badge_out.height)],
            "ellipse_fit": ellipse_out,
            "face_px_estimate": face_px,
            "made_at": made_at,
        })
        print(f"day{spec['day']}_{spec['variant']}: cut {fname} "
              f"({badge_out.width}x{badge_out.height}, face~{face_px}px)")

    MANIFEST_HQ.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {MANIFEST_HQ} ({len(manifest)} stamps)")
    build_preview_hq(manifest)


def build_preview_hq(manifest: list[dict], target_w: int = 2000):
    if not manifest:
        return
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    by_day: dict[int, list[dict]] = {}
    for m in manifest:
        by_day.setdefault(m["day"], []).append(m)

    cols = max(len(v) for v in by_day.values())
    cell = target_w // cols
    face_row_h = int(cell * 0.55)
    label_h = 24
    row_h = label_h + cell + face_row_h
    canvas_w = cell * cols
    canvas_h = row_h * len(by_day)

    cb = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    sq = 16
    for y in range(0, canvas_h, sq):
        for x in range(0, canvas_w, sq):
            c = 170 if ((x // sq) + (y // sq)) % 2 == 0 else 130
            cb[y:y + sq, x:x + sq] = c
    canvas = Image.fromarray(cb, "RGB")
    draw = ImageDraw.Draw(canvas)

    for r, day in enumerate(sorted(by_day)):
        items = sorted(by_day[day], key=lambda m: m["variant"])
        y0 = r * row_h
        draw.text((8, y0 + 2), f"Day {day} ({items[0]['date']})  -  faces: " +
                   ", ".join(f"v{m['variant']}~{m['face_px_estimate']}px" for m in items),
                   fill=(20, 20, 20), font=font)
        badge_y0 = y0 + label_h
        face_y0 = badge_y0 + cell
        for c, m in enumerate(items):
            x0 = c * cell
            im = Image.open(ROOT / m["file"]).convert("RGBA")
            thumb = im.copy()
            thumb.thumbnail((cell - 16, cell - 16))
            canvas.paste(thumb, (x0 + 8, badge_y0 + 8), thumb)
            draw.text((x0 + 8, badge_y0 + 4), m["theme"], fill=(20, 20, 20), font=font_small)

            # 100% zoom crop of the face region: centered on the ellipse center,
            # upper band of the badge (faces sit above the vertical midline here)
            ell = m["ellipse_fit"]
            cx, cy, a, b = ell["center"][0], ell["center"][1], ell["semi_axis_x"], ell["semi_axis_y"]
            crop_w = crop_h = int(2.4 * m["face_px_estimate"])
            fx0 = int(cx - crop_w / 2)
            fy0 = int(cy - 0.35 * b - crop_h / 2)
            crop = im.crop((fx0, fy0, fx0 + crop_w, fy0 + crop_h))
            crop = crop.resize((face_row_h - 16, face_row_h - 16), Image.LANCZOS)
            canvas.paste(crop, (x0 + 8, face_y0 + 8), crop if crop.mode == "RGBA" else None)

    canvas.save(PREVIEW_HQ)
    print(f"wrote {PREVIEW_HQ}")


def verify_hq():
    ok = True
    if not MANIFEST_HQ.exists():
        print("!! HQ manifest missing"); return False
    manifest = json.loads(MANIFEST_HQ.read_text(encoding="utf-8"))
    if not manifest:
        print("!! HQ manifest empty"); return False

    for m in manifest:
        p = ROOT / m["file"]
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"!! {m['file']}: cannot decode ({e})"); ok = False; continue
        if im.mode != "RGBA":
            print(f"!! {m['file']}: mode is {im.mode}, expected RGBA"); ok = False; continue

        arr = np.asarray(im)
        alpha = arr[..., 3]
        corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
        if sum(c < 20 for c in corners) < 4:
            print(f"!! {m['file']}: corners not fully transparent ({corners})"); ok = False

        long_edge = max(im.width, im.height)
        if long_edge < TARGET_LONG_EDGE:
            print(f"!! {m['file']}: long edge {long_edge} < {TARGET_LONG_EDGE}"); ok = False

        fit = m.get("ellipse_fit")
        if fit is None:
            print(f"!! {m['file']}: missing ellipse_fit"); ok = False
        else:
            cx, cy = fit["center"]
            a, b = fit["semi_axis_x"], fit["semi_axis_y"]
            h, w = alpha.shape
            yy, xx = np.mgrid[0:h, 0:w]
            val = ((xx - cx) / a) ** 2 + ((yy - cy) / b) ** 2
            inner = val <= (0.95 ** 2)
            if inner.any() and not np.all(alpha[inner] == 255):
                bad = int((alpha[inner] != 255).sum())
                print(f"!! {m['file']}: {bad} pixels inside 0.95*ellipse are not fully opaque"); ok = False

    if not PREVIEW_HQ.exists():
        print("!! HQ preview missing"); ok = False

    print(f"HQ verify: {len(manifest)} stamps")
    faces = [m["face_px_estimate"] for m in manifest]
    if faces:
        print(f"face_px_estimate range: {min(faces)} - {max(faces)}")
    print("PASS" if ok else "FAIL")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--run-hq", action="store_true", help="one-badge-per-file HQ path")
    ap.add_argument("--verify-hq", action="store_true")
    args = ap.parse_args()
    if args.run:
        run()
    if args.verify:
        sys.exit(0 if verify() else 1)
    if args.run_hq:
        run_hq()
    if args.verify_hq:
        sys.exit(0 if verify_hq() else 1)
    if not any([args.run, args.verify, args.run_hq, args.verify_hq]):
        ap.print_help()


if __name__ == "__main__":
    main()
