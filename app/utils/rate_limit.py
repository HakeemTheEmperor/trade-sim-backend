import logging
import threading
import time
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

logger = logging.getLogger(__name__)

# Fixed-window, in-memory rate limiter keyed by client + endpoint.
#
# This is intentionally dependency-free and process-local, which is adequate
# for the app's current single-process (gunicorn --workers 1) deployment. If
# this is ever scaled to multiple workers/instances, move the counters to a
# shared store (e.g. Redis via Flask-Limiter) so the limit is enforced globally.
#
# Known limitation: the counters live in memory, so every deploy and every
# free-tier spin-down resets them. Acceptable here; the alternative is running
# Redis just for this.
_lock = threading.Lock()
# key -> (window_start_epoch, count, window_seconds). The window is stored per
# entry because limits differ per endpoint (5/60s on signin, 5/300s on
# reset-password); purging with the caller's window would expire another
# endpoint's still-live counter and hand out a free window.
_hits = {}
_MAX_TRACKED_KEYS = 10000
_PURGE_INTERVAL_SECONDS = 60
_last_purge = 0.0


def _purge(now):
    """Drop expired windows, and if still over capacity, the oldest entries.

    Called with _lock held. The second step matters: purging only expired keys
    leaves the dict unbounded when every tracked window is still live.
    """
    expired = [k for k, (start, _, window) in _hits.items() if now - start >= window]
    for k in expired:
        del _hits[k]

    if len(_hits) > _MAX_TRACKED_KEYS:
        # Evict oldest-first down to the cap. Losing a live counter can only
        # grant a client a fresh window, never wrongly block one.
        overflow = len(_hits) - _MAX_TRACKED_KEYS
        oldest = sorted(_hits.items(), key=lambda kv: kv[1][0])[:overflow]
        for k, _ in oldest:
            del _hits[k]
        logger.warning("Rate limit table over capacity; evicted %d entries", overflow)


def _client_key(endpoint):
    """Identify the caller, preferring the authenticated user over their IP.

    User ID is the better identifier wherever we have one: it can't be spoofed,
    doesn't depend on proxy configuration being correct, and doesn't lump
    everyone behind one NAT/egress IP into a shared bucket.

    IP is the fallback for unauthenticated routes (signup/signin) — the only
    place the trusted-proxy setup actually has to be right. See
    TRUSTED_PROXY_HOPS in app/__init__.py.
    """
    try:
        # optional=True so this is a no-op on unauthenticated routes rather
        # than raising. Wrapped because a malformed/expired token (or a CSRF
        # failure on a re-login) should degrade to IP keying, not 500.
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
    except Exception:
        identity = None

    if identity:
        return f"user:{identity}:{endpoint}"
    return f"ip:{request.remote_addr or 'unknown'}:{endpoint}"


def rate_limit(max_requests, window_seconds):
    """Allow at most ``max_requests`` per ``window_seconds`` per client+endpoint."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            global _last_purge
            now = time.time()
            key = _client_key(request.endpoint)
            with _lock:
                if now - _last_purge >= _PURGE_INTERVAL_SECONDS or len(_hits) > _MAX_TRACKED_KEYS:
                    _purge(now)
                    _last_purge = now
                start, count, _ = _hits.get(key, (now, 0, window_seconds))
                if now - start >= window_seconds:
                    start, count = now, 0
                count += 1
                _hits[key] = (start, count, window_seconds)
                retry_after = max(int(window_seconds - (now - start)), 1)

            if count > max_requests:
                logger.warning("Rate limit exceeded for %s", key)
                response = jsonify({
                    "message": "Too many requests. Please slow down and try again later.",
                    "status_code": 429,
                    "status": "RATE LIMIT EXCEEDED"
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response
            return f(*args, **kwargs)
        return wrapper
    return decorator
