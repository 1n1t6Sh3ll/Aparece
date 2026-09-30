"""Seed a separate demo monitoring DB with fictional merchants and real dataset products (TEAM-29).

    python -m monitor.seed_demo --data dataset/output/final/train.jsonl [--signals signals.jsonl] [--db PATH]
    python -m monitor.seed_demo --reset [--db PATH]

Writes to monitor/data/demo.db by default (never the real MONITOR_DB). Each product gets ONE snapshot
built from its dataset record (source "dataset" + the dataset crawl date). No change events are
created; history grows only from real re-crawls. Re-running adds nothing new. --reset deletes the demo
DB file, and only a file named demo.db whose merchants are all demo merchants.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "api"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from monitor import changes, store  # noqa: E402

DEMO_DB = Path(__file__).resolve().parent / "data" / "demo.db"
PER_MERCHANT = 4
# (name, email, bucket): fictional merchants; buckets give variety in language and source.
MERCHANTS = [("Demo Merchant A", "demo-a@example.com", ("en", "wdc")),
             ("Demo Merchant B", "demo-b@example.com", ("en", "amazon")),
             ("Demo Merchant C", "demo-c@example.com", ("es", "wdc")),
             ("Demo Merchant D", "demo-d@example.com", ("other", "wdc"))]
CANDIDATES = 200  # per bucket, read in file order (deterministic)


def is_demo_path(path):
    return Path(path).name == DEMO_DB.name and Path(path).resolve() != store.DEFAULT_DB.resolve()


def load_signals(path):
    out = {}
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = json.loads(line) if line.strip() else None
                if s and s.get("currency_source") == "record" and isinstance(s.get("price"), (int, float)):
                    out[s["product_id"]] = (s["price"], s.get("currency"))
    return out


def pick(data_path, prices):
    """Per bucket: up to PER_MERCHANT records spread across the price range (low to high)."""
    import dashboard_api  # api/: the same ground-truth/normalized adapter the dashboard uses
    buckets = {b: [] for _, _, b in MERCHANTS}
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rec = dashboard_api.adapt(row)
            if not rec or not rec["source"].get("url") or not rec["identity"].get("product_name"):
                continue
            src = rec.get("dataset_source") or ("amazon" if rec["source"].get("merchant_domain") == "amazon.com" else "wdc")
            b = (rec["source"].get("language"), "amazon" if src == "amazon" else "wdc")
            if b in buckets and len(buckets[b]) < CANDIDATES:
                if rec["product_id"] in prices and not dashboard_api.price(rec):
                    rec["commerce"]["price"], rec["commerce"]["currency"] = prices[rec["product_id"]]
                buckets[b].append(rec)
            if all(len(v) >= CANDIDATES for v in buckets.values()):
                break
    out = {}
    for b, recs in buckets.items():
        recs.sort(key=lambda r: (r["commerce"].get("price") is None, r["commerce"].get("price") or 0, r["product_id"]))
        priced = [r for r in recs if r["commerce"].get("price")] or recs
        n = len(priced)
        idx = sorted({round(i * (n - 1) / max(PER_MERCHANT - 1, 1)) for i in range(PER_MERCHANT)}) if n else []
        out[b] = [priced[i] for i in idx]
    return out


def seed(data_path, signals_path=None):
    plans = store.PLANS
    picked = pick(data_path, load_signals(signals_path))
    summary = []
    for i, (name, email, bucket) in enumerate(MERCHANTS):
        plan = plans[i % len(plans)]
        with store.connect() as db:
            seeded = db.execute("SELECT COUNT(*) FROM products p JOIN merchants m ON m.id = p.merchant_id "
                                "WHERE m.email = ?", (email,)).fetchone()[0]
        if seeded:  # already seeded (maybe from other inputs): never add more
            continue
        for rec in picked[bucket]:
            p, _ = store.enroll(rec["source"]["url"], email, plan)
            if store.last_snapshot(p["id"]) is None:
                store.add_snapshot(p["id"], {
                    "content": changes.content(rec, "", None), "product_id": rec["product_id"],
                    "quality_status": rec.get("quality_status"), "gaps": None,
                    "source": "dataset", "crawled_at": rec["source"].get("scraped_at"), "demo": True}, [])
            summary.append((name, p["id"], rec["product_id"]))
        with store.connect() as db:
            if "demo" not in {c["name"] for c in db.execute("PRAGMA table_info(merchants)")}:
                db.execute("ALTER TABLE merchants ADD COLUMN demo INTEGER NOT NULL DEFAULT 0")
                db.execute("ALTER TABLE merchants ADD COLUMN name TEXT")
            db.execute("UPDATE merchants SET demo = 1, name = ? WHERE email = ?", (name, email))
    return summary


def reset(path):
    path = Path(path)
    if not is_demo_path(path):
        sys.exit(f"refusing: {path} is not a demo DB (must be named {DEMO_DB.name})")
    if not path.exists():
        return False
    db = sqlite3.connect(path)
    try:
        cols = {c[1] for c in db.execute("PRAGMA table_info(merchants)")}
        non_demo = db.execute("SELECT COUNT(*) FROM merchants WHERE demo = 0").fetchone()[0] if "demo" in cols else None
    finally:
        db.close()
    if non_demo != 0:
        sys.exit(f"refusing: {path} contains non-demo merchants")
    path.unlink()
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="monitor.seed_demo")
    ap.add_argument("--data")
    ap.add_argument("--signals", default=os.environ.get("PRODUCTLENS_SIGNALS"))
    ap.add_argument("--db", default=str(DEMO_DB))
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args(argv)
    if not is_demo_path(a.db):
        sys.exit(f"refusing: demo data goes only into a file named {DEMO_DB.name}")
    if a.reset:
        print("deleted" if reset(a.db) else "nothing to delete", a.db)
        return
    if not a.data:
        ap.error("--data is required unless --reset")
    os.environ["MONITOR_DB"] = a.db
    for name, pid, record in seed(a.data, a.signals):
        print(f"{name}: monitored #{pid} <- {record}")
    print(f"demo DB: {a.db}  (run the API with MONITOR_DB={a.db})")


if __name__ == "__main__":
    main()
