"""Append-only audit log + approval requests in their own SQLite file.

GOVERNANCE_DB: database path (default governance/data/governance.db).
audit_log rows cannot be updated or deleted (triggers abort). Approvals are mutable state,
but every state change is also written to audit_log.
"""
import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "governance.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  target TEXT, mode TEXT NOT NULL, outcome TEXT NOT NULL, approved_by TEXT, approval_id TEXT, details_hash TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, action TEXT NOT NULL, target TEXT, requested_by TEXT NOT NULL, details_hash TEXT,
  status TEXT NOT NULL, approved_by TEXT, created TEXT NOT NULL, decided TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def details_hash(details):
    return hashlib.sha256(json.dumps(details or {}, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


@contextmanager
def connect():
    path = Path(os.environ.get("GOVERNANCE_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def _log(db, actor, action, target, mode, outcome, dhash, approved_by=None, approval_id=None):
    db.execute("INSERT INTO audit_log (ts, actor, action, target, mode, outcome, approved_by, approval_id, details_hash) "
               "VALUES (?,?,?,?,?,?,?,?,?)", (now(), actor, action, target, mode, outcome, approved_by, approval_id, dhash))


def log(actor, action, target, mode, outcome, dhash, approved_by=None, approval_id=None):
    with connect() as db:
        _log(db, actor, action, target, mode, outcome, dhash, approved_by, approval_id)


def entries(limit=100):
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


def request(action, target, actor, dhash):
    """Reuse an open request for the same action/target/details, else create one. Returns its id."""
    with connect() as db:
        row = db.execute("SELECT id FROM approvals WHERE action=? AND target IS ? AND details_hash=? AND status='pending'",
                         (action, target, dhash)).fetchone()
        if row:
            return row["id"]
        aid = uuid.uuid4().hex
        db.execute("INSERT INTO approvals (id, action, target, requested_by, details_hash, status, created) "
                   "VALUES (?,?,?,?,?,'pending',?)", (aid, action, target, actor, dhash, now()))
        _log(db, actor, action, target, "approve", "pending", dhash, approval_id=aid)
        return aid


def get(aid):
    with connect() as db:
        row = db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None


def pending():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY created")]


def decide(aid, approver, approve):
    """pending -> approved|rejected. Returns the updated row or None if not pending."""
    status = "approved" if approve else "rejected"
    with connect() as db:
        cur = db.execute("UPDATE approvals SET status=?, approved_by=?, decided=? WHERE id=? AND status='pending'",
                         (status, approver, now(), aid))
        if not cur.rowcount:
            return None
        row = dict(db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone())
        _log(db, approver, row["action"], row["target"], "approve", status, row["details_hash"], approver, aid)
        return row


def consume(aid, action, target, dhash, actor):
    """approved -> used, only if it matches exactly. Returns approver or None. Logs the executed action."""
    with connect() as db:
        cur = db.execute("UPDATE approvals SET status='used' WHERE id=? AND action=? AND target IS ? AND details_hash=? "
                         "AND status='approved'", (aid, action, target, dhash))
        if not cur.rowcount:
            return None
        approver = db.execute("SELECT approved_by FROM approvals WHERE id=?", (aid,)).fetchone()[0]
        _log(db, actor, action, target, "approve", "allowed", dhash, approver, aid)
        return approver
