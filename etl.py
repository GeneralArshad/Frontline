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
import os, json, gzip, base64, time, sqlite3, datetime, threading, sys
import requests
from concurrent.futures import ThreadPoolExecutor

BASE      = os.environ.get("FRONTLINE_BASE", "https://hive-frontline-backend.com")
ORG       = os.environ.get("FRONTLINE_ORG_ID", "")
EMAIL     = os.environ.get("FRONTLINE_SVC_EMAIL", "")
PASSWORD  = os.environ.get("FRONTLINE_SVC_PASSWORD", "")
LIFE_START= os.environ.get("LIFETIME_START", "2026-01")            # YYYY-MM
CONC      = int(os.environ.get("ETL_CONCURRENCY", "8"))
DATA_DIR  = os.environ.get("DATA_DIR", "./data")
DB_PATH   = os.path.join(DATA_DIR, "frontline.db")
REPORT    = os.path.join(DATA_DIR, "report.html")
META      = os.path.join(DATA_DIR, "meta.json")
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
                        json={"email": EMAIL, "password": PASSWORD},
                        headers={"X-Organization-Id": ORG}, timeout=30)
        r.raise_for_status()
        j = r.json()
        self.token = j.get("accessToken") or (j.get("data") or {}).get("accessToken") \
                     or (j.get("tokens") or {}).get("accessToken")
        if not self.token:
            raise RuntimeError("login: no accessToken in response")

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

def pool(items, fn, n=CONC):
    out = [None] * len(items)
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in futs:
            i = futs[f]
            try: out[i] = f.result()
            except Exception: out[i] = None
    return out

# ------------------------------------------------------------- roster + geo
def enumerate_roster(api):
    """Union name-search over the alphabet — reaches every rep incl. the cohort the
    list endpoint silently skips."""
    by_id = {}
    terms = list("abcdefghijklmnopqrstuvwxyz0123456789 ")
    for term in terms:
        for p in range(1, 8):
            st, d = api.get(f"/admin/employees?page={p}&limit=100&search={requests.utils.quote(term)}")
            rows = (d or {}).get("data") or (d or {}).get("employees") or []
            if not rows: break
            for e in rows: by_id[e["_id"]] = e
            if len(rows) < 100: break
    return list(by_id.values())

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
    res = pool(emps, one)
    s1 = {r[0]: r[1] for r in res if r}
    return s1, role_map

# --------------------------------------------------------- phase C (incremental)
def _ist(t):
    if not t or ":" not in t: return ""
    hh, mm = t.split(":")[0], t.split(":")[1][:2]
    total = (int(hh)*60 + int(mm) + 330) % 1440
    return f"{total//60:02d}:{total%60:02d}"

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
                     "spec": en.get("specialization") or "", "cat": en.get("category") or "",
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
    fetched = [r for r in pool(tasks, one) if r]
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
    # working days (non-Sundays) in window
    a = datetime.date.fromisoformat(win_start); wd = 0
    while a <= d0:
        if a.weekday() != 6: wd += 1
        a += datetime.timedelta(days=1)
    span_days = max(1, (d0 - datetime.date.fromisoformat(win_start)).days + 1)

    AGG = {}; DAILY = {}; PROD = {}; SPEC = {}; CAT = {}; REACT = {}
    def A(i):
        if i not in AGG:
            AGG[i] = dict(v=0,dv=0,cv=0,uniq=set(),rxd=set(),rx=0,sm=0,pq=0,days=set(),dc={},last="",
                          cluster=0,dcDate={},dcRx={},rxL7=0,spanSum=0,spanDays=0,reactPos=0,reactAny=0,
                          firstSum=0,firstDays=0,scDoc=0,legSum=0)
        return AGG[i]
    CALLS = []  # for rollups (doctor master / daily / roster)
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
                    SPEC[v["spec"] or "?"] = SPEC.get(v["spec"] or "?",0)+vrx
                    CAT[v["cat"] or "?"]   = CAT.get(v["cat"] or "?",0)+vrx
                if v["cat"] == "supercore": ag["scDoc"] += 1
                re = v["react"]
                if re:
                    REACT[re] = REACT.get(re,0)+1; ag["reactAny"] += 1
                    if re in ("Positive","Committed"): ag["reactPos"] += 1
            prod_str = "|".join(f"{p[0]}~{p[1]}" if p[1] else p[0] for p in v["prods"])
            CALLS.append([empCode, date, _ist(v["t"]), isDoc, v["name"], v["code"], v["spec"],
                          v["cat"], v["clinic"], vrx, v["presc"], v["react"], prod_str, v["sm"],
                          v["lat"], v["lng"]])
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
                    mg=mgr["name"] if mgr else "—", da=dc, du=dc)
        if not a_:
            R.append({**base, "vis":0,"dv":0,"cv":0,"ud":0,"cov":0,"cpd":0,"rx":0,"rpc":0,"rxPerDoc":0,
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
        r1 = lambda x: round(x,1); r2 = lambda x: round(x,2)
        row = {**base, "vis":a_["v"],"dv":a_["dv"],"cv":a_["cv"],"ud":uniq,
               "cov":r1(100*uniq/dc) if dc else 0,"cpd":r1(a_["v"]/days) if days else 0,"rx":a_["rx"],
               "rpc":r2(a_["rx"]/a_["v"]) if a_["v"] else 0,"rxPerDoc":r2(a_["rx"]/uniq) if uniq else 0,
               "rxPerDay":r2(a_["rx"]/days) if days else 0,"rxConv":r1(100*rxd/uniq) if uniq else 0,"rxD":rxd,
               "s2r":r2(a_["sm"]/a_["rx"]) if a_["rx"] else (99 if a_["sm"]>0 else 0),"sm":a_["sm"],"pq":a_["pq"],
               "tp":"None","ob":1 if days>0 else 0,
               "zeroRx":1 if (role_of(e)=="BO" and a_["v"]>0 and a_["rx"]==0) else 0,
               "att":r1(100*days/wd),"repc":r1(100*repeat/uniq) if uniq else 0,"cl":a_["cluster"],"rec":rec,
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
    for c in CALLS:
        if c[3] and c[6]: repSp.setdefault(c[0], set()).add(c[6])
    for x in R: x["sp"] = sorted(repSp.get(x["c"], []))
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
    for c in CALLS:
        k=c[0]+"|"+c[1]; d=dm.setdefault(k,dict(code=c[0],date=c[1],calls=0,dr=0,chem=0,rx=0,sm=0))
        d["calls"]+=1; d["dr"]+=1 if c[3] else 0; d["chem"]+=0 if c[3] else 1; d["rx"]+=c[9]; d["sm"]+=c[13]
        if c[3]:
            code=c[5] or ("__"+c[4]); dc=docm.setdefault(code,dict(name=c[4],code=c[5],spec=c[6],cat=c[7],clinic=c[8],rx=0,vis=0,byRep={}))
            dc["rx"]+=c[9]; dc["vis"]+=1; dc["byRep"][c[0]]=dc["byRep"].get(c[0],0)+1
    D_daily=[[d["code"],d["date"],d["calls"],d["dr"],d["chem"],d["rx"],d["sm"]] for d in dm.values()]
    docArr=[]
    for dc in docm.values():
        best=max(dc["byRep"].items(), key=lambda kv:kv[1])[0] if dc["byRep"] else None
        docArr.append((dc,best))
    st_by_code={r["c"]:r["st"] for r in R}
    D_docs=[[dc["code"],dc["name"],dc["spec"],"","","",dc["clinic"],dc["cat"],"",st_by_code.get(best,""),"","",best or "", ""] for dc,best in docArr]
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
    calls_by_code={}
    for c in CALLS:
        calls_by_code.setdefault(c[0],[]).append([c[1],c[2],c[3],c[4],c[5],c[6],c[7],c[8],c[9],c[10],c[11],c[12],c[13],
                                                  (round(float(c[14]),5) if c[14] else ""),(round(float(c[15]),5) if c[15] else "")])
    label = f"Lifetime · {win_start} → {win_end} · {len(R)}-rep roster"
    D = dict(label=label, gen=datetime.date.today().isoformat(), rx=D_rx, reps=R, daily=D_daily, docs=D_docs,
             mgrScore=mgr_roll(), zoneScore=zone_roll(), docsByState=D_docsByState, calls=calls_by_code)
    payload = json.dumps(D, separators=(",", ":"))
    b64 = base64.b64encode(gzip.compress(payload.encode(), 6)).decode()
    with open(TEMPLATE, encoding="utf-8") as fh: tpl = fh.read()
    html = tpl.replace("__DATA_MARKER__", b64)
    tmp = REPORT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: fh.write(html)
    os.replace(tmp, REPORT)
    return dict(reps=len(R), totRx=totRx, totVisits=sum(r["vis"] for r in R), docMet=docMet,
                activeBO=len(bo), conv=round(100*rxDoctors/docMet,1) if docMet else 0, mb=round(len(html)/1048576,2))

# ------------------------------------------------------------------ orchestrate
def run_etl():
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "already running"}
    t0 = time.time()
    try:
        api = Api()
        con = db()
        emps = enumerate_roster(api)
        flat = geo_flat(api)
        s1, role_map = phase_b(api, emps, flat)
        # persist roster/s1/rolemap for fast re-render if needed
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('roster', ?)", (json.dumps(emps),))
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('s1', ?)", (json.dumps(s1),))
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('rolemap', ?)", (json.dumps(role_map),))
        con.commit()
        win_start = LIFE_START + "-01"
        win_end   = datetime.date.today().isoformat()
        seen, fetched = phase_c(api, emps, s1, con, win_start, win_end)
        stats = compute_and_render(con, emps, s1, role_map, win_start, win_end)
        meta = {"ok": True, "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
                "durationSec": round(time.time() - t0, 1), "roster": len(emps),
                "dayPlansInWindow": seen, "dayPlansFetchedThisRun": fetched, **stats}
        with open(META, "w") as fh: json.dump(meta, fh)
        return meta
    except Exception as e:
        meta = {"ok": False, "error": str(e), "at": datetime.datetime.utcnow().isoformat() + "Z"}
        try:
            with open(META, "w") as fh: json.dump(meta, fh)
        except Exception: pass
        return meta
    finally:
        _LOCK.release()

if __name__ == "__main__":
    print(json.dumps(run_etl(), indent=2))
