#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D-063 -- "sticker" cutouts.

Cut a subject out of an album photo and keep it on a transparent background, so the editor can
drop it onto a page over other content (the WhatsApp / Google-Photos sticker look).

This is SEGMENTATION + ALPHA only. No pixel of the subject is ever redrawn, repainted or
regenerated -- the RGB channels are copied verbatim from the source frame and only the alpha
channel is authored. Faces cannot change, because nothing generative ever touches them.

Two variants come out of every input, both RGBA PNG at the SOURCE resolution:
    <name>_sticker.png          plain cutout
    <name>_sticker_outline.png  cutout + white sticker border + soft drop shadow

Usage:
    python scripts/make_sticker.py --list
    python scripts/make_sticker.py --run --id c024 --id c225 ...
    python scripts/make_sticker.py --verify
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "records"
OUT_DIR = ROOT / "assets" / "generated" / "stickers"
MANIFEST = RECORDS / "stickers_manifest.json"
PREVIEW = RECORDS / "stickers_preview.png"

PLAN_FILE = RECORDS / "pageplan_v7.json"
SELECTION_FILE = RECORDS / "selection.json"
UPSCALE_DIR = ROOT / "assets" / "generated" / "upscaled"
UPSCALE_RE = re.compile(r"^(.*)_x\d+_\d+$")
ACCEPTED_ENHANCE = ("accepted", "enhanced-only")
ASPECT_TOL = 0.12                 # a "better" version may not change the picture's shape

# ---- matte tuning
DESPECKLE_FRAC = 0.002            # islands under 0.2% of the subject area are noise
FEATHER_PX = 1.5                  # 1-2px feather on the alpha edge
OUTLINE_FRAC = 0.015              # white border ~1.5% of the subject's short edge
SHADOW_BLUR_MULT = 1.2            # shadow softness relative to the outline width
SHADOW_OFFSET_MULT = 0.55
SHADOW_ALPHA = 0.42

COVER_MIN, COVER_MAX = 5.0, 95.0  # a matte outside this band is a failed matte


# --------------------------------------------------------------------------- resolution chain
def _img_size(path: Path):
    try:
        return ImageOps.exif_transpose(Image.open(path)).size
    except Exception:
        return None


def _upscale_index() -> dict:
    out = {}
    if not UPSCALE_DIR.is_dir():
        return out
    for p in sorted(UPSCALE_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        m = UPSCALE_RE.match(p.stem)
        if m:
            out.setdefault(m.group(1), p.relative_to(ROOT).as_posix())
    return out


def _plan_better(plan: dict) -> dict:
    """source.file -> [display_file, print_file] -- the plan's own authoritative chain."""
    out = {}
    for sp in plan.get("spreads", []):
        for s in sp.get("slots", []):
            src = (s.get("source") or {}).get("file")
            if not src:
                continue
            for key in ("print_file", "display_file"):
                v = s.get(key)
                if v and (ROOT / v).exists():
                    out.setdefault(src, [])
                    if v not in out[src]:
                        out[src].append(v)
    return out


def _accepted_enhancements() -> dict:
    acc = {}
    p4 = RECORDS / "p4_enhance_results.json"
    if p4.exists():
        try:
            for r in json.loads(p4.read_text(encoding="utf-8")):
                if r.get("final_file") and r.get("outcome") in ACCEPTED_ENHANCE:
                    acc[r["cluster_id"]] = r["final_file"]
        except Exception:
            pass
    return acc


def resolve_best(native: str, cluster_id: str | None, plan: dict) -> tuple[str, tuple, tuple]:
    """Best available version of one picture: enhanced > upscaled > native.

    Mirrors spread_audit_tool_gen.resolve_pool, including its shape guard -- a candidate that
    flipped orientation or changed aspect is never a version of the same picture.
    Returns (best_relpath, best_px, native_px).
    """
    nat_sz = _img_size(ROOT / native)
    cands = list(_plan_better(plan).get(native, []))
    acc = _accepted_enhancements()
    if cluster_id and cluster_id in acc and (ROOT / acc[cluster_id]).exists():
        if acc[cluster_id] not in cands:
            cands.append(acc[cluster_id])
    ups = _upscale_index()
    for c in [native] + list(cands):
        u = ups.get(Path(c).stem)
        if u and u not in cands and u != native:
            cands.append(u)

    best, best_sz = native, nat_sz
    for c in cands:
        if not (ROOT / c).exists():
            continue
        sz = _img_size(ROOT / c)
        if not sz or not nat_sz:
            continue
        if (nat_sz[0] > nat_sz[1]) != (sz[0] > sz[1]):
            continue
        ra, rb = nat_sz[0] / float(nat_sz[1]), sz[0] / float(sz[1])
        if abs(ra - rb) / ra > ASPECT_TOL:
            continue
        if sz[0] > best_sz[0]:
            best, best_sz = c, sz
    return best, best_sz, nat_sz


# --------------------------------------------------------------------------- candidates
def load_plan() -> dict:
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))


def selection_reasons() -> dict:
    if not SELECTION_FILE.exists():
        return {}
    d = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    return {c["cluster_id"]: (c.get("reason") or "") for c in d.get("clusters", [])}


def candidates(plan: dict) -> list:
    """Every real, PLACED photo in the pageplan -- these are the only legal sticker sources."""
    reasons, out, seen = selection_reasons(), [], set()
    for sp in plan.get("spreads", []):
        for s in sp.get("slots", []):
            src = s.get("source") or {}
            if src.get("kind") != "cluster" or not src.get("file"):
                continue
            key = (src.get("id"), src["file"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"cluster_id": src.get("id"), "slot_id": s.get("slot_id"),
                        "spread_id": sp.get("spread_id"), "file": src["file"],
                        "people": bool(s.get("people")),
                        "reason": reasons.get(src.get("id"), "")})
    return out


def pick(idval: str, cands: list) -> dict | None:
    for c in cands:
        if idval in (c["cluster_id"], c["slot_id"]):
            return c
    for c in cands:
        if idval == c["file"] or idval == Path(c["file"]).name:
            return c
    p = Path(idval)
    if not p.is_absolute():
        p = ROOT / idval
    if p.exists():
        return {"cluster_id": None, "slot_id": None, "spread_id": None,
                "file": p.relative_to(ROOT).as_posix(), "people": True, "reason": ""}
    return None


# --------------------------------------------------------------------------- matting
_SESSIONS = {}


def _session(model: str):
    from rembg import new_session
    if model not in _SESSIONS:
        _SESSIONS[model] = new_session(model)
    return _SESSIONS[model]


def matte_rembg(img: Image.Image, model: str) -> np.ndarray:
    """Raw 0..255 alpha from rembg. Raises if the model is unavailable (e.g. needs a download
    and there is no network) -- the caller falls back and SAYS SO."""
    from rembg import remove
    out = remove(img.convert("RGB"), session=_session(model),
                 post_process_mask=True, only_mask=True)
    return np.array(out.convert("L"), dtype=np.uint8)


def matte_grabcut(img: Image.Image) -> np.ndarray:
    """Fallback: cv2 GrabCut seeded by the saliency/face region. Markedly worse on hair."""
    import cv2
    bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = 900.0 / max(h, w)
    small = cv2.resize(bgr, (int(w * scale), int(h * scale))) if scale < 1 else bgr
    sh, sw = small.shape[:2]
    rect = (int(sw * 0.08), int(sh * 0.05), int(sw * 0.84), int(sh * 0.92))
    try:
        cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cas.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), 1.15, 5)
        if len(faces):
            xs = [f[0] for f in faces] + [f[0] + f[2] for f in faces]
            ys = [f[1] for f in faces] + [f[1] + f[3] for f in faces]
            x0, x1 = max(0, min(xs) - int(sw * .12)), min(sw, max(xs) + int(sw * .12))
            y0 = max(0, min(ys) - int(sh * .18))
            rect = (x0, y0, x1 - x0, sh - y0 - 1)
    except Exception:
        pass
    mask = np.zeros((sh, sw), np.uint8)
    cv2.grabCut(small, mask, rect, np.zeros((1, 65), np.float64),
                np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_RECT)
    a = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    return cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)


def clean_alpha(alpha: np.ndarray, largest_only: bool = False) -> np.ndarray:
    """Despeckle islands < 0.2% of the subject, fill interior holes, feather 1-2px.

    largest_only: keep ONLY the biggest connected component. u2net_human_seg segments EVERY
    human in the frame, so a selfie with strangers behind comes back as several blobs; this
    reduces it to the one subject the sticker is actually about."""
    import cv2
    from scipy import ndimage
    binm = (alpha >= 128).astype(np.uint8)
    if binm.sum() == 0:
        return alpha
    n, lab, stats, _ = cv2.connectedComponentsWithStats(binm, 8)
    total = float(binm.sum())
    keep = np.zeros_like(binm)
    if largest_only and n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        keep[lab == big] = 1
        return _finish(alpha, keep)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= DESPECKLE_FRAC * total:
            keep[lab == i] = 1
    if keep.sum() == 0:
        keep = binm
    return _finish(alpha, keep)


def _finish(alpha: np.ndarray, keep: np.ndarray) -> np.ndarray:
    import cv2
    from scipy import ndimage
    filled = ndimage.binary_fill_holes(keep.astype(bool)).astype(np.uint8)
    a = alpha.astype(np.float32)
    a[filled == 0] = 0.0                       # dropped islands go fully transparent
    a[(filled == 1) & (alpha < 128)] = 255.0   # filled holes go fully opaque
    a = cv2.GaussianBlur(a, (0, 0), FEATHER_PX)
    return np.clip(a, 0, 255).astype(np.uint8)


def bbox_of(alpha: np.ndarray):
    ys, xs = np.where(alpha >= 128)
    if not len(ys):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def make_outline(rgb: np.ndarray, alpha: np.ndarray, bbox) -> Image.Image:
    """The classic sticker look: a uniform white border from a dilated alpha, plus a soft
    drop shadow underneath. Canvas stays at the source resolution."""
    import cv2
    short = min(bbox[2] - bbox[0], bbox[3] - bbox[1]) if bbox else min(alpha.shape)
    r = max(3, int(round(short * OUTLINE_FRAC)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    dil = cv2.dilate((alpha >= 128).astype(np.uint8) * 255, k)
    dil = cv2.GaussianBlur(dil.astype(np.float32), (0, 0), FEATHER_PX) / 255.0

    off = int(round(r * SHADOW_OFFSET_MULT))
    sh = np.roll(np.roll(dil, off, axis=0), off, axis=1)
    sh[:off, :] = 0
    sh[:, :off] = 0
    sh = cv2.GaussianBlur(sh, (0, 0), max(1.0, r * SHADOW_BLUR_MULT)) * SHADOW_ALPHA

    a_sub = alpha.astype(np.float32) / 255.0
    h, w = alpha.shape
    out_rgb = np.zeros((h, w, 3), np.float32)
    out_a = np.zeros((h, w), np.float32)

    for lay_rgb, lay_a in ((np.zeros((h, w, 3), np.float32), sh),          # shadow (black)
                           (np.full((h, w, 3), 255.0, np.float32), dil),   # white border
                           (rgb.astype(np.float32), a_sub)):               # the subject, verbatim
        na = lay_a + out_a * (1 - lay_a)
        with np.errstate(invalid="ignore", divide="ignore"):
            out_rgb = np.where(na[..., None] > 0,
                               (lay_rgb * lay_a[..., None]
                                + out_rgb * out_a[..., None] * (1 - lay_a[..., None]))
                               / np.maximum(na[..., None], 1e-6), 0)
        out_a = na
    arr = np.dstack([np.clip(out_rgb, 0, 255).astype(np.uint8),
                     np.clip(out_a * 255, 0, 255).astype(np.uint8)])
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- run
def sha256_of(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> list:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8")).get("stickers", [])
        except Exception:
            pass
    return []


def save_manifest(recs: list) -> None:
    MANIFEST.write_text(json.dumps(
        {"meta": {"doc": "D-063 sticker cutouts -- segmentation + alpha only, never generative",
                  "updated_at": datetime.now().isoformat(timespec="seconds"),
                  "count": len(recs)},
         "stickers": recs}, ensure_ascii=False, indent=2), encoding="utf-8")


def keep_outside_poly(alpha: np.ndarray, poly_fracs, shape) -> np.ndarray:
    """D-072 extension: force alpha=255 everywhere OUTSIDE a hand-authored polygon (fractions of
    the image, [(fx,fy), ...]), while leaving the model's own alpha untouched INSIDE it.

    Use case: a ride-vehicle photo where the background (dark water, sky) is confined to a
    geometrically simple region (e.g. one corner along a diagonal rail line) that a generic
    saliency model won't separate from the vehicle itself. The polygon marks that background
    region; anything the human/object matte already kept inside it (a raised hand reaching into
    frame) still survives, because this only ever ADDS opacity outside the polygon -- it never
    subtracts inside it. Still segmentation only: no pixel value is touched, only alpha."""
    import cv2
    from PIL import ImageDraw
    h, w = shape
    pts = [(int(round(fx * w)), int(round(fy * h))) for fx, fy in poly_fracs]
    poly_img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(poly_img).polygon(pts, fill=255)
    inside = np.array(poly_img) > 0
    out = np.where(inside, alpha, 255).astype(np.float32)
    out = cv2.GaussianBlur(out, (0, 0), FEATHER_PX)
    return np.clip(out, 0, 255).astype(np.uint8)


def force_transparent_poly(alpha: np.ndarray, poly_fracs, shape) -> np.ndarray:
    """D-072 extension: the mirror image of keep_outside_poly -- force alpha=0 INSIDE a hand-
    authored polygon regardless of what the model matted there, for a region an operator has
    visually confirmed contains no rider (e.g. the ride's restraint hardware sitting between two
    people, which a human-segmentation model wrongly fused into their silhouette). Only ever
    subtracts; use a tight box well clear of any face/hand/foot."""
    import cv2
    from PIL import ImageDraw
    h, w = shape
    pts = [(int(round(fx * w)), int(round(fy * h))) for fx, fy in poly_fracs]
    poly_img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(poly_img).polygon(pts, fill=255)
    inside = np.array(poly_img) > 0
    out = np.where(inside, 0, alpha).astype(np.float32)
    out = cv2.GaussianBlur(out, (0, 0), FEATHER_PX)
    return np.clip(out, 0, 255).astype(np.uint8)


def run_one(cand: dict, plan: dict, model: str, largest_only=False,
            crop=None, suffix="", max_px=0, exclude_poly=None,
            union_model=None, close_px=0, subtract_poly=None) -> dict:
    """crop: (l,t,r,b) as FRACTIONS of the resolved image -- a tight subject crop taken BEFORE
    matting (e.g. around the beer glasses). Cropping only selects pixels; it never alters them.
    exclude_poly: [(fx,fy), ...] fractions -- see keep_outside_poly().
    union_model: a second rembg model whose raw mask is OR'd with the primary one BEFORE
    despeckle/fill -- e.g. human_seg (people) union'd with u2net (salient object) so a metal/
    plastic ride restraint the human model half-catches doesn't get amputated at its edge.
    close_px: morphological CLOSE kernel (px) run on the binary mask before hole-filling, to
    bridge small gaps a busy metal/plastic surface leaves in the raw matte -- still pure
    segmentation cleanup, no pixel value is touched."""
    native = cand["file"]
    best, best_px, nat_px = resolve_best(native, cand.get("cluster_id"), plan)
    img = ImageOps.exif_transpose(Image.open(ROOT / best)).convert("RGB")
    if crop:
        w, h = img.size
        img = img.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if max_px and max(img.size) > max_px:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    rgb = np.array(img)

    used, note = model, ""
    try:
        alpha = matte_rembg(img, model)
        if union_model:
            alpha = np.maximum(alpha, matte_rembg(img, union_model))
            used = "%s+%s" % (model, union_model)
    except Exception as exc:
        used, note = "grabcut-fallback", "rembg unavailable (%s)" % exc
        print("    !! rembg model unavailable (%s) -- FALLING BACK to cv2 GrabCut "
              "(markedly worse on hair and glass edges)" % exc)
        alpha = matte_grabcut(img)

    if close_px:
        import cv2
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_px, close_px))
        binm = ((alpha >= 128).astype(np.uint8)) * 255
        alpha = np.where(cv2.morphologyEx(binm, cv2.MORPH_CLOSE, k) > 0, 255, alpha)

    alpha = clean_alpha(alpha, largest_only=largest_only)
    if exclude_poly:
        alpha = keep_outside_poly(alpha, exclude_poly, alpha.shape)
    if subtract_poly:
        alpha = force_transparent_poly(alpha, subtract_poly, alpha.shape)
    bbox = bbox_of(alpha)
    cov = 100.0 * float((alpha >= 128).sum()) / alpha.size

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(native).stem)
    name = "%s_%s%s" % (cand.get("cluster_id") or "file", stem, suffix)
    f_plain = OUT_DIR / ("%s_sticker.png" % name)
    f_out = OUT_DIR / ("%s_sticker_outline.png" % name)

    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(f_plain)
    if bbox:
        make_outline(rgb, alpha, bbox).save(f_out)
    else:
        Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(f_out)

    return {"id": (cand.get("cluster_id") or Path(native).stem) + suffix,
            "slot_id": cand.get("slot_id"),
            "source_file": best, "native_file": native,
            "source_sha256": sha256_of(ROOT / best),
            "native_px": list(nat_px) if nat_px else None,
            "source_px": list(best_px) if best_px else None,
            "output_px": list(img.size),
            "crop_frac": list(crop) if crop else None,
            "sticker_file": f_plain.relative_to(ROOT).as_posix(),
            "outline_file": f_out.relative_to(ROOT).as_posix(),
            "subject_bbox": bbox, "alpha_coverage_pct": round(cov, 2),
            "model": used, "largest_only": bool(largest_only), "note": note,
            "made_at": datetime.now().isoformat(timespec="seconds")}


def _upsert(recs: list, r: dict) -> list:
    return [x for x in recs if x["sticker_file"] != r["sticker_file"]] + [r]


def cmd_run(ids: list, model: str, largest_only=False, crop=None, suffix="", max_px=0,
            exclude_poly=None, union_model=None, close_px=0, subtract_poly=None) -> int:
    plan = load_plan()
    cands = candidates(plan)
    recs = load_manifest()
    for idv in ids:
        c = pick(idv, cands)
        if not c:
            print("FAIL: no candidate for %r" % idv)
            return 1
        print("  %s  %s" % (idv, c["file"]))
        r = run_one(c, plan, model, largest_only, crop, suffix, max_px, exclude_poly,
                    union_model, close_px, subtract_poly)
        print("    -> %s  coverage %.2f%%  bbox %s  [%s]"
              % (Path(r["sticker_file"]).name, r["alpha_coverage_pct"], r["subject_bbox"],
                 r["model"]))
        recs = _upsert(recs, r)
        save_manifest(recs)          # incremental: an interrupted run loses at most one image
    print("wrote %s (%d stickers)" % (MANIFEST.relative_to(ROOT), len(recs)))
    return 0


# --------------------------------------------------------------------------- batch
# Precompute-once, instant-afterwards. Nothing here is generative; it is the same matte, run
# unattended over the whole candidate set so the editor never has to wait for one.
BATCH_SKIP_RE = re.compile(
    r"(map|timeline|collage|cover|back_cover|chart|poster|diagram|ticket|panorama)",
    re.IGNORECASE)
BATCH_MAX_PX_CAP = 2400          # applied only if the projected footprint blows past the budget
BATCH_SIZE_BUDGET_GB = 3.0


def batch_candidates() -> list:
    """Every album image that plausibly HAS a subject. Maps, timelines, collage masters and the
    cover masters are excluded -- they have no figure/ground to separate."""
    out, seen = [], set()

    pm = RECORDS / "pool_manifest.json"
    if pm.exists():
        for e in json.loads(pm.read_text(encoding="utf-8")).get("entries", []):
            f = e.get("file")
            if not f or f in seen or BATCH_SKIP_RE.search(f):
                continue
            if not (ROOT / f).exists():
                continue
            seen.add(f)
            out.append({"cluster_id": e.get("cluster_id"), "slot_id": None, "spread_id": None,
                        "file": f, "people": True, "reason": ""})

    im = RECORDS / "incoming_manifest.json"
    if im.exists():
        for e in json.loads(im.read_text(encoding="utf-8")):
            f = e.get("source_file") or e.get("file")
            if not f or f in seen or BATCH_SKIP_RE.search(f) or not (ROOT / f).exists():
                continue
            seen.add(f)
            out.append({"cluster_id": e.get("id"), "slot_id": None, "spread_id": None,
                        "file": f, "people": False, "reason": ""})
    return out


def cmd_batch(model: str, limit: int = 0, probe: int = 5) -> int:
    import time
    plan = load_plan()
    recs = load_manifest()
    done = {(r.get("source_file"), r.get("source_sha256")) for r in recs}

    cands = batch_candidates()
    todo = []
    for c in cands:
        best, _, _ = resolve_best(c["file"], c.get("cluster_id"), plan)
        if (best, sha256_of(ROOT / best)) in done:
            continue
        todo.append(c)
    if limit:
        todo = todo[:limit]
    print("batch: %d candidates, %d already done, %d to do" % (len(cands), len(cands) - len(todo), len(todo)))
    if not todo:
        return 0

    t0, times, failed = time.time(), [], []
    max_px = 0
    for i, c in enumerate(todo):
        ts = time.time()
        try:
            r = run_one(c, plan, model, max_px=max_px)
        except Exception as exc:
            failed.append((c["file"], str(exc)))
            print("  [%d/%d] FAIL %s -- %s" % (i + 1, len(todo), c["file"], exc))
            continue
        cov = r["alpha_coverage_pct"]
        if not (COVER_MIN <= cov <= COVER_MAX):
            failed.append((c["file"], "coverage %.2f%% outside the gate" % cov))
            for k in ("sticker_file", "outline_file"):
                (ROOT / r[k]).unlink(missing_ok=True)
            print("  [%d/%d] GATE %s cov=%.2f%% -- skipped, not shipped"
                  % (i + 1, len(todo), Path(c["file"]).name, cov))
        else:
            recs = _upsert(recs, r)
            save_manifest(recs)                     # incremental -> resume-safe
        times.append(time.time() - ts)

        if i + 1 == probe and len(todo) > probe:
            per = sum(times) / len(times)
            sz = sum(f.stat().st_size for f in OUT_DIR.glob("*.png")) / max(1, len(times) * 2)
            proj = sz * 2 * len(todo) / 1e9
            print("  ESTIMATE: %d images ~ %.0f minutes (%.1fs/img); projected %.1f GB"
                  % (len(todo), per * len(todo) / 60.0, per, proj))
            if proj > BATCH_SIZE_BUDGET_GB:
                max_px = BATCH_MAX_PX_CAP
                print("  projected footprint exceeds %.1f GB -- capping the remaining stickers "
                      "at %dpx on the long edge (still far beyond any printed sticker size)"
                      % (BATCH_SIZE_BUDGET_GB, BATCH_MAX_PX_CAP))

    total = sum(f.stat().st_size for f in OUT_DIR.glob("*.png")) / 1e9
    print("batch done in %.1f min: %d stickers on disk, %d failed, %.2f GB total"
          % ((time.time() - t0) / 60.0, len(recs), len(failed), total))
    for f, why in failed:
        print("  failed: %s -- %s" % (f, why))
    return 0


# --------------------------------------------------------------------------- verify
def cmd_verify() -> int:
    if not MANIFEST.exists():
        print("FAIL verify: no manifest")
        return 1
    recs = json.loads(MANIFEST.read_text(encoding="utf-8")).get("stickers", [])
    if not recs:
        print("FAIL verify: manifest is empty")
        return 1
    bad = 0
    for r in recs:
        for key in ("sticker_file", "outline_file"):
            p = ROOT / r[key]
            errs = []
            if not p.exists():
                print("FAIL %-58s missing" % r[key])
                bad += 1
                continue
            im = Image.open(p)
            im.load()
            if im.mode != "RGBA":
                errs.append("mode=%s not RGBA" % im.mode)
            a = np.array(im)[:, :, 3]
            h, w = a.shape
            corners = [int(a[0, 0]), int(a[0, w - 1]), int(a[h - 1, 0]), int(a[h - 1, w - 1])]
            # A genuinely transparent background. The strict reading is "every corner is 0", but
            # a legitimate sticker (a selfie arm, a full-bleed group) can honestly touch one
            # corner, so the gate is: at most one opaque corner AND most of the frame border
            # transparent. Two opaque corners, or a mostly-opaque border, means a failed matte.
            border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
            btrans = 100.0 * float((border < 16).sum()) / border.size
            if sum(1 for c in corners if c >= 16) > 1 or btrans < 60.0:
                errs.append("background not transparent (corners=%s, border clear %.0f%%)"
                            % (corners, btrans))
            cov = 100.0 * float((a >= 128).sum()) / a.size
            if not (COVER_MIN <= cov <= COVER_MAX):
                errs.append("coverage %.2f%% outside %.0f-%.0f%%" % (cov, COVER_MIN, COVER_MAX))
            opaque = 100.0 * float((a >= 250).sum()) / a.size
            if opaque > 99.0:
                errs.append("fully-opaque frame (%.1f%%) -- matte returned the whole picture"
                            % opaque)
            print("%-4s %-56s cov=%5.2f%%  %dx%d %s"
                  % ("FAIL" if errs else "PASS", r[key], cov, w, h, "; ".join(errs)))
            bad += bool(errs)
    print("VERIFY: %d checks, %d failed" % (2 * len(recs), bad))
    return 1 if bad else 0


# --------------------------------------------------------------------------- preview
def checkerboard(size, sq=24):
    w, h = size
    a = np.indices((h, w)).sum(0) // sq
    v = np.where(a % 2 == 0, 150, 122).astype(np.uint8)
    return Image.fromarray(np.dstack([v, v, v]), "RGB")


def cmd_preview() -> int:
    from PIL import ImageDraw
    recs = json.loads(MANIFEST.read_text(encoding="utf-8")).get("stickers", [])
    W, cell, pad, lab = 2000, 320, 20, 24
    per_row = 2                      # two stickers per row: source | cutout | outline, twice
    cols = 3 * per_row
    rows = (len(recs) + per_row - 1) // per_row
    grid_w = cols * cell + (cols + 1) * pad
    scale = W / float(grid_w)
    row_h = cell + lab + pad
    canvas = Image.new("RGB", (W, int((rows * row_h + pad) * scale)), (34, 34, 38))
    big = Image.new("RGB", (grid_w, rows * row_h + pad), (34, 34, 38))
    draw = ImageDraw.Draw(big)

    def place(im, col, row, label):
        x, y = pad + col * (cell + pad), pad + row * row_h
        th = im.copy()
        th.thumbnail((cell, cell))
        box = Image.new("RGB", (cell, cell), (34, 34, 38))
        if th.mode == "RGBA":
            bg = checkerboard(th.size)
            bg.paste(th, (0, 0), th)
            th = bg
        box.paste(th.convert("RGB"), ((cell - th.size[0]) // 2, (cell - th.size[1]) // 2))
        big.paste(box, (x, y))
        draw.text((x + 4, y + cell + 6), label[:62], fill=(190, 190, 196))

    for i, r in enumerate(recs):
        row, c0 = i // per_row, 3 * (i % per_row)
        place(ImageOps.exif_transpose(Image.open(ROOT / r["source_file"])), c0, row,
              Path(r["source_file"]).name)
        place(Image.open(ROOT / r["sticker_file"]), c0 + 1, row, Path(r["sticker_file"]).name)
        place(Image.open(ROOT / r["outline_file"]), c0 + 2, row, Path(r["outline_file"]).name)

    canvas = big.resize(canvas.size, Image.LANCZOS)
    canvas.save(PREVIEW)
    print("wrote %s (%dx%d)" % (PREVIEW.relative_to(ROOT), *canvas.size))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--batch", action="store_true",
                    help="stickerize every sensible candidate, unattended, resume-safe")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--id", action="append", default=[])
    ap.add_argument("--model", default="u2net_human_seg")
    ap.add_argument("--largest", action="store_true",
                    help="keep only the biggest blob (drops bystanders segmented alongside)")
    ap.add_argument("--crop", default="", help="l,t,r,b as fractions -- tight crop before matting")
    ap.add_argument("--suffix", default="", help="output name suffix, e.g. _glasses")
    ap.add_argument("--max-px", type=int, default=0)
    ap.add_argument("--exclude-poly", default="",
                    help="fx1,fy1,fx2,fy2,... fractions -- force-transparent polygon UNLESS the "
                         "model's own mask already kept those pixels (see keep_outside_poly)")
    ap.add_argument("--union-model", default="",
                    help="second rembg model OR'd with --model before cleanup")
    ap.add_argument("--close-px", type=int, default=0,
                    help="morphological CLOSE kernel (px) to bridge small matte gaps")
    ap.add_argument("--subtract-poly", default="",
                    help="fx1,fy1,fx2,fy2,... fractions -- force-transparent polygon, ALWAYS "
                         "(see force_transparent_poly); only for a region confirmed subject-free")
    a = ap.parse_args()
    crop = tuple(float(x) for x in a.crop.split(",")) if a.crop else None
    exclude_poly = None
    if a.exclude_poly:
        vals = [float(x) for x in a.exclude_poly.split(",")]
        exclude_poly = list(zip(vals[0::2], vals[1::2]))
    subtract_poly = None
    if a.subtract_poly:
        vals = [float(x) for x in a.subtract_poly.split(",")]
        subtract_poly = list(zip(vals[0::2], vals[1::2]))

    if a.list:
        for c in candidates(load_plan()):
            print("%-6s %-8s %-6s %-1s %-52s %s"
                  % (c["cluster_id"], c["slot_id"], c["spread_id"], "P" if c["people"] else ".",
                     c["file"], c["reason"][:70]))
        return 0
    if a.run:
        if not a.id:
            print("FAIL: --run needs at least one --id")
            return 1
        return cmd_run(a.id, a.model, a.largest, crop, a.suffix, a.max_px, exclude_poly,
                       a.union_model or None, a.close_px, subtract_poly)
    if a.batch:
        return cmd_batch(a.model, a.limit)
    if a.preview:
        return cmd_preview()
    if a.verify:
        return cmd_verify()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
