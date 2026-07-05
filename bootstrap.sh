#!/bin/sh
export FLASK_APP=app.index
# Serve with gunicorn (a production WSGI server) instead of the Flask dev
# server, with the debugger disabled. A single worker is used on purpose: the
# APScheduler jobs and the Finnhub websocket listener are started inside
# create_app(), so more than one worker would duplicate them. Threads provide
# in-process request concurrency.
exec pipenv run gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 app.index:app
