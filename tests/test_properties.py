"""Property-based tests: the solver must never emit an invalid plan.

The example-based tests cover jobs someone thought of. Hypothesis covers the
ones nobody did -- boxes taller than they are wide, a single item that fills the
container, twenty copies of a sliver. Any counterexample it finds is shrunk to
a minimal failing job and printed, which is worth far more than the assertion
itself.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core import catalog
from core.models import Dims, Item, ItemType, Job
from core.solver_ep import SolverConfig, solve
from core.validator import validate

#: Constraints F1 is responsible for. K5, K7 and K8 arrive in F4.
F1_CHECKS = ("K1", "K2", "K3", "K4", "K6")


@st.composite
def small_jobs(draw: st.DrawFn) -> Job:
    vehicle = catalog.vehicle(
        draw(st.sampled_from(["CNT-20DV", "CNT-40DV", "TIR-1360"]))
    )
    types = []
    for i in range(draw(st.integers(min_value=1, max_value=4))):
        types.append(
            ItemType(
                sku=f"T{i}",
                name=f"T{i}",
                dims=Dims(
                    l=draw(st.integers(min_value=100, max_value=2400)),
                    w=draw(st.integers(min_value=100, max_value=2400)),
                    h=draw(st.integers(min_value=100, max_value=2400)),
                ),
                weight_g=draw(st.integers(min_value=1_000, max_value=900_000)),
                this_side_up=draw(st.booleans()),
            )
        )

    items = []
    uid = 0
    for item_type in types:
        for _ in range(draw(st.integers(min_value=1, max_value=10))):
            items.append(Item(uid=uid, type=item_type))
            uid += 1

    return Job(job_id="hypothesis", vehicle=vehicle, items=tuple(items))


@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(job=small_jobs())
def test_solver_never_violates_its_own_constraints(job: Job):
    report = validate(job, solve(job), checks=F1_CHECKS)
    assert report.is_valid, f"{report.summary()} :: {report.violations[:3]}"


@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(job=small_jobs())
def test_every_item_is_either_placed_or_explained(job: Job):
    plan = solve(job)
    placed = {p.item_uid for p in plan.placements}
    missed = {u.item_uid for u in plan.unplaced}
    assert placed.isdisjoint(missed)
    assert placed | missed == {item.uid for item in job.items}


@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(job=small_jobs())
def test_loading_sequence_never_doubles_back(job: Job):
    plan = solve(job)
    xs = [p.pos.x for p in plan.placements]
    assert xs == sorted(xs)
    assert [p.seq for p in plan.placements] == list(range(1, len(xs) + 1))


@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(job=small_jobs())
def test_disabling_support_still_produces_a_collision_free_plan(job: Job):
    plan = solve(job, SolverConfig(enforce_support=False))
    report = validate(job, plan, checks=("K1", "K2", "K3", "K6"))
    assert report.is_valid, report.summary()
