import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "model_comparison.sample.json"
client = TestClient(main.app)


class ModelComparisonTest(unittest.TestCase):
    def get(self, path):
        with mock.patch.dict(os.environ, {"PRODUCTLENS_COMPARISON": str(path)}):
            r = client.get("/v1/model-comparison")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_sample_file(self):
        b = self.get(FIX)
        self.assertTrue(b["available"])
        self.assertTrue(b["sample"])
        self.assertEqual(list(b["models"]), ["all_null_baseline", "ft_qwen_0_5b", "gpt-4o-mini"])
        self.assertEqual(b["models"]["ft_qwen_0_5b"]["label"], "Fine-tuned Qwen 0.5B")
        self.assertEqual(b["models"]["gpt-4o-mini"]["non_null_acc"], 0.7)  # passed through, not recomputed
        self.assertEqual(len(b["new_fields"]), 7)
        self.assertEqual(b["models"]["gpt-4o-mini"]["settings"], {"temperature": 0})  # passed through for the UI
        self.assertEqual(b["test"]["note"], "sample")

    def test_missing_and_bad_file(self):
        b = self.get(FIX.parent / "nope.json")
        self.assertEqual((b["available"], b["models"]), (False, {}))
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "c.json"
            bad.write_text("{not json", encoding="utf-8")
            self.assertFalse(self.get(bad)["available"])

    def test_raw_eval_output_shape(self):
        raw = {"all_null_baseline": {"non_null_acc": 0.0, "null_acc": 1.0, "json_valid": 1.0},
               "finetuned": {"non_null_acc": 0.5, "null_acc": 0.9, "json_valid": 0.95, "time_s": 12.0}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            b = self.get(p)
        self.assertTrue(b["available"])
        self.assertFalse(b["sample"])
        self.assertEqual(b["models"]["finetuned"]["label"], "Fine-tuned Qwen")


if __name__ == "__main__":
    unittest.main()
