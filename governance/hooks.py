"""Thin gates for callers. They add a policy check in front of an action and do not change what the action does."""
import os

from . import policy


def gate_benchmark_run(args, actor=None):
    """Call before benchmark.harness.run(args) does a paid run. When approved, or when args.max_usd is within
    BENCHMARK_MAX_USD, it only writes to the log and returns. Otherwise it raises ApprovalRequired, which includes the request id."""
    from benchmark.harness import FREE  # lazy: governance must import without benchmark
    if all(m.split(":", 1)[0] in FREE for m in args.models):
        return policy.require("benchmark_free_run", actor or "cli", target="benchmark")
    cap = os.environ.get("BENCHMARK_MAX_USD")
    within = bool(cap) and args.max_usd is not None and args.max_usd <= float(cap)
    details = {"models": sorted(args.models), "max_usd": args.max_usd, "prompts": str(args.prompts)}
    return policy.require("benchmark_paid_run" if within else "benchmark_paid_run_over_cap",
                          actor or getattr(args, "actor", None) or "cli", target="benchmark", details=details,
                          approval_id=getattr(args, "approval_id", None))


def confirm_prediction(record_id, field, value, actor, approval_id=None):
    """A model prediction becomes a merchant-confirmed fact only after Merchant approval of exactly this value."""
    decision = policy.require("confirm_model_prediction", actor, target=f"{record_id}#{field}",
                              details={"value": value}, approval_id=approval_id)
    return {"record_id": record_id, "field": field, "value": value, "confirmed": True,
            "approved_by": decision["approved_by"]}
