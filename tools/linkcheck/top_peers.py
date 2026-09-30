"""List the product URLs that most often appear as top-k peers (analysis.peers.find_peers), most frequent first,
so the link checker can start with the links audits actually show.

  python -m tools.linkcheck.top_peers --data dataset/output/final/train.jsonl --out peers_urls.txt [--targets 2000]

Targets are a deterministic sample (seed 0) of the dataset; peers are searched within the same product type and
language, which find_peers requires anyway.
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "api"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from analysis.peers import find_peers, get  # noqa: E402
from tools.linkcheck.status import record_url  # noqa: E402


def peer_counts(records, targets, k=10):
    groups = defaultdict(list)
    for r in records:
        groups[(get(r, "identity", "product_type"), get(r, "source", "language"))].append(r)
    counts = Counter()
    for t in targets:
        for _, p in find_peers(t, groups[(get(t, "identity", "product_type"), get(t, "source", "language"))], k):
            if record_url(p):
                counts[record_url(p)] += 1
    return counts


def main(argv=None):
    import dashboard_api  # the same record adapter the API uses
    ap = argparse.ArgumentParser(prog="tools.linkcheck.top_peers")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--targets", type=int, default=2000, help="sampled targets (0 = all)")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--top", type=int, default=2000)
    a = ap.parse_args(argv)
    recs = dashboard_api._load_adapted(a.data)
    targets = recs if not a.targets or a.targets >= len(recs) else random.Random(0).sample(recs, a.targets)
    counts = peer_counts(recs, targets, a.k)
    Path(a.out).write_text("".join(u + "\n" for u, _ in counts.most_common(a.top)), encoding="utf-8")
    print(json.dumps({"records": len(recs), "targets": len(targets), "distinct_peers": len(counts),
                      "written": min(a.top, len(counts))}))


if __name__ == "__main__":
    main()
