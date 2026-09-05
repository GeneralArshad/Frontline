# Conformance — definition of done, item by item

The 19 checklist items in `CARBON_RULES.md`, each restated as **a thing that is either present in the built template or not**. The audit script in `audit/_audit.py` scores exactly this list.

Read this before starting a screen, and again before calling one done. Prose in the README explains *why*; this file is the contract.

**Every screen pass ends with the audit at 0 FAIL.** A screen is not done because it looks right; it is done when the score says so and the unverifiable items have been eyeballed.

Items 5, 9, 10, 11, 12, 14, 17 and 18 are the ones that get stubbed. They are the ones with the most detail below, for that reason.

---

## 1. No colour literals below the tokens — SOURCE

No `#hex`, `rgb()` or `rgba()` anywhere except the token block and `carbon-tokens.css`. The one exemption is a brand asset's own fills (the Hive wordmark SVG), exempt **by name** in the audit, not by pattern.

Scrims use `--cds-overlay`. Semi-transparent whites over dark surfaces need a token; if none exists, restructure rather than inline an rgba.

## 2. No undefined tokens — SOURCE

Every `var(--cds-*)` referenced resolves to a definition. The four names that cost this design four review cycles: `--cds-layer-accent-03`, `--cds-support-warning-inverse`, `--cds-support-success-inverse`, `--cds-text-inverse-secondary`. Using a name that is undefined is the offence — if your token set genuinely defines one of these, it is not a failure.

## 3. Icons render non-zero — SOURCE

Every icon is a real `@carbon/icons` glyph on the 32 grid, from the table in `CARBON_RULES.md`, with a numeric size. No zero-width mounts, no drawn approximations, no unicode glyphs, no emoji.

## 4. Radius 0 except tags — SOURCE

`border-radius` is 0 everywhere except tags/pills (fully rounded), the toggle knob and the spinner.

## 5. Grid: hero 6/10, tile rows in fours — SOURCE

**Definition of done.** The CSS contains both, literally:

```css
grid-template-columns: 6fr 10fr;              /* every hero split */
grid-template-columns: repeat(4, minmax(0, 1fr));  /* every metric tile row */
```

Not `1fr 1.6fr`. Not `minmax(320px, 1fr) minmax(340px, 1.4fr)`. Not `auto-fit`. The two literal declarations are what makes tile edges line up with the hero edge above them, and the audit greps for exactly these strings.

Rows that wrap (period band, quick-range presets) are the exception and use flex-wrap with a `flex: 1 1 <basis>` — see item 6.

If a screen has fewer than four supporting metrics, either find the fourth that earns its place or drop the row; do not widen three tiles across four tracks.

## 6. No gap-background slabs — SOURCE

No rule combines `auto-fit` with `gap: 1px` over a background colour. Wrapping rows use `display: flex; flex-wrap: wrap; gap: 1px` so a wrapped line grows to fill.

## 7. Exactly one headline metric per reporting screen — LIVE

One `headline_metric` per screen, under the eyebrow "Core metric": a 54px/300 number, a plain-language answer sentence, one primary CTA into the list behind it. Document screens (Guide, Notes) and Org tree have none by design — assert zero there, not one.

## 8. Every supporting tile opens the drill panel — SOURCE

**A role and a tabindex are not a behaviour.** Each tile must attach a real handler that calls the app's drill entry point. The audit greps the tile-wiring function for `onclick`/`addEventListener` **and** a drill call; a function that only sets `role="button"` and `tabindex="0"` fails, correctly.

Same for table rows and exception rows. Every number a user can see, they can open.

## 9. Chart titles are questions with an answer line — SOURCE

**Definition of done.** Every chart card has all four parts, in this order:

1. `<h3>` whose text **ends in a question mark** — "Where did conversion go this quarter?"
2. a 12px helper sub-line naming the series and the window — "Weekly Rx conversion against the 17.1% target"
3. an **answer line**: one sentence, 14px, `font-weight: 600`, stating the finding in words — "It has been flat since week 18. The dip is not seasonal — call volume rose 6% over the same weeks."
4. the graphic

The answer line is the item that gets skipped, and it is the one that makes the report readable by someone who does not read charts. It is not a caption and not the sub-line: it is a claim. Write it from the data, and regenerate it when the period changes — a hardcoded answer under a filtered chart is worse than none.

The audit counts `<h3>` elements ending in `?` against the number of chart cards, and checks an answer-line element exists per card. Both must match the card count.

The 13 chart titles used in the design, verbatim, are in the five designed screens of `Frontline Rx Intelligence v3.dc.html`. Reuse them; write new ones in the same voice.

## 10. Multi-series charts share one zero-anchored scale — SOURCE

**Definition of done.** No `yAxisID` and no second axis object anywhere. One scale, `beginAtZero: true`, shared by every series in the chart.

Per-series normalisation is the specific defect: it makes the flat series look volatile and inverts the story the answer line tells. On Trends, calls and Rx must sit on one 0-based axis so the widening gap between them **is** the graphic.

If two series differ in magnitude enough to make a shared scale useless, they are two charts, not two axes.

## 11. Table geometry — SOURCE

**Definition of done.** Every data table has all five:

- rows `height: 48px`;
- header row on `--cds-layer-accent-01`, weight 600, left aligned;
- **no zebra striping** — no `nth-child(odd|even|2n)` rule anywhere;
- a **footer**: a 48px bar with `border-top: 1px solid var(--cds-border-subtle-01)`, the range on the left ("Showing 1 to 10 of 639 reps"), one paging action on the right whose label names what loads ("Show the next 10 reps") and which shows an inline spinner while loading;
- a **sorted-column marker**: `sort--descending` at 16px in `--cds-icon-primary`, in the header cell of the column the data is actually sorted by.

The footer and the marker are the two that get dropped. Without the marker a worst-first table looks like an arbitrary list, which is the whole point of the Doctors and Managers screens. Without the footer the user cannot tell 10 rows from 639.

Row separators are `border-top: 1px solid var(--cds-border-subtle-01)`. No vertical rules.

## 12. Loading: progress plus skeletons, never blocking — SOURCE

**Definition of done.** All four exist and are reachable:

- one helper (`load(patch, ms)` or equivalent) that **every** refetch goes through;
- an indeterminate 4px bar at the bottom of the filter strip — `role="progressbar"`, `--cds-interactive` fill on `--cds-border-subtle-00`, 1.4s loop;
- skeleton blocks (`--cds-skeleton-element` for text/numbers/bars, `--cds-skeleton-background` for chart plots), each **sized to the content it replaces** so nothing reflows on arrival, with the `cdsSkel` opacity pulse;
- an inline 16px spinner + present-participle label for in-flight actions, and disabled + label for jobs.

And one prohibition: **nothing blocks reading.** No overlay, no modal progress card, no spinner covering the report.

Coverage required, not just existence: screen switch, period change, comparison change, each filter change, table paging, drill-panel open, export. Seven paths. A control that does work and shows nothing is a bug.

## 13. Focus ring — SOURCE

`outline: 2px solid var(--cds-focus); outline-offset: -2px` on every interactive element. Never `outline: none`.

## 14. Icon-only controls carry title and aria-label — SOURCE

**Definition of done.** Every button whose entire content is an icon has **both** `title` and `aria-label`, worded as the action: "Close panel", "Expand chart", "Collapse navigation", "Open menu", "Refresh figures".

A button with visible text ("Clear filters") needs neither — the audit only looks at icon-only buttons, so a failure here is real. The two that failed in the first build, `burger` and `pclose`, are exactly the kind that get missed: chrome added late, outside the screen work.

## 15. Renders in White and Gray 100 — LIVE

`data-carbon-theme="g100"` on `<html>` inverts background and text together. Assert both, on every screen. Check that patterns, hatches and area fills survive the swap — a texture built from a light-theme border colour disappears on the dark surface.

## 16. Scope visible as tags and a sentence; period in the URL — SOURCE

The active period, comparison, region and days appear as tags near the page title **and** as a plain sentence in the filter strip. Period, comparison and filters are all in the URL query string so a view is shareable.

## 17. Copy: sentence case, no emoji, no ampersands — SOURCE

**Definition of done.** Zero emoji. Zero `&` in prose ("and"). Zero shouted strings — the only all-caps text permitted is the five nav section labels and 12px uppercase eyebrows/labels, which the audit whitelists by name.

Then the patterns from `CARBON_RULES.md` → Copy: verb + noun buttons of 1–4 words, present-participle loading labels, drill affordances that name what opens, state labels naming the target, Indian digit grouping, dates as `1 Sep 2026`, definitions with periods.

Five ampersands and three emoji in a first build means copy was written outside the rules and never re-read. Do the audit pass on strings as its own commit — it is faster than fixing them per screen.

## 18. Nav items carry a live metric and description — SOURCE

**Definition of done.** Every nav item renders **three** lines of content, not one:

```
[icon chip]  Field activity              [Below 10]
             7.6/day  Calls, day plans, visit records
```

- the name (14px, 600 when active), with an optional tag;
- the **metric** (12px/600) — that item's own headline number, wired to the same query that feeds its screen;
- the **description** (12px `--cds-text-helper`, ellipsised).

The metric and description table is in `README.md` → Information architecture. This is not decoration: the nav doubles as a status board, it is why items are 60px rather than 32px, and it is the reason the top header bar could be removed. A labels-only nav is a different design.

Collapsed rail: labels hidden, icon chip and active border visible, badge counts become a 6px red dot (absolutely positioned), tooltip carries name and description.

## 19. Hairline count in single digits — EYE

Not decidable from source; the audit reports it unverified. Check by eye per surface: **no more than three hairlines in the nav** (masthead bottom, footer top, user-row bottom), and none between nav items or around section labels. Dividers are `--cds-border-subtle-01`; `--cds-border-strong-01` is for input underlines and chart axes only.

---

## Running the gate

```
python3 audit/_audit.py path/to/built_template.html
```

Exit 1 on any FAIL. UNVERIFIED does not fail the build — item 19 is eyeballed, and counting an unverifiable item as a pass is how a score becomes a lie.

Wire it into CI alongside the two colour/token gates. Add an item whenever a defect survives review twice: the correlation held on the first build, where everything the suite checked stayed correct through six rebuilds and everything it did not check was stubbed or missing.
