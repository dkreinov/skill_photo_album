#!/usr/bin/env python3
"""
scripts/triage_batches.py

Step 2.4 — Triage protocol + batches.

Builds everything the vision judges need, frozen on disk:
  - records/triage/PROTOCOL.md      the frozen judge prompt
  - records/triage/batch_NNN.json   one file per batch of clusters to judge

Modes
-----
(no flags)         Generate PROTOCOL.md and batch_NNN.json from
                    records/clusters.json + records/tech_scores.json.
--verify            Structural check of the generated batches + protocol.
--verify-results    Check the judges' records/triage/result_batch_NNN.json
                    files against the output contract (run after judging).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDS_DIR = REPO_ROOT / "records"
TRIAGE_DIR = RECORDS_DIR / "triage"
CLUSTERS_PATH = RECORDS_DIR / "clusters.json"
TECH_SCORES_PATH = RECORDS_DIR / "tech_scores.json"
PROTOCOL_PATH = TRIAGE_DIR / "PROTOCOL.md"

BATCH_SIZE = 8
SEED = 42
AXES = ("moment", "story", "uniqueness", "technical")

PROTOCOL_TEXT = """\
# {{PROJECT}} Family Album -- Cluster Triage Protocol

## Role

You are a photo editor triaging photo clusters for a family photo album covering
a short family trip (five days): an amusement park, a science centre, old town & river, the park lakes, and the salt mine.

## Judging law

> Candid family moments beat postcard scenery. People and moments beat places. Candid beats posed. A slightly soft photo of a great moment outranks a sharp photo of nothing.

Apply this law to every judgment you make below.

## Chapters (context only)

These exist only to help you read the trip's arc. Do not sort, file, or score
images against a chapter -- they are background, not a rubric axis.

1. Departure / first evening
2. amusement park
3. science centre
4. old town & river
5. lake / games / park
6. salt mine
7. Final afternoon & ending

## Task -- per cluster

For every cluster in the batch:

1. View every image supplied for that cluster.
2. Choose `best_member`: the id of the single image that best represents the
   cluster's best moment.
3. Score the cluster's best moment on four axes, each an integer 1-5:
   - `moment` -- emotion / expression / story
   - `story` -- what it tells about the trip
   - `uniqueness` -- vs. typical trip photos
   - `technical` -- sharpness / exposure / composition
4. Set `keep_flag` (boolean): true if this moment belongs in album consideration.
5. Optional: when the moment is strong but the pixels are weak, set
   `needs_enhancement: true` and add a one-line `enhancement_note`
   (e.g. "sharpen faces", "lift shadows").
6. Write a one-line `reason` for your verdict.

## Blindness rule

You know nothing about any previous album version. You see no scores, verdicts,
or notes from any other judge, and no results from any other batch or pass.
Judge only the images placed in front of you, for this cluster, right now.

## Output contract

For batch `NNN`, write your verdicts to the absolute path given as
`result_path` in that batch's file (`records/triage/result_batch_NNN.json`).
The file must be valid JSON and contain nothing else:

```json
{
  "batch": "NNN",
  "verdicts": [
    {
      "cluster_id": "...",
      "best_member": "...",
      "moment": 1,
      "story": 1,
      "uniqueness": 1,
      "technical": 1,
      "keep_flag": true,
      "needs_enhancement": false,
      "enhancement_note": "...",
      "reason": "..."
    }
  ]
}
```

Write exactly one verdict object per cluster in the batch, in any order.
`needs_enhancement` and `enhancement_note` are optional -- omit them entirely
when they do not apply.
"""


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def batch_id(n: int) -> str:
    return f"{n:03d}"


def cluster_images(cluster: dict, tech: dict) -> list[dict]:
    """rep first, then up to 2 additional members with the highest blur scores."""
    rep = cluster["rep"]
    others = [m for m in cluster["members"] if m != rep]
    others_sorted = sorted(others, key=lambda m: tech[m]["blur"], reverse=True)
    chosen = [rep] + others_sorted[:2]
    images = []
    for member_id in chosen:
        thumb_rel = tech[member_id]["thumb"]
        thumb_abs = str((REPO_ROOT / thumb_rel).resolve())
        images.append({"id": member_id, "thumb": thumb_abs})
    return images


# --------------------------------------------------------------------------
# generate
# --------------------------------------------------------------------------

def cmd_generate() -> int:
    clusters = load_json(CLUSTERS_PATH)
    tech = load_json(TECH_SCORES_PATH)

    cluster_ids = [c["cluster_id"] for c in clusters]
    if len(cluster_ids) != len(set(cluster_ids)):
        print("ERROR: duplicate cluster_id in records/clusters.json", file=sys.stderr)
        return 1

    order = list(range(len(clusters)))
    random.Random(SEED).shuffle(order)
    shuffled = [clusters[i] for i in order]

    chunks = [shuffled[i:i + BATCH_SIZE] for i in range(0, len(shuffled), BATCH_SIZE)]

    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)

    total_images = 0
    for n, chunk in enumerate(chunks, start=1):
        nnn = batch_id(n)
        batch_path = TRIAGE_DIR / f"batch_{nnn}.json"
        result_path = TRIAGE_DIR / f"result_batch_{nnn}.json"

        cluster_entries = []
        for c in chunk:
            images = cluster_images(c, tech)
            total_images += len(images)
            cluster_entries.append({
                "cluster_id": c["cluster_id"],
                "images": images,
            })

        batch_obj = {
            "batch": nnn,
            "result_path": str(result_path.resolve()),
            "clusters": cluster_entries,
        }
        dump_json(batch_path, batch_obj)

    with open(PROTOCOL_PATH, "w", encoding="utf-8") as f:
        f.write(PROTOCOL_TEXT)

    print(
        f"GENERATED: {len(clusters)} clusters -> {len(chunks)} batches, "
        f"{total_images} images referenced"
    )
    return 0


# --------------------------------------------------------------------------
# --verify
# --------------------------------------------------------------------------

def cmd_verify() -> int:
    violations: list[str] = []

    if not CLUSTERS_PATH.exists():
        print(f"ERROR: {CLUSTERS_PATH} not found", file=sys.stderr)
        return 1
    clusters = load_json(CLUSTERS_PATH)
    all_cluster_ids = {c["cluster_id"] for c in clusters}

    batch_files = sorted(TRIAGE_DIR.glob("batch_*.json"))
    if not batch_files:
        violations.append("no batch_*.json files found in records/triage/")

    # batch numbering sequential
    expected_nums = [batch_id(i) for i in range(1, len(batch_files) + 1)]
    found_nums = []
    for p in batch_files:
        nnn = p.stem.split("_", 1)[1]
        found_nums.append(nnn)
    if found_nums != expected_nums:
        violations.append(
            f"batch numbering not sequential: found {found_nums}, expected {expected_nums}"
        )

    seen_cluster_ids: dict[str, str] = {}
    for p in batch_files:
        try:
            obj = load_json(p)
        except Exception as e:
            violations.append(f"{p.name}: invalid JSON ({e})")
            continue

        for centry in obj.get("clusters", []):
            cid = centry.get("cluster_id")
            if cid in seen_cluster_ids:
                violations.append(
                    f"cluster {cid} appears in both {seen_cluster_ids[cid]} and {p.name}"
                )
            else:
                seen_cluster_ids[cid] = p.name

            for img in centry.get("images", []):
                thumb = img.get("thumb", "")
                if not Path(thumb).is_absolute():
                    violations.append(
                        f"{p.name}: cluster {cid} image {img.get('id')} thumb not absolute: {thumb}"
                    )
                elif not Path(thumb).exists():
                    violations.append(
                        f"{p.name}: cluster {cid} image {img.get('id')} thumb missing: {thumb}"
                    )

    missing_clusters = all_cluster_ids - set(seen_cluster_ids)
    if missing_clusters:
        violations.append(
            f"{len(missing_clusters)} clusters missing from any batch: "
            f"{sorted(missing_clusters)[:10]}{'...' if len(missing_clusters) > 10 else ''}"
        )

    if not PROTOCOL_PATH.exists() or PROTOCOL_PATH.stat().st_size == 0:
        violations.append("records/triage/PROTOCOL.md missing or empty")
    else:
        text = PROTOCOL_PATH.read_text(encoding="utf-8")
        for axis in AXES:
            if axis not in text:
                violations.append(f"PROTOCOL.md missing axis name: {axis}")
        if "result_batch" not in text:
            violations.append("PROTOCOL.md missing 'result_batch'")

    if violations:
        print(f"BATCHES VERIFY FAILED: {len(violations)} violation(s)", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print(f"BATCHES VERIFY OK: {len(all_cluster_ids)} clusters, {len(batch_files)} batches")
    return 0


# --------------------------------------------------------------------------
# --verify-results
# --------------------------------------------------------------------------

def cmd_verify_results() -> int:
    violations: list[str] = []

    if not CLUSTERS_PATH.exists():
        print(f"ERROR: {CLUSTERS_PATH} not found", file=sys.stderr)
        return 1
    clusters = load_json(CLUSTERS_PATH)
    members_by_cluster = {c["cluster_id"]: set(c["members"]) for c in clusters}

    batch_files = sorted(TRIAGE_DIR.glob("batch_*.json"))
    if not batch_files:
        print("ERROR: no batch_*.json files found in records/triage/", file=sys.stderr)
        return 1

    total_verdicts = 0
    n_batches = 0

    for p in batch_files:
        try:
            batch_obj = load_json(p)
        except Exception as e:
            violations.append(f"{p.name}: invalid JSON ({e})")
            continue

        nnn = batch_obj.get("batch")
        result_path = Path(batch_obj.get("result_path", ""))
        batch_cluster_ids = [c["cluster_id"] for c in batch_obj.get("clusters", [])]

        if not result_path.exists():
            violations.append(f"batch {nnn}: result file missing: {result_path}")
            continue

        n_batches += 1

        try:
            result_obj = load_json(result_path)
        except Exception as e:
            violations.append(f"{result_path.name}: invalid JSON ({e})")
            continue

        if result_obj.get("batch") != nnn:
            violations.append(
                f"{result_path.name}: batch field {result_obj.get('batch')!r} != {nnn!r}"
            )

        verdicts = result_obj.get("verdicts")
        if not isinstance(verdicts, list):
            violations.append(f"{result_path.name}: 'verdicts' is not a list")
            continue

        seen_in_batch: dict[str, int] = {}
        for v in verdicts:
            cid = v.get("cluster_id")
            seen_in_batch[cid] = seen_in_batch.get(cid, 0) + 1

            if cid not in batch_cluster_ids:
                violations.append(
                    f"{result_path.name}: verdict cluster_id {cid!r} not in batch {nnn}"
                )
                continue

            valid_members = members_by_cluster.get(cid, set())
            best_member = v.get("best_member")
            if best_member not in valid_members:
                violations.append(
                    f"{result_path.name}: cluster {cid} best_member {best_member!r} "
                    f"not in cluster members"
                )

            for axis in AXES:
                score = v.get(axis)
                if not isinstance(score, int) or isinstance(score, bool) or not (1 <= score <= 5):
                    violations.append(
                        f"{result_path.name}: cluster {cid} axis {axis!r} invalid score {score!r}"
                    )

            keep_flag = v.get("keep_flag")
            if not isinstance(keep_flag, bool):
                violations.append(
                    f"{result_path.name}: cluster {cid} keep_flag not bool: {keep_flag!r}"
                )

            if "needs_enhancement" in v and not isinstance(v["needs_enhancement"], bool):
                violations.append(
                    f"{result_path.name}: cluster {cid} needs_enhancement not bool: "
                    f"{v['needs_enhancement']!r}"
                )
            if "enhancement_note" in v:
                note = v["enhancement_note"]
                if not isinstance(note, str) or not note.strip() or "\n" in note:
                    violations.append(
                        f"{result_path.name}: cluster {cid} enhancement_note malformed: {note!r}"
                    )

            reason = v.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                violations.append(
                    f"{result_path.name}: cluster {cid} reason missing/empty"
                )

            total_verdicts += 1

        for cid in batch_cluster_ids:
            count = seen_in_batch.get(cid, 0)
            if count != 1:
                violations.append(
                    f"{result_path.name}: cluster {cid} has {count} verdicts (expected 1)"
                )

    if violations:
        print(f"RESULTS VERIFY FAILED: {len(violations)} violation(s)", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print(f"RESULTS VERIFY OK: {n_batches} batches, {total_verdicts} verdicts")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify generated batches/protocol")
    parser.add_argument("--verify-results", action="store_true", help="verify judges' result files")
    args = parser.parse_args()

    if args.verify and args.verify_results:
        parser.error("choose only one of --verify / --verify-results")

    if args.verify:
        return cmd_verify()
    if args.verify_results:
        return cmd_verify_results()
    return cmd_generate()


if __name__ == "__main__":
    sys.exit(main())
