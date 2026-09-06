# Lessons — hard rules, with the evidence that bought them

Every rule below cost real rework on a full album run (a five-day family trip, ~480 pool
images, a 30×30cm layflat book of 76 pages). The clause after each rule is the evidence,
with the actual numbers. Written for an agent who has none of that context: **prefer the
number to the adjective.**

---

## A. Resolution, DPI and print honesty

**A1. When generating art that will be cut into N pieces, ask for N images, not one sheet of N.**
The sheet divides your real resolution by N, and upscaling cannot restore a face. — The image
model returned 1254×1254 sheets of 4 badges, so each badge carried ~570 real px and a face
inside it was ~70px; a ×2 upscale to 1166px only smoothed it. Regenerating one design per
image put ~1254 real px per badge and faces at ~142–151px (about 2×), and all 15 were
accepted on the first generation.

**A2. Compute DPI from NATIVE pixels, never from the upscaled file.**
An upscale inflates the number and flatters a weak image. — One ride photo's true native is
1419×1109; its ×3 upscale (4257px) read 180 DPI at 60cm while carrying ~60 DPI of real
detail. When a `native_width_of()` helper was finally added, **65 of 456 pool images were
overstating their DPI**, and the orchestrator had to retract its own published claim that a
square page was 319 DPI — honestly it is 1254 real px = 106 DPI.

**A3. Resolution floors are content-tiered, not flat.**
Photographic content fails below **120 real DPI**; generated/AI art fails below **90** (it is
smooth and painterly, so interpolation is far less visible). Print the tier per slot for
auditability. — A flat 150 real-DPI gate would have FAILED 27 of 83 already user-approved
slots. Apply the gate HARD only to newly built spreads; inherited approved slots get an
advisory worst-first table, never a silent resize.

**A4. Generative models do not add resolution.**
Chat-based image editing capped at ~1.5Mpx and returned 1254×1254 for every variant
regardless of what was asked; on faces, regeneration means identity drift. A model-composed
album page is 106 real DPI on a 30cm page versus 305 for a locally composed 3600px one.
Upscaling an AI output for print is legitimate only as "sparing the printer's resampling" —
say so plainly, never as detail recovery.

**A5. Official venue photos (ride cams, park cams) are low-res and framed.** Remove decorative
frames by CROPPING only, never regeneration — one venue frame was ~40% of the pixels
(1381×1139 → 976×599). Where the template paints decoration *into* the photo (vines drawn
over a subject's hand), no rectangular crop can remove it; find a clean source instead of
inventing pixels.

## B. Validation and gates

**B1. Never validate a white-on-white property with a colour diff; and assert CLEARANCE, not
mere absence.** — A trim gate diffed the printed spread against a control with tiles removed.
It reported "0.000cm ink in the trim band" for a framed print that was visibly cut: the clamp
is translate-until-touching, so it parks every tile with 0.000–0.025cm of slack, the binary
in-band test passed with **0.25mm** of clearance, and the guillotine tolerance ate it. Fix: a
`TRIM_CLEARANCE_PX = 8` (0.2cm) inset baked into the single safe-box law, plus a per-tile
**sentinel-mask** gate. Negative proof is mandatory: with clearance 0 the new gate fails all
11 tiles the old one passed.

**B2. "The two implementations agree" is not "the result is correct."**
A cross-comparison gate passes whenever both sides are wrong identically. Always add an
ABSOLUTE assertion beside the diff. — The fidelity harness reported worst-case 0.23%
agreement while two user-visible defects existed, because it paired tiles BY Z (circular) and
only ever compared composer against renderer. Rewritten to pair by geometry and to assert
absolute safe-box containment on both sides.

**B3. A geometry-level check can be green while a visible defect exists — the final gate must
look at actual pixels of the actual printed page.** Rendered-page checks, not just data
validators. — Serial patches kept regressing under passing validators; the mat and trim
defects all lived below the geometry layer.

**B4. Never let a per-page exemption silence per-tile checks.** One full-bleed tile marked its
WHOLE PAGE bleed-exempt, so an entire page was never checked at all.

**B5. Keep judgment metrics OUT of mechanical validation.** — Coverage targets ("≥50 of 65
pages matched, ≥70 distinct images") were frozen into `--verify` and produced an honest FAIL
of a *working* matcher at 30/65 and 42 distinct: the content genuinely did not exist in the
pool (maps, timelines and text panels live only inside the old pages). ORCH logged it as its
own spec error. `--verify` = schema and consistency; quality numbers are reported and judged
at acceptance.

**B6. Bound repair families.** 3–5 leaves, then accept as documented best-effort with the
ceiling written down (the usage matcher closed at 30/65 pages after three leaves; the packer
at five). No unbounded pixel-tuning.

**B7. Verify the mirror by importing, not by eye.** When one law is implemented twice (Python
renderer + JS composer), the tool's `--verify` should IMPORT the renderer and prove numeric
equality — that is how the outset/bbox and clamp functions stayed in sync. Shared exemption
lists (which layout kinds may bleed) must likewise be imported from one module by both
engines; two hand-maintained copies drift silently.

**B8. Every new gate needs a negative proof.** Disable the fix and assert that the gate now
fails exactly the items it previously passed. A gate that has never been seen to fail is not
known to work.

**B9. Check the ORACLE before believing the implementation.** An assertion comparing against
pure white failed forever because the product's paper renders as (247,244,238). A wrong
oracle is indistinguishable from a wrong implementation.

**B10. A harness that SKIPS a case it cannot build turns a green run into a lie.** An
unbuildable synthetic case must FAIL, not skip.

**B11. Grow the harness sample by case class, not by count.** 19 → 30 → 40 → 58 → 64 → 69
elements, as rotated, bordered, overlapping, near-edge, imported and hand-rotated cases were
added. Every defect the users found was a *missing case class*, not a too-small sample.

**B12. A harness that seeds itself FROM the export is structurally blind to
export-omission bugs.** Add a second seeding path — the product's real "load JSON" import
flow, and hand-built synthetic state. Seeding through the real import path exposed an element
sitting **1.29cm (2.14% of a spread)** from where it printed; after the fix, 0.11%.

**B13. Verification must ask both halves of the question** — "does the fix preserve the
design?" AND "does the surface still work?" — otherwise the fix ships as the next regression.

**B14. Enforce absolute product promises structurally, not by promise.** A zero-text album
uses a `TEXT_DRAW_CALLS` counter inside the only text-drawing function; every render and PDF
entry point resets it, performs a LIVE full-resolution render pass, and hard-fails unless the
counter ends at 0. Ship the policy as a flippable switch and assert the switch state rather
than a hardcoded count.

**B15. A cross-engine diff validates WHERE the picture is — never WHAT the tile paints where the
picture is NOT.** This is the single most expensive blind spot in the whole pipeline. The
fidelity harness compared centre, size, rotation, border box, layer rank and containment, and
every one of them AGREED — while two defects shipped. (a) A tile whose picture filled only part
of its frame at zoom 65: the composer's tile element had **no background**, so the image beneath
showed through, while the print engine painted the frame **opaque paper** — 0.50 mm of drawn
frame on screen versus 17.04 mm on paper, and the same silent bug was painting white mats on
five other slots nobody had complained about. (b) A slot carrying a legacy `rotate_deg: 270`
beside its `rot: 90`: the renderer pre-rotated the source pixels on load and *then* applied
`rot`, netting 180° and a transposed aspect, while the composer had never heard of the legacy
field. Rects, padding, z and angle all matched, because the disagreement was in **which source
pixels each engine was fitting**. Add to every fidelity harness: the drawn frame width in **mm of
paper**, the **ground opacity** of the tile (transparent vs painted), the **source aspect after
EXIF transpose**, the **identity of the file each engine opened**, and rotation compared **mod
360** with a planted legacy field the engine must ignore.

**B16. "Correct rect" and "visible" are two different assertions.** Two whole defect classes were
elements that existed in the plan, at the right rectangle, and painted nothing a reader could
see: an inset emitted *underneath* the very picture it was meant to sit on (0.0% of its own
rectangle visible, rect perfectly correct), and frame rings hidden beneath overlapping tiles in
scrapbook layouts (worst side 0%). Every numeric gate is structurally blind to this — a slot
never emitted has no rect to disagree about, and a buried slot's rect is exactly right. The gate
is to render the spread **twice, once with the element lifted out**, and require the two renders
to genuinely differ inside that element's own rectangle. A plan entry that paints nothing is a
defect.

**B17. An edge gate answers "is it inside the paper" — never "can it be seen".** Visibility also
needs the **fold** and **occlusion**. An independent pixel audit (63 bordered tiles, all 252
sides, 60,480 samples) agreed with the arithmetic gate exactly, and then found the two things the
gate did not model: a ring pushed into the binding-creep band, and 13 sides occluded by
overlapping tiles the owner had composed deliberately.

**B18. A check written to police a decision must be run against the FIX for that decision.** The
first pan that cleared a person out of the trim strip was immediately FAILED by its own new
check: panning that far brought a background face into the *opposite* strip (confidence 0.77 and
0.68). The fix is a change like any other, and here it was the change that broke the rule.

**B19. A fix that trades one edge for the opposite edge is not a fix — check all four sides.** A
+3.36 mm nudge that rescued a frame's clipped LEFT ring pushed its RIGHT ring to 3.4 mm from the
fold, inside the binding-creep band, where it had been 6.8 mm clear. The write-up disclosed the
drop shadow crossing the fold and failed to state that the ring now lived in the gutter. Only a
four-sided check could see it, and the honest form of such a check names **which edge** cut.

**B20. Declare an exemption together with the fact that justifies it.** Three full-page bleeds
legitimately paint their frame ring off the paper; the exemption records the rect that makes that
legitimate, so the exemption **stops applying the moment such a tile stops bleeding** — and an
exemption pointed at a tile that no longer bleeds FAILS as stale. Related: a "documented
interpretation" waiver that excused any page of a spread handed a free pass to the two pages it
was never written about. **A blanket exemption is where a lost picture hides.**

**B21. Audit a gate periodically with an independent method.** Pixels against arithmetic, a fresh
auditor against the author. Agreement is evidence; the disagreements are the findings — and in
this run both findings the audit produced were real.

## C. The builder tool and the print engine

**C1. A builder UI and a print renderer are two implementations of one geometry — diff them
automatically or they WILL drift.** — The export→plan translation READ the builder's geometry
instead of CARRYING it: a 28.8cm framed photo printed as 30cm full bleed, a preset's square
aspect became 25.2×18.9, border style vanished, and every rotation was dropped so the user's
scatter tiles printed bolt upright. Fix: `builder_geometry` rides verbatim on the slot and is
drawn by a line-for-line port of the composer's arithmetic.

**C2. If the tool computes something per-spread, the tool must EXPORT it.** — One preset's
slot table lived only in the tool. An untouched tile arrived at the renderer with no rect,
fell through to full-bleed, and printed as a full-page backdrop under its neighbour. Same
class of bug: `rot` was absent from every export until r4 (11 tiles).

**C3. One clamp law, one place.** The composer clamped tiles to the SHEET (0..1) while the
renderer printed to a PAGE smaller by the binding margin — **12 of 14 builder tiles were
outside the safe box, worst by 1.1cm**. Fix: `clampToSafe()` (JS) mirrors
`builder_clamp_safe()` (Python), border box and rotation bbox included, with full/span/margins
presets exempt so deliberate bleeds still bleed.

**C3a. The clamp must operate on the full DRAWN extent**, not the content rect: mat/border,
outline ring, drop shadow (offset + blur reached 11/9/27/29px here) and the rotation bounding
box.

**C4. The clip box is part of the geometry.** — The renderer implemented cover-fit by scaling
the picture past the mat's inner box and clipping at the tile's BORDER box, while CSS
`overflow:hidden` clips at the PADDING box; the overflowing axis painted straight over the
white mat (top inset −1.400cm on one tile). Every in-flow matted tile was losing mat (tops
1.441 / 0.979 against a designed 1.50) — only one crossed zero and became visible. Gate:
redraw each matted tile on a magenta sentinel via the REAL draw path and require pure paper
a third of the way into all four mat edges, depths read from the constant so a renderer that
forgets the mat cannot define the check away.

**C5. Special-case layout kinds breed missing controls — model ONE object with defaults.** —
"Full-bleed image" and "collage tile" were separate kinds, so full-bleed images had no
size/zoom/crop/border controls. Making every placed image a tile in a 1-slot layout with
full-bleed as the DEFAULT RECT left untouched spreads exporting byte-identically, and the
dead-end path disappeared.

**C6. Never weld a style into a preset — expose it with the current value as the default.**
The white polaroid border was hardcoded into the scatter presets; it became a resolution chain
(tile > page > preset default) with defaults unchanged, so nothing shifted silently.

**C7. Model the album as ordered blocks with parity constraints, never as a flat page list.**
Binding fixes page pairing physically, so moving one page re-pairs everything downstream. The
tool must PRICE the move — swap (zero reflow, so offer it FIRST) / local merge / full cascade
with the N affected spreads listed / park as a free page — with a preview before apply and one
undo step. Never hide the cost, and never fail at print time. The page budget is fixed (76
here), so every insert must be paid for by a free page.

**C8. The live canvas must stay visible while the user reaches the controls.** Pinned canvas +
scrolling inspector (the ordinary Figma/Canva pattern): capped to ~45vh on phones, two-column
with the canvas on the reading-direction-correct side ≥1100px. Proof the smoke test must
assert: with the LAST control row in view, the composer's box is 100% inside the viewport
(170/170px @390×844, 355/355 @1440×900). Beware the side effects: a sticky bar eats synthetic
clicks, `scrollIntoView` parks rows underneath it, and its measured height becomes load-bearing
for other features.

**C9. Smoke-test both input models.** Three real touch defects shipped invisible to a mouse
profile: `preventDefault` on pointerdown suppressed the synthesized click; a bare `<img>`
thumbnail was dead under WebKit delegated-click; a 15% inset was a 29px tap target. Also: a
sticky topbar intercepts synthetic clicks, and scrolling inside a tap's first event moves the
page under the synthetic click (defer the reveal ~140ms).

**C10. Freeze before loosening.** Stored geometry may be PRE-clamp, so relaxing a constraint
MOVES things. — Adopting the vendor's real 4.4mm margin would have slid **11 of 15 tiles**
outward by 6.6mm and 9.0mm into the gutter, because they sat flush on the old line with
0.00mm slack. Ruling: bake today's clamped geometry into the plan first, prove it with
per-spread sha256 of the rendered PNGs (all digests identical), THEN loosen — so the change
is pure future headroom and zero tiles move. When you loosen a constant, move every gate that
reads the OLD constant too, or a check keeps policing a band the law no longer enforces.

**C11. Replace a physically wrong hard clamp with a non-blocking warning where the risk is
aesthetic, not mechanical** — e.g. a people-photo near the binding fold on a layflat book.
Join the warning to a content-type table so it fires only on content that matters.

**C12. Legacy "usable size" constants coexisting with the true page size are a bug factory.**
Fix at source, and list explicitly which legacy paths you deliberately did NOT touch, and why.

**C13. A guard added to prevent losing work can remove the ability to DO the work.** A seeding
function was the only writer of a panel's scope, so blocking re-seeding left nearly every
rebuild panel blank. Give state initialization its own path, and add a derived check that the
panel is non-empty for EVERY card.

**C14. A feature scoped to the SPREAD when the user thinks per-PAGE is structurally
unrepresentable, not a labelling bug.** Re-express it as an ordinary per-page preset, and
export, import, print and the harness understand it for free.

**C15. Re-derive user-facing labels from live state.** Headings, counts and "placed/unplaced"
badges derived from the frozen plan go stale the moment the user rebuilds — a badge that falls
back to the plan will report a removed photo as placed. Any "live" tab must be rebuilt from
current state on each open.

**C16. A self-contained tool that embeds thumbnails makes the editing view strictly WORSE
than the printed product** (a 240px thumb blown across half a spread). Fix with a dual source:
probe the real file off-DOM, swap the visible element only after a successful decode, keep the
embedded thumb as the fallback, and show an honest chip saying which source is live. Measured
cost: +4% navigation time, +1.2MB heap.

## C-bis. Export / import round-trip integrity

**R1. Audit the export schema for asymmetry**: fields written but never read back (rotation
was silently lost on every round-trip), fields read but never written, and fields the tool
computes per page but never exports.

**R2. Compaction is data loss.** Dropping null holes from a slot array shifts every later
element and corrupts any z-order derived from array index. Preserve holes explicitly.

**R3. Restore must read every key the export writes.** An import path that ignored the
overlay/decoration key silently deleted all of it, while the print engine handled it fine.

**R4. Operations that MOVE content between containers should compute no rectangles at all.**
Move objects verbatim and let the single clamp re-measure against the new container's mirrored
safe box. Assert in `--verify` that the move body contains no clamp call and that exactly one
clamp remains in the file.

**R5. Near a constraint boundary, byte-equality is a fragile assertion** (the export stores
clamped values). Assert every non-geometry key byte-identical, and judge geometry by
containment.

## D. Vendor reality

**D1. Measure the vendor's real spec; do not assume standard print margins.** — Assumed 11mm
outer / 9mm fold / 11mm top-bottom; the editor's own dashed guide measured **8px ≈ 4.4mm on
all four outer edges**, with NO bleed line and ZERO extra fold standoff — about 2.5× too
conservative. The composer's "28cm usable" readout was simply wrong against a 30cm page.
Recovering it gave **+1.56cm per page** (28.00 → 29.56cm safe box), and two fold-pinned tiles
gained a real 9.00mm clearance. The vendor had no file-prep page at all; the numbers came from
measuring canvas pixels — with the remaining unknowns (bleed_mm, the quality-% threshold)
listed as unknowns rather than invented.

**D2. Recon the editor before making typography/collage decisions.** Outcomes that reshaped
the build: ~20 fonts with verified RTL → type captions in-editor rather than baking them; 140
mixed-size blank templates with fully free canvas boxes → build collages natively; JPEG-only
uploads → a conversion step; NO autosave → save deliberately after every batch; an empty
accessibility tree → automate by coordinates + JS DOM queries; template-apply is NOT undone by
the undo button (revert = marquee-select its boxes and delete). Also confirm what the PURCHASE
covers — an 80-page plan met a 24-page project.

**D3. RTL books: reading direction ≠ upload order.** The vendor pairs pages 1-2, 3-4…; the
narratively-first element sits on the RIGHT page. Prove it with two spreads in the real editor
before mass placement.

**D4. Vendor quality warnings measure something else.** The editor's warning is a percentage
quality score, not a DPI threshold — do not treat it as agreement with your own DPI tiers.

**D5. Vendor space is not plan space — convert your laws into it and re-check every tile.** The
editor's printable spread was **58.40 × 29.70 cm**, i.e. two pages of 29.20 × 29.70, not the
"30 × 30" on the tin. Established by arithmetic, not guessing: it is not a uniform inset of
60 × 30 (the axes lose 16.0 mm and 3.0 mm, different), not a uniform scale (58.4/60 = 0.97333 vs
29.7/30 = 0.99000), and a 29.70 square page would imply a 2.8 mm spine that no premium layflat
has. Corroboration: under the old assumption two independently measured px/cm axes disagreed by
2%; under the true sheet they agree to 0.06%, and the editor's guide inset stops being two
numbers and becomes a uniform 4.37 mm. **The reading that makes independent measurements agree
AND implies a physically plausible object is the true one.**
Mapping the plan onto that sheet is one function — `X = 0.99x − 0.5; Y = 0.99y; W = 0.99w;
H = 0.99h`, uniform so no aspect moves, centred so the surplus splits evenly. The choice was
between the only two uniform scales: CONTAIN (0.97333) loses nothing but opens a 2.5 mm white
band top and bottom of every spread, a defect in a full-bleed album; COVER (0.99) fills the sheet
and pushes 10.0 mm of width off it. **State the cost plainly**: 5.0 mm lost at the outer trim
edge of each page, 0.0 mm top, bottom and fold; gained, nothing. And note the consequence — your
4.4 mm safe band lives in *plan* space, so a non-bleed tile parked flush on the safe line ends
0.7 mm outside the vendor's sheet and is **cut, not moved**. A green safe-box gate is measuring a
band nobody cuts unless you convert it.

**D6. Never assume the cover shares the interior's scale — measure the cover canvas itself.** The
cover geometry had been derived from its mask rectangles using the **interior's** px/cm. Reading
the editor's own property panel back against the same objects gave **16.207 px/cm on the cover
canvas** versus 17.462 on the interiors: the cover sheet is really **64.30 × 32.00 cm**, a uniform
**1.0774×** the figure in the spec — front panel 29.60 cm square (right for a "30 × 30" album),
spine 21.76 mm, turn-ins 14.90 / 12.00 mm. The geometry survived (the artwork fills the canvas
either way) but the **resolution did not**: the first wrap, rendered at 120 px/cm of the *wrong*
cm, is only **283 dpi over the true 64.30 cm** — 7.7% short. Caught one step before printing and
re-rendered at 130 px/cm = 7758 × 3861 px = 306 dpi. A larger sheet shown at the same screen
width must display at a *smaller* magnification — that discrepancy is the tell.

**D7. The spine, the turn-in and the wrap are a separate artifact class that no page-level gate
touches.** A `grep` for "spine" across the whole codebase returned **zero hits** while both cover
masters were already built: each assumed a clean half with no fold allowance, and the editor
models the spine as a hairline divider at the exact geometric centre. A real premium layflat
spine is 10–20 mm; taken out of the middle of the wrap, each half loses 5–10 mm at its inner
edge. Soft on a full-bleed photograph; on a collage whose inner **cell column** sits at the fold
it reads as an unevenly cropped tile. Turn-in masks (~1.4 / 1.1 cm at the panel origin here) hide
whatever wraps around the board. **"The PDF looks right" is not "the physical object is right".**

**D8. The vendor's own furniture is content — measure it and reserve it before composing.** The
vendor prints a **barcode + logo block, white-backed, OVER the artwork** on one cover panel. Mapped
into the back-cover collage's pixels it landed on the bottom-left corner and **obliterated four
detected faces** (skin-gamut share of the barcode footprint: 47.9% — it was half flesh). This is
not a trim question; nothing on that rectangle survives. Fix: re-bake the artwork with a declared
**dead zone** (6.03 × 1.30 cm plus a margin) so the packer puts background there, not people —
never "place it anyway". It was caught only because the barcode's rectangle had been measured a
day before there was anything to put under it.

**D9. Front/back handedness of a flat wrap is not a code question — ask the human who has held the
product.** Three circumstantial signals (which panel the barcode sits on, where the previous
project put its front-cover photo, the reading direction of the language) all pointed the same
way, and circumstantial is what they remained. Attempting to settle it by observation instead —
clicking the editor's 3D preview — **wedged the renderer for six minutes** and produced nothing.
Guessing here costs a reprinted cover; asking cost one message.

**D10. The editor may accept only axis-aligned boxes: W, H, X, Y in centimetres.** No angle field,
no crop field, no zoom field. Everything in the plan that is not an axis-aligned box therefore
has to be **resolved in pixels before upload, or it cannot be resolved at all**. Rotation was the
visible instance (27 slots at −6…+7°, one at 90°); the **expensive** one was crop — 101 of 115
slots carried a zoom and a crop position, and **88 had a frame aspect differing from their file's
aspect by more than 2%**, so typing the plan's W and H onto the raw files would have squashed 88
photographs. When a tool offers you four numbers, the question is not "how do I express my design
in four numbers" but **"what must I bake into the pixels first so that four numbers are enough"** —
and you find out by counting how many slots have an aspect their file does not.

**D11. Bake overlapping things together; do not rely on the vendor's alpha.** Transparent PNG was
rejected **on evidence**: all 27 rotated tiles had bounding boxes overlapping a neighbour's, so a
paper-coloured backing would have painted over parts of 27 neighbouring photographs (measured,
not assumed), and a transparent PNG would rest on an alpha behaviour untestable without leaving
an undeletable file in the account's library. Instead, 115 slots + 28 overlays collapsed to
**56 opaque axis-aligned group tiles + 24 full-sheet background objects**, the background placed
first so a group tile's paper meets identical paper and the seam is invisible by construction
rather than by hope. A spread already covered by its group gets **no** background — two objects in
one rectangle would make the geometry key ambiguous. Bake at ~3× the renderer's working canvas
(120 px/cm ≈ 305 dpi; a rotated tile's bbox is at most 12% larger, so ~268 dpi worst case), and
make the group padding exceed the drop shadow's reach (a shadow reaching 0.725 cm was cut at a
0.6 cm pad; the pad is 1.0 cm).

**D12. Key placed objects by GEOMETRY, because vendor ids are regenerated on save.** Neither the
DOM input index nor the canvas object UID survived save → reload. The durable key is the **canvas
index plus the object's geometry in cm rounded to 0.01** (`c06@29.46,0.67+28.33x27.87`), which the
loop proof reproduced through save → reload → reopen at **0.0 mm** error. It needs nothing
recorded, which is exactly what verification after a crash requires. Assert the key **and** a
payload property unique within each canvas so no two objects on one spread can be confused — the
image's natural pixel size where the object exposes it, its aspect ratio where it does not — and
capture the server-assigned filename at upload time (upload one file, diff the library, write the
name down) as the only cross-session link back to which of *your* files a placed object is.

**D13. The editor can wedge silently, and a read-only observation can still cost you the session.**
A full-screen loader overlay that never closed swallowed every click; reload was blocked by an
unsaved-changes dialog, and discarding the owner's unsaved state is his call, not the agent's.
Later, one click on the heaviest view froze the renderer past every screenshot timeout. Probe the
app's heaviest view **before** you have anything unsaved, check for the silent stall between
steps, and treat "the button froze it" as a finding rather than a failure.

## E. Working with the image model

**E1. Two-step generation: one job per turn.** Character sheet FIRST, then scenes from the
sheet; artwork FIRST (with deliberate empty space), then ask the finished image to add the
title. — The character-sheet method produced 5/5 sheets accepted on first generation with zero
retries and likeness holding across 25 badges; two-step titling produced correct RTL titles
letter-by-letter, which the orchestrator had planned to abandon as impossible. The user knew
the model's current behaviour better than the packet did — take hands-on user knowledge over
your prior.

**E2. Physical descriptions of people come from MULTIPLE originals and the user's own word —
and get fixed at the SOURCE file.** — One agent read a physical trait off a single AI-processed
cover image, the orchestrator promoted it to instruction, and the user had to correct a
statement about his own appearance. One wrong descriptive word then propagated agent-to-agent
through the run and caused three separate reruns, one of them ~518k tokens and 461 tool calls.
Correct the reference/character sheet itself, not each generation. Restate identity guardrails
in every generation packet (exact people, exact count, no morphing) and reject-and-retry
rather than shipping.

**E3. Draw a concrete object from the USER'S OWN PHOTO in the repo, not from the
orchestrator's prose.** — A brief described a large sculpture that did not exist: the records
showed a plush toy a child had won and carried. The same brief invented pedal boats on a lake
the family walked around, and omitted a highlight the user cared about. Two wrong descriptions
in one day. Upload the real photo as the drawing reference.

**E4. Segmentation, never generation, for cutouts.** `rembg` copies RGB verbatim and authors
only alpha, so faces cannot change; sending a rendered page to a generative model repaints the
people and caps output at 2048px. Generate only decorative elements on plain white, cut them
locally and deterministically, and composite at full resolution in your own renderer.

**E5. Crop a design by its OWN drawn shape; subject matting is for photographs.** —
Content-aware matting punched holes inside each badge (gaps between limbs, bites out of the
artwork). Recut with a shape fit: measure bbox, fit an ellipse (a circle is the equal-axes
case — one day's badges were genuine ellipses at ratios 1.078–1.323, the others measured
0.955–1.014), single feathered alpha, interior opaque by construction. Never encode a fix as
"the day-4 case" when it can be measured.

**E6. Downstream asset processing can undo the fix.** A picker thumbnail's palette QUANTIZER
thresholded partial alpha to fully transparent, reintroducing pinholes inside the fitted
ellipse even though the full-res PNGs were clean. Quantize RGB only; keep the resized 8-bit
alpha unthresholded; add a build gate that decodes every embedded thumbnail.

**E7. Gates learn cases; they are not waived by hand.** A sticker `--verify` reported 5 FAIL on
deliberately full-bleed cutouts ("border clear 42–56% vs a 60% gate") — the right response is
to teach the gate a full-bleed-subject case and log it, not to ignore it.

**E8. Don't trust generated manifests' ids.** Files named `connectors_route/vine/flourish` were
actually arrows and paper planes; a `*_basilica` file was a dragon and a `*_pretzel` file a
basilica; `*_vehicle` sticker files were whole rectangular photos while `*_riders` were the
real cutouts. Select assets BY EYE from contact sheets until a relabel pass has run. Likewise,
word-matching heuristics ("this asset has a sharper alternative") degrade as the library grows
and start producing confident nonsense — scope them by asset kind.

**E9. An absence in a deliberate composition is not a defect** — ask before "fixing" an
aesthetic choice. And a rejected asset may be wrong only at the SIZE it was tried: a piece
dismissed at full page was right as a 33–39% centrepiece. Record measured justifications in
code (a "source choice" table that raises unless every non-obvious pick is justified), so
trading real resolution for tone reads as a decision later, not a mistake.

**E10. A whole-frame AI edit destroys every face in the frame.** The model's edit path
**re-renders the entire picture** at ~1448 × 1086 whatever you asked it to change. At that size a
face is 40–60 px, so identity is re-invented — including faces nowhere near the requested edit.
Never let a whole-frame AI edit stand where faces matter: either composite the edit back onto the
original, or measure the face pixel size in the returned image and reject it.

**E11. The fix is not to regenerate — it is to composite the real photographic faces back.**
Regenerating reproduces identical damage (see E10) and costs identity drift on top. The recipe:
prove the geometric relationship between generated frame and real source, then paste the real
faces through feathered elliptical masks with per-channel exposure matching to the generated
lighting. **Alignment does not have to be identity; it has to be RECOVERABLE.** Where the model
merely re-rendered, a brute-force offset search proved pixel alignment at (0,0). Where it
**outpainted**, a pure scale+translate was recovered by **gradient correlation** (FFT coarse pass,
then refinement): `X = 1640 + 0.945x, Y = 112 + 0.945y`. Watch the mask edges — the first pass
leaked real-photo background rectangles onto adjacent generated content, fixed with tighter masks
and a smoothstep falloff that ramps the paste to zero before the foreign object. The side effect
is a **gain**: the repaired file was 4032 × 3024 against the AI file's 1448, i.e. real DPI
61 → 171, and in another case 75 → 300.

**E12. Scan the WHOLE frame — and every other asset produced by the same path.** The owner
reported one damaged face. Measurement found **three** in that same image — he had noticed only
the person he was looking at, and two other people in the same frame were damaged too. Two more
re-invented faces would have printed. When AI damage is found anywhere in a frame, audit every face in the frame, then audit
every asset that came through the same generation route.

**E13. Diagnose the layer before you rebuild it.** The first hypothesis blamed the local ×3
upscale; measurement showed the upscaler had faithfully enlarged faces that were **already
broken** in the model's own output. Rebuilding at the upscale layer would have solved nothing and
regenerating would have reproduced the damage.

**E14. A cluster representative is a thumbnail choice, not a provenance claim.** A "real photo"
attached to a generated image had been inherited from the *representative of its burst* — a
lookalike two seconds away — rather than from the provenance record. Gradient-correlation NCC
across scale 0.90–1.11 scored the three candidate frames 0.920 / 0.630 / 0.328 and the actual
upload 0.923, identifying the true source. Ask the provenance record, then **prove it with
pixels**: three frames of one burst are indistinguishable by eye.

## F. Provenance, semantics and linkage

**F1. Provenance over pixel similarity.** pHash-nearest anchoring paired a barcode photo with a
city fantasy; at Hamming 9–20 the nearest real image is essentially random. Anchors come from
the conversation's own edit chain ("Edit of NNN", else the nearest preceding real upload in
the conversation); pHash is a flagged fallback.

**F2. But provenance chains identify the CONVERSATION source, not necessarily the moment the
user means.** — For one slot the true source was a frame the user described in his own words,
while the pairing file pointed at a calm frame two seconds earlier. The user's description is
the tiebreaker.

**F3. Semantic kinds come from eyes, not hashes.** Sharpened ride photos were filed as fantasy
and a costumed fantasy as an enhancement — pHash conflates enhancement and fantasy in BOTH
directions. A vision pass over 45 generated images produced the authoritative split
(44 fantasy / 1 enhancement), and that file became the authority.

## G. Process, agents and the user

**G1. A mid-task message that expands scope looks exactly like an injection — dispatch new
features as NEW tasks with their own authorised scope.** — A worker bounded to "write ONLY
these two files" correctly REFUSED a copy/paste feature sent into its running task. That is
defensive behaviour, not failure; the feature was re-issued as a fresh dispatch.

**G2. Interactive HTML gate tools beat chat Q&A for any batch of visual decisions**, and the
orchestrator keeps images out of its own context — all eyeballing goes to vision subagents
with ≤15-line reports. — ORCH burned context rendering ~10 full-res images hunting anchors in
Phase 1; the rule was made binding for every later phase.

**G3. When a user points at a visual defect, get the precise crop and name the exact failing
property BEFORE dispatching a fix.** — Three consecutive misreads of one tile: "trim clipping"
(wrong), "white-on-white colour blindness" (disproved by experiment — paper is (247,244,238)
and a mat differs by 17/255), and only then the truth: the mat was being PAINTED OVER by the
picture. Two unnecessary code changes and one revert.

**G4. Root causes must be measured, not asserted — and a disproved root cause must be recorded
as disproved.** The worker who disproved the orchestrator's white-on-white theory by controlled
experiment was right; so was the one who proved a revert was unrelated by reproducing the
defect on the reverted tree.

**G5. Executors should stop-with-question on spec contradictions.** Every stop in the run was
correct and every one exposed a real spec gap (packet vs frozen validator; a 150-DPI gate that
would fail 27 approved slots; "adopt 4.4mm" and "nothing moves" being mutually exclusive;
forcing circles onto elliptical badges).

**G6. Guide bans are DEFAULTS; the user is the authority on their own album.** One fantasy
image was auto-omitted per the style guide and restored by the user ("it was a joke for me")
with a `user_override` note so no future review re-removes it. Treat user overrides as
authoritative — never bounce an export.

**G7. Every decision schema needs an exit.** The pairing schema had no exclusion state, so an
irrelevant reference photo had to be force-fitted; a `removed` state was added end-to-end.

**G8. Serial patching without reconciliation drifts.** By the time the user said "step in and
make order", chronology was broken, accepted enhanced versions weren't used in their own slots,
and approved regenerations were missing — because patches were never reconciled against the
accumulated decision list. Periodically re-derive the whole plan from the decisions.

**G9. Cross-link consequences on every decision card.** Users dropped real clusters without
seeing that those clusters anchored fantasy images living in a separate panel — 24 clusters
carried fantasy links and 15 of them were in DROP. Show dependents inline, plus a warning.

**G10. Track what the user has ACTUALLY reviewed.** When a user says "I'm only up to the first
20 images", every `approve` on a later spread is a default, not a ratification. Also separate a
version gap from a bug: a PDF rendered from a two-week-old export is not evidence about live
state.

**G11. When a worker reports a feature is "untestable on X", treat it as a signal the feature
may be ABSENT on X for the user**; demand a per-item survey as the deliverable. Here the survey
found 25 of 35 cards drew zero guide lines — for a completely different reason than the worker
had stated.

**G12. Old exclusion rulings must be enforced as hard blocks in later tooling**, not
remembered. And candidate-listing CLI modes (`--list-candidates`, declared tile lists
overridable by argument) let the user re-drive a composition without new code.

**G13. Stop agents that have finished.** A completed agent kept waking on stale poll timers and
burned 244k tokens.

## H. Downstream staleness — a derived artifact silently keeping an old source

This class bit **three times** in one run, in three unrelated subsystems, and each time every
gate was green. It is the most under-policed failure mode in a pipeline of derived files.

**H1. Ask what OPENS the file, not what DECLARES it.** Repointing the constant at the new back-cover
artwork changed nothing on paper: the frozen plan still named the old file, and every consumer
read a **frozen copy** of that value — plan → cover master (byte copy) → upload staging (byte
copy) → the page the PDF pastes — while a second branch fed the editor preview. Fix at the
mechanism, not the instance: **a frozen plan records the owner's VARIANT CHOICE, never which bytes
to print**; a supersession map plus one `resolve_asset()` function is the single place where a
plan's asset becomes a file to open, and every consumer calls it. Verified by pixels (mean |Δ|
0.000 against the intended file, ~62 against the old), and gated by a walk of
artwork → master → upload copy demanding byte identity at every link.

**H2. Two plans sharing one output filename is how a stale set hides.** The staged upload directory
and its map were keyed to an older plan and covered 80 of the current plan's 110 print files —
discovered only by **comparing upload timestamps against journal dates**. Give each plan chain its
own map file, stage everything through the *same* staging convention (never a parallel
mechanism), and make the newer map assert against its plan's **sha256**. The fatal gate checks
plan hash, slot set, resolved print file and placement against the *current* plan; every staged
file present, decodable, non-blank, non-zero with matching sha and dimensions; every source
unchanged since staging; and no orphans in either direction. Teeth proven on three injected
faults (a zero-byte file, an edited placement, a bogus orphan).

**H3. Two code paths that construct the same state are two places every migration must be applied
— and a comment asserting they converge is not evidence.** A face-repair substitution was applied
on the saved-session route and not on the JSON-import route, which built state in its own
function; importing the owner's own export put the **damaged originals straight back**. The
generator's own comment claimed both routes converged. Fix the migration at the top of *both*
constructors and add a `--verify` assertion that the rewrite exists on both.

**H4. Producing a repaired artifact is not the same as adopting it.** The delivery is the swap, not
the file. Adjacent instances of the same shape in this run: hi-res proof PDFs still rendered from
pre-fix geometry (their verifiers gated only page count and file size); a manifest still saying
`print_file: null` after the files existed; a tool built before a fix and sent to the owner
anyway. Assert derivation; never assume it.

**H5. Seeded state must declare where each value came from.** Importing the owner's export placed a
backdrop **1.29 cm (2.14% of a spread)** from where it printed, because the seed slot table came
from an older plan's **pre-clamp** geometry. Fixed by reading frozen geometry from the current
plan, matched by file first and then leftover-to-leftover in order, with **every slot logging its
source and every fallback printed, never silent**. Error after the fix: 0.11%.

**H6. Regenerating with default arguments re-inflates accepted deliverables.** Pin the arguments in
the command, not in your memory — a PDF regenerated without its explicit width and quality blew
back through the delivery size gate that had already accepted it.

## I. Human rules, turned into gates

The owner states rules in sentences. Written down as checks that run over the **rendered
artefact**, they find instances he never saw.

**I1. The fold must never fall on a face.** Implemented as a face detector run over the real drawn
spread of every spread carrying a full-spread image, flagging any face crossing the fold or
within 5 mm of it. It found **more than the owner did**, including the worst offender in the album
— the fold running between one person's eyes — which he had never mentioned.

**I2. Flag, don't fail, where the remedy costs something only the owner may spend.** The fold check
reports rather than blocks: detection is heuristic (it finds cartoon faces and 8-px crowd faces)
and clearing a seam costs resolution. A build nobody can run is worse than a build that says the
truth loudly. By contrast the **trim must never cut a person** rule was made FATAL, because it was
an explicit condition of the owner's approval and there is no resolution to buy back.

**I3. The arithmetic of clearing a seam.** A 4:3 picture covering a 2:1 spread at zoom 100 is
**height-limited: horizontal overscan is exactly zero**, so there is no pan headroom at all —
headroom has to be *bought* with zoom, priced in DPI. A seam at source fraction *sf* needs
`fw ≥ 0.5 / min(sf, 1−sf)` to keep both page edges covered, so the cheapest seam is always the one
nearest the source's centre and the two extreme pan positions are the only candidates worth
testing. One requested seam position was **geometrically impossible**. Analytic predictions were
~100 px out because detector boxes breathe with scale — measure on the real drawn spread at each
candidate.

**I4. The trim must never cut a person.** The outermost 5.0 mm of *vendor* space is 0.5051 cm of
*plan* space; both strips of every spread are cut out of the real drawn sheet and run through the
same detector. A face in a strip is fatal; skin-gamut share is *reported* alongside, because no
person detector is vendored and skin is the only honest body signal — with the album's own cream
paper excluded by colour, or every margin reads 100% skin. The two constants the law measures
with are asserted against the vendor mapping's own numbers, so the law can never end up policing
a strip the mapping no longer cuts. Two offenders, two modes: a bleed whose edge content crossed
a person, fixed by **pan, not zoom** (zoom pushes edge content further off *and* costs DPI on a
picture already near its floor); and a non-bleed tile parked 0.30 cm from the sheet edge, i.e.
*inside* the trimmed strip, fixed by a uniform 2% inset that keeps it square, centred and
un-recropped.

**I5. A frame that exists but cannot be seen is a defect.** Fatal on the **ring** (frame plus its
outset) with 0.30 mm of required clearance inside both the plan edge and the vendor trim; the
drop-shadow tail is **reported, not gated**, because nudging half the bordered tiles of an
approved album to save a fraction of a millimetre of a blur buys nothing — printing the number
does. State the price of every fix you do apply: the one translation applied here (3.36 mm, x
only, no re-crop) pushed a drop shadow 2.85 mm past the fold onto bare paper, and that was said
out loud rather than discovered later.

**I6. Report what you will not fix, with the reason.** Four remaining trim offenders were left
alone and written down: two whose pan was already pinned by an earlier fold-on-a-face override
that panning back would reopen, and two bleeds at zoom 100 with zero headroom where moving them
would open the white gaps the owner had forbidden. In all four the figure already ran off the
plan's own edge, so the vendor takes 5 mm more of an edge that was always going to be cut — it
newly amputates nobody. **Correcting something that costs more than it buys is not diligence.**

**I7. Never hand-edit the generated plan.** Corrections live as **declared override tables** keyed
by (spread, page, slot) and applied to the export entry inside the build. Every entry states the
export values it `expect`s and the build **stops** if they moved, so an override can never
silently re-frame something the owner has since recomposed. Prove each change with a whole-plan
diff that names exactly N changed fields, and with per-spread render hashes. The plan stays
regenerable from the owner's untouched export plus guarded patches.

## J. Test-harness traps

1. **An assertion using a proxy breaks the moment the real path is short.** String length as a
   stand-in for "embedded data present" is not the assertion you want — assert identity.
2. **A browser `evaluate` call binding only one argument silently passes `undefined`** and
   produces a FALSE FAIL. Check the binding before chasing the "bug".
3. **A build-time asset whitelist means new data keys silently never ship.**
4. **Adapt measurement to display scale** when the UI rescales the canvas; never weaken the
   tolerance to accommodate a UI change.

## K. Environment and tooling gotchas

1. Export ZIPs contain junk temp files — filter by an allowlist of suffixes, never glob `*`
   into a validation set.
2. Image pipelines emit blank files despite a "success" proof — reopen, decode, check
   dimensions and non-blankness before a file enters a final directory.
3. A "valid" archive can be a partial copy — CRC-test the exact final copied file.
4. Chrome completes a download but leaves it as `<uuid>.tmp` when the triggering page context
   is gone — match Downloads by byte-size and magic bytes, never by expected filename. And
   check where Chrome's download directory actually points.
5. Download loops must treat a verified on-disk file as terminal success and STOP polling; cap
   attempts at 2 per image. (A loop re-saved one completed image until it was killed.)
6. Photo-host APIs rot (the Google Photos read API died in 2025) and Takeout misses albums
   shared WITH you — the share-link "Download all" in a real browser is the reliable path.
   Count items via a full-scroll DOM harvest of the share grid (325 anchors), and split image
   vs video counts before validating a file walk (292 images + 33 mp4 = 325).
7. AI-chat lightbox download buttons are unreliable under automation; `fetch` + blob +
   `a[download]` in page JS worked 72/72.
8. Chat UIs swallow submissions and hang — reopen the same conversation URL in a fresh tab
   rather than resubmitting.
9. A bare `python` on Windows may be a broken WindowsApps stub — resolve and pin the real
   interpreter path once at setup.
10. An apostrophe inside a non-Latin string literal can break JS — use the language's own
    punctuation character.
11. Self-contained HTML has a hard size budget (16MB, raised to 22MB here; chat delivery caps
    at 30MB). Find the real driver before optimising: overlay thumbnails cost ~1.7MB even after
    being RAISED to 180/220px — the overflow was simply 110 new decoration assets.
12. Chat-attached images cannot be written to disk by the agent — the user must drop files into
    the ingest folder, or the agent must re-source them (and say so).
13. Segmentation models are 40–170MB and cannot live inside a self-contained offline HTML tool;
    run them locally and embed only the results.
