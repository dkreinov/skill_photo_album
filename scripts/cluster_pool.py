#!/usr/bin/env python
"""Cluster the candidate pool + technical scores + thumbnails (Step 2.3).

POOL = ledger rows (records/ledger.json) with source "gphotos" PLUS rows
with source "generated" whose id starts with
"assets/generated/video_frames/" (chatgpt/v1 rows and any other generated
rows are excluded).

For every pool image this script:
  - orders the pool by exif_time, falling back to a YYYYMMDD_HHMMSS parsed
    from the filename (video frames: stem before "_t", plus the "_tSSS"
    seconds offset); items with neither time source sort to the end, by id.
  - clusters images into bursts/near-duplicates: join two images if their
    time gap is <=8s OR their 64-bit pHash Hamming distance is <=10. All
    frames of one video are force-joined into one initial group first; that
    group only merges into another cluster via the pHash<=10 rule (video
    frame timestamps are derived/approximate, so they are not used to join
    across the video/photo boundary -- see RESEARCH.md ordering note and the
    step-2.3 spec, which states the video-frame merge rule as pHash-only).
  - splits any resulting cluster whose time span exceeds 15 minutes, cutting
    at the largest internal time gap(s) until every piece spans <=15min.
  - computes technical scores (Laplacian-variance blur, % clipped pixels) on
    a 1024px-long-edge EXIF-transposed thumbnail of every pool image, and
    writes that thumbnail to cache/thumbs/.
  - picks each cluster's representative as its highest-blur member.

Outputs:
    records/clusters.json    -- burst/near-dup clusters
    records/tech_scores.json -- per-image technical scores + thumbnail path
    cache/thumbs/*.jpg       -- 1024px-long-edge JPEG q85 thumbnails

Usage:
    python scripts/cluster_pool.py            # build clusters + scores + thumbs
    python scripts/cluster_pool.py --verify   # verify outputs against the ledger
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS_DIR = os.path.join(REPO_ROOT, "records")
LEDGER_JSON = os.path.join(RECORDS_DIR, "ledger.json")
CLUSTERS_JSON = os.path.join(RECORDS_DIR, "clusters.json")
TECH_SCORES_JSON = os.path.join(RECORDS_DIR, "tech_scores.json")
CACHE_DIR = os.path.join(REPO_ROOT, "cache")
THUMBS_DIR = os.path.join(CACHE_DIR, "thumbs")

VIDEO_FRAME_PREFIX = "assets/generated/video_frames/"

TIME_GAP_SECONDS = 8
PHASH_MAX_DIST = 10
SPLIT_SPAN_SECONDS = 15 * 60
THUMB_LONG_EDGE = 1024
THUMB_QUALITY = 85
CLIP_LOW = 2
CLIP_HIGH = 253

# Matches a leading YYYYMMDD_HHMMSS, optionally followed by a video-frame
# "_tSSS_v<n>" suffix (SSS = seconds offset from the base timestamp). Uses
# match() (not fullmatch()) so trailing junk like "(0)" or "_Untappd" after
# the timestamp doesn't block the match.
FNAME_TIME_RE = re.compile(r"^(\d{8}_\d{6})(?:_t(\d+)_v\d+)?")


def fail(msg):
    print(f"VERIFY FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_ledger():
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def is_pool_row(row):
    if row["source"] == "gphotos":
        return True
    if row["source"] == "generated" and row["id"].startswith(VIDEO_FRAME_PREFIX):
        return True
    return False


def load_pool():
    return [r for r in load_ledger() if is_pool_row(r)]


def is_video_frame(row):
    return row["source"] == "generated"


def video_key(row):
    """Group key shared by all frames extracted from the same source video."""
    stem = os.path.splitext(os.path.basename(row["id"]))[0]
    m = FNAME_TIME_RE.match(stem)
    return m.group(1) if m else stem


def effective_time(row):
    """The timestamp used for ordering/clustering, or None if unknown."""
    if row.get("exif_time"):
        return datetime.fromisoformat(row["exif_time"])
    stem = os.path.splitext(os.path.basename(row["id"]))[0]
    m = FNAME_TIME_RE.match(stem)
    if not m:
        return None
    base = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    if m.group(2):
        base += timedelta(seconds=int(m.group(2)))
    return base


def order_key(row):
    """Sort key implementing: exif_time, then filename-parsed time, then
    (for items with neither) end-of-list ordered by id."""
    t = row.get("_t")
    if t is None:
        return (1, datetime.max, row["id"])
    return (0, t, row["id"])


def hamming(hex_a, hex_b):
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")


def flatten_id(pool_id):
    """assets/real_full/foo.jpg -> assets__real_full__foo.jpg (always .jpg,
    since thumbnails are always written as JPEG regardless of source
    format)."""
    base = os.path.splitext(pool_id)[0]
    return base.replace("/", "__") + ".jpg"


class DSU:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def build_initial_groups(pool):
    """Union-find clustering: time gap <=8s OR pHash Hamming <=10, with all
    frames of one video force-joined first, and (per spec) video-frame
    merges into any other cluster judged by pHash only."""
    dsu = DSU([r["id"] for r in pool])

    video_groups = defaultdict(list)
    for r in pool:
        if is_video_frame(r):
            video_groups[video_key(r)].append(r)
    for members in video_groups.values():
        base_id = members[0]["id"]
        for m in members[1:]:
            dsu.union(base_id, m["id"])

    n = len(pool)
    for i in range(n):
        ri = pool[i]
        for j in range(i + 1, n):
            rj = pool[j]
            if hamming(ri["phash"], rj["phash"]) <= PHASH_MAX_DIST:
                dsu.union(ri["id"], rj["id"])
                continue
            if not is_video_frame(ri) and not is_video_frame(rj):
                if ri["_t"] is not None and rj["_t"] is not None:
                    gap = abs((ri["_t"] - rj["_t"]).total_seconds())
                    if gap <= TIME_GAP_SECONDS:
                        dsu.union(ri["id"], rj["id"])

    groups = defaultdict(list)
    for r in pool:
        groups[dsu.find(r["id"])].append(r)
    return list(groups.values())


def split_by_time(members):
    """Split one cluster's members into pieces each spanning <=15min,
    cutting at the largest internal time gap and recursing. Members with no
    effective time can't be placed on the timeline (this never happens in
    the current pool, since no image lacking a time also matches another
    image only via phash into a >15min-spanning cluster); defensively, any
    such member is attached to the earliest piece."""
    timed = sorted((m for m in members if m["_t"] is not None), key=lambda m: m["_t"])
    untimed = [m for m in members if m["_t"] is None]

    if not timed:
        return [list(members)]

    def recurse(chunk):
        if len(chunk) <= 1:
            return [chunk]
        span = (chunk[-1]["_t"] - chunk[0]["_t"]).total_seconds()
        if span <= SPLIT_SPAN_SECONDS:
            return [chunk]
        gaps = [
            (chunk[k + 1]["_t"] - chunk[k]["_t"]).total_seconds()
            for k in range(len(chunk) - 1)
        ]
        idx = gaps.index(max(gaps))
        return recurse(chunk[: idx + 1]) + recurse(chunk[idx + 1 :])

    pieces = recurse(timed)
    if untimed:
        pieces[0] = pieces[0] + untimed
    return pieces


def compute_thumb_and_scores(row):
    """Build the 1024px-long-edge EXIF-transposed thumbnail for one pool
    image, save it under cache/thumbs/, and compute its technical scores."""
    abs_path = os.path.join(REPO_ROOT, row["id"].replace("/", os.sep))
    with Image.open(abs_path) as im:
        im = ImageOps.exif_transpose(im)
        w, h = im.size
        long_edge = max(w, h)
        if long_edge > THUMB_LONG_EDGE:
            scale = THUMB_LONG_EDGE / long_edge
            new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
            im = im.resize(new_size, Image.LANCZOS)

        gray = np.array(im.convert("L"), dtype=np.uint8)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        clipped = int(np.count_nonzero((gray <= CLIP_LOW) | (gray >= CLIP_HIGH)))
        clip_pct = 100.0 * clipped / gray.size

        rgb = im.convert("RGB") if im.mode != "RGB" else im
        thumb_name = flatten_id(row["id"])
        thumb_abs = os.path.join(THUMBS_DIR, thumb_name)
        rgb.save(thumb_abs, "JPEG", quality=THUMB_QUALITY)

    thumb_rel = f"cache/thumbs/{thumb_name}"
    return blur, clip_pct, thumb_rel


def build_cluster_records(pool, tech_scores):
    for r in pool:
        r["_t"] = effective_time(r)

    raw_groups = build_initial_groups(pool)

    pieces = []
    for group in raw_groups:
        pieces.extend(split_by_time(group))

    records = []
    for piece in pieces:
        piece_sorted = sorted(piece, key=order_key)
        member_ids = [m["id"] for m in piece_sorted]
        rep = max(piece_sorted, key=lambda m: tech_scores[m["id"]]["blur"])["id"]
        times = [m["_t"] for m in piece_sorted if m["_t"] is not None]
        time_start = min(times).isoformat() if times else None
        time_end = max(times).isoformat() if times else None
        records.append(
            {
                "members": member_ids,
                "rep": rep,
                "time_start": time_start,
                "time_end": time_end,
            }
        )

    records.sort(key=lambda c: (c["time_start"] is None, c["time_start"] or ""))

    final = []
    for idx, rec in enumerate(records, start=1):
        final.append(
            {
                "cluster_id": f"c{idx:03d}",
                "members": rec["members"],
                "rep": rec["rep"],
                "time_start": rec["time_start"],
                "time_end": rec["time_end"],
            }
        )
    return final


def cmd_build():
    pool = load_pool()
    os.makedirs(THUMBS_DIR, exist_ok=True)

    tech_scores = {}
    for r in pool:
        blur, clip_pct, thumb_rel = compute_thumb_and_scores(r)
        tech_scores[r["id"]] = {
            "blur": blur,
            "clip_pct": clip_pct,
            "thumb": thumb_rel,
        }

    clusters = build_cluster_records(pool, tech_scores)

    os.makedirs(RECORDS_DIR, exist_ok=True)
    with open(CLUSTERS_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(clusters, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(TECH_SCORES_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(tech_scores, f, indent=2, ensure_ascii=False)
        f.write("\n")

    sizes = [len(c["members"]) for c in clusters]
    singletons = sum(1 for s in sizes if s == 1)
    largest = max(sizes) if sizes else 0
    print(
        f"Wrote {len(clusters)} clusters ({singletons} singletons, "
        f"largest={largest}) covering {len(pool)} images to {CLUSTERS_JSON} "
        f"and {TECH_SCORES_JSON}"
    )
    return 0


def cmd_verify():
    pool = load_pool()
    pool_ids = {r["id"] for r in pool}

    if not os.path.isfile(CLUSTERS_JSON):
        fail(f"clusters JSON not found: {CLUSTERS_JSON}")
    if not os.path.isfile(TECH_SCORES_JSON):
        fail(f"tech scores JSON not found: {TECH_SCORES_JSON}")

    with open(CLUSTERS_JSON, "r", encoding="utf-8") as f:
        clusters = json.load(f)
    with open(TECH_SCORES_JSON, "r", encoding="utf-8") as f:
        tech_scores = json.load(f)

    cluster_ids = [c.get("cluster_id") for c in clusters]
    if len(cluster_ids) != len(set(cluster_ids)):
        fail("duplicate cluster_id values in clusters.json")
    expected_ids = [f"c{idx:03d}" for idx in range(1, len(clusters) + 1)]
    if cluster_ids != expected_ids:
        fail(
            f"cluster_id values are not sequential starting at c001; "
            f"got e.g. {cluster_ids[:5]}"
        )

    seen = {}
    for c in clusters:
        members = c.get("members") or []
        if not members:
            fail(f"cluster {c.get('cluster_id')} has no members")
        for m in members:
            if m in seen:
                fail(
                    f"id {m!r} appears in more than one cluster "
                    f"({seen[m]} and {c.get('cluster_id')})"
                )
            seen[m] = c.get("cluster_id")
        if c.get("rep") not in members:
            fail(
                f"cluster {c.get('cluster_id')} rep {c.get('rep')!r} is not "
                f"one of its members"
            )

    missing = pool_ids - set(seen)
    if missing:
        fail(f"{len(missing)} pool id(s) missing from clusters.json, e.g. {sorted(missing)[:5]}")
    extra = set(seen) - pool_ids
    if extra:
        fail(f"{len(extra)} clustered id(s) are not in the current pool, e.g. {sorted(extra)[:5]}")

    for c in clusters:
        ts, te = c.get("time_start"), c.get("time_end")
        if (ts is None) != (te is None):
            fail(f"cluster {c.get('cluster_id')} has only one of time_start/time_end null")
        if ts is not None and te is not None:
            span = (datetime.fromisoformat(te) - datetime.fromisoformat(ts)).total_seconds()
            if span > SPLIT_SPAN_SECONDS:
                fail(f"cluster {c.get('cluster_id')} spans {span / 60:.1f} min > 15 min")

    for pid in pool_ids:
        entry = tech_scores.get(pid)
        if entry is None:
            fail(f"pool id {pid!r} missing from tech_scores.json")
            continue
        for key in ("blur", "clip_pct", "thumb"):
            if key not in entry:
                fail(f"tech_scores[{pid!r}] missing field {key!r}")
        thumb_rel = entry["thumb"]
        thumb_abs = os.path.join(REPO_ROOT, thumb_rel.replace("/", os.sep))
        if not os.path.isfile(thumb_abs):
            fail(f"thumb file for {pid!r} does not exist: {thumb_abs}")
        try:
            with Image.open(thumb_abs) as im:
                im.load()
        except Exception as e:
            fail(f"thumb file for {pid!r} failed to decode: {e}")

    extra_tech = set(tech_scores) - pool_ids
    if extra_tech:
        fail(
            f"{len(extra_tech)} tech_scores.json id(s) are not in the "
            f"current pool, e.g. {sorted(extra_tech)[:5]}"
        )

    sizes = [len(c.get("members") or []) for c in clusters]
    largest = max(sizes) if sizes else 0
    print(f"CLUSTER VERIFY OK: {len(pool_ids)} images, {len(clusters)} clusters, largest={largest}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="verify clusters.json/tech_scores.json"
    )
    args = parser.parse_args()

    if args.verify:
        sys.exit(cmd_verify())
    else:
        sys.exit(cmd_build())


if __name__ == "__main__":
    main()
