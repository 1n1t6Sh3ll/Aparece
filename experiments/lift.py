"""Deterministic experiment analysis (TEAM-42, vision sections 18-21, 23).

Metrics come from benchmark report.json files (benchmark/metrics.py build_report): per model, per product
mention rate, top-k rate and MRR. Each submitted report is one run of one phase (baseline/post) on one prompt
split (dev/hidden). Adjusted lift = treatment change - control change, in percentage points, with a
bootstrap CI that resamples runs. This is an observational comparison, never a causal claim.
"""
import json
import random
from pathlib import Path

from analysis.peers import find_peers, load_records

METRICS = ("mention_rate", "topk_rate", "mrr")
PHASES = ("baseline", "post")
SPLITS = ("dev", "hidden")
BOOTSTRAP = 2000
SEED = 0
OVERFIT_MIN_DEV_PP = 5.0     # dev prompts gained at least this much ...
OVERFIT_MAX_HIDDEN_PP = 1.0  # ... while hidden prompts gained at most this much
GENERALIZES_RATIO = 0.5      # holdout-model lift >= half the optimization-model lift
CAVEAT = ("Observational comparison against comparable untreated control products; "
          "not evidence that the intervention caused the change.")


def pick_controls(product_id, records, k=5, exclude=()):
    """k comparable products (analysis/peers.py) that were not changed during the experiment."""
    target = next((r for r in records if r.get("product_id") == product_id), None)
    if target is None:
        return []
    skip = set(exclude) | {product_id}
    return [r["product_id"] for _, r in find_peers(target, [r for r in records if r.get("product_id") not in skip], k)]


def load_catalog(path):
    return load_records(path) if path and Path(path).is_file() else []


def extract_metrics(report, product_ids, language=None):
    """{model: {product_id: {mention_rate, topk_rate, mrr}}} for the given products.
    Uses per-language product rows when the report has them, else the all-language rows."""
    k = report.get("k", 3)
    out, scope = {}, "all_languages"
    for model, m in (report.get("models") or {}).items():
        rows = m.get("products") or {}
        lang_rows = ((m.get("languages") or {}).get(language) or {}).get("products") if language else None
        if lang_rows:
            rows, scope = lang_rows, "language"
        got = {pid: {"mention_rate": r["mention_rate"], "topk_rate": r.get(f"top{k}_rate"), "mrr": r["mrr"]}
               for pid, r in rows.items() if pid in product_ids}
        if got:
            out[model] = got
    return out, scope


def _run_value(metrics, products, models, metric):
    vals = [metrics[m][p][metric] for m in models if m in metrics for p in products
            if p in metrics[m] and metrics[m][p].get(metric) is not None]
    return sum(vals) / len(vals) if vals else None


def _mean(xs):
    return sum(xs) / len(xs)


def lift(runs, treatment, controls, models, metric):
    """runs: benchmark results for one split. Returns None when a phase has no usable run."""
    pairs = {ph: [] for ph in PHASES}
    for r in runs:
        t = _run_value(r["metrics"], [treatment], models, metric)
        c = _run_value(r["metrics"], controls, models, metric) if controls else 0.0
        if t is not None and c is not None:
            pairs[r["phase"]].append((t, c))
    base, post = pairs["baseline"], pairs["post"]
    if not base or not post:
        return None

    def adjusted(b, p):
        return (_mean([x[0] for x in p]) - _mean([x[0] for x in b])) - (_mean([x[1] for x in p]) - _mean([x[1] for x in b]))

    ci = None
    if len(base) > 1 or len(post) > 1:
        rng = random.Random(SEED)
        boots = sorted(adjusted(rng.choices(base, k=len(base)), rng.choices(post, k=len(post))) for _ in range(BOOTSTRAP))
        ci = [round(100 * boots[int(0.025 * BOOTSTRAP)], 2), round(100 * boots[int(0.975 * BOOTSTRAP) - 1], 2)]
    tb, tp = _mean([x[0] for x in base]), _mean([x[0] for x in post])
    cb, cp = _mean([x[1] for x in base]), _mean([x[1] for x in post])
    return {"treatment_before": round(tb, 4), "treatment_after": round(tp, 4),
            "control_before": round(cb, 4) if controls else None, "control_after": round(cp, 4) if controls else None,
            "raw_change_pp": round(100 * (tp - tb), 2), "control_change_pp": round(100 * (cp - cb), 2) if controls else None,
            "adjusted_lift_pp": round(100 * adjusted(base, post), 2), "ci95_pp": ci,
            "runs_baseline": len(base), "runs_post": len(post)}


def _latest_accuracy(exp, results, phase):
    vals = [r["accuracy"] for r in results if r["kind"] == "accuracy" and r["phase"] == phase]
    return vals[-1] if vals else exp.get(f"accuracy_{phase}")


def _fmt(x):
    return f"{x:+.2f}"


def analyze(exp, results):
    groups = {"optimization": exp["optimization_models"], "holdout": exp.get("holdout_models") or []}
    bench = [r for r in results if r["kind"] == "benchmark"]
    controls = exp.get("control_products") or []
    lifts = {}
    for split in SPLITS:
        runs = [r for r in bench if r["split"] == split]
        lifts[split] = {g: {m: lift(runs, exp["product_id"], controls, models, m) for m in METRICS}
                        for g, models in groups.items() if models}

    def mention(split, group):
        v = (lifts.get(split, {}).get(group) or {}).get("mention_rate")
        return v["adjusted_lift_pp"] if v else None

    dev, hid = mention("dev", "optimization"), mention("hidden", "optimization")
    overfit = None if dev is None or hid is None else (dev >= OVERFIT_MIN_DEV_PP and hid <= OVERFIT_MAX_HIDDEN_PP)
    gen_split = "hidden" if hid is not None else "dev"
    opt, hold = mention(gen_split, "optimization"), mention(gen_split, "holdout")
    generalizes = None
    if opt is not None and hold is not None and opt > 0:
        generalizes = hold >= GENERALIZES_RATIO * opt

    acc_b, acc_a = _latest_accuracy(exp, results, "before"), _latest_accuracy(exp, results, "after")
    guardrail = "unknown" if acc_b is None or acc_a is None else ("fail" if acc_a < acc_b else "pass")

    flags = []
    if guardrail == "fail":
        flags.append("rejected: accuracy_after < accuracy_before")
    if overfit:
        flags.append("flagged: dev-prompt gain did not carry over to hidden prompts (possible overfitting)")
    if generalizes is False:
        flags.append("flagged: gain on optimization models did not carry over to holdout models")

    statement = None
    for split, group in (("hidden", "holdout"), ("hidden", "optimization"), ("dev", "optimization")):
        v = (lifts[split].get(group) or {}).get("mention_rate")
        if v:
            ci = f"95% bootstrap CI {_fmt(v['ci95_pp'][0])} to {_fmt(v['ci95_pp'][1])} pp" if v["ci95_pp"] else "no CI (one run per phase)"
            statement = (f"Observed adjusted visibility lift: {_fmt(v['adjusted_lift_pp'])} pp ({ci}; mention rate, "
                         f"{split} prompts, {group} models, vs {len(controls)} control products).")
            break
    status = "rejected" if guardrail == "fail" else ("flagged" if flags else ("reported" if statement else "pending"))
    return {"status": status, "statement": statement, "caveat": CAVEAT, "lifts": lifts,
            "dev_vs_hidden": {"dev_lift_pp": dev, "hidden_lift_pp": hid, "overfitting_flag": overfit,
                              "rule": f"dev >= {OVERFIT_MIN_DEV_PP} pp and hidden <= {OVERFIT_MAX_HIDDEN_PP} pp"},
            "generalization": {"split": gen_split, "optimization_lift_pp": opt, "holdout_lift_pp": hold,
                               "generalizes": generalizes, "rule": f"holdout >= {GENERALIZES_RATIO} x optimization"},
            "accuracy": {"before": acc_b, "after": acc_a, "guardrail": guardrail},
            "flags": flags}


def dataset_row(exp, analysis):
    """One intervention-dataset row (vision section 23)."""
    primary = None
    for split, group in (("hidden", "holdout"), ("hidden", "optimization"), ("dev", "optimization")):
        primary = (analysis["lifts"][split].get(group) or {}).get("mention_rate")
        if primary:
            break
    keys = ("id", "created_at", "product_id", "language", "market", "problem", "intervention",
            "before_snapshot", "after_snapshot", "control_products", "optimization_models", "holdout_models")
    row = {k: exp.get(k) for k in keys}
    row.update({
        "visibility_before": primary and primary["treatment_before"],
        "visibility_after": primary and primary["treatment_after"],
        "adjusted_lift_pp": primary and primary["adjusted_lift_pp"],
        "ci95_pp": primary and primary["ci95_pp"],
        "dev_lift_pp": analysis["dev_vs_hidden"]["dev_lift_pp"],
        "hidden_lift_pp": analysis["dev_vs_hidden"]["hidden_lift_pp"],
        "overfitting_flag": analysis["dev_vs_hidden"]["overfitting_flag"],
        "holdout_generalizes": analysis["generalization"]["generalizes"],
        "accuracy_before": analysis["accuracy"]["before"], "accuracy_after": analysis["accuracy"]["after"],
        "accuracy_guardrail": analysis["accuracy"]["guardrail"], "status": analysis["status"],
    })
    return row


def export_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
