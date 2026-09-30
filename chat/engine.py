"""Grounded merchant chat (TEAM-46): records -> trends -> retrieval -> LLM -> enforced answer.

A record is {"type", "id", "date", "text", "merchant_stated"}; its reference is "type:id" and the LLM must cite it
as [type:id]. The rules in SYSTEM are also enforced in code by enforce(): a sentence is kept only if it cites known
records, every number in it appears in a cited record, trend wording cites a trend/change_event record, it makes no
causal claim about rankings/visibility, and merchant-stated sources are labelled. Nothing left -> REFUSAL.
"""
import json
import math
import re
from collections import Counter

REFUSAL = "I don't have data on that."
TOP_K = 12
SYSTEM = f"""You answer a merchant's questions about their own products using ONLY the CONTEXT records below.
Rules:
1. Use only facts from CONTEXT. If CONTEXT does not answer the question, reply exactly: {REFUSAL}
2. End every sentence with the reference(s) it relies on, e.g. [snapshot:12]. Every number must come from a cited record.
3. Do no arithmetic. Describe changes over time only by citing a [trend:...] or [change_event:...] record, which
   already contain the computed deltas. Never infer a trend from a single data point.
4. Never claim that anything caused, drove or explains a ranking, mention or visibility result.
5. Records marked MERCHANT-STATED are the merchant's own claims, not verified facts; label them "merchant-stated".
Sentences that break these rules are removed before the merchant sees the answer."""

STOP = set("a an and are as at be by can do does did for from has have how i in is it its me my of on or our so "
           "that the their this to was were what when where which who why will with you your".split())
TREND_Q = re.compile(r"\b(trend|chang|over time|since|increas|decreas|went|grow|grew|drop|fell|rose|history)", re.I)
TREND_A = re.compile(r"\b(increas|decreas|rose|risen|rising|fell|fallen|falling|drop|grew|grow|declin|improv|worsen|"
                     r"trend|went (up|down)|upward|downward)\w*", re.I)
RANKING = re.compile(r"\b(rank|visib|mention|position|recommend|surfac|appear)\w*", re.I)
CAUSAL = re.compile(r"\b(because|due to|caus\w*|led to|leads to|lead to|result(ed|s)? (of|in|from)|thanks to|"
                    r"driven by|drives?|drove|explain\w*|contribut\w*|boost\w*|hurt\w*|responsible for)\b", re.I)
REF = re.compile(r"\[([^\[\]]+)\]")
NUM = re.compile(r"\d+(?:[.,]\d+)*")
SENT = re.compile(r"(?<=[.!?\]])\s+(?!\[)|\n+")  # a sentence ends after its citation(s)


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 1 and t not in STOP]


def numbers(text):
    """Numeric values in text; '1,299.50' -> 1299.5. '12,5' is also read as 12.5 (European decimals)."""
    out = set()
    for n in NUM.findall(text):
        cands = [n.replace(",", "")] + ([n.replace(",", ".")] if n.count(",") == 1 and "." not in n else [])
        for cand in cands:
            try:
                out.add(round(float(cand), 6))
            except ValueError:
                pass
    return out


def ref(r):
    return f"{r['type']}:{r['id']}"


def record(type_, id_, text, date=None, merchant_stated=False):
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return {"type": type_, "id": str(id_), "date": date, "text": text[:2000], "merchant_stated": merchant_stated}


def trends(series):
    """series: {metric: [(date, value, source_ref)]}. Metrics with >= 2 dated numeric points become trend records
    with first/last values and delta computed here (the LLM never does arithmetic)."""
    out = []
    for metric, pts in sorted(series.items()):
        pts = sorted((p for p in pts if p[0] and isinstance(p[1], (int, float)) and not isinstance(p[1], bool)),
                     key=lambda p: p[0])
        if len({p[0] for p in pts}) < 2:
            continue
        (d0, v0, s0), (d1, v1, s1) = pts[0], pts[-1]
        delta = round(v1 - v0, 6)
        pct = f"{round(100 * delta / v0, 2):+g}%" if v0 else "n/a (first value is 0)"
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
        text = (f"{metric} {direction} from {v0:g} on {d0} ({s0}) to {v1:g} on {d1} ({s1}); "
                f"delta {delta:+g}, change {pct}, {len(pts)} dated points")
        out.append({**record("trend", metric, text, d1), "delta": delta, "first": v0, "last": v1, "points": len(pts)})
    return out


def retrieve(records, question, k=TOP_K):
    """TF-IDF keyword score over record text (type included). Records scoring 0 are not relevant. A trend-style
    question also pulls in every trend and change_event record."""
    docs = [Counter(tokens(r["type"] + " " + r["text"])) for r in records]
    n = len(docs)
    df = Counter(t for d in docs for t in d)
    q = set(tokens(question))
    scored = []
    for r, d in zip(records, docs):
        s = sum((1 + math.log(d[t])) * math.log(1 + n / df[t]) for t in q if d[t])
        if TREND_Q.search(question) and r["type"] in ("trend", "change_event"):
            s += 1
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]


def messages(context, question, history=()):
    lines = [f"[{ref(r)}] ({r['date'] or 'undated'}){' MERCHANT-STATED' if r['merchant_stated'] else ''} {r['text']}"
             for r in context]
    msgs = [{"role": "system", "content": SYSTEM}]
    msgs += [{"role": h["role"], "content": h["content"]} for h in list(history)[-6:]]
    msgs.append({"role": "user", "content": "CONTEXT:\n" + "\n".join(lines) + f"\n\nQUESTION: {question}"})
    return msgs


def enforce(answer, context):
    """Returns (text, cited records, dropped sentence count)."""
    by_ref = {ref(r): r for r in context}
    kept, cited, dropped = [], {}, 0
    for sent in (s.strip() for s in SENT.split(answer or "")):
        if not sent or sent.rstrip(".") == REFUSAL.rstrip("."):
            continue
        refs = [x.strip() for m in REF.findall(sent) for x in re.split(r"[,;]", m) if x.strip()]
        body = re.sub(r"\s+([.!?,;:])", r"\1", re.sub(r"\s+", " ", REF.sub("", sent))).strip()
        recs = [by_ref.get(x) for x in refs]
        allowed = set().union(*(numbers(r["text"]) for r in recs if r)) if refs else set()
        ok = (refs and all(recs)
              and numbers(body) <= allowed
              and not (TREND_A.search(body) and not any(r["type"] in ("trend", "change_event") for r in recs))
              and not (RANKING.search(body) and CAUSAL.search(body)))
        if not ok:
            dropped += 1
            continue
        if any(r["merchant_stated"] for r in recs) and "merchant-stated" not in body.lower():
            end = body[-1] if body[-1] in ".!?" else ""
            body = body.rstrip(".!?") + " (merchant-stated)" + end
        kept.append(body + " " + " ".join(f"[{x}]" for x in dict.fromkeys(refs)))
        cited.update((x, by_ref[x]) for x in refs)
    return " ".join(kept), list(cited.values()), dropped


def answer(records, question, llm, history=()):
    """records: all candidate records (trend records included). llm: callable(messages) -> str."""
    context = retrieve(records, question)
    if not context:
        return {"answer": REFUSAL, "citations": [], "refused": True, "dropped_sentences": 0, "context": []}
    text, cited, dropped = enforce(llm(messages(context, question, history)), context)
    if not text:
        return {"answer": REFUSAL, "citations": [], "refused": True, "dropped_sentences": dropped,
                "context": [ref(r) for r in context]}
    cites = [{"type": r["type"], "id": r["id"], "date": r["date"], "merchant_stated": r["merchant_stated"]}
             for r in cited]
    return {"answer": text, "citations": cites, "refused": False, "dropped_sentences": dropped,
            "context": [ref(r) for r in context]}
