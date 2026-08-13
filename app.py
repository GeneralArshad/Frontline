#!/usr/bin/env python3
"""
Frontline live report — web service.

- Serves the pre-rendered interactive report INSTANTLY from the incremental store.
- A background thread refreshes the store on a schedule; a "Refresh now" button
  triggers an on-demand refresh (this is the sensible, viable version of "live").
- Access control: Microsoft (Entra) SSO restricted to your tenant/domain when
  MS_CLIENT_ID is set; otherwise a shared-password gate (interim).
"""
import os, sys, json, threading, time, functools, datetime, sqlite3, re, subprocess
from flask import Flask, session, redirect, url_for, request, Response, jsonify, render_template_string

DATA_DIR = os.environ.get("DATA_DIR", "./data")
REPORT   = os.path.join(DATA_DIR, "report.html")
META     = os.path.join(DATA_DIR, "meta.json")
DOMAIN   = os.environ.get("ALLOWED_EMAIL_DOMAIN", "").lower()
MS_CID   = os.environ.get("MS_CLIENT_ID", "")
MS_SEC   = os.environ.get("MS_CLIENT_SECRET", "")
MS_TEN   = os.environ.get("MS_TENANT_ID", "common")
PASSWORD = os.environ.get("REPORT_PASSWORD", "")
EVERY    = int(os.environ.get("REFRESH_EVERY_MIN", "60"))

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-change-me")

# ------------------------------------------------------------------ auth
oauth = None
if MS_CID:
    from authlib.integrations.flask_client import OAuth
    oauth = OAuth(app)
    oauth.register(
        name="microsoft",
        client_id=MS_CID, client_secret=MS_SEC,
        server_metadata_url=f"https://login.microsoftonline.com/{MS_TEN}/v2.0/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

def authed():
    return bool(session.get("user"))

def require_auth(f):
    @functools.wraps(f)
    def w(*a, **k):
        if authed(): return f(*a, **k)
        return redirect(url_for("login"))
    return w

LOGIN_HTML = """<!doctype html><meta charset=utf-8><title>Frontline report — sign in</title>
<style>body{font-family:Inter,Segoe UI,Arial,sans-serif;background:#0E1740;color:#fff;display:flex;
min-height:100vh;align-items:center;justify-content:center;margin:0}.c{background:#fff;color:#0E1740;
padding:34px 38px;border-radius:18px;box-shadow:0 20px 60px rgba(0,0,0,.4);width:340px}
h1{font-size:19px;margin:0 0 4px}.s{color:#5B6478;font-size:13px;margin-bottom:20px}
input,button{width:100%;box-sizing:border-box;padding:11px 12px;border-radius:10px;border:1px solid #E4E9F4;font-size:14px}
button{background:#1B2A6B;color:#fff;border:0;font-weight:700;margin-top:12px;cursor:pointer}
.e{color:#C8102E;font-size:12px;margin-top:10px}.gradbar{height:4px;border-radius:4px;margin-bottom:18px;
background:linear-gradient(90deg,#E8911A,#D81E5B,#C8102E,#7C3AED,#1B2A6B)}</style>
<div class=c><div class=gradbar></div><h1>Hive Frontline — Field Rx BI</h1>
<div class=s>{{sub}}</div>
{% if ms %}<a href="{{ url_for('login_ms') }}"><button>Sign in with Microsoft</button></a>
{% else %}<form method=post><input type=password name=pw placeholder="Report password" autofocus>
<button>Open report</button></form>{% endif %}
{% if err %}<div class=e>{{err}}</div>{% endif %}</div>"""

@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if not MS_CID and request.method == "POST":
        if PASSWORD and request.form.get("pw") == PASSWORD:
            session["user"] = {"name": "team"}; return redirect(url_for("index"))
        err = "Incorrect password."
    sub = ("Sign in with your britishbiologicals.com account." if MS_CID
           else "Enter the shared report password.")
    return render_template_string(LOGIN_HTML, ms=bool(MS_CID), err=err, sub=sub)

@app.route("/login/ms")
def login_ms():
    return oauth.microsoft.authorize_redirect(url_for("auth_callback", _external=True))

@app.route("/auth/callback")
def auth_callback():
    token = oauth.microsoft.authorize_access_token()
    info = token.get("userinfo") or {}
    email = (info.get("email") or info.get("preferred_username") or "").lower()
    if DOMAIN and not email.endswith("@" + DOMAIN):
        return render_template_string(LOGIN_HTML, ms=True, sub="Access is restricted.",
                                      err=f"{email or 'This account'} is not a {DOMAIN} address."), 403
    session["user"] = {"email": email, "name": info.get("name")}
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

# ------------------------------------------------------------------ report
TOOLBAR = """<div id="__bar" style="position:fixed;bottom:14px;right:14px;z-index:99999;
background:#0E1740;color:#fff;border-radius:12px;padding:8px 12px;font:600 12px Segoe UI,Arial;
box-shadow:0 8px 24px rgba(0,0,0,.3);display:flex;align-items:center;gap:12px">
<span id="__upd" style="opacity:.8"></span>
<button id="__rf" style="background:#1B2A6B;color:#fff;border:0;border-radius:8px;padding:6px 12px;
font-weight:700;cursor:pointer">↻ Refresh now</button>
<a href="/logout" style="color:#9FB0FF;text-decoration:none">Sign out</a></div>
<script>(function(){var b=document.getElementById('__rf'),u=document.getElementById('__upd');
function fmt(iso){if(!iso)return'';var d=new Date(iso);return 'Updated '+d.toLocaleString();}
fetch('/status').then(r=>r.json()).then(m=>{u.textContent=fmt(m.generatedAt)+(m.roster?(' · '+m.roster+' reps'):'');});
b.onclick=function(){b.disabled=true;b.textContent='Refreshing…';
 fetch('/refresh',{method:'POST'}).then(r=>r.json()).then(function(){
  var t=setInterval(function(){fetch('/status').then(r=>r.json()).then(function(m){
    if(m.running){return;} clearInterval(t); location.reload();});},4000);});};})();</script>"""

@app.route("/")
@require_auth
def index():
    if not os.path.exists(REPORT):
        # first boot before any ETL finished
        threading.Thread(target=_refresh_bg, daemon=True).start()
        return ("<h2 style='font-family:sans-serif'>Building the report for the first time…</h2>"
                "<p style='font-family:sans-serif'>The initial lifetime backfill is running. "
                "Refresh this page in a few minutes.</p>"), 200
    with open(REPORT, encoding="utf-8") as fh: html = fh.read()
    html = html.replace("</body>", TOOLBAR + "</body>")
    return Response(html, mimetype="text/html")

_running = {"v": False}
ETL_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etl.py")

def _run_etl_subprocess(*args):
    """Run the ETL in a CHILD PROCESS, never in this worker.

    In-process it broke the service two ways: the CPU-bound compute phase held the
    GIL and starved gunicorn's health-check thread (Render: "health check timed out
    after 5 seconds" -> instance killed), and the memory peak stayed resident in the
    long-lived worker. As a child it can't block request handling, and its memory is
    fully reclaimed on exit.
    """
    _running["v"] = True
    try:
        p = subprocess.run([sys.executable, ETL_PY, *args],
                           capture_output=True, text=True, timeout=3600)
        if p.returncode != 0:
            try:
                with open(META, "w") as fh:
                    json.dump({"ok": False,
                               "error": (p.stderr or "")[-800:] or f"etl exited {p.returncode}",
                               "at": datetime.datetime.utcnow().isoformat() + "Z"}, fh)
            except Exception: pass
    except subprocess.TimeoutExpired:
        try:
            with open(META, "w") as fh:
                json.dump({"ok": False, "error": "ETL timed out after 60 min",
                           "at": datetime.datetime.utcnow().isoformat() + "Z"}, fh)
        except Exception: pass
    except Exception as e:
        try:
            with open(META, "w") as fh:
                json.dump({"ok": False, "error": str(e)[:800],
                           "at": datetime.datetime.utcnow().isoformat() + "Z"}, fh)
        except Exception: pass
    finally:
        _running["v"] = False

def _refresh_bg():
    _run_etl_subprocess()

@app.route("/refresh", methods=["POST"])
@require_auth
def refresh():
    if not _running["v"]:
        threading.Thread(target=_refresh_bg, daemon=True).start()
    return jsonify({"started": True, "running": True})

@app.route("/status")
def status():
    m = {}
    if os.path.exists(META):
        try: m = json.load(open(META))
        except Exception: pass
    m["running"] = _running["v"]
    return jsonify(m)

@app.route("/healthz")
def healthz():
    return "ok", 200

# ------------------------------------------------------------------ notes
# Notes live in their OWN sqlite file on the data disk, so an ETL rebuild can
# never touch them. scope='rep' (key = employee code) or 'report' (key = '').
NOTES_DB = os.path.join(DATA_DIR, "notes.db")

def ndb():
    con = sqlite3.connect(NOTES_DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS note(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL, key TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
        created TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0)""")
    con.execute("CREATE INDEX IF NOT EXISTS note_scope_key ON note(scope,key)")
    return con

def _clean(s, n):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]

@app.route("/api/notes")
@require_auth
def notes_list():
    con = ndb()
    rows = con.execute("SELECT id,scope,key,author,body,created,resolved FROM note ORDER BY id DESC").fetchall()
    con.close()
    return jsonify([{"id": r[0], "scope": r[1], "key": r[2], "author": r[3],
                     "body": r[4], "created": r[5], "resolved": bool(r[6])} for r in rows])

@app.route("/api/notes", methods=["POST"])
@require_auth
def notes_add():
    j = request.get_json(silent=True) or {}
    body = _clean(j.get("body"), 2000)
    if not body:
        return jsonify({"error": "empty note"}), 400
    scope = "rep" if j.get("scope") == "rep" else "report"
    key = _clean(j.get("key"), 40) if scope == "rep" else ""
    if scope == "rep" and not key:
        return jsonify({"error": "missing key"}), 400
    author = _clean(j.get("author"), 60) or (session.get("user", {}).get("email") or "team")
    created = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    con = ndb()
    cur = con.execute("INSERT INTO note(scope,key,author,body,created,resolved) VALUES(?,?,?,?,?,0)",
                      (scope, key, author, body, created))
    con.commit(); nid = cur.lastrowid; con.close()
    return jsonify({"id": nid, "scope": scope, "key": key, "author": author,
                    "body": body, "created": created, "resolved": False})

@app.route("/api/notes/<int:nid>", methods=["PATCH", "DELETE"])
@require_auth
def notes_update(nid):
    con = ndb()
    if request.method == "DELETE":
        con.execute("DELETE FROM note WHERE id=?", (nid,))
    else:
        j = request.get_json(silent=True) or {}
        con.execute("UPDATE note SET resolved=? WHERE id=?", (1 if j.get("resolved") else 0, nid))
    con.commit(); con.close()
    return jsonify({"ok": True})

# ------------------------------------------------------- background scheduler
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")

def _scheduler():
    # backfill once on boot if no report yet
    if not os.path.exists(REPORT):
        _refresh_bg()
    # If only the template/UI changed (newer than the last render), re-render from the
    # cached store — instant, no API pull. Makes UI deploys show up immediately.
    else:
        try:
            if os.path.getmtime(TEMPLATE) > os.path.getmtime(REPORT):
                _run_etl_subprocess("--rerender")
        except Exception:
            pass
    while EVERY > 0:
        time.sleep(EVERY * 60)
        if not _running["v"]:
            _refresh_bg()

threading.Thread(target=_scheduler, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
