"""MODEL_BACKEND=qwen with a stub generator (no torch, no GPU, no model download)."""
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import model_backend as mb  # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures" / "heavy_tee.html").read_text(encoding="utf-8")
URL = "https://shop.example.com/products/heavy-tee"
client = TestClient(main.app)

# heavy_tee rules give product_type=t_shirt (evidence-backed) and leave audience/pattern/stretch null.
OUTPUT = {"identity.product_type": "polo", "identity.audience": "men", "fit_and_style.pattern": "plaid_ish",
          "materials.stretch": True, "care": [], "fit_and_style.style": None}


class Stub:
    name = "stub-qwen"

    def __init__(self, text=None, spans=True, exc=None, sleep=0):
        self.text = text if text is not None else json.dumps(OUTPUT)
        self.spans, self.exc, self.sleep, self.calls = spans, exc, sleep, []

    def __call__(self, messages, max_time=None):
        self.calls.append(messages)
        if self.sleep:
            time.sleep(self.sleep)
        if self.exc:
            raise self.exc
        # one "token" per char, prob 0.9 except 0.5 inside the audience value
        a = self.text.find('"men"')
        spans = [(i, i + 1, 0.5 if a <= i < a + 5 else 0.9) for i in range(len(self.text))] if self.spans else []
        return self.text, spans


def run(stub, **env):
    with mock.patch.dict(os.environ, {"MODEL_BACKEND": "qwen", "QWEN_ADAPTER_PATH": "x", **env}), \
            mock.patch.object(mb, "_gen", stub):
        r = client.post("/v1/extract", json={"html": FIXTURE, "url": URL})
    assert r.status_code == 200, r.text
    return r.json()


class QwenBackendTest(unittest.TestCase):
    def test_rules_primary_model_fills_nulls_only(self):
        stub = Stub()
        body = run(stub)
        rules = client.post("/v1/extract", json={"html": FIXTURE, "url": URL}).json()
        self.assertEqual(body["model_status"], "ok")
        norm = body["normalized"]
        norm.pop("scraped_at", None), rules["normalized"].pop("scraped_at", None)
        self.assertEqual(norm, rules["normalized"])  # model never writes page facts
        self.assertNotIn("_model", norm)
        pred = body["predicted"]
        self.assertNotIn("identity.product_type", pred)  # rules had evidence
        self.assertEqual(pred["identity.audience"], {"value": "men", "confidence": 0.5, "model": "stub-qwen"})
        self.assertEqual(pred["materials.stretch"]["value"], True)
        self.assertAlmostEqual(pred["materials.stretch"]["confidence"], 0.9)
        self.assertNotIn("fit_and_style.pattern", pred)  # not in schema enum
        self.assertNotIn("care", pred)  # empty -> not a prediction
        self.assertNotIn("fit_and_style.style", pred)
        # prompt comes from train/common.py
        self.assertEqual(stub.calls[0][0]["content"], mb.common.messages({})[0]["content"])

    def test_confidence_null_without_token_scores(self):
        pred = run(Stub(spans=False))["predicted"]
        self.assertIsNone(pred["identity.audience"]["confidence"])

    def test_fenced_json_accepted(self):
        pred = run(Stub(text="```json\n" + json.dumps(OUTPUT) + "\n```"))["predicted"]
        self.assertEqual(pred["identity.audience"]["value"], "men")

    def test_fallbacks(self):
        for stub, status in [(Stub(text="not json"), "fallback: JSONDecodeError"),
                             (Stub(text="[1]"), "fallback: ValueError"),
                             (Stub(exc=RuntimeError("cuda oom")), "fallback: RuntimeError")]:
            body = run(stub)
            self.assertEqual((body["predicted"], body["model_status"]), ({}, status))
            self.assertEqual(body["normalized"]["identity"]["product_type"], "t_shirt")

    def test_timeout_falls_back(self):
        body = run(Stub(sleep=1.5), QWEN_TIMEOUT_S="0.1")
        self.assertEqual((body["predicted"], body["model_status"]), ({}, "fallback: timeout"))
        time.sleep(0.5)  # let the stub finish so the single worker is free

    def test_missing_adapter_is_501(self):
        with mock.patch.dict(os.environ, {"MODEL_BACKEND": "qwen"}), mock.patch.object(mb, "_gen", None):
            os.environ.pop("QWEN_ADAPTER_PATH", None)
            self.assertEqual(client.post("/v1/extract", json={"html": FIXTURE}).status_code, 501)

    def test_generator_created_once_across_threads(self):
        got = []
        with mock.patch.dict(os.environ, {"QWEN_ADAPTER_PATH": "runs/qlora"}), mock.patch.object(mb, "_gen", None):
            ts = [threading.Thread(target=lambda: got.append(mb.get_generator())) for _ in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(len({id(g) for g in got}), 1)
        self.assertEqual(got[0].name, "Qwen/Qwen2.5-1.5B-Instruct+qlora")
        self.assertIsNone(got[0]._model)  # lazy: nothing loaded until first generation

    def test_model_load_once_cpu_fp32(self):
        fake = mock.MagicMock()
        fake.cuda.is_available.return_value = False
        fake.AutoModelForCausalLM.from_pretrained.side_effect = lambda *a, **k: time.sleep(0.05) or mock.MagicMock()
        g = mb.QwenGenerator("runs/qlora")
        with mock.patch.dict(sys.modules, {"torch": fake, "peft": fake, "transformers": fake}):
            ts = [threading.Thread(target=g._load) for _ in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        load = fake.AutoModelForCausalLM.from_pretrained
        self.assertEqual(load.call_count, 1)
        self.assertEqual(load.call_args.kwargs, {"torch_dtype": fake.float32})
        fake.PeftModel.from_pretrained.assert_called_once()


if __name__ == "__main__":
    unittest.main()
