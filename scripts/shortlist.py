#!/usr/bin/env python3
"""Step 2.6 -- Shortlist bands.

Reads triage verdicts (records/triage/result_batch_*.json), clusters
(records/clusters.json), tech scores (records/tech_scores.json) and v1 usage
(records/v1_usage.json) and produces records/shortlist.json: one row per
cluster with a band (auto-keep / auto-drop / contested), a sum4 score
(including the +1 incumbent bonus) and a near_twins list.

FROZEN rules -- see the Step 2.6 spec (P2-D3, D-001, amendment <DATE>):

1. sum4 = moment + story + uniqueness + technical, PLUS +1 incumbent bonus
   iff ANY member of the cluster appears in v1_usage.json's usage_by_id.
2. auto-keep = keep_flag AND sum4 >= 16
   auto-drop  = NOT keep_flag OR sum4 <= 9
   contested  = everything else
3. near_twin: for every pair of clusters BOTH in auto-keep or contested whose
   time ranges overlap or whose gap is <= 8 seconds, add each other's
   cluster_id to near_twins on both. Clusters with null time_start/time_end
   always get near_twins: [] and never match anything.

Usage:
    python scripts/shortlist.py            # build records/shortlist.json
    python scripts/shortlist.py --verify   # verify existing outputs
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRIAGE_DIR = REPO_ROOT / "records" / "triage"
CLUSTERS_PATH = REPO_ROOT / "records" / "clusters.json"
TECH_SCORES_PATH = REPO_ROOT / "records" / "tech_scores.json"
V1_USAGE_PATH = REPO_ROOT / "records" / "v1_usage.json"
SHORTLIST_PATH = REPO_ROOT / "records" / "shortlist.json"
DUELS_DIR = REPO_ROOT / "records" / "duels"
ROUND1_PATH = DUELS_DIR / "round_1.json"
PROTOCOL_PATH = DUELS_DIR / "PROTOCOL.md"
TRIAGE_PROTOCOL_PATH = TRIAGE_DIR / "PROTOCOL.md"

AUTO_KEEP = "auto-keep"
AUTO_DROP = "auto-drop"
CONTESTED = "contested"

GAP_SECONDS = 8


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_verdicts() -> list[dict]:
    verdicts: list[dict] = []
    for path in sorted(glob.glob(str(TRIAGE_DIR / "result_batch_*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        verdicts.extend(data["verdicts"])
    return verdicts


def load_clusters() -> dict[str, dict]:
    with open(CLUSTERS_PATH, encoding="utf-8") as fh:
        clusters = json.load(fh)
    return {c["cluster_id"]: c for c in clusters}


def load_incumbent_ids() -> set[str]:
    with open(V1_USAGE_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data["usage_by_id"].keys())


def load_tech_scores() -> dict[str, dict]:
    with open(TECH_SCORES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_sum4(verdict: dict, cluster: dict, incumbent_ids: set[str]) -> tuple[int, bool]:
    base = verdict["moment"] + verdict["story"] + verdict["uniqueness"] + verdict["technical"]
    incumbent = any(m in incumbent_ids for m in cluster["members"])
    return base + (1 if incumbent else 0), incumbent


def compute_band(keep_flag: bool, sum4: int) -> str:
    if keep_flag and sum4 >= 16:
        return AUTO_KEEP
    if (not keep_flag) or sum4 <= 9:
        return AUTO_DROP
    return CONTESTED


def ranges_match(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    a0, a1 = datetime.fromisoformat(a_start), datetime.fromisoformat(a_end)
    b0, b1 = datetime.fromisoformat(b_start), datetime.fromisoformat(b_end)
    if a0 <= b1 and b0 <= a1:
        return True  # overlap
    gap = (b0 - a1) if b0 > a1 else (a0 - b1)
    return gap.total_seconds() <= GAP_SECONDS


def compute_near_twins(rows: list[dict], clusters: dict[str, dict]) -> None:
    """Mutates rows in place, filling in near_twins."""
    pool = []
    for row in rows:
        if row["band"] not in (AUTO_KEEP, CONTESTED):
            continue
        c = clusters[row["cluster_id"]]
        if c["time_start"] is None or c["time_end"] is None:
            continue
        pool.append(row)

    for i in range(len(pool)):
        ci = clusters[pool[i]["cluster_id"]]
        for j in range(i + 1, len(pool)):
            cj = clusters[pool[j]["cluster_id"]]
            if ranges_match(ci["time_start"], ci["time_end"], cj["time_start"], cj["time_end"]):
                pool[i]["near_twins"].append(pool[j]["cluster_id"])
                pool[j]["near_twins"].append(pool[i]["cluster_id"])

    for row in rows:
        row["near_twins"].sort()


def build_shortlist() -> list[dict]:
    verdicts = load_verdicts()
    clusters = load_clusters()
    incumbent_ids = load_incumbent_ids()

    # Preserve canonical cluster order (c001, c002, ... as in clusters.json).
    verdict_by_id = {v["cluster_id"]: v for v in verdicts}
    rows = []
    for cluster_id in clusters:  # dict preserves insertion order == file order
        if cluster_id not in verdict_by_id:
            continue
        verdict = verdict_by_id[cluster_id]
        cluster = clusters[cluster_id]
        sum4, incumbent = compute_sum4(verdict, cluster, incumbent_ids)
        band = compute_band(verdict["keep_flag"], sum4)
        row = {
            "cluster_id": cluster_id,
            "band": band,
            "sum4": sum4,
            "incumbent": incumbent,
            "keep_flag": verdict["keep_flag"],
            "best_member": verdict["best_member"],
        }
        if verdict.get("needs_enhancement"):
            row["needs_enhancement"] = True
            row["enhancement_note"] = verdict.get("enhancement_note", "")
        row["reason"] = verdict["reason"]
        row["near_twins"] = []
        rows.append(row)

    compute_near_twins(rows, clusters)
    return rows


def print_histogram(rows: list[dict]) -> None:
    from collections import Counter

    band_counts = Counter(r["band"] for r in rows)
    sum4_counts = Counter(r["sum4"] for r in rows)

    print("BAND HISTOGRAM:")
    for band in (AUTO_KEEP, AUTO_DROP, CONTESTED):
        print(f"  {band}: {band_counts.get(band, 0)}")
    print("sum4 distribution:")
    dist = " ".join(f"{v}:{sum4_counts[v]}" for v in sorted(sum4_counts))
    print(f"  {dist}")


def run_build() -> None:
    rows = build_shortlist()
    SHORTLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SHORTLIST_PATH, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print_histogram(rows)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def fail(msg: str) -> None:
    print(f"SHORTLIST VERIFY FAILED: {msg}", file=sys.stderr)
    sys.exit(1)


def run_verify() -> None:
    if not SHORTLIST_PATH.exists():
        fail(f"missing {SHORTLIST_PATH}")
    if not ROUND1_PATH.exists():
        fail(f"missing {ROUND1_PATH}")
    if not PROTOCOL_PATH.exists():
        fail(f"missing {PROTOCOL_PATH}")

    with open(SHORTLIST_PATH, encoding="utf-8") as fh:
        shortlist = json.load(fh)
    with open(ROUND1_PATH, encoding="utf-8") as fh:
        round1 = json.load(fh)
    protocol_text = PROTOCOL_PATH.read_text(encoding="utf-8")

    verdicts = load_verdicts()
    clusters = load_clusters()
    incumbent_ids = load_incumbent_ids()

    # 1. every triage cluster in exactly one band
    triage_ids = [v["cluster_id"] for v in verdicts]
    if len(set(triage_ids)) != len(triage_ids):
        fail("duplicate cluster_id in triage verdicts")
    shortlist_by_id = {}
    for row in shortlist:
        cid = row["cluster_id"]
        if cid in shortlist_by_id:
            fail(f"cluster {cid} appears more than once in shortlist.json")
        shortlist_by_id[cid] = row
    if set(shortlist_by_id) != set(triage_ids):
        missing = set(triage_ids) - set(shortlist_by_id)
        extra = set(shortlist_by_id) - set(triage_ids)
        fail(f"shortlist/triage cluster set mismatch: missing={missing} extra={extra}")
    for cid, row in shortlist_by_id.items():
        if row["band"] not in (AUTO_KEEP, AUTO_DROP, CONTESTED):
            fail(f"cluster {cid} has invalid band {row['band']!r}")

    # 2. sum4 arithmetic correct incl. bonus (recompute)
    verdict_by_id = {v["cluster_id"]: v for v in verdicts}
    for cid, row in shortlist_by_id.items():
        verdict = verdict_by_id[cid]
        cluster = clusters[cid]
        expected_sum4, expected_incumbent = compute_sum4(verdict, cluster, incumbent_ids)
        if row["sum4"] != expected_sum4:
            fail(f"cluster {cid} sum4 mismatch: stored={row['sum4']} expected={expected_sum4}")
        if row["incumbent"] != expected_incumbent:
            fail(f"cluster {cid} incumbent mismatch: stored={row['incumbent']} expected={expected_incumbent}")
        expected_band = compute_band(verdict["keep_flag"], expected_sum4)
        if row["band"] != expected_band:
            fail(f"cluster {cid} band mismatch: stored={row['band']} expected={expected_band}")

    # 3. near_twins symmetric and empty for null-time clusters
    for cid, row in shortlist_by_id.items():
        cluster = clusters[cid]
        if cluster["time_start"] is None or cluster["time_end"] is None:
            if row["near_twins"] != []:
                fail(f"null-time cluster {cid} has non-empty near_twins {row['near_twins']}")
        for other in row["near_twins"]:
            if other not in shortlist_by_id:
                fail(f"cluster {cid} near_twins references unknown cluster {other}")
            if cid not in shortlist_by_id[other]["near_twins"]:
                fail(f"near_twins not symmetric between {cid} and {other}")

    near_twin_pairs = sum(len(r["near_twins"]) for r in shortlist) // 2

    # 4. round_1 covers all contested exactly once (+ at most one bye)
    contested_ids = {cid for cid, row in shortlist_by_id.items() if row["band"] == CONTESTED}
    seen_in_round1: list[str] = []
    thumbs_to_check: list[str] = []
    duel_ids_seen = set()
    for duel in round1:
        did = duel.get("duel_id")
        if did in duel_ids_seen:
            fail(f"duplicate duel_id {did} in round_1.json")
        duel_ids_seen.add(did)
        for side in ("a", "b"):
            if side not in duel:
                fail(f"duel {did} missing side {side!r}")
            side_obj = duel[side]
            cid = side_obj["cluster_id"]
            if cid not in contested_ids:
                fail(f"duel {did} side {side} references non-contested cluster {cid}")
            seen_in_round1.append(cid)
            thumbs_to_check.append(side_obj["thumb"])
        if "result_path" not in duel:
            fail(f"duel {did} missing result_path")

    if len(seen_in_round1) != len(set(seen_in_round1)):
        fail("a contested cluster appears more than once across round_1 duels")
    missing_from_round1 = contested_ids - set(seen_in_round1)
    if len(missing_from_round1) > 1:
        fail(f"more than one contested cluster missing from round_1: {missing_from_round1}")

    # 5. every thumb path in round_1 exists
    for thumb in thumbs_to_check:
        if not os.path.exists(thumb):
            fail(f"thumb path does not exist: {thumb}")

    # 6. PROTOCOL.md contains the judging-law line and "result_path"
    triage_protocol_text = TRIAGE_PROTOCOL_PATH.read_text(encoding="utf-8")
    judging_law_line = None
    for line in triage_protocol_text.splitlines():
        if line.strip().startswith(">"):
            judging_law_line = line.strip()
            break
    if judging_law_line is None:
        fail("could not locate judging-law line in triage PROTOCOL.md to compare against")
    if judging_law_line not in protocol_text:
        fail("duels PROTOCOL.md does not contain the judging-law line verbatim")
    if "result_path" not in protocol_text:
        fail("duels PROTOCOL.md does not contain 'result_path'")

    keep_n = sum(1 for r in shortlist if r["band"] == AUTO_KEEP)
    drop_n = sum(1 for r in shortlist if r["band"] == AUTO_DROP)
    contested_n = len(contested_ids)
    pairs_n = len(round1)

    print(
        f"SHORTLIST VERIFY OK: {keep_n} keep, {drop_n} drop, {contested_n} contested, "
        f"{near_twin_pairs} near-twin-pairs, {pairs_n} r1-pairs"
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Step 2.6 shortlist band builder")
    parser.add_argument("--verify", action="store_true", help="verify existing outputs instead of building")
    args = parser.parse_args()

    if args.verify:
        run_verify()
    else:
        run_build()


if __name__ == "__main__":
    main()
