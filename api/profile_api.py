"""Merchant profile routes (TEAM-45). HTTP only; storage is profile/store.py (own SQLite, PROFILE_DB).

POST   /v1/profile                                create; returns a random access token ONCE (stored hashed)
GET|PUT|DELETE /v1/profile                        X-Profile-Token header
POST   /v1/profile/products                       add a product (URL, or manual details labelled merchant-stated)
DELETE /v1/profile/products/{id}
POST   /v1/profile/products/{id}/audit            runs /v1/audit and keeps the result + normalized record
PUT    /v1/profile/products/{id}/suggestion       records accept/dismiss of a /v1/optimize suggestion (never published)
POST|DELETE /v1/profile/share                     opt-in, revocable unlisted report link
POST   /v1/audits  /  GET /v1/audits/{id}      run /v1/audit and keep it under a random unlisted id (stable link)
GET    /v1/share/{token}                          read-only report: company name/website + audits; no personal data

Everything the merchant enters is merchant-stated and never verified here.
"""
import importlib.util
import math
import os
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, model_validator

import audit_api
import safe_fetch

_spec = importlib.util.spec_from_file_location(  # loaded by path: "profile" is also a stdlib module name
    "productlens_profile_store", Path(__file__).resolve().parents[1] / "profile" / "store.py")
store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store)

router = APIRouter(prefix="/v1", tags=["profile"])
_hits: "OrderedDict[tuple[str, str], deque]" = OrderedDict()


def rate_limit(request: Request, bucket: str, env: str, default: int):
    """Per-client sliding window (60 s) for the anonymous write routes. Proxy headers are trusted only with
    PROFILE_TRUST_PROXY=1 (same rule as monitor_api)."""
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[-1].strip() if fwd and os.environ.get("PROFILE_TRUST_PROXY") == "1" else (request.client.host if request.client else "?")
    limit, now, key = int(os.environ.get(env) or default), time.monotonic(), (bucket, ip)
    q = _hits.pop(key, None) or deque()
    _hits[key] = q
    while len(_hits) > 10000:
        _hits.popitem(last=False)
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        wait = max(1, math.ceil(60 - (now - q[0])))
        raise HTTPException(429, f"too_many_requests: too many requests from this network; try again in {wait} s",
                            headers={"Retry-After": str(wait)})
    q.append(now)
NOINDEX = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
Str = lambda n: Field("", max_length=n)  # noqa: E731
Lst = lambda n: Field(default_factory=list, max_length=n)  # noqa: E731


class Person(BaseModel):
    name: str = Str(120)
    role: str = Str(120)
    about: str = Str(2000)


class Company(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    website: str = Str(2048)
    sells: str = Str(1000)
    brand: str = Str(2000)
    markets: list[str] = Lst(30)
    languages: list[str] = Lst(20)
    price_positioning: Literal["", "budget", "mid", "premium", "luxury"] = ""
    audience: str = Str(1000)
    claims: list[str] = Lst(30)
    competitors: list[str] = Lst(20)
    platform: Literal["", "shopify", "woocommerce", "magento", "bigcommerce", "custom", "other"] = ""


class Product(BaseModel):
    url: str | None = Field(None, max_length=2048)
    title: str | None = Field(None, max_length=500)
    text: str | None = Field(None, max_length=20_000)
    price: str | None = Field(None, max_length=20)
    currency: str | None = Field(None, max_length=3)
    language: str | None = Field(None, max_length=35)

    @model_validator(mode="after")
    def one_input(self):
        if not (self.url or self.title):
            raise ValueError("provide a product url, or a title for manual details")
        if self.url and not self.url.lower().startswith(("http://", "https://")):
            raise ValueError("product url must be http(s)")
        return self

    def stored(self):
        """URL products are audited from the page; manual details are merchant-stated (unverified)."""
        if self.url:
            return {"source": "url", "url": self.url, "merchant_stated": False}
        return {"source": "manual", "merchant_stated": True,
                **{k: v for k, v in self.model_dump().items() if k != "url" and v not in (None, "")}}


class ProfileIn(BaseModel):
    person: Person = Field(default_factory=Person)
    company: Company
    language: Literal["en", "es"] = "en"


class CreateIn(ProfileIn):
    products: list[Product] = Field(default_factory=list, max_length=store.MAX_PRODUCTS)


class Decision(BaseModel):
    field: Literal["title", "description"]
    status: Literal["accepted", "dismissed"]
    original: str = Str(20_000)
    suggested: str = Str(20_000)


def stored_profile(p: ProfileIn):
    d = p.model_dump()
    c = d["company"]
    c["competitors"] = [u for u in c["competitors"] if u.strip()]
    c["claims"] = [{"text": s.strip()[:500], "source": "merchant_stated", "verified": False} for s in c["claims"] if s.strip()]
    d["merchant_stated"] = True  # the whole profile is what the merchant told us; nothing is verified
    return d


def need(value):
    if value is None:
        raise HTTPException(401, "missing or unknown X-Profile-Token")
    return value


@router.post("/profile", status_code=201)
def create(body: CreateIn, request: Request):
    rate_limit(request, "profile", "PROFILE_CREATE_RATE_LIMIT", 5)
    token, prof = store.create(stored_profile(body), [p.stored() for p in body.products])
    return {"token": token, "token_note": "Shown once. Store it safely; it cannot be recovered.", "profile": prof}


@router.get("/profile")
def read(x_profile_token: str | None = Header(None)):
    return need(store.get(x_profile_token))


@router.put("/profile")
def replace(body: ProfileIn, x_profile_token: str | None = Header(None)):
    return need(store.update(x_profile_token, stored_profile(body)))


@router.delete("/profile")
def remove(x_profile_token: str | None = Header(None)):
    need(store.delete(x_profile_token) or None)
    return {"deleted": True}


@router.post("/profile/products", status_code=201)
def add_product(body: Product, x_profile_token: str | None = Header(None)):
    try:
        return need(store.add_product(x_profile_token, body.stored()))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/profile/products/{pid}")
def remove_product(pid: int, x_profile_token: str | None = Header(None)):
    need(store.get(x_profile_token))
    if not store.remove_product(x_profile_token, pid):
        raise HTTPException(404, "product not found")
    return {"deleted": True}


def _payload(p):
    """The /v1/audit payload for a stored product: its URL, or the manual (merchant-stated) details as a draft."""
    if p["source"] != "manual":
        return {"url": p["url"]}
    payload = {k: p.get(k) for k in ("title", "price", "currency", "language") if p.get(k) not in (None, "")}
    if p.get("text"):
        payload["description"] = p["text"]
    return payload


def _prepare(payload):
    """(audit payload, ExtractRequest) for a /v1/audit-style payload: a URL is fetched once (safe_fetch) and the page is
    reused for the audit and for the normalized record; a draft is wrapped exactly as /v1/audit does."""
    import main  # lazy: main imports this module
    try:  # bad input is a 422 with the first validation message, as in /v1/audit (never a 500)
        if audit_api.is_draft(payload):
            return payload, audit_api.draft_request(main, audit_api.draft_fields(payload))
        req = main.ExtractRequest(**{k: payload.get(k) for k in ("url", "html", "text", "language") if payload.get(k)})
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"])
    except TypeError as e:
        raise HTTPException(422, str(e).splitlines()[0])
    if req.html or not req.url:
        return payload, req
    try:
        _, page = safe_fetch.fetch_page(req.url)
    except safe_fetch.FetchError as e:
        raise HTTPException(e.status, e.detail)
    return {**payload, "html": page}, main.ExtractRequest(url=req.url, html=page, language=req.language)


def _run(payload):
    """Run /v1/audit once and return (audit, normalized record for /v1/optimize)."""
    import main
    payload, req = _prepare(payload)
    try:
        result = audit_api.audit(payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"])
    except TypeError as e:
        raise HTTPException(422, str(e).splitlines()[0])
    return result, main.extract(req)["normalized"]


@router.post("/audits", status_code=201)
def stored_audit(request: Request, payload: dict = Body(...)):
    """/v1/audit plus a stable, unlisted link: the result is kept under a random id (GET /v1/audits/{id}).
    Only the public product page's audit is stored; no personal data. Results expire after AUDIT_RESULT_TTL_DAYS
    (default 90); the route is rate-limited per client (AUDIT_STORE_RATE_LIMIT per minute, default 60)."""
    rate_limit(request, "audits", "AUDIT_STORE_RATE_LIMIT", 60)
    result, record = _run(payload)
    return {"id": store.save_result(result, record), "audit": result, "record": record}


@router.get("/audits/{audit_id}")
def read_audit(audit_id: str, response: Response):
    response.headers.update(NOINDEX)
    r = store.result(audit_id) if 16 <= len(audit_id) <= 64 else None
    if not r:
        raise HTTPException(404, "audit not found", headers=NOINDEX)
    return r


@router.post("/profile/products/{pid}/audit")
def audit_product(pid: int, x_profile_token: str | None = Header(None)):
    need(store.get(x_profile_token))
    p = store.product(x_profile_token, pid)
    if not p:
        raise HTTPException(404, "product not found")
    result, record = _run(_payload(p))  # record = Product Truth for POST /v1/optimize suggestions
    return store.save_audit(x_profile_token, pid, result, record)


@router.put("/profile/products/{pid}/suggestion")
def decide(pid: int, body: Decision, x_profile_token: str | None = Header(None)):
    need(store.get(x_profile_token))
    p = store.set_suggestion(x_profile_token, pid, body.field, body.model_dump(exclude={"field"}))
    if not p:
        raise HTTPException(404, "product not found")
    return {**p, "note": "Recorded only. ProductLens never publishes to your store."}


@router.post("/profile/share")
def share_on(x_profile_token: str | None = Header(None)):
    need(store.get(x_profile_token))
    return {"share_token": store.set_share(x_profile_token, True)}


@router.delete("/profile/share")
def share_off(x_profile_token: str | None = Header(None)):
    need(store.get(x_profile_token))
    store.set_share(x_profile_token, False)
    return {"share_token": None}


@router.get("/share/{share_token}")
def shared(share_token: str, response: Response):
    response.headers.update(NOINDEX)
    p = store.shared(share_token) if 16 <= len(share_token) <= 64 else None
    if not p:
        raise HTTPException(404, "link not found or revoked", headers=NOINDEX)
    c = p["company"]
    return {"company": {"name": c["name"], "website": c.get("website") or ""}, "language": p.get("language", "en"),
            "products": [{k: x[k] for k in ("id", "source", "url", "title", "merchant_stated", "audit", "audited_at")
                          if k in x} for x in p["products"]]}
