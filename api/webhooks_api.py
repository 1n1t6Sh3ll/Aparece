"""Outgoing webhook routes (TEAM-51). Logic lives in webhooks/; this file is HTTP only. See docs/WEBHOOKS.md.

Every route needs the product's X-Manage-Token (from POST /v1/enroll). The signing secret is returned once, on create.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import safe_fetch  # noqa: E402
from monitor import store as monitor_store  # noqa: E402
from monitor_api import authorize, rate_limit  # noqa: E402
from webhooks import core, store  # noqa: E402

router = APIRouter(prefix="/v1", tags=["webhooks"], on_startup=[core.start_worker], on_shutdown=[core.stop_worker])
MAX_PER_PRODUCT = 10


class WebhookRequest(BaseModel):
    product_id: str = Field(..., max_length=64, description="public product id from POST /v1/enroll")
    url: str = Field(..., max_length=2048)
    events: list[str] = Field(..., min_length=1, max_length=len(core.EVENTS))


def owned(wid, token):
    w = store.get(wid)
    if not w:
        raise HTTPException(404, "webhook not found")
    authorize(w["product_public_id"], token)
    return w


@router.get("/webhooks/events")
def event_types():
    return {"events": list(core.EVENTS)}


@router.post("/webhooks", status_code=201)
async def create(req: WebhookRequest, request: Request, x_manage_token: str | None = Header(None)):
    rate_limit(request)
    authorize(req.product_id, x_manage_token)
    bad = sorted(set(req.events) - set(core.EVENTS))
    if bad:
        raise HTTPException(422, f"unknown event types: {', '.join(bad)}; see GET /v1/webhooks/events")
    try:
        await run_in_threadpool(safe_fetch.check_url, req.url)
    except safe_fetch.FetchError as e:
        raise HTTPException(400, f"webhook url rejected: {e.detail}")
    if store.count(req.product_id) >= MAX_PER_PRODUCT:
        raise HTTPException(409, f"at most {MAX_PER_PRODUCT} webhooks per product")
    w, secret = store.create(req.product_id, req.url, req.events)
    return {"webhook": store.public(w), "secret": secret}


@router.get("/webhooks")
def list_webhooks(x_manage_token: str | None = Header(None)):
    """Webhooks of every product managed by the given token(s) (comma-separated)."""
    tokens = [t.strip() for t in (x_manage_token or "").split(",") if t.strip()][:100]
    if not tokens:
        raise HTTPException(401, "X-Manage-Token header required")
    pids = monitor_store.pids_for_tokens(tokens)
    public_ids = [p["public_id"] for p in monitor_store.monitored(ids=pids)] if pids else []
    return {"results": [store.public(w) for w in store.for_products(public_ids)]}


@router.delete("/webhooks/{wid}", status_code=204)
def delete(wid: str, x_manage_token: str | None = Header(None)):
    owned(wid, x_manage_token)
    store.delete(wid)


@router.post("/webhooks/{wid}/test")
def test(wid: str, request: Request, x_manage_token: str | None = Header(None)):
    """Send one signed webhook.test event to this webhook now (retried like any other event if it fails)."""
    rate_limit(request)
    w = owned(wid, x_manage_token)
    if not w["active"]:
        raise HTTPException(409, f"webhook is disabled: {w['disabled_reason']}")
    eid = core.emit(w["product_public_id"], core.TEST_EVENT, {"message": "ProductLens test event"}, only_webhook=wid)
    if not eid:
        raise HTTPException(500, "test event could not be queued")
    return {"event_id": eid, "delivery": next((d for d in store.deliveries(wid) if d["event_id"] == eid), None)}


@router.get("/webhooks/{wid}/deliveries")
def deliveries(wid: str, x_manage_token: str | None = Header(None)):
    owned(wid, x_manage_token)
    return {"results": store.deliveries(wid)}
