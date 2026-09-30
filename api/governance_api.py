"""Governance routes (TEAM-35). Logic lives in governance/; this file is HTTP only.

POST /v1/approvals is disabled (503) unless GOVERNANCE_TOKEN is set. Callers must send it as X-Governance-Token,
because the API has no user accounts yet.
GET /v1/audit-log and GET /v1/approvals are tenant-scoped: X-Manage-Token (comma list allowed) shows only entries
owned by those monitored products; X-Governance-Admin-Token equal to GOVERNANCE_ADMIN_TOKEN shows everything.
"""
import hmac
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance import audit, hooks, policy  # noqa: E402
from monitor import store  # noqa: E402

router = APIRouter(prefix="/v1", tags=["governance"])


def owned_pids(x_manage_token):
    tokens = [t.strip() for t in (x_manage_token or "").split(",") if t.strip()][:100]
    return store.pids_for_tokens(tokens) if tokens else []


def scope(x_manage_token, x_governance_admin_token):
    """None = admin (all entries); else the product ids this caller's manage token(s) own."""
    admin = os.environ.get("GOVERNANCE_ADMIN_TOKEN")
    if admin and x_governance_admin_token and hmac.compare_digest(x_governance_admin_token, admin):
        return None
    if not x_manage_token:
        raise HTTPException(401, "X-Manage-Token header required")
    pids = owned_pids(x_manage_token)
    if not pids:
        raise HTTPException(403, "invalid manage token")
    return pids


class ApprovalRequest(BaseModel):
    approval_id: str = Field(..., max_length=64)
    approver: str = Field(..., min_length=1, max_length=254)
    role: str = Field(..., max_length=64)
    approve: bool = True


class ConfirmRequest(BaseModel):
    record_id: str = Field(..., max_length=256)
    field: str = Field(..., max_length=128)
    value: Any
    actor: str = Field(..., min_length=1, max_length=254)
    approval_id: str | None = Field(None, max_length=64)


@router.get("/governance/policy")
def get_policy():
    return {"roles": policy.ROLES, "default": "deny", "actions": policy.POLICY}


@router.get("/audit-log")
def audit_log(limit: int = Query(100, ge=1, le=1000), x_manage_token: str | None = Header(None),
              x_governance_admin_token: str | None = Header(None)):
    return {"entries": audit.entries(limit, owners=scope(x_manage_token, x_governance_admin_token))}


@router.get("/approvals")
def pending_approvals(x_manage_token: str | None = Header(None), x_governance_admin_token: str | None = Header(None)):
    return {"pending": audit.pending(owners=scope(x_manage_token, x_governance_admin_token))}


@router.post("/approvals")
def decide(req: ApprovalRequest, x_governance_token: str | None = Header(None)):
    token = os.environ.get("GOVERNANCE_TOKEN")
    if not token:
        raise HTTPException(503, "approvals disabled: GOVERNANCE_TOKEN not set")
    if not x_governance_token or not hmac.compare_digest(x_governance_token, token):
        raise HTTPException(401, "invalid governance token")
    try:
        return policy.approve(req.approval_id, req.approver, req.role, req.approve)
    except policy.GovernanceError as e:
        raise HTTPException(409, str(e))


@router.post("/predictions/confirm")
def confirm(req: ConfirmRequest, x_manage_token: str | None = Header(None)):
    pid = int(req.record_id) if req.record_id.isdigit() else store.pid_for(req.record_id)
    owner = pid if pid is not None and pid in owned_pids(x_manage_token) else None  # tenant only if token owns it
    try:
        return hooks.confirm_prediction(req.record_id, req.field, req.value, req.actor, req.approval_id, owner)
    except policy.ApprovalRequired as e:
        raise HTTPException(403, {"detail": str(e), "approval_id": e.approval_id, "owner": e.owner})
