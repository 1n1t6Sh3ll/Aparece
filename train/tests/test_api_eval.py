"""Offline tests for api_eval.py: no network, fake model call."""
import json
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import api_eval  # noqa: E402
from common import FIELDS  # noqa: E402

PRICES = {"fake-1": {"input": 1.0, "output": 10.0}}


def make_rows(tmp_path, n=6):
    rows = []
    for i in range(n):
        gold = {f: None for f in FIELDS}
        gold["identity.product_type"] = "t-shirt"
        rows.append({"product_id": f"p{i}", "language": "en" if i % 2 else "es", "source": "wdc",
                     "domain": f"d{i % 3}.com", "gold": gold,
                     "messages": [{"role": "system", "content": "SYS"}, {"role": "user", "content": f"item {i}"},
                                  {"role": "assistant", "content": json.dumps(gold)}]})
    path = tmp_path / "test.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def fake_call(provider, model, system, user, max_tokens):
    fake_call.n += 1
    ans = {f: None for f in FIELDS}
    ans["identity.product_type"] = "t-shirt" if user.endswith(("0", "2", "4")) else "polo"
    return {"text": "```json\n" + json.dumps(ans) + "\n```", "model_version": model + "-v", "stop": "end",
            "input_tokens": 100, "output_tokens": 50, "raw": {}}


def args_for(data, out, **kw):
    return Namespace(data=str(data), models=["fake:fake-1"], out_dir=str(out), max_usd=kw.get("max_usd", 1.0),
                     max_tokens=64, dry_run=kw.get("dry_run", False), sample=0, report_only=False)


def test_prompt_is_the_stored_qwen_prompt(tmp_path):
    rows = api_eval.load_rows(make_rows(tmp_path))
    assert (rows[0]["_system"], rows[0]["_user"]) == ("SYS", "item 0")


def test_run_is_resumable_and_scores(tmp_path):
    data, out = make_rows(tmp_path), tmp_path / "out"
    rows, fake_call.n = api_eval.load_rows(data), 0
    api_eval.run(args_for(data, out), rows, PRICES, call=fake_call, log=lambda *a: None)
    api_eval.run(args_for(data, out), rows, PRICES, call=fake_call, log=lambda *a: None)
    assert fake_call.n == 6  # second run reuses stored responses
    base, res = api_eval.report(args_for(data, out), rows)
    r = res["fake-1"]
    assert r["json_valid"] == 1.0 and r["non_null_acc"] == 0.5 and r["null_acc"] == 1.0
    assert r["by_language"]["es"]["non_null_acc"] == 1.0 and r["by_language"]["en"]["non_null_acc"] == 0.0
    assert abs(r["cost_usd"] - 6 * (100 * 1 + 50 * 10) / 1e6) < 1e-9
    saved = json.loads((out / "fake-1_eval.json").read_text())
    assert set(saved) == {"all_null_baseline", "fake-1"} and base["non_null_acc"] == 0.0


def test_changed_prompt_is_called_again(tmp_path):
    data, out = make_rows(tmp_path), tmp_path / "out"
    rows, fake_call.n = api_eval.load_rows(data), 0
    api_eval.run(args_for(data, out), rows, PRICES, call=fake_call, log=lambda *a: None)
    rows[0]["_hash"] = "changed"
    api_eval.run(args_for(data, out), rows, PRICES, call=fake_call, log=lambda *a: None)
    assert fake_call.n == 7


def test_spend_cap_and_dry_run(tmp_path):
    data, out = make_rows(tmp_path), tmp_path / "out"
    rows, fake_call.n = api_eval.load_rows(data), 0
    api_eval.run(args_for(data, out, dry_run=True), rows, PRICES, call=fake_call, log=lambda *a: None)
    assert fake_call.n == 0
    # upper-bound estimate per call is ~ (8/2*1 + 64*10)/1e6 = 0.000644; cap allows 2 calls
    api_eval.run(args_for(data, out, max_usd=0.0015), rows, PRICES, call=fake_call, log=lambda *a: None)
    assert fake_call.n == 2 and api_eval.total_spent(out) <= 0.0015


def test_stratified_is_proportional_and_deterministic(tmp_path):
    rows = api_eval.load_rows(make_rows(tmp_path, n=10))
    a, b = api_eval.stratified(rows, 4), api_eval.stratified(rows, 4)
    assert [r["product_id"] for r in a] == [r["product_id"] for r in b]
    assert sorted(r["language"] for r in a) == ["en", "en", "es", "es"]


def test_comparison_keeps_other_models(tmp_path):
    data, out = make_rows(tmp_path), tmp_path / "out"
    rows = api_eval.load_rows(data)
    api_eval.run(args_for(data, out), rows, PRICES, call=fake_call, log=lambda *a: None)
    base, res = api_eval.report(args_for(data, out), rows)
    comp = tmp_path / "comparison.json"
    comp.write_text(json.dumps({"models": {"qwen": {"label": "Qwen"}}}))
    api_eval.write_comparison(comp, rows, base, res)
    doc = json.loads(comp.read_text())
    assert set(doc["models"]) == {"qwen", "all_null_baseline", "fake-1"}
    assert doc["test"] == {"products": 6, "stores": 3, "note": "Fine-tuned Qwen results coming next."}
    m = doc["models"]["fake-1"]
    assert m["by_language"]["en"]["n"] == 3 and m["cost_per_1k_usd"] == round(600 / 1e6 * 1000, 4)


def test_partial_run_scores_only_answered_rows(tmp_path):
    data, out = make_rows(tmp_path), tmp_path / "out"
    rows, fake_call.n = api_eval.load_rows(data), 0
    api_eval.run(args_for(data, out, max_usd=0.0015), rows, PRICES, call=fake_call, log=lambda *a: None)
    with open(out / "fake-1_responses.jsonl", "a", encoding="utf-8") as f:
        f.write('{"product_id": "p5", "trunc')  # line still being written by a live run
    args = args_for(data, out)
    args.models = ["fake:fake-1", "fake:none-1"]
    base, res = api_eval.report(args, rows)
    r = res["fake-1"]
    assert (r["answered"], r["total"], r["partial"], r["n"]) == (2, 6, True, 2)
    assert r["json_valid"] == 1.0 and r["null_acc"] == 1.0
    comp = tmp_path / "comparison.json"
    api_eval.write_comparison(comp, rows, base, res)
    models = json.loads(comp.read_text())["models"]
    assert "none-1" not in models and models["fake-1"]["partial"] is True
    assert models["fake-1"]["answered"] == 2 and models["fake-1"]["total"] == 6
