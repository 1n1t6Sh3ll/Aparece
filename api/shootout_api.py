"""Read-only AI comparison (description shoot-out) report (TEAM-47).

GET /v1/shootout  report.json from benchmark/shootout/run.py. PRODUCTLENS_SHOOTOUT overrides the path
(default benchmark/shootout/out/report.json). Without it, the committed sample (mock judges, "sample": true;
PRODUCTLENS_SHOOTOUT_SAMPLE) is served so the page is never empty; nothing is computed here.
"""
import json

from fastapi import APIRouter

import dashboard_api as dash

router = APIRouter(prefix="/v1", tags=["shootout"])


def _load(env, default):
    rep = dash._cached(env, default, lambda p: json.loads(p.read_text(encoding="utf-8")), {})
    return rep if isinstance(rep, dict) and isinstance(rep.get("generators"), dict) and rep["generators"] else None


@router.get("/shootout")
def shootout():
    rep = _load("PRODUCTLENS_SHOOTOUT", "benchmark/shootout/out/report.json") \
        or _load("PRODUCTLENS_SHOOTOUT_SAMPLE", "benchmark/shootout/sample_report.json")
    return {**rep, "available": True} if rep else {"available": False}
