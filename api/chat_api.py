"""POST /v1/chat (TEAM-46): merchant chat grounded in existing stores only. Retrieval/rules live in chat/.

Sources (each optional; missing data just means fewer records): a monitored product, addressed by its public id and
readable only with its X-Manage-Token (snapshots with metrics, consecutive-snapshot diffs, change events, trends
computed from >= 2 dated snapshots), dataset record, gaps, competitor table, price/review signals, benchmark visibility per
model/language, experiments (if the experiments package is installed), company profile (CHAT_COMPANY_PROFILE JSON).
CHAT_TOKEN: when set, requests must carry the same `token`. Each answer is written to the governance audit log
(action chat_answer; only a hash of question/answer/citations) when governance/ is present.
"""
import hmac
import json
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard_api  # noqa: E402
from chat import engine, llm  # noqa: E402
from monitor import history as snapshot_history, store  # noqa: E402

router = APIRouter(prefix="/v1", tags=["chat"])


class Turn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    token: str | None = Field(None, max_length=512)
    product_id: str | None = Field(None, max_length=200)
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


def monitor_records(pid):
    """Monitored product (internal id, already authorized): snapshots with their metrics, diffs between consecutive
    snapshots, change events and trends (deltas computed in code). Returns (records, dataset product_id)."""
    p = store.product(pid=pid)
    if not p:
        return [], None
    recs = [engine.record("monitored_product", p["public_id"], {"url": p["url"], "active": bool(p["active"])},
                          p["enrolled_at"])]
    h = store.history(pid)
    rows = h["snapshots"]
    series, dataset_pid = {}, None
    for s, m in zip(rows, snapshot_history.snapshots(pid)):
        c, sref = s["data"].get("content") or {}, f"snapshot:{s['id']}"
        dataset_pid = s["data"].get("product_id") or dataset_pid
        recs.append(engine.record("snapshot", s["id"], {"content": c, "metrics": m["metrics"]}, s["taken_at"],
                                  merchant_stated=True))
        mt = m["metrics"]
        points = {k: mt.get(k) for k in ("price", "description_chars", "attribute_completeness_pct",
                                          "peer_median_completeness_pct")}
        points["completeness_rank.position"] = (mt.get("completeness_rank") or {}).get("position")
        for model, v in (mt.get("visibility") or {}).items():
            for k, x in (v or {}).items():
                points[f"visibility.{model}.{k}"] = x
        for k, v in points.items():
            series.setdefault(k, []).append((s["taken_at"], v, sref))
    for a, b in zip(rows, rows[1:]):
        try:
            d = snapshot_history.diff(a, b)
        except (KeyError, TypeError):  # legacy snapshots without the full content shape
            continue
        recs.append(engine.record("snapshot_diff", f"{a['id']}-{b['id']}", d, b["taken_at"]))
    recs += [engine.record("change_event", e["id"], {k: e[k] for k in ("type", "field", "before", "after")}, e["at"])
             for e in h["events"]]
    return recs + engine.trends(series), dataset_pid


def dataset_records(pid):
    try:
        rec = dashboard_api.find(pid)
    except HTTPException:
        return []
    date = dashboard_api.get(rec, "source", "scraped_at")
    out = [engine.record("product", pid, dashboard_api.product(pid), date, merchant_stated=True),
           engine.record("gaps", pid, dashboard_api.gaps(pid, 10), date),
           engine.record("competitors", pid, dashboard_api.competitors(pid, 5), date)]
    sig = dashboard_api.signals().get(pid)
    if sig:
        out.append(engine.record("signals", pid, sig, sig.get("price_period")))
    return out


def visibility_records(pid):
    rep = dashboard_api.visibility()
    date = rep.get("generated_at") if isinstance(rep, dict) else None
    out = []
    for model, m in (rep.get("models") or {}).items() if isinstance(rep, dict) else []:
        for lang, s in (m.get("languages") or {}).items():
            keep = {k: s.get(k) for k in ("responses", "any_catalog_mention_rate", "stability")}
            out.append(engine.record("visibility", f"{model}/{lang}", {"model": model, "language": lang, **keep}, date))
        if pid and pid in (m.get("products") or {}):
            out.append(engine.record("visibility", f"{model}/product/{pid}",
                                     {"model": model, "product_id": pid, **m["products"][pid]}, date))
    return out


def experiment_records(pids):
    """Experiments on the product (treated or control), their result rows (without the bulky raw report) and the
    lift analysis computed by experiments.lift.analyze (status, statement, caveat, flags, guardrail)."""
    try:
        from experiments import lift, store as exp  # optional package (TEAM-42)
    except ImportError:
        return []
    pids = {p for p in pids if p}
    out = []
    for eid in exp.all_ids():
        e = exp.get(eid)
        if not pids or not pids & {e.get("product_id"), *(e.get("control_products") or [])}:
            continue
        results = exp.results(eid)
        out.append(engine.record("experiment", eid, e, e.get("created_at")))
        out += [engine.record("experiment_result", r["result_id"],
                              {"experiment": eid, **{k: v for k, v in r.items() if k != "report"}}, r.get("at"))
                for r in results]
        try:
            a = lift.analyze(e, results)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        keep = {k: a[k] for k in ("status", "statement", "caveat", "flags", "accuracy", "dev_vs_hidden",
                                  "generalization")}
        out.append(engine.record("experiment_analysis", eid, {"experiment": eid, "product_id": e.get("product_id"),
                                                              **keep}, results[-1]["at"] if results else None))
    return out


def company_records():
    p = os.environ.get("CHAT_COMPANY_PROFILE")
    try:
        data = json.loads(Path(p).read_text(encoding="utf-8")) if p else None
    except (OSError, ValueError):
        data = None
    return [engine.record("company_profile", "1", data, data.get("updated_at") if isinstance(data, dict) else None,
                          merchant_stated=True)] if data else []


def monitor_pid(product_id, manage_token):
    """Public monitor id -> internal id, requiring that product's manage token (401 missing, 403 wrong).
    None when product_id is not a monitored product (it may still be a dataset product id)."""
    pid = store.pid_for(product_id) if product_id else None
    if pid is None:
        return None
    if not manage_token:
        raise HTTPException(401, "X-Manage-Token header required for a monitored product")
    if not store.check_token(pid, manage_token):
        raise HTTPException(403, "invalid manage token")
    return pid


def collect(pid, monitor_id=None):
    """pid: public monitor id or dataset product id. monitor_id: authorized internal monitor id (monitor_pid)."""
    recs, dataset_pid = [], pid
    if monitor_id is not None:
        recs, linked = monitor_records(monitor_id)
        dataset_pid = linked
    if dataset_pid:
        recs += dataset_records(dataset_pid)
    return (recs + visibility_records(dataset_pid) + experiment_records([pid, dataset_pid] if pid else [])
            + company_records())


def audit_log(req, result):
    try:
        from governance import audit
    except ImportError:
        return False
    details = {"message": req.message, "answer": result["answer"], "citations": result["citations"]}
    try:
        audit.log("merchant_chat", "chat_answer", req.product_id, "auto",
                  "refused" if result["refused"] else "answered", audit.details_hash(details))
        return True
    except Exception:  # noqa: BLE001 -- a logging failure must not hide the answer
        return False


@router.post("/chat")
async def chat(req: ChatRequest, x_manage_token: str | None = Header(None)):
    expected = os.environ.get("CHAT_TOKEN")
    if expected and not (req.token and hmac.compare_digest(req.token, expected)):
        raise HTTPException(401, "invalid chat token")
    try:
        backend = llm.get()
    except ValueError as e:
        raise HTTPException(500, str(e))
    monitor_id = await run_in_threadpool(monitor_pid, req.product_id, x_manage_token)
    records = await run_in_threadpool(collect, req.product_id, monitor_id)
    try:
        result = await run_in_threadpool(engine.answer, records, req.message, backend,
                                         [t.model_dump() for t in req.history])
    except Exception as e:  # noqa: BLE001 -- backend/network errors
        raise HTTPException(502, f"chat backend error: {type(e).__name__}")
    result["backend"] = llm.name()
    result["audit_logged"] = await run_in_threadpool(audit_log, req, result)
    return result
