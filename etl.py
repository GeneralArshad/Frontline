#!/usr/bin/env python3
"""
Frontline live-report ETL.

Pulls the FULL roster the correct way (name-search enumeration, so the broken
list-pagination can't drop reps), then geo + day-plans + visit detail, keeping an
incremental SQLite store so only NEW/CHANGED day-plans are fetched each run.
Computes the standard metrics and renders the interactive report to report.html.

Run standalone (python etl.py) or import run_etl() from the web app.
Safe to run concurrently-ish: uses a lock file so two refreshes don't overlap.
"""
import os, json, gzip, base64, time, sqlite3, datetime, threading, sys, re, io, gc
try:
    from org import load_org, match_roster, norm as orgnorm
except Exception as _e:            # a broken org.py must not take the ETL down
    load_org = lambda p: ({}, ["org.py failed to import: %s" % _e])
    match_roster = lambda o, c: dict(matched=0, rosterOnly=list(c), orgOnly=[], rate=0)
    orgnorm = lambda c: re.sub(r"[^A-Z0-9]", "", str(c or "").upper())
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE      = os.environ.get("FRONTLINE_BASE", "https://hive-frontline-backend.com")
ORG       = os.environ.get("FRONTLINE_ORG_ID", "")
# The backend's /auth/login expects a USERNAME (e.g. "superadmin"), not an email.
# Accept either env var name; FRONTLINE_SVC_EMAIL is kept for the existing render.yaml field.
USERNAME  = os.environ.get("FRONTLINE_SVC_USERNAME") or os.environ.get("FRONTLINE_SVC_EMAIL", "")
PASSWORD  = os.environ.get("FRONTLINE_SVC_PASSWORD", "")
LIFE_START= os.environ.get("LIFETIME_START", "2026-01")            # YYYY-MM
CONC      = int(os.environ.get("ETL_CONCURRENCY", "8"))
DATA_DIR  = os.environ.get("DATA_DIR", "./data")
DB_PATH   = os.path.join(DATA_DIR, "frontline.db")
REPORT    = os.path.join(DATA_DIR, "report.html")
META      = os.path.join(DATA_DIR, "meta.json")
PROGRESS  = os.path.join(DATA_DIR, "progress.json")
# Directory of this file. Repo-relative inputs (bb_org.json, hr.json) live beside it,
# NOT in DATA_DIR — that is the persistent disk and holds outputs only.
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))

# ---- progress -----------------------------------------------------------------
# Six phases, in the order run_etl() performs them. The UI names them, so changing
# this list changes the UI; keep the keys stable.
PHASES = [
    ("signin",   "Signing in to Frontline"),
    ("roster",   "Reading the employee roster"),
    ("geo",      "Mapping geography"),
    ("dayplans", "Listing day plans"),
    ("detail",   "Fetching call detail"),
    ("compute",  "Computing metrics and rendering"),
]
_PROG = {"running": False, "phase": "", "phaseIndex": 0, "label": "", "done": 0,
         "total": 0, "note": "", "startedAt": "", "at": "",
         "phases": [{"k": k, "label": l} for k, l in PHASES]}
_PROG_LAST = [0.0]
_PHASE_T0 = [0.0]


def prog(phase=None, note=None, done=None, total=None, force=False):
    """Update the progress file. Never raises: a refresh must not fail because it
    could not describe itself."""
    try:
        if phase is not None:
            keys = [k for k, _ in PHASES]
            # bank the previous phase's duration: the browser paces its progress bar
            # on the last run's timings, so the second refresh onwards is measured
            # rather than guessed
            if _PROG.get("phase") and _PHASE_T0[0]:
                _PROG.setdefault("phaseMs", {})[_PROG["phase"]] = \
                    int((time.time() - _PHASE_T0[0]) * 1000)
            _PHASE_T0[0] = time.time()
            _PROG["phase"] = phase
            _PROG["phaseIndex"] = keys.index(phase) if phase in keys else 0
            _PROG["label"] = dict(PHASES).get(phase, phase)
            _PROG["done"] = 0
            _PROG["total"] = 0
            force = True
        if note is not None:  _PROG["note"] = note
        if done is not None:  _PROG["done"] = done
        if total is not None: _PROG["total"] = total
        now = time.time()
        if not force and now - _PROG_LAST[0] < 0.25:
            return                       # throttle: never a measurable share of the work
        _PROG_LAST[0] = now
        _PROG["at"] = datetime.datetime.utcnow().isoformat() + "Z"
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = PROGRESS + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(_PROG, fh)
        os.replace(tmp, PROGRESS)        # atomic: a poller never sees half a file
    except Exception:
        pass


def prog_start():
    _PROG["running"] = True
    _PROG["startedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
    _PROG["note"] = ""
    prog("signin", force=True)


def prog_end(ok=True, error=""):
    if _PROG.get("phase") and _PHASE_T0[0]:
        _PROG.setdefault("phaseMs", {})[_PROG["phase"]] = \
            int((time.time() - _PHASE_T0[0]) * 1000)
    _PROG["running"] = False
    _PROG["note"] = error or ""
    _PROG["ok"] = bool(ok)
    prog(force=True)
TEMPLATE  = os.path.join(os.path.dirname(__file__), "template.html")
_LOCK     = threading.Lock()

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------- HTTP session
class Api:
    def __init__(self):
        self.s = requests.Session()
        self.token = None
        self.login()

    def login(self):
        r = self.s.post(f"{BASE}/auth/login",
                        json={"username": USERNAME, "password": PASSWORD},
                        headers={"X-Organization-Id": ORG}, timeout=30)
        r.raise_for_status()
        j = r.json()
        data = j.get("data") or j
        self.token = (data.get("accessToken")
                      or (data.get("tokens") or {}).get("accessToken")
                      or j.get("accessToken"))
        if not self.token:
            raise RuntimeError("login: no accessToken in response: " + str(j)[:200])

    def get(self, path, _retry=True):
        h = {"Authorization": f"Bearer {self.token}", "X-Organization-Id": ORG}
        r = self.s.get(f"{BASE}{path}", headers=h, timeout=60)
        if r.status_code == 401 and _retry:
            self.login()
            return self.get(path, _retry=False)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, None

def pool(items, fn, n=CONC, report=False):
    """as_completed rather than submission order: results land in the same slots
    either way, but progress then reflects work actually finished instead of
    waiting on whichever task happened to be submitted first."""
    out = [None] * len(items)
    total = len(items)
    if report: prog(done=0, total=total, force=True)
    done = 0
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in as_completed(futs):
            i = futs[f]
            try: out[i] = f.result()
            except Exception: out[i] = None
            done += 1
            if report: prog(done=done)
    if report: prog(done=total, force=True)
    return out

# ------------------------------------------------------------- roster + geo
def enumerate_roster(api):
    """Union name-search over the alphabet — reaches every rep incl. the cohort the
    list endpoint silently skips."""
    by_id = {}
    terms = list("abcdefghijklmnopqrstuvwxyz0123456789 ")
    prog("roster", total=len(terms), done=0)
    for _ti, term in enumerate(terms):
        prog(done=_ti, note="%d employees found" % len(by_id))
        for p in range(1, 8):
            st, d = api.get(f"/admin/employees?page={p}&limit=100&search={requests.utils.quote(term)}")
            rows = (d or {}).get("data") or (d or {}).get("employees") or []
            if not rows: break
            for e in rows: by_id[e["_id"]] = e
            if len(rows) < 100: break
    return list(by_id.values())

# ------------------------------------------------------- roster completion
ROSTER_GAP = os.path.join(DATA_DIR, "roster_gap.json")


def known_codes():
    """Every employee code we have independent evidence for, and where it came from.

    These files are reference data, not a source of truth about the app: a code here
    only tells us who to go and ask the API about. The API's answer is what counts —
    if it does not know the person, they are genuinely not in Frontline, and that is
    a finding rather than a failure.
    """
    out = {}

    def add(code, src):
        k = orgnorm(code)
        if not k:
            return
        rec = out.setdefault(k, {"code": str(code).strip(), "src": src})
        if src not in rec["src"]:
            rec["src"] = rec["src"] + "+" + src

    try:
        _org, _ = load_org(os.path.join(BASE_DIR, "bb_org.json"))
        for p in ((_org or {}).get("people") or {}).values():
            # vacancies have synthetic keys and no person behind them
            if not p.get("vacant") and p.get("code"):
                add(p["code"], "org")
    except Exception as e:
        print("known_codes: org file unusable (%s)" % str(e)[:120])
    try:
        for c in (load_hr() or {}):
            add(c, "hr")
    except Exception as e:
        print("known_codes: hr file unusable (%s)" % str(e)[:120])
    return out


def fetch_by_code(api, code):
    """One person, by exact code. Pagination never enters into it.

    Returns the row ONLY on an exact normalised code match. Substring search means
    EC991 also matches EC9919; adopting the wrong neighbour would file one person's
    calls under another person's name, silently and permanently.
    """
    try:
        st, dd = api.get("/admin/employees?page=1&limit=25&search=%s"
                         % requests.utils.quote(str(code)))
        rows = (dd or {}).get("data") or (dd or {}).get("employees") or []
        want = orgnorm(code)
        for e in rows:
            if orgnorm(e.get("employeeCode")) == want and e.get("_id"):
                return e
    except Exception:
        pass
    return None


def complete_roster(api, emps):
    """Fill the gap the search enumeration leaves. Returns (emps, stats).

    Never raises: a roster short by 130 people still renders a report, and a refresh
    that dies here would leave you with nothing at all.
    """
    stats = {"enumerated": len(emps), "known": 0, "asked": 0, "recovered": 0,
             "unresolvedOrg": 0, "unresolvedHr": 0}
    try:
        have = {orgnorm(e.get("employeeCode")) for e in emps if e.get("employeeCode")}
        want = known_codes()
        stats["known"] = len(want)
        missing = sorted((k for k in want if k not in have), key=lambda k: want[k]["code"])
        stats["asked"] = len(missing)
        if not missing:
            _write_gap({"missing": [], "recovered": [], "unresolved": []})
            return emps, stats

        prog(note="%d not returned by search - asking for each by code" % len(missing))
        found = pool([want[k]["code"] for k in missing],
                     lambda c: fetch_by_code(api, c), report=True)

        by_id = {e["_id"]: e for e in emps if e.get("_id")}
        before = len(by_id)
        rec, unres = [], []
        for k, e in zip(missing, found):
            if e:
                e["_viaCode"] = True          # provenance: found only because we asked
                by_id[e["_id"]] = e
                rec.append(want[k]["code"])
            else:
                unres.append({"code": want[k]["code"], "src": want[k]["src"]})
        out = list(by_id.values())
        stats["recovered"] = len(by_id) - before
        stats["unresolvedOrg"] = sum(1 for u in unres if "org" in u["src"])
        stats["unresolvedHr"] = sum(1 for u in unres if u["src"] == "hr")
        _write_gap({"at": datetime.datetime.utcnow().isoformat() + "Z",
                    "recovered": rec, "unresolved": unres})
        print("roster: %d by search, +%d recovered by code, %d still unknown to Frontline"
              % (before, stats["recovered"], len(unres)))
        return out, stats
    except Exception as e:
        # A completion pass that fails must cost nothing. Report the roster we had.
        stats["error"] = str(e)[:200]
        print("complete_roster failed (%s) - continuing with the search roster" % stats["error"])
        return emps, stats


def _write_gap(payload):
    """Codes go to the data disk, not to meta.json: /status has no authentication."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = ROSTER_GAP + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(payload, fh, indent=1)
        os.replace(tmp, ROSTER_GAP)
    except Exception:
        pass


def pagination_probe(api, term="a"):
    """Evidence, not a workaround.

    Ask for page 1 and page 2 of the same search and compare the ids. A healthy
    endpoint returns two disjoint pages; the bug returns the same page twice. Two
    read-only requests, and the answer is a number the backend team can act on.
    """
    out = {"term": term}
    try:
        pages = []
        for p in (1, 2):
            st, dd = api.get("/admin/employees?page=%d&limit=100&search=%s"
                             % (p, requests.utils.quote(term)))
            rows = (dd or {}).get("data") or (dd or {}).get("employees") or []
            pages.append([r.get("_id") for r in rows if r.get("_id")])
            out["page%dCount" % p] = len(rows)
            out["page%dStatus" % p] = st
        a, b = set(pages[0]), set(pages[1])
        out["overlap"] = len(a & b)
        out["newOnPage2"] = len(b - a)
        # only a claim when page 2 actually returned something to judge
        out["repeatsPage1"] = bool(pages[1]) and not (b - a)
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


def geo_flat(api):
    st, d = api.get("/admin/geo-hierarchy")
    flat = {}
    def walk(node, chain):
        u = node.get("unit") or {}
        _id = u.get("_id")
        if _id:
            flat[_id] = {"name": u.get("name"), "level": u.get("level"),
                         "chain": [{"name": c["name"], "level": c["level"]} for c in chain]}
        nc = chain + [{"name": u.get("name"), "level": u.get("level")}]
        for ch in (node.get("children") or []): walk(ch, nc)
    for n in (d or []): walk(n, [])
    return flat

def geo_name(gid, lvl, flat):
    rec = flat.get(gid)
    if not rec: return None
    if rec["level"] == lvl: return rec["name"]
    for c in rec["chain"]:
        if c["level"] == lvl: return c["name"]
    return None

def months_from(start_ym):
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    today = datetime.date.today()
    out = []
    while (y < today.year) or (y == today.year and m <= today.month):
        out.append((m, y)); m += 1
        if m > 12: m = 1; y += 1
    return out

# ------------------------------------------------------------------ store
HR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hr.json")

def load_hr():
    """Organisational HR fields keyed by employee code. Optional — absent file is fine.
    A copy on the data disk (hr.json) overrides the repo copy, so HR can be refreshed
    without a redeploy."""
    for p in (os.path.join(DATA_DIR, "hr.json"), HR_PATH):
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh: return json.load(fh)
        except Exception:
            pass
    return {}

def db():
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("""CREATE TABLE IF NOT EXISTS dayplan(
        id TEXT PRIMARY KEY, empId TEXT, empCode TEXT, date TEXT, vc INTEGER,
        status TEXT, visits_json TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS emp(
        id TEXT PRIMARY KEY, json TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS s1(
        id TEXT PRIMARY KEY, json TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
    return con

# --------------------------------------------------------------- phase B
def phase_b(api, emps, flat):
    """Per-employee assignment + geo + roleMap + docCount + day-plan lists (all months)."""
    role_map = {}
    months = months_from(LIFE_START)
    def one(e):
        rec = {"geo": {}, "roleId": None, "parent": None, "docCount": 0, "dayPlans": []}
        st, d = api.get(f"/admin/employees/{e['_id']}")
        dd = (d or {}).get("data") or d or {}
        aa = dd.get("activeAssignment") or {}
        gids = aa.get("geoIds") or []
        gid = gids[0]["_id"] if gids and gids[0] else None
        rec["geo"] = {"division": geo_name(gid,0,flat), "zone": geo_name(gid,2,flat),
                      "state": geo_name(gid,3,flat), "hq": geo_name(gid,4,flat),
                      "territory": geo_name(gid,5,flat)}
        rid = (aa.get("roleId") or {})
        rec["roleId"] = rid.get("_id"); rec["parent"] = rid.get("parentRoleId")
        if rec["roleId"]:
            role_map[rec["roleId"]] = {"name": e.get("name"), "code": e.get("employeeCode"),
                                       "role": (e.get("designationId") or {}).get("code")}
        st, c = api.get(f"/admin/employees/{e['_id']}/doctors?page=1&limit=1")
        rec["docCount"] = ((c or {}).get("pagination") or {}).get("total") or 0
        for (m, y) in months:
            st, p = api.get(f"/admin/employees/{e['_id']}/day-plans?month={m}&year={y}")
            for x in ((p or {}).get("dayPlans") or []):
                rec["dayPlans"].append({"id": x.get("_id"), "date": (x.get("date") or "")[:10],
                                        "status": x.get("status"), "vc": x.get("visitCount") or 0})
        return (e["_id"], rec)
    res = pool(emps, one, report=True)
    s1 = {r[0]: r[1] for r in res if r}
    return s1, role_map

# --------------------------------------------------------- phase C (incremental)
def _ist(t):
    if not t or ":" not in t: return ""
    hh, mm = t.split(":")[0], t.split(":")[1][:2]
    total = (int(hh)*60 + int(mm) + 330) % 1440
    return f"{total//60:02d}:{total%60:02d}"

def _sstr(x):
    """Frontline returns specialization (and sometimes category) as a list — coerce to a string."""
    if isinstance(x, list): return ", ".join(str(i) for i in x)
    return x or ""

def parse_visits(visits):
    rows = []
    for v in visits:
        en = v.get("entity") or {}; vd = v.get("visitData") or {}
        isDoc = v.get("entityType") == "DOCTOR"
        tm = (v.get("submittedAt") or "")[11:16]
        prods = [[p.get("productName") or "?", int(p.get("rxCount") or 0), int(p.get("quantity") or 0)]
                 for p in (vd.get("products") or [])]
        vrx = sum(p[1] for p in prods)
        sm = sum(int(s.get("quantity") or 0) for s in (vd.get("samples") or []))
        presc = 1 if (any(p.get("isPrescriber") for p in (vd.get("products") or [])) or vrx > 0) else 0
        react = (vd.get("products") or [{}])[0].get("doctorReaction") or "" if vd.get("products") else ""
        loc = v.get("location") or {}
        rows.append({"isDoc": 1 if isDoc else 0, "name": en.get("fullName") or en.get("name") or "",
                     "code": en.get("doctorCode") or en.get("chemistCode") or "",
                     "spec": _sstr(en.get("specialization")), "cat": _sstr(en.get("category")),
                     "clinic": en.get("clinicName") or "", "rx": vrx, "sm": sm, "react": react,
                     "presc": presc, "t": tm, "prods": prods,
                     "lat": (loc.get("lat") or loc.get("latitude") or ""),
                     "lng": (loc.get("lng") or loc.get("longitude") or "")})
    return rows

def phase_c(api, emps, s1, con, win_start, win_end):
    """Fetch detail for day-plans in window that we don't have yet (or whose vc changed)."""
    have = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, vc, status FROM dayplan").fetchall()}
    tasks = []
    for e in emps:
        rec = s1.get(e["_id"])
        if not rec: continue
        for dp in rec["dayPlans"]:
            d = dp["date"]
            if dp["vc"] and win_start <= d <= win_end:
                prev = have.get(dp["id"])
                if prev is None or prev[0] != dp["vc"] or prev[1] != dp["status"]:
                    tasks.append((e["_id"], e.get("employeeCode"), dp))
    def one(t):
        empId, code, dp = t
        st, d = api.get(f"/admin/employees/{empId}/day-plans/{dp['id']}")
        if st != 200: return None
        dd = (d or {}).get("data") or d or {}
        rows = parse_visits(dd.get("visits") or [])
        return (dp["id"], empId, code, dp["date"], dp["vc"], dp["status"], json.dumps(rows, separators=(",", ":")))
    prog("detail", note="%d day plans need fetching" % len(tasks))
    fetched = [r for r in pool(tasks, one, report=True) if r]
    cur = con.cursor()
    cur.executemany("INSERT OR REPLACE INTO dayplan(id,empId,empCode,date,vc,status,visits_json) VALUES(?,?,?,?,?,?,?)", fetched)
    con.commit()
    return len(tasks), len(fetched)

# --------------------------------------------------------------- compute + render
def compute_and_render(con, emps, s1, role_map, win_start, win_end):
    emp_by_id = {e["_id"]: e for e in emps}
    role_of = lambda e: (e.get("designationId") or {}).get("code") or "?"
    TODAY = win_end
    d0 = datetime.date.fromisoformat(win_end)
    L7 = (d0 - datetime.timedelta(days=6)).isoformat()

    # ---- use the window where data ACTUALLY exists, not the ETL scan window ----
    # LIFETIME_START is 2026-01, but Frontline captured nothing until 31 Mar. Counting
    # working days from 1 Jan divided everyone's attendance by 193 days when only 117
    # existed — understating it 1.65x and firing "Low attendance <50%" at reps who had
    # worked ~80% of every day available to them. The scan window stays wide (so earlier
    # data is picked up if it ever appears); only the DENOMINATORS use the real range.
    row = con.execute("SELECT MIN(date), MAX(date) FROM dayplan "
                      "WHERE date BETWEEN ? AND ? AND vc > 0", (win_start, win_end)).fetchone()
    data_start = (row and row[0]) or win_start
    data_end   = (row and row[1]) or win_end
    if data_start < win_start: data_start = win_start
    if data_end   > win_end:   data_end   = win_end

    def workdays_between(a_iso, b_iso):
        """Every day except Sunday, matching the report's own definition."""
        a2 = datetime.date.fromisoformat(a_iso); b2 = datetime.date.fromisoformat(b_iso)
        n = 0
        while a2 <= b2:
            if a2.weekday() != 6: n += 1
            a2 += datetime.timedelta(days=1)
        return max(1, n)

    wd = workdays_between(data_start, win_end)
    span_days = max(1, (d0 - datetime.date.fromisoformat(data_start)).days + 1)

    # ---- org & territory (optional enrichment) ----------------------------------
    ORG, ORG_ISSUES = load_org(os.path.join(BASE_DIR, "bb_org.json"))
    ORG_PEOPLE = ORG.get("people", {}) if ORG else {}

    AGG = {}; DAILY = {}; PROD = {}; SPEC = {}; CAT = {}; REACT = {}
    def A(i):
        if i not in AGG:
            AGG[i] = dict(v=0,dv=0,cv=0,uniq=set(),rxd=set(),rx=0,sm=0,pq=0,days=set(),dc={},last="",
                          cluster=0,dcDate={},dcRx={},rxL7=0,spanSum=0,spanDays=0,reactPos=0,reactAny=0,
                          firstSum=0,firstDays=0,scDoc=0,legSum=0)
        return AGG[i]
    calls_by_code = {}   # empCode -> [ per-visit rows ] (the only full-size structure)
    q = con.execute("SELECT empId, empCode, date, visits_json FROM dayplan WHERE date>=? AND date<=?", (win_start, win_end))
    for empId, empCode, date, vj in q:
        visits = json.loads(vj)
        ag = A(empId); ag["days"].add(date)
        if date > ag["last"]: ag["last"] = date
        day = DAILY.setdefault(date, dict(v=0,rx=0,dv=0,cv=0)); times = []
        for v in visits:
            ag["v"] += 1; day["v"] += 1
            if v["t"] and ":" in v["t"]:
                try: times.append(int(v["t"][:2])*60 + int(v["t"][3:5]))
                except Exception: pass
            isDoc = v["isDoc"]
            spec = _sstr(v["spec"]); cat = _sstr(v["cat"])   # tolerate list-valued specialization
            if isDoc: ag["dv"] += 1; day["dv"] += 1
            else: ag["cv"] += 1; day["cv"] += 1
            docId = v["code"] or ("__" + v["name"])
            vrx = v["rx"]; ag["rx"] += vrx
            for pn, rc, qy in v["prods"]:
                ag["pq"] += qy; pr = PROD.setdefault(pn, dict(rx=0, q=0)); pr["rx"] += rc; pr["q"] += qy
            ag["sm"] += v["sm"]; day["rx"] += vrx
            if date >= L7: ag["rxL7"] += vrx
            if isDoc and docId:
                ag["uniq"].add(docId); ag["dc"][docId] = ag["dc"].get(docId,0)+1
                ag["dcRx"][docId] = ag["dcRx"].get(docId,0)+vrx
                if docId not in ag["dcDate"] or date < ag["dcDate"][docId]: ag["dcDate"][docId] = date
                if vrx > 0: ag["rxd"].add(docId)
                if vrx > 0:
                    SPEC[spec or "?"] = SPEC.get(spec or "?",0)+vrx
                    CAT[cat or "?"]   = CAT.get(cat or "?",0)+vrx
                if cat == "supercore": ag["scDoc"] += 1
                rx_react = v["react"]
                if rx_react:
                    REACT[rx_react] = REACT.get(rx_react,0)+1; ag["reactAny"] += 1
                    if rx_react in ("Positive","Committed"): ag["reactPos"] += 1
            prod_str = "|".join(f"{p[0]}~{p[1]}" if p[1] else p[0] for p in v["prods"])
            # single canonical per-visit row, in the shape the report consumes
            calls_by_code.setdefault(empCode, []).append(
                [date, _ist(v["t"]), 1 if isDoc else 0, v["name"], v["code"], spec, cat,
                 v["clinic"], vrx, v["presc"], v["react"], prod_str, v["sm"],
                 (round(float(v["lat"]), 5) if v["lat"] else ""),
                 (round(float(v["lng"]), 5) if v["lng"] else "")])
        if times:
            times.sort(); ist = (times[0]+330) % 1440; ag["firstSum"] += ist; ag["firstDays"] += 1
        if len(times) >= 2:
            ag["spanSum"] += times[-1]-times[0]; ag["spanDays"] += 1; ag["legSum"] += len(times)-1
        if len(times) >= 4:
            mx = 1
            for i in range(len(times)):
                c = 1; j = i+1
                while j < len(times) and times[j]-times[i] <= 30: c += 1; j += 1
                mx = max(mx, c)
            ag["cluster"] = max(ag["cluster"], mx)

    R = []
    for e in emps:
        a_ = AGG.get(e["_id"]); s = s1.get(e["_id"]) or {"geo": {}}; g = s.get("geo") or {}
        dc = s.get("docCount") or 0; mgr = role_map.get(s.get("parent"))
        base = dict(c=e.get("employeeCode"), n=e.get("name"), r=role_of(e), di=g.get("division") or "",
                    zn=g.get("zone") or "", st=g.get("state") or "—", hq=g.get("hq") or "—",
                    mg=mgr["name"] if mgr else "—", mgc=(mgr.get("code") or "") if mgr else "",
                    da=dc, du=dc)
        if not a_:
            R.append({**base, "attFrom":data_start,"attWd":wd,"attSrc":"window",
                      "vis":0,"dv":0,"cv":0,"ud":0,"cov":0,"cpd":0,"rx":0,"rpc":0,"rxPerDoc":0,
                      "rxPerDay":0,"rxConv":0,"rxD":0,"s2r":0,"sm":0,"pq":0,"tp":"None","ob":0,"zeroRx":0,
                      "pi":"","att":0,"repc":0,"cl":0,"rec":"","newd":0,"mom":"","chsh":0,"fhrs":0,"tdc":0,
                      "rpct":"","ds":"","dsMin":99999,"scf":0,"mpc":"","ndc":"","newd7":0,
                      "fl":["Silent (no activity)"],"sp":[]}); continue
        uniq=len(a_["uniq"]); rxd=len(a_["rxd"]); days=len(a_["days"])
        repeat=sum(1 for k in a_["dc"] if a_["dc"][k]>=2)
        newd=0; newdRx=0
        for k in a_["dcDate"]:
            if a_["dcDate"][k] >= L7:
                newd += 1
                if a_["dcRx"].get(k,0) > 0: newdRx += 1
        maxDocRx = max(a_["dcRx"].values()) if a_["dcRx"] else 0
        rec = (d0 - datetime.date.fromisoformat(a_["last"])).days if a_["last"] else ""
        dsMin = a_["firstSum"]/a_["firstDays"] if a_["firstDays"] else 99999
        # ---- this rep's own attendance denominator ----
        # A rep who joined in July cannot be marked absent for April. Prefer the org
        # file's date of joining; fall back to their first recorded activity, which
        # is a lower bound on when they started. Both are clamped to the data window.
        _op = ORG_PEOPLE.get(orgnorm(e.get("employeeCode"))) if ORG_PEOPLE else None
        _doj = (_op or {}).get("doj") or ""
        _first = min(a_["days"]) if a_["days"] else ""
        _from = data_start
        for _cand in (_doj, _first):
            if _cand and _cand > _from: _from = _cand
        if _from > data_end: _from = data_end
        _wd = workdays_between(_from, win_end)
        _att_src = "doj" if (_doj and _doj >= data_start and _doj == _from) else (
                   "first activity" if (_first and _first == _from and _from > data_start)
                   else "window")
        r1 = lambda x: round(x,1); r2 = lambda x: round(x,2)
        row = {**base, "vis":a_["v"],"dv":a_["dv"],"cv":a_["cv"],"ud":uniq,
               "cov":r1(100*uniq/dc) if dc else 0,"cpd":r1(a_["v"]/days) if days else 0,"rx":a_["rx"],
               "rpc":r2(a_["rx"]/a_["v"]) if a_["v"] else 0,"rxPerDoc":r2(a_["rx"]/uniq) if uniq else 0,
               "rxPerDay":r2(a_["rx"]/days) if days else 0,"rxConv":r1(100*rxd/uniq) if uniq else 0,"rxD":rxd,
               "s2r":r2(a_["sm"]/a_["rx"]) if a_["rx"] else (99 if a_["sm"]>0 else 0),"sm":a_["sm"],"pq":a_["pq"],
               "tp":"None","ob":1 if days>0 else 0,
               "zeroRx":1 if (role_of(e)=="BO" and a_["v"]>0 and a_["rx"]==0) else 0,
               "att":r1(min(100.0, 100*days/_wd)),"attFrom":_from,"attWd":_wd,"attSrc":_att_src,
               "repc":r1(100*repeat/uniq) if uniq else 0,"cl":a_["cluster"],"rec":rec,
               "newd":newd,"mom":(round(a_["rxL7"]/(a_["rx"]*7/span_days)*100) if a_["rx"]>0 else ""),
               "chsh":r1(100*a_["cv"]/(a_["dv"]+a_["cv"])) if (a_["dv"]+a_["cv"]) else 0,
               "fhrs":r1(a_["spanSum"]/a_["spanDays"]/60) if a_["spanDays"] else 0,
               "tdc":r1(100*maxDocRx/a_["rx"]) if a_["rx"] else 0,
               "rpct":round(100*a_["reactPos"]/a_["reactAny"]) if a_["reactAny"] else "",
               "dsMin":dsMin,"ds":(f"{int(round(dsMin))//60:02d}:{int(round(dsMin))%60:02d}" if dsMin!=99999 else ""),
               "scf":round(100*a_["scDoc"]/a_["dv"]) if a_["dv"] else 0,
               "mpc":round(a_["spanSum"]/a_["legSum"]) if a_["legSum"] else "",
               "ndc":round(100*newdRx/newd) if newd else "","newd7":newd,"fl":[],"sp":[]}
        R.append(row)

    bo = [x for x in R if x["r"]=="BO" and x["vis"]>0]
    def pct(arr, key):
        s = sorted(x[key] for x in arr)
        def f(v):
            lo,hi=0,len(s)
            while lo<hi:
                m=(lo+hi)//2
                if s[m]<v: lo=m+1
                else: hi=m
            return round(100*lo/(len(s)-1)) if len(s)>1 else 0
        return f
    pC,pR,pV,pA = pct(bo,"cpd"),pct(bo,"rpc"),pct(bo,"cov"),pct(bo,"att")
    for x in R:
        x["pi"] = round(.30*pC(x["cpd"])+.25*pR(x["rpc"])+.30*pV(x["cov"])+.15*pA(x["att"])) if (x["r"]=="BO" and x["vis"]>0) else ""
    # per-rep specializations
    repSp = {}
    for code, vs in calls_by_code.items():
        s = repSp.setdefault(code, set())
        for c in vs:
            if c[2] and c[5]: s.add(c[5])
    for x in R: x["sp"] = sorted(repSp.get(x["c"], []))
    del repSp

    # ---- per-rep monthly series (drives the trend chart in the profile) ----
    # [[YYYY-MM, visits, rx, doctorVisits], ...] — two ints per rep-month.
    # Deliberately NOT tracking distinct doctors per month: that needed a set of doctor
    # codes per rep per month and cost ~70 MB peak for a figure nothing renders.
    for x in R:
        mser = {}
        for c in calls_by_code.get(x["c"], []):
            k = c[0][:7]
            e = mser.get(k)
            if e is None: e = mser[k] = [0, 0, 0]
            e[0] += 1; e[1] += c[8]
            if c[2]: e[2] += 1
        x["ms"] = [[k, v[0], v[1], v[2]] for k, v in sorted(mser.items())]

    # ---- peer ranks within the same designation ----
    # A raw number is meaningless without context: "4,683 Rx" reads very differently
    # as #5 of 487 than as #300 of 487. Rank 1 = best. Ties share the better rank.
    RANKED = ["rx", "vis", "ud", "rxConv", "cov", "pi", "cpd", "rpc", "rxPerDoc", "att"]
    by_role = {}
    for x in R: by_role.setdefault(x["r"], []).append(x)
    for role, grp in by_role.items():
        n = len(grp)
        for m in RANKED:
            vals = sorted(((x.get(m) or 0) for x in grp), reverse=True)
            pos = {}
            for i, v in enumerate(vals):
                if v not in pos: pos[v] = i + 1
            for x in grp:
                x.setdefault("rk", {})[m] = [pos[(x.get(m) or 0)], n]
    del by_role
    # flags
    for x in R:
        f=[]
        if x["r"]=="BO":
            if x["vis"]==0: f.append("Silent (no activity)")
            else:
                if x["rx"]==0: f.append("Zero Rx despite visits")
                if x["rec"]!="" and x["rec"]>=3: f.append("Silent 3+ days")
                if x["att"]<50: f.append("Low attendance <50%")
                if x["du"]>0 and x["cov"]<25: f.append("Low coverage <25%")
                if (x["rx"]>0 and x["s2r"]>4) or (x["sm"]>0 and x["rx"]==0): f.append("Sample-heavy / low Rx")
                if x["cl"]>=10: f.append("Clustered entries (audit)")
                if x["ud"]>=10 and x["repc"]<10: f.append("Weak repeat coverage")
                if x["mom"]!="" and x["mom"]<50: f.append("Rx declining")
                if x["tdc"]>=60 and x["rx"]>=10: f.append("Single-doctor dependent")
                if x["mpc"]!="" and x["mpc"]<8 and x["dv"]>=20: f.append("Rushed calls (audit)")
                if x["newd7"]>=5 and x["ndc"]!="" and x["ndc"]<15: f.append("New doctors not converting")
        x["fl"]=f

    # rollups
    def by_state():
        st={}
        for r in R:
            if r["r"]!="BO": continue
            s=st.setdefault(r["st"],dict(state=r["st"],reps=0,active=0,visits=0,rx=0,docMet=0,rxDoctors=0,samples=0))
            s["reps"]+=1; s["active"]+=1 if r["vis"]>0 else 0; s["visits"]+=r["vis"]; s["rx"]+=r["rx"]
            s["docMet"]+=r["ud"]; s["rxDoctors"]+=r["rxD"]; s["samples"]+=r["sm"]
        return sorted(({**s,"conv":round(100*s["rxDoctors"]/s["docMet"],1) if s["docMet"] else 0} for s in st.values()), key=lambda x:-x["rx"])
    STATES=by_state()
    PRODUCTS=sorted(({"name":n,"rx":v["rx"],"qty":v["q"]} for n,v in PROD.items()), key=lambda x:-x["rx"])
    SPECS=sorted(([n,v] for n,v in SPEC.items()), key=lambda x:-x[1])
    CATS=sorted(([n,v] for n,v in CAT.items()), key=lambda x:-x[1])
    DAYS=sorted(([d,v["v"],v["dv"],v["cv"],v["rx"]] for d,v in DAILY.items()))
    # doctor master + daily + top docs + calls-by-rep
    dm={}; docm={}
    for empCode, vs in calls_by_code.items():
        for c in vs:
            k=empCode+"|"+c[0]; e=dm.setdefault(k,dict(code=empCode,date=c[0],calls=0,dr=0,chem=0,rx=0,sm=0))
            e["calls"]+=1; e["dr"]+=1 if c[2] else 0; e["chem"]+=0 if c[2] else 1; e["rx"]+=c[8]; e["sm"]+=c[12]
            if c[2]:
                code=c[4] or ("__"+c[3])
                dc=docm.setdefault(code,dict(name=c[3],code=c[4],spec=c[5],cat=c[6],clinic=c[7],
                                             rx=0,vis=0,byRep={},sm=0,presc=0,first=c[0],last=c[0],react=""))
                dc["rx"]+=c[8]; dc["vis"]+=1; dc["byRep"][empCode]=dc["byRep"].get(empCode,0)+1
                dc["sm"]+=c[12]
                if c[9]: dc["presc"]=1
                if c[0]<dc["first"]: dc["first"]=c[0]
                if c[0]>=dc["last"]: dc["last"]=c[0]; dc["react"]=c[10] or dc["react"]
    D_daily=[[d["code"],d["date"],d["calls"],d["dr"],d["chem"],d["rx"],d["sm"]] for d in dm.values()]
    docArr=[]
    for dc in docm.values():
        best=max(dc["byRep"].items(), key=lambda kv:kv[1])[0] if dc["byRep"] else None
        docArr.append((dc,best))
    st_by_code={r["c"]:r["st"] for r in R}
    nm_by_code={r["c"]:r["n"]  for r in R}
    hq_by_code={r["c"]:r["hq"] for r in R}
    # Doctor master. Positions 0,1,2,6,7,9,12 are unchanged (other views depend on them);
    # the slots that used to be hardcoded "" now carry real per-doctor facts, and 13-16 are new.
    #  0 code  1 name  2 spec  3 rx  4 visits  5 prescriber  6 clinic  7 category  8 hq
    #  9 state 10 lastSeen 11 firstSeen 12 repCode 13 repName 14 repsCovering 15 samples 16 lastReaction
    D_docs=[[dc["code"],dc["name"],dc["spec"],dc["rx"],dc["vis"],dc["presc"],dc["clinic"],dc["cat"],
             hq_by_code.get(best,""),st_by_code.get(best,""),dc["last"],dc["first"],best or "",
             nm_by_code.get(best,""),len(dc["byRep"]),dc["sm"],dc["react"]] for dc,best in docArr]
    D_topDocs=sorted(([dc["name"],dc["code"],dc["spec"],dc["cat"],dc["clinic"],dc["rx"],dc["vis"],best or "","",st_by_code.get(best,"")] for dc,best in docArr), key=lambda x:-x[5])[:600]
    dsb={}
    for d in D_docs:
        if d[9]: dsb[d[9]]=dsb.get(d[9],0)+1
    D_docsByState=sorted(dsb.items(), key=lambda x:-x[1])
    abo=sorted([x for x in R if x["r"]=="BO" and x["vis"]>0], key=lambda x:-x["rx"])
    n20=max(1,round(len(abo)*0.2)); t20=sum(x["rx"] for x in abo[:n20]); boRx=sum(x["rx"] for x in abo)
    totRx=sum(r["rx"] for r in R); docMet=sum(r["ud"] for r in R); rxDoctors=sum(r["rxD"] for r in R)
    D_rx=dict(totRx=totRx,metDoctors=docMet,rxDoctors=rxDoctors,pareto=round(100*t20/boRx) if boRx else 0,
              paretoN=n20,bySpec=[[x[0],x[1]] for x in SPECS],prod=[[p["name"],p["qty"],p["rx"]] for p in PRODUCTS],
              byCat=[[x[0],x[1]] for x in CATS],topDocs=D_topDocs)
    def mgr_roll():
        mg={}
        for r in R:
            if r["r"]!="BO": continue
            m=mg.setdefault(r["mg"] or "—",dict(name=r["mg"] or "—",team=0,active=0,vis=0,rx=0,zeroRx=0,_cov=[],_pi=[]))
            m["team"]+=1; m["active"]+=1 if r["vis"]>0 else 0; m["vis"]+=r["vis"]; m["rx"]+=r["rx"]; m["zeroRx"]+=r["zeroRx"]
            if r["du"]>0: m["_cov"].append(r["cov"])
            if r["pi"]!="": m["_pi"].append(r["pi"])
        return sorted(({"name":m["name"],"team":m["team"],"active":m["active"],"actPct":round(100*m["active"]/m["team"]),
                        "vis":m["vis"],"rx":m["rx"],"zeroRx":m["zeroRx"],
                        "cov":round(sum(m["_cov"])/len(m["_cov"]),1) if m["_cov"] else 0,
                        "pi":round(sum(m["_pi"])/len(m["_pi"])) if m["_pi"] else 0} for m in mg.values()), key=lambda x:-x["rx"])
    def zone_roll():
        zn={}
        for r in R:
            z=zn.setdefault(r["zn"] or "—",dict(name=r["zn"] or "—",reps=0,active=0,vis=0,rx=0,zeroRx=0,_cov=[]))
            z["reps"]+=1; z["active"]+=1 if r["vis"]>0 else 0; z["vis"]+=r["vis"]; z["rx"]+=r["rx"]; z["zeroRx"]+=r["zeroRx"]
            if r["r"]=="BO" and r["du"]>0: z["_cov"].append(r["cov"])
        return sorted(({"name":z["name"],"reps":z["reps"],"active":z["active"],"actPct":round(100*z["active"]/z["reps"]),
                        "vis":z["vis"],"rx":z["rx"],"zeroRx":z["zeroRx"],
                        "cov":round(sum(z["_cov"])/len(z["_cov"]),1) if z["_cov"] else 0} for z in zn.values()), key=lambda x:-x["rx"])
    # calls_by_code was built during the scan — no second copy needed
    # HR roster (organisational fields only) — matched on employee code, case/space-insensitive.
    hr_all, hr_used, hr_missing = load_hr(), {}, 0
    if hr_all:
        idx = {re.sub(r'[^A-Z0-9]', '', k.upper()): v for k, v in hr_all.items()}
        for x in R:
            rec = idx.get(re.sub(r'[^A-Z0-9]', '', str(x["c"]).upper()))
            if rec: hr_used[x["c"]] = rec
            else:   hr_missing += 1

    # ---- attach org & territory to each rep -------------------------------------
    org_matched = 0
    for x in R:
        p = ORG_PEOPLE.get(orgnorm(x["c"])) if ORG_PEOPLE else None
        if p and not p["vacant"]:
            org_matched += 1
            x["terr"] = p["terr"]; x["doj"] = p["doj"]; x["lvl"] = p["lvl"]
            x["stf"] = p["stf"]; x["opk"] = p["key"]; x["opp"] = p["parent"]
            x["opins"] = len(p["pins"])
            if p["hq"] and (not x.get("hq") or x["hq"] == "—"): x["hq"] = p["hq"]
            if p["st"] and (not x.get("st") or x["st"] == "—"): x["st"] = p["st"]
        else:
            x["terr"] = ""; x["doj"] = ""; x["lvl"] = -1; x["stf"] = ""
            x["opk"] = ""; x["opp"] = ""; x["opins"] = 0

    ORG_OUT = {}
    if ORG_PEOPLE:
        cov = match_roster(ORG, [x["c"] for x in R])
        rx_by_key = {x["opk"]: x["c"] for x in R if x.get("opk")}
        ORG_OUT = dict(
            # [key, code, name, staffType, level, territory, hq, state, parentKey,
            #  doj, vacant, pincodeCount, rosterCode]
            people=[[p["key"], p["code"], p["name"], p["stf"], p["lvl"], p["terr"],
                     p["hq"], p["st"], p["parent"], p["doj"], 1 if p["vacant"] else 0,
                     len(p["pins"]), rx_by_key.get(p["key"], "")]
                    for p in ORG_PEOPLE.values()],
            vac=[[ORG_PEOPLE[k]["key"], ORG_PEOPLE[k]["terr"], ORG_PEOPLE[k]["hq"],
                  ORG_PEOPLE[k]["st"], ORG_PEOPLE[k]["parent"],
                  (ORG_PEOPLE.get(ORG_PEOPLE[k]["parent"]) or {}).get("name", ""),
                  ORG_PEOPLE[k]["pins"]]
                 for k in ORG.get("vacancies", [])],
            cov=dict(matched=cov["matched"], rate=cov["rate"],
                     rosterOnly=cov["rosterOnly"], orgOnly=cov["orgOnly"]),
            meta=ORG.get("meta", {}), issues=ORG.get("issues", []),
            notes=ORG.get("notes", []))
        print("[org] %d of %d reps placed (%.1f%%), %d vacancies, %d issues"
              % (cov["matched"], len(R), cov["rate"], len(ORG.get("vacancies", [])),
                 len(ORG.get("issues", []))))
    else:
        print("[org] no org file — territory, DOJ and the org spine are unavailable")
        for i in ORG_ISSUES[:3]: print("[org]  ", i)

    label = f"{data_start} → {data_end} · {len(R)}-rep roster"
    D = dict(label=label, gen=datetime.date.today().isoformat(),
             dataStart=data_start, dataEnd=data_end, workDays=wd,
             rx=D_rx, reps=R, daily=D_daily, docs=D_docs,
             mgrScore=mgr_roll(), zoneScore=zone_roll(), docsByState=D_docsByState, calls=calls_by_code,
             hr=hr_used, org=ORG_OUT)
    # ---- memory-frugal encode ----------------------------------------------
    # Previously this held ~4 full copies at once (CALLS, the JSON string, the gzip
    # bytes, the final HTML string) which OOM-kills a small instance on lifetime data.
    # Now: free the intermediates, stream JSON -> gzip, and stream the HTML to disk.
    tot_visits = sum(r["vis"] for r in R)
    del dm, docm, docArr
    gc.collect()

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        for chunk in json.JSONEncoder(separators=(",", ":")).iterencode(D):
            gz.write(chunk.encode("utf-8"))
    del D
    gc.collect()
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    del buf
    gc.collect()

    tmp = REPORT + ".tmp"
    with open(TEMPLATE, encoding="utf-8") as fh: tpl = fh.read()
    head, _, tail = tpl.partition("__DATA_MARKER__")
    assert _, "template is missing __DATA_MARKER__"
    size = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(head); fh.write(b64); fh.write(tail)
        size = len(head) + len(b64) + len(tail)
    os.replace(tmp, REPORT)
    del b64, tpl, head, tail
    gc.collect()
    return dict(reps=len(R), totRx=totRx, totVisits=tot_visits, docMet=docMet,
                activeBO=len(bo), conv=round(100*rxDoctors/docMet,1) if docMet else 0,
                mb=round(size/1048576, 2),
                hrRecords=len(hr_all), hrMatched=len(hr_used), hrUnmatched=hr_missing)

# ------------------------------------------------------------------ orchestrate
def rerender_only():
    """Re-render report.html from the cached store WITHOUT hitting the API.
    Used when only the template/UI changed, so a UI deploy is instant."""
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    t0 = time.time()
    try:
        con = db()
        row = con.execute("SELECT v FROM kv WHERE k='roster'").fetchone()
        s1r = con.execute("SELECT v FROM kv WHERE k='s1'").fetchone()
        rmr = con.execute("SELECT v FROM kv WHERE k='rolemap'").fetchone()
        if not (row and s1r):
            return {"ok": False, "error": "no cached roster yet — run a full refresh first"}
        emps = json.loads(row[0]); s1 = json.loads(s1r[0]); role_map = json.loads(rmr[0]) if rmr else {}
        win_start = LIFE_START + "-01"
        win_end = datetime.date.today().isoformat()
        stats = compute_and_render(con, emps, s1, role_map, win_start, win_end)
        meta = {"ok": True, "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
                "durationSec": round(time.time() - t0, 1), "roster": len(emps),
                "rerenderOnly": True, **stats}
        with open(META, "w") as fh: json.dump(meta, fh)
        return meta
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        _LOCK.release()

def run_etl():
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "already running"}
    t0 = time.time()
    try:
        prog_start()
        api = Api()
        con = db()
        emps = enumerate_roster(api)
        # The search enumeration is a workaround for a broken list endpoint and
        # inherits its pagination bug. Ask directly for anyone it did not return.
        emps, roster_fill = complete_roster(api, emps)
        roster_fill["pagination"] = pagination_probe(api)
        prog("geo", note="%d employees" % len(emps))
        flat = geo_flat(api)
        prog("dayplans", note="%d employees" % len(emps))
        s1, role_map = phase_b(api, emps, flat)
        # persist roster/s1/rolemap for fast re-render if needed
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('roster', ?)", (json.dumps(emps),))
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('s1', ?)", (json.dumps(s1),))
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('rolemap', ?)", (json.dumps(role_map),))
        con.commit()
        win_start = LIFE_START + "-01"
        win_end   = datetime.date.today().isoformat()
        seen, fetched = phase_c(api, emps, s1, con, win_start, win_end)
        prog("compute", note="%d day plans in window, %d newly fetched" % (seen, fetched))
        stats = compute_and_render(con, emps, s1, role_map, win_start, win_end)
        meta = {"ok": True, "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
                "durationSec": round(time.time() - t0, 1), "roster": len(emps),
                "dayPlansInWindow": seen, "dayPlansFetchedThisRun": fetched,
                # counts only: /status is unauthenticated, so no employee codes here.
                "rosterFill": roster_fill,
                "phaseMs": dict(_PROG.get("phaseMs") or {}), **stats}
        prog_end(True)
        meta["phaseMs"] = dict(_PROG.get("phaseMs") or {})
        with open(META, "w") as fh: json.dump(meta, fh)
        return meta
    except Exception as e:
        meta = {"ok": False, "error": str(e), "at": datetime.datetime.utcnow().isoformat() + "Z"}
        try:
            with open(META, "w") as fh: json.dump(meta, fh)
        except Exception: pass
        prog_end(False, str(e)[:200])
        return meta
    finally:
        _LOCK.release()

if __name__ == "__main__":
    # Run as a SUBPROCESS from the web service (see app.py). Two reasons:
    #  1. GIL — the compute phase is CPU-bound; in-process it starved the health-check
    #     thread and Render killed the instance ("health check timed out after 5s").
    #  2. Memory — the peak lives in a short-lived child that exits and returns every
    #     byte to the OS, instead of bloating the long-lived gunicorn worker.
    if "--rerender" in sys.argv:
        print(json.dumps(rerender_only(), indent=2))
    else:
        print(json.dumps(run_etl(), indent=2))
