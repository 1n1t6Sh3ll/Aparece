"""SQLite store for experiments (TEAM-42). Experiments and results are append-only (triggers block edits).

EXPERIMENTS_DB: database path (default experiments/data/experiments.db).
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "experiments.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments(id),
  at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS experiments_no_update BEFORE UPDATE ON experiments BEGIN SELECT RAISE(ABORT, 'experiments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS experiments_no_delete BEFORE DELETE ON experiments BEGIN SELECT RAISE(ABORT, 'experiments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS results_no_update BEFORE UPDATE ON results BEGIN SELECT RAISE(ABORT, 'results are append-only'); END;
CREATE TRIGGER IF NOT EXISTS results_no_delete BEFORE DELETE ON results BEGIN SELECT RAISE(ABORT, 'results are append-only'); END;
"""


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def exp_id(n):
    return f"EXP-{n:06d}"


def parse_id(eid):
    """'EXP-000001' -> 1; None when malformed."""
    if isinstance(eid, str) and eid.startswith("EXP-") and eid[4:].isdigit():
        return int(eid[4:])
    return None


@contextmanager
def connect():
    """One transaction (commit on success, rollback on error); the connection is always closed."""
    path = Path(os.environ.get("EXPERIMENTS_DB") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()


def create(data):
    with connect() as db:
        n = db.execute("INSERT INTO experiments (created_at, data) VALUES (?, ?)", (utcnow(), json.dumps(data))).lastrowid
    return get(exp_id(n))


def get(eid):
    n = parse_id(eid)
    if n is None:
        return None
    with connect() as db:
        row = db.execute("SELECT * FROM experiments WHERE id = ?", (n,)).fetchone()
    if not row:
        return None
    return {"id": exp_id(row["id"]), "created_at": row["created_at"], **json.loads(row["data"])}


def add_result(eid, kind, data):
    with connect() as db:
        return db.execute("INSERT INTO results (experiment_id, at, kind, data) VALUES (?, ?, ?, ?)",
                          (parse_id(eid), utcnow(), kind, json.dumps(data))).lastrowid


def results(eid):
    with connect() as db:
        rows = db.execute("SELECT * FROM results WHERE experiment_id = ? ORDER BY id", (parse_id(eid),)).fetchall()
    return [{"result_id": r["id"], "at": r["at"], "kind": r["kind"], **json.loads(r["data"])} for r in rows]


def all_ids():
    with connect() as db:
        return [exp_id(r["id"]) for r in db.execute("SELECT id FROM experiments ORDER BY id")]
