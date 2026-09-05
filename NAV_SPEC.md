# Side navigation — exact spec and fix

The nav in the current build deviates from the design in eight structural ways. This file is the nav-only contract: the deviations, the required DOM, the required CSS, and measurable acceptance checks. It supersedes prose about the nav elsewhere in the handoff.

Read `## Required DOM` and `## Required CSS` as normative. If your implementation differs in structure, change the implementation — do not adapt the spec.

---

## What is wrong now

Evidence from the deployed build, in priority order.

| # | Deviation | Evidence in the build | Required |
| --- | --- | --- | --- |
| 1 | **Nav is far too wide** | ~437px | **320px** expanded, **72px** rail. Fixed, not a percentage, not `min-content` |
| 2 | **Item text wraps to 2–3 lines** | "Field activity", "Doctors by rep", "Needs action", "Org tree" all wrap | Name never wraps; description ellipsises on one line |
| 3 | **Name, metric and description are on one inline run** | "Field activity **10.23/day** Calls, day plans, visit records" flows as one paragraph | **Two rows**: name (+ optional tag) on row 1; metric + description on row 2 |
| 4 | **No icon chip** | bare 16px glyph floating left of the text | 36px square chip, 1px border, 20px glyph inside |
| 5 | **Two items that should not be in the nav** | "Call detail" and "Doctors by rep" are nav destinations | 10 items only. Call detail is a tab inside Field activity; Doctors by rep is a tab inside Doctors |
| 6 | **Section labels have no icon** | "FIELD", "ACTION", "TEAM", "REFERENCE" are bare text | 16px icon + 12px/600 uppercase label, 24px of space above each group |
| 7 | **Active item is a full blue outline box** | Notes has a 4-sided blue border and an inset ring | White plate (`layer-02`) + **4px left border** in blue + blue icon chip + name at 600. No box, no ring |
| 8 | **Footer controls are labelled text rows** | "Dark theme" and "Collapse navigation" as full-width rows | Two **32px icon-only buttons**, right-aligned on one row, `title` + `aria-label` only |

Two content errors visible in the same screenshot, both from wiring the wrong query:

- **Trends metric reads `2,64,175`** — that is a call count. Trends' metric is the **period delta** (`+6.2%`), because the item's job is to say which way things moved.
- **Doctors metric reads `73.4%`** — the design's metric is **doctors met** (a count). If you prefer coverage %, change the description too; do not mix one item's metric with another's meaning.

---

## Anatomy

```
┌────────────────────────────────┐  320px
│ [ Hive FRONTLINE » logo ]      │  masthead, layer-02, 52px logo
│ ──────────────────────────     │  hairline
│ Rx intelligence                │  14px/600
├────────────────────────────────┤
│                                │  24px
│ ⌾ PERFORMANCE                  │  section label, 12px/600 upper
│ ┌──┐                           │
│ │▣ │ Pulse                     │  ← item, 60px, no separators
│ └──┘ 15%  Conversion, volume…  │
│ ┌──┐                           │
│ │▣ │ Rx engine                 │
│ └──┘ 9,608  Prescriptions and… │
│                                │  24px
│ ⌾ FIELD                        │
│ …                              │
├────────────────────────────────┤  hairline
│ AR  Arshad                     │  56px user row
│     HQ · Admin · All regions   │
│ ▣ British Biologicals   ☾  ⇤   │  BB mark + 2 icon buttons
└────────────────────────────────┘
```

Nav surface is `--cds-layer-01` (the grey). Masthead is `--cds-layer-02` (white). Footer is `--cds-layer-accent-01`. The active item is `--cds-layer-02`, i.e. the same white as the content area, which is what makes it read as lifting out of the plate.

**Exactly three hairlines in the whole nav**: under the masthead logo, under the masthead title block (the rule above "Rx intelligence" counts as this one), and above the footer. None between items. None around section labels.

---

## Required DOM

One item, verbatim in structure. Class names are yours to rename; the **nesting and the row split are not optional** — they are what stops deviation 2 and 3.

```html
<a class="nav-item" href="/field-activity" aria-current="false">
  <span class="nav-chip" aria-hidden="true">
    <svg class="icon-20" viewBox="0 0 32 32"><!-- events --></svg>
  </span>
  <span class="nav-body">
    <span class="nav-line1">
      <span class="nav-name">Field activity</span>
      <span class="tag tag--gray">Below 10</span>   <!-- optional -->
    </span>
    <span class="nav-line2">
      <span class="nav-metric">7.6/day</span>
      <span class="nav-desc">Calls, day plans, visit records</span>
    </span>
  </span>
  <span class="nav-dot" hidden></span>              <!-- rail only, when badged -->
</a>
```

Section:

```html
<div class="nav-section">
  <div class="nav-section-label">
    <svg class="icon-16" viewBox="0 0 32 32"><!-- events --></svg>
    <span>Field</span>
  </div>
  <!-- items -->
</div>
```

Footer:

```html
<div class="nav-footer">
  <div class="nav-user">
    <span class="avatar">AR</span>
    <span class="nav-user-text">
      <span class="nav-user-name">Arshad</span>
      <span class="nav-user-meta">HQ · Admin · All regions</span>
    </span>
  </div>
  <div class="nav-footer-row">
    <span class="nav-brand">
      <svg class="bb-mark" viewBox="143.94 0 76.18 74.45"><!-- 4 quadrant paths --></svg>
      <span>British Biologicals</span>
    </span>
    <button class="icon-btn" title="Dark theme" aria-label="Dark theme">
      <svg class="icon-16" viewBox="0 0 32 32"><!-- asleep --></svg>
    </button>
    <button class="icon-btn" title="Collapse navigation" aria-label="Collapse navigation">
      <svg class="icon-16" viewBox="0 0 32 32"><!-- side-panel--close --></svg>
    </button>
  </div>
</div>
```

---

## Required CSS

```css
.nav {
  position: sticky; top: 0;
  flex: 0 0 auto;
  box-sizing: border-box;          /* all three needed or the rail cannot collapse */
  min-width: 0;
  overflow: hidden;
  width: 320px;
  height: 100vh;
  background: var(--cds-layer-01);
  border-right: 1px solid var(--cds-border-subtle-01);
  display: flex; flex-direction: column;
  transition: width 240ms cubic-bezier(0.2, 0, 0.38, 0.9);
}
.nav[data-rail="true"] { width: 72px; }

/* masthead */
.nav-masthead {
  flex: 0 0 auto; box-sizing: border-box;
  padding: 20px;
  background: var(--cds-layer-02);
  border-bottom: 1px solid var(--cds-border-subtle-01);
}
.nav-masthead img { display: block; height: 52px; width: auto; max-width: 100%; }
.nav-masthead .nav-report-name {
  display: block; margin-top: 8px; padding-top: 8px;
  border-top: 1px solid var(--cds-border-subtle-01);
  font-size: 0.875rem; line-height: 1.29; letter-spacing: 0.16px;
  font-weight: 600; color: var(--cds-text-primary);
}

/* scroller */
.nav-scroll { flex: 1 1 auto; overflow-y: auto; overflow-x: hidden; padding: 0 0 24px; }
.nav-section { padding-top: 24px; }
.nav-section-label {
  box-sizing: border-box; min-height: 24px;
  display: flex; align-items: center; gap: 8px;
  padding: 0 20px 8px;
  white-space: nowrap; overflow: hidden;
  font-size: 0.75rem; line-height: 1.33; letter-spacing: 0.32px;
  font-weight: 600; text-transform: uppercase;
  color: var(--cds-text-secondary);
}

/* item — grid, so the chip can never push text into a wrap */
.nav-item {
  position: relative; box-sizing: border-box;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);   /* the fix for deviations 2 and 3 */
  align-items: center;
  column-gap: 16px;
  width: 100%; min-height: 60px;
  padding: 8px 20px 8px 16px;
  background: transparent;
  border: none;
  border-left: 4px solid transparent;
  text-align: left; text-decoration: none; cursor: pointer;
  transition: background 110ms cubic-bezier(0.2, 0, 0.38, 0.9);
}
.nav-item:hover  { background: var(--cds-layer-hover-01); }
.nav-item:active { background: var(--cds-layer-active-01); }
.nav-item:focus-visible { outline: 2px solid var(--cds-focus); outline-offset: -2px; }

.nav-chip {
  width: 36px; height: 36px;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--cds-layer-02);
  border: 1px solid var(--cds-border-subtle-01);
}
.nav-body  { min-width: 0; }                     /* required, or text overflows siblings */
.nav-line1 { display: flex; align-items: center; gap: 8px; min-width: 0; }
.nav-line2 { display: flex; align-items: baseline; gap: 6px; margin-top: 2px; min-width: 0; }

.nav-name {
  flex: 1 1 auto; min-width: 0;
  font-size: 0.875rem; line-height: 1.29; letter-spacing: 0.16px;
  color: var(--cds-text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nav-metric {
  flex: 0 0 auto;
  font-size: 0.75rem; line-height: 1.33; letter-spacing: 0.32px; font-weight: 600;
  color: var(--cds-text-secondary);
  white-space: nowrap;
}
.nav-desc {
  min-width: 0;
  font-size: 0.75rem; line-height: 1.33; letter-spacing: 0.32px;
  color: var(--cds-text-helper);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* active — plate + left edge only. No 4-sided border, no ring. */
.nav-item[aria-current="page"] {
  background: var(--cds-layer-02);
  border-left-color: var(--cds-border-interactive);
}
.nav-item[aria-current="page"] .nav-name { color: var(--cds-text-primary); font-weight: 600; }
.nav-item[aria-current="page"] .nav-chip {
  background: var(--cds-interactive);
  border-color: var(--cds-interactive);
}
.nav-item[aria-current="page"] .nav-chip svg { fill: var(--cds-text-on-color); }

/* metric tint: error only. Success and warning tokens fail 4.5:1 at 12px. */
.nav-metric[data-severity="error"] { color: var(--cds-text-error); }

/* footer */
.nav-footer { flex: 0 0 auto; background: var(--cds-layer-accent-01); border-top: 1px solid var(--cds-border-subtle-01); }
.nav-user { box-sizing: border-box; display: flex; align-items: center; gap: 12px; min-height: 56px; padding: 8px 20px; }
.avatar { flex: 0 0 auto; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
          background: var(--cds-background-inverse); color: var(--cds-text-inverse);
          font-size: 0.75rem; letter-spacing: 0.32px; }
.nav-footer-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; padding: 6px 12px 6px 20px; }
.nav-brand { flex: 1 1 auto; min-width: 0; display: flex; align-items: center; gap: 8px;
             font-size: 0.75rem; letter-spacing: 0.32px; color: var(--cds-text-helper);
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bb-mark { width: 24px; height: 24px; flex: 0 0 auto; fill: var(--cds-text-primary); }
.icon-btn { flex: 0 0 auto; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center;
            background: transparent; border: none; cursor: pointer; }
.icon-btn:hover { background: var(--cds-layer-hover-01); }

/* rail */
.nav[data-rail="true"] .nav-body,
.nav[data-rail="true"] .nav-section-label,
.nav[data-rail="true"] .nav-report-name,
.nav[data-rail="true"] .nav-user-text,
.nav[data-rail="true"] .nav-brand span { display: none; }
.nav[data-rail="true"] .nav-item { grid-template-columns: 36px; }
.nav[data-rail="true"] .nav-footer-row { justify-content: center; }
.nav[data-rail="true"] .nav-dot {
  display: block; position: absolute; top: 8px; right: 8px;
  width: 6px; height: 6px; background: var(--cds-support-error);
}
```

`grid-template-columns: 36px minmax(0, 1fr)` plus `min-width: 0` on `.nav-body` is the whole fix for the wrapping. A flex row with a fixed-basis chip and no `min-width: 0` on the text column is what produces the current three-line items.

---

## The 10 items

Ten items, five sections, in this order. No eleventh item without a design change.

| Section | Item | Icon | Metric | Severity | Description |
| --- | --- | --- | --- | --- | --- |
| Performance | Pulse | `dashboard` | conversion % | error | Conversion, volume, exceptions |
| | Rx engine | `pills` | total Rx | — | Prescriptions and rates |
| | Trends | `chart--line` | **period delta** (`+6.2%`) | — | Week-by-week movement |
| Field | Field activity | `events` | calls/rep/day + tag "Below 10" | — | Calls, day plans, visit records |
| | Doctors | `stethoscope` | **doctors met** (count) | — | Coverage and conversion by rep |
| Action | Needs action | `warning--alt--filled` | open count + red badge | error | Grouped by what to do |
| Team | Managers | `user--multiple` | manager count | — | Teams rolled up to their manager |
| | Org tree | `user` | rep count | — | Reporting lines and territories |
| Reference | Guide | `book` | — | — | How each figure is calculated |
| | Notes | `document` | new count | — | Data caveats and cut-offs |

Section label icons: Performance `analytics`, Field `events`, Action `warning--alt--filled`, Team `user--multiple`, Reference `book`.

**Every metric comes from the same query that feeds its screen.** If the nav badge says 437 open, the Pulse exceptions band and the Needs action screen say 437 too. One query, three renders.

---

## Acceptance checks

Run each in the browser console on the deployed page. All must pass on both a tall and a 540px-tall viewport, expanded and railed.

```js
// 1. width
getComputedStyle(document.querySelector('.nav')).width          // "320px"

// 2. no wrapping: every item is one 60px row, not two or three
[...document.querySelectorAll('.nav-item')].map(n => n.offsetHeight)
// every value 60..68 — a 90+ value means text wrapped

// 3. two rows per item, name and metric in different rows
[...document.querySelectorAll('.nav-item')].every(n =>
  n.querySelector('.nav-line1 .nav-name') && n.querySelector('.nav-line2 .nav-metric'))  // true

// 4. chip present and square
[...document.querySelectorAll('.nav-chip')].map(c => [c.offsetWidth, c.offsetHeight])
// every pair [36, 36]

// 5. exactly ten items, and the two removed ones are gone
document.querySelectorAll('.nav-item').length                    // 10
document.body.innerText.match(/Call detail|Doctors by rep/)      // null in the nav

// 6. section labels carry an icon
[...document.querySelectorAll('.nav-section-label')].every(l => l.querySelector('svg'))  // true

// 7. active item: left border only, no 4-sided box
(a => { const s = getComputedStyle(a); return [s.borderLeftWidth, s.borderTopWidth, s.borderRightWidth, s.outlineStyle]; })
(document.querySelector('.nav-item[aria-current="page"]'))
// ["4px", "0px", "0px", "none"]

// 8. footer controls are icon-only and labelled
[...document.querySelectorAll('.nav-footer .icon-btn')].map(b => [b.offsetWidth, b.innerText.trim(), b.getAttribute('aria-label')])
// [[32, "", "Dark theme"], [32, "", "Collapse navigation"]]

// 9. three hairlines, none between items
[...document.querySelectorAll('.nav *')].filter(el => {
  const s = getComputedStyle(el);
  return ['borderTopWidth','borderBottomWidth'].some(p => s[p] === '1px');
}).length                                                        // <= 3

// 10. rail
document.querySelector('.nav').dataset.rail = 'true';
getComputedStyle(document.querySelector('.nav')).width           // "72px"
document.querySelector('.nav-item .nav-body').offsetParent       // null (hidden)
```

Checks 2, 3 and 7 are the ones the current build fails hardest; check 2 is the fastest signal that the grid fix landed.

---

## Paste this into Claude Code

> Read `design_handoff_frontline_carbon/NAV_SPEC.md` in full before editing anything.
>
> Rebuild the side navigation to match it exactly. Use the `## Required DOM` nesting and the `## Required CSS` rules as given — in particular `grid-template-columns: 36px minmax(0, 1fr)` on the item with `min-width: 0` on the text column, which is what stops the current two- and three-line items, and the two-row split so the name sits on its own line above the metric and description.
>
> Then: set the nav to a fixed 320px (72px railed); add the 36px bordered icon chip; give section labels their 16px icons and 24px of space above each group; remove "Call detail" and "Doctors by rep" from the nav and make them tabs inside Field activity and Doctors; change the active state to a white plate with a 4px blue left border and a blue chip, with no 4-sided border and no inset ring; replace the "Dark theme" and "Collapse navigation" text rows with two 32px icon-only buttons carrying `title` and `aria-label`; and remove every hairline between items so the nav has three in total.
>
> Fix two wired metrics: Trends must show the period delta, not a call count; Doctors must show doctors met, not coverage percent. Each nav metric must come from the same query that feeds its screen — the exceptions count in the nav, on the Pulse band and on the Needs action screen must be one number from one query.
>
> Then run all ten checks in `## Acceptance checks` and paste the actual output of each. Do not report the nav done until every one matches, on a 540px-tall viewport as well as a tall one, expanded and railed.
