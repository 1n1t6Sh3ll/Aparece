"""Generate Fix routes (TEAM-41). Logic lives in optimizer/; this file is HTTP only.

POST /v1/optimize          draft title/description (best of N reward-scored, guarded candidates, with per-candidate
                           reward breakdown), missing attributes, JSON-LD. Never published.
POST /v1/optimize/publish  re-checks the suggestion, then needs Merchant approval (governance publish_suggestions).
"""
import sys
import urllib.error
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dataset" / "collect"))

from optimizer import fix  # noqa: E402

try:  # governance may be absent from older images
    from governance import policy
except ModuleNotFoundError:  # pragma: no cover
    policy = None

router = APIRouter(prefix="/v1", tags=["optimizer"])


class OptimizeRequest(BaseModel):
    product: dict[str, Any] = Field(..., description="Audited normalized record with evidence (Product Truth).")
    language: Literal["en", "es"] = "en"
    gaps: dict[str, Any] | None = Field(None, description="analysis.gaps.analyze() output.")
    peers: list[dict[str, Any]] | None = Field(None, max_length=200, description="Peer records; gaps computed if given.")
    candidates: int | None = Field(None, ge=1, le=fix.MAX_CANDIDATES,
                                   description="Candidates per round (default OPTIMIZER_CANDIDATES or 3).")
    actor: str = Field("api", max_length=254)


class PublishRequest(BaseModel):
    product: dict[str, Any]
    suggestion: dict[str, Any] = Field(..., description="title, description, json_ld, language from /v1/optimize.")
    actor: str = Field(..., min_length=1, max_length=254)
    approval_id: str | None = Field(None, max_length=64)


@router.post("/optimize")
def optimize(req: OptimizeRequest):
    gaps = req.gaps
    if gaps is None and req.peers:
        from analysis.gaps import analyze
        gaps = analyze(req.product, req.peers)
    target = str(req.product.get("product_id") or "")
    if policy:
        policy.require("generate_suggestions", req.actor, target=target)
    try:
        return fix.generate(req.product, req.language, gaps, candidates=req.candidates)
    except (RuntimeError, OSError, urllib.error.URLError) as e:
        raise HTTPException(502, f"text backend failed: {e}")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/optimize/publish")
def publish(req: PublishRequest):
    if policy is None:
        raise HTTPException(503, "governance unavailable; publishing is disabled")
    problems = fix.verify_suggestion(req.product, req.suggestion)
    if problems:
        try:  # forbidden action: this only writes the denied attempt to the audit log
            policy.require("fabricate_claims", req.actor, target=str(req.product.get("product_id") or ""),
                           details=req.suggestion)
        except policy.Forbidden:
            pass
        raise HTTPException(422, {"detail": "suggestion is not grounded in Product Truth", "problems": problems})
    keep = {k: req.suggestion.get(k) for k in ("language", "title", "description", "json_ld")}
    try:
        decision = policy.require("publish_suggestions", req.actor, target=str(req.product.get("product_id") or ""),
                                  details=keep, approval_id=req.approval_id)
    except policy.ApprovalRequired as e:
        raise HTTPException(403, {"detail": str(e), "approval_id": e.approval_id, "owner": e.owner})
    return {"status": "approved_for_publish", "approved_by": decision["approved_by"], "suggestion": keep,
            "note": "Aparece does not write to the storefront; apply the approved text in your store."}
