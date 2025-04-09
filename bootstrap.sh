#!/bin/sh
export FLASK_APP=app.index
pipenv run flask --debug run -h 0.0.0.0