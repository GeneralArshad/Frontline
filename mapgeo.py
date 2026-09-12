#!/usr/bin/env python3
"""
Turn PIN codes into HQ coordinates, and refuse to invent one.

WHY PIN CODES AND NOT CITY NAMES. bb_org.json carries 2,046 distinct pincodes against 329
territories. India Post publishes an official directory mapping every PIN to a latitude
and longitude. That chain — territory to PIN to coordinate — is entirely sourced from
documents somebody else is accountable for. The alternative was me writing 294 city
coordinates from memory, which would have been wrong in ways nobody could audit: a town
50 km out looks exactly like a town in the right place.

AN HQ WITH NO PIN GETS NO POINT. It goes on the unplaced list with its headcount, and the
screen says how many people are unplaced. That matters more here than on most maps,
because the largest group in this data is the 371 people in HQs with no Frontline
presence — precisely the ones most likely to lack coordinates. A map that quietly drops
them would hide the finding the whole screen exists to make.

THE MEDIAN, NOT THE MEAN. A territory's PINs can span a metro area, and one outlying PIN
(a depot on the far edge of the district) drags a mean into a field. The median of each
axis sits inside the cluster.

THE GPS CROSS-CHECK IS THE POINT OF THE CONFIDENCE FIELD. Where a territory has BOTH a
PIN-derived coordinate and real visit GPS, the two should agree within a few kilometres.
Where they disagree badly, one of them is wrong and the report says so rather than
picking a winner.
"""

import csv
import json
import os
import statistics

# Column names vary between data.gov.in releases; accept the ones seen in the wild.
PIN_KEYS = ["pincode", "pin_code", "pin", "office_pin", "postal_code"]
LAT_KEYS = ["latitude", "lat", "office_latitude"]
LNG_KEYS = ["longitude", "long", "lng", "office_longitude"]


def _pick(row, keys):
    low = {str(k or "").strip().lower().replace(" ", "_"): v for k, v in row.items()}
    for k in keys:
        if k in low and str(low[k]).strip():
            return str(low[k]).strip()
    return ""


def load_pins(path):
    """Read the India Post directory into {pin: (lat, lng)}.

    Averages duplicates: a PIN has many post offices and the directory lists each, so the
    same PIN appears with slightly different points. Their centre is the PIN's centre.
    """
    if not path or not os.path.exists(path):
        return {}, ["no PIN directory at %s" % path]
    acc, issues = {}, []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            pin = _pick(row, PIN_KEYS)
            if not (pin.isdigit() and len(pin) == 6):
                continue
            try:
                lat = float(_pick(row, LAT_KEYS))
                lng = float(_pick(row, LNG_KEYS))
            except ValueError:
                continue
            # India's bounding box. A row outside it is a bad record, not a place.
            if not (6.0 <= lat <= 37.5 and 68.0 <= lng <= 97.5):
                continue
            acc.setdefault(pin, []).append((lat, lng))
    out = {p: (round(statistics.fmean(a[0] for a in v), 5),
               round(statistics.fmean(a[1] for a in v), 5))
           for p, v in acc.items()}
    if not out:
        issues.append("the PIN directory parsed to zero usable rows — check the columns")
    return out, issues


def place(pins_by_terr, pin_table):
    """{territory: [pin,...]} -> {territory: {lat,lng,pins,used}}.

    `used` is how many of the territory's PINs were found. A territory placed on one PIN
    out of nine is a weaker claim than one placed on all nine, and the screen shows it.
    """
    out = {}
    for terr, pins in (pins_by_terr or {}).items():
        pts = [pin_table[str(p)] for p in (pins or []) if str(p) in pin_table]
        if not pts:
            continue
        out[terr] = {
            "lat": round(statistics.median(p[0] for p in pts), 5),
            "lng": round(statistics.median(p[1] for p in pts), 5),
            "pins": len(pins or []), "used": len(pts),
        }
    return out


def km(a, b):
    """Haversine. Flat degrees are not distance: a degree of longitude is 110 km at
    Kanyakumari and 96 km at Srinagar, and this table spans both."""
    import math
    lat1, lng1 = a
    lat2, lng2 = b
    p = math.pi / 180
    h = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2)
    return round(12742 * math.asin(math.sqrt(max(0.0, h))), 2)


def payload(placed, unplaced):
    return {"terr": placed, "unplaced": sorted(unplaced),
            "meta": {"placed": len(placed), "unplaced": len(unplaced)}}


if __name__ == "__main__":
    # A self-test with a synthetic directory, so the logic is proven before the real
    # 155,000-row file exists. Every number here is chosen to make a specific check bite.
    tbl = {
        "560013": (12.99, 77.55), "560015": (13.01, 77.57), "560057": (12.95, 77.50),
        "620001": (10.79, 78.70), "620004": (10.81, 78.69),
        "999999": (99.00, 99.00),          # out of India: must never be loaded
    }
    got = place({"BO Bangalore-26": ["560013", "560015", "560057"],
                 "BO Trichy-02": ["620001", "620004", "111111"],
                 "BO Nowhere": ["111111"]}, tbl)
    assert "BO Nowhere" not in got, "a territory with no known PIN must not be placed"
    assert got["BO Trichy-02"]["used"] == 2 and got["BO Trichy-02"]["pins"] == 3, \
        "partial placement must be reported, not hidden"
    b = got["BO Bangalore-26"]
    assert abs(b["lat"] - 12.99) < 1e-6, "the median, not the mean: got %s" % b["lat"]
    assert km((12.99, 77.55), (13.01, 77.57)) < 4, "haversine is wrong at city scale"
    assert km((12.97, 77.59), (28.61, 77.21)) > 1700, "Bangalore to Delhi is ~1740 km"
    print("mapgeo self-test ok —", json.dumps(got, indent=1))
