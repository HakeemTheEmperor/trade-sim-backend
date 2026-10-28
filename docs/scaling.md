# Scaling the API beyond one process

## Why there is one process by default

Two things in the app live inside a single process:

1. **Background jobs.** `create_app()` starts the scheduler (nightly seeding,
   history, snapshots), the Finnhub websocket listener and the Alpaca poller when
   `RUN_BACKGROUND_JOBS` is on. Run them twice and every nightly job runs twice
   and every price is written twice.
2. **The rate limiter.** Its counters are an in-memory dict
   ([`app/utils/rate_limit.py`](../app/utils/rate_limit.py)).

Everything else (sessions, revoked tokens, OTP codes, exchange rates, prices) is
in Postgres, so any number of web processes can share it.

So the default is `GUNICORN_WORKERS=1` with the jobs on: one process does both.
That sustains roughly 40 trades a second on the machine it was measured on.

## Running several workers

`GUNICORN_WORKERS` above 1 starts that many copies of the app. `create_app()`
**refuses** to start when that is combined with `RUN_BACKGROUND_JOBS` on, rather
than silently duplicating the jobs. Split the work into two services built from
the same image:

| | Web service | Job service |
|---|---|---|
| `GUNICORN_WORKERS` | `2` to `4` (about one per CPU core) | `1` |
| `RUN_BACKGROUND_JOBS` | `false` | `true` |
| Serves public traffic | yes | no need to expose it |
| Needs the provider API keys | no | yes (FMP, Finnhub, Alpaca) |
| Creates the admin user, runs seeding | no | yes |

Both run `flask db upgrade` on start (via `bootstrap.sh`). A Postgres advisory
lock in [`migrations/env.py`](../migrations/env.py) makes the second one wait for
the first, so deploying both together is safe.

Never run two job services: only the one with the jobs should have
`RUN_BACKGROUND_JOBS=true`, and nothing enforces that across services.

## Database connections

Each worker keeps its own pool, so the database sees

```
GUNICORN_WORKERS x (DB_POOL_SIZE + DB_MAX_OVERFLOW)
```

connections per service, plus the job service's. The pool defaults to
`max(5, GUNICORN_THREADS)` with 10 overflow, so 4 workers at the default 4
threads can open up to 60. Keep the total under your database's
`max_connections` (Postgres defaults to 100; hosted tiers are often lower).

## Rate limits are per worker

With several web workers each keeps its own counters, so a limit of 5 sign-ins a
minute can become up to 5 per worker (10 with 2 workers) for one client. For
trades that is harmless. For the sign-in and password-reset limits it is a
weaker brute-force guard. If that matters, move the counters to a shared store
(Redis, or a Postgres table); the limiter is isolated in one module so the
change stays local. A Postgres-backed counter adds a database write to every
rate-limited request, trades included.

## On a small instance (Render free: 0.1 CPU, 512 MB)

Do not add workers or split into two services there. CPU is the limit, not
memory, and more processes only share the same tenth of a core. Measured with
the app container limited to 0.1 CPU and 512 MB
(`APP_CPUS=0.1 APP_MEM=512m`, see `loadtest/docker-compose.loadtest.yml`):

| | 1 worker | 2 workers | 4 workers |
|---|---|---|---|
| Memory at idle | 77 MiB | 131 MiB | 237 MiB |
| Time to become healthy | 111 s | 130 s | 195 s |

- **Throughput is about 3 to 3.5 trades a second.** A fixed 3 a second already
  queued (median 4.9 s), and 6, 10 and 15 a second all completed about 3.5.
  That is roughly 30 ms of CPU per request, because a tenth of a core leaves
  little headroom for Python, the ORM and JWT checks. Workers do not raise it.
- **Memory is not the constraint.** One worker stayed near 92 MiB under load.
- **A cold start is slow.** Importing the app and the migration check each cost
  tens of seconds at this CPU, so the first request after the instance sleeps
  waits over a minute. Anything that keeps the instance awake (a health ping)
  avoids it, and the background jobs only run while it is awake.

Keep `GUNICORN_WORKERS=1` with the default threads. At this size the
per-request cost matters most, which is what the query reductions in the trade
path target.

## What was measured on a larger machine

Local Docker Desktop on Windows (4 CPUs shared by the app, Postgres and the load
generator), k6 at a fixed 100 requests/s of buys and sells, mirrored run order:

| Workers | Mirrored batch (1, 2, 4, 4, 2, 1), completed per second | Two later repeats |
|---|---|---|
| 1 | 46 and 65; median latency of seconds | not repeated |
| 2 | 53 and 82 | about 96 and 99 |
| 4 | 86 and 91; median under half a second | about 100 both times (all 6,000 requests) |

More workers helped in the mirrored batch, but the later repeats were faster for
every setting, so part of the spread is the machine's speed drifting between
runs. Treat this as a direction, not a capacity plan: on a host with more spare
cores the numbers will differ. Load test your own deployment (`loadtest/`)
before sizing it.
