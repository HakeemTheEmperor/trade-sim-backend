# Deployment: Supabase + Render + custom domain

End-to-end guide for deploying `trade-sim-backend` on Render's free tier against
a Supabase Postgres database, with `trade-sim-app` on Vercel, both under a
shared parent domain so cookie auth works.

Order matters: create the database first (Render needs its URL), deploy the
backend second, then attach domains, then set up uptime pings.

---

## 0. Before you start

You need accounts on Supabase, Render, Vercel, and UptimeRobot, plus API keys for:

| Provider | Env var | Free-tier limit worth knowing |
|---|---|---|
| Financial Modeling Prep | `FMP_API_KEY` | ~250 requests/day; one full seed uses ~45 |
| Finnhub | `FINNHUB_API_KEY` | websocket, 1 connection |
| Massive (formerly Polygon.io) | `POLYGON_API_KEY` | 5 requests/min — this is why the backfill sleeps 20s per symbol |
| exchangerate-api.com | `EXCHANGE_RATE_API` | daily updates; app caches to ~1 request/day |
| Brevo (transactional email) | `BREVO_API_KEY` | 300 emails/day. Only used for signup OTPs, so ~1 per new user |

Generate a JWT secret now, you'll need it in step 2:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 1. Supabase

### 1.1 Create the project

1. [supabase.com](https://supabase.com) → **New project**.
2. Choose a region **close to your Render region** — every query crosses the
   public internet, so a mismatched pair (e.g. Supabase in Singapore, Render in
   Oregon) adds hundreds of milliseconds to every single database call.
3. Set a strong database password. **Avoid `@ : / ? # [ ] %` in it** — those are
   URL delimiters and will corrupt the connection string unless percent-encoded.
   If your password manager insists, encode it (`@` → `%40`) before pasting into
   the URI.
4. Save the password somewhere. Supabase shows it once.

### 1.2 Get the right connection string

Click **Connect** at the top of the dashboard. You'll see several options, and
picking the wrong one is the single most common way this deploy fails.

Use **Session pooler**:

```
postgresql://postgres.<project-ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres
```

Why this one:

- **Direct connection** (`db.<ref>.supabase.co:5432`) is **IPv6-only** on the
  free tier (IPv4 is a paid add-on). Render does not provide outbound IPv6, so
  this will fail to connect — usually with a confusing DNS or timeout error.
- **Transaction pooler** (port `6543`) doesn't support prepared statements or
  session-scoped state. This app holds long-lived connections (APScheduler jobs,
  the Finnhub websocket, Alembic migrations), so it needs session mode.
- **Session pooler** (port `5432`, `pooler.supabase.com` host) is IPv4 on all
  tiers and is documented for exactly this case: persistent backend servers.

Use this same URI everywhere — Render, migrations, seeding, and your own local
`psql`. There is no separate "seeding URL": seeding is just your Flask app
writing rows through SQLAlchemy, so it flows through `SQLALCHEMY_DATABASE_URI`
like everything else.

> The `https://<ref>.supabase.co` **API URL** shown in the dashboard is for
> Supabase's client SDKs and PostgREST. This app speaks plain Postgres and never
> uses it. Ignore it.

### 1.3 Connection budget

Free tier allows 200 pooler connections. One gunicorn worker with 4 threads plus
the scheduler and websocket uses well under 10. Fine as-is — revisit only if you
scale workers or instances.

---

## 2. Migrations

**You don't need to run these manually.** `bootstrap.sh` runs `flask db upgrade`
on every container start, before gunicorn binds. Alembic is idempotent: it reads
the `alembic_version` table, compares against `migrations/versions/`, and applies
only what's missing. On an already-current database it does nothing.

So the first Render deploy creates the entire schema by itself.

### Optional: run them from your machine first

Useful if you want to confirm the connection string works before dealing with
Render's build queue, or to see migration errors in a faster feedback loop:

```bash
cd trade-sim-backend
export SQLALCHEMY_DATABASE_URI="postgresql://postgres.<ref>:<pw>@aws-1-<region>.pooler.supabase.com:5432/postgres"
export RUN_BACKGROUND_JOBS=false   # don't trigger seeding/scheduler/websocket
export FLASK_APP=app.index
pipenv install
pipenv run flask db upgrade
```

`RUN_BACKGROUND_JOBS=false` matters: without it, building the app for the CLI
command also kicks off admin creation, seeding, and the websocket listener.

Verify in the Supabase dashboard → **Table Editor** that your tables exist.

### Migration hygiene going forward

- A failed migration stops the container (`set -e`), so the service stays down
  rather than serving against a half-migrated schema. That's intentional, but it
  makes schema changes your riskiest deploys — test against a scratch database
  first.
- Never add `db.create_all()`. Schema is Alembic-owned; tables created outside
  it will conflict with future migrations.
- Don't run migrations from two places at once. With one free instance this
  can't happen, but if you ever scale out, move migrations to a separate
  one-off job rather than running them on every boot.

---

## 3. Render

### 3.1 Create the service

1. [render.com](https://render.com) → **New → Web Service** → connect the
   `trade-sim-backend` GitHub repo.
2. Render detects the `Dockerfile`. Select **Docker** as the runtime.
3. Leave build and start commands **empty** — the Dockerfile's `CMD` runs
   `bootstrap.sh`, which migrates then starts gunicorn on `$PORT`.
4. Region: match your Supabase region from step 1.2.
5. Instance type: **Free**.

### 3.2 Environment variables

Add these under **Environment**. Values marked **required** have no default in
code — the app will crash on startup without them.

| Variable | Value | Notes |
|---|---|---|
| `SQLALCHEMY_DATABASE_URI` | session-pooler URI from 1.2 | **required** |
| `JWT_SECRET_KEY` | the random string from step 0 | **required** — anyone with it can forge tokens |
| `SWAGGER_URL` | `/docs` | **required** — read with no default in `create_app()` |
| `API_URL` | `/static/openapi.yaml` | **required** — same |
| `ADMIN_EMAIL` | your admin email | seeds the super-admin on first boot |
| `ADMIN_PASSWORD` | a strong password | change it after first login |
| `CORS_ORIGINS` | `https://app.imockmarket.toluwalase.me,http://localhost:5173` | comma-separated, never `*` |
| `JWT_COOKIE_SECURE` | `True` | |
| `JWT_COOKIE_SAMESITE` | `Lax` | see step 4 before finalizing |
| `RUN_BACKGROUND_JOBS` | `true` | |
| `LOG_LEVEL` | `INFO` | |
| `SQLALCHEMY_TRACK_MODIFICATIONS` | `False` | |
| `JWT_ACCESS_TOKEN_EXPIRES` | `6` | hours |
| `FMP_API_KEY` | your key | |
| `FINNHUB_API_KEY` | your key | |
| `FINNHUB_WS_URL` | `wss://ws.finnhub.io` | |
| `POLYGON_API_KEY` | your Massive/Polygon key | |
| `EXCHANGE_RATE_API` | `https://v6.exchangerate-api.com/v6/<your-key>` | no trailing `/latest` or `/pair` |
| `BREVO_API_KEY` | your Brevo v3 API key | **required in production** — without it signup OTPs are only written to the log, so nobody can verify. See `docs/email-verification.md` |
| `BREVO_SENDER_EMAIL` | `no-reply@imockmarket.toluwalase.me` | must be a sender Brevo has verified, or mail is accepted and silently dropped |
| `BREVO_SENDER_NAME` | `iMockMarket` | optional, defaults to `iMockMarket` |

Do **not** set `PORT` — Render injects it, and `bootstrap.sh` reads it.

Leave `POLYGON_BASE_URL`, `FMP_BASE_URL`, and `BREVO_BASE_URL` unset unless
you're pointing at a sandbox; the defaults in `app/integrations/providers.py`
are correct.

### 3.3 First deploy

Click **Create Web Service** and watch the logs. Expected sequence:

1. Docker build (~3-5 minutes; pipenv install is the slow part).
2. `flask db upgrade` — creates every table.
3. `Admin user created successfully`.
4. Gunicorn binds `$PORT` and Render marks the service live.
5. **In the background**, `initial-seed` starts: `No available stocks found;
   running initial stock seed`, then the history backfill.

The seed thread takes **15-20 minutes** on a fresh database (45 symbols × 20s
sleep for Massive's rate limit). This is deliberate — it runs off the main
thread so gunicorn can serve immediately instead of being killed by its 120s
worker-boot timeout.

### 3.4 Verify

```bash
curl https://<your-service>.onrender.com/health
# {"status":"ok"}
```

That endpoint runs `SELECT 1`, so a 200 confirms the app **and** the Supabase
connection. Also open `https://<your-service>.onrender.com/docs` for Swagger.

Once the logs show the seed finished, check `/api/v1/stocks` (or the Supabase
Table Editor) returns populated data.

### 3.5 Restart once after the first seed

**Do this — it's easy to miss.** `WebSocketListener.__init__` reads the symbol
list from `AvailableStocks` at construction time, which on a fresh database
happens *before* the background seed has written anything. It falls back to
`["AAPL"]`, so live prices only stream for Apple.

After the first seed completes, hit **Manual Deploy → Restart service**. The
listener then picks up all 45 symbols. This is a one-time fix — later restarts
find a populated table.

---

## 4. Domains

Cookie auth is the reason to bother with this. The JWT lives in an HttpOnly
cookie with `SameSite=Lax`, which browsers only send if the frontend and backend
share a **registrable domain**. `imockmarket.vercel.app` calling
`trade-sim.onrender.com` is cross-site: the cookie is silently dropped and every
authenticated request 401s.

Two ways out. Prefer the first.

### Option A — shared parent domain (recommended)

Put both under `toluwalase.me`:

- Frontend: `app.imockmarket.toluwalase.me` → Vercel
- Backend: `api.imockmarket.toluwalase.me` → Render

**Render side:**

1. Service → **Settings → Custom Domains → Add Custom Domain**.
2. Enter `api.imockmarket.toluwalase.me`.
3. Render shows a target. At your DNS provider add:
   `CNAME  api.imockmarket  →  <your-service>.onrender.com`
4. Wait for verification. Render issues a TLS certificate automatically (free
   tier included). Propagation is usually minutes, occasionally an hour.

**Vercel side:**

1. Project → **Settings → Domains → Add** `app.imockmarket.toluwalase.me`.
2. Add the `CNAME` Vercel gives you (typically `cname.vercel-dns.com`).

**Then update config on both sides:**

| Where | Variable | Value |
|---|---|---|
| Render | `CORS_ORIGINS` | `https://app.imockmarket.toluwalase.me,http://localhost:5173` |
| Render | `JWT_COOKIE_SAMESITE` | `Lax` |
| Render | `JWT_COOKIE_SECURE` | `True` |
| Vercel | `VITE_API_BASE_URL` | `https://api.imockmarket.toluwalase.me` |

`VITE_API_BASE_URL` is baked into the bundle at build time, so **redeploy the
frontend** after changing it — setting the variable alone does nothing.

### Locking traffic to the custom domain

Once the custom domain is verified and serving, you can turn off Render's
default URL: **Settings → Custom Domains → Render Subdomain → Disabled**.
Requests to `<service>.onrender.com` then receive a 404 at Render's edge without
reaching your app. It's reversible at any time.

Do it in this order, because the failure mode is quiet:

1. Confirm `https://api.imockmarket.toluwalase.me/health` returns `{"status":"ok"}`.
2. **Repoint UptimeRobot at the custom domain first.** A monitor still pointed at
   `.onrender.com` when you disable it will 404 forever — which means false
   alerts, and no keep-alive traffic, so Render sleeps and Supabase pauses after
   a week.
3. Confirm the frontend has been rebuilt with the new `VITE_API_BASE_URL`.
4. Then disable the subdomain.

### Option B — cross-site cookies (fallback)

If you keep `.vercel.app` / `.onrender.com`, set `JWT_COOKIE_SAMESITE=None` and
`JWT_COOKIE_SECURE=True`. Understand the cost: Safari blocks third-party cookies
by default, Chrome's tracking protection may too, and Firefox partitions them.
Auth will work for some users and mysteriously fail for others. Use Option A.

### CSRF note

`JWT_COOKIE_CSRF_PROTECT` is on, so state-changing requests must echo the
`csrf_access_token` cookie as an `X-CSRF-TOKEN` header. If logins succeed but
POSTs return 401, that's the cause — not CORS.

---

## 5. UptimeRobot keep-alive

Two independent idle timers threaten this stack:

- **Render** spins the free instance down after **15 minutes** without traffic.
- **Supabase** pauses free projects after **7 days** without *database* activity,
  and resuming requires a manual click in the dashboard.

One monitor handles both, because `/health` executes a real query:

1. [uptimerobot.com](https://uptimerobot.com) → **Add New Monitor**.
2. Type **HTTP(s)**, URL `https://api.imockmarket.toluwalase.me/health`.
3. Interval **5 minutes** — the free-tier minimum, comfortably under Render's
   15-minute threshold.
4. Optionally add an alert contact so you hear about real outages.

Point the monitor at a DB-touching endpoint. Pinging a static route would keep
Render awake while Supabase quietly pauses after a week.

---

## 6. Things to watch out for

**750 instance-hours per month covers exactly one always-on service.** A month is
~730 hours, so one keep-alive'd service fits. Deploy a second free service and
they'll exhaust the pool together and start sleeping.

**Cold starts are expensive here.** A spun-down instance takes ~1 minute to come
back, and startup re-runs migrations plus admin seeding before serving. The first
request after a sleep may exceed UptimeRobot's timeout and register a false
"down". More importantly, the scheduler and websocket only run while the instance
is up — sleep means no live prices.

**The seed skips when tables are non-empty.** `run_initial_seed` checks whether
`AvailableStocks` and `StockHistory` are empty and skips if not, so restarts are
cheap and don't burn FMP quota. Trade-off: a symbol added to `DataSeed`'s default
list won't appear until the nightly scheduler job (00:00 UTC) runs.

**Seed failures are non-fatal by design.** They log and let the nightly job
retry. So check logs after the first deploy rather than assuming success —
`Initial seed failed` scrolls past without taking the service down.

**Don't increase gunicorn workers.** `bootstrap.sh` pins `--workers 1` because
APScheduler and the websocket listener start inside `create_app()`; a second
worker duplicates both, double-writing prices. To scale, set
`RUN_BACKGROUND_JOBS=false` on the extra instances so only one runs jobs.

**Rotate any secrets that were ever committed.** Everything belongs in Render's
Environment tab. If a real `.env` ever landed in git, rotate those keys — the
JWT secret especially, since it forges tokens for any user or role.

**Free deploys have downtime.** Render free has no zero-downtime rollout, so
every push produces a brief outage and possibly an UptimeRobot alert. Harmless.

**Watch the storage caps.** Supabase free is 500 MB. `StockHistory` is pruned to
a 30-day window by `update_price_history`, so it stays bounded — but keep an eye
on it if you widen that window or add symbols.

**Change the admin password after first login.** `ADMIN_PASSWORD` seeds a
`SUPER_ADMIN` account on first boot and sits in Render's environment as
plaintext.

---

## 7. Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| Deploy fails at `flask db upgrade`, DNS/timeout error | Using the direct connection (IPv6) instead of the session pooler |
| `password authentication failed` | Unencoded special character in the password inside the URI |
| Crash on boot, `KeyError`/`None` around Swagger | `SWAGGER_URL` or `API_URL` not set |
| Service builds but Render says "no open ports" | `$PORT` not being used — check `bootstrap.sh` wasn't reverted |
| Login works, POSTs 401 | Missing `X-CSRF-TOKEN` header, or cross-site cookie dropped (see step 4) |
| Only AAPL prices update live | Websocket started before the seed — restart the service (step 3.5) |
| `/api/v1/stocks` empty long after deploy | Seed thread failed; search logs for `Initial seed failed` |
| `NotNullViolation` on `available_stocks` during seed | A provider field came back `None`. The seed now skips such symbols and logs `Skipping <SYM>, provider omitted: ...` — check whether FMP renamed a field |
| Price history empty, everything else fine | Massive/Polygon key invalid or rate-limited; check `Failed to update price history` |
| Everything 503 after a week away | Supabase project paused — unpause in the dashboard, then check the uptime monitor |
