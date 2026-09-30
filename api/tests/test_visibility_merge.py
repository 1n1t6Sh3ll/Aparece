import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard_api  # noqa: E402


def report(model, responses=2):
    return {"responses": responses, "models": {model: {"responses": responses, "any_catalog_mention_rate": 0.0,
            "sites": {"a.example": {"mention_rate": 0.0}, "b.example": {"mention_rate": 0.0}}}},
            "product_rows": [{"model": model}]}


class VisibilityMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith("PRODUCTLENS_VISIBILITY")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        for name, val in (("VISIBILITY_RUN", str(self.d / "a" / "report.json")),
                          ("VISIBILITY_MORE", str(self.d / "b" / "report.json"))):
            q = mock.patch.object(dashboard_api, name, val)
            q.start()
            self.addCleanup(q.stop)

    def write(self, sub, rep, brands):
        (self.d / sub).mkdir(exist_ok=True)
        (self.d / sub / "report.json").write_text(json.dumps(rep), encoding="utf-8")
        (self.d / sub / "brands.json").write_text(json.dumps(brands), encoding="utf-8")

    def test_only_base_run_still_works(self):
        self.write("a", report("m1"), {"answers": 2, "top_named": [{"name": "Uniqlo", "answers": 2}]})
        s = dashboard_api.visibility_summary()
        self.assertEqual((s["models"], s["responses"], s["shops"]), (["m1"], 2, 2))
        self.assertEqual(s["top_named"], [{"name": "Uniqlo", "answers": 2}])

    def test_extra_models_and_brands_are_merged(self):
        self.write("a", report("m1"), {"answers": 2, "top_named": [{"name": "Uniqlo", "answers": 1}, {"name": "Nike", "answers": 2}]})
        self.write("b", report("m2", 3), {"answers": 3, "top_named": [{"name": "Uniqlo", "answers": 3}]})
        s = dashboard_api.visibility_summary()
        self.assertEqual(s["models"], ["m1", "m2"])
        self.assertEqual(s["responses"], 5)
        self.assertEqual(s["top_named"], [{"name": "Uniqlo", "answers": 4}, {"name": "Nike", "answers": 2}])
        self.assertEqual(len(dashboard_api.visibility()["product_rows"]), 2)

    def test_pinned_run_is_not_merged(self):
        self.write("a", report("m1"), {})
        self.write("b", report("m2"), {})
        with mock.patch.dict(os.environ, {"PRODUCTLENS_VISIBILITY_RUN": str(self.d / "a" / "report.json")}):
            self.assertEqual(dashboard_api.visibility_summary()["models"], ["m1"])


class CommittedRunTest(unittest.TestCase):
    def test_committed_reports_are_valid_json_with_same_shops(self):
        root = Path(__file__).resolve().parents[2] / "benchmark" / "results"
        shops = []
        for d in ("visibility-2026-09-30", "visibility-2026-09-30-more"):
            rep = json.loads((root / d / "report.json").read_text(encoding="utf-8"))
            for m in rep["models"].values():
                shops.append(sorted(m["sites"]))
        self.assertTrue(all(s == shops[0] for s in shops))


if __name__ == "__main__":
    unittest.main()
