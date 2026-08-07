"""Audit a plan file against its job file.

    python -m tools.validate data/demo/job.json data/plans/plan.json
    python -m tools.validate <job> <plan> --checks K1 K2 K3 --explain 20

The plan does not have to come from this solver -- that is the point. Anything
that speaks the JSON format can be checked, including a plan typed in by hand
to prove the checker catches a known-bad load.

Exit code is 1 when violations are found, so the command can gate a script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.io import load_job, load_plan
from core.validator import ALL_CHECKS, validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a LoadZa plan")
    parser.add_argument("job", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--checks", nargs="+", default=list(ALL_CHECKS),
                        choices=list(ALL_CHECKS))
    parser.add_argument("--explain", type=int, default=10, metavar="N",
                        help="print at most N violations in full")
    args = parser.parse_args()

    job = load_job(args.job)
    plan = load_plan(args.plan)
    report = validate(job, plan, checks=tuple(args.checks))

    print(f"plan   {plan.plan_id}  ({plan.algorithm})")
    print(f"job    {job.job_id}  {len(plan.placements)} placements")
    print(f"checks {report.summary()}")

    for violation in report.violations[: args.explain]:
        print(f"  {violation}")
    hidden = len(report.violations) - args.explain
    if hidden > 0:
        print(f"  ... and {hidden} more")

    if report.is_valid:
        print("VALID")
        return 0
    print(f"INVALID: {len(report.violations)} violations")
    return 1


if __name__ == "__main__":
    sys.exit(main())
