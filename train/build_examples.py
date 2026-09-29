"""Build chat-format train/val/test JSONL, split by merchant domain."""
import argparse
import hashlib
import json
from pathlib import Path

from common import messages

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset" / "output"


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def split_of(domain, val, test):
    # Stable hash of the domain -> every record of a store lands in one split.
    h = int(hashlib.sha256(domain.encode()).hexdigest(), 16) % 1000 / 1000
    return "test" if h < test else "val" if h < test + val else "train"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized", help="default: shirts_clean.jsonl, else shirts_normalized.jsonl")
    ap.add_argument("--raw", default=str(OUT / "shirts_raw.jsonl"))
    ap.add_argument("--examples", action="store_true", help="use dataset/examples (smoke test)")
    ap.add_argument("--out", default=str(ROOT / "train" / "data"))
    ap.add_argument("--val", type=float, default=0.1)
    ap.add_argument("--test", type=float, default=0.1)
    args = ap.parse_args()

    if args.examples:
        ex = ROOT / "dataset" / "examples"
        norms = [json.loads((ex / "normalized_record.example.json").read_text(encoding="utf-8"))]
        raws = [json.loads((ex / "raw_record.example.json").read_text(encoding="utf-8"))]
    else:
        norm_path = args.normalized or next(
            (p for p in (OUT / "shirts_clean.jsonl", OUT / "shirts_normalized.jsonl") if p.exists()), None)
        if not norm_path:
            raise SystemExit("no shirts_clean.jsonl or shirts_normalized.jsonl in dataset/output")
        norms, raws = read_jsonl(norm_path), read_jsonl(args.raw)
    raw_by_id = {r["product_id"]: r for r in raws}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = {"train": [], "val": [], "test": []}
    domains = {"train": set(), "val": set(), "test": set()}
    missing = 0
    for n in norms:
        raw = raw_by_id.get(n["product_id"])
        if raw is None:
            missing += 1
            continue
        dom = n["source"]["merchant_domain"]
        s = "train" if args.examples else split_of(dom, args.val, args.test)
        rows[s].append({"product_id": n["product_id"], "domain": dom, "messages": messages(raw, n)})
        domains[s].add(dom)
    if args.examples:  # one record: reuse it in every split so the pipeline runs end to end
        rows["val"] = rows["test"] = rows["train"]
    else:
        assert not (domains["train"] & domains["val"] or domains["train"] & domains["test"]
                    or domains["val"] & domains["test"]), "domain leak across splits"

    for s, rs in rows.items():
        with open(out / f"{s}.jsonl", "w", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{s}: {len(rs)} records, {len(domains[s]) or len({r['domain'] for r in rs})} domains")
    print(f"skipped (no raw match): {missing}")


if __name__ == "__main__":
    main()
