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
from flask import (Flask, session, redirect, url_for, request, Response, jsonify,
                   render_template_string, send_file)

DATA_DIR = os.environ.get("DATA_DIR", "./data")
REPORT   = os.path.join(DATA_DIR, "report.html")
SERVED   = os.path.join(DATA_DIR, "report_served.html")   # report.html + toolbar, prebuilt
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

WORDMARK = """<svg viewBox="0 0 139 17" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M0 16.6002L2.28061 0.263147H13.4644L13.0477 3.22356H5.26296L4.6928 7.36814H11.3811L10.9645 10.3286H4.27615L3.39899 16.6002H0Z" fill="url(#fl_paint0_linear)"/><path d="M11.9933 16.6002L14.2739 0.263147H20.3044C21.3569 0.263147 22.278 0.453198 23.0674 0.833301C23.8569 1.19878 24.4709 1.74701 24.9094 2.47797C25.3626 3.20894 25.5892 4.11534 25.5892 5.19717C25.5892 5.97199 25.4504 6.68834 25.1726 7.34621C24.9094 8.00408 24.522 8.57423 24.0104 9.05667C23.5133 9.53911 22.9066 9.91921 22.1903 10.197L24.9314 16.6002H21.3131L18.265 9.31982L20.3044 10.6794H16.2256L15.3923 16.6002H11.9933ZM16.6422 7.719H19.5588C20.0704 7.719 20.5163 7.60936 20.8964 7.39007C21.2912 7.17078 21.5982 6.87108 21.8175 6.49098C22.0514 6.11088 22.1683 5.67961 22.1683 5.19717C22.1683 4.59778 21.971 4.12265 21.5762 3.77179C21.1961 3.4063 20.6771 3.22356 20.0193 3.22356H17.2562L16.6422 7.719Z" fill="url(#fl_paint1_linear)"/><path d="M34.8813 16.8634C33.6971 16.8634 32.6007 16.666 31.592 16.2713C30.5978 15.8766 29.728 15.3211 28.9824 14.6047C28.2514 13.8884 27.6813 13.0551 27.2719 12.1048C26.8626 11.1399 26.6579 10.0873 26.6579 8.94703C26.6579 7.67514 26.8918 6.49829 27.3597 5.41646C27.8275 4.33463 28.478 3.39168 29.3113 2.58762C30.1446 1.76894 31.1095 1.133 32.206 0.679799C33.317 0.2266 34.5158 0 35.8023 0C37.0011 0 38.0976 0.197361 39.0917 0.592083C40.1004 0.986805 40.9703 1.54234 41.7012 2.25869C42.4468 2.96041 43.017 3.79372 43.4117 4.75859C43.821 5.70885 44.0257 6.74682 44.0257 7.87251C44.0257 9.14439 43.7918 10.3286 43.324 11.425C42.8561 12.5068 42.1983 13.4571 41.3504 14.2758C40.5171 15.0945 39.5449 15.7304 38.4338 16.1836C37.3374 16.6368 36.1532 16.8634 34.8813 16.8634ZM34.8813 13.7933C35.6707 13.7933 36.409 13.6471 37.0961 13.3548C37.7979 13.0624 38.4119 12.653 38.9382 12.1267C39.4645 11.6004 39.8738 10.9791 40.1662 10.2628C40.4732 9.5318 40.6267 8.74236 40.6267 7.89443C40.6267 6.92956 40.4147 6.08895 39.9908 5.3726C39.5814 4.64164 39.0113 4.07879 38.2803 3.68407C37.564 3.27473 36.738 3.07006 35.8023 3.07006C35.0129 3.07006 34.2673 3.21625 33.5656 3.50864C32.8785 3.80102 32.2718 4.21037 31.7455 4.73666C31.2192 5.24834 30.8025 5.86235 30.4955 6.5787C30.2031 7.29504 30.0569 8.08449 30.0569 8.94703C30.0569 9.89728 30.2616 10.7379 30.6709 11.4689C31.0949 12.1998 31.6651 12.77 32.3814 13.1793C33.1124 13.5887 33.9457 13.7933 34.8813 13.7933Z" fill="url(#fl_paint2_linear)"/><path d="M44.4387 16.6002L46.7194 0.263147H49.3289L56.2804 11.8197L55.0304 12.1487L56.6971 0.263147H60.096L57.8154 16.6002H55.184L48.386 4.95595L49.5043 4.62702L47.8377 16.6002H44.4387Z" fill="url(#fl_paint3_linear)"/><path d="M62.7755 16.6002L64.6395 3.22356H60.4949L60.9115 0.263147H72.5339L72.1172 3.22356H68.0384L66.1745 16.6002H62.7755Z" fill="url(#fl_paint4_linear)"/><path d="M71.0593 16.6002L73.34 0.263147H76.7389L74.875 13.6398H81.7826L81.366 16.6002H71.0593Z" fill="url(#fl_paint5_linear)"/><path d="M82.1746 16.6002L84.4552 0.263147H87.8542L85.5736 16.6002H82.1746Z" fill="url(#fl_paint6_linear)"/><path d="M87.5934 16.6002L89.8741 0.263147H92.4836L99.4351 11.8197L98.1851 12.1487L99.8517 0.263147H103.251L100.97 16.6002H98.3386L91.5407 4.95595L92.659 4.62702L90.9924 16.6002H87.5934Z" fill="url(#fl_paint7_linear)"/><path d="M102.992 16.6002L105.272 0.263147H116.259L115.842 3.22356H108.255L107.75 6.92956H114.899L114.482 9.88997H107.334L106.807 13.6398H114.395L113.978 16.6002H102.992Z" fill="url(#fl_paint8_linear)"/><path fill-rule="evenodd" clip-rule="evenodd" d="M120.389 15.0977L125.464 15.0977L130.919 7.74416L125.464 0.390624L120.389 0.390624L125.844 7.74416L120.389 15.0977ZM127.959 15.0977L133.414 7.74416L127.959 0.390625L133.034 0.390625L138.49 7.74416L133.034 15.0977L127.959 15.0977Z" fill="url(#fl_paint9_linear)"/><defs><linearGradient id="fl_paint0_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint1_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint2_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint3_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint4_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint5_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint6_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint7_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint8_linear" x1="60.7839" y1="-17.2166" x2="39.5834" y2="13.2742" gradientUnits="userSpaceOnUse"><stop stop-color="#2E3790"/><stop offset="0.39691" stop-color="#FF7A45"/><stop offset="1" stop-color="#EB2227"/></linearGradient><linearGradient id="fl_paint9_linear" x1="138.49" y1="7.74416" x2="120.389" y2="7.74416" gradientUnits="userSpaceOnUse"><stop stop-color="#344FA9"/><stop offset="1" stop-color="#353FA7"/></linearGradient></defs></svg>"""

LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hive Frontline &mdash; sign in</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--ink:#101828;--body:#475467;--faint:#98A2B3;--line:#E4E9F2;--accent:#4F46E5;--bg:#F6F7FB}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--ink);
 -webkit-font-smoothing:antialiased}
.wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:24px}
.card{width:min(1120px,100%);background:#fff;border-radius:24px;overflow:hidden;display:grid;
 grid-template-columns:1fr 1fr;box-shadow:0 24px 70px rgba(16,24,64,.14);min-height:620px}
.pane{padding:48px 56px;display:flex;flex-direction:column}
.brandrow svg{width:138px;height:auto;display:block}
.formwrap{margin:auto 0;max-width:380px;width:100%}
h1{font-size:34px;line-height:1.15;letter-spacing:-1px;font-weight:800;margin:0 0 10px}
.sub{font-size:14.5px;color:var(--body);line-height:1.6;margin:0 0 30px}
label{display:block;font-size:13px;font-weight:600;margin:0 0 7px}
.field{position:relative}
input[type=password],input[type=text]{width:100%;font:500 15px Inter,sans-serif;padding:14px 46px 14px 16px;
 border:1.5px solid var(--line);border-radius:12px;background:#fff;color:var(--ink);transition:.16s}
input::placeholder{color:var(--faint);font-weight:400}
input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px rgba(79,70,229,.12)}
.eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);width:38px;height:38px;border:0;
 background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
 border-radius:9px;color:var(--faint)}
.eye:hover{color:var(--body);background:#F4F6FA}
.eye svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.7;
 stroke-linecap:round;stroke-linejoin:round}
button.go{width:100%;margin-top:22px;padding:14px 20px;border:0;border-radius:12px;cursor:pointer;
 background:var(--accent);color:#fff;font:700 15px Inter,sans-serif;
 transition:transform .12s,box-shadow .16s,background .16s;box-shadow:0 8px 20px rgba(79,70,229,.28)}
button.go:hover{background:#4338CA;box-shadow:0 10px 26px rgba(79,70,229,.36)}
button.go:active{transform:translateY(1px)}
.err{margin-top:14px;font-size:13px;color:#B42318;background:#FEF3F2;border:1px solid #FECDCA;
 border-radius:10px;padding:10px 13px;line-height:1.5}
.hint{margin-top:26px;font-size:12.5px;color:var(--faint);line-height:1.6}
.foot{font-size:12px;color:var(--faint);margin-top:auto;padding-top:28px}
.show{position:relative;background:linear-gradient(150deg,#4F46E5 0%,#4338CA 46%,#3B2E9E 100%);
 overflow:hidden;display:flex;flex-direction:column;justify-content:center;padding:52px 48px;color:#fff}
.show::before{content:"";position:absolute;width:520px;height:520px;border-radius:50%;
 background:radial-gradient(circle,rgba(255,255,255,.16),transparent 62%);top:-190px;right:-160px}
.show::after{content:"";position:absolute;width:360px;height:360px;border-radius:50%;
 background:radial-gradient(circle,rgba(124,58,237,.5),transparent 65%);bottom:-140px;left:-110px}
.grid{position:absolute;inset:0;opacity:.16;
 background-image:linear-gradient(rgba(255,255,255,.35) 1px,transparent 1px),
                  linear-gradient(90deg,rgba(255,255,255,.35) 1px,transparent 1px);
 background-size:46px 46px}
.slides{position:relative;z-index:2;min-height:300px}
.slide{position:absolute;inset:0;opacity:0;transform:translateY(14px);pointer-events:none;
 transition:opacity .55s ease,transform .55s ease}
.slide.on{opacity:1;transform:none;pointer-events:auto;position:relative}
.slide .eyebrow{font-size:11px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;
 color:#C7D2FE;margin-bottom:12px}
.slide h2{font-size:30px;line-height:1.24;letter-spacing:-.7px;font-weight:800;margin:0 0 12px;max-width:15ch}
.slide p{font-size:14.5px;line-height:1.65;color:#DDE3FF;margin:0;max-width:34ch}
.chips{display:flex;gap:12px;margin-top:26px;flex-wrap:wrap}
.chipcard{background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.22);border-radius:14px;
 padding:14px 16px;backdrop-filter:blur(8px);min-width:120px;animation:float 5s ease-in-out infinite}
.chipcard:nth-child(2){animation-delay:.9s}
.chipcard .v{font-size:21px;font-weight:800;letter-spacing:-.4px}
.chipcard .l{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
 color:#C7D2FE;margin-top:4px}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}
.dots{position:relative;z-index:2;display:flex;gap:8px;margin-top:38px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.38);border:0;padding:0;
 cursor:pointer;transition:.25s}
.dot.on{width:26px;border-radius:99px;background:#fff}
.prog{position:absolute;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.18);z-index:3}
.prog i{display:block;height:100%;width:0;background:#fff;animation:fill 5s linear infinite}
@keyframes fill{from{width:0}to{width:100%}}
.show:hover .prog i{animation-play-state:paused}
@media(max-width:900px){.card{grid-template-columns:1fr;min-height:0}.show{display:none}
 .pane{padding:38px 28px}h1{font-size:28px}}
@media(prefers-reduced-motion:reduce){.chipcard{animation:none}.prog i{animation:none;width:100%}
 .slide{transition:none}}
</style></head><body>
<div class="wrap"><div class="card">
  <div class="pane">
    <div class="brandrow">{{ wordmark|safe }}</div>
    <div class="formwrap">
      <h1>Welcome back</h1>
      <div class="sub">{{ sub }}</div>
      {% if ms %}
        <a href="{{ url_for('login_ms') }}" style="text-decoration:none">
          <button class="go" type="button">Sign in with Microsoft</button></a>
      {% else %}
        <form method="post" autocomplete="off">
          <label for="pw">Report password</label>
          <div class="field">
            <input id="pw" type="password" name="pw" placeholder="Enter the shared password" autofocus>
            <button class="eye" type="button" id="toggle" aria-label="Show password" title="Show password">
              <svg id="eyeicon" viewBox="0 0 24 24">
                <path d="M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3.2"/>
              </svg>
            </button>
          </div>
          <button class="go" type="submit">Open report</button>
        </form>
      {% endif %}
      {% if err %}<div class="err">{{ err }}</div>{% endif %}
      <div class="hint">Trouble getting in? Ask Arshad &mdash; access is managed centrally.</div>
    </div>
    <div class="foot">Hive Frontline &middot; field-force intelligence</div>
  </div>

  <div class="show">
    <div class="grid"></div>
    <div class="slides" id="slides">
      <div class="slide on">
        <div class="eyebrow">Always current</div>
        <h2>The whole field force, in one link</h2>
        <p>No more emailed spreadsheets. The report refreshes itself and is live every time you open it.</p>
        <div class="chips">
          <div class="chipcard"><div class="v">{{ s_rx }}</div><div class="l">Prescriptions</div></div>
          <div class="chipcard"><div class="v">{{ s_reps }}</div><div class="l">Employees</div></div>
        </div>
      </div>
      <div class="slide">
        <div class="eyebrow">Every doctor</div>
        <h2>Ranked by what they actually produce</h2>
        <p>Prescriptions, visits, samples and days idle &mdash; filter to the ones slipping out of coverage.</p>
        <div class="chips">
          <div class="chipcard"><div class="v">{{ s_docs }}</div><div class="l">Doctors met</div></div>
          <div class="chipcard"><div class="v">{{ s_conv }}</div><div class="l">Rx conversion</div></div>
        </div>
      </div>
      <div class="slide">
        <div class="eyebrow">Every employee</div>
        <h2>A profile for everyone in the field</h2>
        <p>Click any name for their trend, top doctors and peer rank. Managers lead with their team.</p>
        <div class="chips">
          <div class="chipcard"><div class="v">{{ s_reps }}</div><div class="l">Profiles</div></div>
          <div class="chipcard"><div class="v">{{ s_states }}</div><div class="l">States</div></div>
        </div>
      </div>
    </div>
    <div class="dots" id="dots"></div>
    <div class="prog"><i></i></div>
  </div>
</div></div>
<script>
(function(){
 var t=document.getElementById('toggle'), i=document.getElementById('pw'), ic=document.getElementById('eyeicon');
 if(!t||!i)return;
 var OPEN='<path d="M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3.2"/>';
 var SHUT='<path d="M3 3l18 18"/><path d="M10.6 6.2A9.7 9.7 0 0 1 12 5c6.2 0 10 7 10 7a17 17 0 0 1-3.4 4.1"/>'
        +'<path d="M6.5 7.8A17 17 0 0 0 2 12s3.8 7 10 7a9.6 9.6 0 0 0 3.9-.8"/>'
        +'<path d="M9.9 10a3.2 3.2 0 0 0 4.3 4.3"/>';
 t.onclick=function(){
  var show = i.type==='password';
  i.type = show ? 'text' : 'password';
  ic.innerHTML = show ? SHUT : OPEN;
  t.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  t.title = show ? 'Hide password' : 'Show password';
  i.focus();
 };
})();
(function(){
 var sl=[].slice.call(document.querySelectorAll('#slides .slide')), dots=document.getElementById('dots');
 if(sl.length<2||!dots)return;
 var i=0,timer=null;
 sl.forEach(function(_,k){
  var b=document.createElement('button'); b.className='dot'+(k?'':' on');
  b.setAttribute('aria-label','Slide '+(k+1));
  b.onclick=function(){go(k);start();}; dots.appendChild(b);
 });
 var ds=[].slice.call(dots.children);
 function go(n){ sl[i].classList.remove('on'); ds[i].classList.remove('on');
  i=((n % sl.length)+sl.length) % sl.length;
  sl[i].classList.add('on'); ds[i].classList.add('on');
  var bar=document.querySelector('.prog i');
  if(bar){bar.style.animation='none'; void bar.offsetWidth; bar.style.animation='';}
 }
 function start(){ clearInterval(timer); timer=setInterval(function(){go(i+1);},5000); }
 var show=document.querySelector('.show');
 show.addEventListener('mouseenter',function(){clearInterval(timer);});
 show.addEventListener('mouseleave',start);
 document.addEventListener('visibilitychange',function(){document.hidden?clearInterval(timer):start();});
 start();
})();
</script></body></html>"""

def _inr(n):
    """Indian digit grouping, e.g. 199241 -> 1,99,241."""
    try: n = int(n)
    except Exception: return "—"
    s = str(n)
    if len(s) <= 3: return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:]); head = head[:-2]
    if head: parts.insert(0, head)
    return ",".join(parts + [tail])

def _login_stats():
    """Real figures for the brand panel; blanks if the ETL has not run yet."""
    m = {}
    try:
        if os.path.exists(META): m = json.load(open(META))
    except Exception: pass
    conv = m.get("conv")
    return dict(s_rx=_inr(m.get("totRx")), s_reps=_inr(m.get("reps")),
                s_docs=_inr(m.get("docMet")),
                s_conv=(str(round(conv)) + "%") if isinstance(conv, (int, float)) else "—",
                s_states="14")

@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if not MS_CID and request.method == "POST":
        if PASSWORD and request.form.get("pw") == PASSWORD:
            session["user"] = {"name": "team"}; return redirect(url_for("index"))
        err = "Incorrect password."
    sub = ("Sign in with your britishbiologicals.com account." if MS_CID
           else "Enter the shared report password.")
    return render_template_string(LOGIN_HTML, ms=bool(MS_CID), err=err, sub=sub,
                                  wordmark=WORDMARK, **_login_stats())

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
                                      err=f"{email or 'This account'} is not a {DOMAIN} address.",
                                      wordmark=WORDMARK, **_login_stats()), 403
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
    # Serve a PREBUILT copy straight off disk.
    #
    # This used to read the 7.68 MB report into a Python string and then .replace()
    # it — which allocates a second full copy, then a third when encoding the
    # response. ~23 MB per concurrent request, on a 512 MB instance, while the ETL
    # may also be running. send_file streams from disk instead, so a page load
    # costs almost no process memory no matter how many people hit it at once.
    _ensure_served()
    return send_file(SERVED, mimetype="text/html", conditional=True,
                     max_age=0, last_modified=os.path.getmtime(SERVED))

_served_lock = threading.Lock()

def _ensure_served():
    """Rebuild report_served.html only when report.html is newer. Once per ETL, not per request."""
    try:
        if os.path.exists(SERVED) and os.path.getmtime(SERVED) >= os.path.getmtime(REPORT):
            return
    except OSError:
        pass
    with _served_lock:
        try:
            if os.path.exists(SERVED) and os.path.getmtime(SERVED) >= os.path.getmtime(REPORT):
                return
        except OSError:
            pass
        tmp = SERVED + ".tmp"
        with open(REPORT, encoding="utf-8") as src:
            html = src.read()
        head, sep, tail = html.rpartition("</body>")
        with open(tmp, "w", encoding="utf-8") as out:
            if sep:
                out.write(head); out.write(TOOLBAR); out.write(sep); out.write(tail)
            else:
                out.write(html); out.write(TOOLBAR)
        del html, head, tail
        os.replace(tmp, SERVED)

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
