"""Hand-made cases for train/reward.py (CPU only, no model).

Run from the repo root: python -m unittest discover -s train/tests -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

TRAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRAIN))

from common import FIELDS, prompt_text, target  # noqa: E402
from reward import FORMAT_FAIL, HALLUCINATION, copy_reward, reward, score_file  # noqa: E402

EN = prompt_text({"raw_title": "Men's Slim Fit Crew Neck T-Shirt - White",
                  "raw_full_description": "Short sleeves. Composition: 100% cotton, 180 gsm jersey.\nSlightly stretchy.",
                  "raw_size_text": "S, M, L", "raw_care_text": "Machine wash cold"})
ES = prompt_text({"raw_title": "Camiseta de manga corta para mujer",
                  "raw_full_description": "Corte regular, cuello redondo. 100% algodón orgánico, 160 gramos. Color: azul marino.",
                  "raw_size_text": "S M L"})


def pred(**kw):
    out = {f: None for f in FIELDS}
    out.update({k.replace("__", "."): v for k, v in kw.items()})
    return out


GOLD_EN = pred(identity__product_type="t_shirt", identity__audience="men", materials__primary_material="cotton",
               materials__material_percentages={"cotton": 100}, materials__fabric_weight_gsm=180,
               fit_and_style__fit="slim", fit_and_style__neckline="crew", fit_and_style__sleeve_length="short",
               variants__colors=["white"], variants__sizes=["S", "M", "L"], care=["Machine wash cold"])


class Reward(unittest.TestCase):
    def test_supported_values(self):
        r = reward(json.dumps(GOLD_EN), EN, GOLD_EN)
        self.assertTrue(r["format_ok"])
        self.assertEqual(r["hallucinated"], [])
        self.assertEqual(r["total"], 1 + 11)  # format + 11 non-null exact matches
        r = reward(GOLD_EN | {"materials.stretch": True}, EN)  # no gold: format only, stretch is in the text
        self.assertEqual((r["total"], r["hallucinated"]), (1, []))

    def test_hallucinated_material_percentage(self):
        p = GOLD_EN | {"materials.material_percentages": {"cotton": 60, "polyester": 40}}
        r = reward(p, EN, GOLD_EN)
        self.assertEqual(r["hallucinated"], ["materials.material_percentages"])
        self.assertEqual(r["fields"]["materials.material_percentages"]["unsupported"], ["cotton: 60", "polyester: 40"])
        self.assertEqual(r["total"], 1 + 10 - 2)  # one match lost, one hallucination

    def test_invalid_output(self):
        for bad in ("not json", "[1, 2]", pred(fit_and_style__fit="skinny"),
                    pred(materials__material_percentages={"cotton": 150}), pred(materials__fabric_weight_gsm="180")):
            r = reward(bad, EN, GOLD_EN)
            self.assertEqual((r["total"], r["format_ok"]), (FORMAT_FAIL, False), bad)
            self.assertEqual(r["fields"], {})
        self.assertTrue(reward("```json\n" + json.dumps(GOLD_EN) + "\n```", EN)["format_ok"])

    def test_null_handling(self):
        gold = GOLD_EN | {"fit_and_style.fit": None}
        self.assertEqual(reward(pred(), EN, gold)["total"], 1)  # all null: no reward, no penalty
        self.assertEqual(reward(pred(fit_and_style__fit="unknown"), EN, gold)["total"], 1)  # unknown = null
        self.assertEqual(reward({}, EN, gold)["errors"][0], "missing key " + FIELDS[0])  # missing = null
        # gold null, value supported by text: neutral (gold may be incomplete)
        self.assertEqual(reward(pred(fit_and_style__fit="slim"), EN, gold)["total"], 1)
        # gold null, value unsupported: hallucination -2 and unsupported extra -0.5
        r = reward(pred(fit_and_style__fit="oversized"), EN, gold)
        self.assertEqual((r["total"], r["hallucinated"]), (1 - 2.5, ["fit_and_style.fit"]))
        # list with one invented item
        r = reward(pred(variants__sizes=["S", "XXL"], care=["Tumble dry"]), EN)
        self.assertEqual(r["fields"]["variants.sizes"]["unsupported"], ["XXL"])
        self.assertEqual(r["hallucinated"], ["variants.sizes", "care"])

    def test_spanish(self):
        p = pred(identity__product_type="t_shirt", identity__audience="women", materials__primary_material="organic_cotton",
                 materials__material_percentages={"organic_cotton": 100}, materials__fabric_weight_gsm=160,
                 fit_and_style__fit="regular", fit_and_style__neckline="crew", fit_and_style__sleeve_length="short",
                 variants__colors=["navy"], variants__sizes=["S", "M", "L"])
        self.assertEqual(reward(p, ES)["hallucinated"], [])
        r = reward(p | {"fit_and_style.fit": "slim", "materials.material_percentages": {"polyester": 100}}, ES)
        self.assertEqual(r["hallucinated"], ["materials.material_percentages", "fit_and_style.fit"])

    def test_example_gold_is_grounded(self):
        ex = TRAIN.parent / "dataset" / "examples"
        raw = json.loads((ex / "raw_record.example.json").read_text(encoding="utf-8"))
        gold = target(json.loads((ex / "normalized_record.example.json").read_text(encoding="utf-8")))
        r = reward(json.dumps(gold), prompt_text(raw), gold)
        self.assertEqual(r["hallucinated"], [])
        self.assertEqual(r["total"], 1 + sum(v is not None for v in gold.values()))


class ScoreFile(unittest.TestCase):
    def test_api_responses(self):
        data = [{"product_id": "p_1", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": EN},
                                                  {"role": "assistant", "content": json.dumps(GOLD_EN)}]},
                {"product_id": "p_2", "messages": [{"role": "user", "content": ES},
                                                  {"role": "assistant", "content": json.dumps(pred())}]}]
        preds = [{"product_id": "p_1", "model": "m", "text": json.dumps(GOLD_EN | {"fit_and_style.fit": "relaxed"})}]
        with tempfile.TemporaryDirectory() as d:
            dp, pp = Path(d) / "data.jsonl", Path(d) / "pred.jsonl"
            dp.write_text("".join(json.dumps(x) + "\n" for x in data), encoding="utf-8")
            pp.write_text("".join(json.dumps(x) + "\n" for x in preds), encoding="utf-8")
            summary, rows = score_file(pp, dp)
        self.assertEqual(summary["n"], 2)
        self.assertEqual(summary["missing_predictions"], 1)
        self.assertEqual(summary["format_ok"], 0.5)
        self.assertEqual(summary["hallucinated_by_field"], {"fit_and_style.fit": 1})
        self.assertEqual(rows[0]["total"], 1 + 10 - 2)
        self.assertEqual(rows[1]["total"], FORMAT_FAIL)



class CopyRewardTest(unittest.TestCase):
    def test_terms(self):
        ok = {"sentence": "Regular fit.", "problems": []}
        bad = {"sentence": "Waterproof.", "problems": ["words not grounded"]}
        t = {"fit_and_style.fit", "materials.fabric_weight_gsm"}
        r = copy_reward({"title": "Tee", "description": "Regular fit."}, [ok], ["fit_and_style.fit"], t)
        self.assertEqual((r["total"], r["coverage"], r["missing"]), (3.0, 1.0, ["materials.fabric_weight_gsm"]))
        h = copy_reward({"title": "Tee", "description": "Regular fit. Waterproof."}, [ok, bad], ["fit_and_style.fit"], t)
        self.assertEqual((h["hallucination"], h["hallucinated"]), (HALLUCINATION, ["Waterproof."]))
        self.assertLess(h["total"], r["total"])
        self.assertEqual(copy_reward({"title": "x" * 91, "description": "a"}, [], [], t)["total"], FORMAT_FAIL)
        self.assertEqual(copy_reward({"title": "", "description": "a"}, [], [], t)["format_ok"], False)


if __name__ == "__main__":
    unittest.main()
