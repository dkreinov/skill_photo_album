#!/usr/bin/env python3
"""upscale_assets.py -- local print-resolution upscale pipeline (Overnight W2).

Upscales every fantasy/standalone AI-generated image that needs it, locally,
to print resolution (longest edge >= 3600 px), and writes editor-ready
JPEGs (q95, sRGB, no embedded ICC profile).

-----------------------------------------------------------------------------
Worklist (45 images total)
-----------------------------------------------------------------------------
    - All 44 "items" entries across every group in records/fantasy_shortlist.json.
      Every one of these has edit_kind=="fantasy" and upscale_needed==true; the
      JSON's own counts.items==44 confirms groups[].items is the complete
      fantasy/standalone set. "enhanced_versions" (1 entry) and "reuploads"
      (23 entries) in that same file are real-photo reuploads / enhanced twins,
      NOT fantasy standalones -- they are intentionally excluded, matching the
      spec's "44 items" figure.
    - <EXTERNAL_PROJECT>/fantasy_images/cover.png -- outside
      this repo, in the source family-album project; read-only, never
      modified (same external-file convention as build_cover_collage.py's
      CENTER_IMAGE_PATH).

Explicitly OUT of scope (per spec's SKIP note) -- already >=3600px, and
neither is part of the worklist above anyway, so no special-case code is
needed for them:
    - The 3 "enhanced ride" photos (records/selection.json clusters
      c235/c236/c237, files under assets/real_full/ -- real photos, not
      fantasy items from fantasy_shortlist.json).
    - assets/generated/cover_collage_v1.jpg / v2.jpg (already 3600x3600).

(The script also carries a generic "already large enough" skip path -- see
factor_for_longest()/cmd_run() -- in case any worklist source is ever
already >=3600px on disk; none of the current 45 are, but --verify's
"valid output OR documented skip" contract only makes sense if that path
exists and is exercised correctly.)

-----------------------------------------------------------------------------
Method selection (empirical, per spec's stated order of preference)
-----------------------------------------------------------------------------
All 45 worklist images have a longest edge in [1254, 1672] px (confirmed by
opening every file directly, not just trusting the JSON's cached dims) -- a
uniform x3 scale-up (max 1672*3=5016, min 1254*3=3762) clears the >=3600
target for every single item, so only one factor is needed in practice
(x2/x4 model files are also present for robustness -- see MODEL_FILES).

Tried, in the spec's stated order, on 2 sample images
(assets/chatgpt/convoA/002_sample_wide.png, 1672x941, and
assets/chatgpt/convoB/010_sample_square.png, 1254x1254),
comparing visual quality via Read before committing to a full run:

  1. opencv-contrib-python `dnn_superres`, official OpenCV model zoo
     (github.com/Saafke/EDSR_Tensorflow, /Saafke/FSRCNN_Tensorflow,
     /fannymonori/TF-ESPCN -- the sources OpenCV's own dnn_superres docs
     point to). EDSR_x3.pb downloaded fine (38.5MB) but on this machine's
     CPU (Intel i5-6600, 4C/4T, no GPU/CUDA) a single x3 upsample of the
     1672x941 sample had NOT finished after >15 minutes -- ruled out
     empirically as unusable for a 45-image local batch (a single image
     already blew past the ~8-minute chunk budget). FSRCNN_x3.pb (40KB)
     and ESPCN_x3.pb (92KB) both upsampled the same 2 samples in 2-6
     seconds each, with visually sharp, artifact-free output (verified by
     rendering the saved JPEGs) -- clearly better than option 3's softness
     up close, and indistinguishable in quality from each other. FSRCNN is
     explicitly named in the spec as an acceptable option-1 model (ESPCN is
     only spec-sanctioned as a dead-URL fallback), so FSRCNN was chosen.
  => CHOSEN: FSRCNN x3 via cv2.dnn_superres, ~6s/image measured on CPU
     (45 images * ~6-10s ~= well under an hour total, comfortably fits the
     overnight/chunked budget). Options 2 (Real-ESRGAN/basicsr, heavier
     install, much slower on CPU) and 3 (Pillow Lanczos+unsharp, the
     always-works floor) were not needed.

opencv-python was swapped for opencv-contrib-python
(`pip uninstall -y opencv-python && pip install opencv-contrib-python`)
since `dnn_superres` only ships in the contrib build. Contrib is a superset
of the standard cv2 API, so this repo's other cv2 users
(scripts/cluster_pool.py, extract_video_frames.py, v1_usage.py) are
unaffected.

-----------------------------------------------------------------------------
Output / manifest
-----------------------------------------------------------------------------
assets/generated/upscaled/<orig-stem>_x<factor>_3600.jpg
    JPEG q95, RGB, no embedded ICC profile -- an untagged JPEG is
    conventionally interpreted as sRGB, the same convention this repo's
    build_cover_collage.py already uses for its `canvas.save(..., "JPEG",
    quality=95)` output.

records/upscale_manifest.json -- one entry per worklist item: orig id,
    output path, method, factor, orig/final dims, sha256 of the output
    file, per-image runtime, and status ("upscaled" or a documented
    "skipped").

After every write the script reopens + decodes the JPEG and checks
(a) longest edge >= 3600 and (b) non-blank (grayscale stddev >= 5.0 and not
a single solid color) -- the exact blank-JPEG check this repo's
build_cover_collage.py already uses (verify_saved_jpeg), reused here for
the same "project has blank-JPEG history" reason cited in the spec.

-----------------------------------------------------------------------------
Usage
-----------------------------------------------------------------------------
    python scripts/upscale_assets.py --run [--limit N]   # process next batch
                                                           # (resumable; skips
                                                           # already-valid
                                                           # outputs)
    python scripts/upscale_assets.py --verify             # verify only,
                                                            # exit 0/1
    python scripts/upscale_assets.py --run-pageplan       # Phase 4.4 print assets
    python scripts/upscale_assets.py --verify-pageplan
    python scripts/upscale_assets.py --run-regen          # repack-v3 regen renders
    python scripts/upscale_assets.py --verify-regen
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageStat

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
FANTASY_SHORTLIST_PATH = REPO_ROOT / "records" / "fantasy_shortlist.json"
PAGEPLAN_PATH = REPO_ROOT / "records" / "pageplan.json"
MANIFEST_PATH = REPO_ROOT / "records" / "upscale_manifest.json"
OUT_DIR = REPO_ROOT / "assets" / "generated" / "upscaled"
MODEL_DIR = REPO_ROOT / "cache" / "models"

# Center-cover image lives outside this repo, in the source family album
# project. Never modified -- read only. Same convention as
# build_cover_collage.py's CENTER_IMAGE_PATH.
COVER_PATH = Path(r"<PROJECTS_DIR>\family_album\fantasy images\cover.png")

# ---------------------------------------------------------------------------
# Method / model config
# ---------------------------------------------------------------------------
TARGET_LONGEST_EDGE = 3600
JPEG_QUALITY = 95
METHOD_NAME = "fsrcnn"
CV2_MODEL_KEY = "fsrcnn"

MODEL_FILES = {
    2: MODEL_DIR / "FSRCNN_x2.pb",
    3: MODEL_DIR / "FSRCNN_x3.pb",
    4: MODEL_DIR / "FSRCNN_x4.pb",
}

# Same blank-JPEG threshold as scripts/build_cover_collage.py's
# verify_saved_jpeg (grayscale stddev below this reads as "blank").
BLANK_STDDEV_THRESHOLD = 5.0

# --- Phase 4.4 pageplan mode (print-asset finishing) ----------------------------------
# Every file a frozen-pageplan slot actually displays (display_file if set, else
# source.file) whose longest edge is below this threshold gets FSRCNN-upscaled.
UPSCALE_THRESHOLD = 2400
# Factor selection: smallest factor whose output clears BOTH the module-wide
# 3600px longest-edge contract AND >=250 dpi at the slot's planned print size
# (planned_cm, largest across slots sharing the file), capped at x4 per spec
# ("cap x3-x4") when 250 dpi is unreachable.
PRINT_DPI_TARGET = 250
MAX_PAGEPLAN_FACTOR = 4


# ---------------------------------------------------------------------------
# Worklist
# ---------------------------------------------------------------------------
def load_worklist() -> list[dict]:
    data = json.loads(FANTASY_SHORTLIST_PATH.read_text(encoding="utf-8"))

    ids = []
    for group in data["groups"]:
        for item in group["items"]:
            ids.append(item["id"])

    expected = data["counts"]["items"]
    if len(ids) != expected:
        raise AssertionError(
            f"groups[].items count {len(ids)} != counts.items {expected}"
        )
    if len(set(ids)) != len(ids):
        raise AssertionError("duplicate ids found in fantasy_shortlist groups items")

    worklist = [{"id": i, "abs_path": REPO_ROOT / i} for i in ids]
    worklist.append({"id": str(COVER_PATH), "abs_path": COVER_PATH})

    stems = [Path(w["abs_path"]).stem for w in worklist]
    if len(set(stems)) != len(stems):
        raise AssertionError("duplicate output stems across worklist -- naming collision")

    return worklist


def output_path_for(abs_path: Path, factor: int) -> Path:
    stem = Path(abs_path).stem
    return OUT_DIR / f"{stem}_x{factor}_{TARGET_LONGEST_EDGE}.jpg"


# ---------------------------------------------------------------------------
# Super-resolution
# ---------------------------------------------------------------------------
_sr_cache: dict[int, "cv2.dnn_superres_DnnSuperResImpl"] = {}


def get_sr(factor: int):
    if factor not in _sr_cache:
        model_path = MODEL_FILES.get(factor)
        if model_path is None or not model_path.is_file():
            raise FileNotFoundError(f"Missing SR model for factor x{factor}: {model_path}")
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        sr.readModel(str(model_path))
        sr.setModel(CV2_MODEL_KEY, factor)
        _sr_cache[factor] = sr
    return _sr_cache[factor]


def factor_for_longest(longest: int) -> int | None:
    """Smallest available factor that reaches TARGET_LONGEST_EDGE, or None if
    `longest` already meets the target (caller should skip, not upscale)."""
    if longest >= TARGET_LONGEST_EDGE:
        return None
    needed = math.ceil(TARGET_LONGEST_EDGE / longest)
    for f in sorted(MODEL_FILES):
        if f >= needed:
            return f
    raise ValueError(
        f"No available SR factor covers required upscale "
        f"(longest={longest}, needed>=x{needed}, have {sorted(MODEL_FILES)})"
    )


def load_bgr(path: Path) -> np.ndarray:
    """Decode via Pillow (robust to Windows paths with spaces / any codec
    Pillow supports) and hand back a contiguous BGR uint8 array for cv2."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        rgb = np.array(im)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def process_item(abs_path: Path):
    """Load, pick factor, upsample. Returns None if already >= target (the
    documented-skip case), else a dict with factor/dims/rgb array/runtime."""
    bgr = load_bgr(abs_path)
    orig_h, orig_w = bgr.shape[:2]
    longest0 = max(orig_h, orig_w)

    factor = factor_for_longest(longest0)
    if factor is None:
        return {
            "skip": True,
            "orig_dims": (orig_w, orig_h),
        }

    sr = get_sr(factor)
    t0 = time.time()
    result_bgr = sr.upsample(bgr)
    elapsed = time.time() - t0

    final_h, final_w = result_bgr.shape[:2]
    rgb = np.ascontiguousarray(result_bgr[:, :, ::-1])
    return {
        "skip": False,
        "factor": factor,
        "orig_dims": (orig_w, orig_h),
        "final_dims": (final_w, final_h),
        "rgb": rgb,
        "elapsed": elapsed,
    }


# ---------------------------------------------------------------------------
# JPEG verification (write-time and --verify share this)
# ---------------------------------------------------------------------------
def verify_saved_jpeg(path: Path) -> tuple[int, int]:
    """Reopen + decode + check dims >= target and non-blank. Same check
    style as scripts/build_cover_collage.py's verify_saved_jpeg."""
    with Image.open(path) as im:
        im.load()
        w, h = im.size
        if max(w, h) < TARGET_LONGEST_EDGE:
            raise AssertionError(
                f"{path}: longest edge {max(w, h)} < {TARGET_LONGEST_EDGE}"
            )
        gray = im.convert("L")
        stat = ImageStat.Stat(gray)
        if stat.stddev[0] < BLANK_STDDEV_THRESHOLD:
            raise AssertionError(
                f"{path}: looks blank (grayscale stddev={stat.stddev[0]:.3f})"
            )
        extrema = gray.getextrema()
        if extrema[0] == extrema[1]:
            raise AssertionError(f"{path}: single solid color {extrema}")
    return (w, h)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        "target_longest_edge": TARGET_LONGEST_EDGE,
        "method": METHOD_NAME,
        "items": [],
        "counts": {"total": 0, "upscaled": 0, "skipped": 0},
    }


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def entry_is_valid(entry: dict) -> bool:
    """True if a manifest entry's output still exists, verifies OK, and its
    sha256 matches -- i.e. --run can skip reprocessing it."""
    if entry.get("status") == "skipped":
        return bool(entry.get("skip_reason"))
    if entry.get("status") != "upscaled":
        return False
    output = entry.get("output")
    if not output:
        return False
    out_path = REPO_ROOT / output
    if not out_path.is_file():
        return False
    try:
        dims = verify_saved_jpeg(out_path)
    except AssertionError:
        return False
    if sha256_of(out_path) != entry.get("sha256"):
        return False
    final = entry.get("final_dims") or {}
    if final.get("w") != dims[0] or final.get("h") != dims[1]:
        return False
    return True


# ---------------------------------------------------------------------------
# --run
# ---------------------------------------------------------------------------
def cmd_run(limit: int | None) -> int:
    worklist = load_worklist()
    manifest = load_manifest()
    by_id = {e["orig_id"]: e for e in manifest.get("items", [])}

    processed = 0
    skipped_existing = 0

    for w in worklist:
        if limit is not None and processed >= limit:
            break

        wid = w["id"]
        existing = by_id.get(wid)
        if existing is not None and entry_is_valid(existing):
            skipped_existing += 1
            continue

        abs_path = Path(w["abs_path"])
        if not abs_path.is_file():
            raise FileNotFoundError(f"worklist source missing: {abs_path}")

        result = process_item(abs_path)

        if result["skip"]:
            ow, oh = result["orig_dims"]
            entry = {
                "orig_id": wid,
                "output": None,
                "method": None,
                "factor": None,
                "orig_dims": {"w": ow, "h": oh},
                "final_dims": {"w": ow, "h": oh},
                "sha256": None,
                "runtime_sec": 0.0,
                "status": "skipped",
                "skip_reason": f"source already >= {TARGET_LONGEST_EDGE}px longest edge",
            }
            print(f"SKIP (already >= target): {wid} ({ow}x{oh})")
        else:
            factor = result["factor"]
            out_path = output_path_for(abs_path, factor)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(result["rgb"], "RGB").save(
                out_path, "JPEG", quality=JPEG_QUALITY
            )

            dims = verify_saved_jpeg(out_path)
            digest = sha256_of(out_path)
            ow, oh = result["orig_dims"]

            entry = {
                "orig_id": wid,
                "output": str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "method": METHOD_NAME,
                "factor": factor,
                "orig_dims": {"w": ow, "h": oh},
                "final_dims": {"w": dims[0], "h": dims[1]},
                "sha256": digest,
                "runtime_sec": round(result["elapsed"], 2),
                "status": "upscaled",
            }
            print(
                f"[{processed + 1}] {wid} -> {entry['output']} "
                f"({ow}x{oh} -> {dims[0]}x{dims[1]}, x{factor}, "
                f"{entry['runtime_sec']}s)"
            )

        by_id[wid] = entry
        processed += 1

        # Persist after every item so a run is crash-safe / resumable.
        manifest["items"] = list(by_id.values())
        manifest["counts"] = {
            "total": len(worklist),
            "upscaled": sum(1 for e in by_id.values() if e.get("status") == "upscaled"),
            "skipped": sum(1 for e in by_id.values() if e.get("status") == "skipped"),
        }
        save_manifest(manifest)

    total_done = sum(1 for w in worklist if w["id"] in by_id)
    print(
        f"\nBatch complete: processed {processed} new, "
        f"skipped {skipped_existing} already-valid, "
        f"{total_done}/{len(worklist)} total done."
    )
    return 0


# ---------------------------------------------------------------------------
# Phase 4.4 pageplan mode (--run-pageplan / --verify-pageplan)
#
# Extends the proven FSRCNN pipeline to every image the FROZEN pageplan
# actually prints that is still below print resolution: the accepted
# enhancement outputs (assets/generated/enhance/*, ~1448px), the regen art
# (timeline v4 / tycoon v2 / saltmine v1, 1254-1774px), the s10 video frame
# (1920px) and the official-ride booth PNG (1419px).  Fantasy items already
# upscaled by the original 45-item run are REUSED, never reprocessed --
# their legacy manifest["items"] entries remain the source of truth.
# New outputs land in the same OUT_DIR with the established
# <stem>_x<factor>_3600.jpg naming and are recorded under a separate
# manifest key "pageplan_items" so the frozen 45-item contract that
# --verify checks is untouched.
# ---------------------------------------------------------------------------
def load_pageplan_worklist() -> list[dict]:
    """Distinct files used by pageplan slots (display_file wins over
    source.file; text slots carry no file) whose longest edge < threshold."""
    plan = json.loads(PAGEPLAN_PATH.read_text(encoding="utf-8"))
    used: dict[str, dict] = {}
    for sp in plan["spreads"]:
        for s in sp.get("slots", []):
            f = s.get("display_file") or (s.get("source") or {}).get("file")
            if not f:
                continue
            e = used.setdefault(f, {"slots": [], "planned_cm": 0.0})
            e["slots"].append(s["slot_id"])
            e["planned_cm"] = max(e["planned_cm"], float(s.get("planned_cm") or 0.0))

    worklist = []
    for f in sorted(used):
        abs_path = REPO_ROOT / f
        if not abs_path.is_file():
            raise FileNotFoundError(f"pageplan slot file missing: {abs_path}")
        with Image.open(abs_path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        if max(w, h) >= UPSCALE_THRESHOLD:
            continue
        worklist.append({
            "id": f,
            "abs_path": abs_path,
            "longest": max(w, h),
            "planned_cm": used[f]["planned_cm"],
            "slots": used[f]["slots"],
        })

    stems = [Path(w["abs_path"]).stem for w in worklist]
    if len(set(stems)) != len(stems):
        raise AssertionError("duplicate output stems in pageplan worklist -- naming collision")
    return worklist


def pageplan_target_px(planned_cm: float) -> int:
    """Longest-edge pixel target: >=250 dpi at planned size, floor 3600."""
    need = float(TARGET_LONGEST_EDGE)
    if planned_cm > 0:
        need = max(need, planned_cm / 2.54 * PRINT_DPI_TARGET)
    return int(math.ceil(need))


def pageplan_factor(longest: int, planned_cm: float) -> int:
    need = pageplan_target_px(planned_cm)
    for f in sorted(MODEL_FILES):
        if f > MAX_PAGEPLAN_FACTOR:
            continue
        if longest * f >= need:
            return f
    return MAX_PAGEPLAN_FACTOR  # cap: 250 dpi unreachable, take the biggest model


def process_item_at_factor(abs_path: Path, factor: int) -> dict:
    bgr = load_bgr(abs_path)
    orig_h, orig_w = bgr.shape[:2]
    sr = get_sr(factor)
    t0 = time.time()
    result_bgr = sr.upsample(bgr)
    elapsed = time.time() - t0
    final_h, final_w = result_bgr.shape[:2]
    rgb = np.ascontiguousarray(result_bgr[:, :, ::-1])
    return {
        "factor": factor,
        "orig_dims": (orig_w, orig_h),
        "final_dims": (final_w, final_h),
        "rgb": rgb,
        "elapsed": elapsed,
    }


def _legacy_valid_entry(manifest: dict, orig_id: str) -> dict | None:
    """A still-valid entry from the original 45-item run, for reuse."""
    for e in manifest.get("items", []):
        if e.get("orig_id") == orig_id and e.get("status") == "upscaled" and entry_is_valid(e):
            return e
    return None


def cmd_run_pageplan(limit: int | None) -> int:
    worklist = load_pageplan_worklist()
    manifest = load_manifest()
    pp_by_id = {e["orig_id"]: e for e in manifest.get("pageplan_items", [])}

    processed = 0
    reused_legacy = 0
    skipped_existing = 0

    for w in worklist:
        if limit is not None and processed >= limit:
            break
        wid = w["id"]

        legacy = _legacy_valid_entry(manifest, wid)
        if legacy is not None:
            reused_legacy += 1
            continue

        existing = pp_by_id.get(wid)
        if existing is not None and entry_is_valid(existing):
            skipped_existing += 1
            continue

        factor = pageplan_factor(w["longest"], w["planned_cm"])
        target = pageplan_target_px(w["planned_cm"])
        result = process_item_at_factor(Path(w["abs_path"]), factor)

        out_path = output_path_for(Path(w["abs_path"]), factor)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(result["rgb"], "RGB").save(out_path, "JPEG", quality=JPEG_QUALITY)

        dims = verify_saved_jpeg(out_path)
        digest = sha256_of(out_path)
        ow, oh = result["orig_dims"]

        entry = {
            "orig_id": wid,
            "output": str(out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "method": METHOD_NAME,
            "factor": factor,
            "planned_cm": w["planned_cm"],
            "target_px": target,
            "capped": max(dims) < target,
            "slots": w["slots"],
            "orig_dims": {"w": ow, "h": oh},
            "final_dims": {"w": dims[0], "h": dims[1]},
            "sha256": digest,
            "runtime_sec": round(result["elapsed"], 2),
            "status": "upscaled",
        }
        pp_by_id[wid] = entry
        processed += 1
        print(
            f"[{processed}] {wid} -> {entry['output']} "
            f"({ow}x{oh} -> {dims[0]}x{dims[1]}, x{factor}, planned {w['planned_cm']}cm, "
            f"target>={target}px{' CAPPED' if entry['capped'] else ''}, "
            f"{entry['runtime_sec']}s)"
        )

        # Persist after every item so a run is crash-safe / resumable.
        manifest["pageplan_items"] = list(pp_by_id.values())
        manifest["pageplan_counts"] = {
            "worklist": len(worklist),
            "upscaled": len(pp_by_id),
            "reused_legacy": reused_legacy,
        }
        save_manifest(manifest)

    # Persist counts even if nothing new was processed this invocation.
    manifest["pageplan_items"] = list(pp_by_id.values())
    manifest["pageplan_counts"] = {
        "worklist": len(worklist),
        "upscaled": len(pp_by_id),
        "reused_legacy": reused_legacy,
    }
    save_manifest(manifest)

    print(
        f"\nPageplan batch complete: {processed} new, {skipped_existing} already-valid, "
        f"{reused_legacy} reused from the original 45-item run, "
        f"worklist {len(worklist)} files (<{UPSCALE_THRESHOLD}px)."
    )
    return 0


def resolve_pageplan_output(manifest: dict, orig_id: str) -> dict | None:
    """The upscaled-output entry for a pageplan file: legacy run first
    (reuse), then the pageplan run."""
    legacy = _legacy_valid_entry(manifest, orig_id)
    if legacy is not None:
        return legacy
    for e in manifest.get("pageplan_items", []):
        if e.get("orig_id") == orig_id:
            return e
    return None


def cmd_verify_pageplan() -> bool:
    worklist = load_pageplan_worklist()
    if not MANIFEST_PATH.is_file():
        print(f"FAIL: manifest missing: {MANIFEST_PATH}")
        return False
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    ok = True
    for w in worklist:
        wid = w["id"]
        entry = resolve_pageplan_output(manifest, wid)
        if entry is None:
            print(f"FAIL: {wid}: no upscaled output recorded (legacy or pageplan)")
            ok = False
            continue
        output = entry.get("output")
        out_path = REPO_ROOT / output if output else None
        if out_path is None or not out_path.is_file():
            print(f"FAIL: {wid}: output missing: {output}")
            ok = False
            continue
        try:
            dims = verify_saved_jpeg(out_path)
        except AssertionError as exc:
            print(f"FAIL: {exc}")
            ok = False
            continue
        if sha256_of(out_path) != entry.get("sha256"):
            print(f"FAIL: {wid}: sha256 mismatch on {output}")
            ok = False
            continue
        final = entry.get("final_dims") or {}
        if final.get("w") != dims[0] or final.get("h") != dims[1]:
            print(f"FAIL: {wid}: final_dims mismatch on {output}")
            ok = False
            continue
        via = "legacy-x3-run" if entry.get("planned_cm") is None else f"pageplan x{entry.get('factor')}"
        print(f"OK: {wid} -> {output} ({dims[0]}x{dims[1]}, {via})")

    pp_ids = {e["orig_id"] for e in manifest.get("pageplan_items", [])}
    wl_ids = {w["id"] for w in worklist}
    extra = pp_ids - wl_ids
    if extra:
        print(f"FAIL: pageplan_items has {len(extra)} entries outside the worklist: {sorted(extra)}")
        ok = False

    if ok:
        print(f"\nOK: all {len(worklist)} pageplan files below {UPSCALE_THRESHOLD}px have verified upscaled outputs.")
    else:
        print("\nFAIL: pageplan verification failed (see above).")
    return ok


# ---------------------------------------------------------------------------
# Repack-v3 regen mode (--run-regen / --verify-regen)
#
# The two GPT regens the user approved in the v3 repack round (oplan step 5.D)
# are brand-new files that NEITHER frozen worklist can see: they are not in
# records/fantasy_shortlist.json (so the frozen 45-item --run/--verify contract
# is untouched) and not in the frozen records/pageplan.json (so the Phase-4.4
# --run-pageplan worklist is untouched).  They land in this module through an
# explicit, spelled-out list, are upscaled with the same FSRCNN pipeline, the
# same output naming (<stem>_x<factor>_3600.jpg, q95, sRGB) and the same
# reopen+decode+non-blank guard as every other path here.
#
# Factor: pageplan_factor() with the slot's planned print size -- both are
# full-spread (60 cm) fantasies, so the rule asks for >=250 dpi at 60 cm
# (5906 px) and picks x4 (1774*4 = 7096 px), exactly as it already did for the
# same-sized regen art timeline_unified_v4 (1774x887 -> x4).
#
# NO MANIFEST WRITE: step 5.D's write boundary allows new files under
# assets/generated/upscaled/ but not records/upscale_manifest.json, so this
# path deliberately keeps that record byte-identical.  Nothing is lost --
# --verify-regen re-derives everything (factor, expected output path, dims,
# non-blankness) from the constants below plus the files on disk, and
# records/pageplan_v3.json carries the resulting print_file/px per slot.
# ---------------------------------------------------------------------------
REGEN_V3_ITEMS = [
    # (source, planned print width in cm, the v3 slot it feeds)
    {"id": "assets/generated/regen/s07_rapids_fantasy_v2.png",
     "planned_cm": 60.0, "slot": "n05-m1"},
    {"id": "assets/generated/regen/s30_bunny_wide_v1.png",
     "planned_cm": 60.0, "slot": "n29-m1"},
]


def regen_plan() -> list[dict]:
    """[(source, factor, expected output path), ...] -- pure function of the
    constants above plus the source dimensions on disk."""
    out = []
    for it in REGEN_V3_ITEMS:
        abs_path = REPO_ROOT / it["id"]
        if not abs_path.is_file():
            raise FileNotFoundError(f"regen source missing: {abs_path}")
        with Image.open(abs_path) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        factor = pageplan_factor(max(w, h), it["planned_cm"])
        out.append({**it, "abs_path": abs_path, "orig_dims": (w, h),
                    "factor": factor,
                    "target_px": pageplan_target_px(it["planned_cm"]),
                    "out_path": output_path_for(abs_path, factor)})
    return out


def cmd_run_regen() -> int:
    for w in regen_plan():
        out_path = w["out_path"]
        if out_path.is_file():
            try:
                dims = verify_saved_jpeg(out_path)
                print(f"SKIP (already valid): {w['id']} -> "
                      f"{out_path.relative_to(REPO_ROOT).as_posix()} ({dims[0]}x{dims[1]})")
                continue
            except AssertionError:
                pass  # bad output on disk -- redo it
        result = process_item_at_factor(w["abs_path"], w["factor"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(result["rgb"], "RGB").save(out_path, "JPEG", quality=JPEG_QUALITY)
        dims = verify_saved_jpeg(out_path)
        ow, oh = result["orig_dims"]
        print(f"{w['id']} -> {out_path.relative_to(REPO_ROOT).as_posix()} "
              f"({ow}x{oh} -> {dims[0]}x{dims[1]}, x{w['factor']}, slot {w['slot']}, "
              f"planned {w['planned_cm']}cm, target>={w['target_px']}px, "
              f"{result['elapsed']:.2f}s)")
    print(f"\nRegen batch complete: {len(REGEN_V3_ITEMS)} item(s).")
    return 0


def cmd_verify_regen() -> bool:
    ok = True
    for w in regen_plan():
        out_path = w["out_path"]
        rel = out_path.relative_to(REPO_ROOT).as_posix()
        if not out_path.is_file():
            print(f"FAIL: {w['id']}: output missing: {rel}")
            ok = False
            continue
        try:
            dims = verify_saved_jpeg(out_path)
        except AssertionError as exc:
            print(f"FAIL: {exc}")
            ok = False
            continue
        if dims[0] != w["orig_dims"][0] * w["factor"] or dims[1] != w["orig_dims"][1] * w["factor"]:
            print(f"FAIL: {rel}: {dims[0]}x{dims[1]} is not x{w['factor']} of "
                  f"{w['orig_dims'][0]}x{w['orig_dims'][1]}")
            ok = False
            continue
        print(f"OK: {w['id']} -> {rel} ({dims[0]}x{dims[1]}, x{w['factor']})")
    print("\nOK: both repack-v3 regens verified." if ok
          else "\nFAIL: regen verification failed (see above).")
    return ok


# ---------------------------------------------------------------------------
# --verify
# ---------------------------------------------------------------------------
def cmd_verify() -> bool:
    worklist = load_worklist()

    if not MANIFEST_PATH.is_file():
        print(f"FAIL: manifest missing: {MANIFEST_PATH}")
        return False

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_id = {e["orig_id"]: e for e in manifest.get("items", [])}

    ok = True
    for w in worklist:
        wid = w["id"]
        entry = by_id.get(wid)
        if entry is None:
            print(f"FAIL: {wid}: no manifest entry")
            ok = False
            continue

        status = entry.get("status")

        if status == "skipped":
            reason = entry.get("skip_reason")
            if not reason:
                print(f"FAIL: {wid}: status=skipped but no skip_reason documented")
                ok = False
            else:
                print(f"OK (documented skip): {wid}: {reason}")
            continue

        if status != "upscaled":
            print(f"FAIL: {wid}: unexpected status {status!r}")
            ok = False
            continue

        output = entry.get("output")
        if not output:
            print(f"FAIL: {wid}: status=upscaled but no output recorded")
            ok = False
            continue

        out_path = REPO_ROOT / output
        if not out_path.is_file():
            print(f"FAIL: {wid}: output missing: {out_path}")
            ok = False
            continue

        try:
            dims = verify_saved_jpeg(out_path)
        except AssertionError as exc:
            print(f"FAIL: {exc}")
            ok = False
            continue

        digest = sha256_of(out_path)
        if digest != entry.get("sha256"):
            print(
                f"FAIL: {wid}: sha256 mismatch "
                f"(manifest {entry.get('sha256')} vs actual {digest})"
            )
            ok = False
            continue

        final = entry.get("final_dims") or {}
        if final.get("w") != dims[0] or final.get("h") != dims[1]:
            print(
                f"FAIL: {wid}: manifest final_dims {final} != actual "
                f"{{'w': {dims[0]}, 'h': {dims[1]}}}"
            )
            ok = False
            continue

        print(f"OK: {wid} -> {output} ({dims[0]}x{dims[1]}, x{entry.get('factor')})")

    manifest_ids = set(by_id)
    worklist_ids = {w["id"] for w in worklist}
    extra = manifest_ids - worklist_ids
    if extra:
        print(f"FAIL: manifest has {len(extra)} entries outside the worklist: {sorted(extra)}")
        ok = False

    if ok:
        print(f"\nOK: all {len(worklist)} worklist items verified.")
    else:
        print("\nFAIL: verification failed (see above).")

    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--run", action="store_true", help="Process the worklist (resumable)."
    )
    parser.add_argument(
        "--verify", action="store_true", help="Verify manifest + outputs, exit 0/1."
    )
    parser.add_argument(
        "--run-pageplan", action="store_true",
        help="Phase 4.4: upscale every pageplan slot file below "
             f"{UPSCALE_THRESHOLD}px longest edge (resumable; reuses the "
             "original 45-item outputs where valid).",
    )
    parser.add_argument(
        "--verify-pageplan", action="store_true",
        help="Verify every pageplan slot file below the threshold has a "
             "valid upscaled output, exit 0/1.",
    )
    parser.add_argument(
        "--run-regen", action="store_true",
        help="Repack v3: upscale the two approved GPT regen renders "
             "(assets/generated/regen/s07_rapids_fantasy_v2.png, "
             "s30_bunny_wide_v1.png) to print resolution.",
    )
    parser.add_argument(
        "--verify-regen", action="store_true",
        help="Verify the repack-v3 regen outputs exist, decode, are non-blank "
             "and carry the expected factor, exit 0/1.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max NEW images to process this invocation (--run only); "
        "already-valid outputs are always skipped regardless of --limit.",
    )
    args = parser.parse_args()

    if not (args.run or args.verify or args.run_pageplan or args.verify_pageplan
            or args.run_regen or args.verify_regen):
        parser.print_help()
        return 1

    rc = 0
    if args.run:
        rc = cmd_run(args.limit)

    if args.verify:
        ok = cmd_verify()
        rc = 0 if ok else 1

    if args.run_pageplan:
        rc = cmd_run_pageplan(args.limit)

    if args.verify_pageplan:
        ok = cmd_verify_pageplan()
        rc = 0 if ok else 1

    if args.run_regen:
        rc = cmd_run_regen()

    if args.verify_regen:
        ok = cmd_verify_regen()
        rc = 0 if ok else 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
