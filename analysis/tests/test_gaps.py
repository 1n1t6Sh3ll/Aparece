import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from analysis.gaps import analyze, main
from analysis.peers import find_peers


def rec(pid, price=20.0, lang="en", ptype="t_shirt", audience="men", gsm=None,
        schema=False, desc="Soft cotton tee.", fit="regular"):
    return {
        "product_id": pid,
        "source": {"language": lang},
        "identity": {"brand": "B", "product_type": ptype, "audience": audience},
        "content": {"full_description": desc, "bullet_points": []},
        "materials": {"primary_material": "cotton", "fabric_weight_gsm": gsm},
        "fit_and_style": {"fit": fit},
        "variants": {"colors": ["black"], "sizes": []},
        "commerce": {"price": price},
        "structured_data": {"product_schema_present": schema},
    }


TARGET = rec("t", desc="Tee.")
PEERS = [rec(f"p{i}", price=20 + i, gsm=180, schema=True, desc="x" * 200) for i in range(7)]
OTHERS = [
    rec("far_price", price=40), rec("es", lang="es"), rec("hoodie", ptype="hoodie"),
    rec("women", audience="women"), rec("slim", fit="slim", gsm=150),
    rec("slim2", fit="slim"), rec("slim3", fit="slim"),
]
ALL = [TARGET] + PEERS + OTHERS


class PeerTests(unittest.TestCase):
    def test_filters_and_order(self):
        ids = [r["product_id"] for _, r in find_peers(TARGET, ALL, k=10)]
        for bad in ("t", "far_price", "es", "hoodie", "women"):
            self.assertNotIn(bad, ids)
        self.assertEqual(ids[:7], [f"p{i}" for i in range(7)])  # fit match scores higher
        self.assertEqual(len(ids), 10)

    def test_unknown_price_and_audience_allowed(self):
        c = rec("c", price=None, audience=None)
        self.assertEqual([r["product_id"] for _, r in find_peers(TARGET, [c])], ["c"])

    def test_no_product_type(self):
        t = rec("x", ptype=None)
        self.assertEqual(find_peers(t, ALL), [])


class GapTests(unittest.TestCase):
    def setUp(self):
        self.out = analyze(TARGET, find_peers(TARGET, ALL, k=10))

    def test_missing_attribute_issue(self):
        i = next(x for x in self.out["issues"] if x["field"] == "materials.fabric_weight_gsm")
        self.assertEqual(i["type"], "OBSERVED_FACT")
        self.assertIn("present in 8/10 comparable products", i["statement"])
        self.assertEqual(i["evidence"]["count"], 8)
        self.assertIn("if known", i["suggested_action"])

    def test_metrics(self):
        m = self.out["metrics"]
        self.assertEqual(m["peer_count"], 10)
        self.assertEqual(m["language"], "en")
        self.assertEqual(m["attribute_peer_coverage"]["materials.fabric_weight_gsm"],
                         {"present": 8, "of": 10})
        self.assertLess(m["attribute_completeness_pct"]["target"],
                        m["attribute_completeness_pct"]["peer_median"])
        self.assertEqual(m["structured_data"]["product_schema_present"]["peers_present"], 7)

    def test_types_and_honesty(self):
        types = {x["type"] for x in self.out["issues"]}
        self.assertLessEqual(types, {"OBSERVED_FACT", "SUPPORTED_HYPOTHESIS", "UNKNOWN"})
        self.assertTrue(any(x["field"] == "ranking_effect" and x["type"] == "UNKNOWN"
                            for x in self.out["issues"]))
        self.assertNotIn("score", json.dumps(self.out["metrics"]).lower())
        for x in self.out["issues"]:
            self.assertNotIn("because", x["statement"].lower())

    def test_few_peers_unknown(self):
        out = analyze(TARGET, [])
        self.assertTrue(any(x["field"] == "peers" for x in out["issues"]))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r) for r in ALL))
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main(["--data", path, "--product-id", "t"]), 0)
            self.assertEqual(json.loads(buf.getvalue())["metrics"]["product_id"], "t")


if __name__ == "__main__":
    unittest.main()
