#!/bin/sh
set -eu

python -m flask --app app:create_app init-db
exec gunicorn --no-control-socket --bind "0.0.0.0:${PORT:-8080}" --workers 2 --timeout 60 'app:create_app()'
