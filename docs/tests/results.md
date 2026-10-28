# Test and performance results

Everything here was measured on 2026-10-28 while building the test suite and
the trade-path optimisations. Numbers marked **estimate** were derived, not
measured. Numbers marked **retracted** were published once and later found to be
wrong; they are listed at the end so they are not reused.

## At a glance

| Area | Result |
|---|---|
| Automated tests | **39** tests, all passing, about 36 to 48 s, against a real Postgres 16 |
| Double-spend protection | 500 concurrent buys against a wallet affording exactly 10: **10 filled, 490 rejected, 0 overdrafts** |
| Oversell protection | 200 concurrent sells of a 10-share position: **10 filled, 0 oversold** |
| Statements per trade | **11 to 6** (45% fewer) |
| League table (50 members, 10,000-user database) | **about 30 ms instead of about 650 ms** (about 20x), 8 queries instead of 301 |
| Single worker, fixed request rate | Clean at **30 trades/s** (p95 124 to 435 ms over six runs); clean at 40/s after optimisation (p95 309 ms, one run) |
| Four workers at 100 requests/s offered | 86 to 100 completed per second, against 46 to 65 for one worker |
| 0.1 CPU / 512 MB instance (Render free size) | about **3.5 trades/s** maximum; 77 MiB memory; 111 s cold start |
| CPU per trade (gunicorn, unthrottled) | App **15 to 17 ms**, Postgres **4 to 7 ms** |
| Memory per worker | about **76 MB** at startup, 77 to 92 MiB under load |

## How to read these numbers

- **Environment.** Docker Desktop on Windows 11 (Docker engine 28.3.2, a VM with
  4 CPUs and about 8 GB of RAM), Python 3.13, Postgres 16, SQLAlchemy 2.0,
  gunicorn (`gthread`, 1 worker with 4 threads unless stated), k6 2.2.0. The load
  generator, the app and Postgres all shared the same machine.
- **Run-to-run noise was large.** The same configuration swung between "clean"
  and "saturated" (median 16 ms versus several seconds) across runs. Single runs
  are directional. Where it mattered, runs were repeated in mirrored or
  alternating order (see the thread and worker sections).
- **Background jobs were off** (no price websocket, poller or scheduler), which a
  deployed instance runs, so deployed capacity is somewhat lower.
- **Workload.** Each simulated user buys one share, then sells it on the next
  pass, from 2,000 users spread over 5 symbols. The buy and sell routes allow 30
  requests a minute per user, so rates were chosen to stay under that.
- **Fixed-rate load.** k6 `constant-arrival-rate` starts a set number of
  requests a second regardless of how slowly the server answers, so overload shows
  up as latency and "dropped iterations" instead of a lower offered load.

## 1. The automated suite (39 tests)

| File | Tests | What it covers |
|---|---|---|
| `test_smoke.py` | 5 | Health endpoint, schema at migration head, database reset between tests (2), one real buy with its spread fee |
| `test_double_spend.py` | 4 | 500 concurrent buys, 200 concurrent sells, 30 concurrent HTTP buys, 40 concurrent first buys from two wallets |
| `test_trades.py` | 11 | Buy and sell results and every refusal; each refusal leaves wallet, holding and ledger unchanged |
| `test_trade_queries.py` | 2 | A buy and a sell over HTTP stay within 6 SQL statements, with no `FOR UPDATE` and no redundant lookups |
| `test_league_tables.py` | 3 | Season table ranking, career table ranking, every member sees the same table |
| `test_league_performance.py` | 1 | 10,000-user timing, checked against an independent calculation |
| `test_migrations.py` | 1 | Creates real duplicate holdings, upgrades, checks they merge and cannot be recreated |
| `test_migration_lock.py` | 1 | Three real `flask db upgrade` processes against an empty database |
| `test_engine_options.py` | 5 | Connection pool sizing follows the thread count |
| `test_background_jobs_guard.py` | 6 | More than one worker with background jobs on is refused |

Design notes: tests run on a real Postgres (row locks and `ON CONFLICT` do not
exist on SQLite), build the schema from the real Alembic migrations, and truncate
between tests instead of rolling back so threaded tests can commit for real. The
harness refuses any database whose name does not end in `_test`.

## 2. Concurrency and correctness

### Double-spend (buys)

Wallet balance $1,000.50, one share at $100 executing at $100.05 (5 bp half
spread), so exactly 10 buys are affordable. 500 buys released together by a
barrier.

| Check | Result |
|---|---|
| Orders filled | 10 |
| Orders rejected ("Insufficient balance") | 490 |
| Unexpected failures | 0 |
| Final balance | exactly $0.00 |
| Ledger | 10 BUY rows; money spent equals the ledger total ($1,000.50) |
| Holdings | one row, 10 shares |
| **Overdrafts** | **0** |

HTTP variant: 30 concurrent buys through the JWT cookie, CSRF check, rate limiter
and error handlers (30 is the per-user limit of the route): 10 filled, 20
rejected, balance $0.

**How concurrent is "500 concurrent"?** 500 requests are released at the same
instant, but Postgres sees them through the app's connection pool (5 plus 10
overflow), so it is not 500 simultaneous database sessions.

### Oversell (sells)

200 concurrent sells of one share from a 10-share position: 10 filled, 190
rejected, 0 oversold; wallet credited exactly 10 x $99.95; the emptied holding
row removed.

### One holding per position

40 concurrent first buys from two wallets of the same user (two independent wallet
locks) leave exactly one holding row of 40 shares. This is enforced by the unique
constraint on `(user_id, symbol)` added in migration `a4c9e7d15b28`.

### Do the tests detect the bugs? (mutation checks)

| Change made to the code | What happened |
|---|---|
| Disabled `with_for_update` (original lock-based code) | 158 of 500 buys filled instead of 10; the sell test failed with 14 unexpected database errors |
| Removed the rollback after a refused sale | 2 tests failed (a refused sale paid out money) |
| Old code run against the statement-budget tests | Both tests failed |
| Removed the migration advisory lock | 3 of 3 concurrent-upgrade runs failed (`duplicate key ... alembic_version`); with the lock they pass |

## 3. League table at 10,000 users

Seed: 10,000 users, 50,000 holdings, 200 symbols, one running season, daily
snapshots and one 50-member league (the product cap), loaded in about 9 to 10 s.
A league's cost depends on its 50 members, not on the 10,000 users; the extra
users exist so Postgres plans queries against realistic table sizes.

The league table is computed **live** (it is not read from a snapshot table). Three
ways of building it were timed from a fresh session, median of 15 runs:

| Method | After fixes | SELECTs |
|---|---|---|
| Current (batched live query) | **27, 27, 39 ms** | **8** |
| Per-member loop (`compute_equity` for each member) | 625, 678, 667 ms | 301 |
| Snapshot read (stale until the nightly job; reference only) | 10 to 22 ms | n/a |

All three produce the same ranking, checked against an independent calculation
from the seed data. Later full-suite runs gave 26 vs 626, 29 vs 719, 32 vs 571 and
28 vs 680 ms (current vs per-member loop).

### What changed to get there

| Step | Current path | Notes |
|---|---|---|
| Before any fix | 115 to 146 ms, **58** SELECTs | First run: 199 ms vs a 1,769 ms loop |
| Indexes alone | 115 ms | Barely moved: the cost was 50 one-at-a-time user loads |
| Indexes plus eager loading of users | **27 to 39 ms**, 8 SELECTs | Migration `f3a8d2c61b94` and a `joinedload` |

`EXPLAIN (ANALYZE, BUFFERS)` showed the missing-index cost directly (Postgres does
not index foreign keys by itself):

| Query | Without index | With index |
|---|---|---|
| Wallets for 50 users (10,000 rows) | sequential scan, 0.9 to 1.7 ms | index scan, 0.06 to 0.19 ms |
| Holdings for 50 users (50,000 rows) | sequential scan, **4.9 to 17.6 ms** | index scan, **0.10 to 0.21 ms** |

## 4. Efficiency of a trade

### SQL statements per buy

| Version | Statements |
|---|---|
| Original | 11 (8 SELECT, 2 UPDATE, 1 INSERT) |
| After removing redundant queries | 8 |
| After atomic SQL (conditional `UPDATE` plus `INSERT ... ON CONFLICT`) | **6** |

Removed in step 1: a second revoked-token lookup (the rate limiter re-verified the
JWT), a separate `stock_price` query (the price already arrives with the stock),
and a re-read of the stock after `commit()` only to build the message. Removed in
step 2: the `SELECT ... FOR UPDATE` of the wallet and the holding.

### Time per buy, one request at a time (local Postgres, no web server)

| Version | Total | Waiting on Postgres | Python |
|---|---|---|---|
| Original | 28.9 ms | 16.0 ms | 12.8 ms |
| After step 1 | 20.8 ms | 11.3 ms | 9.6 ms |
| After step 2 (four runs) | 23.0, 18.7, 16.8, 16.1 ms | 10.9, 9.2, 8.5, 7.9 ms | 12.0, 9.5, 8.3, 8.2 ms |

These are noisy; the statement count is the dependable figure.

### Where the CPU goes

CPU per request under the real web server (gunicorn, container not throttled),
from `docker stats` over 13 to 16 busy samples per run, two runs each:

| Request | App container | Postgres |
|---|---|---|
| `/health` (one `SELECT 1`) | 4.3 and 4.7 ms | n/a |
| A trade | **16.7 and 16.8 ms** (second method: 15.3 and 17.0) | **4.4 and 7.1 ms** |

Profiling one buy in-process (no web server) with a CPU-time clock: 22.9 ms wall
time, **9.8 ms CPU** and 13.0 ms waiting on Postgres. Share of the CPU:

| Component | Share |
|---|---|
| SQLAlchemy (building SQL, ORM, result handling) | 45.9% |
| Python built-ins and the database driver (psycopg2 `execute` 17.7% and `commit` 3.1% of it) | 34.4% |
| Flask and Werkzeug | 10.2% |
| Other standard library (decimal, logging, ...) | 6.5% |
| JWT login check | 1.7% |
| This app's own code | 1.0% |
| JSON | 0.3% |

The trade logic written for this project is about 1% of the CPU; the cost is the
framework plumbing around it.

## 5. Load tests at a fixed request rate (one worker, 4 threads)

Columns: completed per second, dropped iterations (requests k6 could not start
because the server had fallen behind), median and p95 latency. Error rate was
0.0% in every run below except where noted.

### Original code, first sweep (no database reset between runs)

| Offered | Completed/s | Dropped | Median | p95 |
|---|---|---|---|---|
| 10/s | 10.0 | 0 | 31 ms | 96 ms |
| 20/s | 20.0 | 0 | 26 ms | 146 ms (0.1% errors) |
| 30/s | 30.0 | 0 | 24 ms | 435 ms |
| 40/s | 40.0 | 0 | 20 ms | 78 ms |
| 60/s | 60.0 | 0 | 33 ms | 265 ms (did **not** repeat, see retracted) |
| 70/s | 61.6 | 331 | 2.0 s | 3.1 s |
| 80/s | 62.9 | 632 | 3.6 s | 6.5 s |
| 90/s | 61.4 | 1,161 | 5.0 s | 9.9 s |
| 100/s | 43.0 | 2,798 | 11.0 s | 14.1 s |
| 150/s | 51.3 | 5,078 | 11.9 s | 16.5 s |
| 200/s | 57.2 | 7,534 | 12.0 s | 17.2 s |
| 300/s | 55.2 | 13,374 | 13.9 s | 29.5 s |

Repeats of the 55 and 60/s steps: 55/s completed 53.3 (102 dropped, p95 1.9 s);
60/s completed 41.8 (840 dropped, p95 8.9 s). The ceiling is therefore about 40 to
60 requests/s and varies between runs.

### Original code, database reset before every run (two batches)

| Offered | Batch 1: completed, dropped, p95 | Batch 2: completed, dropped, p95 |
|---|---|---|
| 30/s | 30.0, 0, 184 ms | 30.0, 0, 251 ms |
| 40/s | 40.0, 0, 731 ms | 39.1, 43, 1.4 s |
| 50/s | 38.1, 553, 6.2 s | 38.1, 526, 5.7 s |

### Effect of the optimisation steps (same method, database reset per run)

| Offered | Original | After step 1 (fewer queries) | After step 2 (atomic SQL) |
|---|---|---|---|
| 30/s | 30.0 done, p95 162 ms | 30.0, p95 194 ms | 30.0, p95 **124 ms** |
| 40/s | 38.5 done, 87 dropped, p95 2.3 s | 40.0, 0 dropped, p95 672 ms | 40.0, **0 dropped, p95 309 ms** |
| 50/s | 43.9 done, 286 dropped, p95 3.8 s | 48.9, 68 dropped, p95 1.4 s | 49.2, **49 dropped, p95 1.25 s** |
| 60/s | not measured | not measured | 57.6, 137 dropped, p95 1.3 s |

Honest reading: steps 1 and 2 together are a clear improvement at 50/s. At 40/s
the original code had p95 values of 731 ms, 1.4 s and 2.3 s across three runs, so
the single "after" runs are suggestive, not conclusive. The step 2 gain on top of
step 1 is within the noise at 50/s.

## 6. Threads and workers

### Gunicorn threads: no measurable effect

First sweep (fixed order 4, 8, 16, 32; confounded by drift, kept for the record):

| Threads | 50/s | 60/s | 70/s |
|---|---|---|---|
| 4 | 50.0 done, p95 50 ms | 55.9, 247 dropped | 46.1, 1,214 dropped |
| 8 | 34.6, 772 dropped | 54.5, 285 dropped | 56.2, 719 dropped |
| 16 | 36.5, 672 dropped | 38.5, 1,142 dropped | 43.1, 1,375 dropped |
| 32 | 50.0, p95 36 ms | 59.2, 50 dropped | 70.0, 0 dropped, p95 134 ms |

The pattern is not monotonic, which pointed to machine drift. A fairer
alternating test at 60/s (order 4, 32, 32, 4, 4, 32):

| Run | Threads | Completed/s | Dropped | Median | p95 |
|---|---|---|---|---|---|
| 1 | 4 | 60.0 | 0 | 22 ms | 617 ms |
| 2 | 32 | 59.2 | 50 | 16 ms | 912 ms |
| 3 | 32 | 60.0 | 0 | 15 ms | 99 ms |
| 4 | 4 | 60.0 | 0 | 15 ms | 50 ms |
| 5 | 4 | 52.4 | 259 | 979 ms | 2.6 s |
| 6 | 32 | 52.4 | 391 | 876 ms | 3.1 s |

Each setting had two clean runs and one saturated run (the last two runs were
slow whatever the setting). Conclusion: no effect beyond noise, so the default
stays at 4 threads.

### Workers: 1, 2 and 4 at 100 requests/s offered

Mirrored order (1, 2, 4, 4, 2, 1), 4 CPUs shared with Postgres and k6:

| Run | Workers | Completed/s | Dropped | Median | p95 |
|---|---|---|---|---|---|
| 1 | 1 | 65.1 | 1,654 | 4.5 s | 7.8 s |
| 2 | 2 | 53.4 | 2,519 | 4.1 s | 5.4 s |
| 3 | 4 | 85.6 | 683 | 448 ms | 2.8 s |
| 4 | 4 | 91.4 | 458 | 392 ms | 1.5 s |
| 5 | 2 | 81.6 | 1,046 | 1.1 s | 3.0 s (71 failed responses, see below) |
| 6 | 1 | 45.9 | 2,857 | 6.2 s | 11.8 s |

Four later repeats (2, 4, 2, 4 workers): 5,783, 6,001, 5,965 and 6,001 requests
completed out of about 6,000, with **0 failures** in all four. Every setting was
faster in the later runs, so part of the spread is the machine speeding up and
slowing down.

**Unexplained:** run 5 returned 71 error responses (1.4%); they were not timeouts
(longest request 3.5 s). They were never reproduced in five further repeats with
failure capture, and the app logs showed no errors. Treat as unexplained, not
fixed.

Summary: more workers helped (roughly 1.5x to 2x), but the numbers are
directional only.

## 7. Small instances

### Render free size (0.1 CPU, 512 MB), one worker

| Offered | Completed/s | Dropped | Median | p95 |
|---|---|---|---|---|
| 3/s | 2.8 | 0 | 4.9 s | 6.4 s |
| 6/s | 3.5 | 51 (1.0% errors) | 17.9 s | 27.3 s |
| 10/s | 3.5 | 165 | 24.3 s | 44.5 s |
| 15/s | 3.4 | 324 | 28.3 s | 56.5 s |

The maximum is about **3 to 3.5 trades/s** (roughly 30 ms of CPU per request when
throttled). Memory stayed near 92 MiB under load; CPU sat at about 10%.

| | 1 worker | 2 workers | 4 workers |
|---|---|---|---|
| Memory at idle | 77 MiB | 131 MiB | 237 MiB |
| Time to become healthy | 111 s | 130 s | 195 s |
| Out-of-memory kills | none | none | none |

Extra workers only share the same tenth of a core, so they do not help there.

### Cold start at 0.1 CPU

| Step | Time |
|---|---|
| `pipenv run python -c pass` | **20.9 s** (0.4 s using the virtualenv's Python directly) |
| Importing the app (`import app.index`) | 42.8 s |
| `flask db upgrade` (database already current) | 29.3 s directly, 35.4 s through `pipenv run` |

`pipenv run` is invoked three times at startup (Docker `CMD` and twice in
`bootstrap.sh`), so about 40 to 60 s of the 111 s is avoidable. Not yet fixed.

### 0.2 vCPU (app only; the sustained speed of a 2 vCPU, 1 GB burstable instance)

| Offered | Completed/s | Dropped | Median | p95 |
|---|---|---|---|---|
| 5/s | 5.0 | 0 | 133 ms | 1.6 s |
| 7/s | 7.0 | 0 | 505 ms | 1.2 s |
| 9/s | 7.8 | 14 | 6.2 s | 8.1 s |

The app alone caps near 7 to 8 trades/s at 0.2 vCPU, twice the 0.1 CPU result.

## 8. Footprint

### Memory per worker, by import stage (inside the app image)

| Stage | Added | Running total |
|---|---|---|
| Bare Python | 9.2 MB | 9.2 |
| Standard library basics | +6.2 | 15.5 |
| Flask | +16.7 | 32.2 |
| SQLAlchemy | +18.5 | 50.7 |
| Database driver (psycopg2) | +4.6 | 55.3 |
| JWT, CORS and Migrate extensions | +8.5 | 63.8 |
| requests, websocket, scheduler | +8.6 | 72.5 |
| This app (models, routes, `create_app`) | +3.1 | **75.6** |

About 96% is libraries. Under load a worker used 77 to 92 MiB; Postgres used about
53 to 55 MiB.

### Disk

| Data | Rows | Size | Per row (incl. indexes) |
|---|---|---|---|
| `available_stocks` | 1,001 | 688 kB | 704 B |
| `stock_history` | 120,000 (1,000 tickers x 120 days) | 14 MB | 124 B |
| `transactions` | 100,340 | 12 MB | 124 B |
| Whole test database | | 35 MB | |

A million trades is roughly 120 MB. Docker images dominate disk: the app image is
709 MB (build tools are left in it) and `postgres:16` is 636 MB.

## 9. Capacity estimates for other hosts (estimates, not measured)

Derived from the measured CPU per trade (about 17 ms app plus 4 to 7 ms Postgres
unthrottled, 26 to 29 ms for the app when tightly throttled) and the burstable
baselines in AWS's T4g table (10% per vCPU for micro, 20% for small and medium). The
application and database would share one allowance on a single machine.

| Instance | Sustained | Burst (on credits) |
|---|---|---|
| `t3.micro` / `t4g.micro` (2 vCPU, 0.2 vCPU baseline) | about 6 trades/s (5 to 9) | about 40 to 50 |
| `t4g.small` / `t4g.medium` (2 vCPU, 0.4 vCPU baseline) | about 12 trades/s (10 to 18) | about 40 to 50 |

These have not been tested on a real instance. A `t4g.medium` has the same CPU as a
`t4g.small`, only more RAM.

## 10. Bugs found along the way

| Finding | Effect |
|---|---|
| `pipenv lock` bumped SQLAlchemy 2.0.51 to 2.1.6, which makes `postgresql://` default to the `psycopg` (v3) driver, which the app does not install | A container built from that lock crashed on start (`No module named 'psycopg'`); pinned `sqlalchemy<2.1` |
| Sell took its row locks in the opposite order to buy | One user buying and selling at once could deadlock; both now lock wallet then holding |
| No unique constraint on `users_stock_wallet(user_id, symbol)` | Concurrent first buys could split one position into two rows; migration merges duplicates and adds the constraint |
| Two services running `flask db upgrade` at once | Collision on `alembic_version`; fixed with a Postgres advisory lock |
| No index on `wallets.user_id` or `users_stock_wallet.user_id` | Sequential scans on every per-user lookup; indexes added |

## 11. Retracted figures (do not reuse)

| Figure | Why it is wrong |
|---|---|
| "p95 265 ms at 60 requests/s" (one run) | Did not repeat; the repeat completed only 41.8/s with p95 8.9 s |
| "32 threads handled 70 requests/s cleanly" | Single run in a fixed-order sweep; alternating runs showed no thread effect |
| "About 45 ms of CPU per trade in the app and 16 ms in Postgres" | From only six sampling readings at start-up; re-measured at 15 to 17 ms and 4 to 7 ms |
| Earlier small-instance capacity of "3 to 5 trades/s sustained, 6 to 9 on a small" | Built on the retracted CPU figures; replaced by section 9 |
| "A 10,000-user league leaderboard" | Leagues are capped at 50 members; the test was a 50-member league in a 10,000-user database |
| League table "instead of a snapshot" | The table is live; the comparison is batched query vs per-member loop |
| Ticker count "supported" | The seed list has 536 symbols; the design targets about 1,000, but nothing was tested against live data providers (no API keys) |

## 12. How to reproduce

```bash
# Tests (needs Docker for the throwaway Postgres on port 5433)
docker compose -f docker-compose.test.yml up -d --wait
python -m pytest                    # all 39
python -m pytest -m "not perf"      # skip the 10,000-user timing test

# Load tests (stack with the real Dockerfile; see loadtest/docker-compose.loadtest.yml)
docker compose -f loadtest/docker-compose.loadtest.yml up -d --build --wait
python loadtest/seed.py             # 2,000 users, 5 symbols
RESEED=1 PAUSE=60 sh loadtest/run.sh 30 40 50
sh loadtest/sweep_threads.sh "4 32" "60"           # thread comparison
APP_CPUS=0.1 APP_MEM=512m docker compose -f loadtest/docker-compose.loadtest.yml up -d --force-recreate app   # small instance
docker compose -f loadtest/docker-compose.loadtest.yml down -v
```

Stop the test database while load testing (it competes for the same CPUs), and
compare alternating repeats, not single runs, because the results drift.
