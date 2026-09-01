#!/usr/bin/env python
"""Build the frozen asset ledger (contract C7).

Walks assets/ recursively for image files (jpg/jpeg/png/heic/webp, case
insensitive; videos and other non-image files are excluded) and writes
records/ledger.json and records/ledger.csv, one row per image, sorted by id.

Usage:
    python scripts/build_ledger.py            # build the ledger
    python scripts/build_ledger.py --verify   # verify ledger matches disk
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime

import pillow_heif
from PIL import Image, ImageOps
import imagehash

pillow_heif.register_heif_opener()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(REPO_ROOT, "assets")
RECORDS_DIR = os.path.join(REPO_ROOT, "records")
LEDGER_JSON = os.path.join(RECORDS_DIR, "ledger.json")
LEDGER_CSV = os.path.join(RECORDS_DIR, "ledger.csv")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# Order matters only for readability; matching is by prefix so the first
# match wins (none of these prefixes are prefixes of each other, so order
# is not actually load-bearing).
SOURCE_PREFIX_MAP = [
    ("assets/v1_pages/", "v1"),
    ("assets/real_full/", "gphotos"),
    ("assets/chatgpt/convoA/", "chatgptA"),
    ("assets/chatgpt/convoB/", "chatgptB"),
    ("assets/generated/", "generated"),
]

FIELDS = ["id", "source", "w", "h", "exif_time", "phash", "bytes", "sha256"]

EXIF_DATETIME_ORIGINAL_TAG = 36867
EXIF_SUBIFD_TAG = 0x8769


def relpath_forward_slash(path, root=REPO_ROOT):
    rel = os.path.relpath(path, root)
    return rel.replace(os.sep, "/")


def find_image_files(root=ASSETS_DIR):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                files.append(os.path.join(dirpath, name))
    return files


def source_for_id(rel_id, abs_path):
    for prefix, source in SOURCE_PREFIX_MAP:
        if rel_id.startswith(prefix):
            return source
    print(
        f"ERROR: image file is not under a recognized source prefix "
        f"(assets/v1_pages/, assets/real_full/, assets/chatgpt/convoA/, "
        f"assets/chatgpt/convoB/, assets/generated/): {abs_path}",
        file=sys.stderr,
    )
    sys.exit(2)


def get_exif_datetime_original(im):
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
        # Validate it actually parses as a real timestamp.
        datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
        return iso
    except Exception:
        return None


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_row(abs_path):
    rel_id = relpath_forward_slash(abs_path)
    source = source_for_id(rel_id, abs_path)
    size_bytes = os.path.getsize(abs_path)
    digest = sha256_of(abs_path)

    with Image.open(abs_path) as im:
        exif_time = get_exif_datetime_original(im)
        oriented = ImageOps.exif_transpose(im)
        w, h = oriented.size
        phash = str(imagehash.phash(oriented))

    return {
        "id": rel_id,
        "source": source,
        "w": w,
        "h": h,
        "exif_time": exif_time,
        "phash": phash,
        "bytes": size_bytes,
        "sha256": digest,
    }


def write_ledger(rows):
    os.makedirs(RECORDS_DIR, exist_ok=True)

    with open(LEDGER_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(LEDGER_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build():
    paths = find_image_files()
    rows = [build_row(p) for p in paths]
    rows.sort(key=lambda r: r["id"])
    write_ledger(rows)
    print(f"Wrote {len(rows)} rows to {LEDGER_JSON} and {LEDGER_CSV}")
    return 0


def fail(msg):
    print(f"VERIFY FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def verify():
    if not os.path.isfile(LEDGER_JSON):
        fail(f"ledger JSON not found: {LEDGER_JSON}")

    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)

    expected_field_set = set(FIELDS)
    for row in rows:
        keys = set(row.keys())
        if keys != expected_field_set:
            fail(
                f"row {row.get('id')!r} has fields {sorted(keys)}, "
                f"expected exactly {sorted(expected_field_set)}"
            )

    disk_paths = find_image_files()
    disk_ids = {relpath_forward_slash(p) for p in disk_paths}
    ledger_ids = [r["id"] for r in rows]
    ledger_id_set = set(ledger_ids)

    if len(ledger_ids) != len(ledger_id_set):
        seen = set()
        dupes = sorted({i for i in ledger_ids if i in seen or seen.add(i)})
        fail(f"duplicate id(s) in ledger: {dupes[:10]}")

    if len(rows) != len(disk_paths):
        fail(
            f"row count {len(rows)} != current image-file count "
            f"{len(disk_paths)}"
        )

    missing_from_ledger = disk_ids - ledger_id_set
    if missing_from_ledger:
        fail(
            f"{len(missing_from_ledger)} file(s) on disk missing from "
            f"ledger, e.g. {sorted(missing_from_ledger)[:10]}"
        )

    missing_from_disk = ledger_id_set - disk_ids
    if missing_from_disk:
        fail(
            f"{len(missing_from_disk)} ledger row(s) missing from disk, "
            f"e.g. {sorted(missing_from_disk)[:10]}"
        )

    for row in rows:
        abs_path = os.path.join(REPO_ROOT, row["id"].replace("/", os.sep))
        digest = sha256_of(abs_path)
        if digest != row["sha256"]:
            fail(f"sha256 mismatch for {row['id']}")

    if not os.path.isfile(LEDGER_CSV):
        fail(f"ledger CSV not found: {LEDGER_CSV}")

    with open(LEDGER_CSV, "r", encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))

    if len(csv_rows) != len(rows):
        fail(f"CSV row count {len(csv_rows)} != JSON row count {len(rows)}")

    print(f"VERIFY OK: {len(rows)} rows")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify", action="store_true", help="Verify the ledger against disk"
    )
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify())
    else:
        sys.exit(build())


if __name__ == "__main__":
    main()
