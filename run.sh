#!/usr/bin/env bash
# ProductLens quickstart: venv -> install -> tests -> API on :8000.
# Usage: ./run.sh [--skip-tests]   Optional settings come from .env (see .env.example).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
"$PY" -c "" >/dev/null 2>&1 || PY=python   # Windows: python3 may be a Store stub
[ -d .venv ] || "$PY" -m venv .venv
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python.exe; fi

"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r api/requirements.txt

# SKIP_DOTENV=1 is set by tools/demo_data.sh so .env cannot override fixture paths.
if [ -f .env ] && [ "${SKIP_DOTENV:-0}" != "1" ]; then set -a; . ./.env; set +a; fi

if [ "${1:-}" != "--skip-tests" ]; then
  for suite in analysis benchmark signals; do
    "$VPY" -m unittest discover -s "$suite/tests" -t .
  done
  "$VPY" -m unittest discover -s dataset/tests
  "$VPY" -m unittest discover -s api/tests
fi

echo "ProductLens API: http://127.0.0.1:${PORT:-8000}/docs  dashboard: http://127.0.0.1:${PORT:-8000}/dashboard/"
exec "$VPY" -m uvicorn main:app --app-dir api --host 127.0.0.1 --port "${PORT:-8000}"
