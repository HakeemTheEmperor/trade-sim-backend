#!/bin/sh
set -e
export FLASK_APP=app.index

# Apply DB migrations before serving. RUN_BACKGROUND_JOBS=false so building the
# app for this CLI command doesn't trigger admin/seed/scheduler/websocket (which
# also need the tables this step creates).
RUN_BACKGROUND_JOBS=false pipenv run flask db upgrade

# Serve with gunicorn (a production WSGI server) instead of the Flask dev
# server, with the debugger disabled. A single worker is used on purpose: the
# APScheduler jobs and the Finnhub websocket listener are started inside
# create_app(), so more than one worker would duplicate them. Threads provide
# in-process request concurrency.
exec pipenv run gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 app.index:app
