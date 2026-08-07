"""Solve a job, then anneal the item order for a while and keep the best plan.

    python -m tools.improve data/demo/TIR-1360-mixed-s42.json --seconds 20

Prints what the search actually did -- how many plans it evaluated, how many it
accepted, and where the last improvement came from -- because a run that reports
only its final number cannot be told apart from one that never improved
anything.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from core.improve_sa import AnnealConfig, improve
from core.io import load_job, save_plan
from core.solver_ep import SCORERS, SolverConfig
from core.validator import validate


def main() -> None:
    parser = argparse.ArgumentParser(description="Improve a LoadZa plan")
    parser.add_argument("job", type=Path)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--scorer", default=SolverConfig().scorer, choices=sorted(SCORERS))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    job = load_job(args.job)
    result = improve(
        job,
        AnnealConfig(
            iterations=args.iterations,
            time_budget_s=args.seconds,
            seed=args.seed,
            solver=SolverConfig(scorer=args.scorer),
        ),
    )

    report = validate(job, result.plan)
    plan = result.plan
    if plan.metrics is not None:
        plan = replace(plan, metrics=replace(plan.metrics, violations=report.counts))

    # Score and utilisation are not the same number: the score subtracts a
    # penalty for a load whose balance is outside tolerance. Printing only one
    # of them invites reading a penalty as lost volume.
    print(f"job         {job.job_id}  ({job.vehicle.code}, {len(job.items)} items)")
    print(f"score       {result.start_score:.2%} -> {result.best_score:.2%}"
          f"   ({result.gain:+.2%})")
    if plan.metrics is not None:
        print(f"volume      {plan.metrics.volume_utilization:.2%}"
              f"   payload {plan.metrics.weight_utilization:.2%}")
    print(f"evaluated   {result.evaluations} plans in {result.elapsed_s:.1f} s "
          f"({result.accepted} accepted)")
    if result.improved_at:
        print(f"last gain   at evaluation {result.improved_at}")
    else:
        print("last gain   none -- the constructive plan was not beaten")
    print(f"placed      {len(plan.placements)} / {len(job.items)}")
    print(f"checks      {report.summary()}")

    out = args.out or Path("data/plans") / f"{plan.plan_id}.json"
    save_plan(plan, out)
    print(f"written to  {out}")


if __name__ == "__main__":
    main()
