#!/bin/sh
set -e
export FLASK_APP=app.index

# Apply DB migrations before serving. RUN_BACKGROUND_JOBS=false so building the
# app for this CLI command doesn't trigger admin/seed/scheduler/websocket (which
# also need the tables this step creates).
RUN_BACKGROUND_JOBS=false pipenv run flask db upgrade

# Serve with gunicorn (a production WSGI server) instead of the Flask dev
# server, with the debugger disabled. One worker by default: the APScheduler
# jobs and the Finnhub websocket listener are started inside create_app(), so a
# worker that runs them must be the only one. GUNICORN_WORKERS above 1 is for a
# web-only service (RUN_BACKGROUND_JOBS=false) with the jobs running in a second,
# single-worker service; create_app() refuses the unsafe combination. See
# docs/scaling.md.
#
# Threads provide concurrency within a worker; GUNICORN_THREADS sets how many.
# Each worker keeps its own database connection pool, sized from the thread count
# (see engine_options() in app/__init__.py), so the database sees
# GUNICORN_WORKERS x (pool + overflow) connections.
# Bind to $PORT when the platform provides one (e.g. Render); default 5000 locally.
exec pipenv run gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-4} --timeout 120 app.index:app
