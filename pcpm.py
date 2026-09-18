#!/usr/bin/env python3
"""
The productivity matrix: what each headquarters billed, per person, per month.

    python3 pcpm.py --fy 2026-27 --hq geo.csv         # live, needs CHR_API_TOKEN
    python3 pcpm.py --payload sales.json --hq geo.csv # offline, from a saved response

PCPM is sales divided by people divided by months. It is worth writing that out because
the specification this was built from said

    PCPM = [HQ sales / number of employees] x number of months

and the multiplication is a typo that does not look like one. A "per month" figure that
multiplies by months is off by the square of the period: five months into the financial
year it reports twenty-five times the true number, every headquarters clears the �2.5
Lakh baseline, and the grid shows green everywhere. Nothing downstream would flag it,
because the arithmetic is internally consistent — it is just answering a different
question. So: divided, twice, and the test at the bottom of this file asserts it.

**What a month is.** Complete months only, matching Channel Health's own rule: a month
counts once its data reaches the 26th. Seventeen days of September set beside thirty of
August is not a productivity comparison, it is a fabricated decline, and dividing by a
fraction of a month to "annualise" it makes the noise louder rather than smaller. The
running month is excluded and `months` says how many were used.

**Two denominators, because there are two honest answers.** Sanctioned posts measure the
headquarters against what it was resourced to deliver. Filled posts measure the people
who were actually there. They differ by the vacancies — Bangalore is 38 and 33 — and the
gap is a staffing problem, not a productivity one, so the zone follows filled posts and
the sanctioned figure sits beside it for anyone who wants to argue the other way.

**The town is the stockist's address, not the demand.** This is the metric's real
weakness and it is not small. Srinivasa Drugs bills 85% of its value into Hyderabad;
Marudhar bills 70% into Chennai. Hyderabad is not 85% of Telangana's demand — it is where
the stockists are, and a metro stockist supplies chemists across the state. So a metro HQ
reads extraordinary and the district HQs around it read dead, for a reason that is about
distribution logistics rather than anybody's selling. The decision was to keep HQ-level
rows and label them honestly rather than model a split nobody could audit, so every row
carries `town_concentration`: the share of its super stockist's billing that lands in that
one town. A PERFORM verdict sitting next to 85% concentration is a fact about
warehousing, and the row says so rather than a footnote saying so.

**Money that belongs to nobody.** Some towns have stockists and no headquarters: nine
rupees in every hundred, in the sample this was built against. That billing is real and
it is not any HQ's to claim, so it is reported as its own row and excluded from every
PCPM. Spreading it over nearby headquarters would improve exactly one thing, which is
how the grid looks.
"""
from __future__ import annotations
import os
import csv
import json
import datetime
from collections import defaultdict

import re

import towns as T                      # shared with Channel Health — see SHARED_WITH

# The division prefix Frontline's geo tree puts in front of an HQ name. Stripped before
# looking for the city, so `BBS SOUTH MUMBAI` is read as `SOUTH MUMBAI`.
_HQ_PLACE = re.compile(r'^(BBS|BBN|BB|AN|ADN|SPL)\s+', re.I)

SHARED_WITH = ('channel-health-portal/pipeline/scripts/towns.py',
               'Keep byte-identical. test_shared() below fails the build if it drifts.')

# ------------------------------------------------------------------ the grid
# Rupees per person per month. From the Productivity Grid; the only place they are
# written down in code, so changing a band is one edit and shows up in one diff.
ZONES = [
    (0,        100_000, 'RED ZONE',     'Recovery required',
     'productivity is significantly below the expected level and needs immediate '
     'focused intervention'),
    (100_000,  200_000, 'BUILD ZONE',   'Acceleration required',
     'there is an existing productivity base, but stronger execution is needed to move '
     'toward the company benchmark'),
    (200_000,  250_000, 'STRETCH ZONE', 'Final push required',
     'the group is close to the baseline and needs a focused stretch to cross the '
     'minimum expectation'),
    (250_000, float('inf'), 'PERFORM ZONE', 'Expectation met',
     "the group has achieved the company's baseline productivity and is operating at "
     'the expected level or above'),
]
BASELINE = 250_000

# WHICH RUPEE. Channel Health returns two: `sales` is the invoice value including GST,
# `goods` is the pre-tax goods value. At 12-18% the difference is most of the distance
# between one zone and the next, so it cannot be left to whichever key was typed first.
# The Rs 2.5 L baseline is a productivity target, and GST is collected on the government's
# behalf rather than earned by anybody, so the matrix measures goods. The header says so
# on every output, because a PCPM with no stated basis is a number two people will read
# two ways.
MEASURE = 'goods'
MEASURE_NOTE = 'pre-tax goods value, GST excluded'


def amount(row):
    """The measured rupee for one row, falling back only if the API stops sending it."""
    v = row.get(MEASURE)
    if v is None:
        v = row.get('sales')
    return float(v or 0)


def zone_of(pcpm):
    """The band a PCPM falls in. None in, None out — an HQ with no people has no zone,
    and calling that RED would blame a headquarters for being empty."""
    if pcpm is None:
        return None
    for lo, hi, code, verdict, meaning in ZONES:
        if lo <= pcpm < hi:
            return {'code': code, 'verdict': verdict, 'meaning': meaning,
                    'floor': lo, 'ceiling': None if hi == float('inf') else hi}
    return None


# ------------------------------------------------------------------ months
def complete_months(fy, as_of=None, day_complete=26):
    """The complete months of `fy` up to `as_of`, as 'YYYY-MM' strings.

    A month is complete when `as_of` has reached its 26th. The rule is Channel Health's
    and is repeated here rather than imported so that the two systems can be shown to
    agree — if it ever changes, this divides by a different number and the test says so.
    """
    start = int(str(fy).split('-')[0])
    as_of = as_of or datetime.date.today()
    out = []
    y, m = start, 4
    while True:
        if (y, m) > (as_of.year, as_of.month):
            break
        if (y, m) == (as_of.year, as_of.month) and as_of.day < day_complete:
            break
        out.append('%04d-%02d' % (y, m))
        if len(out) >= 12:
            break
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# ------------------------------------------------------------------ inputs
def _get(base_url, token, path, timeout=90):
    import urllib.request
    req = urllib.request.Request(base_url.rstrip('/') + path,
                                 headers={'X-API-Token': token,
                                          'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


# The division slugs Channel Health accepts. Fetched one at a time rather than in one
# call, because /sales?by=town collapses months and drops the division column — asking
# per division is the only way to get both the town and which force sold there.
DIV_SLUGS = {'main': T.MAIN, 'speciality': T.SPECIALITY, 'nutrition': T.NUTRITION}


def fetch(base_url, token, fy, as_of=None, timeout=90):
    """Pull the sales side, one request per division, and tag each row with it.

    Returns a payload shaped like the old single endpoint so `matrix()` does not have to
    know which API it came from.
    """
    months = complete_months(fy, as_of)
    if not months:
        raise SystemExit('no complete months in %s yet' % fy)
    q = '?from=%s&to=%s&by=town' % (months[0], months[-1])
    rows, seen = [], False
    for slug, name in DIV_SLUGS.items():
        try:
            d = _get(base_url, token, '/api/v1/sales' + q + '&division=' + slug, timeout)
        except Exception as e:                                        # noqa: BLE001
            print('  ! division %s unavailable (%s)' % (slug, e))
            continue
        seen = True
        for r in d.get('rows', ()):
            r['division'] = name
            rows.append(r)
    if not seen:
        # Every per-division call failed. Fall back to the undivided figures rather than
        # returning nothing — a matrix that cannot tell main from specialty is still a
        # matrix, and resolve() says which rows were matched without a division.
        d = _get(base_url, token, '/api/v1/sales' + q, timeout)
        rows = [dict(r, division=None) for r in d.get('rows', ())]
    return {'fy': fy, 'rows': rows, 'months': months,
            'total_sales': sum(amount(r) for r in rows),
            'layer': 'field primary — super stockist billed to stockist'}


def load_hq_csv(path):
    """The geography export. Its first line is a long provenance sentence, not a header."""
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    hdr_i = 0
    for i, r in enumerate(rows[:3]):
        if 'HQ' in r and 'Posts' in r:
            hdr_i = i
            break
    hdr = rows[hdr_i]
    return [dict(zip(hdr, r)) for r in rows[hdr_i + 1:] if len(r) == len(hdr)]


# ------------------------------------------------------------------ the matrix
def sibling_cities(ix):
    """Which HQs share a city with other HQs, so their denominator is incomplete.

    An invoice says `MUMBAI`. It cannot say South or Western, so all of Mumbai's billing
    lands on whichever HQ is named exactly `Mumbai` — three posts carrying the business of
    the forty-three people Frontline posts across eight Mumbai headquarters. The figure
    that comes out is Rs 21.54 L per person per month, eight times the baseline, and it is
    an artefact of the join rather than anything anyone sold.

    Pooling them would fix the arithmetic and destroy the distinction between South and
    Western Mumbai. The decision was to keep the rows and refuse to score them, so this
    finds the groups and the caller withholds the zone: a blank verdict a reader asks
    about is better than a green one they believe.

    **Whole-word containment, not substring.** `SOUTHMUMBAI` contains `MUMBAI` and so
    does `WESTRENMUMBAI` (a typo in the HR data, caught for free). But squashed substrings
    would also match `INDI` inside something longer, and two towns 800km apart would be
    called siblings. So the test is: does another HQ's name appear as a complete word in
    this one.

    **Siblings only count inside one division.** Bangalore has two HQ rows, `Bangalore`
    and `BBS BANGALORE`, and at first glance that looks like the same problem. It is not:
    the product carries the division, so `resolve()` already sends Bangalore's specialty
    billing to the specialty HQ and its main billing to the main one. Those two are
    separable and both are scoreable. Treating them as siblings withheld a verdict from
    137 headquarters and 70% of the billing — a matrix so cautious it said nothing.

    What is genuinely unsplittable is several HQs of the SAME division in one city:
    South, Central and Western Mumbai are all main division, and no field in the sales
    data distinguishes them. Those are the rows that cannot be scored.
    """
    groups = defaultdict(set)
    for div, members in ix['by'].items():
        # Candidate cities: single-word HQ names within this division.
        cities = {}
        for key, name in members.items():
            words = T.norm(_HQ_PLACE.sub('', str(name)).strip()).split()
            if len(words) == 1 and len(words[0]) >= 4:
                cities[words[0]] = name
        for key, name in members.items():
            for w in T.norm(_HQ_PLACE.sub('', str(name)).strip()).split():
                if w in cities:
                    groups[(div, w)].add(name)
    return {'%s / %s' % (c, d): sorted(v)
            for (d, c), v in groups.items() if len(v) > 1}


def concentration(rows):
    """For each (branch, town): that town's share of its super stockist's billing.

    A stockist's town is its billing address. Where one town holds most of a super
    stockist's value, the HQ there is being credited with business that is physically
    warehoused in its town and sold across the state. This does not correct for that —
    correcting would mean inventing a split — it measures it, so the row can say so.
    """
    per_branch, per_town = defaultdict(float), defaultdict(float)
    for r in rows:
        b = r.get('branch_code') or ''
        per_branch[b] += amount(r)
        per_town[(b, T.key_of(r.get('town')))] += amount(r)
    out = defaultdict(float)
    for (b, town), v in per_town.items():
        tot = per_branch[b]
        if tot:
            out[town] = max(out[town], v / tot)       # worst case across super stockists
    return dict(out)


def matrix(payload, hq_rows, fy=None, as_of=None, include_unlabelled=False):
    """Join sales to headcount and compute the grid.

    Returns a dict with `rows` (one per HQ), `unattributed`, `months`, and the totals
    needed to prove nothing was lost between the two.
    """
    fy = fy or payload.get('fy') or '2026-27'
    months = payload.get('months') or complete_months(fy, as_of)
    mset = set(months)
    ix = T.hq_index(hq_rows)
    src = list(payload.get('rows', ()))

    # A batch that arrived with no branch_code is not a super stockist. In the live store
    # one such batch — named `Sale Report : Format` after a header row in the export —
    # carries Rs 8.51 Cr across 40 towns, every one of them a Kandala town, and looks like
    # an earlier Kandala upload that lost its label. Counting it would credit Karnataka
    # twice. Excluded by default, counted separately, and never silently dropped.
    unlabelled = [r for r in src if not (r.get('branch_code') or '').strip()]
    if not include_unlabelled:
        src = [r for r in src if (r.get('branch_code') or '').strip()]

    conc = concentration(src)
    # Which towns the channel reaches at all. An HQ that billed nothing is two very
    # different stories depending on this: if a super stockist bills into its town and
    # the HQ still shows zero, that is a real zero and belongs in the matrix. If no
    # super stockist has ever billed that town, the HQ cannot be measured on channel
    # sales and calling it RED would blame a headquarters for the network's shape.
    covered = {T.key_of(r.get('town')) for r in src if amount(r) > 0}
    sibs = sibling_cities(ix)
    of_city = {}
    for city, members in sibs.items():
        for n in members:
            of_city[n] = city

    by_hq = defaultdict(lambda: {'sales': 0.0, 'towns': set(), 'ss': set(),
                                 'invoices': 0, 'reasons': set()})
    orphan = {'sales': 0.0, 'towns': defaultdict(float), 'reasons': set()}
    dropped_months = 0.0

    for r in src:
        v = amount(r)
        # by=town rows are already collapsed over the requested window, so they carry no
        # month. Only a row that names a month can be outside the window.
        if r.get('month') and r['month'] not in mset:
            dropped_months += v
            continue
        hq, why = T.resolve(r.get('town'), r.get('division'), ix)
        if not hq:
            orphan['sales'] += v
            orphan['towns'][r.get('town')] += v
            orphan['reasons'].add(why)
            continue
        b = by_hq[hq]
        b['sales'] += v
        b['towns'].add(r.get('town'))
        b['ss'].update(r.get('super_stockists')
                       or ([r['ss_name']] if r.get('ss_name') else ()))
        b['invoices'] += int(r.get('invoices') or 0)
        b['reasons'].add(why)

    n = len(months) or 1
    out = []
    for name, row in sorted(ix['rows'].items()):
        s = by_hq.get(name)
        posts = T._num(row.get('Posts'))
        vacant = T._num(row.get('Vacant'))
        filled = max(posts - vacant, 0)
        sales = s['sales'] if s else 0.0
        # An HQ with no people gets no PCPM at all rather than a zero. Zero is a claim
        # about performance; "nobody works here" is a claim about staffing.
        pcpm_filled = (sales / filled / n) if filled else None
        pcpm_posts = (sales / posts / n) if posts else None
        out.append({
            'hq': name,
            'zone_geo': row.get('Zone', ''), 'state': row.get('State', ''),
            'sales': round(sales, 2),
            'posts': posts, 'vacant': vacant, 'filled': filled,
            'pcpm_filled': None if pcpm_filled is None else round(pcpm_filled, 2),
            'pcpm_posts': None if pcpm_posts is None else round(pcpm_posts, 2),
            # No zone where the denominator is incomplete. An HQ sharing a city with
            # other HQs gets the whole city's billing against only its own headcount, so
            # the number is not comparable with anything and must not be coloured.
            'zone': None if name in of_city else zone_of(pcpm_filled),
            'denominator_safe': name not in of_city,
            'shares_city_with': [x for x in sibs.get(of_city.get(name), [])
                                 if x != name],
            'towns': sorted(s['towns']) if s else [],
            'super_stockists': sorted(s['ss']) if s else [],
            'invoices': s['invoices'] if s else 0,
            'merged_from': ix['merged'].get(name, []),
            'town_covered': T.key_of(_HQ_PLACE.sub('', str(name))) in covered,
            # Printed on the row, not in a footnote. 0.85 means one town holds 85% of a
            # super stockist's billing, so this HQ's figure is a warehousing fact as much
            # as a selling one.
            'town_concentration': round(max((conc.get(T.key_of(t), 0)
                                             for t in (s['towns'] if s else ())),
                                            default=0), 3),
            'notes': sorted(s['reasons']) if s else ['no billing reached this HQ'],
        })

    attributed = sum(r['sales'] for r in out)
    return {
        'fy': fy, 'months': months, 'month_count': len(months),
        'as_of': (as_of or datetime.date.today()).isoformat(),
        'baseline': BASELINE, 'measure': MEASURE, 'measure_note': MEASURE_NOTE, 'zones': [dict(code=c, verdict=v, meaning=m,
                                             floor=lo, ceiling=None if hi == float('inf') else hi)
                                        for lo, hi, c, v, m in ZONES],
        'rows': out,
        'unattributed': {
            'sales': round(orphan['sales'], 2),
            'towns': [{'town': t, 'sales': round(v, 2)}
                      for t, v in sorted(orphan['towns'].items(), key=lambda x: -x[1])],
            'why': sorted(orphan['reasons']),
        },
        'excluded_part_months': round(dropped_months, 2),
        'unlabelled_batch': {
            'sales': round(sum(amount(r) for r in unlabelled), 2),
            'towns': sorted({r.get('town') for r in unlabelled}),
            'names': sorted({r.get('ss_name') for r in unlabelled if r.get('ss_name')}),
            'included': bool(include_unlabelled),
        },
        'totals': {
            'attributed': round(attributed, 2),
            'unattributed': round(orphan['sales'], 2),
            'in_scope': round(attributed + orphan['sales'], 2),
            'payload_total': round(float(payload.get('total_sales') or 0), 2),
            # Two headcounts, because mixing them is how a total lies. `posts` is the
            # whole network; `posts_billing` counts only the HQs that billing actually
            # reached. Dividing network-wide sales by network-wide heads is right; setting
            # four super stockists' sales beside all 447 HQs' heads is not.
            'posts': sum(r['posts'] for r in out),
            'filled': sum(r['filled'] for r in out),
            'posts_billing': sum(r['posts'] for r in out if r['sales'] > 0),
            'filled_billing': sum(r['filled'] for r in out if r['sales'] > 0),
            'hqs': len(out),
            'hqs_billing': sum(1 for r in out if r['sales'] > 0),
        },
        'shared_cities': {c: {'hqs': v,
                              'posts': sum(T._num(ix['rows'][h].get('Posts')) for h in v)}
                          for c, v in sorted(sibs.items())},
        'source': {'layer': payload.get('layer'), 'built_with': payload.get('built_with'),
                   'aliases': payload.get('aliases', {})},
    }


# ------------------------------------------------------------------ checks
def check(m):
    """Everything that must hold for the matrix to be worth printing."""
    p = []
    t = m['totals']
    if abs(t['attributed'] + t['unattributed'] + m['excluded_part_months']
           + (0 if m['unlabelled_batch']['included'] else m['unlabelled_batch']['sales'])
           - t['payload_total']) > 1:
        p.append('billing does not reconcile: %.2f attributed + %.2f unattributed + '
                 '%.2f part-months != %.2f from Channel Health'
                 % (t['attributed'], t['unattributed'], m['excluded_part_months'],
                    t['payload_total']))
    if not m['months']:
        p.append('no complete months in this financial year yet — every PCPM would be '
                 'a division by zero')
    # A row that reaches the screen with no name is unreadable and unactionable, and
    # nothing downstream would notice: the table would draw a blank cell and the reader
    # would have no idea which headquarters they were being asked to fix. Caught here,
    # at build time, where it fails a deploy rather than a decision.
    for r in m['rows']:
        if not str(r.get('hq') or '').strip():
            p.append('a headquarters row has no name: %r' % (r,))
    for r in m['rows']:
        if r['filled'] > r['posts']:
            p.append('%s: %g filled of %g sanctioned' % (r['hq'], r['filled'], r['posts']))
        if r['pcpm_filled'] is not None and r['sales'] and r['filled']:
            want = r['sales'] / r['filled'] / m['month_count']
            if abs(want - r['pcpm_filled']) > 0.01:
                p.append('%s: PCPM does not equal sales/filled/months' % r['hq'])
    return p


def test_shared(chr_repo):
    """The shared module must not drift between the two apps."""
    a = os.path.join(chr_repo, 'pipeline', 'scripts', 'towns.py')
    b = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'towns.py')
    if not (os.path.exists(a) and os.path.exists(b)):
        return ['towns.py missing from one side: %s / %s' % (a, b)]
    if open(a, 'rb').read() != open(b, 'rb').read():
        return ['towns.py differs between Frontline and Channel Health — one of them is '
                'canonicalising towns differently, so the join is silently wrong']
    return []


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Productivity matrix by headquarters')
    ap.add_argument('--fy', default='2026-27')
    ap.add_argument('--payload', help='saved /api/v1/hq-sales JSON, instead of fetching')
    ap.add_argument('--hq', required=True, help='Frontline geography CSV')
    ap.add_argument('--url', default=os.environ.get('CHR_URL',
                                                    'https://channel-health.onrender.com'))
    ap.add_argument('--as-of', help='YYYY-MM-DD, for testing the month rule')
    ap.add_argument('--include-unlabelled', action='store_true',
                    help='count batches that arrived with no branch_code (see the note '
                         'in matrix(); off by default because the live one duplicates '
                         'Kandala)')
    ap.add_argument('--json', help='write the matrix here')
    a = ap.parse_args()

    as_of = datetime.date.fromisoformat(a.as_of) if a.as_of else None
    if a.payload:
        payload = json.load(open(a.payload, encoding='utf-8'))
        payload.setdefault('fy', a.fy)
        payload.setdefault('total_sales',
                           sum(amount(r) for r in payload.get('rows', ())))
    else:
        payload = fetch(a.url, os.environ['CHR_API_TOKEN'], a.fy, as_of)
    m = matrix(payload, load_hq_csv(a.hq), a.fy, as_of, a.include_unlabelled)

    problems = check(m)
    L = lambda v: '%.2f L' % (v / 1e5)                                  # noqa: E731
    print('PRODUCTIVITY MATRIX  %s   %d complete month(s): %s'
          % (m['fy'], m['month_count'], ', '.join(m['months'])))
    print('measured on %s' % MEASURE_NOTE)
    print('=' * 92)
    print('%-26s %10s %6s %6s %12s %12s  %s'
          % ('HQ', 'Sales', 'Posts', 'Filled', 'PCPM filled', 'PCPM posts', 'Zone'))
    live = [r for r in m['rows'] if r['sales'] > 0]
    for r in sorted(live, key=lambda x: -(x['pcpm_filled'] or 0)):
        print('%-26s %10s %6g %6g %12s %12s  %s'
              % (r['hq'][:26], L(r['sales']), r['posts'], r['filled'],
                 L(r['pcpm_filled']) if r['pcpm_filled'] is not None else '—',
                 L(r['pcpm_posts']) if r['pcpm_posts'] is not None else '—',
                 ('NOT SCORED — shares %s with %d other HQ(s)'
                  % (r['shares_city_with'] and
                     T.norm(_HQ_PLACE.sub('', r['hq'])).split()[-1] or '?',
                     len(r['shares_city_with']))
                  if not r['denominator_safe']
                  else (r['zone'] or {}).get('code', 'no people posted'))
                 + ('   <- %d%% of one SS is billed here' % round(r['town_concentration'] * 100)
                    if r['town_concentration'] >= 0.45 and r['denominator_safe'] else '')))
    t = m['totals']
    print('-' * 92)
    print('%-26s %10s %6g %6g   headcount of the HQs that billed'
          % ('TOTAL (%d HQs billing)' % len(live), L(t['attributed']),
             t['posts_billing'], t['filled_billing']))
    print('%-26s %10s %6g %6g   the whole network, for scale'
          % ('(all %d HQs)' % t['hqs'], '', t['posts'], t['filled']))
    print('%-26s %10s   %s' % ('Unattributed', L(t['unattributed']),
                               '%d town(s) with no HQ' % len(m['unattributed']['towns'])))
    for x in m['unattributed']['towns'][:5]:
        print('      %-22s %10s' % (x['town'], L(x['sales'])))
    u = m['unlabelled_batch']
    if u['sales'] and not u['included']:
        print('%-26s %10s   EXCLUDED: batch with no branch_code (%s), %d towns'
              % ('Unlabelled batch', L(u['sales']), '; '.join(u['names'])[:40],
                 len(u['towns'])))
    if m['excluded_part_months']:
        print('%-26s %10s   part months, excluded from every comparison'
              % ('Not yet complete', L(m['excluded_part_months'])))
    print()
    counts = defaultdict(int)
    for r in live:
        counts[(r['zone'] or {}).get('code', 'no zone')] += 1
    unsafe = [r for r in live if not r['denominator_safe']]
    if unsafe:
        print('  %-14s %3d HQs   denominator incomplete — the town billing cannot be '
              'split between them' % ('NOT SCORED', len(unsafe)))
        for c, d in sorted(m['shared_cities'].items()):
            print('      %-12s %2d HQ rows, %g posts between them'
                  % (c.title(), len(d['hqs']), d['posts']))
    for lo, hi, code, verdict, _ in ZONES:
        print('  %-14s %3d HQs   %s' % (code, counts.get(code, 0), verdict))
    if problems:
        print('\nPROBLEMS')
        for p in problems:
            print('  ! ' + p)
        raise SystemExit(1)
    print('\nchecks pass: billing reconciles, every PCPM is sales/people/months')
    if a.json:
        json.dump(m, open(a.json, 'w', encoding='utf-8'), indent=1, default=str)
        print('wrote ' + a.json)
