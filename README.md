# Hive Frontline — Live Rx BI Report

Hosts the interactive field-force report live, the same way your `channel-health`
service runs on Render. It pulls from the Frontline backend, keeps an **incremental
store** so it never re-pulls all of history, and serves the report **instantly**.
A background thread (and a "Refresh now" button) keeps it current.

## How it works
- `etl.py` — logs in with a service account, enumerates the **full roster** via name-search
  (so the broken list-pagination can't drop reps), pulls geo + day-plans + visit detail for
  everything since `LIFETIME_START`, and stores it in SQLite on a persistent disk. Each run
  only fetches **new/changed** day-plans, then recomputes and renders `report.html`.
- `app.py` — Flask app. Serves the cached report instantly behind auth, exposes
  `POST /refresh` (background) and `GET /status`, and runs the background refresh loop.
- `template.html` — the report UI (filters, Doctors × Rep tab, all tabs).

## What you provide
1. **A read-only Frontline service account** (e.g. `svc_analytics@britishbiologicals.com`).
   Ask the Frontline team to create it with report/read access only — not superadmin.
2. **Auth for the report.** Either:
   - Microsoft (Entra) SSO restricted to your tenant — recommended; or
   - a shared password (`REPORT_PASSWORD`) to start, add SSO later.

## Deploy to Render (Blueprint)
1. Push this folder to a new **private** GitHub repo.
2. Render → **New +** → **Blueprint** → pick the repo. It reads `render.yaml` and creates
   the web service + a 2 GB persistent disk (Singapore, same region as channel-health).
3. In the service's **Environment**, fill the secrets (`sync:false` keys):
   `FRONTLINE_ORG_ID`, `FRONTLINE_SVC_EMAIL`, `FRONTLINE_SVC_PASSWORD`, and either the
   Microsoft SSO keys **or** `REPORT_PASSWORD`.
4. First boot runs the **lifetime backfill** (a few minutes). After that, page loads are
   instant and refreshes are incremental (seconds–minutes depending on new activity).

### Microsoft SSO setup (if using it)
- Entra admin center → **App registrations → New registration**.
- Redirect URI (Web): `https://<your-service>.onrender.com/auth/callback`.
- Copy **Application (client) ID** → `MS_CLIENT_ID`, **Directory (tenant) ID** → `MS_TENANT_ID`.
- **Certificates & secrets → New client secret** → value → `MS_CLIENT_SECRET`.
- `ALLOWED_EMAIL_DOMAIN=britishbiologicals.com` limits access to your domain.

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in the values
set -a && . ./.env && set +a
python etl.py             # one backfill/refresh (prints stats JSON)
python app.py             # serve at http://localhost:8000
```

## Notes
- The web service uses **1 worker / many threads** on purpose, so the background refresh
  thread and its lock live in one process. Keep it on Render **Starter** (always-on); the
  free tier spins down and would drop the timer.
- `LIFETIME_START` controls how far back the backfill goes. Set it to the first month
  Frontline has data for.
- The report contains doctor names — keep it behind SSO/password; don't make the URL public.
