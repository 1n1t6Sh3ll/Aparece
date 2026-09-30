"""TEAM-37: rules for fabric_type, texture, shirt_length, style, care, sizes, collar_type."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dataset" / "collect"))
sys.path.insert(0, str(ROOT / "dataset" / "build"))
from normalize import extra_fields, find_sizes  # noqa: E402
import fill_null_fields as fill  # noqa: E402


def run(text):
    return extra_fields([("raw_full_description", text)])


class RuleTest(unittest.TestCase):
    def test_english(self):
        v, evs = run("Soft cotton jersey crew neck tee. Vintage wash. Cropped fit. "
                     "Machine wash cold, do not bleach, tumble dry low. Sizes: XS, S, M, L, XL")
        self.assertEqual(v["materials.fabric_type"], "jersey")
        self.assertEqual(v["materials.texture"], "soft")
        self.assertEqual(v["fit_and_style.shirt_length"], "cropped")
        self.assertEqual(v["fit_and_style.style"], "vintage")
        self.assertEqual(v["fit_and_style.collar_type"], "crew")
        self.assertEqual(v["care"], ["machine_wash", "wash_cold", "tumble_dry", "do_not_bleach"])
        self.assertEqual(v["variants.sizes"], ["XS", "S", "M", "L", "XL"])

    def test_spanish(self):
        v, _ = run("Camiseta básica de punto liso con cuello en V. Lavar a máquina con agua fría. "
                   "No usar lejía. No planchar. Talla única")
        self.assertEqual(v["materials.fabric_type"], "jersey")
        self.assertEqual(v["fit_and_style.style"], "basic")
        self.assertEqual(v["fit_and_style.collar_type"], "v_neck")
        self.assertEqual(v["care"], ["machine_wash", "wash_cold", "do_not_bleach", "do_not_iron"])
        self.assertEqual(v["variants.sizes"], ["one_size"])

    def test_evidence_is_verbatim(self):
        text = "Brushed French Terry polo with a Button-Down collar. Do not tumble dry."
        v, evs = run(text)
        self.assertEqual(v["materials.fabric_type"], "french_terry")
        self.assertEqual(v["materials.texture"], "brushed")
        self.assertEqual(v["fit_and_style.collar_type"], "button_down")
        self.assertEqual(v["care"], ["do_not_tumble_dry"])
        for _, _, src, loc in evs:
            self.assertIn(src, text)
            self.assertEqual(loc, "raw_full_description")

    def test_nothing_stated_stays_empty(self):
        v, evs = run("Lord of the Rings logo t-shirt. Iron Man fans love it. Size matters.")
        self.assertEqual(v, {})
        self.assertEqual(evs, [])

    def test_sizes(self):
        self.assertEqual(find_sizes([("x", "Available S-XXL")])[0], ["S", "M", "L", "XL", "2XL"])
        self.assertEqual(find_sizes([("x", "Tallas: 38, 40, 42")])[0], ["38", "40", "42"])
        self.assertIsNone(find_sizes([("x", "M&M's print, L.A. skyline")]))


class ApplyTest(unittest.TestCase):
    def rec(self, text, gold=None):
        g = {f: None for f in fill.FIELDS}
        g.update(gold or {})
        return {"raw": {"source_url": "u", "raw_full_description": text}, "gold": g, "evidence": [],
                "messages": [{"role": "assistant", "content": "{}"}]}

    def test_fills_only_nulls_with_evidence(self):
        r = self.rec("Waffle&#x20;knit henley. Machine wash.", {"fit_and_style.collar_type": "keep"})
        filled = fill.apply(r)
        self.assertEqual(r["gold"]["materials.texture"], "waffle")
        self.assertEqual(r["gold"]["fit_and_style.collar_type"], "keep")
        self.assertNotIn("fit_and_style.collar_type", filled)
        self.assertEqual({e["field"] for e in r["evidence"]}, set(filled))
        self.assertIn('"materials.texture": "waffle"', r["messages"][-1]["content"])

    def test_stratified_is_deterministic(self):
        rows = [{"language": l, "source": s, "i": i} for i, (l, s) in
                enumerate([("en", "wdc")] * 60 + [("es", "wdc")] * 30 + [("en", "amazon")] * 10)]
        a, b = fill.stratified(rows, 10, 42), fill.stratified(rows, 10, 42)
        self.assertEqual([r["i"] for r in a], [r["i"] for r in b])
        self.assertEqual(sum(r["language"] == "es" for r in a), 3)


if __name__ == "__main__":
    unittest.main()
