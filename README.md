# photo-album — a Claude Code skill for culling a thousand photos and printing the survivors

You came back from a trip with a thousand photos. Eleven near-identical frames of the same
statue, four of them sharp; a dozen you already know you love; and several hundred you will
never open again. Nobody sits through that folder twice, so the album never gets made.

**This skill does the pass you never do — and shows its work.**

It clusters the pool first, so eleven frames of the same statue are one decision, not eleven:
near-duplicates grouped by capture time and visual similarity, with a hard split at a long time
gap. Then a fleet of **blind vision judges** scores each cluster on four 1–5 axes and names the
best member of the burst. Absolute scores are reliable at the extremes and useless between close
rivals, so the contested middle goes to **pairwise duels** — Swiss rounds, shuffled A/B order,
and a mandatory reversed re-run whenever the margin is slim. Every verdict is written to a file,
so any pick can be traced back to the judge that made it.

Already have an old version of the album? It gets **re-culled with everything else.** Previous
picks carry a small incumbent bonus and never a veto — "on some of them we were wrong" is a
thing the reference run's owner said out loud, and the pipeline is built to let him be right.

Then the shortlist lands in an **offline HTML tool** in your browser: thumbnails, a full-res
lightbox, and three buttons per cluster — keep, keep + enhance, drop. Your export is the
approval, and your overrides are never argued with. In the reference run that was **30 triage
judges over 237 clusters and 34 duel groups over 139 duels, on a pool of 479 images**, before a
human looked at anything.

**What it explicitly cannot do:** it does not know what matters to you. It cannot tell your
oldest friend from a stranger in the background, or the ordinary-looking frame that happens to
be the last picture of someone. It ranks **sharpness, composition, technical quality and the
strength of the moment** — nothing else — and every final keep, drop and page is yours. The
machine's job is to make the pile small enough that your judgement is affordable.

And then it keeps going: page plan, print assets at honest real-pixel DPI, a **live album
builder** you compose the book in yourself, gates that check the *printed pixels* rather than
the plan that produced them, and assembly in the print vendor's own web editor. **You press
order. Never the agent.**

Built with and for [Claude Code](https://claude.com/claude-code). The agent orchestrates; the
deterministic steps are plain-Python scripts bundled here.

Distilled from one complete run, carried all the way to a book assembled in a print vendor's
own editor: a 30×30cm layflat book, 76 pages, ~480 pool images, 33 videos, two AI-chat
conversations of edited images, 270+ commits, 40 scripts, eight plan revisions, and a hundred
numbered decisions. **Every number quoted in the lessons is a measured number from that run —
none of them is a default to trust.**

## Who this is for

Someone who wants a specific book made properly, is willing to spend real time on it, and cares
that the faces in it are the actual faces of the actual people. If you want a photo book by
Friday, use your vendor's own editor — it is a good tool and this is not a race.

## What it does

| Artifact | Description |
|---|---|
| `ledger.json` / `.csv` | One row per source image: id, source, dimensions, EXIF time, pHash, bytes, sha256 |
| Inventory contact sheet | Offline HTML, browsable by source and by hour |
| `selection.json` | The re-culled pool: keep / keep+enhance / drop, with the judge verdicts behind each |
| Triage + duel records | Every vision judge's verdict file — the selection is fully auditable |
| `pageplan.json` | The user-ratified, spread-by-spread plan |
| **The album builder** | A single offline HTML file: live composer, the full pool, per-tile controls, presets, auto-fill, guides, overlays, page map, undo, JSON import/export |
| Print assets | Every planned image at print resolution, in the vendor's accepted format, with honest real-pixel DPI |
| Print-fidelity PDF | A proof rendered by the same engine that computes the final geometry |
| Gate reports | Fidelity, trim clearance, mat integrity, visibility, fold-on-a-face, trim-cuts-a-person, derivation |
| The book, in the vendor's editor | Assembled, verified object by object at 0.0mm — **and the user orders and pays** |

## What it does not do

- It is **not fast** and not cheap in tokens.
- It is **not vendor-agnostic** out of the box. Trim size, safe margin, accepted formats,
  page-count rules, cover scale and reading direction must be *measured* from your vendor's own
  editor before layout begins. The skill teaches the measuring; it cannot ship your numbers.
- It is **not tied to one image generator**, but it does not ship credentials for any. The
  "fantasy" images need an image-to-image editor that keeps the source composition, accepts a
  reference sheet and returns a full-resolution file — an API, another web UI, or a local model.
  `references/protocols.md` Part 7 defines the one function to reimplement and compares the
  three levels honestly.
- It is **not a design tool**. It gives you a competent, honest layout with guardrails. A
  designer will do better-looking work faster.
- It is **not autonomous**. It is built around user gates and it will stop and ask.
- It **never orders and never pays**, never deletes anything from your vendor account, and never
  reloads over your unsaved work. Those are your clicks.

## Quick start

```
/photo-album      (or just: "build me a photo book from this album link")
```

Install: copy this repo into your skills directory (e.g. `~/.claude/skills/photo-album/`), or
point Claude Code at it as a plugin skill. Then `pip install -r scripts/requirements.txt`.

Then, in order — the full route is at the top of `SKILL.md`:

1. **Contracts** — title, product (trim size, page raster, page-count rule), reading direction,
   identity rules, file layout, ledger schema, and content-tiered DPI floors.
2. **Acquire and select** — the pool is downloaded, inventoried and re-culled by vision-judge
   fleets and pairwise duels. You approve in a generated HTML tool.
3. **Plan** — a page plan you ratify, *after* the agent has measured the vendor's real sheet.
4. **Assets, then build** — print assets (with faces protected), then the album builder lands in
   your browser and you compose the book page by page.
5. **Gate the printed pixels** — fidelity, trim, visibility, the fold, the derivation chain.
6. **Vendor build, then the cover** — assembled in a duplicated project, verified object by
   object; then the wrap, the spine and the vendor's barcode.
7. **You place the order.**

## Repo layout

```
SKILL.md                     the route, the run architecture, the contracts, the ten phases
references/lessons.md        the hard rules (A–K), each with the number that bought it
references/protocols.md      vision-fleet templates, executor packets, gates G1–G14,
                             the vendor-editor build method, the cover/spine/wrap checklist,
                             and Part 7: swapping the image-generation service
references/scripts.md        the bundled scripts, and specs for the parts not shipped
scripts/                     14 generic, verifiable Python scripts
```

## The ideas worth stealing even if you never build a book

**1. More than three visual decisions ⇒ generate a tool, never ask in chat.**
Every gate is an offline single-file HTML tool: thumbnails with a full-res lightbox, every click
persisted to localStorage as an overlay over an immutable draft, a JSON export with a
`<textarea>` fallback, and live invariant guards ported from the validator. *User export =
approval.* The orchestrator, meanwhile, never renders an image into its own context — all
eyeballing goes to subagents that return capped reports.

**2. Two implementations of one geometry must be diffed — and each asserted absolutely.**
A builder UI and a print engine *will* drift, and the drift is invisible until it is printed.
"Both engines agree" is not "the result is correct".

**3. Assert clearance on the printed pixels, not absence in the data.**
And give every new gate a **negative proof**: turn the fix off and watch the gate fail exactly
the items it used to pass.

**4. The owner's sentences are gates.** "The fold must never fall on a face" and "the trim must
never cut a person" became face detectors run over the real drawn spread. They found offenders
he had never noticed — including a fold running between someone's eyes.

## What will bite you

An honest list of the defects that reached, or nearly reached, paper in the reference run. Every
one had green gates at the time.

- **Your fidelity harness will be green while the print is wrong.** It compares rects, padding, z
  and angle — all of which describe *where the picture is*. It says nothing about what a tile
  paints where the picture is **not**. A tile transparent in the composer printed an opaque
  17.04mm white mat (0.50mm on screen), and a legacy `rotate_deg` field the renderer honoured and
  the composer ignored silently turned a picture through 180°. Assert ground, mat, drawn frame
  width in mm of paper, and **which source file each engine opened**.
- **Whole-frame AI edits destroy every face in the frame.** The model re-renders the whole picture
  at ~1450px, so faces come back re-invented — including faces nowhere near the edit you asked
  for. The fix is not to regenerate; it is to composite the real photographic faces back, with the
  transform recovered by gradient correlation where the frame was outpainted. And scan the whole
  frame: the report said one damaged face, the measurement found three.
- **Vendor space is not plan space.** The editor's real sheet was 58.40 × 29.70cm, not the
  "30 × 30" on the tin. The mapping onto it cut 5.0mm off each outer edge, so a tile parked flush
  on our own safe line ended up **outside the vendor's sheet**.
- **The cover does not share the interior's scale.** Measured on its own canvas, the cover sheet
  was 1.077× the spec figure — so the first wrap was rendered at **283 dpi instead of 306, 7.7%
  short**. Caught one step before printing.
- **The vendor prints its own barcode over your artwork.** White-backed, on top. On the back-cover
  collage it landed on four faces. Measure it and reserve it as a dead zone before composing.
- **The spine is real and no page-level gate mentions it.** A grep for "spine" across the codebase
  returned zero hits while two cover masters already existed.
- **A frame that exists but cannot be seen is a defect**, and an edge gate answers "is it inside
  the paper", never "can it be seen". Occlusion and the fold need their own checks.
- **A fix that trades one edge for the opposite edge is not a fix.** A 3.36mm nudge that rescued a
  clipped left ring pushed the right ring into the binding band. Only a four-sided check saw it.
- **A derived artifact silently keeping an old source bit three separate subsystems** — a back-cover
  master, an upload library, and two code paths that constructed the same state. Ask what *opens*
  the file, not what declares it.
- **The canvas DOM order was reversed**, and placing in DOM order would have printed the album back
  to front. Verify order against labels, and prove one unit through place → save → reload → read
  back before committing all of them.
- **The vendor editor can wedge silently.** One click on its heaviest view froze it past every
  timeout. Probe that view before you have anything unsaved.

## What it cost, honestly

Weeks of wall-clock time and a great deal of agent time: 270+ commits, 40 scripts, ~3,100 lines
of run journal, a builder tool that went through twenty versions, and a vendor build that placed
81 objects across 39 canvases by hand-typed centimetres. Phase 5 — the builder — consumed more
effort than every other phase combined, and Phases 6–8 are where a project that *looks* finished
turns out not to be.

## Privacy

This repo publishes the **method** only. No photographs, no generated imagery, no thumbnails, no
page plans, no manifests, no captions and no personal details from the original run are included,
and the vendor is generalised. The worked example is anonymised throughout: it is "a five-day
family trip", and the numbers are measurements, not content. Where a bundled script embedded
run-specific text it has been replaced with a placeholder marked in `references/scripts.md`. The
album project itself is a local repository with no remote, and it will stay that way.

## License

MIT — see [LICENSE](LICENSE).
