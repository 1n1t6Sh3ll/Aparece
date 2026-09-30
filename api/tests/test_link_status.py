"""TEAM-50: dead peer links leave the listing-quality rank (N counts only live comparable listings), the peer list
and competitors; unverified links stay flagged. No link status file = unchanged behaviour."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_audit import ENV, HTML, URL, client

STATUS = {"https://tees.example.org/p/p_slim": "gone", "https://tees.example.org/p/p_linen": "blocked"}


class LinkStatusTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = Path(self.d.name) / "link_status.jsonl"
        self.env = mock.patch.dict(os.environ, {**ENV, "PRODUCTLENS_LINK_STATUS": str(self.path)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.d.cleanup()

    def audit(self):
        r = client.post("/v1/audit", json={"html": HTML, "url": URL})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_without_status_file_rank_unchanged(self):
        b = self.audit()
        self.assertEqual((b["rank"]["position"], b["rank"]["total"]), (4, 5))
        self.assertTrue(all(p["link_status"] is None and not p["link_unverified"] for p in b["peers"]))

    def test_gone_peer_leaves_rank_and_peers_blocked_is_flagged(self):
        self.path.write_text("".join(json.dumps({"url": u, "status": s}) + "\n" for u, s in STATUS.items()))
        b = self.audit()
        self.assertEqual(b["rank"]["total"], 4)  # 3 live comparable listings + you
        ids = [x["product_id"] for x in b["leaderboard"]]
        self.assertNotIn("p_slim", ids)
        self.assertNotIn("p_slim", [p["product_id"] for p in b["peers"]])
        linen = next(x for x in b["leaderboard"] if x["product_id"] == "p_linen")
        self.assertTrue(linen["link_unverified"])
        self.assertEqual(next(p for p in b["peers"] if p["product_id"] == "p_linen")["link_status"], "blocked")
        comp = client.get("/v1/products/p_target/competitors").json()["peers"]
        self.assertNotIn("p_slim", [p["product_id"] for p in comp])
        self.assertTrue(next(p for p in comp if p["product_id"] == "p_linen")["link_unverified"])


if __name__ == "__main__":
    unittest.main()
