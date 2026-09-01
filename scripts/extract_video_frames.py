#!/usr/bin/env python
"""Harvest candidate stills from assets/real_full/*.mp4 (Step 2.1).

For each video: decode every frame once, tracking the frame nearest to each
integer second ("sample at 1 fps"). Score each such frame's sharpness via
Laplacian variance, pick the top-3 sharpest that are pairwise >=2 seconds
apart, then drop any pick whose pHash Hamming distance to an already-kept
sibling (same video) is <=6. Save survivors as JPEGs under
assets/generated/video_frames/ and record one entry per mp4 in
records/video_frames.json.

Usage:
    python scripts/extract_video_frames.py            # harvest frames
    python scripts/extract_video_frames.py --verify   # verify results
"""

import argparse
import json
import os
import sys
import subprocess

import cv2
import imagehash
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_FULL_DIR = os.path.join(REPO_ROOT, "assets", "real_full")
OUT_DIR = os.path.join(REPO_ROOT, "assets", "generated", "video_frames")
RECORDS_DIR = os.path.join(REPO_ROOT, "records")
VIDEO_FRAMES_JSON = os.path.join(RECORDS_DIR, "video_frames.json")
LEDGER_JSON = os.path.join(RECORDS_DIR, "ledger.json")
BUILD_LEDGER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "build_ledger.py"
)

TOP_N = 3
MIN_GAP_S = 2.0
PHASH_DEDUP_THRESHOLD = 6
JPEG_QUALITY = 95
BLANK_FRACTION_THRESHOLD = 0.99


def relpath_forward_slash(path, root=REPO_ROOT):
    rel = os.path.relpath(path, root)
    return rel.replace(os.sep, "/")


def find_videos():
    files = []
    for name in sorted(os.listdir(REAL_FULL_DIR)):
        if name.lower().endswith(".mp4"):
            files.append(os.path.join(REAL_FULL_DIR, name))
    return files


def laplacian_variance(bgr_frame):
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def select_top3(candidates):
    """candidates: {second:int -> {"frame":..., "sharpness":..., "ts":...}}.

    Return an ordered (sharpest-first) list of (second, info) for up to
    TOP_N candidates that are pairwise >= MIN_GAP_S seconds apart.
    """
    ranked = sorted(
        candidates.items(), key=lambda kv: (-kv[1]["sharpness"], kv[0])
    )
    picked = []
    for second, info in ranked:
        if all(abs(second - s) >= MIN_GAP_S for s, _ in picked):
            picked.append((second, info))
        if len(picked) == TOP_N:
            break
    return picked


def phash_dedup(picked):
    """Drop any candidate whose pHash is within PHASH_DEDUP_THRESHOLD of an
    already-kept sibling. Processes in the given (sharpest-first) order, so
    the sharpest candidate is always kept.
    """
    kept = []
    kept_hashes = []
    for second, info in picked:
        rgb = cv2.cvtColor(info["frame"], cv2.COLOR_BGR2RGB)
        pil_im = Image.fromarray(rgb)
        h = imagehash.phash(pil_im)
        if any((h - kh) <= PHASH_DEDUP_THRESHOLD for kh in kept_hashes):
            continue
        kept.append((second, info, pil_im, h))
        kept_hashes.append(h)
    return kept


def validate_written_jpeg(path):
    """Reopen+decode a just-written JPEG; reject empty/undecodable/blank
    (>99% single color) files. Returns (ok: bool, reason: str|None)."""
    if not os.path.isfile(path):
        return False, "file was not written"
    if os.path.getsize(path) == 0:
        return False, "file is 0 bytes"
    try:
        with Image.open(path) as im:
            im.load()
            rgb = im.convert("RGB")
            w, h = rgb.size
            total = w * h
            if total == 0:
                return False, "image has zero pixels"
            colors = rgb.getcolors(maxcolors=total)
            if colors is not None:
                max_count = max(c for c, _ in colors)
                if (max_count / total) > BLANK_FRACTION_THRESHOLD:
                    return False, (
                        f"frame is >{BLANK_FRACTION_THRESHOLD * 100:.0f}% "
                        f"single color (blank)"
                    )
    except Exception as exc:
        return False, f"failed to reopen/decode: {exc}"
    return True, None


def process_video(path):
    rel_video = relpath_forward_slash(path)
    stem = os.path.splitext(os.path.basename(path))[0]

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return {
            "video": rel_video,
            "frames": [],
            "skip_reason": "cv2.VideoCapture could not open the file",
            "duration_s": None,
        }

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count_meta = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    candidates = {}
    best_diff = {}
    last_ts = 0.0
    frame_idx = 0
    decoded_any = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        decoded_any = True

        ts_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        if ts_msec and ts_msec > 0:
            ts = ts_msec / 1000.0
        elif fps and fps > 0:
            ts = frame_idx / fps
        else:
            ts = float(frame_idx)
        last_ts = ts

        target_second = round(ts)
        diff = abs(ts - target_second)
        if target_second not in best_diff or diff < best_diff[target_second]:
            best_diff[target_second] = diff
            candidates[target_second] = {
                "frame": frame,
                "sharpness": laplacian_variance(frame),
                "ts": ts,
            }
        frame_idx += 1

    cap.release()

    if not decoded_any:
        return {
            "video": rel_video,
            "frames": [],
            "skip_reason": "video opened but no frames could be decoded",
            "duration_s": None,
        }

    if fps and fps > 0 and frame_count_meta and frame_count_meta > 0:
        duration_s = frame_count_meta / fps
    else:
        duration_s = last_ts

    picked = select_top3(candidates)
    kept = phash_dedup(picked)

    frame_paths = []
    for second, info, pil_im, _h in kept:
        fname = f"{stem}_t{second:03d}_v1.jpg"
        out_path = os.path.join(OUT_DIR, fname)
        rgb_im = pil_im if pil_im.mode == "RGB" else pil_im.convert("RGB")
        rgb_im.save(out_path, "JPEG", quality=JPEG_QUALITY)

        ok, reason = validate_written_jpeg(out_path)
        if not ok:
            print(
                f"WARNING: dropping {relpath_forward_slash(out_path)}: {reason}",
                file=sys.stderr,
            )
            try:
                os.remove(out_path)
            except OSError:
                pass
            continue

        frame_paths.append(relpath_forward_slash(out_path))

    frame_paths.sort()

    if not frame_paths:
        return {
            "video": rel_video,
            "frames": [],
            "skip_reason": (
                "all extracted frames failed post-write validation "
                "(blank or corrupt)"
            ),
            "duration_s": duration_s,
        }

    return {
        "video": rel_video,
        "frames": frame_paths,
        "skip_reason": None,
        "duration_s": duration_s,
    }


def clear_out_dir():
    if not os.path.isdir(OUT_DIR):
        return
    for name in os.listdir(OUT_DIR):
        p = os.path.join(OUT_DIR, name)
        if os.path.isfile(p):
            os.remove(p)


def harvest():
    os.makedirs(OUT_DIR, exist_ok=True)
    clear_out_dir()

    videos = find_videos()
    entries = []
    for path in videos:
        rel = relpath_forward_slash(path)
        print(f"Processing {rel} ...")
        entry = process_video(path)
        entries.append(entry)
        kept_n = len(entry["frames"])
        reason = entry["skip_reason"]
        suffix = f", skip_reason={reason!r}" if reason else ""
        print(f"  -> {kept_n} frame(s) kept{suffix}")

    entries.sort(key=lambda e: e["video"])

    os.makedirs(RECORDS_DIR, exist_ok=True)
    with open(VIDEO_FRAMES_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")

    total_frames = sum(len(e["frames"]) for e in entries)
    total_skipped = sum(1 for e in entries if e["skip_reason"])
    print(
        f"\nWrote {len(entries)} video entries ({total_frames} frame(s) "
        f"kept, {total_skipped} skipped) to {VIDEO_FRAMES_JSON}"
    )
    return 0


def fail(msg):
    print(f"VERIFY FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def verify():
    if not os.path.isfile(VIDEO_FRAMES_JSON):
        fail(f"{VIDEO_FRAMES_JSON} not found")

    with open(VIDEO_FRAMES_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    disk_videos = {relpath_forward_slash(p) for p in find_videos()}
    entry_videos = [e.get("video") for e in entries]
    entry_video_set = set(entry_videos)

    if len(entry_videos) != len(entry_video_set):
        seen = set()
        dupes = sorted({v for v in entry_videos if v in seen or seen.add(v)})
        fail(f"duplicate video entries in {VIDEO_FRAMES_JSON}: {dupes[:10]}")

    missing = disk_videos - entry_video_set
    if missing:
        fail(
            f"{len(missing)} mp4(s) on disk missing an entry, e.g. "
            f"{sorted(missing)[:10]}"
        )

    extra = entry_video_set - disk_videos
    if extra:
        fail(
            f"{len(extra)} entries reference mp4(s) not on disk, e.g. "
            f"{sorted(extra)[:10]}"
        )

    if not os.path.isfile(LEDGER_JSON):
        fail(f"{LEDGER_JSON} not found")
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        ledger_rows = json.load(f)
    ledger_ids = {r["id"] for r in ledger_rows}

    total_frames_listed = 0
    listed_frame_files = set()

    for e in entries:
        video = e.get("video")
        frames = e.get("frames", [])
        skip_reason = e.get("skip_reason")

        if not (1 <= len(frames) <= 3) and skip_reason is None:
            fail(
                f"{video}: has {len(frames)} frame(s) and null skip_reason "
                f"(need 1-3 frames or a non-null skip_reason)"
            )

        if skip_reason is not None and frames:
            fail(f"{video}: has skip_reason set but frames list is non-empty")

        for frel in frames:
            total_frames_listed += 1
            listed_frame_files.add(frel)
            abs_frame = os.path.join(REPO_ROOT, frel.replace("/", os.sep))
            if not os.path.isfile(abs_frame):
                fail(f"{video}: listed frame file does not exist: {frel}")
                continue
            try:
                with Image.open(abs_frame) as im:
                    im.load()
            except Exception as exc:
                fail(
                    f"{video}: listed frame file failed to decode: "
                    f"{frel} ({exc})"
                )
            if frel not in ledger_ids:
                fail(f"{video}: listed frame {frel} has no row in {LEDGER_JSON}")

    disk_frame_files = set()
    if os.path.isdir(OUT_DIR):
        for name in os.listdir(OUT_DIR):
            p = os.path.join(OUT_DIR, name)
            if os.path.isfile(p):
                disk_frame_files.add(relpath_forward_slash(p))

    stray = disk_frame_files - listed_frame_files
    if stray:
        fail(
            f"{len(stray)} frame file(s) on disk not listed in "
            f"{VIDEO_FRAMES_JSON}, e.g. {sorted(stray)[:10]}"
        )

    result = subprocess.run(
        [sys.executable, BUILD_LEDGER_SCRIPT, "--verify"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        fail(f"ledger --verify failed (exit {result.returncode})")

    print(
        f"FRAMES VERIFY OK: {len(entries)} videos, {total_frames_listed} frames"
    )
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify", action="store_true", help="Verify results against disk"
    )
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify())
    else:
        sys.exit(harvest())


if __name__ == "__main__":
    main()
