# Modules — exact specs and fixes

Three things that arrived after the first build and that prose alone will not land: the **collapsed scope bar**, the **Incentive eligibility** module, and the **rep profile modal**. This file is their contract, in the same form as `NAV_SPEC.md`: what is wrong now, required structure, required behaviour, and console acceptance checks.

Read the `## Required` sections as normative. If your implementation differs in structure, change the implementation.

---

# 1. Scope bar — the vertical-space fix

## What is wrong now

On the deployed build, a user who enters a module from the side nav sees ~490px of chrome before any data: a filter panel, a "no filters applied" line, a "More filters (11)" row, then a three-cell reporting-period band 380px tall. On a 900px laptop viewport that is more than half the screen, and every module costs a long scroll to reach its first figure.

The reporting period is set **once per session and rarely changed**. Chrome that is used once should not occupy space permanently.

## Required

**The period band is collapsed by default.** In its place, the sticky filter bar carries one 56px control:

```html
<button class="scope-toggle" aria-expanded="false">
  <svg class="icon-20"><!-- calendar--heat-map --></svg>
  <span class="scope-text">
    <span class="scope-label">Period · vs previous period</span>
    <span class="scope-value">31 Mar 2026 – 8 Sep 2026</span>
  </span>
  <svg class="icon-16"><!-- chevron--down, chevron--up when open --></svg>
</button>
```

- `flex: 1 1 200px; min-width: 0`, 56px min-height, 3px left border — transparent when closed, `--cds-border-interactive` when open; background `--cds-layer-01` closed, `--cds-layer-selected-01` open.
- The label line carries the **comparison** as well as the word "Period", so the collapsed state states the full scope. The value line is the resolved range, ellipsised.
- Clicking toggles the full three-cell band, which appears **above** the sticky bar exactly as designed — same three cells, same flex-wrap, no grey plate, no inset padding.

**The filter bar packs onto one row and never three.** Its measured failure was five children totalling 1468px natural width against 604px available, forced into three rows because every field cell had `flex-grow: 1` on a 170–250px basis and the action cell was `flex: 0 0 auto` at 295px.

```css
.scope-toggle           { flex: 1 1 200px; min-width: 0; }
.filter-cell            { flex: 1 1 140px; min-width: 0; }   /* region, days, search */
.filter-actions         { flex: 1 1 auto;  min-width: 0; display: flex;
                          justify-content: flex-end; flex-wrap: wrap; }
```

One 56px row at ≥1056px; two rows at narrow widths; never three. Action labels are short — "Clear", not "Clear filters"; the updated-at stamp is a time, not a sentence.

**Removed with it**: the standalone "FILTERS" panel header, the "No filters applied" body line and the "More filters (11)" row. The filter-state sentence lives as helper text inside the bar, and every filter is reachable from the bar itself.

## Acceptance checks

```js
// collapsed by default: the band is not in the document
document.querySelectorAll('[aria-label="Reporting period"]').length            // 0

// the sticky bar is one or two rows, never three
(b => { const tops = [...b.children].map(c => c.offsetTop); return [b.offsetHeight, new Set(tops).size]; })
(document.querySelector('.filter-bar > div'))
// height <= 120, distinct row count <= 2

// toggling opens the band and flips the chevron + aria state
document.querySelector('.scope-toggle').click();
[document.querySelector('.scope-toggle').getAttribute('aria-expanded'),
 document.querySelectorAll('[aria-label="Reporting period"]').length]          // ["true", 1]

// content starts high on the page
document.querySelector('main h1').getBoundingClientRect().top                  // < 160
```

---

# 2. Incentive eligibility

A tab on **Field activity**, alongside Field activity and Call detail. Not a nav destination — it is an aspect of field activity, and the nav is capped at ten items.

## What is wrong now

The current screen reports the mechanism and buries the finding. It leads with four tier counts (10 / 49 / 111 / 460), then a wide rule table, then a percentile grid, then the qualifier list. Nowhere does it say the thing a reader needs in one line: **the rule awards a tier to 27% of the assessable field against a design that intended 85%.** A pay rule that fails three people in four is not a demanding rule, it is a broken measure, and that judgement is the screen's whole purpose.

Two specific defects:

- **The percentile grid** (10th / 25th / median / 75th / 90th per test) asks the reader to compute the finding themselves. Replaced by a **Median column and a per-test verdict** in the rule table, so "bronze sits above the median" is legible rather than derived.
- **Tier tags rendered as three identical gray pills.** `--cds-tag-yellow-bg` does not exist in this token set — the defined tag tones are gray, cool-gray, warm-gray, red, magenta, purple, blue, cyan, teal and green. Passing `type="yellow"` falls back silently, which made Gold, Silver and Bronze pixel-identical in the module whose entire subject is tier differentiation.

## Required structure

1. **Headline metric** — 27%, tagged "58 pts below target", with the answer sentence and a CTA into the 460 who missed.
2. **Chart card** — "Which test is doing the failing?" Horizontal bars of the 460 misses split by cause, with the answer line: days reported accounts for 149 of 179 assessable misses on its own.
3. **Tier tiles** — four, `repeat(4, minmax(0, 1fr))`, each carrying its **intended** share as well as its actual one ("2%" against "10% of the field was intended"). The Not-eligible tile carries the quality-gate count and an error left border.
4. **Rule card + threshold table**, side by side on `6fr 10fr`. The card states the logic in prose plus a four-row gate list; the table gives Gold / Silver / Bronze thresholds per test **plus Median and Verdict**.
5. **Qualifier table** — "Who qualifies, and why", with its own search / role / tier filters, right-aligned numeric columns, the sorted-column marker on Tier, an assessment sentence per row, and a 48px footer. Rows open the rep profile modal.

## Required tier chip

Tier is **ordinal**, and no metal hues exist in the token set. Encode rank as fill weight, not colour:

| Tier | Background | Border | Text |
| --- | --- | --- | --- |
| Gold | `--cds-background-inverse` | `--cds-background-inverse` | `--cds-text-inverse` |
| Silver | `--cds-layer-accent-01` | `--cds-border-strong-01` | `--cds-text-primary` |
| Bronze | `--cds-layer-02` | `--cds-border-subtle-01` | `--cds-text-secondary` |
| Not eligible | `--cds-tag-red-bg` | `--cds-tag-red-bg` | `--cds-tag-red-text` |

Solid → outlined → hairline is a three-step ramp that reads instantly, survives the dark theme, and survives a monochrome print. Do not substitute a hue for it, and do not reintroduce `type="yellow"`.

## Acceptance checks

```js
// tabs, not a nav item
[...document.querySelectorAll('.nav-item')].some(n => /incentive/i.test(n.innerText))   // false
document.querySelectorAll('[role="tab"]').length                                        // 3

// headline metric is the ratio, not a tier count
document.querySelector('.headline-metric .value').innerText                             // "27%"

// the four tier chips are visually distinct
[...document.querySelectorAll('.tier-chip')].map(c => getComputedStyle(c).backgroundColor)
// four different values — no two identical among Gold/Silver/Bronze

// no undefined tag tone anywhere
[...document.querySelectorAll('[class*=tag]')].some(t => getComputedStyle(t).backgroundColor === 'rgba(0, 0, 0, 0)')  // false

// rule table carries median and verdict
[...document.querySelectorAll('.rule-table thead th')].map(t => t.innerText)
// includes "Median" and "Verdict"
```

---

# 3. Rep profile modal

Opened from any person row — the Doctors table, the qualifier table, a drill-down list — and addressable by URL (`#rep=EC7195`).

## What is wrong now

The modal holds the right data and gives the reader no way to reach a judgement.

| # | Defect | Required |
| --- | --- | --- |
| 1 | **Dark hatched header** — gray-100 with a dot texture, ~210px tall. Carbon has no such surface, and the inner white highlight vanishes in the dark theme | Light header on `--cds-layer-01`, ~150px, no texture |
| 2 | **Six equal KPI tiles**, so "1,096 team Rx" and "0 own Rx" carry identical weight | Four tiles, with own-Rx and zero-Rx reps tinted `--cds-text-error` |
| 3 | **No verdict.** The story — a Gold-tier manager with zero personal prescriptions from 1,348 visits, and three of seven reps also at zero — is left for the reader to assemble from six tiles, a chart and two lists | A **verdict strip** directly under the identity block: one bold sentence plus one detail sentence, with a severity icon and a 4px left border |
| 4 | **Dual-axis chart** (visits left, Rx right 0–1.0). Violates the shared-scale rule, and the Rx series is flat at zero so it renders as an invisible line on the floor | Visits as bars on one scale, Rx as a floor band, answer line: "Visits held above 250 a month for five months and Rx never left the floor" |
| 5 | **Top doctors and Top products lists showing every value as 0**, with zero-length bars | A stated zero-state: all 544 covered doctors produced no Rx, so a ranked list of zeros is not drawn. The finding is the coverage-to-Rx gap, not its ordering |
| 6 | **One long scroll** — tiles, chart, reports, doctors, products, HR fields, then a four-screen attendance calendar | Four tabs |
| 7 | **Direct reports as a row of pills**, so "0 Rx" on three of them is easy to miss | A sorted table with an inline Rx bar, zero rows in error colour |
| 8 | **Attendance as six full month grids** (~1,000 date cells) | Seven month strips, one row per month, cell colour by call volume |

## Required structure

- **Shell** — `max-width: 1024px`, `max-height: calc(100vh - 64px)`, centred, `--cds-layer-02`, `0 2px 6px var(--cds-shadow)`, scrim `--cds-overlay`. Header and footer are `flex: 0 0 auto`; the body is the only scroller (`flex: 1 1 auto; min-height: 0; overflow-y: auto`).
- **Header** — 48px initials plate, role eyebrow, tier chip, 28px name, meta line (code · HQ · state · reports to · direct reports), then the verdict strip, then the tab row. Two 32px icon-only buttons top right: copy link, close.
- **Tabs** — Performance · Team · Days worked · Profile. Each tab's icon comes from the table in `CLAUDE.md`; `calendar--tools` for Days worked.
- **Performance** — four tiles, the month chart, then an "Own field activity" strip separating personal figures from the team roll-up. That separation is the point: a manager's team numbers and their own numbers must never sit in one undifferentiated row.
- **Team** — question + answer, then the direct-reports table, then the coverage-to-Rx zero-state.
- **Days worked** — 77% with "107 of 139 days", the answer line that attendance is not the problem, seven month strips, a three-step legend, and the note that approved leave is absent from the data so an empty day means "no call recorded", not "absent".
- **Profile** — two definition-list groups (Assignment, Record). No metric, no chart.
- **Footer** — the active period on the left; Export and "Open the coaching list" on the right.

## Acceptance checks

```js
// header is light and not textured
(h => [getComputedStyle(h).backgroundColor, getComputedStyle(h).backgroundImage])
(document.querySelector('.rep-modal-header'))
// not a gray-100 value; backgroundImage "none"

// verdict strip present, one sentence
document.querySelector('.rep-verdict').innerText.length                 // > 40

// four tiles, not six
document.querySelectorAll('.rep-tile').length                           // 4

// single shared scale on the month chart
document.querySelectorAll('.rep-chart [data-axis="right"]').length      // 0

// four tabs, and only the body scrolls
document.querySelectorAll('.rep-modal [role="tab"]').length             // 4
(m => [m.scrollHeight <= m.clientHeight, document.querySelector('.rep-body').scrollHeight > 0])
(document.querySelector('.rep-modal'))                                  // [true, true]

// no zero-length bar lists
[...document.querySelectorAll('.rep-modal .bar')].every(b => parseFloat(getComputedStyle(b).width) > 0)  // true

// URL addressable
location.hash                                                            // "#rep=EC7195"
```

---

# 4. Typographic pass (applies everywhere)

Four changes made across the whole design after the modules landed. They are cheap, they are what makes a figures-dense report read as considered, and they are easy to omit.

1. **Tabular figures on every data surface.** `font-variant-numeric: tabular-nums` on every `<table>` (inherited by cells), on every metric value, on every axis label. Without it, proportional digits make a column of numbers ragged and defeat vertical comparison — the main thing a reader does with these tables.
2. **Negative tracking on display figures.** `-0.64px` at 3.375rem, `-0.32px` at 2rem and 1.75rem. Carbon's large sizes go lighter; they also need tightening, or a 54px number looks loose against its label.
3. **Numeric columns right-aligned**, header included, with the identifier column at weight 600. Left-aligned numbers in a table are a defect, not a style choice.
4. **Value scales on every line chart.** Both line charts previously had gridlines and no labels, so magnitude was unreadable. Each now has a 32px label column at three to five round values, and the Trends gridlines were moved to land on round numbers (800 / 600 / 400 / 200 / 0) rather than arbitrary pixel offsets. Where a chart has a target line, the target is labelled on the plot.

## Acceptance checks

```js
// tabular figures on tables and metrics
[...document.querySelectorAll('table')].every(t => getComputedStyle(t).fontVariantNumeric.includes('tabular-nums'))  // true

// display figures tightened
getComputedStyle(document.querySelector('.headline-metric .value')).letterSpacing   // negative

// numeric table columns right-aligned
[...document.querySelectorAll('td.num, th.num')].every(c => getComputedStyle(c).textAlign === 'right')  // true

// every line chart has a labelled scale
[...document.querySelectorAll('.chart-line')].every(c => c.querySelectorAll('.axis-label').length >= 3)  // true
```

---

## Paste this into Claude Code

> Read `design_handoff_frontline_carbon/MODULES_SPEC.md` in full before editing anything.
>
> Implement its four parts in this order, each as its own reviewable diff.
>
> **1. Scope bar.** Collapse the reporting-period band behind one 56px toggle in the sticky filter bar, per `## 1`. Remove the standalone FILTERS panel header, the "No filters applied" body line and the "More filters (11)" row. Fix the filter-bar packing with the exact flex values given — the bar must be one row at 1056px and never three at any width.
>
> **2. Incentive eligibility.** Make it a tab on Field activity, not a nav item. Rebuild it in the five-part order in `## 2`: headline ratio, "which test is doing the failing?" chart with an answer line, four tier tiles carrying intended shares, rule card plus a threshold table with Median and Verdict columns, then the qualifier table. Delete the percentile grid. Implement the tier chip from the table in `## 2` — ordinal fill weight, not hue — and remove every `type="yellow"` tag; that tone does not exist in this token set and falls back silently.
>
> **3. Rep profile modal.** Rebuild per the eight-row defect table and the required structure in `## 3`: light header, verdict strip, four tabs, four tiles, single-scale month chart, direct-reports table, seven-strip attendance, stated zero-states. Keep it URL-addressable.
>
> **4. Typographic pass.** Apply all four changes in `## 4` across every screen, including the ones already built.
>
> Then run every console check in this file and paste the actual output of each, plus `python3 audit/_audit.py`. Do not report done until all pass at 1440px and at 1056px, in both themes.
