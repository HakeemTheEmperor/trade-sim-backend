# Task: Move JWT from localStorage → httpOnly cookies (joint FE + BE)

**Why:** The JWT is currently returned in the login/signup JSON body and stored in
`localStorage` by the frontend. `localStorage` is readable by any JavaScript, so a
single XSS bug leaks the token and hands over the account. Moving the token into an
`HttpOnly`, `Secure`, `SameSite` cookie makes it unreadable to JS, which is the real
fix for that class of attack. This requires coordinated changes in **both** repos
(`trade-sim-backend` and `trade-sim-app`) plus a CSRF defense.

Related: this does NOT change the `X-API-Key` gate (separate concern) — see
`.env.example` (`API_KEY` vs `JWT_SECRET_KEY`).

---

## Backend (`trade-sim-backend`, flask-jwt-extended)

flask-jwt-extended has first-class cookie support; no new dependency needed.

1. **Config** (in `create_app`):
   - `JWT_TOKEN_LOCATION = ["headers", "cookies"]`  ← dual mode during rollout, tighten to `["cookies"]` at the end
   - `JWT_COOKIE_SECURE = True`  (HTTPS only)
   - `JWT_COOKIE_SAMESITE = "Lax"`  ← FE and BE are same-site (see topology below), so `Lax` works; do NOT use `None`
   - `JWT_COOKIE_CSRF_PROTECT = True`  (enables the double-submit CSRF token)
   - optionally `JWT_ACCESS_COOKIE_PATH = "/api/"`
   - do **not** set a cookie `Domain` attribute — leave it host-only on the API host (more secure; the browser still sends it on same-site credentialed requests)
2. **Login / signup** (`auth_routes.py`): build the response, then
   `set_access_cookies(response, access_token)` instead of putting the token in the body.
3. **Logout** (`auth_routes.py`): `unset_jwt_cookies(response)` (keep the revoked-token/blocklist logic).
4. **New endpoint** `GET /auth/me` (behind `require_api_key` + `jwt_required`): returns the
   current user from the JWT identity. The SPA needs this to bootstrap auth state, because
   once the token is HttpOnly the frontend can no longer decode it to know who's logged in.
5. **CORS**: keep `supports_credentials=True` (already set) and explicit origins (already
   env-driven via `CORS_ORIGINS`). Wildcard origins are incompatible with credentialed requests.

## Frontend (`trade-sim-app`)

1. `apiClient.ts`: add `credentials: "include"` to every request so the cookie is sent.
2. Stop sending the `Authorization: Bearer` header and stop reading/writing `token` in
   `localStorage`. Keep storing only the **non-sensitive user profile** for UI, if desired.
3. **CSRF**: read the JS-readable `csrf_access_token` cookie and send it as the
   `X-CSRF-TOKEN` header on all state-changing requests (POST/PUT/DELETE).
4. **Auth state**: `authToken.ts`/`ProtectedRoute` can no longer decode the token. Replace
   `isTokenValid()` with a call to `GET /auth/me` (or a lightweight non-HttpOnly "logged in"
   hint cookie) to decide authenticated vs not. The global 401 handler already added in
   `apiClient` continues to cover session expiry.

## CSRF, briefly

Double-submit cookie: the CSRF value lives in a JS-readable cookie AND must be echoed in a
request header. A malicious cross-site page can trigger a request (cookie auto-attached) but
cannot read the cookie to set the header, so it's rejected. flask-jwt-extended verifies this.

## Safe rollout order

1. BE: add cookie support in **dual** mode (`["headers","cookies"]`); set cookies on login
   AND still return the token in the body. Deploy — nothing breaks.
2. FE: switch to `credentials:"include"` + CSRF header; add `/auth/me`; stop reading the token.
3. Verify end-to-end (see acceptance below).
4. BE: remove the token from the JSON body; set `JWT_TOKEN_LOCATION = ["cookies"]`.
5. FE: delete all remaining `localStorage` token code.

## Acceptance checklist

- [ ] Token never appears in `localStorage`/`sessionStorage` or any JS-readable place.
- [ ] Auth cookie has `HttpOnly`, `Secure`, `SameSite` flags set.
- [ ] A state-changing request without a valid `X-CSRF-TOKEN` is rejected (401).
- [ ] Login, token expiry (401 → redirect), logout, and cross-tab logout all still work.

## Cookie domain: resolved — chosen topology

**Decision:** serve both apps under one registrable domain:

- frontend: `https://app.imockmarket.toluwalase.me`
- backend:  `https://api.imockmarket.toluwalase.me`

`.me` is a public suffix, so the registrable domain (eTLD+1) for both hosts is
`toluwalase.me`. That makes them **same-site** (different origins, same site). This is the
happy path:

- The auth cookie is **first-party**, so `SameSite` restrictions and the Safari/Firefox/
  Chrome third-party-cookie clampdowns do **not** apply. Use `SameSite=Lax` (not `None`),
  and none of the ITP/third-party-blocking pain applies.
- The cookie is set host-only by `api.imockmarket.toluwalase.me` (no `Domain` attribute) and
  is automatically sent back to the API on credentialed requests from the frontend.

Still required because it's cross-**origin** (different hostname):

- CORS must echo the explicit frontend origin `https://app.imockmarket.toluwalase.me` (never
  `*`) with `Access-Control-Allow-Credentials: true` — already handled via `CORS_ORIGINS` +
  `supports_credentials=True`.
- Frontend must send `credentials: "include"` on every request.
- Both hosts must be HTTPS (required for `Secure` cookies).

The only constraint to preserve: keep both apps under `toluwalase.me`. If either ever moves
to a different registrable domain, revisit this — it would become cross-site and force
`SameSite=None` with all the third-party-cookie caveats.
