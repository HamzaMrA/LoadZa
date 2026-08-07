"""The validator has to fail loads that are actually wrong.

Every constraint gets a hand-built plan that breaks it exactly once. A checker
that never fires is indistinguishable from a checker that is not wired up, so
these tests matter more than the happy path.
"""

from __future__ import annotations

import pytest

from core import catalog
from core.models import (
    Dims,
    Item,
    ItemType,
    Job,
    Orientation,
    Placement,
    Plan,
    Pos,
    Vehicle,
)
from core.solver_ep import SolverConfig, solve
from core.validator import validate
from tools.gen_demo import generate

SMALL = Vehicle(
    code="TEST",
    name="test box",
    inner=Dims(l=4000, w=2000, h=2000),
    max_payload_g=10_000_000,
)


def make_type(sku: str, dims: Dims, weight_g: int, **kwargs) -> ItemType:
    return ItemType(sku=sku, name=sku, dims=dims, weight_g=weight_g, **kwargs)


def make_job(types_and_counts, vehicle: Vehicle = SMALL) -> Job:
    items = []
    uid = 0
    for item_type, count in types_and_counts:
        for _ in range(count):
            items.append(Item(uid=uid, type=item_type))
            uid += 1
    return Job(job_id="t", vehicle=vehicle, items=tuple(items))


def make_plan(job: Job, boxes) -> Plan:
    """boxes: iterable of (uid, sku, pos, dims, orientation[, stop])."""
    placements = []
    for seq, entry in enumerate(boxes, start=1):
        uid, sku, pos, dims, orientation, *rest = entry
        placements.append(
            Placement(
                seq=seq,
                item_uid=uid,
                sku=sku,
                pos=pos,
                dims=dims,
                orientation=orientation,
                stop=rest[0] if rest else 1,
            )
        )
    return Plan(
        plan_id="t-plan",
        job_id=job.job_id,
        vehicle=job.vehicle,
        algorithm="handmade",
        placements=tuple(placements),
    )


def test_a_clean_plan_reports_nothing():
    # Four boxes arranged symmetrically about the middle of a 4000x2000 floor,
    # so the centre of gravity lands dead centre and K7 has nothing to say.
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 4)])
    plan = make_plan(job, [
        (0, "A", Pos(1000, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (1, "A", Pos(2000, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (2, "A", Pos(1000, 1000, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (3, "A", Pos(2000, 1000, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    report = validate(job, plan)
    assert report.is_valid, report.summary()


def test_k1_catches_interpenetration():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (1, "A", Pos(900, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    assert len(validate(job, plan).of("K1")) == 1


def test_k1_allows_flush_faces():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (1, "A", Pos(0, 1000, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    assert validate(job, plan).of("K1") == ()


def test_k2_catches_a_box_through_the_roof():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 1500), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    assert len(validate(job, plan).of("K2")) == 1


def test_k3_catches_an_overloaded_vehicle():
    t = make_type("HEAVY", Dims(1000, 1000, 1000), 6_000_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "HEAVY", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (1, "HEAVY", Pos(1000, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    assert len(validate(job, plan).of("K3")) == 1


def test_k4_catches_a_floating_box():
    t = make_type("A", Dims(1000, 1000, 500), 100_000)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 900), Dims(1000, 1000, 500), Orientation.LWH),
    ])
    assert len(validate(job, plan).of("K4")) == 1


def test_k4_catches_a_box_hanging_off_the_edge():
    t = make_type("A", Dims(1000, 1000, 500), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 500), Orientation.LWH),
        # Only 20% of the upper box rests on the lower one.
        (1, "A", Pos(800, 0, 500), Dims(1000, 1000, 500), Orientation.LWH),
    ])
    assert len(validate(job, plan).of("K4")) == 1


def test_k5_catches_a_crushed_box():
    fragile = make_type("GLASS", Dims(1000, 1000, 500), 50_000, max_stack_weight_g=0)
    heavy = make_type("ANVIL", Dims(1000, 1000, 500), 900_000)
    job = make_job([(fragile, 1), (heavy, 1)])
    plan = make_plan(job, [
        (0, "GLASS", Pos(0, 0, 0), Dims(1000, 1000, 500), Orientation.LWH),
        (1, "ANVIL", Pos(0, 0, 500), Dims(1000, 1000, 500), Orientation.LWH),
    ])
    violations = validate(job, plan).of("K5")
    assert len(violations) == 1
    assert violations[0].item_uids == (0,)


def test_k5_splits_load_between_two_supporters():
    base = make_type("BASE", Dims(1000, 1000, 500), 50_000, max_stack_weight_g=400_000)
    top = make_type("TOP", Dims(2000, 1000, 500), 600_000)
    job = make_job([(base, 2), (top, 1)])
    plan = make_plan(job, [
        (0, "BASE", Pos(0, 0, 0), Dims(1000, 1000, 500), Orientation.LWH),
        (1, "BASE", Pos(1000, 0, 0), Dims(1000, 1000, 500), Orientation.LWH),
        (2, "TOP", Pos(0, 0, 500), Dims(2000, 1000, 500), Orientation.LWH),
    ])
    # 600 kg split evenly is 300 kg each, under the 400 kg rating.
    assert validate(job, plan).of("K5") == ()


def test_k5_stacks_load_through_a_tower():
    base = make_type("BASE", Dims(1000, 1000, 500), 50_000, max_stack_weight_g=700_000)
    mid = make_type("MID", Dims(1000, 1000, 500), 400_000, max_stack_weight_g=700_000)
    job = make_job([(base, 1), (mid, 2)])
    plan = make_plan(job, [
        (0, "BASE", Pos(0, 0, 0), Dims(1000, 1000, 500), Orientation.LWH),
        (1, "MID", Pos(0, 0, 500), Dims(1000, 1000, 500), Orientation.LWH),
        (2, "MID", Pos(0, 0, 1000), Dims(1000, 1000, 500), Orientation.LWH),
    ])
    # The base carries both boxes above it: 800 kg against a 700 kg rating.
    violations = validate(job, plan).of("K5")
    assert [v.item_uids for v in violations] == [(0,)]


def test_k6_catches_dimensions_that_contradict_the_orientation():
    t = make_type("A", Dims(1000, 800, 600), 100_000)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 800, 600), Orientation.WLH),
    ])
    assert len(validate(job, plan).of("K6")) == 1


def test_k6_catches_a_forbidden_orientation():
    t = make_type("A", Dims(1000, 800, 600), 100_000, this_side_up=True)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(600, 800, 1000), Orientation.HLW),
    ])
    assert len(validate(job, plan).of("K6")) == 1


def test_k7_catches_a_nose_heavy_load():
    light = make_type("LIGHT", Dims(500, 500, 500), 1_000)
    heavy = make_type("HEAVY", Dims(500, 500, 500), 1_000_000)
    job = make_job([(heavy, 1), (light, 1)])
    plan = make_plan(job, [
        (0, "HEAVY", Pos(0, 750, 0), Dims(500, 500, 500), Orientation.LWH),
        (1, "LIGHT", Pos(3500, 750, 0), Dims(500, 500, 500), Orientation.LWH),
    ])
    violations = validate(job, plan).of("K7")
    assert any("lengthwise" in v.detail for v in violations)


def test_k8_catches_a_buried_early_stop():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        # Stop 1 is deep in the trailer, stop 2 stands between it and the doors.
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH, 1),
        (1, "A", Pos(1000, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH, 2),
    ])
    assert len(validate(job, plan).of("K8")) == 1


def test_k8_accepts_the_correct_drop_order():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH, 2),
        (1, "A", Pos(1000, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH, 1),
    ])
    assert validate(job, plan).of("K8") == ()


def test_checks_can_be_narrowed():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 2)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
        (1, "A", Pos(900, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    report = validate(job, plan, checks=("K2", "K3"))
    assert report.is_valid
    assert set(report.counts) == {"K2", "K3"}


def test_mismatched_job_and_plan_are_rejected():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (0, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    other = Job(job_id="different", vehicle=SMALL, items=job.items)
    with pytest.raises(ValueError):
        validate(other, plan)


def test_placements_for_unknown_items_are_rejected():
    t = make_type("A", Dims(1000, 1000, 1000), 100_000)
    job = make_job([(t, 1)])
    plan = make_plan(job, [
        (99, "A", Pos(0, 0, 0), Dims(1000, 1000, 1000), Orientation.LWH),
    ])
    with pytest.raises(ValueError):
        validate(job, plan)


def test_unknown_check_names_are_rejected():
    job = make_job([(make_type("A", Dims(100, 100, 100), 1000), 1)])
    plan = make_plan(job, [])
    with pytest.raises(KeyError):
        validate(job, plan, checks=("K9",))


@pytest.mark.parametrize(
    "vehicle_code,mix,fill,seed",
    [
        ("CNT-20DV", "cartons", 0.90, 13),
        ("CNT-40HC", "pallets", 1.10, 7),
        ("TIR-1360", "mixed", 1.05, 42),
    ],
)
def test_solver_output_satisfies_the_constraints_it_claims(vehicle_code, mix, fill, seed):
    """F1 enforces K1-K4 and K6. K5, K7 and K8 are not its job yet."""
    job = generate(vehicle_code=vehicle_code, mix=mix, fill=fill, seed=seed)
    report = validate(job, solve(job), checks=("K1", "K2", "K3", "K4", "K6"))
    assert report.is_valid, report.summary()


@pytest.mark.parametrize(
    "vehicle_code,mix,fill,stops,seed",
    [
        ("CNT-40DV", "mixed", 0.85, 3, 77),
        ("TIR-1360", "mixed", 1.05, 1, 42),
        ("CNT-40HC", "pallets", 1.10, 2, 7),
    ],
)
def test_stacking_and_reach_are_enforced(vehicle_code, mix, fill, stops, seed):
    """K5 and K8 are solver constraints from F4 on, not just audit findings."""
    job = generate(vehicle_code=vehicle_code, mix=mix, fill=fill, stops=stops, seed=seed)
    report = validate(job, solve(job), checks=("K5", "K8"))
    assert report.is_valid, report.summary()


def test_enforcement_can_be_switched_off_and_the_violations_come_back():
    """Guards against the checks passing because nothing exercises them."""
    job = generate(vehicle_code="CNT-40DV", mix="mixed", fill=0.85, stops=3, seed=77)
    loose = SolverConfig(enforce_stacking=False, enforce_lifo=False)
    report = validate(job, solve(job, loose), checks=("K5", "K8"))
    assert report.counts["K5"] > 0
    assert report.counts["K8"] > 0


def test_lifo_costs_utilisation():
    """Reach is a real constraint, and real constraints are not free.

    Packing the last stop deepest forbids using a gap in the wrong region, so
    the plan holds fewer boxes. A version of this that cost nothing would mean
    the constraint was not being applied.
    """
    job = generate(vehicle_code="CNT-40DV", mix="mixed", fill=0.85, stops=3, seed=77)
    strict = solve(job).metrics.volume_utilization
    loose = solve(job, SolverConfig(enforce_lifo=False)).metrics.volume_utilization
    assert strict < loose


def test_longitudinal_balance_is_solved_but_lateral_is_not():
    """Sliding the load centres it lengthwise; sideways it cannot help.

    A block translated along the vehicle keeps every relative position, so the
    lengthwise centre of gravity can always be corrected while there is free
    length. Sideways there usually is none -- the load spans the full width --
    so the residual lean has to be fixed by choosing sides during packing, and
    a greedy rule does that badly. Hence balance_lateral defaults off and the
    job below still leans.
    """
    job = generate(vehicle_code="CNT-40HC", mix="pallets", fill=1.10, seed=7)
    plan = solve(job)
    vehicle = job.vehicle

    assert abs(plan.metrics.cog_longitudinal_mm) <= (
        vehicle.cog_long_tol_ratio * vehicle.inner.l
    )
    assert abs(plan.metrics.cog_lateral_mm) > vehicle.cog_lateral_tol_mm

    for violation in validate(job, plan, checks=("K7",)).violations:
        assert "sideways" in violation.detail
