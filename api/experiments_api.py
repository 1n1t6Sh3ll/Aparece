"""Experiment routes (TEAM-42). Logic lives in experiments/; this file is HTTP only.

EXPERIMENTS_CATALOG: normalized records JSONL used to auto-pick control products
(falls back to PRODUCTLENS_DATA, then dataset/output/final/train.jsonl).
"""
import os
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import lift, store  # noqa: E402

router = APIRouter(prefix="/v1", tags=["experiments"])
Id = Field(..., min_length=1, max_length=200)


class ExperimentRequest(BaseModel):
    product_id: str = Id
    language: str = Field(..., min_length=2, max_length=16)
    market: str = Field(..., min_length=1, max_length=64)
    problem: str = Field(..., min_length=1, max_length=2000)
    intervention: str = Field(..., min_length=1, max_length=2000)
    before_snapshot: str | None = Field(None, max_length=500)
    after_snapshot: str | None = Field(None, max_length=500)
    optimization_models: list[str] = Field(..., min_length=1, max_length=20)
    holdout_models: list[str] = Field([], max_length=20)
    control_products: list[str] | None = Field(None, max_length=50)
    k_controls: int = Field(5, ge=1, le=50)
    changed_products: list[str] = Field([], max_length=1000)  # products changed during the experiment; never controls
    accuracy_before: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def disjoint(self):
        if set(self.optimization_models) & set(self.holdout_models):
            raise ValueError("holdout_models must not overlap optimization_models")
        if self.control_products and (set(self.control_products) & (set(self.changed_products) | {self.product_id})):
            raise ValueError("control_products must not include the treated product or changed products")
        return self


class ResultRequest(BaseModel):
    kind: Literal["benchmark", "accuracy"]
    phase: Literal["baseline", "post", "before", "after"]
    split: Literal["dev", "hidden"] | None = None
    run: str | None = Field(None, max_length=200)
    report: dict | None = None  # benchmark report.json (benchmark/metrics.py build_report)
    accuracy: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "benchmark" and (self.phase not in ("baseline", "post") or not self.split or self.report is None):
            raise ValueError("benchmark results need phase baseline|post, split dev|hidden and report")
        if self.kind == "accuracy" and (self.phase not in ("before", "after") or self.accuracy is None):
            raise ValueError("accuracy results need phase before|after and accuracy")
        return self


def catalog_path():
    return (os.environ.get("EXPERIMENTS_CATALOG") or os.environ.get("PRODUCTLENS_DATA")
            or str(ROOT / "dataset" / "output" / "final" / "train.jsonl"))


def get_experiment(eid):
    exp = store.get(eid)
    if not exp:
        raise HTTPException(404, "experiment not found")
    return exp


def view(exp):
    res = store.results(exp["id"])
    return {"experiment": exp, "results": res, "analysis": lift.analyze(exp, res)}


@router.post("/experiments", status_code=201)
def create_experiment(req: ExperimentRequest):
    data = req.model_dump()
    if req.control_products is None:
        data["control_products"] = lift.pick_controls(req.product_id, lift.load_catalog(catalog_path()),
                                                      req.k_controls, req.changed_products)
        data["control_source"] = "auto: analysis/peers.py"
    else:
        data["control_source"] = "manual"
    return view(store.create(data))


@router.get("/experiments/{eid}")
def read_experiment(eid: str):
    return view(get_experiment(eid))


@router.post("/experiments/{eid}/results", status_code=201)
def add_result(eid: str, req: ResultRequest):
    exp = get_experiment(eid)
    if req.kind == "accuracy":
        data = {"phase": req.phase, "accuracy": req.accuracy}
    else:
        metrics, scope = lift.extract_metrics(req.report, {exp["product_id"], *exp["control_products"]}, exp["language"])
        if exp["product_id"] not in {p for m in metrics.values() for p in m}:
            raise HTTPException(422, "report has no metrics for the experiment product")
        data = {"phase": req.phase, "split": req.split, "run": req.run, "scope": scope, "metrics": metrics}
    store.add_result(eid, req.kind, data)
    return view(exp)
