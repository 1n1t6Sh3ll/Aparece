"""Read-only AI comparison (description shoot-out) report (TEAM-47).

GET /v1/shootout  report.json from benchmark/shootout/run.py. First valid report wins:
  1. PRODUCTLENS_SHOOTOUT (a path; if set but missing/invalid, falls through)
  2. benchmark/shootout/out/report.json (a local run; gitignored)
  3. the committed real run, benchmark/shootout/results/2026-09-29/report.json (PRODUCTLENS_SHOOTOUT_REAL)
  4. the committed sample (mock judges, "sample": true; PRODUCTLENS_SHOOTOUT_SAMPLE)
so the page is never empty; nothing is computed here.
"""
import json

from fastapi import APIRouter

import dashboard_api as dash

router = APIRouter(prefix="/v1", tags=["shootout"])

SOURCES = (  # (cache/env key, repo-relative default); keys without a real env var just use the default
    ("PRODUCTLENS_SHOOTOUT", "benchmark/shootout/out/report.json"),
    ("PRODUCTLENS_SHOOTOUT_OUT", "benchmark/shootout/out/report.json"),
    ("PRODUCTLENS_SHOOTOUT_REAL", "benchmark/shootout/results/2026-09-29/report.json"),
    ("PRODUCTLENS_SHOOTOUT_SAMPLE", "benchmark/shootout/sample_report.json"),
)


def _load(env, default):
    rep = dash._cached(env, default, lambda p: json.loads(p.read_text(encoding="utf-8")), {})
    return rep if isinstance(rep, dict) and isinstance(rep.get("generators"), dict) and rep["generators"] else None


@router.get("/shootout")
def shootout():
    rep = next((r for r in (_load(e, d) for e, d in SOURCES) if r), None)
    return {**rep, "available": True} if rep else {"available": False}
