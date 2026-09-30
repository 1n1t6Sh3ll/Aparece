"""Shared prompt/target helpers for build_examples.py and eval.py."""
import html
import json

SYSTEM = (
    "Extract shirt attributes from the product text. Reply with one JSON object only, "
    "using exactly these keys. Use null when the text does not state a value."
)

# Target fields (dotted paths into the normalized record).
FIELDS = [
    "identity.product_type", "identity.audience",
    "materials.primary_material", "materials.material_percentages", "materials.fabric_type",
    "materials.fabric_weight_gsm", "materials.fabric_weight_raw", "materials.stretch", "materials.texture",
    "fit_and_style.fit", "fit_and_style.neckline", "fit_and_style.collar_type",
    "fit_and_style.sleeve_length", "fit_and_style.shirt_length", "fit_and_style.pattern", "fit_and_style.style",
    "variants.colors", "variants.sizes", "care", "features",
]

# Raw text fields shown to the model, in order.
RAW_FIELDS = [
    ("Title", "raw_title"), ("Name", "raw_product_name"), ("Category", "raw_category_text"),
    ("Description", "raw_full_description"), ("Short description", "raw_short_description"),
    ("Bullets", "raw_bullet_points"), ("Specifications", "raw_specifications"),
    ("Material", "raw_material_text"), ("Fit", "raw_fit_text"), ("Colors", "raw_color_text"),
    ("Sizes", "raw_size_text"), ("Care", "raw_care_text"), ("Features", "raw_features_text"),
]


def get(rec, path):
    for part in path.split("."):
        rec = rec.get(part) if isinstance(rec, dict) else None
    return rec


def prompt_text(raw, max_chars=4000):
    parts = []
    for label, key in RAW_FIELDS:
        v = raw.get(key)
        if not v:
            continue
        if isinstance(v, (list, dict)):
            v = "\n".join(map(str, v)) if isinstance(v, list) else json.dumps(v, ensure_ascii=False)
        parts.append(f"{label}: {html.unescape(str(v))}")  # "&#x20;" etc. waste tokens
    return "\n".join(parts)[:max_chars]


def target(norm):
    """Only fields with an evidence entry keep their value; the rest are null."""
    backed = {e["field"] for e in norm.get("evidence", [])}
    out = {}
    for f in FIELDS:
        v = get(norm, f) if f in backed else None
        if f == "variants.colors" and v:
            v = [c.get("normalized") for c in v]
        elif f == "variants.sizes" and v:
            v = [s.get("normalized_size") for s in v]
        out[f] = v if v not in ([], {}) else None
    return out


def messages(raw, norm=None, max_chars=4000, gold=None):
    """gold: an already-built target dict (dataset/output/final records carry one)."""
    msgs = [{"role": "system", "content": SYSTEM + "\nKeys: " + ", ".join(FIELDS)},
            {"role": "user", "content": prompt_text(raw, max_chars)}]
    if gold is None and norm is not None:
        gold = target(norm)
    if gold is not None:
        msgs.append({"role": "assistant",
                     "content": json.dumps({f: gold.get(f) for f in FIELDS}, ensure_ascii=False)})
    return msgs
