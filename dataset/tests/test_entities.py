"""HTML entities in extracted text are decoded before normalization; raw stays as scraped (issue #103)."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))

from extract import build_raw  # noqa: E402
from normalize import build_normalized, unescape  # noqa: E402
from run import evidence_errors  # noqa: E402

LOTR = "Lord&#x20;of&#x20;the&#x20;Rings"
NAME = "Lord&#x20;Of&#x20;The&#x20;Rings&#x3A;&#x20;Gold&#x20;Foil&#x20;Logo&#x20;T-Shirt"
DESC = "100&#x25;&#x20;cotton&#x20;t-shirt,&#x20;short&#x20;sleeve.&amp;amp;&#x20;Regular&#x20;fit."


def raw_record():
    ld = '{"@type": "Product", "name": "%s", "brand": {"@type": "Brand", "name": "%s"}, ' \
         '"offers": {"price": "20", "priceCurrency": "GBP"}}' % (NAME, LOTR)
    html = f'<html lang="en"><head><title>{NAME}</title><script type="application/ld+json">{ld}</script></head></html>'
    prod = {"title": NAME, "variants": [{"id": "1", "price": "20", "available": True}]}
    raw = build_raw(prod, html, "https://www.merchoid.com/p/", "https://www.merchoid.com/p/",
                    {"merchant": "merchoid", "domain": "merchoid.com"}, "2026-09-30T00:00:00Z")
    raw["raw_full_description"] = DESC
    raw["raw_description"] = {"sections": [{"heading": None, "section_type": "overview", "text": DESC}], "combined_text": DESC}
    return raw


class Entities(unittest.TestCase):
    def test_unescape_until_stable(self):
        self.assertEqual(unescape(LOTR), "Lord of the Rings")
        self.assertEqual(unescape("A &amp;amp;#x20;B &#233; &eacute;"), "A  B é é")

    def test_only_terminated_entities(self):
        for s in ("cotton&notice", "Tom&Jerry", "a &amp b", "&#x20 x", "R&D 100%"):
            self.assertEqual(unescape(s), s)
        self.assertEqual(unescape("cotton &amp; notice&#59;"), "cotton & notice;")

    def test_wdc_decode_uses_same_rule(self):
        from wdc import decode
        self.assertEqual(decode("cotton&notice &amp;amp; Lord&#x20;of"), "cotton&notice & Lord of")

    def test_ground_truth_verifies_decoded_evidence(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))
        from make_ground_truth import verify
        raw = raw_record()
        n = build_normalized(raw)
        drops = {}
        kept = verify(n, raw, drops)
        self.assertEqual(kept["identity"]["brand"], "Lord of the Rings")
        self.assertEqual(len(kept["evidence"]), len(n["evidence"]))

    def test_normalized_fields_decoded_raw_unchanged(self):
        raw = raw_record()
        before = copy.deepcopy(raw)
        n = build_normalized(raw)
        self.assertEqual(raw, before)  # raw stays raw
        self.assertEqual(n["identity"]["brand"], "Lord of the Rings")
        self.assertEqual(n["identity"]["product_name"], "Lord Of The Rings: Gold Foil Logo T-Shirt")
        self.assertEqual(n["content"]["title"], "Lord Of The Rings: Gold Foil Logo T-Shirt")
        self.assertNotIn("&#", n["content"]["full_description"])
        self.assertEqual(n["materials"]["material_percentages"], {"cotton": 100})  # "100&#x25;" is now readable
        self.assertEqual(n["identity"]["product_type"], "t_shirt")
        self.assertFalse(any("&#x" in str(e["source_text"]) for e in n["evidence"]))
        self.assertEqual(evidence_errors(raw, n), [])  # evidence still resolves against the raw record


if __name__ == "__main__":
    unittest.main()
