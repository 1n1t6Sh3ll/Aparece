"""TEAM-50: dead catalog products leave the AI-visibility catalog; broken citation rate per model."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmark import citations
from benchmark.match import load_catalog

CATALOG = str(Path(__file__).resolve().parents[1] / "examples" / "catalog.example.jsonl")
DEAD = "https://northwindtees.com/products/classic-organic-tee"


def ans(model, text, provider="mock"):
    return {"provider": provider, "model": model, "response_text": text}


class LinkCitationTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = Path(self.d.name) / "link_status.jsonl"
        self.env = mock.patch.dict(os.environ, {"PRODUCTLENS_LINK_STATUS": str(self.path)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.d.cleanup()

    def test_catalog_drops_dead_products_only_when_status_known(self):
        full = load_catalog(CATALOG)
        self.assertIn("p_nw_classic_com", [p["product_id"] for p in full])
        self.path.write_text(json.dumps({"url": DEAD, "status": "gone"}) + "\n")
        ids = [p["product_id"] for p in load_catalog(CATALOG)]
        self.assertNotIn("p_nw_classic_com", ids)
        self.assertEqual(len(ids), len(full) - 1)
        self.assertEqual(len(load_catalog(CATALOG, drop_dead=False)), len(full))

    def test_broken_citation_rate_per_model(self):
        st = {"a.example.com/p/1": {"status": "live"}, "a.example.com/p/2": {"status": "gone"},
              "a.example.com/p/3": {"status": "redirected_away"}, "a.example.com/p/4": {"status": "blocked"}}
        recs = [ans("m1", "See https://a.example.com/p/1 and https://a.example.com/p/2."),
                ans("m1", "Try https://www.a.example.com/p/3/ or https://a.example.com/p/4"),
                ans("m2", "Buy https://a.example.com/p/1, https://new.example.com/x"),
                ans("m3", "No links here.")]
        rep = citations.citation_report(recs, st)
        m1, m2, m3 = rep["m1"], rep["m2"], rep["m3"]
        self.assertEqual((m1["citations"], m1["live"], m1["broken"], m1["unverified"]), (4, 1, 2, 1))
        self.assertAlmostEqual(m1["broken_citation_rate"], 2 / 3, places=4)
        self.assertEqual(m1["broken_urls"], ["https://a.example.com/p/2", "https://www.a.example.com/p/3/"])
        self.assertEqual((m2["broken_citation_rate"], m2["unchecked"]), (0.0, 1))
        self.assertIsNone(m3["broken_citation_rate"])
        self.assertIn("| m1 | 2 | 4 | 1 | 2 | 1 | 0 | 0.67 |", citations.citations_markdown(rep))

    def test_check_flag_checks_only_cited_urls(self):
        res = Path(self.d.name) / "runs.jsonl"
        res.write_text(json.dumps(ans("m1", "https://a.example.com/p/9 https://a.example.com/p/9")) + "\n")
        seen = []

        def fake_run(items, out, workers):
            seen.extend(items)
            Path(out).write_text(json.dumps({"url": items[0][0], "status": "gone"}) + "\n")

        with mock.patch("tools.linkcheck.check.run", fake_run):
            rep = citations.main(["--results", str(res), "--status", str(self.path), "--check"])
        self.assertEqual(seen, [("https://a.example.com/p/9", None)])
        self.assertEqual(rep["m1"]["broken_citation_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
