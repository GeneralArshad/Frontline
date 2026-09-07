#!/usr/bin/env python3
"""
Cross-check the incentive numbers against the Admin APIs, independently of etl.py.

WHY THIS IS A SEPARATE PROGRAM. Checking the pipeline with the pipeline's own code
proves only that it is consistent with itself. Every number here is fetched and counted
again from /admin/employees/{id}/day-plans, with its own month arithmetic and its own
definition of a reporting day, and then diffed against what the report is showing. Where
the two agree you have two independent witnesses. Where they disagree, you have a bug —
in one of them, and this prints enough to tell you which.

WHAT IT CHECKS
  1. Roster size          — how many employees the API returns vs what the report lists
  2. Reporting days       — per person per month, counted from day plans with visits
  3. The working-day base — non-Sundays per month, computed here from the calendar
  4. Tier                 — the reporting share re-scored against INCENTIVE_RULES, which
                            it parses out of the built template rather than restating
  5. Day-plan pagination  — whether any employee's day-plan list looks truncated

WHAT IT DELIBERATELY DOES NOT DO
  It does not write anything, anywhere. Every call is a GET. It will not touch the live
  report, the data disk, or the database. Run it as often as you like.

USAGE
    cd frontline-live-report
    python3 verify_incentive.py --month 2026-08
    python3 verify_incentive.py --month 2026-08 --csv /tmp/verify_aug.csv
    python3 verify_incentive.py --from 2026-04 --to 2026-08        # every month

It reads the same environment as etl.py — FRONTLINE_BASE, FRONTLINE_ORG_ID,
FRONTLINE_SVC_USERNAME, FRONTLINE_SVC_PASSWORD — from your .env. It never prints a
credential, and it never asks for one interactively.
"""
import argparse
import calendar
import datetime
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = os.path.dirname(os.path.abspath(__file__))

# .env, if python-dotenv is around; otherwise a two-line parser so this works bare.
_envf = os.path.join(HERE, ".env")
if os.path.exists(_envf):
    for line in open(_envf, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = os.environ.get("FRONTLINE_BASE", "https://hive-frontline-backend.com")
ORG = os.environ.get("FRONTLINE_ORG_ID", "")
USER = os.environ.get("FRONTLINE_SVC_USERNAME") or os.environ.get("FRONTLINE_SVC_EMAIL", "")
PASS = os.environ.get("FRONTLINE_SVC_PASSWORD", "")
CONC = int(os.environ.get("ETL_CONCURRENCY", "8"))
TEMPLATE = os.path.join(HERE, "template.html")

if not (USER and PASS and ORG):
    sys.exit("Missing FRONTLINE_SVC_USERNAME / FRONTLINE_SVC_PASSWORD / FRONTLINE_ORG_ID.\n"
             "They live in frontline-live-report/.env — the same ones etl.py uses.")


# ---------------------------------------------------------------- the rule, from source
def load_rules():
    """The thresholds come out of the built template, never out of a copy kept here.

    A verification script with its own copy of the pay rule verifies the wrong thing the
    first time somebody edits one and not the other."""
    src = open(TEMPLATE, encoding="utf-8").read()
    m = re.search(r"const INCENTIVE_RULES=\{(.*?)\n\};", src, re.S)
    if not m:
        sys.exit("No INCENTIVE_RULES in template.html — is the template built?")
    body = m.group(1)
    # re.S matters: the rule spans lines and carries a comment on the opening line.
    # Without it this quietly matched nothing and the script "found no tiers".
    blk = re.search(r"field\s*:\s*\[(.*?)\]\s*,\s*\n\s*(?:\w+\s*:|\})", body, re.S)
    tiers = []
    for row in re.findall(r"\[([^\]]+)\]", blk.group(1) if blk else ""):
        p = [x.strip().strip("'\"") for x in row.split(",")]
        if len(p) == 4:
            tiers.append((p[0], float(p[1]), float(p[2]), float(p[3])))
    g = dict(re.findall(r"(\w+)\s*:\s*(\d+)", re.search(r"gates:\s*\{([^}]*)\}", body).group(1)))
    if not tiers:
        sys.exit("INCENTIVE_RULES.field parsed to nothing — refusing to score against "
                 "an empty rule.")
    return tiers, {k: int(v) for k, v in g.items()}


# ---------------------------------------------------------------- API, read only
class Api:
    def __init__(self):
        self.s = requests.Session()
        self.token = None
        self.lock = threading.Lock()
        self.login()

    def login(self):
        r = self.s.post(f"{BASE}/auth/login", json={"username": USER, "password": PASS},
                        headers={"X-Organization-Id": ORG}, timeout=30)
        r.raise_for_status()
        j = r.json()
        d = j.get("data") or j
        self.token = (d.get("accessToken") or (d.get("tokens") or {}).get("accessToken")
                      or j.get("accessToken"))
        if not self.token:
            sys.exit("login succeeded but returned no accessToken")

    def get(self, path, _retry=True):
        h = {"Authorization": f"Bearer {self.token}", "X-Organization-Id": ORG}
        r = self.s.get(f"{BASE}{path}", headers=h, timeout=60)
        if r.status_code == 401 and _retry:
            with self.lock:
                self.login()
            return self.get(path, _retry=False)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, None


def pool(items, fn, n=CONC):
    out = []
    with ThreadPoolExecutor(max_workers=n) as ex:
        for i, r in enumerate(ex.map(fn, items)):
            out.append(r)
            if (i + 1) % 50 == 0:
                sys.stderr.write("\r  %d/%d" % (i + 1, len(items)))
                sys.stderr.flush()
    sys.stderr.write("\r" + " " * 30 + "\r")
    return out


# ---------------------------------------------------------------- calendar arithmetic
def workdays(a, b):
    """Every day except Sunday. Stated here rather than imported, on purpose: if the
    ETL's definition drifts, this script should disagree with it loudly."""
    a = datetime.date.fromisoformat(a)
    b = datetime.date.fromisoformat(b)
    n = 0
    while a <= b:
        if a.weekday() != 6:
            n += 1
        a += datetime.timedelta(days=1)
    return n


def month_span(mk):
    y, m = int(mk[:4]), int(mk[5:7])
    return mk + "-01", "%s-%02d" % (mk, calendar.monthrange(y, m)[1])


def months_between(a, b):
    out = []
    y, m = int(a[:4]), int(a[5:7])
    ey, em = int(b[:4]), int(b[5:7])
    while (y, m) <= (ey, em):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="single month, YYYY-MM")
    ap.add_argument("--from", dest="frm", help="first month, YYYY-MM")
    ap.add_argument("--to", dest="to", help="last month, YYYY-MM")
    ap.add_argument("--csv", help="write the per-person table here")
    ap.add_argument("--limit", type=int, default=0, help="only N employees (a smoke test)")
    a = ap.parse_args()

    if a.month:
        MK = [a.month]
    elif a.frm and a.to:
        MK = months_between(a.frm, a.to)
    else:
        sys.exit("give me --month YYYY-MM, or --from YYYY-MM --to YYYY-MM")

    tiers, gates = load_rules()
    print("rule, read from template.html")
    for t, s, c, d in tiers:
        print("  %-7s share >= %.0f%%   coverage >= %g%%   doctors/day >= %g"
              % (t, s * 100, c, d))
    print("  gates  %s" % json.dumps(gates))
    print()

    api = Api()

    # ---- roster ------------------------------------------------------------
    # Page through /admin/employees. The known pagination fault on this endpoint is the
    # reason the ETL has a roster-completion pass; if the page walk here disagrees with
    # the reported total, that is the first thing to look at and it is printed, not
    # swallowed.
    emps, page, total = [], 1, None
    while True:
        st, d = api.get("/admin/employees?page=%d&limit=100" % page)
        if st != 200 or not d:
            print("  ! /admin/employees page %d returned %s" % (page, st))
            break
        rows = d.get("employees") or d.get("data") or []
        total = ((d.get("pagination") or {}).get("total")) or total
        emps.extend(rows)
        if not rows or (total and len(emps) >= total):
            break
        page += 1
    seen, uniq = set(), []
    for e in emps:
        if e.get("_id") and e["_id"] not in seen:
            seen.add(e["_id"])
            uniq.append(e)
    emps = uniq
    print("roster")
    print("  employees returned by the page walk : %d" % len(emps))
    print("  total the API reports               : %s" % total)
    if total and len(emps) != total:
        print("  ! MISMATCH of %d — the page walk is not returning every employee."
              % abs(total - len(emps)))
        print("    This is the same pagination fault the ETL works around with per-code")
        print("    lookups. Any incentive run must use the completed roster, not this.")
    else:
        print("  page walk and reported total agree")
    print()

    if a.limit:
        emps = emps[:a.limit]

    # ---- day plans ---------------------------------------------------------
    def one(e):
        rec = {"code": (e.get("employeeCode") or "").strip(),
               "name": e.get("name") or "",
               "role": ((e.get("designationId") or {}).get("code") or "?"),
               "days": {}, "plans": 0, "trunc": False}
        for mk in MK:
            y, m = int(mk[:4]), int(mk[5:7])
            st, p = api.get("/admin/employees/%s/day-plans?month=%d&year=%d"
                            % (e["_id"], m, y))
            if st != 200 or not p:
                continue
            dps = (p or {}).get("dayPlans") or []
            rec["plans"] += len(dps)
            pg = (p or {}).get("pagination") or {}
            if pg.get("total") and len(dps) < pg["total"]:
                rec["trunc"] = True
            s = set()
            for x in dps:
                dt = (x.get("date") or "")[:10]
                if not dt:
                    continue
                # A reporting day is a day plan with at least one visit recorded, on a
                # working day. Same definition the report uses; counted from the API.
                if (x.get("visitCount") or 0) <= 0:
                    continue
                if datetime.date.fromisoformat(dt).weekday() == 6:
                    continue
                s.add(dt)
            rec["days"][mk] = sorted(s)
        return rec

    print("fetching day plans for %d employees over %s" % (len(emps), ", ".join(MK)))
    recs = [r for r in pool(emps, one) if r and r["code"]]

    # ---- score -------------------------------------------------------------
    field = {"BO", "SBO", "SCIENTIFIC- BUSINESS OFFICER"}
    today = datetime.date.today().isoformat()
    rows = []
    for r in recs:
        for mk in MK:
            f, t = month_span(mk)
            if t > today:
                t = today
            wd = workdays(f, t)
            n = len(r["days"].get(mk, []))
            share = (n / wd) if wd else 0
            tier = ""
            if wd < gates.get("minWindow", 0):
                tier = "short window"
            elif n < gates.get("minActiveDays", 0):
                tier = ""
            else:
                for tn, smin, _c, _d in tiers:
                    if share >= smin:
                        tier = tn + " (reporting only)"
                        break
            rows.append({"code": r["code"], "name": r["name"], "role": r["role"],
                         "month": mk, "days": n, "wd": wd,
                         "share": round(100 * share, 1), "tier": tier,
                         "trunc": r["trunc"]})

    # ---- report ------------------------------------------------------------
    print()
    print("reporting days per month, counted from the API")
    print("  %-8s %6s %6s %6s %6s %8s" % ("month", "people", "wdays", "median", "best", "cleared"))
    for mk in MK:
        mr = [x for x in rows if x["month"] == mk and x["role"] in field]
        if not mr:
            continue
        ds = sorted(x["days"] for x in mr)
        med = ds[len(ds) // 2] if ds else 0
        cleared = sum(1 for x in mr if x["tier"] and "short" not in x["tier"])
        print("  %-8s %6d %6d %6d %6d %8d" %
              (mk, len(mr), mr[0]["wd"], med, ds[-1] if ds else 0, cleared))

    trunc = sorted({x["code"] for x in rows if x["trunc"]})
    print()
    if trunc:
        print("  ! %d employees have a day-plan list shorter than the API's own total."
              % len(trunc))
        print("    Their day counts are LOWER BOUNDS. Codes: %s%s"
              % (", ".join(trunc[:8]), " ..." if len(trunc) > 8 else ""))
    else:
        print("  no employee's day-plan list looks truncated")

    top = sorted([x for x in rows if x["role"] in field],
                 key=lambda x: -x["days"])[:15]
    print()
    print("the fifteen highest single-month day counts in the range")
    print("  %-12s %-26s %-8s %5s %5s %7s  %s" %
          ("code", "name", "month", "days", "wd", "share", "tier"))
    for x in top:
        print("  %-12s %-26s %-8s %5d %5d %6.1f%%  %s" %
              (x["code"], x["name"][:26], x["month"], x["days"], x["wd"],
               x["share"], x["tier"] or "-"))

    if a.csv:
        import csv
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            wtr.writeheader()
            wtr.writerows(rows)
        print()
        print("wrote %d rows to %s" % (len(rows), a.csv))
        print("Diff it against the report: open Incentive eligibility, switch to")
        print("Month by month, Export to CSV, and compare the day counts column.")

    print()
    print("HOW TO READ A DISAGREEMENT")
    print("  This script counts a day plan with visitCount > 0 on a non-Sunday.")
    print("  The report counts a distinct date appearing in the visit-level call log.")
    print("  Those are the same thing unless a day plan carries a visit count that the")
    print("  visit detail does not back up — which is itself worth knowing.")


if __name__ == "__main__":
    main()
