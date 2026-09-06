# Reusable protocols, packets and gates

- **Part 1** — the vision-fleet protocol family (delegated image judgment at scale).
- **Part 2** — the executor packet shape.
- **Part 3** — the gate machinery that made the print engine trustworthy.
- **Part 4** — the asset pipelines (ingestion, stickers, decorations, badges).
- **Part 5** — building the book inside the vendor's editor.
- **Part 6** — the cover, the spine and the wrap (a different product from the interior).

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

## G10. Ground, source and rotation — what G1 cannot see

G1 compares rects, padding, z and angle. All four can AGREE while the print is wrong, because
they only describe **where the picture is**. Add these four assertions, each of which caught a
defect that shipped past a green G1:

1. **Drawn frame width in millimetres of paper**, per side, per bordered tile. A tile whose picture
   filled part of its frame read as a 0.50 mm hairline on screen and printed a 17.04 mm white mat.
2. **Ground opacity.** Assert explicitly whether each engine paints anything behind the picture.
   The composer element had no background (the image beneath showed through); the renderer painted
   opaque paper. Tiles should alpha-composite and be transparent except for a real mat.
3. **Which source file each engine opened**, and the **source aspect after EXIF transpose**. A
   substitution applied on one code path and not another means the two engines are drawing
   different pictures at identical rectangles.
4. **Rotation mod 360, with legacy fields planted.** A slot carrying a legacy `rotate_deg` beside
   its `rot` made the renderer pre-rotate pixels and then rotate again — net 180° and a transposed
   aspect — while the composer had never heard of the legacy field. Define a tile's rotation in
   exactly one function, and give the harness a case with a legacy field the engine must ignore.

## G11. Visibility gate — "it is in the plan but it is not visible"

Every numeric gate is blind to an element that paints nothing: a slot never emitted has no rect to
disagree about, and a slot buried under the picture it sits on has a perfectly correct rect. Ask
the two questions they cannot:

- **Identity and position**, re-derived from the user's own export through the very same shared
  law the composer uses — a fallback to a default position counting as a FAILURE, not a pass.
- **Visibility**: render the spread twice, once with the element lifted out, and require the two
  renders to genuinely differ **inside that element's own rectangle**. Prove teeth both ways — the
  pre-fix plan must fail naming the affected spreads, and moving an element under its neighbour
  must fail with "0.0% of its own rectangle".

Note the sibling rule: an edge gate answers "is it inside the paper", never "can it be seen".
Occlusion and the fold need their own checks, and an exemption must be declared **with the rect
that justifies it** so it goes stale automatically.

## G12. Human-rule gates (turning the owner's sentences into checks)

Run an offline face detector over the **real drawn spread**, not over source files:

- **Fold on a face** — flag any face crossing the fold or within ~5 mm of it, on every spread
  carrying a full-spread image. **Report, do not block**: detection is heuristic and clearing a
  seam costs resolution, a trade only the owner may make.
- **Trim cuts a person** — convert the vendor's trim into plan space (here 5.0 mm of vendor space
  = 0.5051 cm of plan space), cut both strips out of the real drawn sheet, and make a face in a
  strip **fatal**. Report skin-gamut share beside it as the only honest body signal, with the
  album's own paper colour excluded or every margin reads 100% skin. Assert the two constants the
  law uses against the vendor mapping's own numbers, so the law cannot police a strip nobody cuts.
- **Frame-ring clipping, four-sided** — measure every bordered tile's frame, its ring and its full
  drawn bbox against **both** edges that can cut (your own sheet and the vendor's trim), name
  which edge cut, and check all four sides: a fix that trades the left edge for the right edge is
  not a fix.
- **Re-run every one of these against the FIX**, not just against the original defect.

## G13. Derivation gate — against downstream staleness

A frozen plan records the owner's **variant choice**, never which bytes to print. One
`resolve_asset()` function turns a plan entry into a file to open, and every consumer calls it.
Then gate the chain: walk artwork → master → staged upload copy and demand **byte identity at
every link**, and assert the plan's own sha256, its slot set, the resolved print file and the
placement of every slot against the *current* plan. Give each plan chain its own map file — two
plans sharing one output filename is how a stale set hides. Prove teeth on injected faults: a
zero-byte file, an edited placement, a bogus orphan.

## G14. Vendor-space mapping gate

Your safe-area law lives in plan space; the vendor's trim lives in vendor space. Write the mapping
as **one function**, assert that every gate reading a trim constant reads it from that function,
and re-check every tile after conversion — a non-bleed tile parked flush on your safe line can end
up outside the vendor's sheet. Assert the mapping is **uniform** (no aspect moves) and print what
it costs on each edge. Separately, assert the **cover** canvas's own scale rather than inheriting
the interior's, and assert the delivered wrap's dpi over the **measured** sheet size.

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

---

# Part 5 — Building the book inside the vendor's editor

The plan is finished, the print files exist, and now every one of them has to end up in a web app
you do not control. This is the part of the run with no undo, so it has its own method.

## 5.1 Work in a DUPLICATE project

Duplicate the project in the vendor's own UI before touching anything, and take a **baseline
snapshot of every canvas's object geometry** before the first change. The whole run then stays
reversible in one click, and you have something to diff against.

## 5.2 Establish what the editor can actually be told

Recon first, and write the answer down as a sentence. Here it was: **the editor accepts only
axis-aligned boxes — W, H, X, Y in centimetres. No angle field, no crop field, no zoom field.**
Everything else must be baked into pixels before upload or it cannot be expressed at all. Also
establish: accepted upload formats and size limit, whether uploads are one-file-at-a-time, whether
there is autosave (assume not), whether "apply template" is undoable (often not), and what the
purchase actually covers.

## 5.3 Bake, don't fight

A baked tile is **the whole drawn appearance** — crop, zoom, border, rotation — so every placed
object is angle 0. Count how many slots have a frame aspect their file does not before you decide
that rotation is your only problem; in this run 27 slots were rotated and **88 would have been
squashed** by typing the plan's W/H onto the raw file. Where tiles overlap, bake them **together**
into opaque groups over a full-sheet background object rather than relying on the vendor's alpha
handling (see lessons D11). Bake at ~3× the renderer's working canvas.

## 5.4 Prove ONE unit end to end before committing all of them

The mandated order on a single spread: **place → type → save → reload → read back**, and require
0.0 mm error before doing the other N−1. Save deliberately after every batch, and re-verify
**after** the save, not before it — the read-back is the assertion, and the object model after a
server-confirmed save is the only state that matters.

## 5.5 Verify the canvas ORDER against the labels

Read the DOM order and compare it to the visible page labels. In this run the canvas DOM order was
**REVERSED** — DOM index 0 was the LAST spread and DOM index 37 the first — so `dom_index =
37 − canvas_index`. The recon had it right about the count and wrong about the direction, and
placing in DOM order would have printed the whole album back to front. The same class of error
appeared twice more: right-page-first ordering in an RTL book, and a proof PDF whose page N was
spread index N−2. **Pin down every index↔label mapping explicitly and write it down.**

## 5.6 Key objects by geometry

Vendor ids and DOM input indices are regenerated on save. Key by **canvas index + geometry in cm
rounded to 0.01**, assert a payload property unique per canvas (the image's natural pixel size, or
its aspect where the object hides the size), and record the server-assigned filename at upload
time as the only cross-session link back to your own file. See lessons D12.

## 5.7 The standing prohibitions

Nothing uploaded that was not planned, **nothing deleted**, nothing reloaded over unsaved work,
**nothing ordered and nothing paid**. Stale library images are listed for the owner to delete
himself, as a separate authorised act. End every session log by restating what was and was not
done, and leave a resume point driven entirely off the map file.

# Part 6 — The cover, the spine and the wrap

Treat the cover as a **different product** from the interior. Nothing that gates a page gates a
wrap.

1. **Measure the cover canvas's own scale.** Do not inherit the interior's px/cm. Read the editor's
   property panel back against a known object and derive px/cm to five figures; a physically
   larger sheet displayed at the same screen width must show at a smaller magnification, and that
   discrepancy is the tell. Getting this wrong cost 7.7% of linear scale here — a wrap rendered at
   283 dpi instead of 306, caught one step before printing.
2. **Establish the spine width** from the page count and binding, and reserve it. A spine grep that
   returns zero hits across your codebase while two cover masters already exist is a finding.
3. **Map the turn-in / wrap masks** and size the artwork so nothing you care about goes round the
   board.
4. **Map the vendor's printed furniture** — barcode, logo, legal text — as a hard **no-content dead
   zone** declared to whatever packs the artwork. It prints white-backed OVER your picture.
5. **Ask the owner which panel is the front.** Circumstantial signals are not proof and a wrong
   cover is a reprint.
6. **Run the face check on the delivered wrap**, in true millimetres, against every protected zone
   at once — barcode, spine band, all four turn-ins — and report the nearest-face clearance per
   zone as a number for the owner to accept or reject.
7. **Place one continuous wrap image, not three panels**, where the editor fills a frame from a
   single file: three panels add two seams and two more chances to mistype a number, for nothing.
