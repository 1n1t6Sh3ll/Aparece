"""SQLite store for enrolled products (TEAM-28). Snapshots and change events are append-only (triggers block edits).

MONITOR_DB: database path (default monitor/data/monitor.db).
"""
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "monitor.db"
PLANS = ["free", "pro", "team"]  # labels only; no billing

SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants (id INTEGER PRIMARY KEY, email TEXT UNIQUE, plan TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, merchant_id INTEGER REFERENCES merchants(id),
  url TEXT NOT NULL UNIQUE, enrolled_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  public_id TEXT, token_hash TEXT);
CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
  taken_at TEXT NOT NULL, content_hash TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_events (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id), at TEXT NOT NULL, type TEXT NOT NULL, field TEXT,
  before TEXT, after TEXT);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, product_id INTEGER, started_at TEXT NOT NULL,
  status TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS snapshot_metrics (snapshot_id INTEGER PRIMARY KEY REFERENCES snapshots(id), metrics TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT, 'snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON change_events BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON change_events BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def connect():
    """One transaction (commit on success, rollback on error); the connection is always closed."""
    path = Path(os.environ.get("MONITOR_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        migrate(db)
        with db:
            yield db
    finally:
        db.close()


def migrate(db):
    """Add public_id/token_hash to older databases and give every product a random public id."""
    cols = {r["name"] for r in db.execute("PRAGMA table_info(products)")}
    for c in ("public_id", "token_hash"):
        if c not in cols:
            db.execute(f"ALTER TABLE products ADD COLUMN {c} TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS products_public_id ON products(public_id)")
    for r in db.execute("SELECT id FROM products WHERE public_id IS NULL").fetchall():
        db.execute("UPDATE products SET public_id = ? WHERE id = ?", (new_public_id(), r["id"]))
    db.commit()


def new_public_id():
    return secrets.token_urlsafe(12)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def content_hash(content):
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def enroll(url, email=None, plan="free"):
    """Returns (product row, created). Re-enrolling a known URL reactivates it."""
    with connect() as db:
        m = db.execute("SELECT id FROM merchants WHERE email IS ? ORDER BY id LIMIT 1", (email,)).fetchone()
        if m:
            mid = m["id"]
            db.execute("UPDATE merchants SET plan = ? WHERE id = ?", (plan, mid))
        else:
            mid = db.execute("INSERT INTO merchants (email, plan, created_at) VALUES (?, ?, ?)",
                             (email, plan, utcnow())).lastrowid
        old = db.execute("SELECT id FROM products WHERE url = ?", (url,)).fetchone()
        if old:
            db.execute("UPDATE products SET active = 1 WHERE id = ?", (old["id"],))
        else:
            db.execute("INSERT INTO products (merchant_id, url, enrolled_at, public_id) VALUES (?, ?, ?, ?)",
                       (mid, url, utcnow(), new_public_id()))
    return product(url=url), old is None


def product(pid=None, url=None):
    with connect() as db:
        row = db.execute("SELECT p.*, m.email, m.plan FROM products p LEFT JOIN merchants m ON m.id = p.merchant_id "
                         "WHERE p.id = ? OR p.url = ?", (pid, url)).fetchone()
    return dict(row) if row else None


def pid_for(public_id):
    """Internal id for a public id, or None."""
    with connect() as db:
        row = db.execute("SELECT id FROM products WHERE public_id = ?", (public_id,)).fetchone()
    return row["id"] if row else None


def issue_token(pid):
    """Return a new manage token (stored hashed) if the product has none yet; otherwise None (shown only once)."""
    token = secrets.token_urlsafe(32)
    with connect() as db:
        n = db.execute("UPDATE products SET token_hash = ? WHERE id = ? AND token_hash IS NULL",
                       (hash_token(token), pid)).rowcount
    return token if n else None


def check_token(pid, token):
    with connect() as db:
        row = db.execute("SELECT token_hash FROM products WHERE id = ?", (pid,)).fetchone()
    return bool(row and row["token_hash"] and token and secrets.compare_digest(row["token_hash"], hash_token(token)))


def unenroll(pid):
    with connect() as db:
        return db.execute("UPDATE products SET active = 0 WHERE id = ?", (pid,)).rowcount > 0


def monitored(active_only=False):
    q = ("SELECT p.id, p.public_id, p.url, p.enrolled_at, p.active, m.plan, "
         "(SELECT taken_at FROM snapshots s WHERE s.product_id = p.id ORDER BY s.id DESC LIMIT 1) AS last_snapshot_at, "
         "(SELECT content_hash FROM snapshots s WHERE s.product_id = p.id ORDER BY s.id DESC LIMIT 1) AS last_hash, "
         "(SELECT COUNT(*) FROM snapshots s WHERE s.product_id = p.id) AS snapshot_count, "
         "(SELECT COUNT(*) FROM change_events e WHERE e.product_id = p.id) AS event_count "
         "FROM products p LEFT JOIN merchants m ON m.id = p.merchant_id" + (" WHERE p.active = 1" if active_only else "")
         + " ORDER BY p.id")
    with connect() as db:
        return [dict(r) for r in db.execute(q)]


def last_snapshot(pid):
    with connect() as db:
        row = db.execute("SELECT * FROM snapshots WHERE product_id = ? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    return {**dict(row), "data": json.loads(row["data"])} if row else None


def add_snapshot(pid, data, events):
    """data: {"content": ..., ...}; the hash covers content only. events: dicts from monitor.changes.diff."""
    at = utcnow()
    with connect() as db:
        sid = db.execute("INSERT INTO snapshots (product_id, taken_at, content_hash, data) VALUES (?, ?, ?, ?)",
                         (pid, at, content_hash(data["content"]), json.dumps(data, ensure_ascii=False))).lastrowid
        db.executemany("INSERT INTO change_events (product_id, snapshot_id, at, type, field, before, after) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)",
                       [(pid, sid, at, e["type"], e.get("field"), json.dumps(e.get("before"), ensure_ascii=False),
                         json.dumps(e.get("after"), ensure_ascii=False)) for e in events])
    return sid


def snapshot(pid, sid):
    """One snapshot of product pid (None if it belongs to another product)."""
    with connect() as db:
        row = db.execute("SELECT * FROM snapshots WHERE id = ? AND product_id = ?", (sid, pid)).fetchone()
    return {**dict(row), "data": json.loads(row["data"])} if row else None


def cached_metrics(sid):
    with connect() as db:
        row = db.execute("SELECT metrics FROM snapshot_metrics WHERE snapshot_id = ?", (sid,)).fetchone()
    return json.loads(row["metrics"]) if row else None


def cache_metrics(sid, metrics):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO snapshot_metrics (snapshot_id, metrics) VALUES (?, ?)",
                   (sid, json.dumps(metrics, ensure_ascii=False)))


def history(pid):
    with connect() as db:
        snaps = [{**dict(r), "data": json.loads(r["data"])}
                 for r in db.execute("SELECT * FROM snapshots WHERE product_id = ? ORDER BY id", (pid,))]
        events = [{**dict(r), "before": json.loads(r["before"]), "after": json.loads(r["after"])}
                  for r in db.execute("SELECT * FROM change_events WHERE product_id = ? ORDER BY id", (pid,))]
        runs = [dict(r) for r in db.execute("SELECT * FROM runs WHERE product_id = ? ORDER BY id DESC LIMIT 20", (pid,))]
    return {"snapshots": snaps, "events": events, "runs": runs}


def log_run(kind, status, detail=None, product_id=None):
    with connect() as db:
        db.execute("INSERT INTO runs (kind, product_id, started_at, status, detail) VALUES (?, ?, ?, ?, ?)",
                   (kind, product_id, utcnow(), status, detail))
