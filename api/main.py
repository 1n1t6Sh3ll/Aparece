"""ProductLens API v1 (issue #30). Reuses dataset/collect extract.py + normalize.py; no logic duplicated here."""
import hashlib
import html as htmllib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset" / "collect"))

from bs4 import BeautifulSoup  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from pydantic import BaseModel, Field, model_validator  # noqa: E402

from extract import as_list, build_raw, json_ld_nodes, ld_type  # noqa: E402
from normalize import build_normalized  # noqa: E402
import safe_fetch  # noqa: E402
import dashboard_api  # noqa: E402
import monitor_api  # noqa: E402
import audit_api  # noqa: E402

VERSION = "0.1.0"
app = FastAPI(title="Aparece API", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.include_router(dashboard_api.router)
app.include_router(monitor_api.router)
app.include_router(audit_api.router)  # also serves the web UI at "/" and "/assets/*" (exact routes, no catch-all)
try:  # governance/ may be missing from older images; the API still starts without it
    import governance_api  # noqa: E402
    app.include_router(governance_api.router)
except ModuleNotFoundError:
    pass
try:  # optimizer/ may be missing from older images
    import optimizer_api  # noqa: E402
    app.include_router(optimizer_api.router)
except ModuleNotFoundError:
    pass
try:  # experiments/ may be missing from older images; the API still starts without it
    import experiments_api  # noqa: E402
    app.include_router(experiments_api.router)
except ModuleNotFoundError:
    pass
try:  # profile/ may be missing from older images; the API still starts without it
    import profile_api  # noqa: E402
    app.include_router(profile_api.router)
except (ModuleNotFoundError, FileNotFoundError):
    pass
try:  # chat/ may be missing from older images
    import chat_api  # noqa: E402
    app.include_router(chat_api.router)
except ModuleNotFoundError:
    pass
try:  # TEAM-47 shoot-out report route; optional like the others
    import shootout_api  # noqa: E402
    app.include_router(shootout_api.router)
except ModuleNotFoundError:
    pass
try:  # live AI-assistant visibility check (needs benchmark/; optional like the others)
    import visibility_live_api  # noqa: E402
    app.include_router(visibility_live_api.router)
except ModuleNotFoundError:
    pass
try:  # TEAM-51 outgoing webhooks; webhooks/ may be missing from older images
    import webhooks_api  # noqa: E402
    app.include_router(webhooks_api.router)
except ModuleNotFoundError:
    pass


@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard/{rest:path}", include_in_schema=False)
def old_dashboard(rest: str = ""):
    """The static analyst dashboard was replaced by the web app at "/"; keep old links working."""
    return RedirectResponse("/", status_code=307)


class ExtractRequest(BaseModel):
    url: str | None = Field(None, max_length=2048)
    html: str | None = Field(None, max_length=safe_fetch.MAX_BYTES)
    text: str | None = Field(None, max_length=200_000)
    language: str | None = Field(None, max_length=35, description="Overrides the page's <html lang>.")

    @model_validator(mode="after")
    def one_input(self):
        if not (self.url or self.html or self.text):
            raise ValueError("provide url, html or text")
        if self.html and self.text:
            raise ValueError("provide html or text, not both")
        return self


def product_from_page(html):
    """Minimal products.json-shaped dict from the page's JSON-LD so build_raw works on any page, not only Shopify."""
    _, nodes = json_ld_nodes(BeautifulSoup(html, "html.parser"))
    top = next((n for n in nodes if ld_type(n, "Product")), None) or next((n for n in nodes if ld_type(n, "ProductGroup")), {})
    offers = [o for o in as_list(top.get("offers")) if isinstance(o, dict)]
    product = {"title": top.get("name") if isinstance(top.get("name"), str) else None}
    if isinstance(top.get("description"), str):
        product["body_html"] = "<p>" + htmllib.escape(top["description"]).replace("\n", "<br>") + "</p>"
    variants = [{"id": str(o.get("sku") or i + 1), "sku": o.get("sku"), "price": o.get("price") or o.get("lowPrice"),
                 "available": "instock" in str(o.get("availability", "")).lower()} for i, o in enumerate(offers)]
    if variants:
        product["variants"] = variants
    return product


def rules_backend(raw):
    return build_normalized(raw)


def qwen_backend(raw):
    import model_backend  # lazy: needs train/ + dataset/schema, which the rules-only Docker image does not ship
    return model_backend.qwen_backend(raw)


BACKENDS = {"rules": rules_backend, "qwen": qwen_backend}


def backend():
    name = os.environ.get("MODEL_BACKEND", "rules")
    if name not in BACKENDS:
        raise HTTPException(500, f"unknown MODEL_BACKEND {name!r}")
    return BACKENDS[name]


@app.get("/v1/health")
def health():
    return {"status": "ok", "version": VERSION, "model_backend": os.environ.get("MODEL_BACKEND", "rules")}


@app.post("/v1/extract")
def extract(req: ExtractRequest):
    normalize = backend()
    if req.html or req.text:
        page = req.html or "<html></html>"
        product = product_from_page(page)
        if req.text:
            product["body_html"] = "".join(f"<p>{htmllib.escape(ln)}</p>" for ln in req.text.splitlines())
        url = req.url or "https://unknown.invalid/" + hashlib.sha256((req.html or req.text).encode()).hexdigest()[:16]
        final_url = url
    else:
        try:
            final_url, page = safe_fetch.fetch_page(req.url)
        except safe_fetch.FetchError as e:
            raise HTTPException(e.status, e.detail)
        url, product = req.url, product_from_page(page)
    host = urlsplit(final_url).hostname or "unknown"
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    raw = build_raw(product, page, url, final_url, {"merchant": host, "domain": host}, scraped_at)
    if req.language:
        raw["page_language"] = req.language
    norm = normalize(raw)
    model = norm.pop("_model", {})  # qwen only: {predicted, model_status}, kept out of the schema-bound record
    archive = getattr(page, "archive", None)  # set only for a page read from a Common Crawl copy, not the live page
    return {"product_id": raw["product_id"], "language": raw["page_language"], "raw": raw, "normalized": norm,
            "evidence": norm["evidence"], "conflicts": norm["conflicts"], "quality_status": norm["quality_status"],
            **({"archive": archive} if archive else {}), **model}
