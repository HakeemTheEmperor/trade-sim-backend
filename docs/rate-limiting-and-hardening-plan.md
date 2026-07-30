# Plan: rate limiting, client-IP trust, and hardening

Status: **implemented** (phases 1, 2, 4, 5). Phase 3 (Cloudflare) is still
optional and not applied. The `onrender.com` subdomain has been disabled.

Outstanding: the §7 Step 0 verification has NOT been done yet — deploy with
`LOG_CLIENT_IP=true`, confirm `remote_addr` is a real public IP, then set it
back to `false`. Until that's checked, `TRUSTED_PROXY_HOPS=1` is an assumption,
not a verified fact.

Covers the rate limiter rework (including making it correct behind Render and
Cloudflare), plus the correctness fixes and cleanup found alongside it.

---

## 1. Why the current limiter doesn't work

`app/utils/rate_limit.py` keys on `request.remote_addr`, and `ProxyFix` is not
configured anywhere in the app.

Behind a reverse proxy, `remote_addr` is the *proxy's* address, not the client's.
Render terminates TLS and forwards to your container, so every request almost
certainly arrives with the same `remote_addr`. That collapses all users into one
bucket, which inverts what the limiter is for:

- It does **not** stop brute force — an attacker gets the same 5/minute as
  everyone, and simply isn't slowed by a limit shared with idle users.
- It **does** create a denial-of-service vector — five failed logins from any
  one person exhausts the window for *every* user for the next minute.

So today the limiter is plausibly worse than not having one. Confirm before
building on this assumption (see §7, step 0).

Coverage is also thin. Only two of ~45 endpoints are limited:

| Endpoint | Limit |
|---|---|
| `POST /api/v1/auth/signup` | 10 / 60s |
| `POST /api/v1/auth/signin` | 5 / 60s |

Notably unlimited: `POST /api/v1/auth/reset-password` (accepts `old_password`,
so it's brute-forceable by anyone holding a stolen token), and `POST /buy` /
`POST /sell` (unbounded authenticated writes against a free-tier database).

---

## 2. The Cloudflare complication

`ProxyFix(x_for=N)` takes the **Nth value from the right** of `X-Forwarded-For`.
The correct `N` equals the number of proxies you actually have. Verified
behaviour:

| Topology | `X-Forwarded-For` seen by app | `x_for` | Resulting `remote_addr` |
|---|---|---|---|
| Render only | `203.0.113.7` | 1 | `203.0.113.7` ✅ |
| Cloudflare → Render | `203.0.113.7, 172.68.1.1` | 2 | `203.0.113.7` ✅ |
| Cloudflare → Render | `203.0.113.7, 172.68.1.1` | 1 | `172.68.1.1` ❌ Cloudflare's edge |
| **Direct to Render, attacker forges header** | `1.2.3.4, 198.51.100.9` | 2 | `1.2.3.4` ❌ **spoofed** |
| Direct to Render, attacker forges header | `1.2.3.4, 198.51.100.9` | 1 | `198.51.100.9` ✅ real |

The last two rows are the trap. Setting `x_for=2` tells the app "there are always
two proxies in front of me." But `<service>.onrender.com` stays publicly
reachable after you put Cloudflare on the custom domain. An attacker who hits
Render directly supplies their own first hop, so the app reads an
attacker-controlled value as the client IP — and can rotate it per request to
get unlimited attempts.

**`x_for=2` is only safe if Cloudflare is genuinely the only path to the origin.**
That has to be enforced, not assumed. §6 covers how.

---

## 3. Design decisions

### 3.1 Key authenticated endpoints by user identity, not IP

The proxy problem only exists because we identify clients by IP. For any route
behind `@jwt_required()`, we already have a better identifier: the JWT subject.

Keying on user ID is strictly better there — immune to proxy misconfiguration,
immune to IP spoofing, immune to NAT (an office or campus sharing one egress IP
currently shares one bucket), and immune to a user's IP changing mid-session.

This reduces IP-based limiting to just the two unauthenticated routes, `signup`
and `signin`, which shrinks the blast radius of getting the proxy config wrong.

### 3.2 Make the trusted hop count configurable

Hard-coding `x_for` means the Cloudflare cutover requires a code change and
redeploy. An env var (`TRUSTED_PROXY_HOPS`, default `1`) makes it a dashboard
change you can revert instantly if the cutover goes wrong.

Default `1` is the safe default: it's correct for Render-only, and if Cloudflare
is added without updating the var, the failure mode is over-restrictive
(everyone shares Cloudflare's edge IP) rather than insecure (spoofable).

### 3.3 Fail closed on limiter errors, but never 500

If we can't determine a key, fall back to a single shared bucket rather than
skipping the limit. Degraded but safe.

---

## 4. Phase 1 — client identity foundation

**Files:** `app/__init__.py`, `.env.example`

Wrap the WSGI app in `ProxyFix`, driven by env:

```python
from werkzeug.middleware.proxy_fix import ProxyFix

# Number of reverse proxies in front of this app, outermost last:
#   1 = Render only
#   2 = Cloudflare -> Render
# ProxyFix reads the Nth X-Forwarded-For value from the right, so this MUST
# match reality. Too high and a client can forge the value (see docs).
trusted_hops = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_hops, x_proto=trusted_hops)
```

`x_proto` is included so `request.is_secure` and generated external URLs reflect
the original HTTPS scheme rather than the plaintext hop inside Render's network.

Add to `.env.example` with the warning inline.

**Do not set `x_host` or `x_port`** — nothing here depends on them, and each one
trusted is another header a client could influence.

---

## 5. Phase 2 — rate limiter rework

**File:** `app/utils/rate_limit.py`, plus decorators on routes.

### 5.1 Identity-aware keying

Replace `_client_key` so it prefers the authenticated user:

```python
def _client_key(endpoint):
    # Prefer the authenticated user: stable, unspoofable, and unaffected by
    # proxy configuration or NAT. Falls back to IP for unauthenticated routes
    # (signup/signin), which is the only place proxy trust matters.
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None
    if identity:
        return f"user:{identity}:{endpoint}"
    return f"ip:{request.remote_addr or 'unknown'}:{endpoint}"
```

Note the ordering constraint: `@rate_limit` must sit **below** `@jwt_required()`
in the decorator stack (i.e. run after it) on protected routes, or use
`verify_jwt_in_request(optional=True)` as above so it works either way. The
`optional=True` form is why this doesn't break the unauthenticated routes.

### 5.2 Fix unbounded growth

`_purge_expired` currently runs only when the dict exceeds `_MAX_TRACKED_KEYS`
and only removes *expired* entries. If 10,000 keys are all live, the dict keeps
growing. Change to purge on a time interval as well, and if still over the cap
after purging, evict the oldest entries.

### 5.3 Extend coverage

| Endpoint | Proposed limit | Rationale |
|---|---|---|
| `POST /auth/reset-password` | 5 / 300s | Accepts `old_password`; same brute-force surface as signin |
| `POST /stocks/buy` | 30 / 60s | Generous for real use, bounds runaway clients |
| `POST /stocks/sell` | 30 / 60s | Same |
| `POST /auth/signin` | 5 / 60s | unchanged, now correctly keyed |
| `POST /auth/signup` | 10 / 60s | unchanged, now correctly keyed |

Buy/sell keyed by user ID means one user's loop can't affect anyone else.

### 5.4 Known limitation, accepted

The store is in-memory and process-local. Every deploy and every Render free-tier
spin-down wipes it. Not worth solving now — the fix is Redis, which is another
service to run. Document it and move on. The existing comment at the top of the
file already says this; keep it accurate.

---

## 6. Phase 3 — Cloudflare cutover

Do this **after** phases 1–2 are deployed and verified on Render alone.

### 6.1 DNS and certificate ordering

1. Add the custom domain in Render with the Cloudflare record set to
   **DNS-only (grey cloud)**. Cloudflare would otherwise intercept the ACME
   challenge and certificate issuance can hang.
2. Wait for Render to show the domain verified and the certificate issued.
3. Only then flip to **Proxied (orange cloud)**.

### 6.2 Cloudflare settings

- **SSL/TLS mode: Full (strict).** "Flexible" causes an infinite redirect loop,
  because Render redirects HTTP→HTTPS.
- **Bypass cache for `/health`.** Cloudflare won't cache an extensionless JSON
  route by default, but make it explicit. A cached health response is silently
  catastrophic: UptimeRobot gets a 200 from the edge, the origin never wakes,
  and Supabase never sees the `SELECT 1` — so Render sleeps and Supabase pauses
  while the dashboard stays green.
- **Bot Fight Mode off**, or allowlist UptimeRobot. It challenges monitoring
  services, producing phantom downtime alerts.
- Be aware of the **100s edge timeout** (error 524) versus gunicorn's 120s. Only
  bites on a cold start, which the keep-alive should prevent.

### 6.3 Closing the origin-bypass hole

`x_for=2` is unsafe while the origin is reachable outside Cloudflare (§2). Three
measures, in increasing strength. Do the first regardless.

**Step 1 — disable the `onrender.com` subdomain (do this either way).**

Render supports this natively. Once the service has at least one verified custom
domain: **Settings → Custom Domains → Render Subdomain → Disabled.** Requests to
`<service>.onrender.com` then get a 404 *at Render's edge* and never reach the
app. Reversible at any time.

This removes the obvious bypass path and is worth doing whether or not you use
Cloudflare. See §6.4 for the ordering, which matters.

**Step 2 — decide whether the residual path matters.**

Disabling the subdomain does **not** fully close the hole. The custom domain is
still served from Render's edge, so someone who resolves Render's IP (via the
still-resolvable `onrender.com` DNS record) and connects to it with
`Host: api-imockmarket.toluwalase.me` can reach the origin without traversing
Cloudflare — and then forge `X-Forwarded-For`.

That's a deliberate, non-trivial attack rather than something a casual scanner
stumbles into. For a portfolio project, stopping here and setting
`TRUSTED_PROXY_HOPS=2` is defensible: §3.1 keys every authenticated route by
user ID, so the exposure is limited to the signup/signin IP limits.

**Step 3 — enforce Cloudflare-only access (only if you want the hole actually
closed).** Free on Cloudflare:

1. Generate a random secret.
2. Cloudflare → **Rules → Transform Rules → Modify Request Header**: add
   `X-Origin-Secret: <secret>` on all requests to the API hostname.
3. Store the same value on Render as `ORIGIN_SHARED_SECRET`.
4. Add a `before_request` hook rejecting requests whose header doesn't match,
   exempt while the env var is unset so it can roll out without downtime.

This makes `x_for=2` genuinely sound: every request reaching the app provably
came through Cloudflare. Trade-off: delete the Transform Rule and the whole API
returns 403. Roll out in log-only mode first.

### 6.4 Ordering — do not lock yourself out

The subdomain toggle is only available *after* a custom domain is verified, and
disabling it while anything still depends on the `onrender.com` URL breaks that
thing silently. Correct order:

1. Add the custom domain in Render (grey cloud) and wait for verification +
   certificate issuance.
2. Confirm `https://api-imockmarket.toluwalase.me/health` returns
   `{"status":"ok"}`.
3. **Repoint UptimeRobot to the custom domain.** If the monitor is still hitting
   `.onrender.com` when you disable it, it starts 404ing — which means constant
   false alerts *and*, far worse, no keep-alive traffic at all. Render then
   sleeps and Supabase pauses after 7 days.
4. Confirm `VITE_API_BASE_URL` on Vercel points at the custom domain, and that
   the frontend has been **rebuilt** (Vite inlines it at build time).
5. Only now: disable the Render subdomain.
6. If using Cloudflare, flip to orange cloud and set `TRUSTED_PROXY_HOPS=2`.

---

## 7. Verification

**Step 0 — before writing any code**, confirm the premise. Temporarily log
`request.remote_addr` and `request.headers.get("X-Forwarded-For")` on one
endpoint, deploy, hit it from your phone on mobile data, and read the logs.

- If `remote_addr` is already your phone's public IP, Render is not obscuring it
  and Phase 1 is less urgent (though still correct to add).
- If it's a private address (`10.x`, `172.16-31.x`) or a fixed Render address,
  the limiter is confirmed broken as described.

Record what you find — it determines whether `TRUSTED_PROXY_HOPS=1` is right.

**After Phase 1:** repeat. `remote_addr` should now equal your real public IP.

**After Phase 2:**
- From two different accounts, exceed the buy limit on one. The other must be
  unaffected (proves per-user keying).
- Fail signin 6 times from one network; confirm 429 with a `Retry-After` header.
  From a different network (phone on mobile data), confirm signin still works —
  this is the exact regression that a broken proxy config causes.

**After Phase 3:** re-run the signin test through the Cloudflare-proxied domain.
If a second network is *also* blocked, `TRUSTED_PROXY_HOPS` is wrong.

---

## 8. Phase 4 — correctness fixes

Independent of rate limiting; can ship in the same PR or separately.

**`/api/v1/auth/admin-signup` is broken.** `AuthService.admin_signup` builds a
`User` without `username`, which is `nullable=False` and unique, so every call
raises `IntegrityError` and returns a generic 409. The route half: it defines a
`required_fields` list containing `"username"` then validates against a
different hardcoded list omitting it, so the field is never required and never
forwarded. Fix: validate against `required_fields`, accept `username`, pass it
through.

**Per-symbol exception handling in `update_history.py`.** The whole loop is
wrapped in one `except Exception`, so a failure on the first symbol aborts all
45 and logs a single line that reads like a transient provider blip. This is
what let the `api.massive.com ` typo hide. Move the handler inside the loop and
continue, logging the symbol.

**Remove the no-op `try/except`** in `auth_routes.py` (`except ValueError as e:
raise` catches and immediately re-raises).

**Use the enum for roles consistently.** `auth_routes.py` passes the literal
`'SUPERADMIN'` while `user_routes.py` passes `UserRoles.SUPER_ADMIN.value`. Both
resolve to the same string today (`SUPER_ADMIN = "SUPERADMIN"`), so there's no
live bug — but the literal breaks silently if the enum value is renamed. Same
for `role="ADMIN"` in `auth_service.py`.

---

## 9. Phase 5 — cleanup

- Delete `seed_available_stock()` in `app/__init__.py`. It's unreachable, and it
  would raise a NOT NULL violation if called (inserts `AvailableStocks` with only
  a symbol). It also carries a stale symbol list that diverges from the live one
  in `data_seed.py`.
- Delete `app/models/user_roles.py` — the file is empty; `UserRoles` lives in
  `user.py`.
- Delete `WebSocketListener.update_stock_price` — an explicit no-op kept "for
  reference".
- Fix the `README.md` clone instructions (they `cd stock-trade-sims`, which
  doesn't match the repo name).

---

## 10. Suggested sequencing

1. **Step 0 verification** (§7) — one small logging change, deploy, observe.
2. **Phase 1** ProxyFix + `TRUSTED_PROXY_HOPS=1`. Verify.
3. **Phase 2** limiter rework + expanded coverage. Verify.
4. **Phase 4 + 5** correctness fixes and cleanup — low risk, no ordering
   dependency.
5. **Phase 3** Cloudflare, only if you decide you want it. Flip
   `TRUSTED_PROXY_HOPS=2` in the same change as the orange cloud, and re-verify.

Phases 1 and 2 are worth doing **whether or not you use Cloudflare** — the
limiter is broken on Render alone.

---

## 11. Risks

**Getting `TRUSTED_PROXY_HOPS` wrong is a security bug, not a cosmetic one.**
Too high allows spoofing. This is the single most important thing to verify
empirically rather than reason about.

**Per-user keying changes limiter semantics.** An attacker with many accounts
gets many buckets. Acceptable here because signup itself is IP-limited, but it
means user-keyed limits are about protecting the *system from runaway clients*,
not about stopping a determined adversary.

**Option B can take the whole API down** if the Cloudflare Transform Rule is
removed. Roll out in log-only mode and keep the env-unset exemption.

**Nothing here is covered by tests.** The repo has no test suite, so all
verification is manual (§7). Consider that a separate gap.

---

## 12. Deliberately not doing

- **Redis / Flask-Limiter.** Correct long-term answer for multi-instance limiting;
  overkill while pinned to `--workers 1` on a free tier.
- **Making `market_cap` nullable.** The seed now skips incomplete symbols, which
  preserves the data guarantee.
- **A global catch-all rate limit.** Tempting, but risks throttling legitimate
  dashboard page-loads that fan out into several API calls. Revisit with real
  traffic data.
