"""SQLite store for outgoing merchant webhooks (TEAM-51). Own database, separate from monitor.db.

WEBHOOKS_DB: database path (default webhooks/data/webhooks.db).
Secrets are kept in clear here because every delivery must be signed with them; they are returned by the API once.
"""
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "webhooks.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS webhooks (id TEXT PRIMARY KEY, product_public_id TEXT NOT NULL, url TEXT NOT NULL,
  events TEXT NOT NULL, secret TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  deleted INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, disabled_reason TEXT);
CREATE INDEX IF NOT EXISTS webhooks_product ON webhooks(product_public_id);
CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, type TEXT NOT NULL, product_public_id TEXT NOT NULL,
  created_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries (id INTEGER PRIMARY KEY, webhook_id TEXT NOT NULL REFERENCES webhooks(id),
  event_id TEXT NOT NULL REFERENCES events(id), status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL, last_status_code INTEGER, last_error TEXT, created_at TEXT NOT NULL, delivered_at TEXT,
  UNIQUE (webhook_id, event_id));
CREATE INDEX IF NOT EXISTS deliveries_due ON deliveries(status, next_attempt_at);
"""
PUBLIC = ("id", "product_public_id", "url", "events", "created_at", "active", "failures", "disabled_reason")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def connect():
    path = Path(os.environ.get("WEBHOOKS_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def public(row):
    """API shape of a webhook: never the secret."""
    d = {k: row[k] for k in PUBLIC}
    d["events"], d["active"] = json.loads(d["events"]), bool(d["active"])
    return d


def create(product_public_id, url, events):
    """Returns (webhook, secret); the secret is shown to the caller once."""
    wid, secret = "wh_" + secrets.token_urlsafe(12), "whsec_" + secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("INSERT INTO webhooks (id, product_public_id, url, events, secret, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (wid, product_public_id, url, json.dumps(sorted(set(events))), secret, utcnow()))
    return get(wid), secret


def get(wid):
    with connect() as db:
        row = db.execute("SELECT * FROM webhooks WHERE id = ? AND deleted = 0", (wid,)).fetchone()
    return dict(row) if row else None


def for_products(public_ids):
    ids = list(public_ids)
    if not ids:
        return []
    with connect() as db:
        rows = db.execute(f"SELECT * FROM webhooks WHERE deleted = 0 AND product_public_id IN ({','.join('?' * len(ids))}) "
                          "ORDER BY created_at, id", ids).fetchall()
    return [dict(r) for r in rows]


def count(product_public_id):
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM webhooks WHERE deleted = 0 AND product_public_id = ?",
                          (product_public_id,)).fetchone()[0]


def delete(wid):
    """Soft delete (delivery history stays for audit); pending deliveries are dropped."""
    with connect() as db:
        db.execute("UPDATE webhooks SET deleted = 1, active = 0 WHERE id = ?", (wid,))
        db.execute("UPDATE deliveries SET status = 'cancelled', next_attempt_at = NULL "
                   "WHERE webhook_id = ? AND status = 'pending'", (wid,))


def add_event(event_id, type_, product_public_id, created_at, body, webhook_ids):
    """Store an event and one pending delivery per webhook. Idempotent per (webhook, event id)."""
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO events (id, type, product_public_id, created_at, body) VALUES (?, ?, ?, ?, ?)",
                   (event_id, type_, product_public_id, created_at, body))
        db.executemany("INSERT OR IGNORE INTO deliveries (webhook_id, event_id, status, next_attempt_at, created_at) "
                       "VALUES (?, ?, 'pending', 0, ?)", [(w, event_id, created_at) for w in webhook_ids])


def due(now, limit=100, webhook_id=None, event_id=None):
    q = ("SELECT d.id, d.webhook_id, d.event_id, d.attempts, e.body, e.type, w.url, w.secret, w.active "
         "FROM deliveries d JOIN events e ON e.id = d.event_id JOIN webhooks w ON w.id = d.webhook_id "
         "WHERE d.status = 'pending' AND d.next_attempt_at <= ?")
    args = [now]
    if webhook_id:
        q, args = q + " AND d.webhook_id = ?", args + [webhook_id]
    if event_id:
        q, args = q + " AND d.event_id = ?", args + [event_id]
    with connect() as db:
        return [dict(r) for r in db.execute(q + " ORDER BY d.id LIMIT ?", args + [limit])]


def record(delivery_id, webhook_id, status, attempts, next_at, code, error, disable_after):
    """Save one attempt's outcome and the webhook's consecutive-failure count; disables the webhook (and dead-letters
    its pending deliveries) after `disable_after` consecutive failed attempts."""
    with connect() as db:
        db.execute("UPDATE deliveries SET status = ?, attempts = ?, next_attempt_at = ?, last_status_code = ?, "
                   "last_error = ?, delivered_at = CASE WHEN ? = 'delivered' THEN ? ELSE delivered_at END WHERE id = ?",
                   (status, attempts, next_at, code, error, status, utcnow(), delivery_id))
        if status == "delivered":
            db.execute("UPDATE webhooks SET failures = 0 WHERE id = ?", (webhook_id,))
            return
        db.execute("UPDATE webhooks SET failures = failures + 1 WHERE id = ?", (webhook_id,))
        if db.execute("SELECT failures FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()[0] >= disable_after:
            db.execute("UPDATE webhooks SET active = 0, disabled_reason = ? WHERE id = ? AND active = 1",
                       (f"disabled after {disable_after} consecutive failed deliveries", webhook_id))
            db.execute("UPDATE deliveries SET status = 'dead', next_attempt_at = NULL, "
                       "last_error = COALESCE(last_error, 'webhook disabled') WHERE webhook_id = ? AND status = 'pending'",
                       (webhook_id,))


def deliveries(webhook_id, limit=50):
    with connect() as db:
        rows = db.execute("SELECT d.id, d.event_id, e.type, d.status, d.attempts, d.last_status_code, d.last_error, "
                          "d.next_attempt_at, d.created_at, d.delivered_at FROM deliveries d "
                          "JOIN events e ON e.id = d.event_id WHERE d.webhook_id = ? ORDER BY d.id DESC LIMIT ?",
                          (webhook_id, limit)).fetchall()
    return [dict(r) for r in rows]
