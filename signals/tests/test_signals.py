import json
import os
import tempfile
import unittest

from signals import build, reference, reviews

HERE = os.path.dirname(os.path.abspath(__file__))


def clean(pid, price, currency="EUR", sale=None, rating=None, domain="shop.example", lang="en"):
    return {"product_id": pid,
            "source": {"url": "https://%s/%s" % (domain, pid), "merchant_domain": domain, "language": lang,
                       "scraped_at": "2024-10-01T00:00:00Z"},
            "identity": {"product_type": "t_shirt"},
            "commerce": {"price": price, "sale_price": sale, "currency": currency, "rating": rating}}


def raw(pid, offers=None, product_schema=None, asin=None):
    r = {"product_id": pid, "raw_offer_schema": offers, "raw_product_schema": product_schema}
    if asin:
        r["provenance"] = {"original": {"parent_asin": asin}}
    return r


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


class ReviewsTest(unittest.TestCase):
    def test_aggregate_only_wanted_with_verbatim_excerpts(self):
        with open(os.path.join(HERE, "fixtures", "reviews_sample.jsonl"), "rb") as f:
            agg = reviews.aggregate(f, {"B000TEST01"})
        self.assertEqual(list(agg), ["B000TEST01"])
        a = agg["B000TEST01"]
        self.assertEqual(a["rating_count"], 4)
        self.assertEqual(a["rating_mean"], 3.25)
        self.assertEqual(a["rating_histogram"], {"1": 1, "2": 0, "3": 1, "4": 1, "5": 1})
        # most helpful first, ties broken by earliest timestamp; text kept verbatim
        self.assertEqual([e["text"] for e in a["excerpts"]],
                         ["Shrank after one wash.", "Soft and fits well.", "Average shirt."])
        self.assertEqual(a["provenance"]["license"], "undeclared-research-only")


class HelpersTest(unittest.TestCase):
    def test_quantile_and_percentile(self):
        v = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertEqual(build.quantile(v, .25), 20.0)
        self.assertEqual(build.quantile(v, .5), 30.0)
        self.assertEqual(build.percentile_rank(v, 30.0), 50.0)
        self.assertEqual(build.percentile_rank(v, 5.0), 0.0)

    def test_fx_and_cpi(self):
        self.assertAlmostEqual(reference.fx_to_usd(10.0, "EUR", "2024-10-01"), 11.086)
        self.assertIsNone(reference.fx_to_usd(10.0, "ARS", "2024-10-01"))
        self.assertIsNone(reference.fx_date_for("2025-03"))
        self.assertAlmostEqual(reference.to_target_usd(304.702, "2023"), 334.98)
        self.assertIsNone(reference.to_target_usd(10.0, "1999"))


class BuildTest(unittest.TestCase):
    def run_build(self, wdc_clean, wdc_raw, amz_clean=(), amz_raw=(), agg=None):
        with tempfile.TemporaryDirectory() as d:
            paths = [os.path.join(d, n) for n in ("wc", "wr", "ac", "ar")]
            for p, rows in zip(paths, (wdc_clean, wdc_raw, amz_clean, amz_raw)):
                write_jsonl(p, rows)
            out = build.build([("wdc", paths[0], paths[1]), ("amazon-reviews-2023", paths[2], paths[3])], agg or {})
        return {s["product_id"]: s for s in out}

    def test_signals_and_flags(self):
        peers = [clean("p%d" % i, float(p)) for i, p in enumerate([20, 22, 24, 26, 28, 30, 32, 34, 36, 38])]
        rows = peers + [
            clean("disc", 20.0),
            clean("outlier", 5000.0),
            clean("zero", 0.0),
            clean("nocur", 25.0, currency=None),
            clean("badrate", 25.0, rating=96),
            clean("conflict", 25.0),
            clean("ars", 9000.0, currency="ARS"),
        ]
        raws = [raw("disc", offers=[{"price": "20", "priceCurrency": "EUR", "priceSpecification":
                                     {"priceType": "https://schema.org/ListPrice", "price": "80"}}]),
                raw("conflict", offers=[{"price": "25", "priceCurrency": "EUR"}, {"price": "90", "priceCurrency": "EUR"}]),
                raw("badrate", product_schema={"aggregateRating": {"ratingValue": "96", "bestRating": "100",
                                                                   "reviewCount": "5"},
                                               "review": [{"reviewBody": "Top", "reviewRating": {"ratingValue": "5"}}]})]
        s = self.run_build(rows, raws)
        d = s["disc"]
        self.assertEqual((d["list_price"], d["discount_pct"], d["suspicious_discount"]), (80.0, 75.0, True))
        self.assertIn("suspicious_discount", d["flags"])
        self.assertIn("price_outlier", s["outlier"]["flags"])
        self.assertIn("nonpositive_price", s["zero"]["flags"])
        self.assertIsNone(s["zero"]["peer"])
        self.assertIn("missing_currency", s["nocur"]["flags"])
        self.assertIsNone(s["nocur"]["price_usd"])
        self.assertIn("rating_out_of_range", s["badrate"]["flags"])
        self.assertEqual(s["badrate"]["reviews"]["rating_5"], 4.8)
        self.assertEqual(s["badrate"]["reviews"]["excerpts"][0]["text"], "Top")
        self.assertIn("conflicting_prices", s["conflict"]["flags"])
        self.assertIsNone(s["ars"]["price_usd"])  # no ECB rate -> null, never guessed
        p = s["p0"]
        self.assertEqual(p["peer"]["group"], "t_shirt|en|EUR")
        self.assertEqual(p["peer"]["position"], "below_peer_range")
        self.assertIn("not a recommended or guaranteed price", p["guidance"]["note"])
        self.assertAlmostEqual(p["price_usd"], 22.17)
        self.assertAlmostEqual(p["price_usd_2026"], round(20 * 1.1086 * 334.98 / 315.664, 2))
        self.assertEqual(p["flags"], [])

    def test_amazon_reviews_join_and_assumed_currency(self):
        agg = {"B000TEST01": {"parent_asin": "B000TEST01", "rating_mean": 1.5, "rating_count": 4,
                              "rating_histogram": {}, "excerpts": [], "product_id": "x", "provenance": {}}}
        s = self.run_build([], [], [clean("a1", 17.99, currency=None, rating=4.7, domain="amazon.com")],
                           [raw("a1", asin="B000TEST01")], agg)["a1"]
        self.assertEqual((s["currency"], s["research_only"], s["price_period"]), ("USD", True, "2023"))
        self.assertIn("missing_currency", s["flags"])
        self.assertIn("rating_conflict", s["flags"])
        self.assertEqual(s["reviews"]["rating_count"], 4)
        self.assertAlmostEqual(s["price_usd_2026"], round(17.99 * 334.98 / 304.702, 2))


if __name__ == "__main__":
    unittest.main()
