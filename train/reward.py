"""Deterministic, verifiable reward for one model output (the JSON over common.FIELDS).

reward(output, input_text, gold=None) -> {"total", "format_ok", "fields", "hallucinated", "errors"}

  format       +1 if the output is one JSON object whose values pass the dataset schema, else FORMAT_FAIL and stop.
  grounding    each non-null predicted value must be supported by the input text: re-derived with the
               dataset/collect/normalize.py rules, or matched verbatim / by alias. Unsupported = hallucination, HALLUCINATION each.
  correctness  only with gold: +1 per exact match on a non-null gold field; -0.5 for filling a field gold has as
               null *only if* the value is also unsupported (supported-but-not-in-gold is neutral: gold may be incomplete).

Enum value "unknown" is read as null (an abstention, not a claim). Missing keys count as null.
CLI: python train/reward.py PRED.jsonl DATA.jsonl [--rows OUT.jsonl]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dataset" / "collect"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import FIELDS, get, prompt_text  # noqa: E402
from normalize import (AUDIENCE, COLORS, FIT, MATERIALS, NECKLINE, PATTERN, PRODUCT_TYPE, SLEEVE,  # noqa: E402
                       parse_composition, parse_weight)

FORMAT_OK, FORMAT_FAIL, HALLUCINATION, MATCH, UNSUPPORTED_EXTRA = 1.0, -10.0, -2.0, 1.0, -0.5

# ---- schema: one validator per field, taken from normalized_record.schema.json -------------------------

_SCHEMA = json.loads((ROOT / "dataset" / "schema" / "normalized_record.schema.json").read_text(encoding="utf-8"))


def _field_schema(field):
    """Target shape of a field (common.target): colors/sizes become lists of their normalized strings,
    empty lists/objects become null."""
    node = _SCHEMA
    for part in field.split("."):
        node = node["properties"][part]
    if field == "variants.colors":
        node = {"type": "array", "items": node["items"]["properties"]["normalized"]}
    elif field == "variants.sizes":
        node = {"type": "array", "items": node["items"]["properties"]["normalized_size"]}
    return {"anyOf": [node, {"type": "null"}], "$defs": _SCHEMA["$defs"]}


VALIDATORS = {f: Draft202012Validator(_field_schema(f)) for f in FIELDS}

# ---- grounding ---------------------------------------------------------------------------------------

LOOKUPS = {"fit_and_style.fit": FIT, "fit_and_style.neckline": NECKLINE, "fit_and_style.sleeve_length": SLEEVE,
           "fit_and_style.pattern": PATTERN, "identity.audience": AUDIENCE, "identity.product_type": PRODUCT_TYPE,
           "materials.primary_material": MATERIALS}
ALIASES = {"blend": r"\bblend\b|\bmezcla\b", "tailored": r"\btailored\b|\ba medida\b",
           "color_block": r"colou?r[ -]?block", "textured": r"\btextur", "three_quarter": r"3/4|three[ -]quarter"}


def _norm(s):
    return re.sub(r"\s+", " ", str(s).replace("_", " ")).strip().lower()


def _alias(value, text):
    """Verbatim (underscores as spaces or hyphens) or ALIASES match."""
    words = r"[ _-]?".join(map(re.escape, str(value).split("_")))
    return bool(re.search(r"(?<!\w)" + words + r"(?!\w)", text, re.I)
                or (value in ALIASES and re.search(ALIASES[value], text, re.I)))


def _rule(table, value, text):
    pattern = dict(table).get(value)
    return bool(pattern and re.search(pattern, text, re.I))


def _enum_supported(field, value, text):
    if field == "identity.product_type" and value in ("short_sleeve_shirt", "long_sleeve_shirt"):
        return _rule(PRODUCT_TYPE, "_shirt", text) and _rule(SLEEVE, value.split("_")[0], text)
    return _rule(LOOKUPS[field], value, text) or _alias(value, text)


def _compositions(text):
    """Every composition normalize.py would parse: up to 4 consecutive lines, as in build_normalized."""
    lines, out = text.split("\n"), []
    for i in range(len(lines)):
        for k in range(1, 5):
            comp, _ = parse_composition("\n".join(lines[i:i + k]))
            if comp:
                out.append(comp)
                break
    return out


def _pct_supported(comp, text):
    """Unsupported entries of a material -> percent dict ([] = fully supported)."""
    if any(comp == c for c in _compositions(text)):
        return []
    bad = []
    for mat, pct in comp.items():
        num = f"{pct:g}".replace(".", "[.,]")
        if not (re.search(r"(?<![\d.,])" + num + r"\s*%", text) and _rule(MATERIALS, mat, text)):
            bad.append(f"{mat}: {pct}")
    return bad


def _gsm_supported(gsm, text):
    for chunk in [text] + text.split("\n"):
        w = parse_weight(chunk)
        if w and w[0] is not None and abs(w[0] - gsm) <= 1:
            return True
    return False


def _size_supported(size, text):
    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(str(size)) + r"(?![A-Za-z0-9])", text, re.I))


def unsupported(field, value, text):
    """Parts of a non-null predicted value not supported by the input text ([] = supported)."""
    if field in LOOKUPS:
        return [] if _enum_supported(field, value, text) else [value]
    if field == "materials.material_percentages":
        return _pct_supported(value, text)
    if field == "materials.fabric_weight_gsm":
        return [] if _gsm_supported(value, text) else [value]
    if field == "materials.stretch":
        pat = r"\bstretch(?:y)?\b|\bel[aá]stic[oa]\b" if value else r"non[- ]stretch|no stretch|sin el[aá]stic|\brigid\b"
        return [] if re.search(pat, text, re.I) else [value]
    if field == "variants.colors":
        return [c for c in value if c is not None
                and not (re.search(r"\b(?:" + COLORS[c] + r")\b", text, re.I) if c in COLORS else _alias(c, text))]
    if field == "variants.sizes":
        return [s for s in value if s is not None and not _size_supported(s, text)]
    if field in ("care", "features"):
        return [s for s in value if _norm(s) not in _norm(text)]
    return [] if _norm(value) in _norm(text) else [value]  # free-text fields: verbatim


# ---- reward ------------------------------------------------------------------------------------------

def parse(output):
    """dict, or JSON text (optionally in a ``` fence). None unless it is one JSON object."""
    if isinstance(output, dict):
        return output
    if not isinstance(output, str):
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", output.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _clean(v):
    return None if v in ([], {}, "unknown") else v


def reward(output, input_text, gold=None):
    pred = parse(output)
    if pred is None:
        return {"total": FORMAT_FAIL, "format_ok": False, "fields": {}, "hallucinated": [], "errors": ["not a JSON object"]}
    errors = [f"{f}: {e.message}" for f in FIELDS if f in pred for e in VALIDATORS[f].iter_errors(pred[f])]
    if errors:
        return {"total": FORMAT_FAIL, "format_ok": False, "fields": {}, "hallucinated": [], "errors": errors}

    total, fields, hallucinated = FORMAT_OK, {}, []
    for f in FIELDS:
        value = _clean(pred.get(f))
        g = _clean(gold.get(f)) if gold is not None else None
        bad = unsupported(f, value, input_text) if value is not None else []
        row = {"value": value, "grounding": HALLUCINATION if bad else 0.0, "unsupported": bad, "correctness": 0.0}
        if bad:
            hallucinated.append(f)
        if gold is not None:
            if g is not None and value == g:
                row["correctness"] = MATCH
            elif g is None and bad:
                row["correctness"] = UNSUPPORTED_EXTRA
        total += row["grounding"] + row["correctness"]
        fields[f] = row
    return {"total": total, "format_ok": True, "fields": fields, "hallucinated": hallucinated,
            "errors": [f"missing key {f}" for f in FIELDS if f not in pred]}


# ---- files ------------------------------------------------------------------------------------------

def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def input_of(row):
    """Model input text of a data row: the user message (build_examples.py), else prompt_text(raw)."""
    for m in row.get("messages") or []:
        if m.get("role") == "user":
            return m["content"]
    return prompt_text(row["raw"])


def gold_of(row):
    msgs = row.get("messages") or []
    if msgs and msgs[-1].get("role") == "assistant":
        return json.loads(msgs[-1]["content"])
    return row.get("gold")


def output_of(row):
    """api_eval *_responses.jsonl use "text"; other scripts may save "output" or "prediction" (str or dict)."""
    return next((row[k] for k in ("text", "output", "prediction") if k in row), None)


def score_file(pred_jsonl, data_jsonl):
    """Score saved outputs against their inputs (joined on product_id). A data row with no prediction
    counts as a format failure. Returns (summary, per-row results)."""
    preds = {r["product_id"]: r for r in read_jsonl(pred_jsonl)}
    rows = []
    for d in read_jsonl(data_jsonl):
        p = preds.get(d["product_id"])
        res = reward(output_of(p) if p else None, input_of(d), gold_of(d))
        rows.append({"product_id": d["product_id"], **res})
    n = max(len(rows), 1)
    filled = sum(1 for r in rows for x in r["fields"].values() if x["value"] is not None)
    counts = {}
    for r in rows:
        for f in r["hallucinated"]:
            counts[f] = counts.get(f, 0) + 1
    summary = {"n": len(rows), "missing_predictions": sum(r["product_id"] not in preds for r in rows),
               "mean_reward": sum(r["total"] for r in rows) / n,
               "format_ok": sum(r["format_ok"] for r in rows) / n,
               "filled_fields": filled, "hallucinated_fields": sum(counts.values()),
               "hallucination_rate": sum(counts.values()) / max(filled, 1),
               "hallucinated_by_field": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}
    return summary, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pred_jsonl", help="rows with product_id and text/output/prediction")
    ap.add_argument("data_jsonl", help="build_examples.py rows (product_id, messages) or rows with raw")
    ap.add_argument("--rows", help="also write per-row rewards here")
    args = ap.parse_args()
    summary, rows = score_file(args.pred_jsonl, args.data_jsonl)
    if args.rows:
        with open(args.rows, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(summary, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
