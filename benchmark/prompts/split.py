"""Deterministic 60/20/20 dev/val/hidden split by canonical intent (VISION §27).

Both language expressions of an intent share its split. Hidden prompts live in
hidden.jsonl so optimizers can simply never read that file.
"""
import random

SEED = 32


def assign_splits(intents, seed=SEED):
    ids = sorted(set(intents))
    random.Random(seed).shuffle(ids)
    n_dev, n_val = round(len(ids) * 0.6), round(len(ids) * 0.2)
    return {i: "dev" if k < n_dev else "val" if k < n_dev + n_val else "hidden"
            for k, i in enumerate(ids)}
