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

## H. Test-harness traps

1. **An assertion using a proxy breaks the moment the real path is short.** String length as a
   stand-in for "embedded data present" is not the assertion you want — assert identity.
2. **A browser `evaluate` call binding only one argument silently passes `undefined`** and
   produces a FALSE FAIL. Check the binding before chasing the "bug".
3. **A build-time asset whitelist means new data keys silently never ship.**
4. **Adapt measurement to display scale** when the UI rescales the canvas; never weaken the
   tolerance to accommodate a UI change.

## I. Environment and tooling gotchas

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
