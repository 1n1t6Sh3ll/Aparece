"""Validate the dataset JSON Schemas against the example records and a few invalid cases.

Run from the repo root: python -m unittest discover -s dataset/tests -v
"""
import copy
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

DATASET = Path(__file__).resolve().parents[1]


def load(rel):
    return json.loads((DATASET / rel).read_text(encoding="utf-8"))


RAW_SCHEMA = load("schema/raw_record.schema.json")
NORM_SCHEMA = load("schema/normalized_record.schema.json")
RAW = load("examples/raw_record.example.json")
NORM = load("examples/normalized_record.example.json")


def errors(schema, record):
    return list(Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(record))


def resolve(record, path):
    """Follow a path like raw_description.sections[0].text into a record."""
    node = record
    for key, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
        node = node[key] if key else node[int(index)]
    return node


class ValidExamples(unittest.TestCase):
    def test_schemas_are_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(RAW_SCHEMA)
        Draft202012Validator.check_schema(NORM_SCHEMA)

    def test_raw_example_is_valid(self):
        self.assertEqual(errors(RAW_SCHEMA, RAW), [])

    def test_normalized_example_is_valid(self):
        self.assertEqual(errors(NORM_SCHEMA, NORM), [])

    def test_records_share_product_id(self):
        self.assertEqual(RAW["product_id"], NORM["product_id"])

    def test_evidence_text_is_found_in_the_raw_record(self):
        for item in NORM["evidence"]:
            target = resolve(RAW, item["source_location"])
            haystack = target if isinstance(target, str) else json.dumps(target, ensure_ascii=False)
            self.assertIn(item["source_text"], haystack, item["field"])


class InvalidRecords(unittest.TestCase):
    def assertRejected(self, schema, record):
        self.assertNotEqual(errors(schema, record), [])

    def test_bad_enum(self):
        rec = copy.deepcopy(NORM)
        rec["fit_and_style"]["fit"] = "baggy"
        self.assertRejected(NORM_SCHEMA, rec)

    def test_unknown_material_key(self):
        rec = copy.deepcopy(NORM)
        rec["materials"]["material_percentages"] = {"cottn": 100}
        self.assertRejected(NORM_SCHEMA, rec)

    def test_missing_required_normalized_field(self):
        rec = copy.deepcopy(NORM)
        del rec["commerce"]["sale_price"]  # must be null, not omitted
        self.assertRejected(NORM_SCHEMA, rec)

    def test_missing_required_raw_field(self):
        rec = copy.deepcopy(RAW)
        del rec["raw_meta_description"]
        self.assertRejected(RAW_SCHEMA, rec)

    def test_raw_description_needs_combined_text(self):
        rec = copy.deepcopy(RAW)
        del rec["raw_description"]["combined_text"]
        self.assertRejected(RAW_SCHEMA, rec)

    def test_empty_string_instead_of_null(self):
        rec = copy.deepcopy(RAW)
        rec["raw_short_description"] = ""
        self.assertRejected(RAW_SCHEMA, rec)

    def test_bad_timestamp(self):
        rec = copy.deepcopy(RAW)
        rec["scraped_at"] = "yesterday"
        self.assertRejected(RAW_SCHEMA, rec)

    def test_bad_product_id(self):
        rec = copy.deepcopy(RAW)
        rec["product_id"] = "jules-shirt"
        self.assertRejected(RAW_SCHEMA, rec)

    def test_unresolved_conflict_cannot_carry_a_resolution(self):
        rec = copy.deepcopy(NORM)
        rec["conflicts"] = [{
            "field": "materials.material_percentages",
            "status": "conflicting",
            "observations": [
                {"value": "100% cotton", "source": "raw_full_description"},
                {"value": "95% cotton, 5% elastane", "source": "raw_specifications"},
            ],
            "resolution": {"value": {"cotton": 100}, "rule": "guess"},
        }]
        self.assertRejected(NORM_SCHEMA, rec)
        rec["conflicts"][0]["resolution"] = None
        self.assertEqual(errors(NORM_SCHEMA, rec), [])

    def test_evidence_needs_source_text(self):
        rec = copy.deepcopy(NORM)
        del rec["evidence"][0]["source_text"]
        self.assertRejected(NORM_SCHEMA, rec)


if __name__ == "__main__":
    unittest.main()
