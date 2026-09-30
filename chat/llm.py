"""Pluggable chat LLM: callable(messages) -> str. CHAT_LLM = stub (default) | openai | anthropic | qwen.

openai: OPENAI_API_KEY, CHAT_MODEL (default gpt-4o-mini). anthropic: ANTHROPIC_API_KEY, CHAT_MODEL (default
claude-haiku-4-5). qwen: any OpenAI-compatible local server (vLLM, llama.cpp, Ollama) at CHAT_QWEN_URL (default
http://localhost:8000/v1), CHAT_MODEL (default Qwen/Qwen2.5-1.5B-Instruct). Paid backends run only when CHAT_LLM
names them. CHAT_TIMEOUT_S (default 60). Temperature 0.
"""
import os
import re

import httpx

CTX_LINE = re.compile(r"^\[([^\]]+)\] \(([^)]*)\)(?: MERCHANT-STATED)? (.*)$")


def stub(messages):
    """Deterministic, offline: restates the first three context records, each cited."""
    user = messages[-1]["content"]
    lines = [m for m in (CTX_LINE.match(ln) for ln in user.split("\n")) if m]
    if not lines:
        return "I don't have data on that."
    return " ".join(f"{m.group(3).replace('. ', '; ').replace('[', '(').replace(']', ')').rstrip('.')}. [{m.group(1)}]" for m in lines[:3])


def _timeout():
    return float(os.environ.get("CHAT_TIMEOUT_S", "60"))


def _openai_compatible(messages, base, key, model):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = httpx.post(f"{base.rstrip('/')}/chat/completions", headers=headers, timeout=_timeout(),
                   json={"model": model, "messages": messages, "temperature": 0, "max_tokens": 600})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def openai(messages):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("CHAT_LLM=openai needs OPENAI_API_KEY")
    return _openai_compatible(messages, "https://api.openai.com/v1", key, os.environ.get("CHAT_MODEL", "gpt-4o-mini"))


def qwen(messages):
    return _openai_compatible(messages, os.environ.get("CHAT_QWEN_URL", "http://localhost:8000/v1"), None,
                              os.environ.get("CHAT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"))


def anthropic(messages):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("CHAT_LLM=anthropic needs ANTHROPIC_API_KEY")
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=_timeout(),
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                   json={"model": os.environ.get("CHAT_MODEL", "claude-haiku-4-5"), "system": system,
                         "max_tokens": 600, "temperature": 0,
                         "messages": [m for m in messages if m["role"] != "system"]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")


BACKENDS = {"stub": stub, "openai": openai, "anthropic": anthropic, "qwen": qwen}


def name():
    return os.environ.get("CHAT_LLM", "stub")


def get():
    if name() not in BACKENDS:
        raise ValueError(f"unknown CHAT_LLM {name()!r}; one of {sorted(BACKENDS)}")
    return BACKENDS[name()]
