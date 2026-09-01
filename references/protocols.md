# Reusable protocols, packets and gates

- **Part 1** — the vision-fleet protocol family (delegated image judgment at scale).
- **Part 2** — the executor packet shape.
- **Part 3** — the gate machinery that made the print engine trustworthy.
- **Part 4** — the asset pipelines (ingestion, stickers, decorations, badges).

---

# Part 1 — Vision-fleet protocols

Every protocol is FROZEN on disk (`records/<fleet>/PROTOCOL.md`) before any judge runs, and
self-validates: its fenced JSON example must pass the same schema checker the result files
will face. Placeholders look like `{{THIS}}`.

## Shared skeleton (all protocols)

```markdown
# {{PROJECT}} — {{FLEET NAME}} Protocol

Frozen judge protocol for {{PHASE.STEP}}. Do not renegotiate scope — {{ONE-LINE SCOPE,
e.g. "classification only" / "vetting of EXISTING items only" / "idea-spotting only"}}.

## Role
You are a {{PERSONA: photo editor / archivist / skeptical vetter / creative director}}
{{DOING WHAT, FOR WHAT ALBUM}}.

## Judging law            <- only for protocols that rank or score
> {{ONE EDITORIAL SENTENCE. Reference run: "Candid family moments beat postcard scenery.
> People and moments beat places. Candid beats posed. A slightly soft photo of a great
> moment outranks a sharp photo of nothing."}}

## Chapters (context only)
These exist only to help you read the trip's arc — background, not a rubric axis.
{{NUMBERED CHAPTER LIST}}

## Task — per {{UNIT}}
{{NUMBERED STEPS: view the image(s); decide the fields; write a one-line reason.}}

## Blindness rule
You know nothing about any previous album version. You see no scores, verdicts, or notes
from any other judge, and no results from any other batch, duel, or pass. Judge only the
images placed in front of you, right now.

## Output contract
Write your verdicts to the absolute `result_path` given in your dispatch
(`records/{{FLEET}}/result_{{UNIT}}_NNN.json`). Valid JSON, nothing else:
{{FENCED JSON EXAMPLE — must validate against the fleet's schema checker}}
Schema, field by field: {{EVERY FIELD: name (type, required?), allowed values.}}

## Chat report cap
Keep your chat reply to ≤15 lines — the JSON file is the deliverable, not your
commentary. Report only: counts done, and anything that failed to open.
```

## Template 1 — Cluster triage (absolute scoring pass)

Unit: a cluster; ~8 clusters per judge; one result file per batch.
Fields per cluster: `best_member` (id); four integer 1–5 axes `moment` / `story` /
`uniqueness` / `technical`; `keep_flag` (bool); optional `needs_enhancement` (bool) + a
one-line `enhancement_note` (omit both entirely when not applicable); `reason` (one line).
Result: `{"batch":"NNN","verdicts":[{...}]}` — exactly one verdict per cluster, any order.
Scale reached: 30 judges, 237 clusters, 3 waves, zero malformed results, zero re-dispatches.
Implemented in `scripts/triage_batches.py`.

## Template 2 — Pairwise duel (contested-band ranking)

Unit: a duel (A vs B); ~5 duels per judge, each an independent decision with its own result
file (grouping cut ~120 dispatches to ~24 without touching the methodology).
Blindness additionally bans: bands, the summed score, `keep_flag`, any other duel's outcome.
Result: `{"duel_id":"...","winner":"a"|"b","margin":"clear"|"slim","reason":"<one line>"}`.
Dispatcher rules (not the judge's business): A/B sides shuffled with a fixed seed; slim margins
trigger a mandatory reversed re-run by a fresh judge (disagreement = split).
Scale: 2 rounds, 139 duels + 47 reversals across 34 judge groups. See `scripts/duels.py`.

## Template 3 — Gap scan / archivist (describe, don't decide)

Unit: a prior-album page the automated matcher could not match. Input: an absolute `page_file`
plus its caption from the prior manifest. Fields: `content_class` (exactly one of
`map` | `timeline` | `text-panel` | `collage-of-pool-photos` | `photo-not-in-pool` | `other`);
`regen_worthy` (bool — true only for clean map/timeline graphics, always false for classes
re-planned from the pool anyway); `note`. Output one file; `page_file` as a BASENAME exactly as
it appears in the usage map, with key normalization stated in the schema.

## Template 4 — Variant vetting (flag broken, don't pick favourites)

Unit: a generated variant of ONE known real source; the protocol states the reference
composition explicitly. Fields: `identity_ok` (same people/faces/poses — the fantasy addition
is expected, a distorted face or a missing/extra person is not); `landmark_ok`;
`{{USE}}_suitable` (e.g. reads well as a SMALL collage tile: clear silhouette, distinct style,
not a near-dup crop); `note`. One entry per input item, same order, `item_id` copied verbatim.

## Template 5 — Creative pass (bounded proposal generation)

Unit: one chapter's KEPT photos (thumbnails + each keep's triage reason), one dispatch per
chapter. Binding constraints, verbatim: the base must be a provided keep from THIS chapter;
preserve the people and add exactly ONE fantasy element; stated tone (warm, playful, no
horror); one line per concept; **at most 2 proposals, and 0–1 is expected — no quota-filling**.
Plus one `coverage_note`: which family members appear a lot versus little (an observation, not
a proposal — this is how "one parent is under-represented" surfaced).

## Template 6 — Spread audit (rendered-page critique)

Unit: one rendered spread preview (composer or print). Fields: per-slot `overlap` /
`covers_face` / `crop_cut` booleans with the affected subject named, a `coherence` verdict on
whether the page's images belong together (time gap, scene), and one-line notes.
This fleet's verdicts were made AUTHORITATIVE scene-truth: the five pairings it declared
incoherent were dissolved and blocklisted so the packer could never re-form them.

## Dispatch + validation checklist (all fleets)

- [ ] `PROTOCOL.md` frozen on disk; `--verify-protocols` passes (the example validates against
      the real schema checker; the ≤15-line cap note is present; the validator self-tests).
- [ ] Batch/input files on disk with absolute paths and an explicit `result_path`.
- [ ] Judges dispatched in waves (~10 parallel), disjoint result files, the single-writer
      exception logged in the journal each time.
- [ ] `--verify-results`: every expected file exists, parses, is schema-valid; malformed ⇒
      re-dispatch that unit only.
- [ ] The downstream merge is script-owned and single-writer; ORCH reads verdicts, never
      renders the pixels.

---

# Part 2 — Executor packet shape

Every worker dispatch carries these blocks, in this order:

1. **Boundary.** The exact files the worker may write, as absolute paths. Everything else is
   read-only. (This boundary is what let a worker correctly REFUSE a scope-expanding message
   sent mid-task — lessons G1. Never send a new feature into a running, narrowly-bounded task;
   dispatch it fresh.)
2. **Context, from files only.** Point at `plan.md`, the journal range, and the record files —
   never a prose summary of state the worker can read itself. Fresh planners get files only,
   no conversation.
3. **The job**, in numbered steps, naming the frozen contract each step serves.
4. **Frozen validation.** The literal command to run, with all arguments, and the exact pass
   criterion. Decided BEFORE the work. The worker implements thresholds, never tunes them.
5. **Escalation clause.** "If this packet contradicts a frozen validator or a decision in
   plan.md, STOP and report — do not guess." Every stop in the reference run was correct.
6. **Report shape.** did / surprises / deviations / validation_first_try / retries, capped
   (≤15 lines for vision agents). Deviations must be named, never smuggled.
7. **Hard prohibitions** for browser packets, verbatim every time: never click
   order/checkout/payment/coupon anything; never accept terms or dialogs beyond the editor's
   own save/upload flows; never modify browser settings; never touch other tabs.

The orchestrator then RE-RUNS the frozen validation itself in a clean shell before accepting,
and writes a journal entry with tokens, retries and the audit verdict.

---

# Part 3 — Gates for the two-engine problem

The builder tool (a JS composer in a browser) and the print engine (Pillow, centimetres) are
TWO IMPLEMENTATIONS OF ONE GEOMETRY. These gates keep them honest. Each is additive: the later
ones exist because the earlier ones passed while a defect was visible.

The reference implementation of G1–G4 was a ~1400-line `verify_wysiwyg.py` too tightly bound to
one product's UI to ship here; what follows is its full specification.

## G1. WYSIWYG fidelity harness

Drive a real browser (Playwright), extract each composer tile's rendered box, and compare it
against the renderer's own rects for the same spread.

- Compare **centre, width, height, rotation, border-box, layer rank, and safe containment** —
  not just position. Tolerance: 1.5% of spread width (achieved: worst 0.23%, typical
  0.09–0.12%, i.e. ~0.5–0.7mm on a 60cm spread).
- **Pair tiles by GEOMETRY, never by z** — pairing by the same field you are validating is
  circular and hides exactly the ordering bugs you are looking for.
- **Seed the harness two ways.** A harness that seeds itself from the export is structurally
  blind to export-omission bugs. Add the product's real "load JSON" import path (this exposed
  an element 1.29cm / 2.14% of a spread from where it printed; 0.11% after the fix) and
  hand-built synthetic state.
- Cover every layout kind, and specifically these case classes, which a naive sample misses:
  **rotated**, **bordered/matted**, **overlapping**, **near-edge**, **imported**,
  **hand-rotated**. Add synthetic spreads for them in a second browser instance.
- A case the harness cannot build must **FAIL, not skip** — a silent skip turns a green run
  into a lie.
- Adapt measurement to display scale when the UI rescales the canvas; never weaken the
  tolerance to accommodate a UI change.
- Sample size is a real quality dial, grown by case class: 19 → 30 → 40 → 58 → 64 → 69 elements.

## G2. Absolute containment assertion

Assert on BOTH sides independently that every photo tile lies fully inside the page safe box,
including its border box and rotation bbox. Without this, mutual agreement excuses a shared
violation. Deliberate bleeds (full / span / margins presets) are exempt **per tile**, never per
page — and the exemption list is imported from one module by both engines.

## G3. Sentinel-mask trim gate

Render each spread on the real print canvas with every photo tile painted as an **opaque
sentinel mask**, and overlays in a separate sentinel. Then assert, per tile:

- clearance from the trim ≥ the configured constant (0.2cm), **not** mere absence of ink;
- zero "flush-run" mask pixels against the page boundary (the fingerprint of clipping);
- mask area within tolerance of the expected rotated, bordered rect.

Do not use a colour diff against a tiles-removed control: white mats on white paper barely
differ, and — the real killer — a binary in-band test passes at 0.25mm of clearance while the
guillotine eats it. Always include a **negative proof**: with the clearance constant set to 0
the gate must fail the tiles the old gate passed (11 of them, here).

## G4. Mat-band gate

For every matted/bordered tile, redraw it unrotated on a magenta sentinel **via the real draw
path** and require pure paper a third of the way into all four mat edges, with the depths read
from the mat constant so a renderer that forgets the mat cannot define the check away. Negative
proof: reinstating the old clip must fail exactly the known tile.

## G5. Structural content gates

Where a product promise is absolute, enforce it structurally rather than by promise. A
zero-text album uses a `TEXT_DRAW_CALLS` counter inside the only text-drawing function; every
render and PDF entry point resets it, performs a LIVE full-resolution render pass, and
hard-fails unless the counter ends at 0. Review sheets are counted separately so they can never
be mistaken for album pages. Ship the policy as a flippable switch and assert the switch state,
not a hardcoded count.

## G6. Freeze-then-loosen (changing a geometry constant safely)

1. Prove the precondition: per-spread sha256 of the rendered PNGs before vs after baking the
   currently-clamped rects into the plan. All digests must be IDENTICAL.
2. Only then relax the constant. Re-render; digests must still be identical and the
   rect-vs-frame delta < 1e-9 ⇒ zero tiles moved; the clamp is now a strict no-op with headroom.
3. Have the verifier RE-DERIVE the baked rects from the user's untouched export, so the freeze
   is proved rather than trusted.
4. Move every gate that reads the OLD constant at the same time, or a check keeps policing a
   band the law no longer enforces.

## G7. Builder-tool build gates

The tool generator's own `--verify` (236+ checks in the reference run) should: byte-compare the
embedded data island against the frozen draft JSON; **import the renderer** to prove the JS
mirrors its constants; decode every embedded thumbnail and assert asset-specific properties
(e.g. zero fully-transparent pixels inside a badge's fitted ellipse); assert the size budget;
and assert structural invariants of the code itself (e.g. that a move operation's body contains
no clamp call and that exactly one clamp function exists in the file). A Playwright SMOKE run
then exercises the real product on BOTH touch and mouse profiles, and must assert **the actual
reported bug**, not a proxy for it.

## G8. Round-trip integrity gate

Export → import → export must be a fixed point. Assert every non-geometry key byte-identical,
and judge geometry by containment (the export stores clamped values, so near a boundary
byte-equality is fragile). Separately, enumerate the schema and assert there is no key written
but never read, and none read but never written.

## G9. The periodic adversarial audit

Every few phases, commission a fresh-eyes audit of the builder against its own artifacts:
script-reproduced defects, severity-ranked, plus a feature-gap comparison against commercial
editors in the same category. Convert every repro into a permanent regression test. In the
reference run this surfaced three data-loss / wrong-print defects that all internal gates had
passed, and it is where auto-fill and alignment guides came from.

---

# Part 4 — Asset pipelines

## Ingestion pipeline (new photos from outside the original pool)

Two paths, both needed:

- **Drop folder** (`assets/incoming/` + `scripts/ingest_incoming.py --scan/--ingest/--verify`):
  EXIF transpose, `taken_at` extraction, sha256 idempotency so re-running is safe, DPI computed
  at the two target print sizes, a capped FSRCNN upscale (skip when the min edge is ≥2400px or
  the image is >12MP — unconditional upscaling OOM'd on large sources), and a manifest.
  `--scan` must be able to report "0 files ready" without changing anything.
- **In-tool upload**: an external image is registered into the pool dict under a synthetic id so
  every downstream feature works unchanged, chipped honestly as not-yet-saved, with native px
  still driving the DPI badge, and exported under an `external` flag so placements reconcile
  against the dropped files later.

## Sticker pipeline (subject cutouts) — `scripts/make_sticker.py`

`rembg` (`u2net_human_seg` for people, `u2net` for objects), models cached locally — no network.
**Segmentation only**: RGB is copied verbatim and only alpha is authored, so faces cannot
change. Variants: plain, white-outline, drop-shadow. QA gate: RGBA, transparent corners, 5–95%
coverage, no opaque-rectangle failure. Ship nothing that amputates a hand, foot or face. Expect
and report the hard cases honestly: transparent liquid and glass rims go blocky; a flat wall
with no figure/ground yields 1.9% coverage and must be deleted; `human_seg` merges a subject
with nearby bystanders. The models fixate on people, so vehicles need an opt-in, hand-authored
polygon assist (`--exclude-poly` / `--subtract-poly` / `--union-model` / `--close-px`) added
**additively**, so existing calls are unaffected.

## Decoration pipeline (generated ornament, safely) — `scripts/cut_decor_sheets.py`

NEVER send a rendered album page to a generative model — it repaints the people's faces and
caps output at ~2048px. Instead:

1. The model generates ONLY decorative elements on plain white: motifs, connectors, scrapbook
   furniture, seamless patterns. No text, no people.
2. Cut them LOCALLY and deterministically. Expect to switch algorithms per sheet: grid-cell
   projection profiles for sparse line art (connected components under-segment dashed
   connectors), connected components for dense rows. Patterns stay opaque as background tiles —
   they are fills, not cutouts, so the transparency gate is skipped for that set only, and
   explicitly.
3. Composite at full resolution in your own renderer, with the user controlling size, rotation,
   position, opacity and z, above or below photos.

Gate on the coverage range, no white halos, no clipped ink, no text, no people.

## Badge / stamp pipeline (art that is already a shape) — `scripts/cut_day_stamps.py`

Ask for ONE design per image (lessons A1). Cut by the design's own drawn shape: a generic grid
split by weakest column then weakest row (works whether cells have a white gutter or touch), a
tight non-white bbox, an ellipse fit +1px so the rim's antialiasing is never shaved, and one
feathered alpha (sigma ~1.5px) cut from the RAW sheet RGB so the interior is opaque by
construction. Gate: no transparent pixel inside 0.95 of the fitted ellipse, corners alpha <20,
opaque area within 3% of πab. Record the fitted centre and both semi-axes in the manifest.
Report a per-design face-size estimate — and label it a heuristic if it is one — and put a 100%
face-crop row in the preview so the user judges faces visually, not numerically.
