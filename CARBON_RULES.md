# Carbon rules — Frontline

Binding spec for every screen of this app. Values come from `carbon-tokens.css`; never write a literal.

## Absolute rules

1. **Radius 0** on everything except tags/pills (fully rounded) and the toggle knob.
2. **Blue 60 `--cds-interactive` is the only interactive colour.** Links, focus, selection, primary buttons, chart series 1. If something is blue, it is interactive or it is data.
3. **Colour carries meaning or it is absent.** A tile gets a coloured left border only when it is in error or warning. Neutral tiles get `--cds-border-subtle-00`. No decorative accent bars.
4. **Spacing on the 8px scale only**: 2 / 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48 / 64.
5. **No shadows except overlays.** Menus, modals and the drill panel get `0 2px 6px var(--cds-shadow)`. Tiles and cards are flat `--cds-layer-01` with no border and no shadow; separation comes from 1px grid gaps over `--cds-border-subtle-00`.
6. **No gradients, no background images, no textures, no emoji.**
7. **Motion 70–240ms**, `cubic-bezier(0.2,0,0.38,0.9)`. Fades and slides. Nothing scales, springs or bounces.

## Type

| Role | Size / line-height | Weight | Tracking |
| --- | --- | --- | --- |
| Headline metric | 3.375rem / 1.07 | 300 | 0 |
| Page title (h1) | 2rem / 1.25 | 400 | 0 |
| Section heading (h2) | 1.25rem / 1.4 | 400 | 0 |
| Card title | 1rem / 1.5 | 600 | 0 |
| Tile value | 2rem / 1.25 | 400 | 0 |
| Body | 0.875rem / 1.43 | 400 | 0.16px |
| Label, helper, eyebrow | 0.75rem / 1.33 | 400 | 0.32px |

IBM Plex Sans 300/400/600. Plex Mono only for fingerprints and code. Large sizes go *lighter*, never bolder.

## Controls

Heights: sm 32 · md 40 · lg 48 · xl 64. Inputs and selects sit on `--cds-field-01` with **only** `border-bottom: 1px solid var(--cds-border-strong-01)`. Buttons have square corners, left-aligned labels, `padding: 0 63px 0 15px` (15px right when they carry a trailing icon).

## Geometry to match exactly

- **Header** 48px, `--cds-gray-100`, inverse text, active nav `inset 0 -3px 0 var(--cds-blue-60)`.
- **Filter bar** sticky at `top: 48px`, `--cds-layer-01`, fields in 1px-gap cells, bottom border `--cds-border-subtle-01`.
- **Page content** `max-width: 1584px`, `padding: 0 16px 96px`, title block capped at 720px.
- **Tile grid** `repeat(auto-fit, minmax(200px, 1fr))`, `gap: 1px`, container background `--cds-border-subtle-00`.
- **Table** header row 48px on `--cds-layer-accent-01`, weight 600, left aligned; body rows 48px, `padding: 0 16px`, `border-top: 1px solid var(--cds-border-subtle-01)`; first column `--cds-text-primary`, the rest `--cds-text-secondary`; no zebra, no vertical rules.
- **Drill panel** `min(520px, 100vw)`, full height, right edge, `--cds-layer-01`, scrim `rgba(0,0,0,0.5)`, 240ms slide-in, 40px header row in the inner table.
- **Progress** 4px track `--cds-border-subtle-00`, 25%-wide fill `--cds-interactive`, 1.4s indeterminate loop.

## Charts

- Series 1 `--cds-interactive`. Series 2 `--cds-support-warning`. Threshold and target lines dashed `4 4` in `--cds-support-warning`. Gridlines 1px `--cds-border-subtle-00`. Axis `--cds-border-strong-01`.
- **Every chart card carries a question as its title and a bold one-line answer above the graphic.** A chart that does not answer a stated question does not ship.
- **Multi-series charts share one scale, anchored at zero.** Never normalise each series to its own min/max — it makes flat series look volatile and can invert the story.
- Bar charts: 16px bars for horizontal, 8px gaps for columns. Value labels sit outside the bar in `--cds-text-primary`.

## Copy

Sentence case everywhere — headings, buttons, labels, tabs. Plain, declarative, no superlatives, no exclamation marks. Buttons are verb or verb + noun in 1–3 words. Numerals for counts, Indian grouping for large figures (`2,49,720`). Dates as `1 Sep 2026`. Say "and", not "&". No emoji.

Answer lines state the finding, not the metric: "For 6 doctors in 7, it did not," not "Conversion rate: 15%."

## What not to change in the codebase

Jinja logic and macros' behaviour, route paths, sort and filter query parameters, column order, the `#i-*` icon sprite, and the confidentiality footer. The restyle is CSS, class names and macro substitution.

---

## Per-screen checklist

Run before considering a screen done.

- [ ] Zero hex, `rgb()`, or `rgba()` literals outside `carbon-tokens.css` (scrim excepted).
- [ ] Zero unresolved tokens. Probe: every `var(--cds-*)` used resolves to a non-empty computed value.
- [ ] Every border radius is 0, except tags.
- [ ] Exactly one headline metric on the screen.
- [ ] Every supporting metric tile is clickable and opens the drill panel.
- [ ] Every chart title is a question and has a bold answer line beneath it.
- [ ] Multi-series charts share one zero-anchored scale.
- [ ] Tables: 48px rows, accent-01 header, no zebra, no vertical rules.
- [ ] Every interactive element shows the 2px Blue 60 focus ring on keyboard focus.
- [ ] Screen renders correctly in both `:root` and `[data-carbon-theme="g100"]`.
- [ ] Filters are in the sticky bar, reflected in the URL, and the active scope is visible as tags.
- [ ] Loading does not block reading: the report stays usable while figures update.
- [ ] Copy is sentence case with no emoji and no ampersands.
