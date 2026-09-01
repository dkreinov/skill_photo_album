#!/usr/bin/env python3
"""Step 2.6 -- Duel round builder.

Default action (no flags): builds records/duels/round_1.json and
records/duels/PROTOCOL.md from the contested band in records/shortlist.json.

FROZEN rule for round 1 (P2-D3, D-001, amendment <DATE>):

    round 1 = contested clusters sorted by sum4 desc, paired adjacent
    (1v2, 3v4, ...), odd one gets a bye; SHUFFLE who is A vs B within each
    pair with random.Random(42).

Tie-breaking within the sum4-desc sort is resolved by a stable sort over the
canonical cluster order (c001, c002, ... as they appear in records/clusters.json
/ records/shortlist.json), so the pairing is fully deterministic and
reproducible across runs.

The odd "bye" cluster (if any) is not written as a duel entry -- round_1.json
follows the frozen schema exactly (a list of {duel_id, a, b, result_path}
duel objects). Verification tolerates at most one contested cluster missing
from round_1.json, which is exactly the bye.

Step 2.7a adds the reversed re-run machinery for slim-margin round-1 results
(P2-D4 + duel protocol: every slim result gets a REVERSED re-run; agreement
on the same underlying cluster lets that winner stand, disagreement scores
0.5/0.5 for both clusters):

    --reversals   round_1.json + its results -> records/duels/reversals_r1.json
                  (one reversed duel per slim result; idempotent).
    --resolve     round_1.json + result_r1_*.json + result_r1rev_*.json ->
                  records/duels/r1_resolved.json (per-duel cluster outcome
                  scores; FAILS if a slim duel's reversal result is missing).
    --next-round  records/duels/r1_resolved.json -> records/duels/round_2.json
                  (Swiss-style: ALL clusters re-paired by score desc, sum4
                  desc, adjacent, A/B shuffled with random.Random(43)).
    --verify      state-aware: round_1/PROTOCOL checks always run; reversals /
                  resolved / round_2 checks only apply once those files exist.

Step 2.7b generalizes the reversal/resolve machinery to round 2 and adds
final standings (P2-D4):

    --reversals --round {1,2}   defaults to round 1 (backward compatible).
                  Round 2 reads round_2.json + result_r2_*.json and writes
                  records/duels/reversals_r2.json (ids r2rev_NNN, result
                  paths result_r2rev_NNN.json).
    --resolve --round {1,2}     Round 2 writes records/duels/r2_resolved.json
                  with the same outcome semantics as round 1.
    --standings   requires r1_resolved.json + r2_resolved.json; per contested
                  cluster, sums its outcome scores across both rounds (0,
                  0.5, 1, 1.5, or 2), ranks by (score desc, sum4 desc,
                  rep-blur desc, cluster_id asc), and writes
                  records/duels/final_standings.json.
    --verify      also state-aware for round 2 (reversals_r2 / r2_resolved),
                  and validates final_standings.json when present.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHORTLIST_PATH = REPO_ROOT / "records" / "shortlist.json"
TECH_SCORES_PATH = REPO_ROOT / "records" / "tech_scores.json"
CLUSTERS_PATH = REPO_ROOT / "records" / "clusters.json"
TRIAGE_PROTOCOL_PATH = REPO_ROOT / "records" / "triage" / "PROTOCOL.md"
DUELS_DIR = REPO_ROOT / "records" / "duels"
PROTOCOL_PATH = DUELS_DIR / "PROTOCOL.md"
ROUND1_PATH = DUELS_DIR / "round_1.json"
REVERSALS_R1_PATH = DUELS_DIR / "reversals_r1.json"
RESOLVED_R1_PATH = DUELS_DIR / "r1_resolved.json"
ROUND2_PATH = DUELS_DIR / "round_2.json"
REVERSALS_R2_PATH = DUELS_DIR / "reversals_r2.json"
RESOLVED_R2_PATH = DUELS_DIR / "r2_resolved.json"
FINAL_STANDINGS_PATH = DUELS_DIR / "final_standings.json"

CONTESTED = "contested"
SHUFFLE_SEED = 42
NEXT_ROUND_SHUFFLE_SEED = 43

# Per-round path/id-prefix bundles used by --reversals/--resolve/--verify so
# round 1 and round 2 share one implementation.
ROUND_PATHS = {
    1: {
        "round_path": ROUND1_PATH,
        "reversals_path": REVERSALS_R1_PATH,
        "resolved_path": RESOLVED_R1_PATH,
        "rev_prefix": "r1rev",
    },
    2: {
        "round_path": ROUND2_PATH,
        "reversals_path": REVERSALS_R2_PATH,
        "resolved_path": RESOLVED_R2_PATH,
        "rev_prefix": "r2rev",
    },
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_shortlist() -> list[dict]:
    with open(SHORTLIST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_tech_scores() -> dict[str, dict]:
    with open(TECH_SCORES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def thumb_for(tech_scores: dict[str, dict], member_id: str) -> str:
    rel = tech_scores[member_id]["thumb"]
    return str((REPO_ROOT / rel).resolve())


def load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_round1() -> list[dict]:
    return load_json(ROUND1_PATH)  # type: ignore[return-value]


def load_clusters() -> list[dict]:
    return load_json(CLUSTERS_PATH)  # type: ignore[return-value]


def write_json(path: Path, obj: object) -> None:
    DUELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Round 1 build
# ---------------------------------------------------------------------------

def make_side(row: dict, tech_scores: dict[str, dict]) -> dict:
    return {
        "cluster_id": row["cluster_id"],
        "best_member": row["best_member"],
        "thumb": thumb_for(tech_scores, row["best_member"]),
    }


def build_round1(shortlist: list[dict], tech_scores: dict[str, dict]) -> list[dict]:
    # Canonical order == order rows appear in shortlist.json (which mirrors
    # records/clusters.json order, i.e. c001, c002, ...).
    contested_rows = [r for r in shortlist if r["band"] == CONTESTED]
    ordered = sorted(contested_rows, key=lambda r: -r["sum4"])  # stable sort

    pairs: list[tuple[dict, dict]] = []
    i = 0
    while i + 1 < len(ordered):
        pairs.append((ordered[i], ordered[i + 1]))
        i += 2
    # if len(ordered) is odd, ordered[-1] is the bye and is simply omitted.

    rng = random.Random(SHUFFLE_SEED)
    duels = []
    for idx, (row_x, row_y) in enumerate(pairs, start=1):
        members = [row_x, row_y]
        rng.shuffle(members)
        row_a, row_b = members
        duel_id = f"r1_{idx:03d}"
        result_path = str((DUELS_DIR / f"result_{duel_id}.json").resolve())
        duels.append(
            {
                "duel_id": duel_id,
                "a": make_side(row_a, tech_scores),
                "b": make_side(row_b, tech_scores),
                "result_path": result_path,
            }
        )
    return duels


def build_protocol_md() -> str:
    triage_text = TRIAGE_PROTOCOL_PATH.read_text(encoding="utf-8")
    lines = triage_text.splitlines()

    def extract_section(header: str) -> str:
        start = None
        for i, line in enumerate(lines):
            if line.strip() == header:
                start = i
                break
        if start is None:
            raise RuntimeError(f"section {header!r} not found in triage PROTOCOL.md")
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break
        return "\n".join(lines[start:end]).rstrip() + "\n"

    role_section = extract_section("## Role")
    judging_law_section = extract_section("## Judging law")
    chapters_section = extract_section("## Chapters (context only)")

    task_section = (
        "## Task -- per duel\n\n"
        "For every duel:\n\n"
        "1. View image A and image B.\n"
        "2. Decide which single image belongs in the family album, applying the "
        "judging law above.\n"
        "3. Write your verdict as JSON to the absolute `result_path` given for "
        "this duel.\n"
    )

    blindness_section = (
        "## Blindness rule\n\n"
        "You know nothing else about this duel or any other: no scores, no bands, "
        "no sum4, no keep_flag, and no results or outcomes from any other duel or "
        "pass. Judge only the two images placed in front of you, for this duel, "
        "right now.\n"
    )

    output_section = (
        "## Output contract\n\n"
        "For duel `duel_id`, write your verdict to the absolute path given as "
        "`result_path` for that duel (`records/duels/result_r1_NNN.json`). The "
        "file must be valid JSON and contain nothing else:\n\n"
        "```json\n"
        "{\n"
        '  "duel_id": "...",\n'
        '  "winner": "a" | "b",\n'
        '  "margin": "clear" | "slim",\n'
        '  "reason": "<one line>"\n'
        "}\n"
        "```\n"
    )

    parts = [
        "# {{PROJECT}} Family Album -- Duel Judging Protocol\n",
        role_section,
        judging_law_section,
        chapters_section,
        task_section,
        blindness_section,
        output_section,
    ]
    return "\n".join(parts)


def run_build() -> None:
    if not SHORTLIST_PATH.exists():
        print(f"missing {SHORTLIST_PATH} -- run scripts/shortlist.py first", file=sys.stderr)
        sys.exit(1)

    shortlist = load_shortlist()
    tech_scores = load_tech_scores()

    DUELS_DIR.mkdir(parents=True, exist_ok=True)

    duels = build_round1(shortlist, tech_scores)
    round1_path = DUELS_DIR / "round_1.json"
    with open(round1_path, "w", encoding="utf-8") as fh:
        json.dump(duels, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    protocol_text = build_protocol_md()
    PROTOCOL_PATH.write_text(protocol_text, encoding="utf-8")

    contested_n = sum(1 for r in shortlist if r["band"] == CONTESTED)
    bye_n = contested_n - 2 * len(duels)
    print(f"round_1: {contested_n} contested -> {len(duels)} duels, bye={bye_n}")
    print(f"wrote {round1_path}")
    print(f"wrote {PROTOCOL_PATH}")


# ---------------------------------------------------------------------------
# --reversals -- reversed re-run duels for every slim round-N result
# ---------------------------------------------------------------------------

def build_reversals(round_duels: list[dict], rev_prefix: str, round_num: int) -> tuple[list[dict], list[str]]:
    """Returns (reversals, slim_duel_ids). Raises via sys.exit(1) (through the
    caller) if any round-N duel is missing its result -- we cannot tell which
    duels are slim without a complete result set.
    """
    missing = []
    reversals: list[dict] = []
    for duel in round_duels:
        did = duel["duel_id"]
        result_path = Path(duel["result_path"])
        if not result_path.exists():
            missing.append(did)
            continue
        result = load_json(result_path)
        if result.get("margin") != "slim":
            continue
        nnn = did.split("_", 1)[1]
        rev_id = f"{rev_prefix}_{nnn}"
        rev_result_path = str((DUELS_DIR / f"result_{rev_id}.json").resolve())
        reversals.append(
            {
                "duel_id": rev_id,
                "original_duel_id": did,
                "a": duel["b"],
                "b": duel["a"],
                "result_path": rev_result_path,
            }
        )
    if missing:
        print(
            f"cannot build reversals: missing result(s) for {len(missing)} round-{round_num} "
            f"duel(s): {missing[:10]}",
            file=sys.stderr,
        )
        sys.exit(1)
    return reversals, [r["original_duel_id"] for r in reversals]


def run_reversals(round_num: int = 1) -> None:
    paths = ROUND_PATHS[round_num]
    round_path = paths["round_path"]
    reversals_path = paths["reversals_path"]

    if not round_path.exists():
        print(f"missing {round_path} -- run scripts/duels.py first", file=sys.stderr)
        sys.exit(1)

    round_duels = load_json(round_path)
    reversals, slim_ids = build_reversals(round_duels, paths["rev_prefix"], round_num)
    write_json(reversals_path, reversals)
    print(
        f"reversals_r{round_num}: {len(slim_ids)} slim round-{round_num} result(s) -> "
        f"{len(reversals)} reversal duel(s)"
    )
    print(f"wrote {reversals_path}")


# ---------------------------------------------------------------------------
# --resolve -- combine round-1 + reversal results into per-cluster outcomes
# ---------------------------------------------------------------------------

def resolve_duel(duel: dict, result: dict, reversals_by_original: dict[str, dict]) -> tuple[dict, str | None]:
    """Returns (outcome_dict, missing_reversal_duel_id_or_None) for one
    original round-1 duel given its result and the reversals index.
    """
    cluster_a = duel["a"]["cluster_id"]
    cluster_b = duel["b"]["cluster_id"]
    margin = result.get("margin")
    winner_side = result.get("winner")

    if margin == "clear":
        outcome = {cluster_a: 0, cluster_b: 0}
        outcome[cluster_a if winner_side == "a" else cluster_b] = 1
        return outcome, None

    if margin == "slim":
        did = duel["duel_id"]
        rev = reversals_by_original.get(did)
        if rev is None:
            return {}, did
        rev_result_path = Path(rev["result_path"])
        if not rev_result_path.exists():
            return {}, did
        rev_result = load_json(rev_result_path)
        rev_winner_side = rev_result.get("winner")
        # reversal duel: a == original b, b == original a
        rev_winner_cluster = cluster_b if rev_winner_side == "a" else cluster_a
        orig_winner_cluster = cluster_a if winner_side == "a" else cluster_b
        if rev_winner_cluster == orig_winner_cluster:
            outcome = {cluster_a: 0, cluster_b: 0}
            outcome[orig_winner_cluster] = 1
        else:
            outcome = {cluster_a: 0.5, cluster_b: 0.5}
        return outcome, None

    print(f"duel {duel['duel_id']} has invalid margin {margin!r}", file=sys.stderr)
    sys.exit(1)


def run_resolve(round_num: int = 1) -> None:
    paths = ROUND_PATHS[round_num]
    round_path = paths["round_path"]
    reversals_path = paths["reversals_path"]
    resolved_path = paths["resolved_path"]

    if not round_path.exists():
        print(f"missing {round_path} -- run scripts/duels.py first", file=sys.stderr)
        sys.exit(1)
    if not reversals_path.exists():
        print(f"missing {reversals_path} -- run --reversals --round {round_num} first", file=sys.stderr)
        sys.exit(1)

    round_duels = load_json(round_path)
    reversals = load_json(reversals_path)
    reversals_by_original = {r["original_duel_id"]: r for r in reversals}

    missing_result = []
    missing_reversal = []
    resolved = []
    for duel in round_duels:
        did = duel["duel_id"]
        result_path = Path(duel["result_path"])
        if not result_path.exists():
            missing_result.append(did)
            continue
        result = load_json(result_path)
        outcome, missing_rev_id = resolve_duel(duel, result, reversals_by_original)
        if missing_rev_id is not None:
            missing_reversal.append(missing_rev_id)
            continue
        resolved.append(
            {
                "duel_id": did,
                "cluster_a": duel["a"]["cluster_id"],
                "cluster_b": duel["b"]["cluster_id"],
                "outcome": outcome,
            }
        )

    if missing_result:
        print(
            f"cannot resolve: missing round-{round_num} result(s) for {len(missing_result)} "
            f"duel(s): {missing_result[:10]}",
            file=sys.stderr,
        )
        sys.exit(1)
    if missing_reversal:
        print(
            f"cannot resolve: {len(missing_reversal)} slim duel(s) lack a reversal "
            f"result: {missing_reversal[:10]}",
            file=sys.stderr,
        )
        sys.exit(1)

    write_json(resolved_path, resolved)
    print(f"r{round_num}_resolved: {len(resolved)} round-{round_num} duel(s) resolved")
    print(f"wrote {resolved_path}")


# ---------------------------------------------------------------------------
# --verify (duels.py's own, structural check of round_1.json / PROTOCOL.md)
# ---------------------------------------------------------------------------

def _verify_round1_core() -> tuple[list[dict], list[str]]:
    """Existing (step-2.6) structural checks. Returns (duels, seen_clusters)
    on success; exits the process on any failure.
    """
    if not ROUND1_PATH.exists():
        print(f"missing {ROUND1_PATH}", file=sys.stderr)
        sys.exit(1)
    if not PROTOCOL_PATH.exists():
        print(f"missing {PROTOCOL_PATH}", file=sys.stderr)
        sys.exit(1)

    duels = load_round1()

    seen_ids = set()
    seen_clusters: list[str] = []
    for duel in duels:
        did = duel.get("duel_id")
        if not did or did in seen_ids:
            print(f"invalid or duplicate duel_id: {did}", file=sys.stderr)
            sys.exit(1)
        seen_ids.add(did)
        for side in ("a", "b"):
            side_obj = duel.get(side)
            if not side_obj or "cluster_id" not in side_obj or "thumb" not in side_obj:
                print(f"duel {did} malformed side {side!r}", file=sys.stderr)
                sys.exit(1)
            if not os.path.exists(side_obj["thumb"]):
                print(f"duel {did} side {side} thumb missing: {side_obj['thumb']}", file=sys.stderr)
                sys.exit(1)
            seen_clusters.append(side_obj["cluster_id"])
        if "result_path" not in duel:
            print(f"duel {did} missing result_path", file=sys.stderr)
            sys.exit(1)
    if len(seen_clusters) != len(set(seen_clusters)):
        print("a cluster appears more than once across round_1 duels", file=sys.stderr)
        sys.exit(1)

    protocol_text = PROTOCOL_PATH.read_text(encoding="utf-8")
    if "result_path" not in protocol_text:
        print("PROTOCOL.md missing 'result_path'", file=sys.stderr)
        sys.exit(1)

    return duels, seen_clusters


def _verify_reversals(duels: list[dict], reversals_path: Path, rev_prefix: str) -> int:
    """Structural check of a round's reversals_rN.json against that round's
    results. Does NOT require reversal result files to exist (that check
    only applies once the round's resolved file exists -- see
    _verify_resolved). Returns the reversal count, or 0 if reversals_path
    does not exist yet.
    """
    if not reversals_path.exists():
        return 0

    reversals = load_json(reversals_path)
    by_duel_id = {d["duel_id"]: d for d in duels}

    slim_duel_ids = set()
    for duel in duels:
        result_path = Path(duel["result_path"])
        if result_path.exists():
            result = load_json(result_path)
            if result.get("margin") == "slim":
                slim_duel_ids.add(duel["duel_id"])

    reversal_originals = {r.get("original_duel_id") for r in reversals}
    missing_rev = slim_duel_ids - reversal_originals
    if missing_rev:
        print(
            f"{reversals_path.name} missing entries for slim duel(s): {sorted(missing_rev)}",
            file=sys.stderr,
        )
        sys.exit(1)
    extra_rev = reversal_originals - slim_duel_ids
    if extra_rev:
        print(
            f"{reversals_path.name} has entries for non-slim/unknown duel(s): {sorted(extra_rev)}",
            file=sys.stderr,
        )
        sys.exit(1)

    seen_rev_ids = set()
    for r in reversals:
        rid = r.get("duel_id")
        oid = r.get("original_duel_id")
        if not rid or rid in seen_rev_ids:
            print(f"invalid or duplicate reversal duel_id: {rid}", file=sys.stderr)
            sys.exit(1)
        seen_rev_ids.add(rid)
        orig = by_duel_id.get(oid)
        if orig is None:
            print(f"reversal {rid} references unknown original duel {oid}", file=sys.stderr)
            sys.exit(1)
        expected_nnn = oid.split("_", 1)[1]
        if rid != f"{rev_prefix}_{expected_nnn}":
            print(f"reversal duel_id {rid} does not match expected {rev_prefix}_{expected_nnn}", file=sys.stderr)
            sys.exit(1)
        if (
            r.get("a", {}).get("cluster_id") != orig["b"]["cluster_id"]
            or r.get("b", {}).get("cluster_id") != orig["a"]["cluster_id"]
        ):
            print(f"reversal {rid} sides are not swapped relative to {oid}", file=sys.stderr)
            sys.exit(1)
        for side in ("a", "b"):
            side_obj = r.get(side)
            if not side_obj or "cluster_id" not in side_obj or "thumb" not in side_obj:
                print(f"reversal {rid} malformed side {side!r}", file=sys.stderr)
                sys.exit(1)
            if not os.path.exists(side_obj["thumb"]):
                print(f"reversal {rid} side {side} thumb missing: {side_obj['thumb']}", file=sys.stderr)
                sys.exit(1)
        expected_result_path = str((DUELS_DIR / f"result_{rid}.json").resolve())
        if r.get("result_path") != expected_result_path:
            print(f"reversal {rid} result_path mismatch", file=sys.stderr)
            sys.exit(1)

    return len(reversals)


def _verify_resolved(duels: list[dict], reversals_path: Path, resolved_path: Path, round_num: int) -> int:
    """Recomputes every resolved-round entry from round_N + result files +
    reversal results and checks it matches what's on disk. This is where the
    reversal RESULT-file existence check applies (per spec: only once the
    round's resolved file exists). Returns the resolved-duel count, or 0 if
    resolved_path does not exist yet.
    """
    if not resolved_path.exists():
        return 0

    resolved = load_json(resolved_path)
    by_duel_id = {d["duel_id"]: d for d in duels}
    reversals = load_json(reversals_path) if reversals_path.exists() else []
    reversals_by_original = {r["original_duel_id"]: r for r in reversals}

    for entry in resolved:
        did = entry.get("duel_id")
        orig = by_duel_id.get(did)
        if orig is None:
            print(f"r{round_num}_resolved entry references unknown duel {did}", file=sys.stderr)
            sys.exit(1)
        cluster_a = orig["a"]["cluster_id"]
        cluster_b = orig["b"]["cluster_id"]
        if entry.get("cluster_a") != cluster_a or entry.get("cluster_b") != cluster_b:
            print(f"r{round_num}_resolved entry {did} cluster_a/b mismatch with round_{round_num}.json", file=sys.stderr)
            sys.exit(1)

        result_path = Path(orig["result_path"])
        if not result_path.exists():
            print(f"r{round_num}_resolved entry {did}: round-{round_num} result file missing: {result_path}", file=sys.stderr)
            sys.exit(1)
        result = load_json(result_path)

        if result.get("margin") == "slim":
            rev = reversals_by_original.get(did)
            if rev is None:
                print(f"slim duel {did} has no reversal twin in {reversals_path.name}", file=sys.stderr)
                sys.exit(1)
            rev_result_path = Path(rev["result_path"])
            if not rev_result_path.exists():
                print(f"slim duel {did} reversal result missing: {rev_result_path}", file=sys.stderr)
                sys.exit(1)

        expected, missing_rev_id = resolve_duel(orig, result, reversals_by_original)
        if missing_rev_id is not None:
            print(f"slim duel {missing_rev_id} has no usable reversal result", file=sys.stderr)
            sys.exit(1)
        if entry.get("outcome") != expected:
            print(
                f"r{round_num}_resolved arithmetic mismatch for {did}: "
                f"got {entry.get('outcome')} expected {expected}",
                file=sys.stderr,
            )
            sys.exit(1)

    return len(resolved)


def _verify_round2() -> int:
    """Structural check of round_2.json (when present): valid duel schema,
    thumbs exist, and it covers exactly the contested clusters again (each
    exactly once, +/- one bye). Returns the round_2 duel count, or 0 if
    round_2.json does not exist yet.
    """
    if not ROUND2_PATH.exists():
        return 0

    r2_duels = load_json(ROUND2_PATH)
    seen_ids2 = set()
    seen_clusters2: list[str] = []
    for duel in r2_duels:
        did = duel.get("duel_id")
        if not did or did in seen_ids2:
            print(f"invalid or duplicate round_2 duel_id: {did}", file=sys.stderr)
            sys.exit(1)
        seen_ids2.add(did)
        for side in ("a", "b"):
            side_obj = duel.get(side)
            if not side_obj or "cluster_id" not in side_obj or "thumb" not in side_obj:
                print(f"round_2 duel {did} malformed side {side!r}", file=sys.stderr)
                sys.exit(1)
            if not os.path.exists(side_obj["thumb"]):
                print(f"round_2 duel {did} side {side} thumb missing: {side_obj['thumb']}", file=sys.stderr)
                sys.exit(1)
            seen_clusters2.append(side_obj["cluster_id"])
        if "result_path" not in duel:
            print(f"round_2 duel {did} missing result_path", file=sys.stderr)
            sys.exit(1)

    if len(seen_clusters2) != len(set(seen_clusters2)):
        print("a cluster appears more than once across round_2 duels", file=sys.stderr)
        sys.exit(1)

    shortlist = load_shortlist()
    contested_ids = {r["cluster_id"] for r in shortlist if r["band"] == CONTESTED}
    seen_set2 = set(seen_clusters2)
    extra_in_r2 = seen_set2 - contested_ids
    if extra_in_r2:
        print(f"round_2 references non-contested cluster(s): {sorted(extra_in_r2)}", file=sys.stderr)
        sys.exit(1)
    missing_from_r2 = contested_ids - seen_set2
    if len(missing_from_r2) > 1:
        print(
            f"round_2 missing {len(missing_from_r2)} contested cluster(s) "
            f"(more than one bye): {sorted(missing_from_r2)}",
            file=sys.stderr,
        )
        sys.exit(1)

    return len(r2_duels)


def _verify_standings() -> int:
    """Recomputes final_standings.json from r1_resolved.json + r2_resolved.json
    + shortlist/clusters/tech_scores and checks it matches what's on disk.
    build_standings() itself enforces full contested-cluster coverage
    (exactly once) and internal consistency, so calling it here doubles as
    that check. Returns the standings count, or 0 if final_standings.json
    does not exist yet.
    """
    if not FINAL_STANDINGS_PATH.exists():
        return 0

    if not RESOLVED_R1_PATH.exists() or not RESOLVED_R2_PATH.exists():
        print(
            "final_standings.json exists but r1_resolved.json/r2_resolved.json is missing",
            file=sys.stderr,
        )
        sys.exit(1)

    standings = load_json(FINAL_STANDINGS_PATH)
    resolved_r1 = load_json(RESOLVED_R1_PATH)
    resolved_r2 = load_json(RESOLVED_R2_PATH)
    shortlist = load_shortlist()
    clusters = load_clusters()
    tech_scores = load_tech_scores()

    expected = build_standings(resolved_r1, resolved_r2, shortlist, clusters, tech_scores)

    if len(standings) != len(expected):
        print(
            f"final_standings.json has {len(standings)} entries, expected {len(expected)}",
            file=sys.stderr,
        )
        sys.exit(1)
    for got, exp in zip(standings, expected):
        if got != exp:
            print(f"final_standings.json mismatch: got {got} expected {exp}", file=sys.stderr)
            sys.exit(1)

    return len(standings)


def run_verify() -> None:
    duels1, _seen_clusters = _verify_round1_core()
    rev1_count = _verify_reversals(duels1, REVERSALS_R1_PATH, "r1rev")
    resolved1_count = _verify_resolved(duels1, REVERSALS_R1_PATH, RESOLVED_R1_PATH, 1)
    r2_count = _verify_round2()

    rev2_count = 0
    resolved2_count = 0
    if ROUND2_PATH.exists():
        duels2 = load_json(ROUND2_PATH)
        rev2_count = _verify_reversals(duels2, REVERSALS_R2_PATH, "r2rev")
        resolved2_count = _verify_resolved(duels2, REVERSALS_R2_PATH, RESOLVED_R2_PATH, 2)

    standings_count = _verify_standings()

    print(
        f"DUELS VERIFY OK: R1 {resolved1_count} resolved, REV {rev1_count}, R2 {r2_count} pairs, "
        f"R2REV {rev2_count}, R2 {resolved2_count} resolved, STANDINGS {standings_count}"
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# --next-round (Swiss-style round 2 from r1_resolved.json cluster scores)
# ---------------------------------------------------------------------------

def build_round2(shortlist: list[dict], tech_scores: dict[str, dict], resolved: list[dict]) -> list[dict]:
    """Swiss-style pairing: every scored cluster (winners, losers, and 0.5s
    alike) advances to round 2. Sort all clusters by (score desc, sum4 desc,
    canonical shortlist order) -- this sort already groups same-score bands
    contiguously, so pairing simply-adjacent pairs within a band naturally
    (winners-vs-winners, losers-vs-losers, 0.5s-vs-0.5s), with any odd band
    boundary spilling into the next band exactly like round 1's bye rule.
    """
    cluster_score: dict[str, float] = {}
    for entry in resolved:
        for cid, score in entry["outcome"].items():
            if cid in cluster_score:
                print(f"cluster {cid} scored more than once in r1_resolved.json", file=sys.stderr)
                sys.exit(1)
            cluster_score[cid] = score

    contested_rows = [r for r in shortlist if r["band"] == CONTESTED]
    sum4_by_cluster = {r["cluster_id"]: r["sum4"] for r in contested_rows}
    canonical_index = {r["cluster_id"]: i for i, r in enumerate(contested_rows)}
    row_by_cluster = {r["cluster_id"]: r for r in contested_rows}

    clusters = list(cluster_score.keys())
    clusters.sort(key=lambda cid: (-cluster_score[cid], -sum4_by_cluster[cid], canonical_index[cid]))

    pairs: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(clusters):
        pairs.append((clusters[i], clusters[i + 1]))
        i += 2
    # odd count -> clusters[-1] is the bye, simply omitted (mirrors round 1).

    rng = random.Random(NEXT_ROUND_SHUFFLE_SEED)
    duels_out = []
    for idx, (cid_x, cid_y) in enumerate(pairs, start=1):
        members = [cid_x, cid_y]
        rng.shuffle(members)
        cid_a, cid_b = members
        duel_id = f"r2_{idx:03d}"
        result_path = str((DUELS_DIR / f"result_{duel_id}.json").resolve())
        duels_out.append(
            {
                "duel_id": duel_id,
                "a": make_side(row_by_cluster[cid_a], tech_scores),
                "b": make_side(row_by_cluster[cid_b], tech_scores),
                "result_path": result_path,
            }
        )
    return duels_out


def run_next_round() -> None:
    """Builds round_2.json from r1_resolved.json (--resolve must run first).
    Mechanical only -- no judging, no policy decisions.
    """
    if not RESOLVED_R1_PATH.exists():
        print(f"missing {RESOLVED_R1_PATH} -- run --resolve first", file=sys.stderr)
        sys.exit(1)

    resolved = load_json(RESOLVED_R1_PATH)
    shortlist = load_shortlist()
    tech_scores = load_tech_scores()

    duels_out = build_round2(shortlist, tech_scores, resolved)
    write_json(ROUND2_PATH, duels_out)

    n_scored = sum(len(e["outcome"]) for e in resolved)
    bye_n = n_scored - 2 * len(duels_out)
    print(f"round_2: {n_scored} scored -> {len(duels_out)} duels, bye={bye_n}")
    print(f"wrote {ROUND2_PATH}")


# ---------------------------------------------------------------------------
# --standings -- final ranking from r1_resolved.json + r2_resolved.json
# ---------------------------------------------------------------------------

def build_standings(
    resolved_r1: list[dict],
    resolved_r2: list[dict],
    shortlist: list[dict],
    clusters: list[dict],
    tech_scores: dict[str, dict],
) -> list[dict]:
    """Per contested cluster, sums its outcome score across both rounds and
    ranks by (score desc, sum4 desc, rep-blur desc, cluster_id asc).

    rep-blur is looked up via records/clusters.json's "rep" member (NOT
    shortlist's "best_member" -- the two differ for ~1/3 of contested
    clusters) into records/tech_scores.json's "blur" field.
    """
    score: dict[str, float] = {}
    opponent_r1: dict[str, str] = {}
    opponent_r2: dict[str, str] = {}

    for round_num, resolved, opponent in ((1, resolved_r1, opponent_r1), (2, resolved_r2, opponent_r2)):
        for entry in resolved:
            cluster_a = entry["cluster_a"]
            cluster_b = entry["cluster_b"]
            for cid, other in ((cluster_a, cluster_b), (cluster_b, cluster_a)):
                if cid in opponent:
                    print(f"cluster {cid} appears more than once in round-{round_num} resolved", file=sys.stderr)
                    sys.exit(1)
                opponent[cid] = other
            for cid, s in entry["outcome"].items():
                score[cid] = score.get(cid, 0) + s

    contested_rows = [r for r in shortlist if r["band"] == CONTESTED]
    sum4_by_cluster = {r["cluster_id"]: r["sum4"] for r in contested_rows}
    contested_ids = set(sum4_by_cluster.keys())

    rep_by_cluster = {c["cluster_id"]: c["rep"] for c in clusters}
    blur_by_cluster: dict[str, float] = {}
    for cid in contested_ids:
        rep = rep_by_cluster.get(cid)
        if rep is None:
            print(f"cluster {cid}: no rep in records/clusters.json", file=sys.stderr)
            sys.exit(1)
        if rep not in tech_scores:
            print(f"cluster {cid}: rep {rep!r} missing from records/tech_scores.json", file=sys.stderr)
            sys.exit(1)
        blur_by_cluster[cid] = tech_scores[rep]["blur"]

    scored_ids = set(score.keys())
    missing = contested_ids - scored_ids
    if missing:
        print(f"final standings missing {len(missing)} contested cluster(s): {sorted(missing)}", file=sys.stderr)
        sys.exit(1)
    extra = scored_ids - contested_ids
    if extra:
        print(f"final standings has {len(extra)} non-contested cluster(s): {sorted(extra)}", file=sys.stderr)
        sys.exit(1)

    ordered = sorted(
        contested_ids,
        key=lambda cid: (-score[cid], -sum4_by_cluster[cid], -blur_by_cluster[cid], cid),
    )

    standings = []
    for rank, cid in enumerate(ordered, start=1):
        standings.append(
            {
                "rank": rank,
                "cluster_id": cid,
                "score": score[cid],
                "sum4": sum4_by_cluster[cid],
                "r1_opponent": opponent_r1.get(cid),
                "r2_opponent": opponent_r2.get(cid),
            }
        )
    return standings


def run_standings() -> None:
    if not RESOLVED_R1_PATH.exists():
        print(f"missing {RESOLVED_R1_PATH} -- run --resolve --round 1 first", file=sys.stderr)
        sys.exit(1)
    if not RESOLVED_R2_PATH.exists():
        print(f"missing {RESOLVED_R2_PATH} -- run --resolve --round 2 first", file=sys.stderr)
        sys.exit(1)

    resolved_r1 = load_json(RESOLVED_R1_PATH)
    resolved_r2 = load_json(RESOLVED_R2_PATH)
    shortlist = load_shortlist()
    clusters = load_clusters()
    tech_scores = load_tech_scores()

    standings = build_standings(resolved_r1, resolved_r2, shortlist, clusters, tech_scores)
    write_json(FINAL_STANDINGS_PATH, standings)
    print(f"final_standings: {len(standings)} contested cluster(s) ranked")
    print(f"wrote {FINAL_STANDINGS_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Step 2.6/2.7a/2.7b duel round builder")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--verify", action="store_true", help="verify existing duel outputs")
    group.add_argument("--reversals", action="store_true", help="build reversed re-run duels for slim results")
    group.add_argument("--resolve", action="store_true", help="combine a round + its reversal results into r{N}_resolved.json")
    group.add_argument("--next-round", action="store_true", help="build round_2.json from r1_resolved.json")
    group.add_argument("--standings", action="store_true", help="build final_standings.json from r1_resolved.json + r2_resolved.json")
    parser.add_argument(
        "--round",
        type=int,
        choices=(1, 2),
        default=1,
        help="round number for --reversals/--resolve (default: 1)",
    )
    args = parser.parse_args()

    if args.verify:
        run_verify()
    elif args.reversals:
        run_reversals(args.round)
    elif args.resolve:
        run_resolve(args.round)
    elif args.next_round:
        run_next_round()
    elif args.standings:
        run_standings()
    else:
        run_build()


if __name__ == "__main__":
    main()
