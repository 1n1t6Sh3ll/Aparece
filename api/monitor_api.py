"""Enrollment + monitoring routes (TEAM-28). Logic lives in monitor/; this file is HTTP only.

URLs use a random public id; internal ids and merchant emails are never returned. Enrollment returns a manage
token once (stored hashed); DELETE /v1/enroll/{id} and POST /v1/monitored/{id}/crawl require it as X-Manage-Token.
Enroll/delete are rate limited per client IP (MONITOR_RATE_LIMIT requests per minute, default 10).
"""
import os
import re
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import safe_fetch  # noqa: E402
from monitor import crawl, scheduler, store  # noqa: E402

router = APIRouter(prefix="/v1", tags=["monitor"], on_startup=[scheduler.start], on_shutdown=[scheduler.stop])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EnrollRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    email: str | None = Field(None, max_length=254)
    plan: str = "free"
    crawl_now: bool = True


PUBLIC = ("url", "enrolled_at", "active", "plan", "last_snapshot_at", "last_hash", "snapshot_count", "event_count")
_hits = defaultdict(deque)  # client ip -> recent request times


def rate_limit(request: Request):
    limit = int(os.environ.get("MONITOR_RATE_LIMIT") or 10)
    now, q = time.monotonic(), _hits[request.client.host if request.client else "?"]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "too many requests; try again in a minute")
    q.append(now)


def public(p):
    """Product row -> API shape: public id only, no internal id, merchant id, email or token hash."""
    return {"id": p["public_id"], **{k: p[k] for k in PUBLIC if k in p}}


def get_pid(public_id):
    pid = store.pid_for(public_id)
    if not pid:
        raise HTTPException(404, "monitored product not found")
    return pid


def authorize(public_id, token):
    pid = get_pid(public_id)
    if not token:
        raise HTTPException(401, "X-Manage-Token header required")
    if not store.check_token(pid, token):
        raise HTTPException(403, "invalid manage token")
    return pid


@router.get("/plans")
def plans():
    return {"plans": store.PLANS, "billing": False}


@router.post("/enroll", status_code=201)
async def enroll(req: EnrollRequest, request: Request):
    rate_limit(request)
    if req.plan not in store.PLANS:
        raise HTTPException(422, f"plan must be one of {store.PLANS}")
    if req.email and not EMAIL.match(req.email):
        raise HTTPException(422, "invalid email")
    try:
        await run_in_threadpool(safe_fetch.check_url, req.url)
    except safe_fetch.FetchError as e:
        raise HTTPException(e.status, e.detail)
    p, created = store.enroll(req.url, req.email, req.plan)
    token = store.issue_token(p["id"])  # None when the product already has an owner token
    result = await run_in_threadpool(crawl.crawl, p["id"]) if req.crawl_now else None
    return {"product": public(p), "created": created, "manage_token": token, "crawl": result}


@router.get("/monitored")
def monitored():
    return {"results": [public(p) for p in store.monitored()]}


@router.delete("/enroll/{public_id}", status_code=204)
def unenroll(public_id: str, request: Request, x_manage_token: str | None = Header(None)):
    rate_limit(request)
    store.unenroll(authorize(public_id, x_manage_token))


@router.post("/monitored/{public_id}/crawl")
def recrawl(public_id: str, x_manage_token: str | None = Header(None)):
    return crawl.crawl(authorize(public_id, x_manage_token))


@router.get("/products/{public_id}/history")
def history(public_id: str):
    pid = get_pid(public_id)
    h = {k: [{c: v for c, v in r.items() if c != "product_id"} for r in rows] for k, rows in store.history(pid).items()}
    return {"product": public(store.product(pid=pid)), **h}
