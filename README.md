# photo-album — a Claude Code skill for building a real printed photo book

Turn a large, messy pool of photos, videos and AI-edited images into a **print-ready vendor
photo book** — with an auditable selection trail, a live album builder the user drives
themselves, and gates that check the *printed pixels*, not just the plan.

Built with and for [Claude Code](https://claude.com/claude-code). The agent orchestrates; the
deterministic steps are plain-Python scripts bundled here.

This skill is distilled from one complete run: a 30×30cm layflat book, 76 pages, ~480 pool
images, 33 videos, two AI-chat conversations of edited images, 267 commits, 40 scripts and
seven plan revisions. Every number quoted in the lessons is a measured number from that run —
not a default to trust.

## What it produces

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
| The book, in the vendor's editor | Assembled and reviewed — **the user orders and pays** |

## Quick start

```
/photo-album      (or just: "build me a photo book from this album link")
```

Then, in order:

1. **Phase 0** — the agent establishes frozen contracts: title, product (trim size, page
   raster, page-count rule), reading direction, identity rules, file layout, ledger schema.
2. **Phase 1–2** — it downloads and inventories the pool, then re-culls it with vision-judge
   fleets and pairwise duels. You approve via a generated HTML tool.
3. **Phase 3** — a page plan you ratify, after the agent has *measured* the vendor's real safe
   margin from the editor's own guide.
4. **Phase 4–5** — print assets, then the album builder lands in your browser and you build the
   book page by page.
5. **Phase 6** — the agent assembles it in the vendor's editor. You place the order.

Install: copy this repo into your skills directory (e.g. `~/.claude/skills/photo-album/`), or
point Claude Code at it as a plugin skill. Then `pip install -r scripts/requirements.txt`.

## Repo layout

```
SKILL.md                     the skill: run architecture, contracts, the seven phases
references/lessons.md        the hard rules, each with the number that bought it
references/protocols.md      vision-fleet templates, executor packets, the print gates
references/scripts.md        the bundled scripts, and specs for the parts not shipped
scripts/                     14 generic, verifiable Python scripts
```

## The three ideas worth stealing

**1. More than three visual decisions ⇒ generate a tool, never ask in chat.**
Every gate is an offline single-file HTML tool: thumbnails with a full-res lightbox, every
click persisted to localStorage as an overlay over an immutable draft, a JSON export with a
`<textarea>` fallback, and live invariant guards ported from the validator. *User export =
approval.* The user works at their own pace, sees consequences cross-linked inline, and cannot
lose work to a tool bug.

**2. The builder UI and the print engine are two implementations of one geometry — so diff
them automatically.**
They *will* drift, and the drift is invisible until it is printed. A 28.8cm framed photo
printed as full bleed; every rotation silently dropped; 12 of 14 tiles outside the safe box,
the worst by 1.1cm. The fix is a browser-driven fidelity harness that compares centre, size,
rotation, border box, layer rank and containment within 1.5% of spread width — plus an
*absolute* assertion on both sides, because "the two implementations agree" is not "the result
is correct".

**3. Assert clearance on the printed pixels, not absence in the data.**
A trim check that diffs colours reported "0.000cm of ink in the trim band" for a print that was
visibly cut, because the clamp parks tiles with 0.25mm of slack and the guillotine ate it.
Replace it with a per-tile sentinel-mask gate on the real print canvas — and give every new
gate a **negative proof**: turn the fix off and watch the gate fail exactly the items it used to
pass.

## What this cost, honestly

The reference run took weeks of wall-clock time and a great deal of agent time: 267 commits,
40 scripts, ~2300 lines of run journal, and a builder tool that went through twenty versions.
Phase 5 — the builder — consumed more effort than every other phase combined. If you want a
photo book by Friday, use the vendor's own editor.

**What it is good at**

- Re-culling a pool too large to hold in your head, with a written reason behind every keep and
  every drop.
- Catching print defects *before* the print run: real-pixel DPI, trim clearance, mat integrity,
  rotation and layout fidelity between what you saw and what prints.
- Making the user the decider on taste while the agent handles everything mechanical.
- Surviving handoffs. State lives in files (`plan.md`, `journal.md`, `records/*.json`), so a
  fresh agent with no conversation history can pick the run up.
- Working honestly with AI-generated imagery: identity preserved, provenance tracked,
  upscaling described as what it is (no detail is created).

**What it is not**

- Not fast, and not cheap in tokens.
- Not vendor-agnostic out of the box. Trim size, safe margin, accepted formats, page-count rules
  and RTL/LTR behaviour must be *measured* from your vendor's own editor before layout begins.
- Not a design tool. It gives you a competent, honest layout with guardrails — a designer will
  do better-looking work faster.
- Not autonomous. It is built around user gates, and it will stop and ask.
- It never orders and never pays. That is always the user's click.

## Privacy

This repo publishes the **method** only. No photographs, no generated imagery, no thumbnails,
no page plans, no manifests, and no personal details from the original run are included. The
worked example is anonymised throughout: it is "a five-day family trip", and the numbers are
measurements, not content. Where a bundled script embedded run-specific text, it has been
replaced with a placeholder marked in `references/scripts.md`.

## License

MIT — see [LICENSE](LICENSE).
