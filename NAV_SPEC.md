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

---

## Deviations (v36)

Logged rather than silently applied. Both were made because the rail did not fit on a
laptop screen: ten items at a 60px minimum plus five section labels carrying 24px of air
each came to roughly 1060px of nav in a 900px viewport, so it scrolled — and a rail that
scrolls always reads as crowded, because you can never see the whole thing at once.

| Spec says | Shipped | Why |
|---|---|---|
| 36px icon chip | **32px** | Four pixels per item, ten items. The 20px glyph steps to 18px so the chip does not look cramped. |
| 24px of air above each group | **16px** | Five groups, so 40px recovered. The label still reads as a separator; 24px read as a gap. |
| 52px logo | **180px wide, height auto** | Not a deviation so much as a correction. The real lockup is 480x58 — an 8.3:1 wordmark. Sized by height at 52px it demands 430px of width; `max-width:100%` then clamps the box while `preserveAspectRatio` letterboxes the art to fill it, so it rendered 288px wide inside a 320px rail. A wordmark this wide has to be sized by width. 180px is 56% of the rail and ~22px tall. |

Item minimum height also went 60px to 46px, which the spec does not fix. The two text
lines need 38px; the other 22 were air.

Nothing was removed. Both the live metric and the description stay on every item —
conformance item 18 requires them, and they are what earns the rail its 320px.

Estimated nav height after: ~820px, which fits without scrolling.

## Deviations (v37) — hierarchy

Feedback: *"everything in the nav looks the same and flat, the hierarchy is missing."*
That is a checkable claim, and it was correct. Three things sat at the same weight:
a 32px bordered chip on every item, a semibold text-primary metric beside a
text-primary name, and a full description on every row at all times.

| Spec says | Shipped | Why |
|---|---|---|
| 36px bordered icon chip on every item | **24px bare icon; the filled plate is active-only** | Ten identical outlined boxes distinguish nothing from nothing. The border only carries meaning on the active item, where it is a filled blue plate — so "where am I" is answered by fill rather than by hunting for the one box that is shaded differently. |
| Description always visible under the name | **On hover and on keyboard focus** | It answers a question nobody asks ten times at once. Still in the DOM, still wired to `SCREENS[].lead()`, and now bound with `aria-describedby` — so it is *more* available to a screen reader than it was as a loose line of text. |

Also, not spec deviations but part of the same fix:

- Name and metric moved onto **one row, two columns** — name left in `text-primary`,
  metric right-aligned in `text-secondary`. Two equally loud things on one row is a tie,
  not a hierarchy. Severity metrics keep red and semibold, because that is a signal.
- Section labels dropped to `text-helper` at 11px. They are signposts, and they were
  competing with the items they label.
- Item minimum 46px → 40px. Nav is now ~750px.
- `title="<the item's own name>"` removed. It produced a slow native tooltip repeating
  the label already on screen, and would have fought the real one.

Three levels of text now exist by construction, and `_navcalm_test.js` asserts it:
name, metric and section label must resolve to three different sizes AND three
different colours. A future change that flattens them again fails the suite.

## Spacing (v38)

Two ragged left edges, and the air in the wrong place.

**One left edge.** Section labels and items were indented differently — icons 4px apart,
text 18px apart:

| | icon starts | text starts |
|---|---|---|
| section label (before) | 16px | 38px |
| nav item | 20px | 56px |

The item reserves a 4px transparent left border, so the row does not shift sideways when
it becomes current and the blue edge appears. The label reserved nothing. Two near-misses
read worse than an honest outdent, because the eye keeps trying to resolve them into one
column. The label now takes the same 4px border, the same left-padding token, the same
gap token, and a 24px icon box matching the item's chip — so icons share one edge at 20px
and text shares one at 56px.

Section icons stay: spec item 6 added them on purpose, and `_drill_test.js` asserts every
label has one. Aligning them was the fix, not deleting them because alignment was awkward.

**Air redistributed.** v36 squeezed the rail to fit a laptop; v37's single-line rows then
handed back 200px that went straight into dead space at the bottom, leaving it cramped at
the top of a mostly empty column.

| | v37 | v38 |
|---|---|---|
| item minimum | 40px | **44px** |
| air above a group | 16px | **24px** — back to what item 6 asked for |
| masthead padding | 12px | **16px** |
| "Below 10" tag | 12px on solid grey | **11px on layer-02** |

~870px against a 900px viewport. The space below the last item is now a margin rather
than a void.

`_navtidy_test.js` asserts the alignment as an invariant — same border width, same
padding token, same gap token, same icon-box width — so it survives a change to the
token values themselves.

## Deviations (v39) — icons, the collapse control, motion

**Section icons removed**, at Arshad's explicit request: *"don't need icons for the
section headers."* This reverses spec item 6, which added them — so it is a signed-off
decision being un-signed, not a tidy-up. `_drill_test.js` now asserts their **absence**,
so they cannot drift back in unnoticed. With no icon to align, the label indents its
text to where the item names start (reserved border + left padding + chip width + gap),
built from the same tokens the item row uses rather than a hard-coded 56px.

**Where the icons come from.** IBM Carbon v11 — 37 glyphs inlined into
`_carbon_icons.json` at build time. No CDN, no runtime dependency. They are already
geometric: a 32×32 grid with 2px strokes drawn as filled paths. Three CHOICES were
wrong, and those are what changed:

| Item | Was | Now | Why |
|---|---|---|---|
| Org tree | `user` — one person | `hierarchy` | An org tree is not a person. Parent box, bus, two children, drawn as filled bars the way `enterprise` is. |
| Field activity | `events` — three people | `calendar--task` | The screen is day plans, calls and visit records. The people language belonged to Managers. |
| Needs action | `warning--alt--filled` | `warning--alt` | Everything else in the rail is an outline; a solid triangle read as an alert rather than a nav item. Composed from the filled icon's own outline triangle, bar and dot — Carbon's geometry, not a redrawing. |

`_navicons_test.js` checks the hand-drawn paths sit inside the 32-unit grid, and checks
the borrowed ones appear verbatim in the bundle. Provenance where it can be proved,
measurement where it cannot.

**Collapse control moved to the masthead.** It was in the footer, ~400px below the thing
it collapses. Same button, same id, same handler — moved, not rebuilt. The masthead now
survives the collapsed state, because it holds the only way back out. The theme toggle
stays in the footer: it is a preference and belongs with the user.

This also surfaced a real bug: `railSet()` updated the labels on `railtoggle` and
`rail2` but never on `rail3`. In the footer that was cosmetic. As the primary control, a
button whose label never changes is a button that lies about what it does.

**Motion.** The rail transitions its width and the main column its margin, both on
`--cds-duration-moderate-02` with `--cds-easing-standard-productive`. Reduced motion
cancels it via the existing global rule.

**It opens on every load**, as asked — including over a stored collapsed preference. The
shell starts collapsed with a `.boot` class suppressing transitions, then releases both
on the second animation frame. Two frames, not one: the first is when the browser applies
the collapsed state, and removing `.boot` in that same frame would cancel the transition
before it had anything to animate from. The preference is still written, so the toggle
behaves normally within a session.

## Correction (v40) — the label goes back to the outer edge

v39 was wrong and this reverses it.

When the section icons came out, I indented the label to line its text up with the item
**names**. That inverts the hierarchy: the label is what marks where a group *begins*, so
putting it at 112px while its own items' icons sit at 48px places the parent sixty pixels
inside its children, and the icons hang outside the group entirely. Arshad's phrasing was
exact — *"the icons are out of the nesting"*.

```
PERFORMANCE            <- label text at 20px, flush with the icon column
[icon] Pulse    91.4%  <- icon box at 20px, name at 56px
```

The label opens the group; everything under it is contained by it. `_navtidy_test.js`
now asserts label text and item icons share one left edge, and that the label carries far
more air above (24px) than below (4px) — a six-to-one ratio, so it binds downward to the
group it opens instead of floating between two.

**The tooltip moved out of the rail.** Hovering Field activity put its description
straight over Doctors. That was a constraint I accepted in v37 rather than a decision:
`.sidescroll` clips `overflow-x`, so a tooltip anchored inside it cannot escape right and
has to open downward over the list. It is now one shared `position:fixed` element outside
the scroll container, placed from the hovered item's bounding rect, sitting beside the
rail where it covers nothing. It works collapsed too, where a tooltip is worth more than
it is expanded.

The per-item `.nav-desc` stays in the DOM as the `aria-describedby` target, visually
hidden — the spoken description and the drawn one read the same string and cannot drift.
Handlers are delegated from `#tabs` and wired once, because `navRender()` re-runs on every
filter change and per-item binding would stack a listener each time.

## Brand and the collapsed rail (v41)

**Two assets now, not one.** The wordmark (`brand/frontline-intelligence.svg`) for the
expanded rail; the mark alone (`brand/frontline-mark.svg`) for the collapsed one, which
is all 72px can hold — the previous build clipped the wordmark mid-letter. Both are in
the DOM and CSS chooses between them, so the logo cannot desynchronise from the rail
state the way a JS swap could.

Three things were stripped before inlining, by `_brand.py`'s builder rather than by hand:

| | why |
|---|---|
| the white plate | The lockup ships with `<rect width="563" height="119" fill="white"/>` behind the art. Invisible on the light theme, a white slab around the logo on Gray 100. |
| the filters | Both files carry drop and inner shadows. At 38px and 28px those render as mud, and they cost a filter pass on every repaint of a rail that now animates. |
| colliding ids | Both files number their gradients `paint0..paintN`. Two assets on one page means two `#paint0_linear` and the second silently wins for both. Namespaced `fi_` and `fm_`; the builder asserts every `url(#…)` still resolves afterwards. |

The lockup carries "Intelligence" in its own gradient pill, so the separate
"Rx intelligence" line under it is gone — the masthead was about to say intelligence
twice, in two type treatments, using two different words.

`_audit.py` and `_carbon_test.js` now exempt **both** assets from the no-colour-literals
rule and pin the count at two. A third would mean a copy had crept in, which is what
that check was really guarding.

### The collapsed rail showed nine alerts that did not exist

```css
.app.railed .nav-dot{display:block; ...}
```

`navRender()` sets `dot.hidden` on every item that is not alerting, but `hidden` is only
a UA-stylesheet `display:none` and an author rule with `display:block` beats it. So the
collapsed rail lit a red dot on all ten items — the single signal that state has, firing
on everything. Scoped to `:not([hidden])`.

Also: the icon column still reserved 36px for a chip that has been 24px since v37; groups
lost all separation once their labels were hidden (air only — NAV_SPEC allows three
hairlines in the whole rail and they are spent); and the footer brand icon is decoration
that 72px cannot afford.

**Open question, not changed here.** `NAVMETA.ov` carries `sev:'error'`, so Pulse's
metric is red unconditionally — it was red at 35.7% and it is red at 91.4%. A signal that
is always on carries no information, and collapsed it means Pulse always shows an alert
dot. Worth a threshold or removing the severity, but that is a product decision.

## The one-axis rule (v42)

**Collapsing the rail changes its width. Nothing else may move.**

Every element that swaps between the expanded and collapsed states keeps the same
vertical box. Text may go, a wordmark may become a mark, but no row may change height —
the width transition takes 240ms and a height change happens in a single frame, which is
the jump.

What was moving:

| | expanded | collapsed | fix |
|---|---|---|---|
| brand | 180 × **38** | 28 × **23** | both sized by height from `--brand-h: 32px` → 151×32 and 39×32 |
| masthead | padding `spacing-05` | padding `spacing-04` | same vertical padding in both |
| items | min-height 44px | 40px | 44px in both |
| section labels | visible | `display:none` | `visibility:hidden` — the box stays |
| footer rows | text | no text | `min-height: 44px` in both |

**Sizing brand assets by height is the whole trick.** A 4.73:1 wordmark and a 1.22:1 mark
sized by *width* cannot land on the same height — the arithmetic forbids it. By height
they agree by construction and the widths differ, which is fine, because width is the
axis the rail is already animating.

The section-label change is the one you feel: the label keeps its box and loses only its
text, so every icon holds its exact y-position and collapsing becomes a pure horizontal
move. It also makes the group separation automatic, which is why the railed section
margin v41 added could be removed.

A dead rule went too — `.app.railed .masthead .fl-lockup{height:24px}` survived from v36,
when the lockup was the only asset. It sized nothing (the lockup is `display:none` when
collapsed) but it still stated a number.

### Enforced, not remembered

`_navstable_test.js` diffs every `.app.railed X` rule against the base rule for `X` and
fails on any difference in a vertical-size property. Adding one later is a test failure
rather than something spotted in a screenshot three weeks on.

The lint runs **against the DOM**, not just the stylesheet. The sheet still carries rules
from three superseded nav layers — `.nav button` matches nothing, `.userchip` is present
but never rendered — and a lint that flags those teaches people to ignore it. A rule is
only checked if its selector matches something that actually renders, and skipped if the
element is `display:none` in either state, because an element with no box cannot shift
anything. Current run: 8 live rules checked, 21 skipped, 0 offenders.
