"""Machine-readable governance policy (human-readable version: docs/GOVERNANCE.md).

mode: auto (runs, logged) | approve (needs a named human of the owner role) | forbidden (never runs).
Unknown actions are denied. `require()` is the single gate; every decision lands in the audit log.
"""
from . import audit

ACCOUNT_OWNER, MERCHANT, OPERATOR = "Account owner", "Merchant", "ProductLens operator"
ROLES = (ACCOUNT_OWNER, MERCHANT, OPERATOR)

POLICY = {
    # automated (logged)
    "extract_product": {"mode": "auto", "owner": OPERATOR, "description": "Extract/normalize a product page the user submitted."},
    "monitor_crawl": {"mode": "auto", "owner": OPERATOR, "description": "Recrawl an enrolled product and record changes."},
    "benchmark_free_run": {"mode": "auto", "owner": OPERATOR, "description": "Benchmark with mock/local models (no spend)."},
    "benchmark_paid_run": {"mode": "auto", "owner": ACCOUNT_OWNER,
                           "description": "Paid benchmark within the owner's standing budget (--max-usd <= BENCHMARK_MAX_USD)."},
    "generate_suggestions": {"mode": "auto", "owner": OPERATOR, "description": "Draft listing suggestions for review (not published)."},
    "change_alert": {"mode": "auto", "owner": ACCOUNT_OWNER, "description": "Notify an enrolled owner about detected changes."},
    # needs human approval
    "benchmark_paid_run_over_cap": {"mode": "approve", "owner": ACCOUNT_OWNER,
                                    "description": "Paid benchmark above the standing budget, or with no budget set."},
    "confirm_model_prediction": {"mode": "approve", "owner": MERCHANT,
                                 "description": "Accept a model-predicted attribute as fact in the merchant's record."},
    "publish_suggestions": {"mode": "approve", "owner": MERCHANT, "description": "Mark suggestions publish-ready / apply them."},
    "run_experiment": {"mode": "approve", "owner": MERCHANT, "description": "Start a listing experiment against a baseline."},
    "change_plan_or_billing": {"mode": "approve", "owner": ACCOUNT_OWNER, "description": "Change plan or enable paid features."},
    # never automatic
    "auto_publish_to_storefront": {"mode": "forbidden", "owner": MERCHANT,
                                   "description": "Write to a live storefront without a per-change merchant approval."},
    "optimize_on_hidden_split": {"mode": "forbidden", "owner": OPERATOR,
                                 "description": "Feed hidden-split prompts or results to any optimizer."},
    "share_merchant_data": {"mode": "forbidden", "owner": ACCOUNT_OWNER,
                            "description": "Sell or share merchant/shopper data with third parties."},
    "train_on_restricted_data": {"mode": "forbidden", "owner": OPERATOR,
                                 "description": "Train on data whose license or consent does not allow it."},
    "fabricate_claims": {"mode": "forbidden", "owner": MERCHANT,
                         "description": "Publish attributes, reviews or metrics without evidence."},
    "alter_audit_log": {"mode": "forbidden", "owner": OPERATOR, "description": "Update or delete audit entries."},
}


class GovernanceError(Exception):
    pass


class Forbidden(GovernanceError):
    pass


class ApprovalRequired(GovernanceError):
    def __init__(self, action, approval_id, owner):
        super().__init__(f"{action} needs approval by {owner}: approval_id={approval_id}")
        self.action, self.approval_id, self.owner = action, approval_id, owner


def require(action, actor, target=None, details=None, approval_id=None, owner=None):
    """Gate an action. Returns the audit decision dict; raises Forbidden or ApprovalRequired.
    owner: monitored product id; pass it only after validating that product's manage token (tenant scoping)."""
    rule = POLICY.get(action)
    dhash = audit.details_hash(details)
    if rule is None:
        audit.log(actor, action, target, "unknown", "denied", dhash, owner=owner)
        raise Forbidden(f"unknown action {action!r} (deny by default)")
    mode = rule["mode"]
    if mode == "forbidden":
        audit.log(actor, action, target, mode, "denied", dhash, owner=owner)
        raise Forbidden(f"{action} is never automatic: {rule['description']}")
    if mode == "auto":
        audit.log(actor, action, target, mode, "allowed", dhash, owner=owner)
        return {"action": action, "mode": mode, "approved_by": None}
    approver = audit.consume(approval_id, action, target, dhash, actor, owner) if approval_id else None
    if approver:
        return {"action": action, "mode": mode, "approved_by": approver, "approval_id": approval_id}
    raise ApprovalRequired(action, audit.request(action, target, actor, dhash, owner), rule["owner"])


def _norm(actor):
    return (actor or "").strip().casefold()


def approve(approval_id, approver, role, approve=True):
    """Named human of the action's owner role decides a pending request; requester cannot self-approve."""
    row = audit.get(approval_id)
    if not row or row["status"] != "pending":
        raise GovernanceError("no pending approval with that id")
    owner = POLICY[row["action"]]["owner"]
    if role != owner:
        raise GovernanceError(f"{row['action']} must be decided by {owner}")
    if _norm(approver) == _norm(row["requested_by"]):
        raise GovernanceError("requester cannot approve their own request")
    decided = audit.decide(approval_id, approver, approve)
    if not decided:
        raise GovernanceError("no pending approval with that id")
    return decided
