"""Enrollment + monitoring routes (TEAM-28). Logic lives in monitor/; this file is HTTP only."""
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
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


def get_product(pid):
    p = store.product(pid=pid)
    if not p:
        raise HTTPException(404, "monitored product not found")
    return p


@router.get("/plans")
def plans():
    return {"plans": store.PLANS, "billing": False}


@router.post("/enroll", status_code=201)
async def enroll(req: EnrollRequest):
    if req.plan not in store.PLANS:
        raise HTTPException(422, f"plan must be one of {store.PLANS}")
    if req.email and not EMAIL.match(req.email):
        raise HTTPException(422, "invalid email")
    try:
        await run_in_threadpool(safe_fetch.check_url, req.url)
    except safe_fetch.FetchError as e:
        raise HTTPException(e.status, e.detail)
    p, created = store.enroll(req.url, req.email, req.plan)
    result = await run_in_threadpool(crawl.crawl, p["id"]) if req.crawl_now else None
    return {"product": p, "created": created, "crawl": result}


@router.get("/monitored")
def monitored():
    return {"results": store.monitored()}


@router.delete("/enroll/{pid}")
def unenroll(pid: int):
    get_product(pid)
    store.unenroll(pid)
    return {"id": pid, "active": False}


@router.post("/monitored/{pid}/crawl")
def recrawl(pid: int):
    get_product(pid)
    return crawl.crawl(pid)


@router.get("/products/{pid}/history")
def history(pid: int):
    return {"product": get_product(pid), **store.history(pid)}
