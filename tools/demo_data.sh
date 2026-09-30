#!/usr/bin/env bash
# Start the API + dashboard on bundled test fixtures (no downloads, no keys, no paid calls).
# Usage: tools/demo_data.sh   then open http://127.0.0.1:8000/dashboard/
set -euo pipefail
cd "$(dirname "$0")/.."
FX="$PWD/api/tests/fixtures"
export PRODUCTLENS_DATA="$FX/dashboard_records.jsonl"
export PRODUCTLENS_SIGNALS="$FX/dashboard_signals.jsonl"
export PRODUCTLENS_VISIBILITY="$FX/dashboard_visibility.json"
export PRODUCTLENS_EVAL="$FX/dashboard_eval.json"
export MODEL_BACKEND=rules MONITOR_ENABLED=0 SKIP_DOTENV=1
exec ./run.sh --skip-tests
