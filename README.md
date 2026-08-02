# iMockMarket — Backend (`trade-sim-backend`)

The REST API behind **iMockMarket**, a stock-trading simulator where players
trade real market data with fake money and are ranked against their friends.

Built with Flask + PostgreSQL. It owns the entire domain: accounts and sessions,
wallets in multiple currencies, buy/sell execution with realistic trading costs,
live and historical price data pulled from three market-data providers, social
"shadow" links, and seasonal leaderboards.

| | |
|---|---|
| **Frontend repo** | https://github.com/HakeemTheEmperor/trade-sim-app |
| **Backend repo** (this one) | https://github.com/HakeemTheEmperor/trade-sim-backend |
| **Live app** | https://app.imockmarket.toluwalase.me |
| **Live API** | https://api-imockmarket.toluwalase.me/api/v1 |
| **API docs (Swagger UI)** | https://api-imockmarket.toluwalase.me/docs |

---

## Table of contents

- [What this service does](#what-this-service-does)
- [Architecture](#architecture)
  - [Request flow](#request-flow)
  - [Layers](#layers)
  - [Project structure](#project-structure)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Run with Docker (recommended)](#run-with-docker-recommended)
  - [Run locally without Docker](#run-locally-without-docker)
  - [First-run behaviour](#first-run-behaviour)
- [Configuration](#configuration)
  - [Required variables](#required-variables)
  - [Market-data providers](#market-data-providers)
  - [Variables that fail quietly](#variables-that-fail-quietly)
- [Database](#database)
  - [Data model](#data-model)
  - [Migrations](#migrations)
- [API reference](#api-reference)
  - [Conventions](#conventions)
  - [Endpoints](#endpoints)
- [Authentication and security](#authentication-and-security)
- [The simulated economy](#the-simulated-economy)
- [Background jobs and market data](#background-jobs-and-market-data)
- [Deployment](#deployment)
- [Further documentation](#further-documentation)
- [Contributing](#contributing)
- [License](#license)

---

## What this service does

| Capability | Summary |
|---|---|
| **Accounts** | Signup gated behind a 6-digit emailed OTP; sign-in issues a JWT in an HttpOnly cookie. Roles: `USER`, `ADMIN`, `SUPER_ADMIN`. |
| **Wallets** | Multi-currency cash wallets. Every new account is created with `100,000.00` in a USD wallet; additional wallets start at `0`. |
| **Trading** | Buy and sell against live prices, with a bid-ask half-spread applied on each side and fractional quantities supported. |
| **Market data** | ~45 seeded symbols, real-time prices over a Finnhub websocket, nightly fundamentals refresh and daily price-history backfill. |
| **Portfolio** | Holdings, per-symbol quantity, equity valuation, and a paginated transaction ledger. |
| **Watchlist** | Per-user symbol watchlist. |
| **Shadows** | Mutual opt-in links that let one player follow another's activity, with invite/accept/decline and notifications. |
| **Leagues & leaderboards** | Named, join-code leagues (max 50 members, 5 leagues per user) ranked by percentage return over 90-day seasons. |
| **Notifications** | In-app notification feed with unread counts. |

---

## Architecture

### Request flow

```
Browser (trade-sim-app)
   │  fetch(..., credentials: "include") + X-CSRF-TOKEN header
   ▼
Cloudflare ──► Render ──► ProxyFix (recovers the real client IP)
                            │
                            ▼
                       Flask app  (app/__init__.py: create_app)
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
        CORS + security  JWT cookie    rate limiter
          headers        + CSRF        (per IP / user)
                            │
                            ▼
                    Blueprint  (app/routes/*)      ← HTTP shape only
                            │
                            ▼
                    Service   (app/services/*)     ← business rules
                            │
                            ▼
                    Model     (app/models/*)       ← SQLAlchemy ORM
                            │
                            ▼
                      PostgreSQL

Alongside the request path, inside the same process:
  • APScheduler  — nightly seed, history backfill, equity snapshots, season roll
  • WebSocketListener — streams Finnhub trades into stock_price
```

### Layers

The codebase keeps a strict three-layer split. When adding a feature, add one
file per layer rather than growing a route:

| Layer | Directory | Responsibility | Must not |
|---|---|---|---|
| **Routes** | `app/routes/` | Parse and validate the request, call one service, shape the JSON response, apply `@jwt_required` and `@rate_limit`. | Contain business rules or touch `db.session`. |
| **Services** | `app/services/` | All business logic, transactions, and invariants (ownership checks, fee maths, ranking). Raise domain exceptions from `app/custom_exceptions.py`. | Know about `request`, `jsonify`, or HTTP status codes. |
| **Models** | `app/models/` | SQLAlchemy table definitions, enums, relationships, and small row-level helpers. | Contain multi-entity workflows. |

Errors are converted to HTTP responses in exactly one place —
`app/error_handlers.py` — so a service can raise a domain error without knowing
what status code it becomes.

### Project structure

```
trade-sim-backend/
├── app/
│   ├── __init__.py              # create_app(): config, extensions, blueprints, startup jobs
│   ├── index.py                 # WSGI entrypoint (`app.index:app`) used by gunicorn
│   ├── custom_exceptions.py     # Domain exceptions raised by services
│   ├── error_handlers.py        # The single exception → HTTP response mapping
│   ├── data_seed.py             # Seeds available stocks + fundamentals from FMP
│   ├── websocket_listener.py    # Finnhub real-time trade stream → stock_price
│   ├── integrations/
│   │   └── providers.py         # Every external endpoint URL, in one place
│   ├── models/                  # SQLAlchemy models (one file per table group)
│   ├── routes/                  # Flask blueprints, all mounted under /api/v1
│   ├── services/                # Business logic
│   ├── utils/
│   │   ├── auth_utils.py        # Role decorators, identity helpers
│   │   ├── enums_utils.py       # Shared enums
│   │   ├── fees.py              # Trade half-spread and FX spread maths
│   │   ├── rate_limit.py        # In-memory fixed-window limiter
│   │   ├── update_history.py    # Daily price-history backfill (Massive/Polygon)
│   │   └── validation_utils.py  # Input validation helpers
│   ├── static/openapi.yaml      # OpenAPI 3 spec served at /openapi.yaml
│   └── docs/                    # Additional spec fragments
├── migrations/                  # Alembic; the schema is owned here, not by create_all
├── docs/                        # Design and operations write-ups (see below)
├── Dockerfile
├── docker-compose.yml
├── bootstrap.sh                 # `flask db upgrade` then exec gunicorn
├── Pipfile / Pipfile.lock
└── .env.example                 # Every variable, annotated — start here
```

---

## Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.13 |
| Web framework | Flask |
| ORM / migrations | Flask-SQLAlchemy, Flask-Migrate (Alembic) |
| Database | PostgreSQL 16 |
| Auth | flask-jwt-extended (JWT in HttpOnly cookies + double-submit CSRF) |
| Scheduling | APScheduler (`BackgroundScheduler`) |
| Realtime | `websocket-client` against Finnhub |
| API docs | OpenAPI 3 + flask-swagger-ui |
| Server | gunicorn (1 worker, 4 threads) |
| Packaging | pipenv, Docker |
| Hosting | Render (app), Supabase (Postgres), Cloudflare (DNS/proxy) |

---

## Getting started

### Prerequisites

**With Docker (recommended)**

- [Docker](https://www.docker.com/get-started/) and Docker Compose. Compose ships
  with Docker Desktop; on Linux see the
  [install guide](https://docs.docker.com/compose/install/).

**Without Docker**

- [Python 3.13](https://www.python.org/downloads/)
- `pip` (bundled with Python — check with `pip --version`)
- `pipenv` — `pip install pipenv --user`
- A PostgreSQL 16 instance you can reach

### Run with Docker (recommended)

```bash
git clone https://github.com/HakeemTheEmperor/trade-sim-backend.git
cd trade-sim-backend

cp .env.example .env        # then edit — see Configuration below
docker compose up --build
```

The API is then available at **http://localhost:5000**, with Swagger UI at
**http://localhost:5000/docs** and a health probe at
**http://localhost:5000/health**.

To stop, and to also drop the Postgres volume:

```bash
docker compose down          # stop
docker compose down -v       # stop and delete the database volume
```

### Run locally without Docker

```bash
pipenv install --dev
cp .env.example .env         # point SQLALCHEMY_DATABASE_URI at your own Postgres

export FLASK_APP=app.index
RUN_BACKGROUND_JOBS=false pipenv run flask db upgrade   # apply migrations
pipenv run flask run --port 5000                        # or: ./bootstrap.sh
```

`RUN_BACKGROUND_JOBS=false` is important for any `flask db …` command: it stops
`create_app()` from starting the seeder, scheduler and websocket, which would
otherwise try to query tables the migration is about to create.

### First-run behaviour

On the first boot against an empty database the app will:

1. Create the super-admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (already
   verified — it never goes through the OTP flow).
2. Open a leaderboard season and enrol existing accounts.
3. Start a **background thread** that seeds ~45 symbols from FMP and backfills
   price history from Massive/Polygon. This takes roughly **15 minutes**,
   because the backfill sleeps 20s between symbols to respect a 5 req/min free
   tier. The API serves traffic normally throughout; stock endpoints just return
   little until it finishes.

Both jobs are skipped when the tables are already populated, so restarts are
cheap — important, since one full seed uses ~45 of FMP's 250 daily requests.

---

## Configuration

All configuration is environment variables, loaded from `.env` via
python-dotenv (and by `docker-compose` through `env_file`).

**[`.env.example`](.env.example) is the authoritative reference.** It documents
every variable, the reasoning behind each default, and the failure mode of
getting it wrong. The tables below are a summary.

### Required variables

| Variable | Purpose |
|---|---|
| `SQLALCHEMY_DATABASE_URI` | Postgres connection string. Overridden by `docker-compose` from the `POSTGRES_*` values so the two can't drift. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Credentials for the composed `db` service. |
| `JWT_SECRET_KEY` | Signs every JWT. Must be long and random — anyone holding it can forge a token for any user or role. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seed super-admin created on startup. |
| `CORS_ORIGINS` | Comma-separated allowed browser origins. Never `*` — cookie auth uses credentialed requests. |

### Market-data providers

Every provider URL is assembled in one module,
[`app/integrations/providers.py`](app/integrations/providers.py); only keys and
optional base overrides live in the environment.

| Provider | Variable | Used for | Free-tier limit that shaped the design |
|---|---|---|---|
| Financial Modeling Prep | `FMP_API_KEY` | Seeding symbols, company profiles, market caps | ~250 req/day; one seed ≈ 45 |
| Finnhub | `FINNHUB_API_KEY` | Real-time price websocket | 1 connection — hence the single gunicorn worker |
| Massive (formerly Polygon.io) | `POLYGON_API_KEY` | Daily price-history backfill | 5 req/min — hence the 20s sleep per symbol |
| exchangerate-api.com | `EXCHANGE_RATE_API` | Cross-currency wallet transfers | Daily refresh; rates cached to ~1 req/day |
| Brevo | `BREVO_API_KEY` | Signup verification emails | 300 emails/day |

> **Local development needs none of these to sign up.** Leave `BREVO_API_KEY`
> unset and the OTP is written to the server log at WARNING level (`code=123456`)
> instead of being emailed, so the whole verification flow works without a Brevo
> account. In production it is required — without it signup still returns `201`
> and no user can ever verify.

### Variables that fail quietly

These three are worth reading about before deploying, because getting them wrong
produces a *misleading* symptom rather than an obvious error:

| Variable | Wrong value looks like | Correct value |
|---|---|---|
| `JWT_COOKIE_DOMAIN` | Browsing works fine, but **any action logs the user out**. (The access cookie is still sent; the CSRF cookie can't be read by JS on another host, so the API answers `401 Missing CSRF token` and the client treats it as an expired session.) | The shared parent with a leading dot, e.g. `.toluwalase.me`, whenever the frontend and API are on different subdomains. Empty for localhost. |
| `TRUSTED_PROXY_HOPS` | Too low: every client collapses onto one infrastructure IP and rate limits over-restrict. Too high: **silently exploitable** — the extra `X-Forwarded-For` entry is client-controlled, so anyone can forge an IP and walk past the limiter. | Measure it. `0` local, `2` Render only, `3` Cloudflare-proxied → Render. Verify with `LOG_CLIENT_IP=true`, then turn it back off. |
| `VITE_API_BASE_URL` (frontend) | Every endpoint 404s, surfacing in the browser as a **CORS preflight failure**, not a 404. `/health` still returns 200, so the base URL looks fine. | Must include the `/api/v1` prefix. |

---

## Database

### Data model

```
users ──┬── wallets ────────────┬── transactions
        │   (multi-currency,    │   (BUY / SELL / TRANSFER, with fee + currency)
        │    100k USD at signup)│
        ├── users_stock_wallet ──── available_stocks ──┬── stock_price
        │   (holdings)                                 └── stock_history
        ├── watchlists ──────────── available_stocks
        ├── email_verification_codes   (hashed OTP, expiry, attempt counter)
        ├── shadow_links               (subject ↔ shadow, PENDING/ACCEPTED)
        ├── notifications              (typed, JSON payload, read flag)
        ├── league_memberships ──── leagues        (join code, owner, member cap)
        ├── season_participants ─── seasons        (baseline equity per season)
        └── equity_snapshots           (nightly cash / holdings / equity)

revoked_tokens   — JWT blocklist by jti, checked on every request
exchange_rates   — cached FX pairs with the provider's own next_update
```

Notes worth knowing before you touch a query:

- **All money is `Numeric`, never `float`.** Balances, prices, fees and equity
  are `Decimal` end to end; a custom Flask JSON provider serialises them as JSON
  numbers so response shapes are unchanged. See
  [`docs/money-decimal-and-migrations.md`](docs/money-decimal-and-migrations.md).
- **Quantities are fractional** (`Numeric(15, 6)`), so partial shares work.
- Every user-owned table cascades on user delete.

### Migrations

The schema is owned by Alembic, **not** `db.create_all()`.

```bash
export FLASK_APP=app.index

# Create a migration after changing a model
RUN_BACKGROUND_JOBS=false pipenv run flask db migrate -m "short description"

# Review the generated file in migrations/versions/ — always. Autogenerate
# misses enum changes, server defaults and index renames.

RUN_BACKGROUND_JOBS=false pipenv run flask db upgrade   # apply
RUN_BACKGROUND_JOBS=false pipenv run flask db downgrade # roll back one
```

`bootstrap.sh` runs `flask db upgrade` on every container start, so deploys
apply migrations automatically before gunicorn binds its port.

---

## API reference

Interactive docs are served by the app itself at **`/docs`** (Swagger UI), backed
by the OpenAPI 3 spec at **`/openapi.yaml`**. That route rewrites the `servers:`
entry from `PUBLIC_API_BASE_URL` at request time, so "Try it out" targets the
deployed host rather than the localhost value committed to the file.

### Conventions

- **Base path:** every blueprint is mounted under `/api/v1`. `/health` and
  `/openapi.yaml` are the only routes outside it.
- **Auth:** send the session cookie (`credentials: "include"` in the browser).
  State-changing requests must additionally echo the readable
  `csrf_access_token` cookie as an `X-CSRF-TOKEN` header.
- **Responses:** JSON. Successful payloads are wrapped as `{"data": …}`; errors
  are `{"error": "message"}`.
- **Money:** JSON numbers, computed as `Decimal` server-side.

### Endpoints

**Auth** — `/api/v1/auth`

| Method | Path | Auth | Rate limit | Description |
|---|---|---|---|---|
| `POST` | `/signup` | — | 10 / 60s | Create an account; emails a 6-digit OTP. Returns `201` with **no session**. |
| `POST` | `/verify-email` | — | 10 / 300s | Exchange the OTP for an active account and a session cookie. |
| `POST` | `/resend-otp` | — | 3 / 300s | Re-issue a verification code. |
| `POST` | `/signin` | — | 5 / 60s | Sign in. Sets the JWT + CSRF cookies. `403 ACCOUNT_UNVERIFIED` if the OTP was never entered. |
| `GET` | `/me` | ✔ | — | Current user, read from the database (not from JWT claims, so profile edits are reflected immediately). |
| `POST` | `/logout` | ✔ | — | Revoke the token (added to the `revoked_tokens` blocklist) and clear cookies. |
| `POST` | `/reset-password` | ✔ | 5 / 300s | Change password. |
| `POST` | `/admin-signup` | admin | — | Create an elevated account. |

**Stocks & trading** — `/api/v1/stocks`

| Method | Path | Auth | Rate limit | Description |
|---|---|---|---|---|
| `GET` | `/all` | ✔ | — | Paginated, sortable list of tradable symbols. |
| `GET` | `/symbol/<symbol>` | ✔ | — | One stock with its current price. |
| `GET` | `/id/<id>` | ✔ | — | Same, by internal id. |
| `GET` | `/search/symbol/<symbol>` | ✔ | — | Symbol search. |
| `GET` | `/search/company/<name>` | ✔ | — | Company-name search. |
| `GET` | `/stock/price/<symbol>` | ✔ | — | Latest price only. |
| `GET` | `/stock/history/<symbol>` | ✔ | — | Daily close history for charts. |
| `POST` | `/buy` | ✔ | 30 / 60s | Buy. Executes **above** the quote by the half-spread. |
| `POST` | `/sell` | ✔ | 30 / 60s | Sell. Executes **below** the quote by the half-spread. |
| `GET` | `/user` | ✔ | — | All holdings. |
| `GET` | `/user/quantity/<symbol>` | ✔ | — | Held quantity for one symbol. |
| `GET` | `/portfolio` | ✔ | — | Valued portfolio (cash + holdings + equity). |

**Wallets** — `/api/v1/wallet`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/all` | ✔ | All wallets for the caller. |
| `GET` | `/<wallet_id>` | ✔ | One wallet. |
| `POST` | `/create` | ✔ | Create a wallet in another currency (starts at `0`). |
| `DELETE` | `/delete` | ✔ | Delete a wallet. |
| `POST` | `/transfer` | ✔ | Move money **between your own wallets only**; cross-currency transfers pay the FX spread. |

**Transactions** — `/api/v1/transactions`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/history` | ✔ | Paginated ledger, filterable by wallet and currency. |
| `GET` | `/transaction/<id>` | ✔ | One transaction, including the fee charged. |

**Watchlist** — `/api/v1/watchlist`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/get` | ✔ | The caller's watchlist. |
| `POST` | `/add/<symbol>` | ✔ | Add a symbol. |
| `DELETE` | `/delete/<symbol>` | ✔ | Remove a symbol. |
| `GET` | `/check/<symbol>` | ✔ | Whether a symbol is watched. |

**Shadows (social)** — `/api/v1/shadow`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/invite` | ✔ | Invite another user to link. |
| `POST` | `/invite/<link_id>/accept` | ✔ | Accept an invite. |
| `POST` | `/invite/<link_id>/decline` | ✔ | Decline an invite. |
| `GET` | `/invites` | ✔ | Incoming invites. |
| `GET` | `/shadows` | ✔ | Users shadowing you. |
| `DELETE` | `/shadows/<link_id>` | ✔ | Remove a shadow. |
| `GET` | `/following` | ✔ | Users you shadow. |
| `DELETE` | `/following/<link_id>` | ✔ | Stop following. |

**Leagues & leaderboard** — `/api/v1/leagues`, `/api/v1/leaderboard`

| Method | Path | Auth | Rate limit | Description |
|---|---|---|---|---|
| `GET` | `/leagues` | ✔ | — | Leagues you belong to. |
| `POST` | `/leagues` | ✔ | 10 / 3600s | Create a league; returns its join code. |
| `POST` | `/leagues/join` | ✔ | 10 / 300s | Join by code. |
| `GET` | `/leagues/<id>` | ✔ | — | Season standings, computed live. |
| `GET` | `/leagues/<id>/career` | ✔ | — | All-time standings. |
| `DELETE` | `/leagues/<id>/leave` | ✔ | — | Leave a league. |
| `DELETE` | `/leagues/<id>` | ✔ | — | Delete a league (owner only, and only while empty). |
| `GET` | `/leaderboard/season` | ✔ | — | The current season window. |

**Users, notifications, config, ops**

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/user` | ✔ | Profile. |
| `POST` | `/api/v1/users/user/edit` | ✔ | Edit profile. |
| `GET` | `/api/v1/users/all` | admin | List users. |
| `GET` | `/api/v1/notifications/` | ✔ | Notification feed. |
| `GET` | `/api/v1/notifications/unread-count` | ✔ | Unread badge count. |
| `POST` | `/api/v1/notifications/<id>/read` | ✔ | Mark one read. |
| `POST` | `/api/v1/notifications/read-all` | ✔ | Mark all read. |
| `GET` | `/api/v1/config/trading` | ✔ | Current spread/fee rates, so the client can show costs before a trade instead of hardcoding them. |
| `GET` | `/health` | — | Liveness probe. Runs `SELECT 1`, so pinging it also keeps the free-tier database from idling. |

---

## Authentication and security

**Sessions.** The JWT lives in an **HttpOnly cookie**, not `localStorage`, so
JavaScript — and therefore any XSS — cannot read it. Access tokens last 6 hours
by default (`JWT_ACCESS_TOKEN_EXPIRES`) and logout adds the token's `jti` to a
`revoked_tokens` blocklist that is consulted on every authenticated request.

**CSRF.** Because the cookie is sent automatically, cookie auth needs CSRF
protection. flask-jwt-extended's double-submit scheme is enabled: a second,
JS-readable `csrf_access_token` cookie must be echoed as an `X-CSRF-TOKEN`
header on every `POST`/`PUT`/`PATCH`/`DELETE`. The frontend does this centrally
in `apiClient.ts`. See
[`docs/httponly-cookie-migration.md`](docs/httponly-cookie-migration.md).

**Rate limiting.** A dependency-free, in-memory fixed-window limiter
(`app/utils/rate_limit.py`) keyed by client IP or user id, applied to the
endpoints listed above. It is process-local by design, which is adequate for the
single-worker deployment; scaling to multiple workers means moving the counters
to a shared store such as Redis. Counters reset on deploy and on free-tier
spin-down.

**Client IP.** `ProxyFix` is configured with a measured `TRUSTED_PROXY_HOPS` so
the limiter sees the real client address rather than the edge's. See the warning
in [Variables that fail quietly](#variables-that-fail-quietly) and
[`docs/rate-limiting-and-hardening-plan.md`](docs/rate-limiting-and-hardening-plan.md).

**Response headers.** Every response carries `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and HSTS.

**Information disclosure.** Endpoints are deliberately vague where being helpful
would leak: sign-in doesn't distinguish an unknown email from a wrong password,
and a failed transfer returns the same message whether the wallet doesn't exist
or isn't yours — so the endpoint can't be used to enumerate wallet ids or
owners. Auth rejections are logged in full server-side, because three very
different production failures otherwise look identical.

---

## The simulated economy

The leaderboard only means something if real-world wealth can't buy rank, so the
economy is **closed**. Three rules enforce that, and all three are load-bearing:

1. **No deposits.** `DEPOSIT` and `WITHDRAWAL` exist in the transaction enum but
   are referenced nowhere. Money enters an account exactly once: the
   `100,000.00` default balance at signup.
2. **Transfers are own-wallet only.** `transfer_funds` verifies that *both*
   wallets belong to the caller. Validating only the sender was the one hole in
   an otherwise closed economy — and, with a leaderboard, an obvious collusion
   route.
3. **Trading costs money**, so there is no free-value loop to grind.

| Cost | Default | Applies to |
|---|---|---|
| `TRADE_HALF_SPREAD` | `0.0005` (5bp per side, ~0.1% round trip) | Buys execute above the quote, sells below |
| `FX_SPREAD` | `0.005` (0.5%) | Cross-currency transfers only |

Spreads rather than commissions, because flat commissions are largely gone from
US retail while the bid-ask spread is always present — and it is the cost retail
traders least understand, which makes it the one worth teaching.

**Leaderboards** rank by percentage return over 90-day seasons
(`SEASON_LENGTH_DAYS`). Money persists across seasons; only the ranking resets,
rebaselining to the equity you hold when the season opens. Accounts created
within `SEASON_JOIN_GRACE_DAYS` (30) of the open are enrolled immediately with
their own starting equity as baseline — without that window, signing up a minute
after a season opened would make you unrankable for a whole quarter.

Full reasoning, including the tie-handling and known gaps:
[`docs/economy-and-leaderboards.md`](docs/economy-and-leaderboards.md).

---

## Background jobs and market data

Started inside `create_app()` and gated behind `RUN_BACKGROUND_JOBS`, so CLI
commands and any additional web workers don't duplicate them.

| Job | Schedule | What it does |
|---|---|---|
| `DataSeed.load_available_stocks` | 00:00 daily | Refresh symbols, profiles and market caps from FMP. |
| `UpdateHistory.update_price_history` | 00:05 daily | Backfill daily closes from Massive/Polygon, sleeping 20s per symbol for the rate limit. |
| `LeaderboardService.snapshot_all` | 01:00 daily | Snapshot each user's cash, holdings and equity — deliberately *after* the price refresh, so equity is valued against today's prices. |
| `LeaderboardService.ensure_season` | 01:30 daily | Roll into the next season once the current one lapses. A missed run self-corrects the next day. |
| `WebSocketListener` | continuous | Streams Finnhub trades and writes them into `stock_price`. |

> **Why a single gunicorn worker.** The scheduler and the websocket both start in
> `create_app()`, and Finnhub's free tier allows one connection. Extra workers
> would duplicate the jobs and break the socket. Concurrency comes from threads
> (`--threads 4`) instead. If you ever scale horizontally, run the extra
> instances with `RUN_BACKGROUND_JOBS=false`.

---

## Deployment

Production runs on **Render** (app) against **Supabase** Postgres, behind
**Cloudflare**, with the frontend on **Vercel** — both under a shared parent
domain so cookie auth works.

`bootstrap.sh` is the container entrypoint: it applies migrations, then execs
gunicorn bound to `$PORT` (never set `PORT` in `.env` — the platform injects it,
and overriding it reads as "no open ports detected" and fails the deploy).

A complete, step-by-step runbook — database creation, connection-string
gotchas, every environment variable with its production value, custom domains,
the cookie-domain trap, and UptimeRobot keep-alive pings — lives in
**[`docs/deployment.md`](docs/deployment.md)**. Start there rather than
improvising; several steps fail in non-obvious ways.

---

## Further documentation

| Document | Read it when |
|---|---|
| [`docs/deployment.md`](docs/deployment.md) | Deploying, or debugging anything environment-shaped. |
| [`docs/economy-and-leaderboards.md`](docs/economy-and-leaderboards.md) | Touching money, fees, seasons or rankings. |
| [`docs/email-verification.md`](docs/email-verification.md) | Working on signup, OTPs, or Brevo. |
| [`docs/httponly-cookie-migration.md`](docs/httponly-cookie-migration.md) | Working on auth, cookies or CSRF. |
| [`docs/money-decimal-and-migrations.md`](docs/money-decimal-and-migrations.md) | Adding a money column, or writing a migration. |
| [`docs/rate-limiting-and-hardening-plan.md`](docs/rate-limiting-and-hardening-plan.md) | Changing rate limits or proxy trust. |
| [`.env.example`](.env.example) | Configuring anything at all. |

---

## Contributing

1. Branch off `master`.
2. Keep the layer split: routes stay thin, logic goes in a service, the schema
   changes through a migration.
3. If you change a model, generate a migration **and read the generated file** —
   autogenerate misses enum changes and server defaults.
4. If you add or change an endpoint, update
   [`app/static/openapi.yaml`](app/static/openapi.yaml) in the same change.
5. If you add configuration, document it in [`.env.example`](.env.example),
   including what happens when it's wrong.
6. Money is `Decimal`. Never introduce a `float` column or intermediate.

> **Current gap:** there is no automated test suite. Changes are verified
> manually against a local `docker compose` stack and Swagger UI. Adding pytest
> coverage — starting with the fee maths and the ownership checks in
> `wallet_service` — is the highest-value contribution available.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025 Akinyemi Toluwalase.
