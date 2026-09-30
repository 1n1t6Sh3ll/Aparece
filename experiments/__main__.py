"""Export the intervention dataset (vision section 23): python -m experiments export out.jsonl"""
import argparse

from experiments import lift, store


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m experiments")
    ap.add_argument("command", choices=["export"])
    ap.add_argument("out")
    a = ap.parse_args(argv)
    rows = []
    for eid in store.all_ids():
        exp = store.get(eid)
        rows.append(lift.dataset_row(exp, lift.analyze(exp, store.results(eid))))
    lift.export_jsonl(a.out, rows)
    print(f"wrote {len(rows)} rows to {a.out}")


if __name__ == "__main__":
    main()
