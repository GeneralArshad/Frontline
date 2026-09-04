# Hive Frontline — project rules

Read this before any task in this repo. `CARBON_RULES.md` beside it is the binding
design spec; this file records how that spec maps onto an architecture it was not
written for.

## What this codebase actually is

One self-contained HTML file. `template.html` (250 KB) holds every CSS rule and every
line of JavaScript inline; `etl.py` renders it once into `report.html`; `app.py` serves
that with a toolbar merged in. There is no `templates/` directory, no Jinja, no
`static/`, and no build step beyond the patch chain below.

The Carbon handoff assumes Flask with `templates/base.html`, `templates/_carbon.html`
macros and `static/css/`. Its four consistency mechanisms translate as follows.

| Handoff says | Here it is |
| --- | --- |
| One token file, no local literals | `carbon-tokens.css` is in this repo for provenance and inlined verbatim at the top of `template.html`. Below the `END OF TOKENS` marker there is not one colour literal, in CSS or JS. `_carbon_test.js` fails the build if that stops being true. The one exemption is the Frontline wordmark SVG — a brand asset, not UI chrome. |
| One Jinja macro per pattern | Already true, in JS. `kpi()`, `th()`, `chart()`, `empTable()`, `pl()`, `dcrDay()`, `teamRow()` are the macro layer, and screens compose them rather than hand-rolling markup. Add a pattern as a function here, never as inline markup in a view. |
| Rules file at the repo root | This file plus `CARBON_RULES.md`. |
| Screen by screen with a review gate | The patch chain below is that gate: each step is one reviewable script with its own tests. |

## The alias layer

`template.html` refers to `--bg`, `--surface`, `--ink`, `--line`, `--accent` and so on
in hundreds of rules. Rather than rewrite them, `_carbon.py` redefines those names in
terms of `var(--cds-*)`. **Change colour by editing the alias block, never by editing a
rule.** A value written into a rule is a bug the test will catch.

The dark theme carries no palette of its own: every alias points at a Carbon token, and
Carbon's g100 block answers to both `[data-carbon-theme="g100"]` and the app's existing
`[data-theme=dark]`, so the toggle and its localStorage key are untouched.

## Never edit template.html by hand

It is generated. `./_build.sh` in the outputs folder rebuilds it from
`_std_template_v12.html` through the chain:

```
_period.py:v13  _orgtree.py:v14  _org_v15.py:v15  _org_v16.py:v16
_restore_state.py:v17  _export.py:v18  _dcr.py:v19  _filters.py:v20  _carbon.py:v21
_drill.py:v22
```

## The drill panel hosts sections, it does not copy them

`drillOpen(key)` **moves** `#sec_<key>` into the panel and moves it back on close. Never
clone a section: this document looks elements up by id constantly, so a copy would give
you two `#pb` tables and handlers wired to whichever one lost. One node, one set of ids,
and the panel can never disagree with the page about what it shows.

The three screens that left the sidebar — Productivity, Call detail, Doctors by rep —
keep their nav buttons under `.navhidden`. That is what makes `go('prod')`, an old
bookmark, a share link and `restoreState()` all still work, and what keeps predeploy's
tab-equals-section check honest. Do not delete them.

Each script asserts its anchor exists, so a silent no-op is impossible. A hand edit is
lost on the next rebuild. `app.py` and `etl.py` patches (`_minimize.py`, `_roster.py`)
are applied in place and are not re-run by `_build.sh`.

## Tests

Run all of them before pushing. They need a fixture first:

```
FX_TPL=_std_template_v21.html FX_REPS=400 python3 _period_fixture.py
node _period_test.js _orgtree_test.js _export_test.js _dcr_test.js \
     _filters_test.js _carbon_test.js
python3 _attendance_test.py _progress_test.py _status_test.py _roster_test.py
```

## What not to change

Per `CARBON_RULES.md`: no route paths, no query parameters, no column order, no Jinja
(there is none) — and here additionally: never mutate `BASE`, never widen `/status` to
carry employee codes, and never let an export read the data model instead of the
rendered DOM.

## Carbon work still outstanding

The v21 pass is foundation only — tokens, type, geometry, charts. Still to do, in order:

1. One headline metric per screen, with a plain-language answer line.
2. Every chart title a question, with a bold one-line answer above the graphic.
3. The right-side drill panel; every tile and row a button into it.
4. The 13 → 7 information architecture. Rep Productivity Index folds into Pulse.
5. Sentence case sweep across headings, buttons and tabs.
