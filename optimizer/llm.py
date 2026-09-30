"""Pluggable text backends. Each backend is a callable (system, user) -> str that should return a JSON object
{"title": ..., "description": ...}.

OPTIMIZER_BACKEND: stub (default; deterministic, no model, no spend) | openai | anthropic | qwen.
OPTIMIZER_MODEL overrides the model (openai default gpt-4o-mini; anthropic default claude-haiku-4-5;
qwen default QWEN_BASE_MODEL or Qwen/Qwen2.5-1.5B-Instruct). Keys: OPENAI_API_KEY / ANTHROPIC_API_KEY.
Paid backends run only when the operator selects them explicitly.
"""
import json
import os
import re
import threading
import urllib.request

TIMEOUT = float(os.environ.get("OPTIMIZER_TIMEOUT_S", "60"))


def stub(system, user):
    """Deterministic: title and description are the localized fact lines given in the prompt."""
    data = json.loads(user.rsplit("\n", 1)[-1])  # the fact JSON is the prompt's last line
    return json.dumps({"title": data["fallback_title"], "description": " ".join(data["facts"])}, ensure_ascii=False)


def _post(url, headers, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 (fixed https endpoints)
        return json.loads(r.read())


def openai(system, user):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    body = {"model": os.environ.get("OPTIMIZER_MODEL", "gpt-4o-mini"), "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    out = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}, body)
    return out["choices"][0]["message"]["content"]


def anthropic(system, user):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = {"model": os.environ.get("OPTIMIZER_MODEL", "claude-haiku-4-5"), "max_tokens": 1024, "system": system,
            "messages": [{"role": "user", "content": user}]}
    out = _post("https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"}, body)
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")


_qwen, _qwen_lock = {}, threading.Lock()


def qwen(system, user):
    """Local base Qwen (no adapter; the TEAM extraction adapter is not a copywriter). Needs requirements-qwen.txt."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = os.environ.get("OPTIMIZER_MODEL") or os.environ.get("QWEN_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    with _qwen_lock:
        if name not in _qwen:
            _qwen[name] = (AutoTokenizer.from_pretrained(name), AutoModelForCausalLM.from_pretrained(name))
    tok, model = _qwen[name]
    ids = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                  add_generation_prompt=True, return_tensors="pt")
    out = model.generate(ids, max_new_tokens=400, do_sample=False)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)


BACKENDS = {"stub": stub, "openai": openai, "anthropic": anthropic, "qwen": qwen}


def get_backend(name=None):
    name = (name or os.environ.get("OPTIMIZER_BACKEND") or "stub").lower()
    if name not in BACKENDS:
        raise ValueError(f"unknown OPTIMIZER_BACKEND {name!r}; use one of {sorted(BACKENDS)}")
    return name, BACKENDS[name]


def parse(text):
    """One JSON object with string title and description (a ```json fence is tolerated)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    obj = json.loads(m.group(0) if m else text)
    if not isinstance(obj, dict) or not isinstance(obj.get("title"), str) or not isinstance(obj.get("description"), str):
        raise ValueError("backend output needs string 'title' and 'description'")
    return obj
