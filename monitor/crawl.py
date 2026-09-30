"""Crawl enrolled products: safe_fetch -> extract/normalize (api/main.py) -> gaps (analysis/) -> snapshot + change events."""
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "api", ROOT / "dataset" / "collect"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import safe_fetch  # noqa: E402
from extract import build_raw  # noqa: E402

from monitor import changes, store  # noqa: E402

log = logging.getLogger("monitor")


def normalize_page(url, final_url, html):
    import main  # lazy: main imports monitor_api, which imports this module
    host = urlsplit(final_url).hostname or "unknown"
    raw = build_raw(main.product_from_page(html), html, url, final_url, {"merchant": host, "domain": host}, store.utcnow())
    return main.backend()(raw)


def gaps_for(norm):
    """Gaps vs peers from the local dataset (same as /v1/products/{pid}/gaps); None if unavailable."""
    try:
        import dashboard_api
        from analysis.gaps import analyze
        from analysis.peers import find_peers
        out = analyze(norm, find_peers(norm, dashboard_api.records(), 10))
        return {"metrics": out.get("metrics"), "issues": out.get("issues")}
    except Exception as e:  # gaps are advisory; never fail a crawl on them
        log.warning("gaps skipped: %s", e)
        return None


def snapshot(pid, url, html, final_url=None, visibility=None):
    """Store one immutable snapshot for html; returns (snapshot_id, events)."""
    norm = normalize_page(url, final_url or url, html)
    prev = store.last_snapshot(pid)
    old = prev["data"]["content"] if prev else None
    if visibility is None and old:
        visibility = old.get("visibility")  # carry the last weekly result forward
    new = changes.content(norm, html, visibility)
    events = changes.diff(old, new)
    sid = store.add_snapshot(pid, {"content": new, "product_id": norm["product_id"],
                                   "quality_status": norm["quality_status"], "gaps": gaps_for(norm)}, events)
    return sid, events


def crawl(pid):
    """Fetch (robots.txt + SSRF guard via safe_fetch) and snapshot one product. Returns a result dict."""
    p = store.product(pid=pid)
    try:
        final, html = safe_fetch.fetch_page(p["url"])
        sid, events = snapshot(pid, p["url"], html, final)
    except safe_fetch.FetchError as e:
        store.log_run("crawl", "error", f"{e.status} {e.detail}", pid)
        return {"status": "error", "detail": e.detail}
    except Exception as e:  # a bad page must not stop the daily job
        log.exception("crawl failed for %s", pid)
        store.log_run("crawl", "error", type(e).__name__, pid)
        return {"status": "error", "detail": "extraction failed"}
    store.log_run("crawl", "ok", f"snapshot {sid}, {len(events)} events", pid)
    return {"status": "ok", "snapshot_id": sid, "events": events}


def crawl_all():
    """Daily job: every active product, politely spaced (MONITOR_DELAY seconds, default 2)."""
    delay = float(os.environ.get("MONITOR_DELAY", "2"))
    results = {}
    for i, p in enumerate(store.monitored(active_only=True)):
        if i:
            time.sleep(delay)
        results[p["id"]] = crawl(p["id"])
    log.info("daily crawl: %s", results)
    return results


def benchmark_runner(urls, max_usd):
    """Run benchmark/harness over enrolled products; returns {url: {model: product metrics}}.
    BENCHMARK_MODELS (e.g. anthropic:claude-haiku-4-5), BENCHMARK_PROMPTS (default examples), BENCHMARK_REPEATS (1)."""
    import json
    import tempfile
    from argparse import Namespace

    from benchmark import harness
    from benchmark.match import load_catalog
    from benchmark.metrics import build_report

    catalog = []
    for p in store.monitored(active_only=True):
        snap = store.last_snapshot(p["id"])
        if p["url"] in urls and snap:
            c = snap["data"]["content"]
            catalog.append({"product_id": snap["data"]["product_id"],
                            "source": {"url": p["url"], "merchant_domain": urlsplit(p["url"]).hostname},
                            "identity": {"brand": c["attributes"].get("identity.brand"), "product_name": c["title"]}})
    models = [m.strip() for m in os.environ.get("BENCHMARK_MODELS", "").split(",") if m.strip()]
    if not catalog or not models:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        cat, out = Path(tmp) / "catalog.jsonl", Path(tmp) / "runs.jsonl"
        cat.write_text("\n".join(json.dumps(r) for r in catalog), encoding="utf-8")
        harness.run(Namespace(
            prompts=os.environ.get("BENCHMARK_PROMPTS") or str(harness.HERE / "examples" / "prompts.example.jsonl"),
            models=models, out=str(out), catalog=str(cat), prices=str(harness.HERE / "prices.json"),
            splits={"dev", "val"}, repeats=int(os.environ.get("BENCHMARK_REPEATS", "1")), shuffle=False,
            system=harness.DEFAULT_SYSTEM, temperature=0.7, max_tokens=600, max_usd=max_usd, dry_run=False,
            min_interval=float(os.environ.get("BENCHMARK_MIN_INTERVAL", "1")), retries=3), log=log.info)
        records = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
        products = load_catalog(cat)
    report = build_report(records, products) if records else {"models": {}}
    by_pid = {r["product_id"]: r["source"]["url"] for r in catalog}
    vis = {}
    for model, m in report["models"].items():
        for pid, metrics in m["products"].items():
            vis.setdefault(by_pid[pid], {})[model] = metrics
    return vis


def visibility_all(runner=None):
    """Weekly job. Runs only with an API key and BENCHMARK_MAX_USD set; otherwise logs 'skipped'. No other spend."""
    keys = any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"))
    cap = os.environ.get("BENCHMARK_MAX_USD")
    runner = runner or benchmark_runner
    reason = "no API key" if not keys else None if cap else "BENCHMARK_MAX_USD not set"
    if reason:
        store.log_run("visibility", "skipped", reason)
        log.info("weekly visibility skipped: %s", reason)
        return {"status": "skipped", "detail": reason}
    prods = store.monitored(active_only=True)
    try:
        results = runner([p["url"] for p in prods], max_usd=float(cap))
    except (SystemExit, Exception) as e:  # harness exits on missing key/price; never crash the scheduler
        store.log_run("visibility", "error", str(e)[:200])
        log.warning("weekly visibility failed: %s", e)
        return {"status": "error", "detail": str(e)[:200]}
    for p in prods:
        prev = store.last_snapshot(p["id"])
        vis = results.get(p["url"])
        if prev and vis is not None:  # re-snapshot the last content with the new visibility result
            new = {**prev["data"]["content"], "visibility": vis}
            events = changes.diff(prev["data"]["content"], new)
            store.add_snapshot(p["id"], {**prev["data"], "content": new}, events)
    store.log_run("visibility", "ok", f"{len(prods)} products, cap {cap} USD")
    return {"status": "ok"}
