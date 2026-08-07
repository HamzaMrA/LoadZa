"""HTTP interface.

    uvicorn app.api:app --reload

Endpoints are synchronous on purpose. Solving is CPU-bound Python; declaring
the handlers ``async`` would run them on the event loop and block every other
request, while a plain ``def`` handler gets a worker thread. The annealing
budget is capped for the same reason -- an HTTP request is not the place for an
unbounded search.

The database path comes from ``LOADZA_DB``, so tests point it at a temporary
file instead of reaching for a fixture that monkey-patches a global.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from app.db import NotFound, Store
from app.schemas import (
    JobSummary,
    PlanSummary,
    SolveRequest,
    ValidationRequest,
    ValidationResponse,
    ViolationOut,
)
from core import __version__, catalog
from core.improve_sa import AnnealConfig, improve
from core.io import (
    item_type_to_dict,
    job_from_dict,
    job_to_dict,
    plan_from_dict,
    plan_to_dict,
    vehicle_to_dict,
)
from core.solver_ep import ITEM_ORDERS, SCORERS, SolverConfig, solve
from core.validator import ALL_CHECKS, validate

app = FastAPI(
    title="LoadZa",
    version=__version__,
    summary="3D container loading: solve, audit and compare vehicle loads.",
)


def get_store() -> Store:
    store = Store(os.environ.get("LOADZA_DB", "data/loadza.sqlite"))
    store.initialise()
    return store


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/catalog")
def read_catalog() -> dict[str, list[dict[str, Any]]]:
    """Vehicles and unit-load types a client can build a job from.

    Without this a caller has to know the catalogue by heart, which pushed job
    creation out of the browser and into curl. The UI populates its dropdowns
    from here.
    """
    return {
        "vehicles": [vehicle_to_dict(v) for v in catalog.VEHICLES.values()],
        "item_types": [item_type_to_dict(t) for t in catalog.ITEM_TYPES.values()],
    }


@app.get("/jobs", response_model=list[JobSummary])
def list_jobs(store: Store = Depends(get_store)) -> list[dict]:
    return store.list_jobs()


@app.post("/jobs", status_code=201, response_model=JobSummary)
def create_job(document: dict[str, Any], store: Store = Depends(get_store)) -> dict:
    try:
        job = job_from_dict(document)
    except (KeyError, ValueError, TypeError) as error:
        raise HTTPException(422, f"malformed job: {error}") from error

    store.save_job(job, note=document.get("note"))
    return {
        "job_id": job.job_id,
        "vehicle_code": job.vehicle.code,
        "items": len(job.items),
        "created_at": next(
            row["created_at"] for row in store.list_jobs() if row["job_id"] == job.job_id
        ),
        "note": document.get("note"),
    }


@app.get("/jobs/{job_id}")
def read_job(job_id: str, store: Store = Depends(get_store)) -> dict:
    try:
        return job_to_dict(store.load_job(job_id))
    except NotFound as error:
        raise HTTPException(404, str(error)) from error


@app.post("/jobs/{job_id}/solve", response_model=PlanSummary)
def solve_job(
    job_id: str, request: SolveRequest, store: Store = Depends(get_store)
) -> dict:
    """Solve, audit, store, and return the plan's metrics.

    The stored plan always carries the validator's verdict. A plan in the
    database without violation counts would be one nobody had checked.
    """
    if request.item_order not in ITEM_ORDERS:
        raise HTTPException(422, f"unknown item order {request.item_order!r}")
    if request.scorer not in SCORERS:
        raise HTTPException(422, f"unknown scorer {request.scorer!r}")

    try:
        job = store.load_job(job_id)
    except NotFound as error:
        raise HTTPException(404, str(error)) from error

    config = SolverConfig(
        item_order=request.item_order,
        scorer=request.scorer,
        search=request.search,
        enforce_support=request.enforce_support,
        enforce_stacking=request.enforce_stacking,
        enforce_lifo=request.enforce_lifo,
        rebalance=request.rebalance,
        balance_lateral=request.balance_lateral,
    )

    if request.anneal_seconds:
        plan = improve(
            job,
            AnnealConfig(
                iterations=1_000_000,
                time_budget_s=request.anneal_seconds,
                solver=config,
            ),
        ).plan
    else:
        plan = solve(job, config)

    report = validate(job, plan)
    if plan.metrics is not None:
        plan = replace(plan, metrics=replace(plan.metrics, violations=report.counts))
    store.save_plan(plan)

    summary = {"plan_id": plan.plan_id, "job_id": plan.job_id,
               "algorithm": plan.algorithm, "violations": report.counts}
    if plan.metrics is not None:
        summary |= {
            "volume_utilization": plan.metrics.volume_utilization,
            "weight_utilization": plan.metrics.weight_utilization,
            "placed": plan.metrics.placed,
            "unplaced": plan.metrics.unplaced,
            "cog_lateral_mm": plan.metrics.cog_lateral_mm,
            "cog_longitudinal_mm": plan.metrics.cog_longitudinal_mm,
            "solve_ms": plan.metrics.solve_ms,
        }
    return summary


@app.get("/jobs/{job_id}/plans", response_model=list[PlanSummary])
def compare_plans(job_id: str, store: Store = Depends(get_store)) -> list[dict]:
    """Every plan for a job, best utilisation first."""
    try:
        return store.plans_for(job_id)
    except NotFound as error:
        raise HTTPException(404, str(error)) from error


@app.get("/plans/{plan_id}")
def read_plan(plan_id: str, store: Store = Depends(get_store)) -> dict:
    """The full plan document, in the format the 3D viewer consumes."""
    try:
        return plan_to_dict(store.load_plan(plan_id))
    except NotFound as error:
        raise HTTPException(404, str(error)) from error


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _report(plan_id: str, store: Store, kind: str) -> Response:
    try:
        plan = store.load_plan(plan_id)
        job = store.load_job(plan.job_id)
    except NotFound as error:
        raise HTTPException(404, str(error)) from error

    try:
        from app.report import item_list_xlsx_bytes, loading_plan_pdf_bytes
    except ImportError as error:  # pragma: no cover - depends on the install
        raise HTTPException(
            501, "reporting needs the viz extra: pip install -e '.[viz]'"
        ) from error

    if kind == "pdf":
        payload, media, suffix = loading_plan_pdf_bytes(job, plan), "application/pdf", "pdf"
    else:
        payload, media, suffix = item_list_xlsx_bytes(job, plan), XLSX_MEDIA_TYPE, "xlsx"

    return Response(
        content=payload,
        media_type=media,
        headers={
            "content-disposition": f'attachment; filename="{plan.plan_id}.{suffix}"'
        },
    )


@app.get("/plans/{plan_id}/report.pdf")
def plan_report_pdf(plan_id: str, store: Store = Depends(get_store)) -> Response:
    """The printable loading plan: drawings, metrics and the pick list."""
    return _report(plan_id, store, "pdf")


@app.get("/plans/{plan_id}/report.xlsx")
def plan_report_xlsx(plan_id: str, store: Store = Depends(get_store)) -> Response:
    """The same pick list as a spreadsheet, with a summary sheet."""
    return _report(plan_id, store, "xlsx")


@app.post("/validate", response_model=ValidationResponse)
def validate_plan(request: ValidationRequest) -> ValidationResponse:
    """Audit any plan against any job. Nothing is stored and nothing is trusted.

    The plan does not have to have come from this service. Checking a plan
    produced elsewhere -- or typed in by hand to prove the checker fires -- is
    the reason this endpoint exists.
    """
    try:
        job = job_from_dict(request.job)
        plan = plan_from_dict(request.plan)
    except (KeyError, ValueError, TypeError) as error:
        raise HTTPException(422, f"malformed document: {error}") from error

    checks = tuple(request.checks) if request.checks else ALL_CHECKS
    try:
        report = validate(job, plan, checks=checks)
    except KeyError as error:
        raise HTTPException(422, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error

    return ValidationResponse(
        valid=report.is_valid,
        counts=report.counts,
        violations=[
            ViolationOut(
                constraint=v.constraint, detail=v.detail, item_uids=list(v.item_uids)
            )
            for v in report.violations
        ],
    )


@app.exception_handler(NotFound)
def _not_found(_request, error: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})
