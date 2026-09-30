import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import visibility_live_api as vl  # noqa: E402

os.environ["VISIBILITY_LIVE_RATE_LIMIT"] = "1000"  # the tests post many times from one client
client = TestClient(main.app)
REC = {"identity": {"brand": "Merch Monger", "product_name": "Green Line Short Sleeve Unisex T-Shirt", "product_type": "t_shirt"},
       "source": {"url": "https://merchmonger.com/products/green-line-tee", "merchant_domain": "merchmonger.com"}}
KEYS = {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "y"}


class Fake:
    """No network: answers from a script keyed by call number; reports token usage so the Budget charges."""
    def __init__(self, answers, calls, in_tok=100, out_tok=200):
        self.answers, self.calls, self.tok = answers, calls, (in_tok, out_tok)

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        text = self.answers[len(self.calls) % len(self.answers)]
        self.calls.append(prompt)
        return {"text": text, "input_tokens": self.tok[0], "output_tokens": self.tok[1]}


NAMED = "1. Uniqlo - reliable basics\n2. **Merch Monger** Green Line Tee - soft cotton\n3. Gap - classic"
NOT = "1. Uniqlo - reliable basics\n2. Gap - classic\n3. Everlane - premium"
CITED = "Try this: https://merchmonger.com/products/green-line-tee for a soft tee."


def run(answers, calls=None, env=None, **kw):
    calls = [] if calls is None else calls
    with mock.patch.dict(os.environ, {**KEYS, **(env or {})}):
        return vl.check(REC, kw.pop("lang", "en"), factory=lambda p, m: Fake(answers, calls, **kw)), calls


class VisibilityLiveTest(unittest.TestCase):
    def setUp(self):
        vl._cache.clear()
        vl._day.update(date=None, spent=0.0)

    def test_no_key_never_fakes(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            r = client.post("/v1/visibility/live", json={"product": REC, "language": "en"})
        self.assertEqual(r.json(), {"available": False, "reason": "no_api_key"})

    def test_bad_product(self):
        self.assertEqual(client.post("/v1/visibility/live", json={"product": {}}).status_code, 422)

    def test_questions_deterministic_and_typed(self):
        a = vl.questions(REC, "en")
        self.assertEqual(a, vl.questions(REC, "en"))
        self.assertEqual(len(a), 6)
        polo = vl.questions({"identity": {"product_name": "Piqué Polo Shirt"}}, "en")
        self.assertTrue(any("polo" in q["text"].lower() for q in polo[:2]))
        self.assertTrue(all(q["language"] == "es" for q in vl.questions(REC, "es")))
        self.assertTrue(all(q["split"] != "hidden" for q in a))

    def test_brand_parsing_skips_advice(self):
        self.assertEqual(vl._brand("**Everlane - The Cotton Crew** - soft"), "Everlane")
        self.assertEqual(vl._brand("Uniqlo Airism Cotton T-Shirt: nice"), "Uniqlo Airism Cotton T-Shirt")
        self.assertEqual(vl._brand("Wash in cold water"), "")
        self.assertEqual(vl._brand("**Use gentle detergent**: x"), "")

    def test_pound_sign_repaired(self):
        self.assertTrue(all("�" not in q["text"] and "Â" not in q["text"] for q in vl.questions(REC, "en")))
        self.assertEqual(vl._fix("around �25"), "around £25")

    def test_malformed_product_is_422_not_500(self):
        bad = [{"identity": {"brand": 5}}, {"identity": {"brand": "A"}, "source": "x"},
               {"identity": {"brand": "A"}, "source": {"url": 5}}, {"identity": {"brand": "A"}, "source": {"merchant_domain": ["a"]}},
               {"identity": {"product_name": ["x"]}}, {"identity": []}, {"identity": {"brand": "A"}, "source": []},
               {"identity": {"brand": "A" * 301}}, {"identity": {"brand": "A"}, "source": {"url": "https://x.com/" + "a" * 300}}]
        with mock.patch.dict(os.environ, KEYS):
            for b in bad:
                self.assertEqual(client.post("/v1/visibility/live", json={"product": b}).status_code, 422, b)

    def test_cache_key_includes_brand_and_name(self):
        run([NAMED])
        other = {"identity": {"brand": "Fake Brand", "product_name": "Other Tee", "product_type": "t_shirt"}, "source": REC["source"]}
        calls = []
        with mock.patch.dict(os.environ, KEYS):
            r = vl.check(other, "en", factory=lambda p, m: Fake([NOT], calls))
        self.assertEqual(len(calls), 12)  # not served from the first product's entry
        self.assertEqual(r["models"]["openai:gpt-4o-mini"]["mentioned"], 0)
        _, calls = run([NOT])
        self.assertEqual(calls, [])  # the original still hits its own entry

    def test_cache_is_bounded(self):
        with mock.patch.object(vl, "MAX_CACHE", 2):
            for i in range(3):
                rec = {"identity": {"brand": f"Brand{i}"}, "source": REC["source"]}
                with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": ""}):
                    vl.check(rec, "en", factory=lambda p, m: Fake([NOT], []))
        self.assertLessEqual(len(vl._cache), 2)

    def test_named_with_position_and_brands_instead(self):
        r, calls = run([NAMED, NOT])
        self.assertTrue(r["available"])
        self.assertEqual(len(calls), 12)
        m = r["models"]["openai:gpt-4o-mini"]
        self.assertEqual((m["asked"], m["mentioned"], m["mention_rate"], m["best_position"], m["top3"]), (6, 3, 0.5, 2, 3))
        names = {b["brand"]: b["count"] for b in m["brands_named_instead"]}
        self.assertEqual(names["Uniqlo"], 6)
        self.assertNotIn("Merch Monger", names)
        self.assertFalse(m["partial"])
        self.assertEqual(len(r["questions_used"]), 6)
        self.assertIn("small sample", r["caveats"][0])
        self.assertGreater(r["cost_usd"], 0)

    def test_not_named(self):
        r, _ = run([NOT])
        m = r["models"]["anthropic:claude-haiku-4-5-20251001"]
        self.assertEqual((m["mentioned"], m["mention_rate"], m["best_position"], m["cited"]), (0, 0.0, None, 0))

    def test_cited_url_counts(self):
        r, _ = run([CITED])
        m = r["models"]["openai:gpt-4o-mini"]
        self.assertEqual((m["mentioned"], m["cited"], m["best_position"]), (6, 6, None))

    def test_analyze_domain_only_and_other_page_of_site(self):
        t = vl._target(REC)
        self.assertTrue(vl.analyze("See merchmonger.com for tees", t)["mentioned"])
        self.assertTrue(vl.analyze("Shop at https://merchmonger.com/collections/all", t)["cited"])
        self.assertFalse(vl.analyze("Try Merch Monsters tees", t)["mentioned"])

    def test_cap_enforced_partial(self):
        r, calls = run([NAMED], env={"VISIBILITY_LIVE_MAX_USD": "0.0005"})
        self.assertLess(len(calls), 12)
        self.assertLessEqual(r["cost_usd"], 0.0005)
        parts = [m for m in r["models"].values() if m["partial"]]
        self.assertTrue(parts or not r["available"])
        if r["available"]:
            self.assertIn("Partial results", " ".join(r["caveats"]))
            self.assertLess(min(m["asked"] for m in r["models"].values()), 6)

    def test_daily_cap_blocks_and_refunds(self):
        r, calls = run([NAMED], env={"VISIBILITY_LIVE_DAILY_USD": "0"})
        self.assertEqual((r["available"], r["reason"], calls), (False, "spend_cap", []))
        vl._day.update(date=None, spent=0.0)
        r, _ = run([NAMED])
        self.assertAlmostEqual(vl._day["spent"], r["cost_usd"], places=6)  # only real spend stays reserved

    def test_cache_hit_no_new_calls(self):
        run([NAMED])
        r, calls = run([NOT])
        self.assertEqual(calls, [])
        self.assertEqual(r["cost_usd"], 0)
        self.assertEqual(r["models"]["openai:gpt-4o-mini"]["mentioned"], 6)  # the cached NAMED run, not the NOT one
        self.assertIn("Reused", " ".join(r["caveats"]))

    def test_cache_expires_and_keys_on_language(self):
        run([NAMED])
        _, calls = run([NAMED], lang="es")
        self.assertEqual(len(calls), 12)
        with mock.patch.dict(os.environ, KEYS):
            vl.check(REC, "en", factory=lambda p, m: Fake([NOT], calls), now=lambda: 10 ** 12)
        self.assertEqual(len(calls), 24)

    def test_only_keyed_model_runs_and_error_is_partial(self):
        class Boom(Fake):
            def complete(self, *a, **k):
                if len(self.calls) >= 2:
                    raise RuntimeError("boom")
                return super().complete(*a, **k)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": ""}):
            r = vl.check(REC, "en", factory=lambda p, m: Boom([NAMED], []))
        self.assertEqual(list(r["models"]), ["openai:gpt-4o-mini"])
        m = r["models"]["openai:gpt-4o-mini"]
        self.assertEqual((m["asked"], m["partial"]), (2, True))
        self.assertEqual(vl._cache, {})  # partial results are not cached


if __name__ == "__main__":
    unittest.main()
