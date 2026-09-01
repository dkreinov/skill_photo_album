# Bundled scripts — modes and frozen validations

Every script follows one pattern: a **build/run mode** plus a **frozen `--verify` mode** whose
pass criteria were written into the step spec BEFORE the code existed. Workers implement
thresholds; they never tune them. Tool generators additionally ship `--apply` (merge a user
export onto the immutable draft), `--selftest` (round-trip a synthetic export) and
`--verify-final` (gate the merged file).

**Before running anything:**

```bash
pip install -r scripts/requirements.txt     # Pillow, pillow-heif, imagehash, opencv-python
# additionally, per script: numpy, scipy (badge cutting), rembg + onnxruntime (stickers)
```

All scripts resolve paths relative to a `ROOT` two levels up from the script, and expect the
project layout `assets/` + `records/` + `scripts/`. On Windows, pin the real interpreter path —
a bare `python` may be a broken WindowsApps stub.

> **Project-specific constants are marked below.** Each script has a small constants block near
> the top (thresholds, chapter lists, sheet manifests, judging law text). Those are the things
> to change; the algorithms below them are generic. Places where the original run's private
> content was removed are left as `{{PROJECT}}`, `<PROJECT_ROOT>`, `<HEBREW-UI-STRING>` or
> neutral placeholder dates — replace them with your own.

## Inventory and integrity

| Script | What it does | Modes | Frozen validation |
|---|---|---|---|
| `check_no_empty.py` | Walks a directory; fails on 0-byte / undersized / undecodable images; optional expected-count check against a JSON key | `--min-bytes --allowlist --expect-count-from --expect-count-key` | itself: exit 0 on a clean tree |
| `build_ledger.py` | Walks `assets/` → `ledger.json` + `ledger.csv` (contract C7: id, source, w, h, exif_time, phash, bytes, sha256) | build, `--verify` | `--verify` (re-walk; row count == file count; all sha256 match) |
| `inventory_sheet.py` | Offline HTML contact sheet of the whole inventory (by source / by hour, pairing status, per-image notes) | build, `--verify` | `--verify` (HTML refs == ledger rows, no broken relative paths) |
| `ingest_incoming.py` | One-command intake for new photos dropped into `assets/incoming/`: EXIF transpose, `taken_at`, sha256 idempotency, DPI at the two target print sizes, capped FSRCNN upscale, manifest | `--scan --ingest --verify` | `--verify` |

*Project-specific:* the print sizes DPI is reported at, and the allowlist of accepted suffixes.

## Selection

| Script | What it does | Modes | Frozen validation |
|---|---|---|---|
| `extract_video_frames.py` | Mines frames from clips: 1 fps sample, top-3 sharpest (Laplacian), ≥2s apart, sibling pHash ≤6 dedup, blank-check (33 videos → 92 frames in the reference run) | build, `--verify` | `--verify` |
| `cluster_pool.py` | Burst / near-dup clustering (gap ≤8s OR pHash ≤10, split at >15min), tech scores (blur/clip), 1024px thumbs (384 candidates → 237 clusters) | build, `--verify` | `--verify` (every candidate exactly once) |
| `triage_batches.py` | Writes the frozen triage `PROTOCOL.md` + `batch_NNN.json` (8 clusters/batch, seed 42); validates the fleet's outputs | build, `--verify`, `--verify-results` | `--verify-results` (all result files exist, parse, schema-valid) |
| `shortlist.py` | Bands verdicts into auto-keep / auto-drop / contested (summed four axes ≥16 / ≤9, +1 incumbent bonus), emits round-1 pairings, flags near-twins | build, `--verify` | `--verify` (reference split: 46 / 75 / 116) |
| `duels.py` | Swiss pairwise tournament: r1/r2 pairings, A/B shuffle seed 42, duel protocol, reversal re-runs on slim margins, standings (wins → summed axes → blur) | `--round --next-round --reversals --resolve --standings --verify` | `--verify` (139 duels + 47 reversals schema-valid) |

*Project-specific:* **`triage_batches.py` and `duels.py` embed the judging law and the chapter
list as prose in `PROTOCOL_TEXT` — rewrite both for your album.** Also the banding thresholds
in `shortlist.py` and the incumbent bonus.

## Asset production

| Script | What it does | Modes | Frozen validation |
|---|---|---|---|
| `upscale_assets.py` | Local FSRCNN print-resolution upscale pipeline (longest edge ≥3600px), q95 sRGB JPEG output, with separate worklists per asset set. Documents the model comparison that chose FSRCNN | `--run --run-pageplan --run-regen --limit --verify --verify-pageplan --verify-regen` | the matching `--verify*` mode |
| `make_sticker.py` | `rembg` (`u2net_human_seg` / `u2net`) subject cutouts with plain + outline/shadow variants; hand-authored polygon assists for objects the models won't cut | `--run --batch --list --preview --id --model --crop --largest --max-px --limit --suffix --exclude-poly --subtract-poly --union-model --close-px --verify` | `--verify` (RGBA, transparent corners, 5–95% coverage, no opaque-rectangle failure) |
| `cut_decor_sheets.py` | Cuts generated decoration sheets into individual RGBA assets **deterministically** (grid-cell projection profiles for sparse line art, connected components for dense rows); patterns stay opaque as background tiles | `--run --run2 --verify --verify2` | `--verify` / `--verify2` (174 assets across 18 sets in the reference run) |
| `cut_day_stamps.py` | Cuts badge sheets by fitting **each badge's own drawn shape** (bbox → ellipse fit +1px, single feathered alpha, interior opaque by construction); `--run-hq` is the additive one-badge-per-file path | `--run --run-hq --verify --verify-hq` | `--verify` (no transparent pixel inside 0.95r, corners alpha <20, opaque area within 3% of πab) |

*Project-specific:* the `SHEETS` / `SLUGS` / `HQ_DESIGNS` tables in the two cutting scripts
enumerate one run's generated sheets (with placeholder dates and themes); replace them wholesale.
The upscale target edge and the DPI targets are parameters.

---

# Patterns that were NOT shipped as code

These parts of the reference run were too tightly bound to one album's private content, one
vendor's editor and one non-Latin UI to publish. Rebuild them from these specs.

**The selection tool generator** (~2.2k lines). Generates a single-file HTML tool: keep /
keep+enhance / drop per cluster, enhanced twins shown side by side, free-text enhancement notes
that may carry conditional logic, a full-res lightbox, and fantasy-link strips so a drop shows
what it would orphan. Ships `--apply` (merge the export), `--verify` (+selftest) and
`--verify-final` (a keep-count window with a `user_override` escape). See SKILL.md → *Pattern:
the interactive HTML tool gate*.

**The page-plan packer and its mockup tool.** Chapters → spreads → slots; a bench for
unplaceable keeps; people-size invariants (people ≥9cm, ≤4 people-photos per page); a strict
chronology validator; a pairing constraint of time gap ≤45min AND same chapter; fantasy
presentation defaults. The tool renders spread mockups, cover A/B, a proposals panel, a
labelling picker, a live mod-4 page counter, and an unplaced-photo invariant guard. Gate:
`--verify-tool` byte-compares the tool's embedded data island against the frozen draft.

**The print engine.** `pageplan.json` → spread PNGs and print-fidelity PDFs. Its geometry
functions (`draw_builder_slot`, `builder_clamp_safe`, `builder_drawn_bbox`,
`builder_picture_box`) are **imported** by every other script rather than reimplemented — that
import is what keeps one geometry law in one place. Always pass explicit PDF width/quality
(`--pdf-width 3000 --pdf-quality 82`); the defaults re-inflated accepted PDFs past the delivery
size gate.

**The album builder generator** (the single largest artifact of the run). Emits the offline
single-file HTML builder described in SKILL.md Phase 5. Its own `--verify` grew to 236+ checks
and imports the renderer to prove the JS mirrors it; a Playwright smoke run then exercises both
touch and mouse profiles.

**The WYSIWYG fidelity harness.** Full specification in `protocols.md` Part 3, gates G1–G4.

**The editor-layout exporter.** Converts every box the renderer draws into centimetres for a
browser agent to place in the vendor's editor (image boxes, text boxes, covers), validated so
that every slot appears exactly once, in bounds, with its file present.

**A vendor-export validator** — counts, dimensions, decode, non-blank, ZIP CRC on the exact
final files. Small, but the last thing standing between you and a bad print run: write one and
run it on the files you actually upload.
