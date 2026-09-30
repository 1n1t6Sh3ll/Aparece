"""Merchant profile store (TEAM-45). Own SQLite file; nothing here is shared with monitor/ or governance/.

PROFILE_DB: database path (default profile/data/profile.db).
Why a hash lookup is enough (no constant-time compare): tokens are 256-bit random values and only their SHA-256 is
stored; lookup is `WHERE token_hash = ?` on the hash, so timing can at most leak bytes of a hash of an unguessable
secret, which does not help an attacker find the token. Share and result ids are 128/192-bit random and unlisted.
Access tokens and share tokens are random (secrets.token_urlsafe); only the SHA-256 of the access token is stored,
so a token is shown once at sign-up and cannot be recovered. Everything the merchant types is merchant-stated and
never verified by ProductLens; audits are stored as returned by /v1/audit.
"""
import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "profile.db"
MAX_PRODUCTS = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, share_token TEXT UNIQUE,
  data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL REFERENCES profiles(id)
  ON DELETE CASCADE, data TEXT NOT NULL, audit TEXT, record TEXT, audited_at TEXT, suggestions TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, audit TEXT NOT NULL, record TEXT, created_at TEXT NOT NULL);
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def connect():
    path = Path(os.environ.get("PROFILE_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def _product(row, full=True):
    p = {"id": row["id"], **json.loads(row["data"]), "audited_at": row["audited_at"],
         "audit": json.loads(row["audit"]) if row["audit"] else None,
         "suggestions": json.loads(row["suggestions"] or "{}")}
    if full:
        p["record"] = json.loads(row["record"]) if row["record"] else None
    return p


def _profile(db, row, full=True):
    prods = db.execute("SELECT * FROM products WHERE profile_id = ? ORDER BY id", (row["id"],)).fetchall()
    return {**json.loads(row["data"]), "shared": bool(row["share_token"]), "share_token": row["share_token"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "products": [_product(p, full) for p in prods]}


def _row(db, token):
    if not token:
        return None
    return db.execute("SELECT * FROM profiles WHERE token_hash = ?", (token_hash(token),)).fetchone()


def create(data, products):
    """Returns (token, profile). The token is not stored and cannot be shown again."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    with connect() as db:
        pid = db.execute("INSERT INTO profiles (token_hash, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                         (token_hash(token), json.dumps(data), now, now)).lastrowid
        for p in products[:MAX_PRODUCTS]:
            db.execute("INSERT INTO products (profile_id, data, created_at) VALUES (?, ?, ?)", (pid, json.dumps(p), now))
        return token, _profile(db, db.execute("SELECT * FROM profiles WHERE id = ?", (pid,)).fetchone())


def get(token):
    with connect() as db:
        row = _row(db, token)
        return _profile(db, row) if row else None


def update(token, data):
    with connect() as db:
        row = _row(db, token)
        if not row:
            return None
        db.execute("UPDATE profiles SET data = ?, updated_at = ? WHERE id = ?", (json.dumps(data), utcnow(), row["id"]))
        return _profile(db, db.execute("SELECT * FROM profiles WHERE id = ?", (row["id"],)).fetchone())


def delete(token):
    """Deletes the profile, its products, audits and share link. Returns False for an unknown token."""
    with connect() as db:
        row = _row(db, token)
        if not row:
            return False
        db.execute("DELETE FROM products WHERE profile_id = ?", (row["id"],))
        db.execute("DELETE FROM profiles WHERE id = ?", (row["id"],))
        return True


def add_product(token, data):
    """Returns the new product, None for an unknown token, or raises ValueError at the product limit."""
    with connect() as db:
        row = _row(db, token)
        if not row:
            return None
        n = db.execute("SELECT COUNT(*) FROM products WHERE profile_id = ?", (row["id"],)).fetchone()[0]
        if n >= MAX_PRODUCTS:
            raise ValueError(f"at most {MAX_PRODUCTS} products per profile")
        pid = db.execute("INSERT INTO products (profile_id, data, created_at) VALUES (?, ?, ?)",
                         (row["id"], json.dumps(data), utcnow())).lastrowid
        return _product(db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone())


def product(token, product_id):
    with connect() as db:
        row = _row(db, token)
        p = row and db.execute("SELECT * FROM products WHERE id = ? AND profile_id = ?", (product_id, row["id"])).fetchone()
        return _product(p) if p else None


def remove_product(token, product_id):
    with connect() as db:
        row = _row(db, token)
        return bool(row) and db.execute("DELETE FROM products WHERE id = ? AND profile_id = ?",
                                        (product_id, row["id"])).rowcount == 1


def save_audit(token, product_id, audit, record):
    with connect() as db:
        row = _row(db, token)
        if not row:
            return None
        db.execute("UPDATE products SET audit = ?, record = ?, audited_at = ? WHERE id = ? AND profile_id = ?",
                   (json.dumps(audit), json.dumps(record), utcnow(), product_id, row["id"]))
        p = db.execute("SELECT * FROM products WHERE id = ? AND profile_id = ?", (product_id, row["id"])).fetchone()
        return _product(p) if p else None


def set_suggestion(token, product_id, field, decision):
    """Records the merchant's accept/dismiss decision for one suggested field. Nothing is published."""
    with connect() as db:
        row = _row(db, token)
        p = row and db.execute("SELECT * FROM products WHERE id = ? AND profile_id = ?", (product_id, row["id"])).fetchone()
        if not p:
            return None
        s = json.loads(p["suggestions"] or "{}")
        s[field] = {**decision, "decided_at": utcnow()}
        db.execute("UPDATE products SET suggestions = ? WHERE id = ?", (json.dumps(s), product_id))
        return _product(db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone())


def set_share(token, on):
    """Creates (or keeps) a random unlisted share token, or revokes it. Returns the token or None."""
    with connect() as db:
        row = _row(db, token)
        if not row:
            raise KeyError("unknown token")
        share = (row["share_token"] or secrets.token_urlsafe(24)) if on else None
        db.execute("UPDATE profiles SET share_token = ? WHERE id = ?", (share, row["id"]))
        return share


def shared(share_token):
    """The profile behind an active share link (products without their stored records), or None."""
    if not share_token:
        return None
    with connect() as db:
        row = db.execute("SELECT * FROM profiles WHERE share_token = ?", (share_token,)).fetchone()
        return _profile(db, row, full=False) if row else None


def ttl_cutoff():
    days = float(os.environ.get("AUDIT_RESULT_TTL_DAYS") or 90)
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")


def save_result(audit, record):
    """Keeps one audit under a random unlisted id (the stable report link) and purges expired ones. Returns the id."""
    rid = secrets.token_urlsafe(16)
    with connect() as db:
        db.execute("DELETE FROM results WHERE created_at < ?", (ttl_cutoff(),))
        db.execute("INSERT INTO results (id, audit, record, created_at) VALUES (?, ?, ?, ?)",
                   (rid, json.dumps(audit), json.dumps(record), utcnow()))
    return rid


def result(rid):
    with connect() as db:
        r = db.execute("SELECT * FROM results WHERE id = ? AND created_at >= ?", (rid, ttl_cutoff())).fetchone()
        return r and {"id": r["id"], "audit": json.loads(r["audit"]), "record": json.loads(r["record"]) if r["record"] else None,
                      "created_at": r["created_at"]}
