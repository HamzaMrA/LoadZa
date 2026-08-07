"""The improvement pass.

The property that matters is not "it finds a better plan" -- some jobs have no
better plan to find. It is that the search can never *lose*, that its output is
still a legal load, and that it is reproducible.
"""

from __future__ import annotations

import pytest

from core import catalog
from core.improve_sa import AnnealConfig, improve, objective
from core.models import Dims, Item, ItemType, Job, Metrics, Plan
from core.solver_ep import SolverConfig, solve
from core.validator import validate
from tools.gen_demo import generate

FAST = AnnealConfig(iterations=25, seed=3)


def small_job() -> Job:
    return generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.6, seed=13)


def test_result_is_never_worse_than_the_constructive_plan():
    job = small_job()
    result = improve(job, FAST)
    assert result.best_score >= result.start_score
    assert result.gain >= 0


def test_result_is_still_a_legal_load():
    job = generate(vehicle_code="CNT-40DV", mix="mixed", fill=0.8, stops=3, seed=77)
    result = improve(job, AnnealConfig(iterations=15, seed=5))
    report = validate(job, result.plan, checks=("K1", "K2", "K3", "K4", "K5", "K6", "K8"))
    assert report.is_valid, report.summary()


def test_same_seed_gives_the_same_answer():
    job = small_job()
    a = improve(job, FAST)
    b = improve(job, FAST)
    assert a.best_score == b.best_score
    assert a.plan.placements == b.plan.placements


def test_zero_iterations_returns_the_constructive_plan():
    job = small_job()
    result = improve(job, AnnealConfig(iterations=0, seed=1))
    assert result.evaluations == 0
    assert result.best_score == result.start_score
    assert result.plan.placements == solve(job).placements


def test_time_budget_stops_the_search():
    job = small_job()
    result = improve(job, AnnealConfig(iterations=100_000, time_budget_s=0.5, seed=1))
    assert result.evaluations < 100_000
    assert result.elapsed_s < 5.0


def test_every_item_is_still_accounted_for():
    job = small_job()
    plan = improve(job, FAST).plan
    placed = {p.item_uid for p in plan.placements}
    missed = {u.item_uid for u in plan.unplaced}
    assert placed.isdisjoint(missed)
    assert placed | missed == {item.uid for item in job.items}


def test_plan_is_labelled_with_the_search_not_the_inner_pass():
    plan = improve(small_job(), FAST).plan
    assert plan.plan_id.endswith("-sa")
    assert plan.algorithm.startswith("SA(")


def test_sequence_order_is_honoured_by_the_solver():
    """The search would be pointless if the solver re-sorted its permutations."""
    job = small_job()
    forward = solve(job, SolverConfig(item_order="sequence"))
    reversed_job = Job(
        job_id=job.job_id, vehicle=job.vehicle, items=tuple(reversed(job.items))
    )
    backward = solve(reversed_job, SolverConfig(item_order="sequence"))
    assert forward.placements != backward.placements


def test_objective_ignores_balance_inside_tolerance():
    """A load centred to the millimetre is worth no more than one within spec."""
    job = small_job()
    vehicle = job.vehicle
    base = Metrics(
        volume_utilization=0.8, weight_utilization=0.5, placed=1, unplaced=0,
        cog_lateral_mm=0, cog_longitudinal_mm=0, solve_ms=1,
    )

    def scored(lateral: int) -> float:
        metrics = Metrics(
            volume_utilization=base.volume_utilization,
            weight_utilization=base.weight_utilization,
            placed=base.placed, unplaced=base.unplaced,
            cog_lateral_mm=lateral, cog_longitudinal_mm=0, solve_ms=1,
        )
        plan = Plan(
            plan_id="p", job_id=job.job_id, vehicle=vehicle,
            algorithm="t", placements=(), metrics=metrics,
        )
        return objective(job, plan)

    inside = vehicle.cog_lateral_tol_mm
    assert scored(0) == scored(inside)
    assert scored(inside + 500) < scored(inside)


def test_objective_of_a_plan_without_metrics_is_zero():
    job = small_job()
    plan = Plan(plan_id="p", job_id=job.job_id, vehicle=job.vehicle,
                algorithm="t", placements=())
    assert objective(job, plan) == 0.0


def test_unknown_item_order_fails_loudly():
    job = small_job()
    with pytest.raises(KeyError):
        improve(job, AnnealConfig(iterations=1, solver=SolverConfig(item_order="nope")))


def test_a_job_that_cannot_be_improved_still_returns_a_plan():
    box = ItemType(sku="ONE", name="one", dims=Dims(1000, 900, 800), weight_g=10_000)
    job = Job(
        job_id="single",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=box),),
    )
    result = improve(job, AnnealConfig(iterations=10, seed=2))
    assert len(result.plan.placements) == 1
    assert result.gain == 0
