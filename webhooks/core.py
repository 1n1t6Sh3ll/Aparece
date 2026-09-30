"""Outgoing merchant webhooks (TEAM-51): emit events, sign, deliver with retries, dead-letter, auto-disable.

Delivery: POST JSON {id, type, created_at, product: {id}, data} with headers X-ProductLens-Event-Id and
X-ProductLens-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>. Every attempt re-runs
safe_fetch.check_url (public http(s) only), redirects are not followed (3xx = failure), timeout 5 s, 2xx = delivered.
Failed attempts retry with exponential backoff (WEBHOOKS_BACKOFF_BASE s, default 30: 30 s, 2 min, 8 min, 32 min);
after WEBHOOKS_MAX_ATTEMPTS (5) the delivery is dead-lettered. A webhook is disabled after WEBHOOKS_DISABLE_AFTER
(default 15) consecutive failed attempts. Retries run in the API's worker thread (WEBHOOKS_WORKER=0 turns it off)
or via `python -m webhooks deliver` from cron. No emails or other PII are ever put in payloads.
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "api", ROOT / "dataset" / "collect"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import requests  # noqa: E402

import safe_fetch  # noqa: E402
from webhooks import store  # noqa: E402

log = logging.getLogger("webhooks")
EVENTS = ("audit.completed", "product.changed", "snapshot.created", "visibility.changed", "experiment.result",
          "optimizer.suggestion_ready")
TEST_EVENT = "webhook.test"
TIMEOUT = 5
USER_AGENT = "ProductLens-Webhooks/1"


def env_int(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def sign(secret, body, t=None):
    """Signature header value for body (bytes or str)."""
    t = int(time.time()) if t is None else int(t)
    body = body.encode() if isinstance(body, str) else body
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify(secret, body, header, tolerance=300, now=None):
    """Receiver-side check (documented in docs/WEBHOOKS.md): valid v1 signature and timestamp within tolerance s."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t = int(parts["t"])
    except (ValueError, KeyError, AttributeError):
        return False
    if abs((time.time() if now is None else now) - t) > tolerance:
        return False
    return hmac.compare_digest(sign(secret, body, t), f"t={t},v1={parts.get('v1', '')}")


def emit(product_public_id, type_, data, only_webhook=None):
    """Queue one event for every active webhook of the product subscribed to type_ and try delivery now.
    Never raises (a webhook problem must not break a crawl). Returns the event id, or None if nobody listens."""
    try:
        hooks = [w for w in store.for_products([product_public_id]) if w["active"]
                 and (only_webhook == w["id"] if only_webhook else type_ in json.loads(w["events"]))]
        if not hooks:
            return None
        eid, at = "evt_" + secrets.token_urlsafe(16), store.utcnow()
        body = json.dumps({"id": eid, "type": type_, "created_at": at, "product": {"id": product_public_id},
                           "data": data}, ensure_ascii=False, separators=(",", ":"), default=str)
        store.add_event(eid, type_, product_public_id, at, body, [w["id"] for w in hooks])
        deliver_due(event_id=eid)
        return eid
    except Exception:
        log.exception("webhook emit failed (%s)", type_)
        return None


def emit_snapshot(product_public_id, snapshot_id, events, record=None, gaps=None):
    """Monitor hook: one snapshot and its change events -> snapshot.created, product.changed, visibility.changed,
    audit.completed (the gap audit that runs with each crawl; only when `record` is given)."""
    if not product_public_id:
        return
    emit(product_public_id, "snapshot.created", {"snapshot_id": snapshot_id, "change_count": len(events)})
    vis = [e for e in events if e["type"] == "VISIBILITY_CHANGED"]
    other = [e for e in events if e["type"] != "VISIBILITY_CHANGED"]
    if other:
        emit(product_public_id, "product.changed", {"snapshot_id": snapshot_id, "changes": other,
                                                    "change_types": sorted({e["type"] for e in other})})
    for e in vis:
        emit(product_public_id, "visibility.changed", {"snapshot_id": snapshot_id, "before": e["before"],
                                                       "after": e["after"]})
    if record is not None:
        issues = (gaps or {}).get("issues") or []
        emit(product_public_id, "audit.completed", {"snapshot_id": snapshot_id,
                                                    "quality_status": record.get("quality_status"),
                                                    "issue_count": len(issues), "metrics": (gaps or {}).get("metrics")})


def attempt(d):
    """One HTTP attempt. Returns (ok, status_code, error)."""
    try:
        safe_fetch.check_url(d["url"])
    except safe_fetch.FetchError as e:
        return False, None, f"url rejected: {e.detail}"[:200]
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, "X-ProductLens-Event-Id": d["event_id"],
               "X-ProductLens-Event-Type": d["type"], "X-ProductLens-Signature": sign(d["secret"], d["body"])}
    try:
        r = requests.post(d["url"], data=d["body"].encode(), headers=headers, timeout=TIMEOUT, allow_redirects=False)
        r.close()
    except requests.RequestException as e:
        return False, None, type(e).__name__
    if 200 <= r.status_code < 300:
        return True, r.status_code, None
    return False, r.status_code, "redirect not followed" if 300 <= r.status_code < 400 else f"HTTP {r.status_code}"


def deliver_due(webhook_id=None, event_id=None, now=None):
    """Attempt every due pending delivery (optionally one webhook / one event). Returns the outcomes."""
    now = time.time() if now is None else now
    base, max_attempts = env_int("WEBHOOKS_BACKOFF_BASE", 30), env_int("WEBHOOKS_MAX_ATTEMPTS", 5)
    disable_after = env_int("WEBHOOKS_DISABLE_AFTER", 15)
    out = []
    for d in store.due(now, webhook_id=webhook_id, event_id=event_id):
        if not d["active"]:
            ok, code, err = False, None, "webhook disabled"
            n, status, next_at = d["attempts"], "dead", None
        else:
            ok, code, err = attempt(d)
            n = d["attempts"] + 1
            status = "delivered" if ok else "dead" if n >= max_attempts else "pending"
            next_at = now + base * 4 ** (n - 1) if status == "pending" else None
        store.record(d["id"], d["webhook_id"], status, n, next_at, code, err, disable_after)
        out.append({"event_id": d["event_id"], "status": status, "attempts": n, "status_code": code, "error": err})
    return out


_stop = threading.Event()
_thread = None


def start_worker():
    """Retry loop for the API process (every WEBHOOKS_POLL s, default 15). Off when WEBHOOKS_WORKER=0."""
    global _thread
    if os.environ.get("WEBHOOKS_WORKER") == "0" or (_thread and _thread.is_alive()):
        return
    _stop.clear()

    def loop():
        while not _stop.wait(env_int("WEBHOOKS_POLL", 15)):
            try:
                deliver_due()
            except Exception:
                log.exception("webhook worker pass failed")
    _thread = threading.Thread(target=loop, name="webhooks", daemon=True)
    _thread.start()


def stop_worker():
    _stop.set()
