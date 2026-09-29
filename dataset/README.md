# Shirt dataset

Schemas and examples for the PowerLens shirt product dataset. The spec and all decisions are in [`docs/DATASET_SPEC.md`](../docs/DATASET_SPEC.md).

- `schema/raw_record.schema.json`: source text exactly as found on a product page.
- `schema/normalized_record.schema.json`: normalized attributes, each backed by evidence.
- `examples/`: one real raw record and its normalized record (Thinking MU, White hemp Jules shirt).
- `tests/test_schema.py`: validates the examples and rejects invalid records.

## Run the checks

Requires Python 3.9+.

```sh
python -m pip install -r dataset/requirements.txt
python -m unittest discover -s dataset/tests -v
```

Run from the repo root. Generated data goes in `dataset/output/` and page caches in `dataset/.cache/`; both are git-ignored.
