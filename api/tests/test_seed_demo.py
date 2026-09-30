import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from monitor import seed_demo, store  # noqa: E402  (sets import paths)
import safe_fetch  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
PAGE = (Path(__file__).resolve().parents[2] / "monitor" / "fixtures" / "tee_v1.html").read_text(encoding="utf-8")
FAIL = "comme-des-gar-ons"  # the 2nd fixture row's URL contains this; its fetch fails


def fake_fetch(url):
    if FAIL in url.lower():
        raise safe_fetch.FetchError(403, "robots.txt disallows this URL")
    return url, PAGE


class SeedDemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "demo.db")
        for p in (mock.patch.dict(os.environ, {"MONITOR_DB": self.db, "MONITOR_DELAY": "0",
                                               "PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl")}),
                  mock.patch.object(safe_fetch, "fetch_page", side_effect=fake_fetch)):
            p.start()
            self.addCleanup(p.stop)

    def seed(self):
        return seed_demo.seed(str(FIX / "dashboard_groundtruth.jsonl"), log=lambda *a: None)

    def test_live_crawl_snapshot_skip_failures_idempotent(self):
        first = self.seed()
        self.assertEqual(len(first), 2)  # 3 en/wdc rows, one fetch fails and is skipped
        self.assertEqual(safe_fetch.fetch_page.call_count, 3)
        self.assertEqual(self.seed(), [])  # re-run adds nothing and fetches nothing
        self.assertEqual(safe_fetch.fetch_page.call_count, 3)
        rows = store.monitored()
        self.assertEqual(len(rows), 2)
        self.assertFalse(any(FAIL in r["url"].lower() for r in rows))
        for r in rows:
            self.assertEqual((r["snapshot_count"], r["event_count"]), (1, 0))
            snap = store.last_snapshot(r["id"])["data"]
            self.assertEqual(snap["content"]["title"], "Everyday Tee")  # from the crawled page, not the dataset
        db = sqlite3.connect(self.db)
        self.assertEqual(db.execute("SELECT email, demo, name FROM merchants").fetchall(),
                         [("demo-a@example.com", 1, "Demo Merchant A")])
        db.close()

    def test_reset_only_deletes_demo_db(self):
        self.seed()
        with self.assertRaises(SystemExit):
            seed_demo.reset(os.path.join(self.tmp.name, "monitor.db"))
        self.assertTrue(seed_demo.reset(self.db))
        self.assertFalse(os.path.exists(self.db))

    def test_reset_refuses_db_with_real_merchants(self):
        store.enroll("https://shop.example.com/p/1", "shop@example.com", "free")
        self.seed()
        with self.assertRaises(SystemExit):
            seed_demo.reset(self.db)
        self.assertTrue(os.path.exists(self.db))

    def test_main_refuses_non_demo_path(self):
        with self.assertRaises(SystemExit):
            seed_demo.main(["--data", str(FIX / "dashboard_groundtruth.jsonl"), "--db", os.path.join(self.tmp.name, "m.db")])


if __name__ == "__main__":
    unittest.main()
