#!/usr/bin/env python3
"""
The HR geography overlay: hr_org.json on top of what Frontline knows.

WHY AN OVERLAY AND NOT A REPLACEMENT. The two systems do not cover the same people.
HR's workbook is BB Main Division only — 803 posts across four zones. Frontline also
carries BB Specialty, a Nepal zone, and a large group with no zone recorded at all.
Neither is a superset. So this does not pick a winner; it merges, and it records WHERE
EACH PERSON'S GEOGRAPHY CAME FROM.

That provenance is the whole point. Before this, a rep in the report showed state '—'
and there was no way to tell whether that meant "we don't know" or "nobody works there".
Now every person carries gsrc: 'hr' (HR's roster said so), 'fl' (only Frontline said so),
or '' (neither did). A blank is reported as a blank rather than being back-filled from a
neighbouring row, because a guessed state is worse than an admitted gap — it looks
identical to a known one and cannot be audited.

THE OTHER HALF OF THE JOB IS THE PEOPLE FRONTLINE HAS NEVER HEARD OF. 371 people sit in
HQs where nobody appears in Frontline at all. They are not in D.reps, because D.reps is
built from Frontline's employee list. If the geography screen counted only D.reps it
would report those HQs as empty — which is exactly the wrong answer, since the whole
finding is that they are staffed but not onboarded. So HR-only posts are emitted
separately, and the screen adds them to headcount while keeping them out of any metric
that needs activity data they cannot have.
"""

import json
import os


def _norm_code(s):
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def norm_hq(s):
    """Frontline writes 'BB TENALI', HR writes 'Tenali'. One place, two systems."""
    t = " ".join(str(s or "").split()).upper()
    if t.startswith("BB "):
        t = t[3:]
    return "".join(ch for ch in t if ch.isalnum())


def load(path):
    """Read hr_org.json. Absent or broken is not fatal — the report predates it."""
    issues = []
    if not os.path.exists(path):
        return None, ["no hr_org.json at " + path]
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        return None, ["hr_org.json did not parse: %s" % e]
    people = d.get("people") or []
    if not people:
        return None, ["hr_org.json has no people"]
    by = {}
    for p in people:
        c = _norm_code(p.get("code"))
        if not c:
            continue                                          # vacancies have no code
        if c in by:
            issues.append("duplicate EmpCode in HR roster: %s" % p.get("code"))
            continue
        by[c] = p
    return {"by": by, "people": people, "meta": d.get("meta") or {},
            "zoneOf": d.get("zoneOf") or {}}, issues


def overlay(hr, reps):
    """Attach HR geography to each Frontline rep. Returns counts, mutates reps.

    Frontline's own zone/state/hq are LEFT ALONE. They are what the rest of the report
    already filters and groups by, and silently changing them here would move numbers on
    every other screen. The HR view is additive: new fields, new screen.
    """
    if not hr:
        for x in reps:
            x["hzn"] = x["hst"] = x["hlab"] = x["hhq"] = ""
            x["gsrc"] = "fl" if (x.get("st") and x["st"] != "—") else ""
        return {"matched": 0, "flOnly": len(reps), "hrOnly": 0}
    by, seen = hr["by"], set()
    matched = 0
    for x in reps:
        c = _norm_code(x.get("c"))
        p = by.get(c)
        if p:
            seen.add(c)
            matched += 1
            x["hzn"] = p.get("zone") or ""
            x["hst"] = p.get("state") or ""       # the true state, for the map
            x["hlab"] = p.get("stateRaw") or ""   # HR's own sales label, kept verbatim
            x["hhq"] = p.get("hq") or ""
            x["gsrc"] = "hr"
        else:
            x["hzn"] = x["hst"] = x["hlab"] = x["hhq"] = ""
            # Frontline knows where some of these people are even though HR does not —
            # Specialty and Nepal, mostly. '—' is the ETL's own placeholder for unknown.
            x["gsrc"] = "fl" if (x.get("st") and x["st"] != "—") else ""
    return {"matched": matched, "flOnly": len(reps) - matched,
            "hrOnly": sum(1 for p in hr["people"]
                          if p.get("code") and _norm_code(p["code"]) not in seen)}


def payload(hr, reps, stats):
    """The D.hrgeo block the browser reads. Arrays, not objects, to keep it small."""
    if not hr:
        return {}
    seen = {_norm_code(x.get("c")) for x in reps}
    # [code, design, staff, hq, territory, trueState, hrLabel, zone, doj, vacant]
    only = [[p.get("code", ""), p.get("design", ""), p.get("staff", ""), p.get("hq", ""),
             p.get("terr", ""), p.get("state", ""), p.get("stateRaw", ""),
             p.get("zone", ""), p.get("doj", ""), 1 if p.get("vacant") else 0]
            for p in hr["people"]
            if p.get("vacant") or _norm_code(p.get("code")) not in seen]
    return {
        "only": only,
        "zoneOf": hr["zoneOf"],
        "meta": dict(hr["meta"], matched=stats["matched"], flOnly=stats["flOnly"],
                     hrOnly=stats["hrOnly"]),
    }
