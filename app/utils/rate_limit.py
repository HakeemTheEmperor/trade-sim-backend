import threading
import time
from functools import wraps

from flask import jsonify, request

# Fixed-window, in-memory rate limiter keyed by client IP + endpoint.
#
# This is intentionally dependency-free and process-local, which is adequate
# for the app's current single-process (gunicorn --workers 1) deployment. If
# this is ever scaled to multiple workers/instances, move the counters to a
# shared store (e.g. Redis via Flask-Limiter) so the limit is enforced globally.
_lock = threading.Lock()
_hits = {}  # key -> [window_start_epoch, count]
_MAX_TRACKED_KEYS = 10000


def _purge_expired(now, window_seconds):
    expired = [k for k, (start, _) in _hits.items() if now - start >= window_seconds]
    for k in expired:
        del _hits[k]


def _client_key(endpoint):
    # request.remote_addr is used (not the spoofable X-Forwarded-For). If this
    # app is deployed behind a trusted proxy, configure Werkzeug's ProxyFix so
    # remote_addr reflects the real client IP.
    return f"{request.remote_addr or 'unknown'}:{endpoint}"


def rate_limit(max_requests, window_seconds):
    """Allow at most ``max_requests`` per ``window_seconds`` per client+endpoint."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time.time()
            key = _client_key(request.endpoint)
            with _lock:
                if len(_hits) > _MAX_TRACKED_KEYS:
                    _purge_expired(now, window_seconds)
                start, count = _hits.get(key, (now, 0))
                if now - start >= window_seconds:
                    start, count = now, 0
                count += 1
                _hits[key] = (start, count)
                retry_after = max(int(window_seconds - (now - start)), 1)

            if count > max_requests:
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
