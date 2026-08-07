"""Solver behaviour.

These checks are deliberately written against the plan, not against the
solver's internals: they re-derive overlap, containment, payload and support
from the placements alone. That is the same stance ``core.validator`` will take
in F2, and it is the only way a test can catch a solver that lies.
"""

from __future__ import annotations

import pytest

from core import catalog
from core.geometry import make_box, overlaps
from core.models import Dims, Item, ItemType, Job, Plan
from core.solver_ep import SolverConfig, solve
from tools.gen_demo import generate


def boxes_of(plan: Plan):
    return [make_box(p.pos, p.dims) for p in plan.placements]


def assert_physically_sane(job: Job, plan: Plan) -> None:
    boxes = boxes_of(plan)
    inner = job.vehicle.inner

    for i, a in enumerate(boxes):
        assert a[0] >= 0 and a[1] >= 0 and a[2] >= 0, "box starts outside the vehicle"
        assert a[3] <= inner.l and a[4] <= inner.w and a[5] <= inner.h, "box pokes out"
        for b in boxes[i + 1:]:
            assert not overlaps(a, b), f"overlap between {a} and {b}"

    weights = {item.uid: item.weight_g for item in job.items}
    total = sum(weights[p.item_uid] for p in plan.placements)
    assert total <= job.vehicle.max_payload_g

    placed_uids = {p.item_uid for p in plan.placements}
    missed_uids = {u.item_uid for u in plan.unplaced}
    assert placed_uids.isdisjoint(missed_uids)
    assert len(placed_uids) + len(missed_uids) == len(job.items), "an item vanished"


def assert_nothing_floats(job: Job, plan: Plan) -> None:
    """Every box rests on the floor or on the top face of boxes below it."""
    boxes = boxes_of(plan)
    for a in boxes:
        if a[2] == 0:
            continue
        footprint = (a[3] - a[0]) * (a[4] - a[1])
        supported = 0
        for b in boxes:
            if b[5] != a[2]:
                continue
            dx = min(a[3], b[3]) - max(a[0], b[0])
            dy = min(a[4], b[4]) - max(a[1], b[1])
            if dx > 0 and dy > 0:
                supported += dx * dy
        ratio = supported / footprint
        assert ratio >= job.vehicle.min_support_ratio - 1e-9, (
            f"box at {a} only {ratio:.0%} supported"
        )


@pytest.mark.parametrize(
    "vehicle_code,mix,fill,seed",
    [
        ("TIR-1360", "mixed", 1.05, 42),
        ("CNT-20DV", "cartons", 0.90, 13),
        ("CNT-40HC", "pallets", 1.10, 7),
    ],
)
def test_demo_jobs_produce_sane_plans(vehicle_code, mix, fill, seed):
    job = generate(vehicle_code=vehicle_code, mix=mix, fill=fill, seed=seed)
    plan = solve(job)
    assert_physically_sane(job, plan)
    assert_nothing_floats(job, plan)
    assert plan.metrics is not None
    assert plan.metrics.placed > 0


def test_support_can_be_switched_off_for_comparison_runs():
    job = generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.9, seed=13)
    plan = solve(job, SolverConfig(enforce_support=False))
    assert_physically_sane(job, plan)


def test_solver_is_deterministic():
    job = generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.8, seed=5)
    a = solve(job)
    b = solve(job)
    assert a.placements == b.placements
    assert a.unplaced == b.unplaced


def test_loading_sequence_runs_from_the_deep_end_outwards():
    job = generate(vehicle_code="CNT-40DV", mix="cartons", fill=0.7, seed=21)
    plan = solve(job)
    seqs = [p.seq for p in plan.placements]
    assert seqs == list(range(1, len(seqs) + 1))
    xs = [p.pos.x for p in plan.placements]
    assert xs == sorted(xs), "sequence must not jump back towards the doors"


def single_box_job() -> Job:
    box_type = ItemType(
        sku="ONE", name="one", dims=Dims(1000, 900, 800), weight_g=10_000
    )
    return Job(
        job_id="single",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=box_type),),
    )


def test_a_single_box_packs_into_the_deep_left_bottom_corner():
    plan = solve(single_box_job(), SolverConfig(rebalance=False))
    assert len(plan.placements) == 1
    placement = plan.placements[0]
    assert (placement.pos.x, placement.pos.y, placement.pos.z) == (0, 0, 0)


def test_rebalancing_slides_a_single_box_to_the_middle_of_the_floor():
    """The corner is where packing starts, not where the load should sit."""
    job = single_box_job()
    placement = solve(job).placements[0]
    inner = job.vehicle.inner

    assert placement.pos.z == 0, "sliding must not lift anything off the floor"
    assert abs((placement.pos.x + placement.dims.l / 2) - inner.l / 2) <= 1
    assert abs((placement.pos.y + placement.dims.w / 2) - inner.w / 2) <= 1


def test_oversized_item_is_reported_not_dropped():
    huge = ItemType(sku="HUGE", name="huge", dims=Dims(9000, 9000, 9000), weight_g=1000)
    job = Job(
        job_id="huge",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=huge),),
    )
    plan = solve(job)
    assert plan.placements == ()
    assert [u.reason for u in plan.unplaced] == ["no_fit"]


def test_payload_limit_is_respected_and_reported():
    heavy = ItemType(
        sku="HEAVY", name="heavy", dims=Dims(1000, 1000, 1000), weight_g=20_000_000
    )
    job = Job(
        job_id="heavy",
        vehicle=catalog.vehicle("CNT-20DV"),  # 28.23 t payload
        items=tuple(Item(uid=i, type=heavy) for i in range(3)),
    )
    plan = solve(job)
    assert len(plan.placements) == 1
    assert [u.reason for u in plan.unplaced] == ["payload", "payload"]


def test_this_side_up_items_keep_their_height_axis():
    job = generate(vehicle_code="TIR-1360", mix="pallets", fill=0.5, seed=99)
    plan = solve(job)
    for placement in plan.placements:
        item_type = catalog.item_type(placement.sku)
        if item_type.this_side_up:
            assert placement.dims.h == item_type.dims.h


@pytest.mark.parametrize("scorer", ["dbl", "layer", "contact"])
def test_every_scorer_produces_a_valid_plan(scorer):
    job = generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.6, seed=31)
    search = "best_fit" if scorer == "contact" else "first_fit"
    plan = solve(job, SolverConfig(scorer=scorer, search=search))
    assert_physically_sane(job, plan)
    assert_nothing_floats(job, plan)


def test_unknown_config_values_fail_loudly():
    job = generate(fill=0.1, seed=1)
    with pytest.raises(KeyError):
        solve(job, SolverConfig(scorer="nope"))
    with pytest.raises(KeyError):
        solve(job, SolverConfig(item_order="nope"))
