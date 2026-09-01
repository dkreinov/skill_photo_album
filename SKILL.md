---
name: photo-album
description: Turn a large mixed pool of photos, videos and AI-edited images into a print-ready vendor photo book, with an orchestrator + worker-agent team and a gate at every irreversible step — acquire and inventory into a hashed ledger, re-cull with vision-judge fleets and pairwise duels, page-plan and then hand the user a live single-file HTML album builder whose geometry is diffed automatically against the print engine, produce print assets at honest real-pixel DPI, and assemble in the vendor's web editor. Use when the user asks to build a photo book, family album, printed photo album, yearbook or trip album from their photo library, or wants an auditable selection-and-layout pipeline with user approval at every gate.
---

# photo-album — a printed photo book, end to end

Distilled from a real 30×30cm layflat book run: ~480 pool images, 33 videos, two AI-chat
conversations of edited/fantasy images, 76 pages, 267 commits, 40 scripts, seven plan
revisions. Every named constant below is a **parameter** — the numbers are the ones that
were actually measured, not defaults to trust blindly.

Read `references/lessons.md` **before making any resolution, validation or geometry
decision.** Almost every expensive mistake in this pipeline is already listed there, with
the number that bought it.

## Run architecture (set up before Phase 1)

- **Roles.** One orchestrator (ORCH) decides, dispatches one step at a time to clean-context
  WORKER executors, re-runs every frozen validation itself in a clean shell, and routes
  taste questions to the user. Steps needing the user's authenticated browser (photo host,
  AI chat, vendor editor) are `owner: ORCH` — browser sessions cannot be handed to
  subagents. **Payment and ordering are USER-only, always.**
- **Capture layers** (the run must survive any handoff): `plan.md` (frozen contracts C1..Cn
  plus an append-only decision log D-NNN), append-only `journal.md`, `records/*.json` (all
  state), `scripts/` (all logic). Git tracks records/scripts/plans; binaries are gitignored
  — integrity lives in the ledger's sha256, not in git.
- **Frozen validation.** Every step ships a `--verify` mode whose pass criteria are frozen
  in the spec BEFORE execution. Workers implement thresholds, never tune them. Keep
  judgment metrics OUT of mechanical validation — report them, and let ORCH judge at
  acceptance (lessons B5).
- **Bounded step families.** A failing step gets 3–5 repair leaves, then is accepted as
  documented best-effort with its ceiling written down. No unbounded pixel-tuning.
- **Single-writer.** One agent owns each file's writes. Parallel dispatch only for disjoint
  write sets, logged as an exception each time (vision fleets qualify).
- **Context hygiene.** ORCH never renders images in-thread. All image-eyeballing goes to
  vision subagents with capped ≤15-line reports; ORCH reads verdict files and 3-line
  validation outputs only.
- **Escalation.** Executors stop-with-question on spec contradictions; ORCH amends the
  packet and re-dispatches fresh. Packet shape: `references/protocols.md` Part 2.

## Frozen contracts to establish at the plan gate (parameterize per project)

- **C1 TITLE** — exact string, exact language, decided early and never improvised later.
- **C2 PRODUCT** — vendor, binding, trim size, page raster in px (30×30cm → 3600×3600;
  spreads 7200×3600), the page-count rule (a multiple of 4, inside the vendor's range **and**
  inside what the purchase actually covers), and DPI floors — see C2a.
- **C2a REAL-DPI FLOORS** — DPI is computed from **native pre-upscale pixels**, and the
  floors are content-tiered: photographic fails below **120 real DPI**, generated/AI art
  below **90**. Print the tier per slot.
- **C3 READING DIRECTION** — for RTL books, reading direction ≠ upload order: the vendor
  pairs pages 1-2, 3-4…, and the narratively-first element sits on the RIGHT page. Prove it
  with a two-spread in-editor proof before mass placement.
- **C4 IDENTITY & HONESTY** — every AI image preserves the real people (no substituted or
  invented faces); every fantasy image used has a real anchor on the same or facing page, or
  an explicitly user-approved standalone status.
- **C5 FILE LAYOUT** — fixed `assets/` subtrees per source plus `assets/generated/` for
  derived files with `_vN` suffixes. **C6 IMMUTABILITY** — originals are never edited in place.
- **C7 LEDGER SCHEMA** — one row per image file: id (relpath), source, w, h, exif_time,
  phash (64-bit), bytes, sha256; JSON + CSV, same rows, same order.
- **C8 GIT** — records/plans/scripts committed, binaries not.

## Pattern: the interactive HTML tool gate

Rule: **more than three visual decisions for the user ⇒ generate an offline single-file HTML
tool, never chat Q&A.** The tool (a) embeds a verbatim data island of the frozen draft JSON
so the generator's `--verify-tool` can byte-compare it; (b) shows thumbnails with a lightbox
loading the FULL-RES original; (c) persists every click to localStorage immediately, as an
overlay over an immutable draft, so a tool bug can never destroy decisions; (d) exports a
JSON overrides file via a Blob download **plus** a visible `<textarea>` fallback; (e) is
RTL-correct where the album's language needs it; (f) carries live invariant guards ported
from the validator. A companion script `--apply` merges the export onto the draft,
`--selftest` round-trips a synthetic export, `--verify-final` gates the merged file.
**User export = approval.** Cross-link consequences inline (a cluster card must show the
fantasy images it anchors). Treat user overrides as authoritative — never bounce an export.
Every decision schema needs a `removed`/exclude exit.

## Pattern: the vision fleet

A worker writes a frozen `PROTOCOL.md` to disk (role, judging law, blindness rule, and the
exact JSON output contract with a fenced example that must pass the same schema checker the
results will face). ORCH dispatches one blind judge per batch (~5–8 units each), each writing
a **disjoint** result file, in waves of ~10. `--verify-results` checks that every expected
file exists, parses and is schema-valid; a malformed file re-dispatches that unit only.
Scale reached: 30 triage judges over 237 clusters and 34 duel groups over 139 duels + 47
reversals, with zero malformed results. Templates: `references/protocols.md` Part 1.

---

## Phase 1 — Acquire & inventory

Purpose: every source image local, catalogued in one ledger, AI↔real pairing drafted and
user-resolved.

- Extract any prior album version with junk filtering; validate exact counts and dimensions.
- Browser-download the full real pool via the share link's "Download all". Photo-host read
  APIs have rotted, and Takeout misses albums shared *with* you. Count items by a full-scroll
  DOM harvest of the share grid, and split image vs video counts before validating a file walk.
- Harvest AI-conversation images at full resolution in on-page order (`NNN_desc.png`) with a
  one-line provenance note per image ("real photo | generated | Edit of NNN") — **these notes
  are the pairing ground truth**, not pixel similarity.
- Build the ledger (C7) with `scripts/build_ledger.py`. Draft pairing by provenance first;
  pHash only as a flagged fallback. Statuses: fantasy | real-dup | filler | standalone | removed.
- Contact sheet (`scripts/inventory_sheet.py`), then a pairing tool for the unknowns.

Gate: the user reviews the inventory and resolves pairs in the tool; `--verify-final` passes.

## Phase 2 — Selection

Purpose: re-cull the whole pool on merit. Prior album picks compete with a small incumbent
bonus — never a veto.

- Mine video frames (`extract_video_frames.py`): 1 fps sample, top-3 sharpest per clip, ≥2s
  apart, sibling-pHash dedup.
- Map prior-album usage (page/region pHash with aspect-fit cropping). Accept a best-effort
  map with a documented ceiling; selection quality must not depend on it.
- Cluster (`cluster_pool.py`): time-gap ≤8s OR pHash ≤10, split at >15min, plus tech scores.
- **Triage fleet** (`triage_batches.py`): per cluster, four 1–5 axes + `keep_flag` +
  `best_member` + an optional enhancement note, under a frozen judging law
  ("candid family moments beat postcard scenery").
- Band into auto-keep / auto-drop / contested (`shortlist.py`); look at the histogram BEFORE
  paying for duels.
- **Pairwise duels** on the contested band only (`duels.py`): 2 Swiss rounds, seeded A/B
  shuffle, mandatory reversed re-run on slim margins. Pairwise beats absolute rescoring for
  fine ordering.
- Fantasy shortlist is INVENTORY ONLY — every usage decision defers to the page-plan gate.
- Selection tool: keep | keep+enhance | drop. Enhancement notes are free text that can carry
  conditional logic ("sharpen faces; if still bad → drop") which a later phase must evaluate
  and act on. Edit kinds (enhancement vs fantasy) come from a **semantic vision pass**, never
  from pHash.

Gate: the user works the tool and exports; the merged `selection.json` passes `--verify-final`
with a `user_override` escape from the keep window.

## Phase 3 — Page plan

Purpose: a user-ratified spread-by-spread plan, planned by a fresh planner from files only.

- Draft packer: chapters → spreads → slots, with the **spread as the editorial unit**
  (hero / sequence / diptych / collage / breathing / transition); an honest bench for
  unplaceable keeps; people-size invariants (people ≥9cm, ≤4 people-photos per page); a
  strict chronology validator (chapter order + intra-chapter time); pairing constraint =
  time gap ≤45min **AND** same chapter.
- Vision passes: prior-page gap scan, cover-art vetting, and a bounded creative pass per
  chapter (≤2 new fantasy proposals, base = a kept photo, ONE added element, no quota) plus
  coverage notes on who is under-represented.
- **Vendor recon BEFORE typography/collage decisions** — fonts, RTL support, text-over-photo,
  template library, box freedom, accepted upload formats, autosave behaviour, and exactly what
  the purchase covers. Then **measure the vendor's real safe margin from its own on-canvas
  guide**; do not assume print defaults (lessons D1).
- Collage policy: collages are for places, details and atmosphere — never tiles of people
  photos. People get large frames, sequences and diptychs; mosaics use varied tile sizes.
- Fantasy/real integrity: the real inset must be the fantasy's actual source moment, must
  never cover a face, must never be split across pages — and when both appear on a spread,
  never both large.
- Page-plan mockup tool → a frozen `pageplan.json` plus the asset work manifest.

Gate: the export ratifies page count, cover, labelling, fantasy usage and proposals. In
practice a user may rule continuously in chat instead of exporting — then ORCH assembles the
frozen plan from the draft plus every chat ruling, with any unresolved item recorded as a
**named default pending user flip**, never as a silent choice.

## Phase 4 — Asset production

Purpose: every planned asset exists at print resolution.

- Execute the work manifest: approved new generations and enhancements via the AI chat,
  identity-preserving per C4, each judged against the user's stated conditional with the
  stated fallback applied.
- **Two-step generation, one job per turn**: character sheet first, then scenes from the
  sheet; artwork first (with deliberate empty space), then titling of the finished artwork.
  Ask for N images, never one sheet of N (lessons A1).
- **Fix a wrong physical description at its source file** — the reference/character sheet
  every later generation starts from — not per generation. One wrong descriptive word
  propagated agent-to-agent through a whole run and forced three separate reruns.
- Upscale AI outputs (typically 1024–1536px native) toward the page raster with
  `upscale_assets.py`, and state plainly that this adds no real detail. De-frame official
  venue photos by cropping only.
- Convert to the vendor's accepted format (JPEG q95 in the reference run; PNG was rejected),
  EXIF-transposed. Build flattened masters only for effects the editor cannot do natively.
- Validate: decode-reopen + non-blank on every written image (`check_no_empty.py`),
  dimensions, real-DPI floors, and the vendor-export validator run on the exact final files.

## Phase 5 — The album builder

Purpose: hand the user a **live, offline, single-file HTML album builder** and let them build
the book page by page — because a plan the user cannot manipulate directly will be
renegotiated in chat forever. This phase consumed more effort than every other phase combined
(twenty tool versions) and is where the pipeline's real value sits.

**The core discipline:** the builder's composer and the print renderer are **two
implementations of one geometry**, and they must be diffed automatically or they will drift.
See `references/protocols.md` Part 3 for the gates. Never let the export→plan step *read* the
builder's geometry — make the geometry **ride verbatim** on the slot and draw it with a
line-for-line port of the composer's arithmetic.

What the builder must have, in the order the run learned it:

1. **Live composer.** Every change re-renders instantly; anything less and the user cannot
   judge. Pin the canvas and scroll the inspector so the canvas stays visible while the
   controls are reached.
2. **The full pool, not the selection.** Selection is a default, not a boundary — "on some we
   were wrong." Tabs, a picker, and honest capability chips (spread-capable / page-capable /
   small-only) derived from **real native pixels**.
3. **One object model.** Every placed image is a tile in a layout; full bleed is the default
   rect, not a special kind. Otherwise some images silently lack controls.
4. **Per-tile controls**: size, zoom, aspect, crop fit + drag-to-position, free frame drag,
   8 resize handles, free rotation, z-order, border style, gutters, reset — all writing one
   single-truth rect, with the DPI badge recomputed from the FINAL rendered picture box.
5. **Layout presets** (~15) shown as schematics generated FROM the geometry, plus seeded
   rebuilds that pre-load the plan's actual arrangement, so a proposal is a starting point
   rather than a menu.
6. **Auto-fill** — "fill this page with the next N unplaced items". This was the single
   biggest reduction in manual work and the one feature every mainstream editor already had.
   Fill in chronological order anchored on what the page already holds; choose a preset by
   available count rather than inventing layouts; skip anything already placed or of the
   wrong kind; flag — never silently place — a below-floor-resolution item; one undo step;
   and a second press must duplicate nothing.
7. **Alignment guides.** Derive the snap threshold on the PRINTED page (~3mm), never in
   screen pixels. Match same-edge-to-same-edge only (edge-to-any-edge catches bottom-to-top,
   i.e. stacking, which grid presets trigger constantly). Compare clamped rects against
   clamped rects, or the snap silently never fires. Always include page REFERENCE lines
   (safe-area top/bottom, page centre, fold) — a page holding one big picture has no
   neighbouring edges to extend, and that is exactly when the user asks "how high is this?".
8. **Structure editing** on a block-river page map: insert (budget-guarded), delete, reorder,
   move, swap-first, with the true cost of every hole resolution shown BEFORE it applies.
9. **Overlays**: subject cutouts, decorations, day markers, whole-page day dividers — free
   position/rotation/opacity/z, above or below photos, with alpha honoured in composer,
   viewer and print alike.
10. **Copy/paste of a page's whole contents.** A "replace" paste is a verbatim clone, so a
    pasted page exports byte-identically to its source. Keyboard paste is ADDITIVE only, so a
    shortcut can never destroy a page; destructive replace stays an explicit button.
11. **Safety rails**: one clamp law shared by both engines, live DPI honesty with an
    "(upscaled)" breakdown, a non-blocking warning when a people-photo nears the fold, real
    undo at depth 50, and JSON import/restore that reads **every** key the export writes.
12. **External intake**, so a new photo can enter mid-build (drop folder + in-tool upload).
13. **Proof artefacts the user actually judges by**: a print-fidelity PDF at ~3000px/spread
    q82 under the delivery size cap, plus a hires proof (4800px/spread) of the range they are
    actually working on, with a real-DPI quality sheet.

Build gates: the generator's own `--verify` (grown to 236+ checks) plus a Playwright smoke run
on **both** touch and mouse profiles, plus the fidelity harness — all re-run by ORCH. Watch
the file-size budget, and find the real driver before optimising.

Commission a **periodic adversarial audit** of your own builder — script-reproduced,
severity-ranked, with a feature-gap comparison against commercial editors in the same
category — and convert every repro into a permanent regression test. In the reference run
that audit surfaced three data-loss / wrong-print defects that every internal gate had passed.

## Phase 6 — Vendor build

Purpose: the album assembled in the vendor's editor, ready for the user to order.

Verify the editor runs in the user's browser early (WebGL). Reconcile project settings with
the plan (raise the page count in-editor). Upload the asset set. Place TWO spreads and verify
the reading-direction convention on the real product with the user before mass placement.
Save deliberately after every batch (assume there is no autosave). Work in chunked sequential
sessions of ~6 spreads with a per-chunk checker audit against the exported layout. Finish
with a joint full-book review. **The user orders and pays — never the agent.**

## Phase 7 — Distillation

Re-read the journal, the decision log and the records; update this skill: generalize new
scripts, promote new lessons with their numbers, parameterize anything project-specific that
leaked in. Gate: the user approves the skill.

---

## Decision framework (the reusable principles)

1. **Provenance over pixel similarity** for linking AI edits to sources — but the user's
   description of the moment outranks the provenance chain.
2. **Semantic kinds by eyes, not hashes** — enhancement vs fantasy is a vision judgement.
3. **Real pixels over interpolated ones** in every number you show the user.
4. **Pairwise duels over absolute scores** for the contested middle.
5. **User tools over chat Q&A** for any batch of visual decisions; user overrides are
   authoritative.
6. **Validate the exact final files**, and validate the printed pixels, not just the data.
7. **Two implementations of one geometry must be diffed — and each must also be asserted
   absolutely**, because mutual agreement is not correctness.
8. **Vendor recon and vendor measurement before layout decisions.**
9. **Full re-cull with an incumbent bonus** — prior picks compete, never veto.
10. **Defer irreversible and creative decisions to the latest responsible gate.**
11. **Every decision schema needs an exit.**
12. **Model one object with defaults rather than special-case kinds**, and expose welded
    styles as parameters with the current value as the default.
13. **Freeze before loosening** — prove nothing moves, then relax the constraint.
14. **The user is the authority on their own album**; style-guide bans are defaults, and a
    waiver is recorded so no later review silently re-applies it.

## References

- `references/lessons.md` — the hard rules, each with the number that bought it.
- `references/protocols.md` — vision-fleet templates, the executor packet, the fidelity /
  trim / mat gates, round-trip integrity, and the ingestion / sticker / decoration pipelines.
- `references/scripts.md` — the bundled scripts, their modes and frozen validations, plus the
  patterns for the parts that were too project-specific to ship.
