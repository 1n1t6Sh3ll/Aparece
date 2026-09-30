import unittest

from analysis.gaps import description_coverage, repetition
from analysis.peers import find_peers, pack_size


def rec(pid, title="Crew tee", sleeve="short", audience=None, price=None, currency=None, **extra):
    return {"product_id": pid, "source": {"language": "en"}, "content": {"title": title},
            "identity": {"product_type": "t_shirt", "audience": audience},
            "fit_and_style": {"sleeve_length": sleeve}, "commerce": {"price": price, "currency": currency}, **extra}


class PeerFilters(unittest.TestCase):
    """#84: peers match sleeve length, adult vs kids, pack size and live links; price band needs both currencies."""

    def ids(self, target, cands):
        return [c["product_id"] for _, c in find_peers(target, cands, 50)]

    def test_sleeve_length(self):
        t = rec("t")
        self.assertEqual(self.ids(t, [rec("a"), rec("b", sleeve="long"), rec("c", sleeve=None)]), ["a", "c"])

    def test_kids_never_peers_of_adult_or_unknown(self):
        t = rec("t")  # audience unknown -> adult
        cands = [rec("a", audience="kids"), rec("b", title="Little Green Radicals kids tee"), rec("c", audience="men"),
                 rec("d", title="Cooperstown Tee (Adult or Youth)"), rec("e")]
        self.assertEqual(sorted(self.ids(t, cands)), ["c", "d", "e"])
        self.assertEqual(sorted(self.ids(rec("k", audience="kids"), cands)), ["a", "b"])

    def test_pack_size(self):
        self.assertEqual([pack_size(rec("x", title=t)) for t in ("True Regular Fit Tee 3-Pack", "Pack of 2 tees",
                                                               "Camiseta 3 piezas", "Crew tee", "1-pack tee")],
                         [3, 2, 3, 1, 1])
        t = rec("t", title="Regular Fit Tee 3-Pack")
        self.assertEqual(self.ids(t, [rec("a"), rec("b", title="Organic tee 3 pack")]), ["b"])

    def test_dead_links_excluded_when_status_exists(self):
        cands = [rec("a", link_status="dead"), rec("b", link_status=404), rec("c", source={"language": "en",
                 "link_status": "redirected"}), rec("d", link_status={"status": 200}), rec("e")]
        self.assertEqual(self.ids(rec("t"), cands), ["d", "e"])

    def test_price_band_only_when_both_currencies_known(self):
        t = rec("t", price=20, currency="EUR")
        cands = [rec("a", price=100, currency="EUR"), rec("b", price=21, currency="EUR"), rec("c", price=100)]
        self.assertEqual(self.ids(t, cands), ["b"])  # c: no currency -> not the same market
        self.assertEqual(sorted(self.ids(rec("u", price=20), cands)), ["a", "b", "c"])  # target currency unknown


class Description(unittest.TestCase):
    """#83: the description scores distinct shopper intents once each; repetition lowers it."""
    BASE = "Classic men's crew neck t-shirt in soft 100% cotton jersey. Regular fit, short sleeves. Machine washable."

    def cov(self, text):
        return description_coverage({"content": {"full_description": text}})

    def test_stuffing_and_repetition_earn_nothing(self):
        base = self.cov(self.BASE)
        self.assertGreater(base["value"], 0.5)
        self.assertLessEqual(self.cov(self.BASE + " cotton t-shirt men tee crew neck black cotton" * 12)["value"],
                             base["value"])
        self.assertEqual(self.cov(" ".join([self.BASE] * 6))["value"], 0.0)
        self.assertGreater(self.cov(self.BASE + " Made in Portugal.")["value"], base["value"])  # a new fact counts
        self.assertEqual(repetition(self.BASE), 0.0)


if __name__ == "__main__":
    unittest.main()
