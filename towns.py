#!/usr/bin/env python3
"""
Which town a stockist is in, and which Frontline HQ that town belongs to.

    python3 towns.py --db data/channel.db            # what merges, and what will not map
    python3 towns.py --db data/channel.db --hq geography.csv

Two questions that look like one. A Margbooks export says a stockist is in `BELGAUM`;
another row in the same export says `BELAGAVI`. Those are the same city — the state
renamed it in 2014 and half the trade never changed the ledger — but nothing in the data
says so, so the town table shows two rows, the drill-down from either shows half the
accounts, and a per-town productivity figure is computed against half a denominator.

That is question one: **what is the canonical town**. Question two only exists because
the two systems were built from different registers. Channel Health knows towns, because
Margbooks records where it shipped. Frontline knows HQs, because HR records where a
person is posted. `BELGAUM` the town and `BBS BELGAUM BO` the HQ are the same place and
share no characters in common at the ends. Joining sales to headcount means resolving
both to something a computer can match.

**Why a curated alias table and not fuzzy matching.** Edit distance says `INDI` and
`INDORE` are two edits apart; they are 800km apart and in different states. It also says
`BIJAPUR` and `BIJNOR` are close, and they are in Karnataka and Uttar Pradesh. Anything
that merges towns by string similarity will eventually merge two real towns and move
money between them, silently, in a direction nobody can audit. So the merges here are
either mechanical and safe (case, spacing, punctuation, a trailing branch number) or they
are named explicitly by a human in ALIASES below. Everything else is left alone and
reported by `near_misses()` for someone to look at — a list to review is a nuisance, a
wrong merge is a wrong report.

**Why the division matters to the HQ join.** British Biologicals posts two field forces
into the same cities: 379 main-division HQs and 68 specialty ones, the specialty rows
prefixed `BBS`. Bangalore therefore has a `Bangalore` HQ with 33 posts and a
`BBS BANGALORE` HQ with 8. Town alone cannot say which of the two a sale belongs to —
but the product can, because `divisions.py` already resolves every item to BB-Main,
BB-Speciality or Advanced Nutrition. So the key is (town, division), not town, and the
specialty sales of Bangalore go to the specialty HQ. Where a town has no specialty HQ,
specialty sales fall back to the main HQ rather than vanishing, and `resolve()` says so
in its reason field.

Nothing in this module guesses in silence. Every function that cannot answer returns the
reason it could not, and the callers print those reasons into the report.
"""
from __future__ import annotations
import re
import unicodedata
from collections import defaultdict

# --------------------------------------------------------------------- normalising
# Mechanical, reversible, and safe: none of these can merge two different places.
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_SPACE = re.compile(r"\s+")

# Trailing noise on a station string. A branch number or a compass point distinguishes
# two depots inside one city, not two cities: BANGALORE-1 and BANGALORE-2 are Bangalore.
# The suffix is dropped for the canonical key and preserved in the alias list, so the
# report can still say which spellings fed a row.
_TRAIL = re.compile(
    r"(?:\s+|\s*[-–]\s*)(?:"
    r"NO\.?\s*\d+|\d+|[IVX]{1,4}|"
    r"EAST|WEST|NORTH|SOUTH|CENTRAL|E|W|N|S|C|"
    r"BO|HO|RO|DEPOT|BRANCH|CITY|TOWN|DIST|DISTT|DISTRICT|MAIN|POOL"
    r")\s*$", re.I)

# Division tags Margbooks leaves inside a station string on some branches.
_TAG = re.compile(r"\((?:ADN|ADV|SPL|BB|BBS|AN)\)", re.I)


def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s)
                   if not unicodedata.combining(c))


def norm(name) -> str:
    """Upper, unaccented, unpunctuated, single-spaced. No merging beyond that."""
    s = _strip_accents(str(name or '')).upper()
    s = _TAG.sub(' ', s)
    s = _PUNCT.sub(' ', s)
    return _SPACE.sub(' ', s).strip()


def _squash(s: str) -> str:
    """Spaces removed as well. `NEW DELHI` and `NEWDELHI` are one town; nobody
    has ever founded a settlement whose name differs from another's only by a space."""
    return s.replace(' ', '')


def base(name) -> str:
    """The canonical key: normalised, branch suffixes peeled, spaces squashed."""
    s = norm(name)
    prev = None
    while s and s != prev:                 # `BANGALORE - 1 EAST` needs two passes
        prev = s
        s = _TRAIL.sub('', s).strip()
    return _squash(s or norm(name))


# --------------------------------------------------------------------- named aliases
# One line per city whose spellings a human has confirmed are the same place. The key is
# the canonical name we print; the values are every other spelling seen in the trade.
# Add to this table rather than loosening the matching rules — a new line here is a
# decision somebody made and can be argued with, a looser rule is a decision nobody made.
ALIASES = {
    # Karnataka — the 2014 renamings, both spellings still in daily use
    'BENGALURU': ['BANGALORE', 'BANGLORE', 'BENGALOORU'],
    'BELAGAVI': ['BELGAUM', 'BELGAON'],
    'VIJAYAPURA': ['BIJAPUR', 'VIJAYAPUR'],
    'KALABURAGI': ['GULBARGA', 'KALABURGI'],
    'MYSURU': ['MYSORE'],
    'MANGALURU': ['MANGALORE'],
    'HUBBALLI': ['HUBLI', 'HUBLI DHARWAD', 'HUBBALLI DHARWAD'],
    'SHIVAMOGGA': ['SHIMOGA'],
    'BALLARI': ['BELLARY'],
    'TUMAKURU': ['TUMKUR'],
    'CHIKKAMAGALURU': ['CHIKMAGALUR', 'CHICKMAGALUR', 'CHIKAMAGALUR'],
    'HOSAPETE': ['HOSPET'],
    'CHIKKABALLAPURA': ['CHIKKABALLAPUR', 'CHIKBALLAPUR'],
    'DAVANAGERE': ['DAVANGERE'],
    'CHAMARAJANAGARA': ['CHAMARAJ NAGAR', 'CHAMARAJANAGAR'],

    # Tamil Nadu
    'TIRUCHIRAPPALLI': ['TRICHY', 'TIRUCHY', 'TRICHIRAPALLI'],
    'THOOTHUKUDI': ['TUTICORIN'],
    'THANJAVUR': ['TANJORE', 'TANJAVUR'],
    'VIRUDHUNAGAR': ['VIRUTHUNAGAR'],
    'RAMANATHAPURAM': ['RAMNAD'],
    'KOVILPATTI': ['KOVILPPATTI'],
    'NAGERCOIL': ['NAGARCOIL', 'NAGERKOIL'],
    'TIRUPPUR': ['TIRUPUR'],
    'PUDUCHERRY': ['PONDICHERRY', 'PONDY'],

    # Kerala
    'KOZHIKODE': ['CALICUT'],
    'THIRUVANANTHAPURAM': ['TRIVANDRUM'],
    'THRISSUR': ['TRICHUR'],
    'KOLLAM': ['QUILON'],
    'ALAPPUZHA': ['ALLEPPEY'],
    'PALAKKAD': ['PALGHAT'],
    'KANNUR': ['CANNANORE'],
    'THALASSERY': ['TELLICHERRY'],
    'KOCHI': ['COCHIN'],          # Ernakulam is deliberately NOT merged here — see below

    # Maharashtra / Gujarat / west
    'MUMBAI': ['BOMBAY'],
    'PUNE': ['POONA'],
    'NASHIK': ['NASIK'],
    'CHHATRAPATI SAMBHAJINAGAR': ['AURANGABAD'],
    'SOLAPUR': ['SHOLAPUR'],
    'AHILYANAGAR': ['AHMEDNAGAR', 'AHMADNAGAR'],
    'VADODARA': ['BARODA'],
    'AHMEDABAD': ['AMDAVAD', 'AHEMDABAD', 'AHMADABAD'],
    'BILIMORA': ['BILMORA'],
    'GODHRA': ['GODHARA'],
    'MEHSANA': ['MAHESANA', 'MEHASANA'],
    'NAVSARI': ['NAVASARI'],
    'JUNAGADH': ['JUNAGARH'],
    'BHAVNAGAR': ['BHAUNAGAR'],

    # North
    'DELHI': ['NEW DELHI', 'NEWDELHI'],
    'GURUGRAM': ['GURGAON'],
    'PRAYAGRAJ': ['ALLAHABAD'],
    'VARANASI': ['BENARES', 'BANARAS', 'BANARES'],
    'KANPUR': ['CAWNPORE'],
    'SHIMLA': ['SIMLA'],
    'DEHRADUN': ['DEHRA DUN'],

    # East / north-east
    'KOLKATA': ['CALCUTTA'],
    'BHUBANESWAR': ['BHUBANESHWAR', 'BHUBANESWER'],
    'JAMSHEDPUR': ['TATANAGAR'],
    'GUWAHATI': ['GAUHATI'],
    'BRAHMAPUR': ['BERHAMPUR', 'BEHRAMPUR', 'BRAHMPUR'],
    'BAHARAMPUR': ['BEHARAMPORE', 'BERHAMPORE', 'BAHARAMPORE'],
    'AIZAWL': ['AIZWAL'],
    'HOOGHLY': ['HOOGLY', 'HUGLI'],

    # Andhra / Telangana
    'VISAKHAPATNAM': ['VIZAG', 'VISAKAPATNAM'],
    'VIJAYAWADA': ['BEZAWADA'],
    'RAJAMAHENDRAVARAM': ['RAJAHMUNDRY', 'RAJMUNDRY'],
    'ANANTAPUR': ['ANANTHAPUR', 'ANANTAPURAMU'],
}

# Two places the trade uses interchangeably that this module refuses to merge, with the
# reason, so the next person does not "fix" it. Both are reported by near_misses().
NOT_MERGED = {
    ('KOCHI', 'ERNAKULAM'): 'a city and its district; some ledgers bill them separately',
    ('HYDERABAD', 'SECUNDERABAD'): 'twin cities, routinely separate stockist territories',
    ('MUMBAI', 'THANE'): 'adjacent but distinct territories with their own HQs',
    ('HUBBALLI', 'DHARWAD'): 'twin cities; the export uses both, sometimes for one party',
}

# canonical-key -> canonical display name, built once
_CANON = {}
for _display, _variants in ALIASES.items():
    _CANON[base(_display)] = _display
    for _v in _variants:
        _CANON[base(_v)] = _display


def key_of(name) -> str:
    """The join key. Canonical first, THEN based — so BANGALORE the HQ and BENGALURU the
    canonical town produce the same key. Keying one side before canonicalising and the
    other after is how a join silently loses every renamed city."""
    k = base(name)
    disp = _CANON.get(k)
    return base(disp) if disp else k


def canonical(name):
    """Canonical display name for a station string, and the key it matched on."""
    k = base(name)
    return _CANON.get(k, norm(_TRAIL.sub('', norm(name)).strip()) or norm(name)), k


def canonicalise(stations):
    """Map every raw station string to a canonical town.

    Returns (mapping, aliases) where mapping is raw -> canonical display name and
    aliases is canonical -> sorted list of the raw spellings that fed it. The alias
    list is what the report prints beside a merged town, so a reader who knew the
    town as BELGAUM can see where it went.
    """
    mapping, groups = {}, defaultdict(set)
    for s in stations:
        if not str(s or '').strip():
            continue
        disp, key = canonical(s)
        mapping[s] = disp
        groups[disp].add(norm(s))
    aliases = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
    return mapping, aliases


# --------------------------------------------------------------------- review, not merge
def _lev(a, b, cap=3):
    """Levenshtein, abandoned once it exceeds `cap` — we only care about near ties."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def near_misses(towns, cap=2, minlen=6):
    """Pairs close enough to be worth a human look, that this module did NOT merge.

    Short names are excluded: at four characters an edit of two is a different word.
    """
    ts = sorted({t for t in towns if len(t) >= minlen})
    out = []
    for i, a in enumerate(ts):
        for b in ts[i + 1:]:
            if abs(len(a) - len(b)) > cap:
                continue
            d = _lev(_squash(a), _squash(b), cap)
            if 0 < d <= cap:
                why = NOT_MERGED.get((a, b)) or NOT_MERGED.get((b, a))
                out.append({'a': a, 'b': b, 'distance': d,
                            'note': why or 'not merged — confirm whether these are one town'})
    return out


# --------------------------------------------------------------------- town -> HQ
# Frontline's specialty HQs are the main-division name with a BBS prefix and sometimes a
# BO (branch office) suffix: `BBS BELGAUM BO`. The prefix is the division, not the place.
_HQ_PREFIX = re.compile(r'^(BBS|BBN|BB|AN|ADN|SPL)\s+', re.I)

MAIN = 'BB-Main'
SPECIALITY = 'BB-Speciality'
NUTRITION = 'Advanced Nutrition'
NEPAL = 'BB Nepal'

# Frontline's geo tree names the same division several ways, and Channel Health's
# divisions.py names it a third. One table, so the join is not re-argued per caller.
DIV_ALIASES = {
    MAIN: ['BB MAIN', 'BB MAIN DIVISION', 'MAIN', 'BB-MAIN', 'BB'],
    SPECIALITY: ['SPECIALTY', 'SPECIALITY', 'BB SPECIALTY', 'BB SPECIALITY',
                 'BB-SPECIALITY', 'BBS'],
    NUTRITION: ['ADVANCED NUTRITION', 'ADN', 'AN', 'ADV', 'NUTRITION'],
    NEPAL: ['BB NEPAL', 'NEPAL', 'BBN'],
}
_DIV = {}
for _d, _vs in DIV_ALIASES.items():
    _DIV[norm(_d)] = _d
    for _v in _vs:
        _DIV[norm(_v)] = _d


def division_of(value):
    """Canonical division name, or None when the value names nothing we know.

    None is returned rather than a default. A sale whose division cannot be read must
    show up as unattributed, not quietly land in the largest division.
    """
    return _DIV.get(norm(value))


def _hq_parts(hq_name, division=None):
    """(place key, division, raw name) for a Frontline HQ.

    `division` is the geo tree's own level-0 name when the caller has it. The prefix is
    only consulted when it does not — a CSV export of the HQ table drops the division
    column, and `BBS BELGAUM BO` is then the only evidence left of which force is posted
    there. Reading the prefix as authoritative when the real field exists would let a
    naming convention outrank the data.
    """
    raw = str(hq_name or '').strip()
    m = _HQ_PREFIX.match(raw)
    div = division_of(division) if division else None
    if div is None and m:
        div = division_of(m.group(1))
    place = _HQ_PREFIX.sub('', raw) if m else raw
    return key_of(place), div or MAIN, raw


# Headcount columns that are summed when two rows turn out to be one HQ. Anything not
# named here is taken from the row whose name wins, because summing a zone or a state is
# meaningless and averaging a status is worse.
_SUM_COLS = ('Posts', 'Vacant', 'On Frontline', 'Reporting', 'Rx',
             'posts', 'vacant', 'on_frontline', 'reporting', 'rx')


def _num(v):
    try:
        return float(str(v).replace(',', '').strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def hq_index(hqs):
    """Index Frontline HQ rows for lookup, merging rows that name the same HQ.

    `hqs` is any iterable of dicts carrying at least an `HQ` key; whatever else each
    row holds (posts, vacant, zone, state) is carried through.

    **Why rows get merged.** The geo tree lists Bangalore twice — once as `Bangalore`
    with 33 posts and once as `BB BANGALORE` with 5 — and they are the same
    headquarters written two ways, not two places. Left separate, Bangalore's PCPM is
    computed over 33 people while five of its colleagues sell into the same town under
    a name the sales data has never heard of, and the town's billing lands entirely on
    the first row. So same place plus same division means one HQ: posts are summed,
    and the shorter, unprefixed name is the one printed, because that is the name the
    rest of the business uses.
    """
    ix = {'by': defaultdict(dict), 'rows': {}, 'merged': defaultdict(list)}
    for row in hqs:
        name = row.get('HQ') or row.get('hq')
        if not name or str(name).strip() in ('—', ''):
            continue
        key, div, raw = _hq_parts(name, row.get('Division') or row.get('division'))
        if not key:
            continue
        seen = ix['by'][div].get(key)
        if seen is None:
            ix['by'][div][key] = raw
            ix['rows'][raw] = dict(row)
            continue
        # The unprefixed name wins; ties go to the shorter string. `Bangalore` beats
        # `BB BANGALORE`, and `Begusarai` beats `BB BEGUSARAI BO`.
        keep, drop = (raw, seen) if _better(raw, seen) else (seen, raw)
        merged = ix['rows'].pop(seen)
        for c in _SUM_COLS:
            if c in merged or c in row:
                merged[c] = _num(merged.get(c)) + _num(row.get(c))
        if keep != seen:                       # the new name is the better one
            for k, v in row.items():
                if k not in _SUM_COLS and k not in ('HQ', 'hq'):
                    merged.setdefault(k, v)
            merged['HQ'] = keep
        ix['by'][div][key] = keep
        ix['rows'][keep] = merged
        ix['merged'][keep].append(drop)
    ix['by'] = dict(ix['by'])
    ix['merged'] = dict(ix['merged'])
    return ix


def _better(a, b):
    """True when `a` is the better display name of two spellings of one HQ."""
    pa, pb = bool(_HQ_PREFIX.match(a)), bool(_HQ_PREFIX.match(b))
    if pa != pb:
        return not pa                          # unprefixed wins
    return len(a) < len(b)


def resolve(town, division, ix):
    """(HQ name or None, reason). Never guesses without saying so.

    **A division's sales are never credited to another division's people.** British
    Biologicals runs three forces on three product ranges, and the rule from the business
    is that each is accounted for only on its own range. An earlier version of this
    function, finding no speciality HQ in a town, credited the sale to the main HQ there
    and said so in the reason. Labelled or not, that put a speciality rupee into a main
    rep's denominator: it lifted main's productivity by the amount of a product main does
    not sell, and it did it most where speciality is thinnest on the ground.

    The size of it: 98.8% of Advanced Nutrition's billing — a range with no employees
    onboarded at all — and 23.6% of speciality's landed on main HQs this way. So the
    fallback is gone. Billing with no HQ of its own division behind it is returned
    unresolved, with the division named, and `matrix()` reports it as its own figure.
    That number is not a gap in the arithmetic; it is the business's white space, and it
    is worth more on the page than buried in somebody else's PCPM.
    """
    key = key_of(town)
    if not key:
        return None, 'no town on the sale'
    div = division_of(division) if division else None
    by = ix['by']
    if div and key in by.get(div, {}):
        return by[div][key], 'matched on town and division'
    here = [d for d in by if key in by[d] and d != div]
    if div:
        if here:
            return None, ('no %s post in this town — %s sells here, but its people are '
                          'not measured on %s products' % (div, ' and '.join(sorted(here)), div))
        return None, 'no %s post in this town, and no other division either' % div
    if here:
        # No division on the sale at all. This is not a cross-division credit — there is
        # no division to violate — and it only happens on the emergency path where every
        # per-division fetch failed. `check()` raises it if it carries real money.
        pick = MAIN if MAIN in here else sorted(here)[0]
        return by[pick][key], 'matched on town; division not stated on the sale'
    return None, 'town has no Frontline HQ in any division'


# --------------------------------------------------------------------- report
def report(db_path, hq_csv=None):
    import sqlite3
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT branch_code, station, COUNT(DISTINCT party) "
                       "FROM sale_line GROUP BY 1, 2").fetchall()
    con.close()
    per_branch = defaultdict(list)
    for b, s, n in rows:
        per_branch[b].append((s, n))

    print("TOWN MERGES — what canonicalising changes, per super stockist")
    print("=" * 74)
    total_before = total_after = 0
    for b, items in sorted(per_branch.items()):
        raw = [s for s, _ in items]
        mapping, aliases = canonicalise(raw)
        before, after = len({norm(r) for r in raw}), len(set(mapping.values()))
        total_before += before
        total_after += after
        flag = '' if before == after else '   <-- merges'
        print(f"\n{b}: {before} station strings -> {after} towns{flag}")
        for canon_name, spellings in sorted(aliases.items()):
            counts = {s: n for s, n in items}
            tot = sum(counts.get(s, 0) for s in raw if norm(s) in spellings)
            print(f"    {canon_name:<26} <- {', '.join(spellings)}   ({tot} stockists)")
    print(f"\nNetwork: {total_before} station strings -> {total_after} towns")

    allt = set()
    for items in per_branch.values():
        m, _ = canonicalise([s for s, _ in items])
        allt |= set(m.values())
    nm = near_misses(allt)
    print(f"\nNOT MERGED — {len(nm)} pair(s) close enough to check by hand")
    print("=" * 74)
    for p in nm:
        print(f"  {p['a']:<24} {p['b']:<24} d={p['distance']}  {p['note']}")

    if hq_csv:
        import csv
        with open(hq_csv, encoding='utf-8-sig') as f:
            r = list(csv.reader(f))
        hdr = r[1] if r and r[0] and len(r[0]) == 1 else r[0]
        start = 2 if hdr is r[1] else 1
        hqs = [dict(zip(hdr, x)) for x in r[start:] if len(x) == len(hdr)]
        ix = hq_index(hqs)
        counts = ', '.join('%d %s' % (len(v), d) for d, v in sorted(ix['by'].items()))
        print(f"\nTOWN -> HQ  ({counts})")
        print("=" * 74)
        miss, fell = [], []
        for t in sorted(allt):
            hq, why = resolve(t, None, ix)
            if not hq:
                miss.append(t)
            elif 'credited to' in why:
                fell.append((t, hq, why))
        print(f"  {len(allt) - len(miss)} of {len(allt)} towns resolve to an HQ")
        if miss:
            print(f"  {len(miss)} will not map — their sales cannot be credited to anyone:")
            for t in miss:
                print(f"      {t}")
        if fell:
            print(f"\n  {len(fell)} town(s) resolved across divisions:")
            for t, hq, why in fell:
                print(f"      {t:<22} -> {hq:<24} {why}")
        if ix['merged']:
            n = sum(len(v) for v in ix['merged'].values())
            print(f"\n  {n} duplicate HQ row(s) merged into {len(ix['merged'])} HQ(s):")
            for keep, dropped in sorted(ix['merged'].items())[:12]:
                posts = ix['rows'][keep].get('Posts')
                print(f"      {keep:<24} absorbed {', '.join(dropped):<28} posts now {posts:g}")
            if len(ix['merged']) > 12:
                print(f"      ... and {len(ix['merged']) - 12} more")


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--db', default='data/channel.db')
    ap.add_argument('--hq', help='Frontline geography CSV, to test the HQ join')
    a = ap.parse_args()
    report(a.db, a.hq)
