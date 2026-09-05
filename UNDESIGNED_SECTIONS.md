# Undesigned sections — specs and guidelines

Five sections are in the navigation but were not designed: **Needs action, Managers, Org tree, Guide, Notes.** This file carries enough direction to design and build them without another round with us.

Build them in the order below. Needs action first — it is the one HQ will look for. Until a section is built, it renders the shared empty state (`idea` icon on a 64px `--cds-layer-accent-01` plate, sentence-case title, one supporting line, one tertiary "Go to Pulse" button).

## How to design a screen in this system

Do not invent a new layout. Every screen is the same five moves, composed from the `_carbon.html` macros:

1. **Page header** — `page_header(eyebrow, title, desc)`. Eyebrow is always "Field Rx intelligence" with the section's icon. Title is sentence case. Description is one or two sentences saying what decision the screen supports.
2. **One headline metric** — `headline_metric()` under the eyebrow "Core metric": the single number this screen exists to move, a plain-language answer sentence, one primary CTA that opens the list behind it. Exactly one per screen. If you cannot name one number, the screen is a table, not a dashboard — skip straight to move 4.
3. **One chart card** answering a question — `chart_card()`, title phrased as a question, a bold one-line answer, then the graphic. If no chart answers a real question, leave it out rather than filling the space.
4. **Supporting figures or a table** — `tile_row()` in fours (every tile clickable into the drill panel with a named affordance), or `data_table()` with the sorted column marked and a footer carrying the range and one paging action.
5. **Drill-down** — every number and every row opens the existing panel. Never build a second panel or a modal.

Then run the per-screen checklist in `CLAUDE.md`. Loading, hover, focus, theming and copy rules are not optional extras — they are what makes a new screen feel like the rest of the app.

House rules for new work: no new colours, no new fonts, no new component patterns, no icon outside the table in `CLAUDE.md`, nothing below 12px, one purpose per element. If you find yourself wanting a pattern the design does not have, prefer the plainer thing that already exists.

---

## 1. Needs action

**Purpose.** The exceptions queue. HQ's working screen: what is broken, who owns it, what it costs.

**Question it answers.** What must someone do this week, and who?

The Pulse band is a four-row summary of this screen; the full screen extends it. Keep them consistent — same grouping, same ranking, same counts.

**Headline metric.** Open exceptions (50), with the count under an SLA age — e.g. "50 open · 14 older than 7 days". CTA: "See the oldest 14".

**Chart card.** "Are exceptions being cleared or accumulating?" — weekly opened vs closed, two series on one zero-anchored scale. Answer line states the direction.

**Body.** The four exception groups as a table, one row per group, ranked by what is at stake, not by count:

| Column | Notes |
| --- | --- |
| Severity | 4px bar + 40px icon plate, `--cds-support-error` or `--cds-support-warning` |
| Exception | Title states the finding; sub-line gives the rule that fired |
| Owner | Manager count; row click lists them |
| At stake | Doctors, planned calls or rupees |
| Age | Oldest item in the group |
| Action | "See the reps" |

Group rows expand into the drill panel listing every rep with the manager who owns the follow-up. Add a status filter (Open / Acknowledged / Cleared) as a fourth control in the filter strip **on this screen only**.

**States.** Loading: skeleton rows. Empty: "No open exceptions in this period" with the period named. Error: inline notification, do not blank the screen.

**Data needed.** Exception rule id, severity, rep, manager, opened-at, cleared-at, stake value and unit.

---

## 2. Managers

**Purpose.** Performance by manager rather than by rep — the layer HQ actually acts through.

**Question it answers.** Which managers' teams are converting, and which are not?

**Headline metric.** Spread between the best and worst manager's team conversion — e.g. "19 pts" — with the answer line naming how many managers sit below the national rate. CTA: "See the 12 below the line".

**Chart card.** "Is the gap coaching or territory?" — team conversion against doctors met per rep, as a simple two-column comparison per manager (not a scatter; the app has no scatter pattern). Answer line states whether the low group also has low coverage.

**Body.** Manager table sorted worst-conversion-first: Manager · Region · Reps · Doctors met · Rx · Team conversion (inline 96px bar, threshold-coloured like the Doctors screen) · Open exceptions. Row click opens the drill panel listing that manager's reps with each rep's conversion.

Reuse the Doctors screen's table treatment exactly, including the initials plate. Two screens with the same shape must look identical.

**Data needed.** Manager, region, rep roster, per-rep aggregates, open exception count per manager.

---

## 3. Org tree

**Purpose.** Structure and territory ownership. A reference screen, not an analysis screen.

**Question it answers.** Who reports to whom, and which territory is whose?

**No headline metric and no chart.** Do not manufacture either. Lead with the page header, then a four-tile row of structural counts (regions, managers, reps, unassigned territories — the last one tinted warning if non-zero and clickable).

**Body.** An indented hierarchy list, not a drawn tree: region → manager → rep, each row 48px with the person's initials plate, name, territory and rep count. Rows expand and collapse with `chevron--down` / `chevron--right`; state persists in the URL so a view is shareable. Indent 24px per level, one hairline per group, never per row. Rep rows open the drill panel with that rep's detail.

If the roster exceeds ~200 rows, page it with the same footer treatment rather than virtualising.

**States.** Empty: "No reporting lines recorded for this region". Flag unassigned territories with a warning tag in place of a name.

**Data needed.** Region, manager, rep, territory code, assignment status.

---

## 4. Guide

**Purpose.** How every figure on the report is calculated. This is what stops the "your number is wrong" argument.

**Question it answers.** What exactly does this metric count, and what does it exclude?

**No metric, no chart, no table.** A document screen: `max-width: 720px`, left aligned, and the only screen in the app allowed to be a single column of prose.

**Body.** One entry per metric, in the order the metrics appear in the app. Each entry:

- metric name as a 1.25rem/400 heading;
- one-sentence definition in 14px body;
- the formula in Plex Mono at 14px on `--cds-layer-01` with 16px padding — the one sanctioned use of mono;
- "Includes" and "Excludes" as two short lists;
- the source table or report the figure comes from;
- a "Used on" line linking the screens where it appears.

Group entries under the same five section names as the nav so the structure matches. Add a jump list at the top — anchor links, not tabs.

Metrics to document, at minimum: Rx conversion, Total Rx, Doctors met, Rx doctors, Doctors met with no Rx, Zero-Rx reps, Doctor coverage, Calls logged, Calls per rep per working day, Avg Rx per call, Rx per doctor met, Rx per day, Samples per Rx, each exception rule, and the comparison periods.

Write the definitions with the data owner. Do not guess a formula — an authoritative-looking wrong definition is worse than an empty entry, so mark anything unconfirmed "Definition pending" with a `gray` tag.

---

## 5. Notes

**Purpose.** Data caveats, cut-offs and known gaps for the current period. Read before quoting a number in a meeting.

**Question it answers.** What should I know before trusting these figures?

**No metric, no chart.** Same 720px document column as Guide.

**Body.** A reverse-chronological list of notes. Each note: date (`1 Sep 2026`), a severity tag (`red` blocking / `yellow` caveat / `gray` informational), a sentence-case title, one or two sentences of detail, and the screens affected. New notes since the user's last visit get a `blue` "New" tag — that is what the nav's "3 new" metric counts.

Keep the note count in the nav and the count of `New` tags derived from one query.

**States.** Empty: "No notes for this period", which is a good state, not a failure — do not tint it warning.

**Data needed.** Note text, severity, date, affected screens, publication state.

---

## Cross-cutting requirements for all five

- Register each screen in the nav model with its icon, metric and description from the table in `README.md`; wire the metric to the same query that feeds the screen.
- Period and filters from the reporting-period band and the filter strip apply here too — including on the two document screens, where the period governs which notes and which metric definitions are current.
- Every screen works at 320px of nav plus a 1056px content area, and in the collapsed rail; every screen works in both themes.
- Every fetch uses the shared loading helper. Document screens get skeleton text blocks, not spinners.
- Nothing on these screens introduces a pattern the five designed screens do not already use. If you believe one is genuinely needed, build the plain version, ship it, and raise the pattern separately.
