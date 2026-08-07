"""F0 smoke tests: the domain model holds together and JSON round-trips."""

from __future__ import annotations

import pytest

from core import catalog
from core.io import job_from_dict, job_to_dict, plan_from_dict, plan_to_dict
from core.models import (
    ALL_ORIENTATIONS,
    UPRIGHT_ORIENTATIONS,
    Dims,
    ItemType,
    Metrics,
    Orientation,
    Placement,
    Plan,
    Pos,
    Unplaced,
    rotate,
)
from core.solver_ep import solve
from tools.gen_demo import generate


def test_rotate_preserves_volume_for_every_orientation():
    dims = Dims(l=1200, w=800, h=1450)
    for orientation in ALL_ORIENTATIONS:
        assert rotate(dims, orientation).volume == dims.volume


def test_rotate_produces_six_distinct_axis_assignments():
    dims = Dims(l=3, w=5, h=7)
    results = {rotate(dims, o) for o in ALL_ORIENTATIONS}
    assert len(results) == 6


def test_dims_reject_non_positive():
    with pytest.raises(ValueError):
        Dims(l=0, w=100, h=100)


def test_this_side_up_narrows_orientations():
    box = ItemType(
        sku="X", name="x", dims=Dims(600, 400, 400), weight_g=1000, this_side_up=True
    )
    assert box.allowed_orientations == UPRIGHT_ORIENTATIONS


def test_placement_max_corner():
    p = Placement(
        seq=1,
        item_uid=0,
        sku="X",
        pos=Pos(100, 200, 300),
        dims=Dims(1200, 800, 1450),
        orientation=Orientation.LWH,
    )
    corner = p.max_corner
    assert (corner.x, corner.y, corner.z) == (1300, 1000, 1750)


def test_catalogue_vehicles_are_loadable():
    for code in catalog.VEHICLES:
        v = catalog.vehicle(code)
        assert v.inner.volume > 0
        assert v.max_payload_g > 0


def test_unknown_catalogue_entries_raise():
    with pytest.raises(KeyError):
        catalog.vehicle("NOPE")
    with pytest.raises(KeyError):
        catalog.item_type("NOPE")


def test_generated_job_is_deterministic():
    a = generate(seed=7)
    b = generate(seed=7)
    assert [i.sku for i in a.items] == [i.sku for i in b.items]
    assert a.total_weight_g == b.total_weight_g


def test_generated_job_respects_payload_cap():
    job = generate(vehicle_code="CNT-20DV", mix="pallets", fill=2.0, seed=3)
    assert job.total_weight_g <= job.vehicle.max_payload_g


def test_job_json_round_trip():
    job = generate(vehicle_code="CNT-40HC", mix="mixed", fill=0.6, stops=3, seed=11)
    restored = job_from_dict(job_to_dict(job))

    assert restored.job_id == job.job_id
    assert restored.vehicle == job.vehicle
    assert len(restored.items) == len(job.items)
    assert restored.total_volume == job.total_volume
    # Item order is regrouped by (sku, stop) on the way out, so compare as bags.
    assert sorted((i.sku, i.stop) for i in restored.items) == sorted(
        (i.sku, i.stop) for i in job.items
    )


def test_job_round_trip_preserves_item_uids():
    """Placements refer to items by uid, so renumbering would silently retarget
    a plan at different boxes."""
    job = generate(vehicle_code="CNT-20DV", mix="mixed", fill=0.4, stops=2, seed=4)
    restored = job_from_dict(job_to_dict(job))
    assert {(i.uid, i.sku, i.stop) for i in restored.items} == {
        (i.uid, i.sku, i.stop) for i in job.items
    }


def test_job_documents_without_uids_still_load():
    """Hand-written and benchmark-derived files legitimately omit them."""
    document = {
        "job_id": "manual",
        "vehicle": {"code": "CNT-20DV"},
        "items": [{"sku": "BOX-M", "qty": 3}, {"sku": "BOX-S", "qty": 2}],
    }
    job = job_from_dict(document)
    assert [i.uid for i in job.items] == [0, 1, 2, 3, 4]


def test_conflicting_uids_are_rejected():
    document = {
        "job_id": "clash",
        "vehicle": {"code": "CNT-20DV"},
        "items": [
            {"sku": "BOX-M", "qty": 2, "uids": [0, 1]},
            {"sku": "BOX-S", "qty": 2, "uids": [1, 2]},
        ],
    }
    with pytest.raises(ValueError, match="duplicate"):
        job_from_dict(document)


def test_uid_count_must_match_quantity():
    document = {
        "job_id": "short",
        "vehicle": {"code": "CNT-20DV"},
        "items": [{"sku": "BOX-M", "qty": 5, "uids": [0, 1]}],
    }
    with pytest.raises(ValueError, match="uids"):
        job_from_dict(document)


def test_plan_json_round_trip():
    plan = Plan(
        plan_id="p1",
        job_id="j1",
        vehicle=catalog.vehicle("TIR-1360"),
        algorithm="test",
        placements=(
            Placement(
                seq=1,
                item_uid=0,
                sku="EUR-FULL",
                pos=Pos(0, 0, 0),
                dims=Dims(1200, 800, 1450),
                orientation=Orientation.LWH,
                stop=2,
            ),
        ),
        unplaced=(Unplaced(item_uid=1, sku="BOX-M", reason="volume"),),
        metrics=Metrics(
            volume_utilization=0.5,
            weight_utilization=0.4,
            placed=1,
            unplaced=1,
            cog_lateral_mm=12,
            cog_longitudinal_mm=-340,
            solve_ms=7,
            violations={"K1": 0, "K2": 0},
        ),
    )
    assert plan_from_dict(plan_to_dict(plan)) == plan


def test_metrics_is_valid_flag():
    clean = Metrics(0.9, 0.5, 10, 0, 0, 0, 5, {"K1": 0, "K4": 0})
    dirty = Metrics(0.9, 0.5, 10, 0, 0, 0, 5, {"K1": 0, "K4": 2})
    assert clean.is_valid and clean.checked
    assert not dirty.is_valid


def test_an_unchecked_plan_is_not_valid():
    """The solver leaves violations empty because it may not grade itself.

    Reading that as a clean bill of health is how an unaudited plan ships.
    """
    unchecked = Metrics(0.9, 0.5, 10, 0, 0, 0, 5)
    assert not unchecked.checked
    assert not unchecked.is_valid

    fresh = solve(generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.4, seed=1))
    assert not fresh.metrics.checked
