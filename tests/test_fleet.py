"""Splitting a job across vehicles."""

from __future__ import annotations

import pytest

from core import catalog
from core.fleet import assign, summarise
from core.models import Dims, Item, ItemType, Job
from core.solver_ep import SolverConfig
from core.validator import validate
from tools.gen_demo import generate


def oversized_job(fill: float = 3.0, seed: int = 55) -> Job:
    return generate(vehicle_code="CNT-20DV", mix="mixed", fill=fill, stops=2, seed=seed)


def test_a_job_that_fits_uses_one_vehicle():
    job = generate(vehicle_code="TIR-1360", mix="cartons", fill=0.25, seed=8)
    result = assign(job)
    assert result.vehicles_used == 1
    assert result.stranded == ()
    assert result.placed == len(job.items)


def test_an_oversized_job_is_split_and_nothing_is_lost():
    job = oversized_job()
    result = assign(job)

    assert result.vehicles_used > 1
    carried = [p.item_uid for trip in result.trips for p in trip.plan.placements]
    stranded = [item.uid for item in result.stranded]
    assert len(carried) == len(set(carried)), "an item was loaded onto two vehicles"
    assert set(carried) | set(stranded) == {item.uid for item in job.items}


def test_every_trip_is_a_legal_load():
    """Each trip is a real solve, so it answers to the same validator."""
    job = oversized_job()
    result = assign(job)
    for trip in result.trips:
        loaded = {p.item_uid for p in trip.plan.placements}
        sub_job = Job(
            job_id=trip.plan.job_id,
            vehicle=trip.vehicle,
            items=tuple(item for item in job.items if item.uid in loaded),
        )
        report = validate(sub_job, trip.plan, checks=("K1", "K2", "K3", "K4", "K6"))
        assert report.is_valid, f"trip {trip.index}: {report.summary()}"


def test_bigger_vehicles_are_preferred_over_better_percentages():
    """Utilisation is a ratio and a ratio flatters the smallest vehicle.

    Choosing by percentage packs a small container to a high number and sends
    several; choosing by volume loaded sends fewer vehicles, which is what is
    being paid for.
    """
    job = oversized_job()
    fleet = tuple(catalog.vehicle(code) for code in ("CNT-20DV", "CNT-40HC", "TIR-1360"))
    result = assign(job, fleet=fleet)

    assert result.trips[0].vehicle.code != "CNT-20DV"
    only_small = assign(job, fleet=(catalog.vehicle("CNT-20DV"),))
    assert result.vehicles_used < only_small.vehicles_used


def test_max_trips_is_a_hard_stop():
    job = oversized_job(fill=6.0)
    result = assign(job, max_trips=2)
    assert result.vehicles_used == 2
    assert result.stranded, "cargo beyond the trip limit has to be reported"


def test_cargo_no_vehicle_can_take_is_stranded_not_looped():
    """A vehicle that places nothing must end the run, not be retried."""
    huge = ItemType(sku="HUGE", name="huge", dims=Dims(9000, 9000, 9000), weight_g=1000)
    small = ItemType(sku="SMALL", name="small", dims=Dims(400, 300, 300), weight_g=7000)
    job = Job(
        job_id="mixed-feasibility",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=huge), *(Item(uid=i, type=small) for i in range(1, 5))),
    )
    result = assign(job)
    assert result.vehicles_used == 1
    assert [item.uid for item in result.stranded] == [0]


def test_an_impossible_job_strands_everything_without_a_trip():
    huge = ItemType(sku="HUGE", name="huge", dims=Dims(9000, 9000, 9000), weight_g=1000)
    job = Job(
        job_id="impossible",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=huge),),
    )
    result = assign(job)
    assert result.trips == ()
    assert len(result.stranded) == 1
    assert result.mean_utilization == 0.0


def test_configuration_is_passed_through_to_each_solve():
    job = oversized_job()
    result = assign(job, config=SolverConfig(scorer="dbl"))
    assert all("dbl" in trip.plan.algorithm for trip in result.trips)


def test_empty_fleet_and_silly_limits_are_rejected():
    job = oversized_job()
    with pytest.raises(ValueError):
        assign(job, fleet=())
    with pytest.raises(ValueError):
        assign(job, max_trips=0)


def test_summary_has_a_line_per_trip():
    job = oversized_job()
    result = assign(job)
    lines = summarise(result, job).splitlines()
    assert len(lines) >= result.vehicles_used + 2  # header + trips + total
    assert lines[-1].startswith("total") or "stranded" in lines[-1]
