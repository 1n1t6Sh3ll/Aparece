import unittest

from benchmark.brands import brand_of, build, named_brands


class BrandsTest(unittest.TestCase):
    def test_brand_of(self):
        self.assertEqual(brand_of("Uniqlo U Oversized T-Shirt"), "Uniqlo")
        self.assertEqual(brand_of("Patagonia - Capilene Cool"), "Patagonia")
        self.assertEqual(brand_of("Under Armour Tech Tee"), "Under Armour")
        self.assertEqual(brand_of("H&M Basic Tee"), "H&M")

    def test_counted_once_per_answer(self):
        text = "1. **Uniqlo Tee**\n2. **Uniqlo Crew**\n- **Nike Dri-FIT**\nplain **bold** mid-line"
        self.assertEqual(named_brands(text), {"Uniqlo", "Nike"})

    def test_build(self):
        b = build([{"language": "en", "response_text": "1. **Uniqlo A**"},
                   {"language": "es", "response_text": "1. **Uniqlo B**\n2. **Zara C**"}])
        self.assertEqual(b["answers"], 2)
        self.assertEqual(b["top_named"][0], {"name": "Uniqlo", "answers": 2})
        self.assertEqual(b["by_language"], {"en": 1, "es": 1})


if __name__ == "__main__":
    unittest.main()
