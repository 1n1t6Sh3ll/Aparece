# Webhooks (TEAM-51)

Outgoing, signed HTTP notifications for merchants about a monitored product. Code: `webhooks/` (store + delivery),
`api/webhooks_api.py` (routes), hook calls in `monitor/crawl.py`. Storage: its own SQLite file, `WEBHOOKS_DB`
(default `webhooks/data/webhooks.db`).

## Routes

All routes need the product's `X-Manage-Token` (returned once by `POST /v1/enroll`).

| Route | Purpose |
|---|---|
| `GET /v1/webhooks/events` | Event types you can subscribe to |
| `POST /v1/webhooks` `{product_id, url, events[]}` | Register (201). Returns `{webhook, secret}`; the `whsec_…` secret is shown **only here**. At most 10 per product |
| `GET /v1/webhooks` | Webhooks of every product managed by the token(s) (comma-separated); never includes secrets |
| `DELETE /v1/webhooks/{id}` | Remove (204); pending deliveries are cancelled |
| `POST /v1/webhooks/{id}/test` | Send one `webhook.test` event now; returns the delivery result |
| `GET /v1/webhooks/{id}/deliveries` | Last 50 deliveries: status (`pending`, `delivered`, `dead`, `cancelled`), attempts, last HTTP status/error, next attempt |

`POST` and `/test` share the monitor per-IP rate limit (`MONITOR_RATE_LIMIT`).

## Events

| Type | Emitted when | `data` |
|---|---|---|
| `snapshot.created` | Every monitor crawl / weekly visibility snapshot | `snapshot_id`, `change_count` |
| `product.changed` | A snapshot has change events | `snapshot_id`, `change_types[]`, `changes[{type, field, before, after}]` with types `DESCRIPTION_CHANGED`, `PRICE_CHANGED`, `ATTRIBUTE_ADDED`, `ATTRIBUTE_REMOVED`, `SCHEMA_CHANGED`, `LANGUAGE_PAGE_ADDED` |
| `visibility.changed` | Weekly AI-visibility result differs from the last one | `snapshot_id`, `before`, `after` |
| `audit.completed` | The gap audit that runs with each monitor crawl finished | `snapshot_id`, `quality_status`, `issue_count`, `metrics` |
| `experiment.result` | Reserved; accepted for subscription, **no emitter yet** | - |
| `optimizer.suggestion_ready` | Reserved; accepted for subscription, **no emitter yet** | - |

`experiment.result` and `optimizer.suggestion_ready` have no emitter because `api/experiments_api.py` and
`api/optimizer_api.py` are not tied to a monitored product id today. Wiring them is one call:
`webhooks.core.emit(product_public_id, "experiment.result", data)`.

## Payload

```json
{"id": "evt_…", "type": "product.changed", "created_at": "2026-09-29T03:00:00Z",
 "product": {"id": "<public product id>"}, "data": {…}}
```

No emails, tokens or other personal data are included. Headers: `Content-Type: application/json`,
`X-ProductLens-Event-Id`, `X-ProductLens-Event-Type`, `X-ProductLens-Signature: t=<unix seconds>,v1=<hex>`.

## Delivery

- **Signature**: `v1 = HMAC-SHA256(secret, "<t>." + raw body)`, hex.
- **Idempotency**: retries resend the identical body with the same event `id`; de-duplicate on it.
- **Success**: any 2xx within 5 s. Redirects are **not followed** (3xx counts as a failure).
- **SSRF guard**: the URL must pass `api/safe_fetch.check_url` (http(s), public addresses only, no Amazon) at
  registration and again before every attempt.
- **Retries**: up to 5 attempts, backoff `WEBHOOKS_BACKOFF_BASE` × 4^(n-1) seconds (default 30 s, 2 min, 8 min,
  32 min); then the delivery is dead-lettered (`dead`, kept for inspection).
- **Auto-disable**: after `WEBHOOKS_DISABLE_AFTER` (default 15) consecutive failed attempts the webhook is
  disabled (`active: false`, `disabled_reason`), its pending deliveries become `dead`. Delete and re-create to resume.
- **Worker**: the API retries due deliveries every `WEBHOOKS_POLL` s (default 15); `WEBHOOKS_WORKER=0` turns that
  off, then run `python -m webhooks deliver` from cron. The first attempt happens inline when the event is emitted.

## Verifying a signature

Python (same as `webhooks.core.verify`):

```python
import hashlib, hmac, time

def verify(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t = int(parts["t"])
    if abs(time.time() - t) > tolerance:
        return False  # replay protection
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))
```

Node.js:

```js
const crypto = require("crypto");
function verify(secret, rawBody, header, tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map(p => p.split("=", 2)));
  const t = Number(parts.t);
  if (Math.abs(Date.now() / 1000 - t) > tolerance) return false;
  const expected = crypto.createHmac("sha256", secret).update(`${t}.`).update(rawBody).digest("hex");
  return parts.v1?.length === expected.length && crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v1));
}
```

Always verify against the raw request bytes, before JSON parsing.

## Limits and known risks

- Secrets are stored in clear in `WEBHOOKS_DB` (needed to sign); protect that file like the monitor database.
- `check_url` resolves DNS before `requests` resolves it again, so a DNS-rebinding host could in principle pass the
  check and then resolve privately (same residual risk as `safe_fetch`).
- Tests: `python -m unittest discover -s api/tests -p "test_webhooks*.py"` (local mock receiver on 127.0.0.1).
