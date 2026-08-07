"""Command line solver.

    python -m tools.solve data/demo/TIR-1360-mixed-s42.json
    python -m tools.solve <job.json> --scorer contact --search best_fit --out plan.json

Prints a one-screen summary and writes the plan JSON that the viewer (F7) and
the report generator (F8) consume.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.io import load_job, save_plan
from core.solver_ep import ITEM_ORDERS, SCORERS, SolverConfig, solve
from core.models import Job, Plan


def summarise(job: Job, plan: Plan) -> str:
    m = plan.metrics
    assert m is not None
    lines = [
        f"job        {job.job_id}  ({job.vehicle.code}, {len(job.items)} items)",
        f"algorithm  {plan.algorithm}",
        f"placed     {m.placed} / {len(job.items)}",
        f"volume     {m.volume_utilization:6.1%} of {job.vehicle.inner.volume / 1e9:.1f} m3",
        f"payload    {m.weight_utilization:6.1%} of {job.vehicle.max_payload_g / 1e6:.1f} t",
        f"cog offset {m.cog_longitudinal_mm:+d} mm lengthwise, "
        f"{m.cog_lateral_mm:+d} mm sideways",
        f"time       {m.solve_ms} ms",
    ]
    if plan.unplaced:
        reasons: dict[str, int] = {}
        for u in plan.unplaced:
            reasons[u.reason] = reasons.get(u.reason, 0) + 1
        detail = ", ".join(f"{count} {reason}" for reason, count in sorted(reasons.items()))
        lines.append(f"unplaced   {len(plan.unplaced)} ({detail})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve a LoadZa job")
    parser.add_argument("job", type=Path, help="path to a job JSON file")
    parser.add_argument("--item-order", default="volume_desc", choices=sorted(ITEM_ORDERS))
    parser.add_argument("--scorer", default="dbl", choices=sorted(SCORERS))
    parser.add_argument("--search", default="first_fit", choices=["first_fit", "best_fit"])
    parser.add_argument("--no-support", action="store_true",
                        help="disable the K4 support check (for comparison runs)")
    parser.add_argument("--max-points", type=int, default=400)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    job = load_job(args.job)
    config = SolverConfig(
        item_order=args.item_order,
        scorer=args.scorer,
        search=args.search,
        enforce_support=not args.no_support,
        max_points=args.max_points,
    )
    plan = solve(job, config)

    print(summarise(job, plan))
    out = args.out or Path("data/plans") / f"{plan.plan_id}.json"
    save_plan(plan, out)
    print(f"written to {out}")


if __name__ == "__main__":
    main()
