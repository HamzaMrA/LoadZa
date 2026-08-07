"""Request and response models for the HTTP layer.

Only the *control* messages are modelled here -- what to solve, how long to
search, what came back. Jobs and plans themselves travel in the JSON format
already defined by :mod:`core.io`, and are validated by that module rather than
duplicated as Pydantic classes.

That is a deliberate line. The wire format for a plan is a published contract
shared with the viewer and the benchmark files; re-declaring it in Pydantic
would mean two definitions to keep in step, and the one that drifts would be
the one nobody is testing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.solver_ep import ITEM_ORDERS, SCORERS

#: A search longer than this is a background job, not an HTTP request. Without
#: a cap a single call can hold a worker for as long as the caller likes.
MAX_ANNEAL_SECONDS = 60.0


class SolveRequest(BaseModel):
    item_order: str = Field(default="volume_desc", examples=sorted(ITEM_ORDERS))
    scorer: str = Field(default="layer", examples=sorted(SCORERS))
    search: str = Field(default="first_fit", pattern="^(first_fit|best_fit)$")
    enforce_support: bool = True
    enforce_stacking: bool = True
    enforce_lifo: bool = True
    rebalance: bool = True
    balance_lateral: bool = False
    anneal_seconds: float | None = Field(
        default=None, ge=0.0, le=MAX_ANNEAL_SECONDS,
        description="Search item orders for this long instead of solving once.",
    )


class JobSummary(BaseModel):
    job_id: str
    vehicle_code: str
    items: int
    created_at: str
    note: str | None = None


class PlanSummary(BaseModel):
    plan_id: str
    job_id: str | None = None
    algorithm: str
    created_at: str | None = None
    volume_utilization: float | None = None
    weight_utilization: float | None = None
    placed: int | None = None
    unplaced: int | None = None
    cog_lateral_mm: int | None = None
    cog_longitudinal_mm: int | None = None
    solve_ms: int | None = None
    violations: dict[str, int] = Field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Checked and clean. An unchecked plan is not valid -- see Metrics."""
        return bool(self.violations) and all(
            count == 0 for count in self.violations.values()
        )


class ValidationRequest(BaseModel):
    """A job and a plan to audit together.

    Both are raw core.io documents. The plan does not have to have come from
    this service -- checking someone else's plan is the point of the endpoint.
    """

    job: dict[str, Any]
    plan: dict[str, Any]
    checks: list[str] | None = None


class ViolationOut(BaseModel):
    constraint: str
    detail: str
    item_uids: list[int] = Field(default_factory=list)


class ValidationResponse(BaseModel):
    valid: bool
    counts: dict[str, int]
    violations: list[ViolationOut]
