import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from monitor import seed_demo, store  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


class SeedDemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "demo.db")
        p = mock.patch.dict(os.environ, {"MONITOR_DB": self.db})
        p.start()
        self.addCleanup(p.stop)

    def seed(self):
        return seed_demo.seed(str(FIX / "dashboard_groundtruth.jsonl"))

    def test_seed_is_idempotent_one_snapshot_no_events(self):
        first = self.seed()
        self.assertEqual(len(first), 3)  # fixture has 3 en/wdc rows; other buckets are empty
        self.assertEqual(self.seed(), [])  # re-run adds nothing
        rows = store.monitored()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual((r["snapshot_count"], r["event_count"]), (1, 0))
            snap = store.last_snapshot(r["id"])["data"]
            self.assertEqual(snap["source"], "dataset")
            self.assertTrue(snap["crawled_at"])
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
