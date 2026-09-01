#!/usr/bin/env python
"""Reusable validator: fail if any image file under <dir> is empty, too small
(and not allowlisted), or fails to open+decode via Pillow.

Usage:
    python scripts/check_no_empty.py <dir> [--min-bytes N] [--allowlist FILE]
        [--expect-count-from FILE --expect-count-key KEY]
"""

import argparse
import json
import os
import sys

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def find_image_files(root):
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                files.append(os.path.join(dirpath, name))
    return files


def relpath_forward_slash(path, root):
    rel = os.path.relpath(path, root)
    return rel.replace(os.sep, "/")


def main():
    parser = argparse.ArgumentParser(
        description="Validate that no image files under <dir> are empty, "
        "undersized, or undecodable."
    )
    parser.add_argument("dir", help="Directory to walk recursively")
    parser.add_argument(
        "--min-bytes",
        type=int,
        default=None,
        help="Minimum acceptable file size in bytes (beyond the 0-byte check)",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help="JSON file containing an array of relative (forward-slash) paths "
        "exempt from the --min-bytes rule",
    )
    parser.add_argument(
        "--expect-count-from",
        default=None,
        help="JSON file to read an expected file count from",
    )
    parser.add_argument(
        "--expect-count-key",
        default=None,
        help="Key within --expect-count-from whose integer value is the "
        "expected file count",
    )
    args = parser.parse_args()

    root = args.dir

    if not os.path.isdir(root):
        print(f"FAIL: not a directory: {root}")
        return 1

    allowlist = set()
    if args.allowlist:
        with open(args.allowlist, "r", encoding="utf-8") as f:
            allowlist_data = json.load(f)
        if not isinstance(allowlist_data, list):
            print(f"FAIL: allowlist file {args.allowlist} does not contain a JSON array")
            return 1
        allowlist = set(allowlist_data)

    files = find_image_files(root)

    failures = []

    for path in sorted(files):
        rel = relpath_forward_slash(path, root)
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            failures.append((rel, f"could not stat file: {exc}"))
            continue

        if size == 0:
            failures.append((rel, "file is 0 bytes"))
            continue

        if args.min_bytes is not None and size < args.min_bytes and rel not in allowlist:
            failures.append(
                (rel, f"file is {size} bytes, below --min-bytes {args.min_bytes} "
                      f"and not in allowlist")
            )
            continue

        try:
            with Image.open(path) as im:
                im.load()
        except Exception as exc:
            failures.append((rel, f"failed to open/decode: {exc}"))
            continue

    if args.expect_count_from:
        with open(args.expect_count_from, "r", encoding="utf-8") as f:
            expect_data = json.load(f)
        if args.expect_count_key is None:
            print("FAIL: --expect-count-key is required when --expect-count-from is given")
            return 1
        expected = expect_data.get(args.expect_count_key) if isinstance(expect_data, dict) else None
        if expected is None:
            print(
                f"FAIL: key '{args.expect_count_key}' missing or null in "
                f"{args.expect_count_from}"
            )
            return 1
        if not isinstance(expected, int):
            print(
                f"FAIL: key '{args.expect_count_key}' in {args.expect_count_from} "
                f"is not an integer: {expected!r}"
            )
            return 1
        if len(files) != expected:
            print(
                f"FAIL: walked file count {len(files)} does not equal expected "
                f"count {expected} (from {args.expect_count_from}#{args.expect_count_key})"
            )
            return 1

    if failures:
        print(f"FAIL: {len(failures)} offending file(s):")
        for rel, reason in failures:
            print(f"  {rel}: {reason}")
        return 1

    print(f"OK: {len(files)} files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
