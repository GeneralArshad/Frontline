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
PROGRESS = os.path.join(DATA_DIR, "progress.json")
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

BLUEPRINT = """<rect x="56.4" y="120.5" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 60.4 124.5)" style="animation:pulse 2.6s ease-in-out infinite;animation-delay:0.00s"/><path d="M178.5 233.3H188.5M183.5 228.3V238.3" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 3.2s ease-in-out infinite;animation-delay:0.21s"/><circle cx="75.7" cy="548.7" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 3.8s ease-in-out infinite;animation-delay:0.42s"/><rect x="479.3" y="204.1" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 483.3 208.1)" style="animation:pulse 4.4s ease-in-out infinite;animation-delay:0.63s"/><path d="M263.0 613.4H273.0M268.0 608.4V618.4" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 5.0s ease-in-out infinite;animation-delay:0.84s"/><circle cx="420.2" cy="627.1" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 2.6s ease-in-out infinite;animation-delay:1.05s"/><rect x="725.3" y="430.0" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 729.3 434.0)" style="animation:pulse 3.2s ease-in-out infinite;animation-delay:1.26s"/><path d="M134.3 506.4H144.3M139.3 501.4V511.4" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 3.8s ease-in-out infinite;animation-delay:1.47s"/><circle cx="521.4" cy="393.8" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 4.4s ease-in-out infinite;animation-delay:1.68s"/><rect x="411.6" y="131.2" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 415.6 135.2)" style="animation:pulse 5.0s ease-in-out infinite;animation-delay:1.89s"/><path d="M154.6 561.3H164.6M159.6 556.3V566.3" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 2.6s ease-in-out infinite;animation-delay:2.10s"/><circle cx="298.8" cy="423.3" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 3.2s ease-in-out infinite;animation-delay:2.31s"/><rect x="161.3" y="378.6" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 165.3 382.6)" style="animation:pulse 3.8s ease-in-out infinite;animation-delay:2.52s"/><path d="M110.3 254.0H120.3M115.3 249.0V259.0" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 4.4s ease-in-out infinite;animation-delay:2.73s"/><circle cx="81.7" cy="625.2" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 5.0s ease-in-out infinite;animation-delay:2.94s"/><rect x="120.4" y="445.8" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 124.4 449.8)" style="animation:pulse 2.6s ease-in-out infinite;animation-delay:3.15s"/><path d="M197.0 429.8H207.0M202.0 424.8V434.8" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 3.2s ease-in-out infinite;animation-delay:3.36s"/><circle cx="521.2" cy="208.9" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 3.8s ease-in-out infinite;animation-delay:3.57s"/><rect x="541.0" y="187.3" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 545.0 191.3)" style="animation:pulse 4.4s ease-in-out infinite;animation-delay:3.78s"/><path d="M265.7 126.0H275.7M270.7 121.0V131.0" stroke="var(--fnt)" stroke-width="1.4" style="animation:pulse 5.0s ease-in-out infinite;animation-delay:3.99s"/><circle cx="75.0" cy="430.7" r="3.4" fill="none" stroke="var(--ac)" stroke-width="1.4" style="animation:pulse 2.6s ease-in-out infinite;animation-delay:4.20s"/><rect x="494.5" y="50.9" width="8" height="8" fill="none" stroke="var(--ac)" stroke-width="1.4" transform="rotate(45 498.5 54.9)" style="animation:pulse 3.2s ease-in-out infinite;animation-delay:4.41s"/>"""

LOGIN_HTML = """<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hive Frontline &mdash; console access</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* Palette carried over from the Hive Frontline v2 handoff: warm paper, ember accent.
   Inter throughout (the prototype's Bricolage + IBM Plex Mono were dropped by request);
   the letter-spaced uppercase treatment does the work the mono was doing. */
[data-theme=light]{--bg:#F2F0E9;--srf:#FBFAF7;--srf2:#ECEAE1;--line:#DBD7CA;
  --ink:#191B20;--mut:#5F6470;--fnt:#9A9C94;--ok:#0E6E4A;--bad:#C8102E;--ac:#C2410C;--acInk:#fff}
[data-theme=dark]{--bg:#0A0B0E;--srf:#15181F;--srf2:#1F232C;--line:#2C313D;
  --ink:#ECEEF2;--mut:#AAB1C0;--fnt:#78808F;--ok:#3ACF95;--bad:#FF5C69;--ac:#FF8A5B;--acInk:#0B0C0F}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--ink);
  font-size:13.5px;line-height:1.5;-webkit-font-smoothing:antialiased;
  transition:background .25s,color .25s}
.wrap{min-height:100vh;display:grid;grid-template-columns:minmax(420px,540px) 1fr}
/* ---------------- left: the form ---------------- */
.pane{display:flex;flex-direction:column;padding:44px 56px;border-right:1px solid var(--line);
  background:var(--srf)}
.brand{display:flex;align-items:center;gap:11px}
.brand svg{width:132px;height:auto;display:block}
.mid{margin:auto 0;max-width:350px;width:100%;animation:fadeUp .5s ease both}
.eyebrow{font-size:10.5px;font-weight:700;letter-spacing:.2em;color:var(--ac)}
h1{font-size:34px;font-weight:700;letter-spacing:-.02em;margin:12px 0 8px;line-height:1.1}
.sub{color:var(--mut);font-size:14px;margin:0 0 30px;line-height:1.6}
.lbl{font-size:10px;font-weight:700;letter-spacing:.16em;color:var(--mut);margin-bottom:8px}
.field{position:relative}
input{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:2px;
  padding:13px 44px 13px 15px;color:var(--ink);font:500 15px Inter,sans-serif;outline:none;
  letter-spacing:.14em;transition:border-color .15s,box-shadow .15s}
input::placeholder{color:var(--fnt);letter-spacing:.14em}
input:focus{border-color:var(--ac);box-shadow:0 0 0 3px color-mix(in srgb,var(--ac) 20%,transparent)}
.eye{position:absolute;right:5px;top:50%;transform:translateY(-50%);width:34px;height:34px;border:0;
  background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;
  color:var(--fnt);border-radius:2px}
.eye:hover{color:var(--ink);background:var(--srf2)}
.eye svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.7;
  stroke-linecap:round;stroke-linejoin:round}
.go{width:100%;margin-top:16px;background:var(--ac);color:var(--acInk);border:0;border-radius:2px;
  padding:13px 18px;font:600 14px Inter,sans-serif;cursor:pointer;transition:filter .15s,transform .08s}
.go:hover{filter:brightness(1.12)}
.go:active{transform:translateY(1px)}
.go[disabled]{opacity:.6;cursor:default}
.or{display:flex;align-items:center;gap:12px;margin:20px 0}
.or i{flex:1;height:1px;background:var(--line)}
.or span{font-size:10px;font-weight:600;letter-spacing:.1em;color:var(--fnt)}
.ms{width:100%;background:transparent;color:var(--mut);border:1px solid var(--line);border-radius:2px;
  padding:12px 18px;font:600 13.5px Inter,sans-serif;cursor:pointer;display:flex;align-items:center;
  justify-content:center;gap:9px;transition:.15s;text-decoration:none}
.ms:hover{border-color:var(--mut);color:var(--ink)}
.err{margin-top:14px;font-size:12.5px;color:var(--bad);border:1px solid color-mix(in srgb,var(--bad) 35%,transparent);
  background:color-mix(in srgb,var(--bad) 7%,transparent);border-radius:2px;padding:9px 12px;
  animation:shake .32s}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-4px)}75%{transform:translateX(4px)}}
.hint{margin-top:26px;font-size:12px;color:var(--fnt);line-height:1.6}
.foot{display:flex;align-items:center;justify-content:space-between}
.foot .fl{font-size:10.5px;font-weight:500;letter-spacing:.08em;color:var(--fnt)}
.tbtn{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:2px;
  width:30px;height:30px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:.15s}
.tbtn:hover{border-color:var(--mut);color:var(--ink)}
.tbtn svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round}
/* ---------------- right: blueprint ---------------- */
.show{position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center;
  padding:64px 72px;
  background-image:radial-gradient(color-mix(in srgb,var(--fnt) 30%,transparent) 1px,transparent 1px);
  background-size:26px 26px}
.bp{position:absolute;inset:0;width:100%;height:100%;opacity:.7;pointer-events:none}
.showin{position:relative;z-index:2;max-width:560px;animation:fadeUp .6s .1s ease both}
.live{display:flex;align-items:center;gap:9px;font-size:10.5px;font-weight:600;letter-spacing:.2em;color:var(--mut)}
.live i{width:8px;height:8px;background:var(--ok);animation:pulse 2.2s ease-in-out infinite;display:block}
h2{font-size:44px;font-weight:700;letter-spacing:-.03em;line-height:1.08;margin:20px 0 14px}
.lead{color:var(--mut);font-size:14.5px;line-height:1.65;margin:0;max-width:44ch}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,220px));gap:1px;background:var(--line);
  border:1px solid var(--line);margin-top:36px;width:fit-content}
.stat{background:var(--srf);padding:16px 20px}
.stat .v{font-size:22px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat .l{font-size:9.5px;font-weight:600;letter-spacing:.16em;color:var(--fnt);margin-top:6px}
.rule{position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--ac)}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes pulse{0%,100%{opacity:.25}50%{opacity:1}}
@media(max-width:900px){.wrap{grid-template-columns:1fr}.show{display:none}.pane{padding:36px 26px;border-right:0}
  h1{font-size:28px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<div class="wrap">
  <div class="pane">
    <div class="brand">{{ wordmark|safe }}</div>
    <div class="mid">
      <div class="eyebrow">CONSOLE ACCESS</div>
      <h1>Welcome back.</h1>
      <p class="sub">{{ sub }}</p>
      {% if ms %}
        <a href="{{ url_for('login_ms') }}" style="text-decoration:none"><button class="go" type="button">Sign in with Microsoft</button></a>
      {% else %}
        <form method="post" autocomplete="off" id="f">
          <div class="lbl">ACCESS KEY</div>
          <div class="field">
            <input id="pw" type="password" name="pw" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" autofocus>
            <button class="eye" type="button" id="toggle" aria-label="Show access key" title="Show access key">
              <svg id="eyeicon" viewBox="0 0 24 24"><path d="M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3.2"/></svg>
            </button>
          </div>
          <button class="go" type="submit" id="submit">Open console &rarr;</button>
        </form>
      {% endif %}
      {% if err %}<div class="err">{{ err }}</div>{% endif %}
      <div class="hint">Trouble getting in? Ask Arshad &mdash; access is managed centrally.</div>
    </div>
    <div class="foot">
      <div class="fl">FIELD RX INTELLIGENCE</div>
      <button class="tbtn" id="theme" title="Switch theme">
        <svg id="themeicon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>
      </button>
    </div>
  </div>

  <div class="show">
    <svg class="bp" viewBox="0 0 800 680" preserveAspectRatio="xMidYMid slice">{{ blueprint|safe }}</svg>
    <div class="showin">
      <div class="live"><i></i>LIVE &middot; FIELD RX INTELLIGENCE</div>
      <h2>Every rep, every doctor, every prescription.</h2>
      <p class="lead">No emailed spreadsheets. The console refreshes itself from the field and is
        current every time you open it.</p>
      <div class="stats">
        <div class="stat"><div class="v">{{ s_rx }}</div><div class="l">PRESCRIPTIONS</div></div>
        <div class="stat"><div class="v">{{ s_reps }}</div><div class="l">EMPLOYEES</div></div>
        <div class="stat"><div class="v">{{ s_docs }}</div><div class="l">DOCTORS MET</div></div>
        <div class="stat"><div class="v">{{ s_conv }}</div><div class="l">RX CONVERSION</div></div>
      </div>
    </div>
    <div class="rule"></div>
  </div>
</div>
<script>
/* access-key visibility */
(function(){
 var t=document.getElementById('toggle'), i=document.getElementById('pw'), ic=document.getElementById('eyeicon');
 if(!t||!i)return;
 var OPEN='<path d="M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3.2"/>';
 var SHUT='<path d="M3 3l18 18"/><path d="M10.6 6.2A9.7 9.7 0 0 1 12 5c6.2 0 10 7 10 7a17 17 0 0 1-3.4 4.1"/>'
        +'<path d="M6.5 7.8A17 17 0 0 0 2 12s3.8 7 10 7a9.6 9.6 0 0 0 3.9-.8"/>'
        +'<path d="M9.9 10a3.2 3.2 0 0 0 4.3 4.3"/>';
 t.onclick=function(){ var s=i.type==='password'; i.type=s?'text':'password'; ic.innerHTML=s?SHUT:OPEN;
  t.setAttribute('aria-label', s?'Hide access key':'Show access key');
  t.title=s?'Hide access key':'Show access key'; i.focus(); };
})();
/* theme toggle, remembered */
(function(){
 var b=document.getElementById('theme'), ic=document.getElementById('themeicon'), r=document.documentElement;
 var MOON='M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z';
 var SUN='M12 17a5 5 0 100-10 5 5 0 000 10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4';
 try{ var p=localStorage.getItem('hf_login_theme'); if(p) r.setAttribute('data-theme',p); }catch(e){}
 function paint(){ ic.innerHTML='<path d="'+(r.getAttribute('data-theme')==='dark'?SUN:MOON)+'"/>'; }
 paint();
 b.onclick=function(){ var d=r.getAttribute('data-theme')==='dark';
  r.setAttribute('data-theme', d?'light':'dark'); paint();
  try{ localStorage.setItem('hf_login_theme', d?'light':'dark'); }catch(e){} };
})();
/* submit feedback — the ETL-backed page can take a moment to hand over */
(function(){
 var f=document.getElementById('f'), b=document.getElementById('submit');
 if(!f||!b)return;
 f.addEventListener('submit',function(){ b.disabled=true; b.textContent='Opening console…'; });
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
                                  wordmark=WORDMARK, blueprint=BLUEPRINT, **_login_stats())

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
                                      wordmark=WORDMARK, blueprint=BLUEPRINT, **_login_stats()), 403
    session["user"] = {"email": email, "name": info.get("name")}
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

# ------------------------------------------------------------------ report
TOOLBAR = """<div id="__bar" class="__idle">
<span id="__upd"></span>
<button id="__rf">&#8635; Refresh now</button>
<a href="/logout" id="__so">Sign out</a>
<div id="__panel">
  <div class="__ph"><span class="__dot"></span><b id="__ptitle">Refreshing</b>
    <span id="__pel">0:00</span></div>
  <div class="__bar"><i id="__pfill"></i></div>
  <div id="__pnow">Starting&hellip;</div>
  <ol id="__psteps"></ol>
  <div id="__pfoot">The report stays usable while this runs.</div>
</div></div>
<style>
#__bar{position:fixed;bottom:14px;right:14px;z-index:99999;background:#0E1740;color:#fff;
 border-radius:12px;padding:8px 12px;font:600 12px Inter,'Segoe UI',Arial;
 box-shadow:0 10px 30px rgba(0,0,0,.34);display:flex;align-items:center;gap:12px;
 transition:border-radius .2s}
#__bar.__busy{flex-direction:column;align-items:stretch;gap:0;padding:0;width:288px;border-radius:14px}
#__upd{opacity:.82}
#__bar.__busy #__upd,#__bar.__busy #__rf,#__bar.__busy #__so{display:none}
#__rf{background:#1B2A6B;color:#fff;border:0;border-radius:8px;padding:6px 12px;
 font:700 12px Inter,'Segoe UI',Arial;cursor:pointer}
#__rf:disabled{opacity:.6;cursor:default}
#__so{color:#9FB0FF;text-decoration:none}
#__panel{display:none;padding:13px 14px 12px}
#__bar.__busy #__panel{display:block}
.__ph{display:flex;align-items:center;gap:8px;margin-bottom:9px;font-size:12px}
.__ph b{flex:1;font-weight:800;letter-spacing:.02em}
#__pel{opacity:.6;font-variant-numeric:tabular-nums;font-weight:600}
.__dot{width:8px;height:8px;border-radius:50%;background:#3ddc97;flex:0 0 auto;
 animation:__pulse 1.4s ease-in-out infinite}
@keyframes __pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.8)}}
.__bar{height:5px;border-radius:3px;background:rgba(255,255,255,.14);overflow:hidden}
.__bar i{display:block;height:100%;width:0%;border-radius:3px;
 background:linear-gradient(90deg,#2E3790,#FF7A45 55%,#EB2227);
 transition:width .5s cubic-bezier(.4,0,.2,1)}
#__bar.__done .__bar i{background:#3ddc97}
#__bar.__err .__bar i{background:#FF6B6B}
#__bar.__err .__dot{background:#FF6B6B;animation:none}
#__bar.__done .__dot{background:#3ddc97;animation:none}
#__pnow{font-size:11.5px;opacity:.88;margin:9px 0 2px;font-weight:600}
#__psteps{list-style:none;margin:8px 0 0;padding:0;font-size:11px;font-weight:500}
#__psteps li{display:flex;align-items:center;gap:7px;padding:2.5px 0;opacity:.42;
 transition:opacity .3s}
#__psteps li.__on{opacity:1}
#__psteps li.__ok{opacity:.72}
#__psteps li em{font-style:normal;flex:1}
#__psteps li s{text-decoration:none;opacity:.6;font-variant-numeric:tabular-nums}
.__mk{width:13px;height:13px;border-radius:50%;border:1.5px solid rgba(255,255,255,.35);
 flex:0 0 auto;position:relative}
li.__ok .__mk{border-color:#3ddc97;background:#3ddc97}
li.__ok .__mk:after{content:'';position:absolute;left:3.6px;top:1.4px;width:3px;height:6px;
 border:solid #0E1740;border-width:0 1.7px 1.7px 0;transform:rotate(45deg)}
li.__on .__mk{border-color:#FF7A45;animation:__spin 1s linear infinite}
li.__on .__mk:after{content:'';position:absolute;left:-1.5px;top:-1.5px;right:-1.5px;
 bottom:-1.5px;border-radius:50%;border:1.5px solid transparent;border-top-color:#FF7A45}
@keyframes __spin{to{transform:rotate(360deg)}}
#__pfoot{margin-top:10px;padding-top:9px;border-top:1px solid rgba(255,255,255,.13);
 font-size:10.5px;opacity:.6;font-weight:500}
#__pfoot button{background:transparent;border:1px solid rgba(255,255,255,.3);color:#fff;
 border-radius:6px;padding:3px 9px;font:700 10.5px Inter,Arial;cursor:pointer;margin-left:6px}
@media(prefers-reduced-motion:reduce){
 .__dot,li.__on .__mk{animation:none}
 .__bar i{transition:none}}
</style>
<script>(function(){
var bar=document.getElementById('__bar'),b=document.getElementById('__rf'),
    u=document.getElementById('__upd'),panel=document.getElementById('__panel'),
    title=document.getElementById('__ptitle'),el=document.getElementById('__pel'),
    fill=document.getElementById('__pfill'),now=document.getElementById('__pnow'),
    steps=document.getElementById('__psteps'),foot=document.getElementById('__pfoot');
var t0=0,timer=null,poll=null,lastMs=null,built=false,cancelled=false;
function fmt(iso){if(!iso)return'';var d=new Date(iso);return 'Updated '+d.toLocaleString();}
function nfmt(n){return (typeof n==='number'?n:0).toLocaleString('en-IN');}
function mmss(s){var m=Math.floor(s/60);return m+':'+String(Math.floor(s%60)).padStart(2,'0');}

/* Weight the bar by the LAST run's per-phase timings. Equal weights on the first
   run, measured ones after that — a bar that lies about its pace is worse than no
   bar, because people learn to distrust it. */
function weights(phases){
 var w=[],tot=0,i;
 for(i=0;i<phases.length;i++){
  var ms=(lastMs&&lastMs[phases[i].k])||0; w.push(ms); tot+=ms;
 }
 if(tot<=0){for(i=0;i<w.length;i++)w[i]=1;tot=w.length;}
 for(i=0;i<w.length;i++)w[i]=w[i]/tot;
 return w;
}
function overall(p){
 var ph=p.phases||[],w=weights(ph),acc=0,i;
 for(i=0;i<ph.length;i++){
  if(i<p.phaseIndex)acc+=w[i];
  else if(i===p.phaseIndex){
   var frac=(p.total>0)?Math.min(1,p.done/p.total):0.35;
   acc+=w[i]*frac;break;
  }
 }
 return Math.max(0.02,Math.min(0.99,acc));
}
function buildSteps(p){
 if(built)return;built=true;
 steps.innerHTML=(p.phases||[]).map(function(x){
  return '<li data-k="'+x.k+'"><span class="__mk"></span><em>'+x.label+'</em><s></s></li>';
 }).join('');
}
function render(p){
 buildSteps(p);
 fill.style.width=Math.round(overall(p)*100)+'%';
 var det=(p.total>0)?(nfmt(p.done)+' of '+nfmt(p.total)):'';
 now.textContent=(p.label||'Working')+(det?' — '+det:'');
 var li=steps.querySelectorAll('li');
 for(var i=0;i<li.length;i++){
  li[i].className=(i<p.phaseIndex)?'__ok':(i===p.phaseIndex?'__on':'');
  var s=li[i].querySelector('s');
  s.textContent=(i===p.phaseIndex&&p.total>0)?(nfmt(p.done)+'/'+nfmt(p.total)):'';
 }
 if(p.note)foot.textContent=p.note;
}
function tick(){el.textContent=mmss((Date.now()-t0)/1000);}
function stop(){if(poll)clearInterval(poll);if(timer)clearInterval(timer);poll=timer=null;}

/* Keep the reader's place: a refresh should not cost them their tab, period and
   filters. Saved here, restored by the report on boot. */
function save(){
 try{
  var s={};
  if(typeof TAB!=='undefined')s.tab=TAB;
  if(typeof PR!=='undefined')s.period={mode:PR.mode,from:PR.from,to:PR.to,wd:PR.wd};
  if(typeof F!=='undefined')s.filters=JSON.parse(JSON.stringify(F));
  sessionStorage.setItem('__fl_state',JSON.stringify(s));
 }catch(e){}
}
function finish(ok,msg){
 stop();
 bar.classList.remove('__busy');bar.classList.add(ok?'__done':'__err');
 if(!ok){
  bar.classList.add('__busy');
  title.textContent='Refresh failed';fill.style.width='100%';
  now.textContent=msg||'The ETL did not complete.';
  foot.innerHTML='The report still shows the last good data.'+
   '<button id="__dismiss">Dismiss</button>';
  var dz=document.getElementById('__dismiss');
  if(dz)dz.onclick=function(){bar.className='__idle';b.disabled=false;
   b.innerHTML='&#8635; Refresh now';built=false;};
  return;
 }
 bar.classList.add('__busy');
 title.textContent='New data ready';fill.style.width='100%';
 var n=5;
 now.textContent='Reloading in '+n+'s to show it';
 foot.innerHTML='Your tab, period and filters are kept.'+
  '<button id="__stay">Stay here</button>';
 var st=document.getElementById('__stay');
 var cd=setInterval(function(){
  n--;
  if(cancelled){clearInterval(cd);return;}
  if(n<=0){clearInterval(cd);save();location.reload();return;}
  now.textContent='Reloading in '+n+'s to show it';
 },1000);
 if(st)st.onclick=function(){
  cancelled=true;clearInterval(cd);
  now.textContent='Reload when you are ready.';
  foot.innerHTML='<button id="__go">Reload now</button>';
  var g=document.getElementById('__go');
  if(g)g.onclick=function(){save();location.reload();};
 };
}
function look(){
 fetch('/status').then(function(r){return r.json();}).then(function(m){
  if(m.lastPhaseMs)lastMs=m.lastPhaseMs;
  if(m.progress)render(m.progress);
  if(!m.running){
   var okRun=(m.progress&&m.progress.ok!==false)&&m.ok!==false;
   finish(okRun,(m.progress&&m.progress.note)||m.error||'');
  }
 }).catch(function(){});
}
fetch('/status').then(function(r){return r.json();}).then(function(m){
 u.textContent=fmt(m.generatedAt)+(m.roster?(' · '+m.roster+' reps'):'');
 if(m.lastPhaseMs)lastMs=m.lastPhaseMs;
 if(m.running){start(true);}                 /* a refresh someone else began */
}).catch(function(){});
function start(already){
 bar.className='__busy';b.disabled=true;t0=Date.now();cancelled=false;
 title.textContent=already?'Refresh in progress':'Refreshing';
 tick();timer=setInterval(tick,1000);
 poll=setInterval(look,1200);look();
}
b.onclick=function(){
 start(false);
 fetch('/refresh',{method:'POST'}).then(function(r){return r.json();})
  .catch(function(){finish(false,'Could not reach the server.');});
};
})();</script>"""

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
    # progress.json is written by the ETL child process, so it is the only source
    # that knows what is happening inside a run. It also survives a worker restart,
    # which the in-memory _running flag does not.
    p = {}
    if os.path.exists(PROGRESS):
        try: p = json.load(open(PROGRESS))
        except Exception: p = {}
    if p:
        m["progress"] = p
    stale = True
    try:
        at = p.get("at") or ""
        if at:
            t = datetime.datetime.strptime(at[:19], "%Y-%m-%dT%H:%M:%S")
            stale = (datetime.datetime.utcnow() - t).total_seconds() > 120
    except Exception:
        stale = True
    m["running"] = bool(_running["v"] or (p.get("running") and not stale))
    if isinstance(m.get("phaseMs"), dict):
        m["lastPhaseMs"] = m["phaseMs"]       # the bar paces itself on the last run
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
