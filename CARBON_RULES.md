# Carbon rules — Frontline

Binding spec for every screen of this app. Values come from `carbon-tokens.css`; never write a literal.

## Absolute rules

1. **Radius 0** on everything except tags/pills (fully rounded), the toggle knob and the loading spinner.
2. **Blue 60 `--cds-interactive` is the only interactive colour.** Links, focus, selection, primary buttons, active nav, chart series 1. If something is blue it is interactive or it is data.
3. **Colour carries meaning or it is absent.** A tile gets a coloured left border only in error or warning. Neutral tiles get `--cds-border-subtle-00`. No decorative accent bars.
4. **Spacing on the 8px scale only**: 2 / 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64.
5. **No shadows except overlays and sticky bars.** Menus, modals, the drill panel and the sticky filter strip get `0 2px 6px var(--cds-shadow)`. Tiles and cards are flat, no border, no shadow — separation comes from 1px grid gaps over `--cds-border-subtle-00`.
6. **No gradients, no background images, no textures beyond the sanctioned set below, no emoji.**
7. **Motion 70–240ms**, `cubic-bezier(0.2,0,0.38,0.9)`. Fades and slides. Nothing scales, springs or bounces.
8. **Hairlines are `--cds-border-subtle-01`.** `--cds-border-strong-01` (#8d8d8d) is for input underlines and chart axes, not for dividing rows — at list density it reads as noise. Any surface should have single-digit hairlines, not one per row.

## Type

| Role | Size / line-height | Weight | Tracking |
| --- | --- | --- | --- |
| Headline metric | 3.375rem / 1.07 | 300 | 0 |
| Period range | clamp(1.25rem, 2.4vw, 1.75rem) / 1.29 | 300 | 0 |
| Page title (h1) | 2rem / 1.25 | 400 | 0 |
| Section heading (h2) | 1.25rem / 1.4 | 400 | 0 |
| Card title | 1rem / 1.5 | 600 | 0 |
| Tile value | 2rem / 1.25 | 400 | 0 |
| Body | 0.875rem / 1.43 | 400 | 0.16px |
| Nav item name | 0.875rem / 1.29 | 400 (600 active) | 0.16px |
| Label, helper, eyebrow, metric | 0.75rem / 1.33 | 400 (600 for metrics and section labels) | 0.32px |

IBM Plex Sans 300/400/600. Plex Mono only for code and fingerprints. Large sizes go *lighter*, never bolder. Never below 12px.

## Controls

Heights: sm 32 · md 40 · lg 48 · xl 64. Inputs and selects sit on `--cds-field-01` with **only** `border-bottom: 1px solid var(--cds-border-strong-01)`. Buttons: square corners, left-aligned labels, `padding: 0 63px 0 15px`. Icon-only buttons are 32px with `title` **and** `aria-label` worded as the action.

## Grid

Carbon 2x grid: 16 columns ≥1056px, 32px gutters, 16px page margins, breakpoints 320 / 672 / 1056 / 1312 / 1584.

- **Hero split** `grid-template-columns: 6fr 10fr` — 6 and 10 of 16. Never `minmax()` pairs; their edges line up with nothing.
- **Tile rows** `repeat(4, minmax(0, 1fr))`, `gap: 1px`. Design content to divide into four.
- **Any wrapping row whose item count does not divide the track count uses flex-wrap, not `auto-fit` grid** — `display: flex; flex-wrap: wrap; gap: 1px` with a `flex: 1 1 <basis>` per item, so a wrapped line grows to fill. With `auto-fit`, leftover tracks paint as grey slabs through the gap-background. This bit the reporting-period band and its preset tiles; do not reintroduce it.
- Every flex child that holds text needs `min-width: 0`, or a sibling with `flex: 0 0 auto` crushes it to zero width and the text overflows on top of it.

## Loading states

Every state change that would hit the server shows a loading state. Four kinds, no others.

| Kind | When | Treatment |
| --- | --- | --- |
| Page progress | any refetch: screen change, period change, comparison change, filter change, refresh | 4px indeterminate bar at the bottom of the filter strip, `--cds-interactive` on `--cds-border-subtle-00`, 1.4s loop, `role="progressbar"` |
| Skeleton | the values being refetched | block in `--cds-skeleton-element` (text, numbers, bars) or `--cds-skeleton-background` (chart plots), sized to the content it replaces, `cdsSkel` opacity pulse 1500ms |
| Inline spinner | an action in flight inside a control | 16px Carbon `Loading` in place of the control's icon; label becomes the present participle |
| Disabled + label | a job the user must not restart | control disabled, label states the job ("Preparing export") |

Rules:
- **Never block reading.** No overlay, no modal progress card. The report stays interactive.
- **Skeleton for content, spinner for actions.** A number, row or chart being fetched shows a skeleton of its own shape and size so nothing reflows on arrival.
- **Micro-loading counts.** Drill-panel opens, table paging, exports and single-filter changes each get a treatment. A control that does work and shows nothing is a bug.
- **Route every refetch through one helper** (`load(patch, ms)` in the reference) so the treatment cannot drift.
- Keep skeletons visible ~300ms minimum; a flash reads as a glitch.

## Charts

- Series 1 `--cds-interactive`; series 2 `--cds-support-warning`; target and threshold lines dashed `4 4` in `--cds-support-warning`; gridlines `--cds-border-subtle-00`; axis `--cds-border-strong-01`.
- **Every chart card has the same header**: question title (1rem/600), 12px helper sub-line, 32px ghost `maximize` button on the right. Then a bold one-line answer. Then the graphic.
- **Multi-series charts share one zero-anchored scale.** Per-series normalisation makes a flat series look volatile and can invert the story the copy tells.
- Sanctioned textures, and only these: a 1px repeating column/row grid behind a plot (`--cds-border-subtle-01`), a 135° 2px hatch to mark a negative or excluded segment, a filled area under a line in `--cds-highlight`, and a 24px dot grid on empty states.
- Bars: 16px horizontal, 8px gaps for columns. Value labels outside the bar in `--cds-text-primary`.

## Icons

`@carbon/icons` only, drawn on the 32 grid, rendered at 16px in UI, 20px for section and item icons, 32px in empty states. Never draw an approximation, never a unicode glyph or emoji. Recolour with `--cds-icon-primary` (active) / `--cds-icon-secondary` (resting), `--cds-text-on-color` on a blue chip, or a status colour for status glyphs. **Pass `size` as a number, not a string** — a string silently renders 0×0.

| Meaning | Icon |
| --- | --- |
| Pulse / overview | `dashboard` |
| Rx, prescriptions | `pills` |
| Trends, movement over time | `chart--line` |
| Field activity, calls | `events` |
| Doctors | `stethoscope` |
| Exceptions, needs action | `warning--alt--filled` |
| Managers | `user--multiple` |
| Org tree, one person | `user` |
| Guide | `book` |
| Notes | `document` |
| Performance section | `analytics` |
| Volume section heading | `growth` |
| Rates / table section heading | `table--split` |
| Call list heading | `list--checked` |
| Coverage, territory grid | `grid` |
| Opportunity, target | `target` |
| Reporting period | `calendar--heat-map` |
| Quick range, elapsed time | `time` |
| Comparison | `compare` |
| Collapse / expand the rail | `side-panel--close` / `side-panel--open` |
| Dark / light theme | `asleep` / `light` |
| Refresh | `renew` |
| Filters | `filter` |
| Clear, dismiss, close | `close` |
| Export | `download` |
| Expand a chart | `maximize` |
| Sorted column | `sort--descending` |
| Forward navigation on a button | `arrow--right` |
| Up / down / flat | `arrow--up` / `arrow--down` / `subtract` |
| Info, helper | `information` |
| Empty state | `idea` |

Status glyphs keep fixed colours: `error--filled` red 60, `warning--filled` yellow 30, `checkmark--filled` green 50, `information--filled` blue 70.

## Copy

Sentence case everywhere. Plain, declarative, no superlatives, no exclamation marks. Numerals for counts, Indian grouping for large figures (`2,49,720`). Dates `1 Sep 2026`. "and", not "&". No emoji. No ellipsis in loading labels.

- **Answer lines state the finding, not the metric.** "For 6 doctors in 7, it did not," not "Conversion rate: 15%."
- **Drill affordances name what opens**: "See the 20 reps", "See by region", "See the 4,172 doctors" — never "View", "Details", "More".
- **Buttons are verb + noun, 1–4 words**: "Export to Excel", "Show the next 10 reps", "Go to Pulse", "Clear filters".
- **Loading labels are present participle**: "Updating figures", "Preparing export", "Loading".
- **State labels name the target, not the current state.** In light mode the theme control reads "Dark theme" with the `asleep` icon.
- **Filter state is stated in words**, not inferred from the controls.
- **Counts agree everywhere.** Nav badge, exceptions band and the exceptions screen come from one query.
- Empty states: sentence-case title naming the thing, one supporting line, one tertiary button.

## Known pitfalls

Every one of these shipped at least once during the design and cost a review cycle.

1. **Undefined tokens fail silently** — the property renders as nothing, or inherits. These names do **not** exist in this token set: `--cds-layer-accent-03`, `--cds-support-warning-inverse`, `--cds-support-success-inverse`, `--cds-text-inverse-secondary`. There is no secondary inverse text token; use `--cds-text-inverse` and differentiate by size. CI gate 2 exists for this.
2. **`--cds-layer-02` is `#ffffff` in the White theme, the same as `--cds-background`; `--cds-layer-01` is the `#f4f4f4` grey.** Layering is not "higher number = darker". To make a surface read as a distinct plate, put it on `layer-01` or `layer-accent-01` with its cards on `layer-02`, or give it a hairline — do not assume a layer step is visible.
3. **Neither White-theme success nor warning token passes 4.5:1 as 12px text.** `--cds-support-success` is ~3.35:1, green 40 ~2.4:1. Tint only the error case (`--cds-text-error`); carry success and warning severity with a tag or a status icon instead of coloured small text.
4. **`auto-fit` grids leave remainder tracks** that paint through a gap-background. Use flex-wrap for any row whose item count does not divide the track count.
5. **A flex child without `min-width: 0`** gets crushed to zero by a fixed-basis sibling, and its text paints on top of the neighbour.
6. **A component mount with no explicit height collapses.** Give sticky bars and header mounts a real height.
7. **Shrinking a full lockup is not the same as using a mark.** Below ~160px wide the BB wordmark is illegible; use the mark and set the name in type.

---

## Per-screen checklist

- [ ] Zero hex, `rgb()` or `rgba()` literals outside `carbon-tokens.css`.
- [ ] Zero undefined tokens: every `var(--cds-*)` used resolves to a non-empty computed value.
- [ ] Every icon mount renders non-zero (numeric `size`, mask URL resolves).
- [ ] Every border radius is 0, except tags, the toggle knob and the spinner.
- [ ] Content resolves to the grid: hero 6/10, tile rows in fours, 16px page margins, flex-wrap wherever a row can leave a remainder.
- [ ] No orphaned grid cells: no gap-background visible as a slab anywhere.
- [ ] Exactly one headline metric on the screen.
- [ ] Every supporting metric tile is clickable and opens the drill panel.
- [ ] Every chart title is a question, has a bold answer line, and a `maximize` button.
- [ ] Multi-series charts share one zero-anchored scale.
- [ ] Tables: 48px rows, accent-01 header, sorted column marked, footer with range and one paging action, no zebra, no vertical rules.
- [ ] Every fetch shows page progress plus skeletons; every in-flight action shows a spinner or a disabled label; nothing blocks reading.
- [ ] Every interactive element shows the 2px Blue 60 focus ring on keyboard focus.
- [ ] Every icon-only control has `title` and `aria-label`.
- [ ] Renders correctly in both `:root` and `[data-carbon-theme="g100"]`.
- [ ] Period and filters are reflected in the URL; the active scope is visible as tags and as a sentence.
- [ ] Copy: sentence case, verb + noun buttons, named drill affordances, no emoji, no ampersands, counts agree with the nav badges.
- [ ] Nav: item metrics come from the same queries as their screens; collapsed rail keeps icons, active borders, dots and tooltips.
- [ ] Hairline count on the surface is in single digits.
