"""Spread a job that does not fit one vehicle across several.

The single-vehicle solver answers "what fits here". This answers "how many
vehicles, and which cargo in each", which is the question a dispatcher actually
has when the order is bigger than a trailer.

The approach is deliberately plain: fill a vehicle with the ordinary solver,
take what it left behind, and start the next one. That is a greedy
next-fit-decreasing over vehicles, and it is not optimal -- a better split
exists for most jobs. It has two properties that matter more here than
optimality:

* **Every load it produces is a real load.** Each is a full solve, so it obeys
  the same constraints and passes the same validator. A cleverer split that
  reasoned about volumes without packing would produce numbers nobody could
  load.
* **It cannot loop.** A vehicle that places nothing ends the process rather
  than being handed the same impossible cargo forever.

Vehicle choice, when several types are offered, is by the **volume actually
loaded**, not by utilisation. Utilisation is a ratio, and a ratio always
flatters the smallest vehicle: given a 20 ft container and a 13.6 m trailer,
picking the better percentage fills the container to 75% and sends three of
them, where the trailer would have taken the lot in one. Fewer vehicles is what
the dispatcher is paying for.

With four vehicle types and a handful of trips that is a few dozen solves,
which is affordable; it would not be for a hundred.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from core.models import Gram, Item, Job, Plan, Vehicle
from core.solver_ep import SolverConfig, solve


@dataclass(frozen=True, slots=True)
class Trip:
    """One vehicle and the plan for it."""

    index: int
    vehicle: Vehicle
    plan: Plan

    @property
    def volume_utilization(self) -> float:
        return self.plan.metrics.volume_utilization if self.plan.metrics else 0.0


@dataclass(frozen=True, slots=True)
class FleetPlan:
    job_id: str
    trips: tuple[Trip, ...]
    #: Items no vehicle in the fleet could take, with the reason from the last
    #: attempt. Non-empty means the fleet cannot carry this job at all.
    stranded: tuple[Item, ...]
    solve_ms: int

    @property
    def vehicles_used(self) -> int:
        return len(self.trips)

    @property
    def mean_utilization(self) -> float:
        if not self.trips:
            return 0.0
        return sum(t.volume_utilization for t in self.trips) / len(self.trips)

    @property
    def placed(self) -> int:
        return sum(len(t.plan.placements) for t in self.trips)


def _sub_job(job: Job, vehicle: Vehicle, items: tuple[Item, ...], index: int) -> Job:
    return Job(job_id=f"{job.job_id}-t{index}", vehicle=vehicle, items=items)


def _total_weight(items: tuple[Item, ...]) -> Gram:
    return sum(item.weight_g for item in items)


def assign(
    job: Job,
    fleet: tuple[Vehicle, ...] | None = None,
    config: SolverConfig | None = None,
    max_trips: int = 20,
) -> FleetPlan:
    """Split ``job`` across vehicles until the cargo runs out.

    ``fleet`` lists the vehicle types available; the job's own vehicle is used
    when it is omitted. Vehicles are unlimited in number, not in type -- this
    plans trips, it does not allocate a physical yard.
    """
    config = config or SolverConfig()
    # `or` would treat an explicitly empty fleet as "not given" and quietly
    # fall back to the job's own vehicle, which is not what the caller asked
    # for. None means "use the job's vehicle"; () is a mistake worth reporting.
    if fleet is None:
        fleet = (job.vehicle,)
    if not fleet:
        raise ValueError("the fleet is empty")
    if max_trips < 1:
        raise ValueError("max_trips must be at least 1")

    started = perf_counter()
    remaining = tuple(job.items)
    trips: list[Trip] = []

    while remaining and len(trips) < max_trips:
        index = len(trips) + 1
        best: tuple[Plan, Vehicle] | None = None
        best_volume = -1

        for vehicle in fleet:
            # Skip a vehicle that cannot carry even the lightest item left;
            # solving it would return an empty plan and waste the attempt.
            if all(item.weight_g > vehicle.max_payload_g for item in remaining):
                continue
            candidate = solve(_sub_job(job, vehicle, remaining, index), config)
            if not candidate.placements:
                continue
            loaded_volume = sum(p.dims.volume for p in candidate.placements)
            if loaded_volume > best_volume:
                best_volume = loaded_volume
                best = (candidate, vehicle)

        if best is None:
            # Nothing in the fleet can take any of what is left.
            break

        plan, vehicle = best
        trips.append(Trip(index=index, vehicle=vehicle, plan=plan))

        loaded = {p.item_uid for p in plan.placements}
        remaining = tuple(item for item in remaining if item.uid not in loaded)

    return FleetPlan(
        job_id=job.job_id,
        trips=tuple(trips),
        stranded=remaining,
        solve_ms=int((perf_counter() - started) * 1000),
    )


def summarise(fleet_plan: FleetPlan, job: Job) -> str:
    """One line per trip, for a CLI or a log."""
    lines = [
        f"{'trip':<6}{'vehicle':<12}{'boxes':>7}{'volume':>9}{'payload':>9}{'weight':>10}"
    ]
    weights = {item.uid: item.weight_g for item in job.items}
    for trip in fleet_plan.trips:
        metrics = trip.plan.metrics
        carried = sum(weights[p.item_uid] for p in trip.plan.placements)
        lines.append(
            f"{trip.index:<6}{trip.vehicle.code:<12}"
            f"{len(trip.plan.placements):>7}"
            f"{metrics.volume_utilization:>9.1%}"
            f"{metrics.weight_utilization:>9.1%}"
            f"{carried / 1e6:>9.2f}t"
        )
    lines.append(
        f"{'total':<6}{fleet_plan.vehicles_used:<12}"
        f"{fleet_plan.placed:>7}{fleet_plan.mean_utilization:>9.1%}"
        f"{'':>9}{_total_weight(tuple(job.items)) / 1e6:>9.2f}t"
    )
    if fleet_plan.stranded:
        lines.append(f"stranded: {len(fleet_plan.stranded)} items no vehicle could take")
    return "\n".join(lines)
