---
name: photo-album
description: Rank, cull and lay out a thousand holiday photos, and carry the survivors all the way to a printed book. Clusters near-duplicate bursts by capture time and visual similarity so a burst is judged once, then runs a fleet of blind vision judges that score every cluster on four 1-5 axes and name its best member, then settles the contested middle with pairwise duels because absolute scores are weak between close rivals — 30 triage judges over 237 clusters and 34 duel groups over 139 duels on a 479-image pool in the reference run. Any previous album is re-culled on merit too: prior picks get an incumbent bonus, never a veto. The shortlist then lands in an offline HTML tool where the user rules keep / keep+enhance / drop, and that verdict wins. Downstream: page plan, print assets at honest real-pixel DPI, optional AI-edited "fantasy" images with the real photographic faces composited back, a live single-file album builder the user composes in, gates that read the printed pixels (trim, fold-on-a-face, visibility, derivation), and assembly in the vendor's web editor — the user orders and pays, never the agent. What it does not do: it does not know what matters to you emotionally, cannot tell the friend from the stranger, and does not judge sentiment; it ranks sharpness, composition, technical quality and moment quality, and the human makes the final call on every keep, drop and page. Use when the user asks to cull, rank, shortlist or de-duplicate a large photo library, pick the best shots from bursts or a trip, or build a photo book, family album, printed photo album, yearbook or trip album — or wants an auditable selection-and-layout pipeline with user approval at every gate.
---

# photo-album — a printed photo book, end to end

Distilled from a real 30×30cm layflat book run: ~480 pool images, 33 videos, two AI-chat
conversations of edited/fantasy images, 76 pages, 270+ commits, 40 scripts, eight plan
revisions, and a book finally assembled object-by-object in the vendor's own editor. Every
named constant below is a **parameter** — the numbers are the ones that were actually
measured, not defaults to trust blindly.

Read `references/lessons.md` **before making any resolution, validation or geometry
decision.** Almost every expensive mistake in this pipeline is already listed there, with
the number that bought it.

## The route, end to end

```
Phase 0  contracts        title, product, trim size, reading direction, identity rules, DPI floors
Phase 1  acquire          every source image local, in one hashed ledger, AI↔real pairs resolved
Phase 2  select           re-cull the whole pool: vision triage → duels → the user's own tool
Phase 3  plan             chapters → spreads → slots, AFTER measuring the vendor's real sheet
Phase 4  assets           every planned image at print resolution, faces intact, honest DPI
Phase 5  build            the user composes the book in a live single-file HTML builder
Phase 6  print files      render, then gate the PRINTED PIXELS — fidelity, trim, visibility, faces
Phase 7  vendor build     assemble in the vendor's editor, in a duplicate project
Phase 8  cover            the wrap, the spine, the turn-in and the vendor's barcode
Phase 9  order            the USER presses order and pays. Never the agent.
Phase 10 distil           fold what this run learned back into this skill
```

Phases 6–8 are where a project that "looks finished" is still wrong. Budget for them.

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

## Phase 0 — Frozen contracts, established before anything else (parameterize per project)

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

- Execute the work manifest: approved new generations and enhancements through **whatever
  image-generation service the project uses**, identity-preserving per C4, each judged against
  the user's stated conditional with the stated fallback applied.

**The generator is swappable — the requirements are not.** The reference run drove a chat model
in a browser; that is an implementation detail. Any service works if it offers (a) image-to-image
editing that keeps the source composition, (b) a reference/character sheet the model honours, and
(c) a downloadable result at native full resolution. Swapping means reimplementing one function,
`generate(job) -> asset`; provenance recording, the pairs file, upscaling, the face composite and
every validator stay identical. An API generator is the cleanest (scriptable, so the step leaves
`owner: ORCH`); a browser UI costs you automation and hand-written provenance; a local model
costs a GPU and buys privacy and seeds. Full comparison and the seam's contract:
`references/protocols.md` Part 7.
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

**Faces and whole-frame AI edits — the rule that saves the album.** An image model's edit
path **re-renders the entire frame** at ~1450px whatever you asked it to change, so every
face in the picture comes back re-invented at 40–60px, including faces nowhere near the
edit. Do not regenerate: **composite the real photographic faces back in.**

1. Recover the transform between the generated frame and its real source. It does not have
   to be identity — it has to be **recoverable**. A brute-force offset search proves pixel
   alignment for a plain re-render; for an **outpainted** frame, recover a scale+translate by
   **gradient correlation** (FFT coarse pass, then refinement).
2. Paste through feathered elliptical masks with per-channel exposure matching to the
   generated lighting, and a smoothstep falloff that ramps to zero before any adjacent
   generated object — otherwise the paste leaks rectangles of real background.
3. **Scan the whole frame, not the face the user pointed at.** In this run the user reported
   one damaged face and there were three; two more re-invented faces would have printed.
   Then audit every other asset produced by the same route.
4. Record the substitution as a declared, guarded table applied inside the build — and apply
   it on **every** path that constructs state, including the import path (lessons H3).

The repaired file is also the higher-resolution one: 4032×3024 of real photograph against
the model's 1448, i.e. real DPI 61 → 171 in one case and 75 → 300 in another.

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

**And know what the harness does NOT catch.** A fidelity harness that compares rects,
padding, z and angle validates only **where the picture is**. In this run all four agreed
perfectly while two defects shipped: a tile that was transparent in the composer and painted
**opaque paper** in the renderer (0.50mm of drawn frame on screen, 17.04mm on paper — and the
same bug was silently matting five other slots), and a **lost rotation** caused by a legacy
`rotate_deg` field the renderer honoured and the composer had never heard of. So the harness
must also assert **what a tile paints where the picture is NOT** (ground opacity, drawn frame
width in mm of paper, mat, shadow) and **which source file each engine opened**, with
rotation compared mod 360 and a planted legacy field the engine must ignore. Gate G10.

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

## Phase 6 — Print files, and the gates that read printed pixels

Purpose: turn the ratified plan into the exact files that will be printed, and prove things
about the **printed pixels** that no data validator can see. This is the phase most projects
skip, and every defect that reached paper in this run would have been caught here.

Render the plan, then run, in this order (all specified in `references/protocols.md` Part 3):

- **G1/G10 fidelity** — composer vs print engine, paired by geometry, plus ground opacity,
  drawn frame width in mm, source identity and rotation mod 360.
- **G2 absolute containment** — asserted independently on both sides, exempt per tile and
  never per page.
- **G3 sentinel-mask trim** — clearance as a number, not absence of ink.
- **G4 mat band**, **G8 round-trip**, **G5 structural product promises**.
- **G11 visibility** — every element rendered twice, once lifted out, and required to differ
  inside its own rectangle. A frame that exists in the plan but cannot be seen is a defect.
- **G12 human-rule gates** — the fold must never fall on a face (report); the trim must never
  cut a person (fatal); frame rings checked on **all four sides** against both your sheet and
  the vendor's trim.
- **G13 derivation** — every derived artifact re-derived from its current source, byte for
  byte. A stale downstream copy bit this run three separate times, in three subsystems, with
  every other gate green (lessons H).

Every new gate ships with a **negative proof**: turn the fix off and watch the gate fail
exactly the items it used to pass. Corrections to an approved plan go in a **declared override
table** whose entries state the export values they `expect`, so the build stops if the owner
has since recomposed that tile — never hand-edit a generated plan (lessons I7).

## Phase 7 — Vendor build

Purpose: the album assembled in the vendor's editor, ready for the user to order. Full method
in `references/protocols.md` Part 5; the short form:

1. **Duplicate the project** and snapshot every canvas's object geometry first. There is no
   undo here; the duplicate is the undo.
2. **Establish what the editor can be told.** In this run: axis-aligned boxes only — W, H, X,
   Y in centimetres, no angle, no crop, no zoom. Everything else must be **baked into pixels
   before upload**. Rotation is the visible instance; **crop is the expensive one** — 88 of 115
   slots had a frame aspect their file did not, and typing the plan's W/H onto the raw files
   would have squashed all 88.
3. **Bake overlapping things together** into opaque groups over a full-sheet background object,
   rather than trusting the vendor's alpha handling. Bake at ~3× the renderer's canvas.
4. **Prove ONE unit end to end** — place → type → save → reload → read back at 0.0mm — before
   committing all N. Save deliberately after every batch; assume no autosave; verify *after*
   the save.
5. **Verify canvas ORDER against the labels.** The DOM order here was **reversed** (DOM index 0
   was the last spread), and placing in DOM order would have printed the album back to front.
   Pin down every index↔label mapping explicitly: reading direction, DOM order, and proof-PDF
   page numbering are three separate mappings and each was wrong once.
6. **Key objects by geometry**, because vendor ids are regenerated on save: canvas index plus
   geometry in cm rounded to 0.01, with a payload property unique per canvas.
7. **Nothing deleted, nothing ordered.** Stale library images are listed for the owner to
   delete as his own authorised act.

## Phase 8 — The cover, the spine and the wrap

Purpose: the outside of the book, which is a **different product** from the inside. No
page-level gate touches any of it. Full checklist in `references/protocols.md` Part 6.

- **Measure the cover canvas's own scale.** Do not inherit the interior's px/cm. Here the
  cover sheet was really 64.30 × 32.00cm, a uniform 1.077× the figure in the spec — so a wrap
  rendered at the spec's cm was **283 dpi, 7.7% short**, caught one step before printing.
- **The spine is real.** A codebase-wide grep for "spine" returning zero hits while two cover
  masters already exist is a finding, not a relief. 10–20mm comes out of the middle of the
  wrap; on a collage whose inner cell column sits at the fold it reads as a badly cropped tile.
- **Reserve the vendor's own furniture.** The barcode and logo print **white-backed, over your
  artwork**. Mapped into this run's back-cover collage the block landed on four faces (47.9%
  skin by area). Declare it as a dead zone to whatever packs the artwork and re-bake — never
  place it anyway.
- **Ask the owner which panel is the front.** Circumstantial evidence is not proof, and trying
  to settle it by clicking the editor's 3D preview wedged the app for six minutes.
- **Run the face check on the delivered wrap**, in true millimetres, against every protected
  zone at once, and report the nearest-face clearance per zone as a number for the owner to
  accept or reject.

## Phase 9 — The order

Joint full-book review, then **the user orders and pays. Never the agent.** The same applies to
deleting stale uploads and to reloading a tab over unsaved work: irreversible acts belong to
the owner.

## Phase 10 — Distillation


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
15. **A cross-engine diff proves where a picture is, never what a tile paints where the
    picture is not** — assert ground, mat, drawn frame width and which source each engine read.
16. **"Correct rect" and "visible" are different assertions.** Render it twice, once without
    the element, and require a difference.
17. **Never regenerate a frame to fix a face — composite the real face back.** Alignment need
    not be identity; it must be recoverable. And scan the whole frame, not the face reported.
18. **Vendor space is not plan space, and the cover is not the interior.** Measure both sheets,
    and measure the vendor's printed furniture as content.
19. **Assert derivation, never assume it.** Ask what *opens* the file, not what declares it.
20. **Turn the owner's sentences into gates that run over the rendered artefact** — they will
    find instances he never saw — and re-run every gate against its own fix.
21. **Prove one unit end to end before committing all of them**, and verify order against
    labels rather than against your recon.

## References

- `references/lessons.md` — the hard rules, each with the number that bought it.
- `references/protocols.md` — vision-fleet templates, the executor packet, the fourteen print
  gates (fidelity, ground/source, containment, trim, mat, visibility, human-rule, derivation,
  vendor-space), the ingestion / sticker / decoration pipelines, the vendor-editor build
  method, the cover / spine / wrap checklist, and how to swap the image-generation service
  (Part 7).
- `references/scripts.md` — the bundled scripts, their modes and frozen validations, plus the
  patterns for the parts that were too project-specific to ship.
