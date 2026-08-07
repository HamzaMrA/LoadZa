"""Split a job across vehicles and write one plan per trip.

    python -m tools.fleet data/demo/big-job.json
    python -m tools.fleet <job> --fleet TIR-1360 CNT-40HC --outdir data/plans

The job's own vehicle is used unless --fleet names others.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core import catalog
from core.fleet import assign, summarise
from core.io import load_job, save_plan
from core.solver_ep import SCORERS, SolverConfig
from core.validator import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign a job to a fleet")
    parser.add_argument("job", type=Path)
    parser.add_argument(
        "--fleet", nargs="+", default=None, choices=sorted(catalog.VEHICLES)
    )
    parser.add_argument("--scorer", default=SolverConfig().scorer, choices=sorted(SCORERS))
    parser.add_argument("--max-trips", type=int, default=20)
    parser.add_argument("--outdir", type=Path, default=Path("data/plans"))
    args = parser.parse_args()

    job = load_job(args.job)
    fleet = tuple(catalog.vehicle(code) for code in args.fleet) if args.fleet else None
    result = assign(
        job, fleet=fleet, config=SolverConfig(scorer=args.scorer), max_trips=args.max_trips
    )

    print(f"job     {job.job_id}  ({len(job.items)} items)")
    print(f"time    {result.solve_ms} ms")
    print()
    print(summarise(result, job))
    print()

    invalid = 0
    for trip in result.trips:
        sub_job = job.__class__(
            job_id=trip.plan.job_id,
            vehicle=trip.vehicle,
            items=tuple(
                item
                for item in job.items
                if item.uid in {p.item_uid for p in trip.plan.placements}
            ),
        )
        report = validate(sub_job, trip.plan, checks=("K1", "K2", "K3", "K4", "K6"))
        if not report.is_valid:
            invalid += 1
            print(f"trip {trip.index}: {report.summary()}")
        path = save_plan(trip.plan, args.outdir / f"{trip.plan.plan_id}.json")
        print(f"trip {trip.index}  {path}")

    if invalid:
        print(f"WARNING: {invalid} trips failed validation")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
