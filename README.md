# Handoff: Frontline Rx Intelligence — Carbon redesign (v3, final)

## Overview

The Frontline BI report (`frontline-report.onrender.com`) rebuilt on IBM Carbon v11, with a new information architecture, a promoted reporting-period component, a heavier side navigation, and Hive Frontline / British Biologicals branding.

**Build from `Frontline Rx Intelligence v3.dc.html`.** It is the current and final design reference. `v2` and the original are in the folder for history only — where they differ from v3, v3 wins.

## About the design files

The `.dc.html` files are **design references created in HTML** — prototypes showing intended look, structure and behaviour. They are not production code to copy. Recreate them inside the Frontline codebase (Flask + Jinja) using that codebase's own patterns, following `CARBON_RULES.md`.

## Fidelity

**High fidelity.** Colour, type, spacing, control heights, grid columns, loading behaviour, copy and interaction states are final and all colour/type/spacing values are Carbon tokens. Match them exactly. Figures are illustrative — wire the real query results.

## Files in this bundle

| File | What it is |
| --- | --- |
| `Frontline Rx Intelligence v3.dc.html` | **The design reference.** Five built screens, side nav, reporting-period band, filter strip, drill panel, loading states, branding. |
| `CARBON_RULES.md` | The binding spec: tokens, grid, geometry, loading contract, icon table, copy patterns, known pitfalls, per-screen checklist. Install as `CLAUDE.md`. |
| `UNDESIGNED_SECTIONS.md` | Specs for the five sections that were **not** designed, with enough direction to design and build them without coming back to us. |
| `NAV_SPEC.md` | **Nav-only contract**: the eight deviations seen in the first build, required DOM, required CSS, the 10 items with their metrics, and 10 console acceptance checks. Supersedes nav prose elsewhere. |
| `CONFORMANCE.md` | **Definition of done for each of the 19 checklist items** — what must literally be present in the built template. Read before starting a screen and before calling one done. |
| `CLAUDE_CODE_PROMPT.md` | Paste-ready prompts, one per pass. |
| `audit/_audit.py` | The scored gate. `python3 audit/_audit.py <built template>`; exit 1 on any FAIL. Wire into CI in pass 1. |
| `carbon-tokens.css` | The token file to drop into the app. |
| `brand/` | `hive-frontline.svg` (nav lockup), `hive-mark.png` (collapsed rail mark), `british-biologicals.svg` (source lockup — see Branding). |
| `Frontline Rx Intelligence v2.dc.html`, `Frontline Rx Intelligence.dc.html` | Earlier explorations. Reference only. |

---

## Deploy in this order

Each pass ends in a reviewable diff. `CLAUDE_CODE_PROMPT.md` has the prompt for each.

0. **Install the rules** — `CARBON_RULES.md` → `CLAUDE.md`; `carbon-tokens.css` → static CSS, loaded first; `brand/` → static assets.
1. **Foundation** — tokens replace the existing custom properties; both themes; the 13 Jinja macros.
2. **Chrome and IA** — remove the top header bar, build the side nav, collapse 13 nav items into 10 in five sections.
3. **Reporting period** — the promoted period component; move region/days/search into the slim strip.
4. **Loading system** — one helper, four treatments, then audit for silent work.
5. **Screens, one at a time** — Pulse → Rx engine → Doctors → Field activity → Trends.
6. **Undesigned sections** — Needs action → Managers → Org tree → Guide → Notes, per `UNDESIGNED_SECTIONS.md`.
7. **Copy and icon audit.**
8. **CI gates** — no colour literals; no undefined tokens.

Do not restyle screens before pass 2. The IA change moves content between screens, and styling it twice is the most common way this kind of migration wastes a week.

---

## Chrome and layout

**There is no top header bar.** It was removed in v3: it held only a duplicate product name and three placeholder icons. The side nav carries identity; the reporting-period band and filter strip carry controls. This reclaims 48px on every screen.

```
┌──────────────┬─────────────────────────────────────────────┐
│ nav          │ reporting period band   (static, edge-to-edge)│
│ 320px        ├─────────────────────────────────────────────┤
│ sticky       │ filter strip            (sticky, top: 0)     │
│ top: 0       ├─────────────────────────────────────────────┤
│ height:100vh │ page header + screen content                 │
│              │ report footer with BB lockup                 │
└──────────────┴─────────────────────────────────────────────┘
```

- Nav: `position: sticky; top: 0; height: 100vh`, 320px expanded / 72px rail, own scroller, `box-sizing: border-box; min-width: 0; overflow: hidden` (without all three the rail cannot collapse).
- Filter strip: `position: sticky; top: 0; z-index: 30`, `0 2px 6px var(--cds-shadow)`.
- Content: `max-width: 1584px; margin: 0 auto; padding: 0 16px 96px`.
- Drill panel: fixed right, `min(520px, 100vw)`, `z-index: 51` over a `--cds-overlay` scrim at 50.

## Information architecture

13 sidebar items → 10, in five task-named sections. Numbered group labels ("01 CORE") are gone — they carried no meaning. Call detail and Doctors × Rep are in-screen table variants, not destinations. The sidebar navigates and does nothing else.

| Section | Items | Absorbs |
| --- | --- | --- |
| Performance | Pulse, Rx engine, Trends | Overview, Rx Engine, Trends |
| Field | Field activity, Doctors | Daily Calls, Call Detail, Doctors, Doctors × Rep |
| Action | Needs action (badge 50) | Exceptions |
| Team | Managers, Org tree | Managers, Org tree |
| Reference | Guide, Notes | Guide, Notes |

Every nav item carries a **live metric and a one-line description** — that is part of the design, not decoration; the nav doubles as a status board. Wire each from the same query that feeds its screen so the numbers cannot disagree.

| Item | Metric | Description |
| --- | --- | --- |
| Pulse | conversion % (error tint) | Conversion, volume, exceptions |
| Rx engine | total Rx | Prescriptions and rates |
| Trends | period delta | Week-by-week movement |
| Field activity | calls/rep/day + "Below 10" tag | Calls, day plans, visit records |
| Doctors | doctors met | Coverage and conversion by rep |
| Needs action | open count (error tint) + red badge | Grouped by what to do |
| Managers | manager count | 43 managers, 9 regions |
| Org tree | rep count | Reporting lines and territories |
| Guide | — | How each figure is calculated |
| Notes | new count | Data caveats and cut-offs |

## Screens designed in v3

**Pulse** — headline Rx conversion with an answer line and a CTA into the 20 zero-Rx reps; conversion-vs-target chart with a filled area; four-tile volume row; "Needs a decision this week" band grouping all 50 exceptions by implied action, ranked by what is at stake.

**Rx engine** — headline 9,608 Rx; a 15/85 split bar (hatched on the no-Rx side) replacing the original donut, with a legend block per segment; four-tile volume row; a quieter four-tile "Rates" row; horizontal bars of Rx by specialization with a conversion column.

**Field activity** — headline 7.6 calls/rep/day against a standard of 10; day-of-week columns with sub-threshold days in warning yellow; call-detail table with outcome tags, sorted-column marker and a paging footer.

**Doctors** — a chart card framing the question, then the rep table sorted worst-conversion-first, each row with initials plate and an inline 96px conversion bar coloured by threshold (0% red, <10% yellow, else blue).

**Trends** — two-series line chart (calls vs Rx) on a shared zero-anchored scale with the calls area filled; four delta tiles whose tags carry direction icons.

## Reporting period — the centrepiece component

Promoted out of the filter row into its own full-width band directly under the nav, on white, **edge to edge with no inset padding or grey plate**. Three cells separated by 1px hairlines (`display: flex; flex-wrap: wrap; gap: 1px` over `--cds-border-subtle-01`, each cell `--cds-layer-02` with 20px padding).

| Cell | Basis | Contents |
| --- | --- | --- |
| Reporting period | `flex: 1 1 300px` | `calendar--heat-map` + label; the range at `clamp(1.25rem, 2.4vw, 1.75rem)` weight 300; day and working-week count; two tags (active preset, comparison); two date fields when Custom is selected |
| Quick range | `flex: 1 1 340px` | `time` + label; six preset tiles (`flex: 1 1 124px`, 64px tall, label + its dates, 2px top border blue when selected); the window bar — a 24px ruled track with a blue fill showing where the range sits in captured history, with the % and both end dates |
| Compare against | `flex: 1 1 280px` | `compare` + label; three stacked options (label above sub-label, 3px blue left border when selected); one helper line, "Applies to every figure and drill-down below" |

Presets: Last 30 days · Last 90 days · Quarter to date · Year to date · All time · Custom. Comparisons: Previous period · Same period last year · No comparison. Changing either goes through the loading helper and updates the range, the tags, the window bar, the delta tags on Trends and the tag in the drill panel header.

**Flex-wrap, not `auto-fit` grid** — for both the band and the preset tiles. Six tiles in an `auto-fit` grid resolve to 4 tracks at some widths, leaving empty tracks that paint as grey slabs through the gap-background. Flex-wrap makes the last line grow to fill. Apply the same reasoning to any wrapping row whose item count doesn't divide the track count.

Region, days of week and rep/doctor search live in the slim sticky strip below, with a filter-state sentence, a Clear filters action (disabled when nothing is applied) and Refresh.

## Side navigation anatomy

- **Masthead** 96px, `--cds-layer-02`, `border-bottom: 1px solid var(--cds-border-subtle-01)`. `brand/hive-frontline.svg` at `width: 80%`, left aligned; the collapsed rail shows `brand/hive-mark.png` at 40px instead. No text under the logo.
- **Scroller** — five sections, each `padding-top: 24px`. Section label: 12px/600 uppercase `--cds-text-secondary` with a 16px icon, 20px side padding, no band and no rule.
- **Items** 60px, `padding: 8px 20px 8px 16px`, `border-left: 4px solid transparent`, **no separators between items**. A 36px icon chip (`--cds-layer-02`, 1px `--cds-border-subtle-01`) holds a 20px icon. Then name (14px, 600 when active) with an optional tag, and below it the metric (12px/600) plus description (12px `--cds-text-helper`, ellipsised).
- **Active item** — `background: var(--cds-layer-02)` (the content colour, so it lifts out of the grey nav plate), `border-left-color: var(--cds-border-interactive)`, icon chip `--cds-interactive` with an on-color icon, name 600.
- **Hover** `--cds-layer-hover-01`, **pressed** `--cds-layer-active-01`, 110ms.
- **Footer** on `--cds-layer-accent-01` with `border-top: 1px solid var(--cds-border-subtle-01)`: a 56px user row (32px initials plate on `--cds-background-inverse`, name, "HQ · Admin · All regions"), then one row holding the BB mark and name on the left and two **icon-only 32px buttons** on the right — theme and collapse. No written labels; `title` + `aria-label` only.
- **Rail (72px)** — labels hidden, icon chips and active borders visible, badge counts become a 6px red dot pinned top-right (absolutely positioned so flex can't crush it), tooltips carry name and description, footer icons centre.

Total nav hairlines: three. Earlier versions had one under every item and two per section band; that reads as noise at this density.

## Naming

The report is **Hive Frontline intelligence**, abbreviated **HFI**. Hive Frontline is the mobile app; this is its reporting surface, not a second brand.

- **Full name once, initialism after.** The name appears in the nav masthead — the word "intelligence" set at 12px directly under the Frontline logo, so the lockup and the type together read "Hive Frontline intelligence" without repeating words the logo already says — and in the report footer's ownership line: "Hive Frontline intelligence · Prepared by Field Effectiveness, HQ".
- **HFI only in tight spots**: the browser tab title, the drill-panel eyebrow ("HFI · Behind the number"), export filenames (`HFI_<screen>_<ISO date>.xlsx`, e.g. `HFI_Rx-engine_2026-09-01.xlsx`), and the print header.
- **Never as a logo.** No lockup, no wordmark, no coloured HFI badge, no second mark anywhere. The report's identity comes from type and masthead position.
- **Page eyebrows stay sectional.** Do not repeat the product name above every screen title; it is already in the masthead.

## Branding

**Hive Frontline** — `brand/hive-frontline.svg` in the nav masthead at 80% width. `brand/hive-mark.png` (chevron only) in the collapsed rail. Ask the brand owner for an SVG of the mark alone to replace the PNG.

**British Biologicals** — the uploaded `british-biologicals.svg` is a full lockup (mark + wordmark + tagline) in a 364×181 viewBox, and its `<defs>` is empty, so every path falls back to black. Two consequences: it must never be scaled down to badge size (the wordmark drops below 2px), and it cannot be used on a dark surface as authored.

The design therefore uses the **mark only**, inlined as SVG so it recolours with the theme, with the name set in Plex:

- **Nav footer** — 24px mark + "British Biologicals" at 12px, in the same row as the theme and collapse icons.
- **Report footer** — 44px mark + name at 16px/600 + "Nutrition science since 1988", beside "Prepared by Field Effectiveness, HQ", separated by a 48px vertical rule, under a hairline above the confidentiality line.

Extract the mark with `viewBox="143.94 0 76.18 74.45"` and the four quadrant paths; set `fill: var(--cds-text-primary)` and `opacity: 0.55` on the two diagonal quadrants to preserve the two-tone reading. **If the brand team supplies the coloured SVG or the two brand hex values, use those instead and stop overriding the fill** — the opacity trick is a stand-in, not the brand.

Do not place either logo on a photo, a gradient, or the gray-100 surface.

## What is not built

`UNDESIGNED_SECTIONS.md` specifies Needs action, Managers, Org tree, Guide and Notes. In v3 they render a shared empty state (`idea` icon on a 64px plate, sentence-case title, one line, one tertiary button back to Pulse). Ship that empty state on day one, then build the sections in the order given — Needs action first; it is the one users will look for.
