"""MODEL_BACKEND=qwen: rules first, then a base Qwen + LoRA adapter fills fields the rules left null.

Merge policy: rule-extracted facts with evidence stay primary and untouched. Model outputs only cover fields that
train/common.target() leaves null, are validated against dataset/schema, and are returned separately as
`predicted: {field: {value, confidence, model}}` -- never written into the normalized record (no evidence).

Confidence: geometric mean of the generated tokens' probabilities (greedy decoding, softmax of the step scores) over
the tokens that overlap the field's JSON value in the output. It is null when the generator returns no token scores.
It is the model's own likelihood, not a calibrated accuracy.

Env: QWEN_ADAPTER_PATH (required), QWEN_BASE_MODEL (default Qwen/Qwen2.5-1.5B-Instruct),
QWEN_TIMEOUT_S (default 30), QWEN_MAX_NEW (default 512).
The model loads lazily once (thread-safe); 4-bit NF4 via bitsandbytes when CUDA is available, else CPU fp32.
Any load/generation/parse error or timeout falls back to the rules-only result with `model_status` explaining why.
"""
import concurrent.futures
import importlib.util
import json
import math
import os
import threading
from pathlib import Path

from fastapi import HTTPException
from jsonschema import Draft202012Validator
from normalize import build_normalized

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("train_common", ROOT / "train" / "common.py")
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

DEFAULT_BASE = "Qwen/Qwen2.5-1.5B-Instruct"


def _field_validators():
    schema = json.loads((ROOT / "dataset" / "schema" / "normalized_record.schema.json").read_text(encoding="utf-8"))
    out = {}
    for f in common.FIELDS:
        node = schema
        for part in f.split("."):
            node = node["properties"][part]
        if f == "variants.colors":  # target() flattens to the normalized names
            node = {"type": "array", "items": node["items"]["properties"]["normalized"]}
        elif f == "variants.sizes":
            node = {"type": "array", "items": node["items"]["properties"]["normalized_size"]}
        out[f] = Draft202012Validator({**node, "$defs": schema["$defs"]})
    return out


VALIDATORS = _field_validators()


def parse(text):
    """Same tolerance as train/eval.py: strip a ```json fence, require one JSON object."""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("model output is not a JSON object")
    return obj


def field_confidence(text, field, token_probs):
    """token_probs: [(start, end, prob)] char spans in `text`. Geometric mean over tokens overlapping the value."""
    if not token_probs:
        return None
    key = text.find(json.dumps(field))
    if key < 0:
        return None
    start = text.find(":", key) + 1
    while start < len(text) and text[start].isspace():
        start += 1
    try:
        _, end = json.JSONDecoder().raw_decode(text, start)
    except ValueError:
        return None
    probs = [p for s, e, p in token_probs if s < end and e > start and p > 0]
    if not probs:
        return None
    return round(math.exp(sum(math.log(p) for p in probs) / len(probs)), 4)


def merge(norm, text, token_probs, model_name):
    """Predictions only for fields the rules left null; invalid or null predictions are dropped."""
    rules = common.target(norm)
    obj = parse(text)
    predicted = {}
    for f in common.FIELDS:
        v = obj.get(f)
        if rules[f] is not None or v is None or v in ([], {}):
            continue
        if not VALIDATORS[f].is_valid(v):
            continue
        predicted[f] = {"value": v, "confidence": field_confidence(text, f, token_probs), "model": model_name}
    return predicted


class QwenGenerator:
    """messages -> (text, [(start, end, prob)]). Loads once on first call."""

    def __init__(self, adapter, base=DEFAULT_BASE, max_new=512):
        self.adapter, self.base, self.max_new = adapter, base, max_new
        self.name = f"{base}+{Path(adapter).name}"
        self._lock = threading.Lock()
        self._model = self._tok = None

    def _load(self):
        with self._lock:
            if self._model is not None:
                return
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            if torch.cuda.is_available():
                q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                       bnb_4bit_compute_dtype=torch.bfloat16)
                model = AutoModelForCausalLM.from_pretrained(self.base, quantization_config=q, device_map="auto")
            else:
                model = AutoModelForCausalLM.from_pretrained(self.base, torch_dtype=torch.float32)
            self._tok = AutoTokenizer.from_pretrained(self.base)
            self._model = PeftModel.from_pretrained(model, self.adapter).eval()

    def __call__(self, messages, max_time=None):
        import torch
        self._load()
        tok, model = self._tok, self._model
        ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt",
                                      return_dict=True).to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=self.max_new, do_sample=False, max_time=max_time,
                                 output_scores=True, return_dict_in_generate=True)
        gen = out.sequences[0, ids["input_ids"].shape[1]:].tolist()
        text, spans = "", []
        for i, t in enumerate(gen):
            prob = torch.softmax(out.scores[i][0].float(), -1)[t].item()
            nxt = tok.decode(gen[:i + 1], skip_special_tokens=True)
            spans.append((len(text), len(nxt), prob))
            text = nxt
        return text, spans


_gen = None
_gen_lock = threading.Lock()
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen")  # serializes generation


def get_generator():
    global _gen
    adapter = os.environ.get("QWEN_ADAPTER_PATH")
    if not adapter:
        raise HTTPException(501, "MODEL_BACKEND=qwen requires QWEN_ADAPTER_PATH")
    with _gen_lock:
        if _gen is None:
            _gen = QwenGenerator(adapter, os.environ.get("QWEN_BASE_MODEL", DEFAULT_BASE),
                                 int(os.environ.get("QWEN_MAX_NEW", "512")))
        return _gen


def qwen_backend(raw):
    """Rules-normalized record plus `_model: {predicted, model_status}` for api/main.py to lift out."""
    norm = build_normalized(raw)
    gen = get_generator()
    timeout = float(os.environ.get("QWEN_TIMEOUT_S", "30"))
    try:
        text, spans = _pool.submit(gen, common.messages(raw), timeout).result(timeout=timeout + 1)
        predicted, status = merge(norm, text, spans, getattr(gen, "name", "qwen")), "ok"
    except concurrent.futures.TimeoutError:  # generate(max_time) bounds the worker; this is the backstop
        predicted, status = {}, "fallback: timeout"
    except Exception as e:  # noqa: BLE001 -- any model failure falls back to rules
        predicted, status = {}, f"fallback: {type(e).__name__}"
    norm["_model"] = {"predicted": predicted, "model_status": status}
    return norm
