#!/usr/bin/env python3
"""ingest_incoming.py -- one-command ingestion path for NEW photos the user
drops into assets/incoming/.

Usage
-----
    python scripts/ingest_incoming.py --scan     # report only, change nothing
    python scripts/ingest_incoming.py --ingest    # do the work (idempotent)
    python scripts/ingest_incoming.py --verify    # verify manifest, exit 0/1

Pipeline (per file in assets/incoming/)
----------------------------------------
1. Validate it decodes (Pillow, + pillow-heif for .heic).
2. Apply ImageOps.exif_transpose (this album's EXIF rule -- 13 photos were
   previously printed sideways without it; see records/ledger.json history).
3. Read native dims (post-transpose) + EXIF DateTimeOriginal (fallback: file
   mtime), using the exact tag-38867/sub-IFD lookup scripts/build_ledger.py
   already uses for the rest of the album.
4. Compute a stable id ("x001", "x002", ... continuing past any existing
   ids in records/incoming_manifest.json) and copy the transposed original
   into assets/generated/incoming_src/<id>_<sanitized-name>.jpg (q95).
5. Print-readiness: effective DPI at 30cm (full page, square) and 15cm
   (half/tile) is derived from the SMALLER pixel dimension (the limiting
   edge for a square crop/print). If DPI at 30cm < 300, the project's
   FSRCNN upscale path (scripts/upscale_assets.py -- reused via import,
   its frozen 45-item / pageplan / regen contracts are never touched) is
   run to produce assets/generated/upscaled/<id>_..._x{N}_3600.jpg, capped
   at x4.
6. records/incoming_manifest.json is written/extended. Idempotent: matched
   by sha256 of the original incoming file bytes, so re-running --ingest on
   an unchanged assets/incoming/ never duplicates entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upscale_assets as ua  # reuse the project's frozen FSRCNN pipeline

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
INCOMING_DIR = REPO_ROOT / "assets" / "incoming"
SRC_OUT_DIR = REPO_ROOT / "assets" / "generated" / "incoming_src"
UPSCALED_DIR = REPO_ROOT / "assets" / "generated" / "upscaled"
MANIFEST_PATH = REPO_ROOT / "records" / "incoming_manifest.json"

VALID_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
JPEG_QUALITY = 95

# Print target: 300 DPI at 30cm full-page, 300 DPI at 15cm half/tile.
DPI_TARGET = 300
PX_30CM = DPI_TARGET * 30 / 2.54  # ~3543.3
PX_15CM = DPI_TARGET * 15 / 2.54  # ~1771.7
MAX_FACTOR = 4

# Same EXIF DateTimeOriginal lookup as scripts/build_ledger.py.
EXIF_DATETIME_ORIGINAL_TAG = 36867
EXIF_SUBIFD_TAG = 0x8769

ID_RE = re.compile(r"^x(\d{3,})$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_hidden_or_temp(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("~$"):
        return True
    lower = name.lower()
    if lower.endswith((".tmp", ".crdownload", ".part", ".download")):
        return True
    return False


def scan_incoming() -> tuple[list[Path], list[Path]]:
    """(candidate image files, ignored files) sorted by name."""
    if not INCOMING_DIR.is_dir():
        return [], []
    candidates, ignored = [], []
    for p in sorted(INCOMING_DIR.iterdir()):
        if not p.is_file():
            continue
        if is_hidden_or_temp(p):
            ignored.append(p)
            continue
        if p.suffix.lower() in VALID_EXTS:
            candidates.append(p)
        else:
            ignored.append(p)
    return candidates, ignored


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_name(stem: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")
    return s.lower() or "img"


def get_exif_datetime_original(im: Image.Image) -> str | None:
    try:
        exif = im.getexif()
    except Exception:
        return None
    if not exif:
        return None
    raw = exif.get(EXIF_DATETIME_ORIGINAL_TAG)
    if raw is None:
        try:
            sub_ifd = exif.get_ifd(EXIF_SUBIFD_TAG)
        except Exception:
            sub_ifd = None
        if sub_ifd:
            raw = sub_ifd.get(EXIF_DATETIME_ORIGINAL_TAG)
    if not raw:
        return None
    raw = str(raw).strip().strip("\x00")
    try:
        date_part, time_part = raw.split(" ", 1)
        iso = f"{date_part.replace(':', '-')}T{time_part}"
        datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
        return iso
    except Exception:
        return None


def next_id(existing_ids: list[str]) -> str:
    max_n = 0
    for i in existing_ids:
        m = ID_RE.match(i)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"x{max_n + 1:03d}"


def load_manifest() -> list[dict]:
    if MANIFEST_PATH.is_file():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return []


def save_manifest(entries: list[dict]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def dpi_for(min_edge: int, cm: float) -> float:
    return min_edge / (cm / 2.54)


def factor_needed(min_edge: int, target_px: float) -> int:
    """Smallest factor (from upscale_assets.MODEL_FILES, capped MAX_FACTOR)
    that gets min_edge to >= target_px."""
    needed = math.ceil(target_px / min_edge)
    for f in sorted(ua.MODEL_FILES):
        if f > MAX_FACTOR:
            continue
        if f >= needed:
            return f
    return MAX_FACTOR


# ---------------------------------------------------------------------------
# --scan
# ---------------------------------------------------------------------------
def cmd_scan() -> int:
    candidates, ignored = scan_incoming()
    if not INCOMING_DIR.is_dir():
        print(f"SCAN: incoming dir does not exist: {INCOMING_DIR}")
        return 0
    print(f"SCAN: {INCOMING_DIR}")
    if not candidates:
        print("0 files, ready")
    else:
        for p in candidates:
            print(f"  candidate: {p.name}")
        print(f"{len(candidates)} candidate image(s) found.")
    if ignored:
        for p in ignored:
            print(f"  ignored: {p.name}")
    return 0


# ---------------------------------------------------------------------------
# --ingest
# ---------------------------------------------------------------------------
def cmd_ingest() -> int:
    SRC_OUT_DIR.mkdir(parents=True, exist_ok=True)
    UPSCALED_DIR.mkdir(parents=True, exist_ok=True)

    candidates, _ignored = scan_incoming()
    manifest = load_manifest()
    existing_sha256 = {e["sha256"] for e in manifest if e.get("sha256")}
    existing_ids = [e["id"] for e in manifest]

    added = 0
    skipped_dupe = 0

    for src_path in candidates:
        content_sha = sha256_of(src_path)
        if content_sha in existing_sha256:
            print(f"SKIP (already ingested, sha256 match): {src_path.name}")
            skipped_dupe += 1
            continue

        new_id = next_id(existing_ids)
        existing_ids.append(new_id)

        with Image.open(src_path) as im:
            im.load()  # validate decode
            im = ImageOps.exif_transpose(im)
            taken_at = get_exif_datetime_original(im)
            im_rgb = im.convert("RGB")
            native_w, native_h = im_rgb.size

            sanitized = sanitize_name(src_path.stem)
            src_out_path = SRC_OUT_DIR / f"{new_id}_{sanitized}.jpg"
            im_rgb.save(src_out_path, "JPEG", quality=JPEG_QUALITY)

        if not taken_at:
            mtime = datetime.fromtimestamp(src_path.stat().st_mtime, tz=timezone.utc)
            taken_at = mtime.strftime("%Y-%m-%dT%H:%M:%S")
            taken_at_source = "file_mtime"
        else:
            taken_at_source = "exif"

        min_edge = min(native_w, native_h)
        dpi_30 = dpi_for(min_edge, 30.0)
        dpi_15 = dpi_for(min_edge, 15.0)

        print_file = str(src_out_path.relative_to(REPO_ROOT)).replace("\\", "/")
        print_w, print_h = native_w, native_h
        upscale_info = None

        # Already large enough for a full 60cm spread at 150 real DPI (3543px):
        # upscaling adds nothing and can exhaust memory on very large sources.
        # 2400px already gives >=200 real DPI on a 30cm page; beyond that an upscale
        # buys nothing. Very large sources also exhaust the FSRCNN allocator.
        SPREAD_CAPABLE_PX = 2400
        MAX_UPSCALE_MP = 12_000_000
        if (dpi_30 < DPI_TARGET and min_edge < SPREAD_CAPABLE_PX
                and native_w * native_h <= MAX_UPSCALE_MP):
            factor = factor_needed(min_edge, PX_30CM)
            bgr = ua.load_bgr(src_out_path)
            sr = ua.get_sr(factor)
            result_bgr = sr.upsample(bgr)
            up_h, up_w = result_bgr.shape[:2]
            rgb = result_bgr[:, :, ::-1]

            up_out_path = UPSCALED_DIR / f"{new_id}_{sanitized}_x{factor}_3600.jpg"
            Image.fromarray(rgb, "RGB").save(up_out_path, "JPEG", quality=JPEG_QUALITY)
            dims = ua.verify_saved_jpeg(up_out_path)

            print_file = str(up_out_path.relative_to(REPO_ROOT)).replace("\\", "/")
            print_w, print_h = dims
            new_min_edge = min(print_w, print_h)
            upscale_info = {
                "factor": factor,
                "capped": new_min_edge < PX_30CM - 0.5,
            }
            print(
                f"[{new_id}] {src_path.name}: {native_w}x{native_h} "
                f"(dpi30={dpi_30:.0f}) -> upscaled x{factor} -> {print_w}x{print_h}"
            )
        else:
            print(
                f"[{new_id}] {src_path.name}: {native_w}x{native_h} "
                f"(dpi30={dpi_30:.0f}, print-ready, no upscale)"
            )

        entry = {
            "id": new_id,
            "original_name": src_path.name,
            "file": print_file,
            "source_file": str(src_out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "native_px": [native_w, native_h],
            "print_px": [print_w, print_h],
            "taken_at": taken_at,
            "taken_at_source": taken_at_source,
            "dpi_30cm": round(dpi_30, 1),
            "dpi_15cm": round(dpi_15, 1),
            "chapter_hint": None,
            "added_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "sha256": content_sha,
        }
        if upscale_info:
            entry["upscale"] = upscale_info

        manifest.append(entry)
        existing_sha256.add(content_sha)
        save_manifest(manifest)  # crash-safe, one write per item
        added += 1

    print(f"\nIngest complete: {added} new, {skipped_dupe} already-ingested (skipped).")
    return 0


# ---------------------------------------------------------------------------
# --verify
# ---------------------------------------------------------------------------
def cmd_verify() -> bool:
    if not MANIFEST_PATH.is_file():
        print("PASS: no manifest yet (empty is valid).")
        return True

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not manifest:
        print("PASS: manifest is empty (valid).")
        return True

    ok = True
    seen_sha256: dict[str, str] = {}

    for e in manifest:
        eid = e.get("id", "?")

        sha = e.get("sha256")
        if sha:
            if sha in seen_sha256:
                print(f"FAIL: {eid}: duplicate sha256 with {seen_sha256[sha]}")
                ok = False
            else:
                seen_sha256[sha] = eid

        for key in ("file", "source_file"):
            rel = e.get(key)
            if not rel:
                print(f"FAIL: {eid}: missing {key}")
                ok = False
                continue
            p = REPO_ROOT / rel
            if not p.is_file():
                print(f"FAIL: {eid}: {key} missing on disk: {p}")
                ok = False
                continue
            try:
                with Image.open(p) as im:
                    im.load()
                    w, h = im.size
            except Exception as exc:
                print(f"FAIL: {eid}: {key} failed to decode: {exc}")
                ok = False
                continue
            if key == "source_file":
                native = e.get("native_px") or [None, None]
                if [w, h] != native:
                    print(f"FAIL: {eid}: source_file dims {[w, h]} != native_px {native}")
                    ok = False
            else:
                print_px = e.get("print_px") or [None, None]
                if [w, h] != print_px:
                    print(f"FAIL: {eid}: file dims {[w, h]} != print_px {print_px}")
                    ok = False

        print(f"OK: {eid} ({e.get('original_name')})" if ok else f"(see above for {eid})")

    if ok:
        print(f"\nPASS: all {len(manifest)} incoming manifest entries verified.")
    else:
        print("\nFAIL: incoming manifest verification failed (see above).")
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scan", action="store_true", help="Report what's in assets/incoming/, change nothing.")
    parser.add_argument("--ingest", action="store_true", help="Ingest new files from assets/incoming/ (idempotent).")
    parser.add_argument("--verify", action="store_true", help="Verify records/incoming_manifest.json, exit 0/1.")
    args = parser.parse_args()

    if not (args.scan or args.ingest or args.verify):
        parser.print_help()
        return 1

    rc = 0
    if args.scan:
        rc = cmd_scan()
    if args.ingest:
        rc = cmd_ingest()
    if args.verify:
        rc = 0 if cmd_verify() else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
