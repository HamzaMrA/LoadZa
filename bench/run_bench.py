"""Run the solver across published instances and write a comparison table.

    python -m bench.run_bench                      # BR1..BR7, default config
    python -m bench.run_bench --sets BR1 BR7 --limit 20
    python -m bench.run_bench --configs baseline layer support --out results.csv

Utilisation here is placed volume over container volume -- the same measure the
CLP literature reports, so the numbers can be held against any paper that names
these instances. It is not a claim that any particular published figure was
reproduced: comparing means requires reading the specific paper's constraints
(support, stability, orientation freedom), and those differ between them.

Every run is validated. A configuration that scores well while emitting
overlapping boxes is not a result, it is a bug.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from bench.loader import SETS, Instance, load_set
from core.solver_ep import SolverConfig, solve
from core.validator import validate

#: Constraints that must hold for a benchmark row to count as a result.
BENCH_CHECKS = ("K1", "K2", "K3", "K6")

#: Named runs. ``support`` carries the 70% resting rule that most published
#: results do not apply -- kept separate so the comparison stays honest.
CONFIGS: dict[str, tuple[SolverConfig, float]] = {
    "baseline": (SolverConfig(), 0.0),
    "layer": (SolverConfig(scorer="layer"), 0.0),
    "contact": (SolverConfig(scorer="contact", search="best_fit"), 0.0),
    "best_fit": (SolverConfig(search="best_fit"), 0.0),
    "area_order": (SolverConfig(item_order="base_area_desc"), 0.0),
    "support": (SolverConfig(), 0.70),
}


@dataclass(frozen=True, slots=True)
class Row:
    config: str
    set_name: str
    instance: int
    boxes: int
    placed: int
    utilization: float
    solve_ms: int
    violations: int


def run_instance(instance: Instance, config_name: str) -> Row:
    config, support = CONFIGS[config_name]
    job = instance.to_job(support_ratio=support)
    plan = solve(job, config)

    checks = BENCH_CHECKS + ("K4",) if support > 0 else BENCH_CHECKS
    report = validate(job, plan, checks=checks)

    placed_volume = sum(p.dims.volume for p in plan.placements)
    return Row(
        config=config_name,
        set_name=instance.set_name,
        instance=instance.number,
        boxes=instance.total_boxes,
        placed=len(plan.placements),
        utilization=placed_volume / instance.container.volume,
        solve_ms=plan.metrics.solve_ms if plan.metrics else 0,
        violations=len(report.violations),
    )


def summarise(rows: list[Row]) -> str:
    lines = [
        f"{'config':<12}{'set':<7}{'n':>5}{'mean':>9}{'min':>8}{'max':>8}"
        f"{'ms/inst':>10}{'invalid':>9}"
    ]
    seen: list[tuple[str, str]] = []
    for row in rows:
        if (row.config, row.set_name) not in seen:
            seen.append((row.config, row.set_name))

    for config_name, set_name in seen:
        group = [r for r in rows if r.config == config_name and r.set_name == set_name]
        utils = [r.utilization for r in group]
        bad = sum(1 for r in group if r.violations)
        lines.append(
            f"{config_name:<12}{set_name:<7}{len(group):>5}"
            f"{mean(utils):>9.1%}{min(utils):>8.1%}{max(utils):>8.1%}"
            f"{mean(r.solve_ms for r in group):>10.0f}{bad:>9}"
        )

    for config_name in dict.fromkeys(r.config for r in rows):
        group = [r for r in rows if r.config == config_name]
        lines.append(
            f"{config_name:<12}{'ALL':<7}{len(group):>5}"
            f"{mean(r.utilization for r in group):>9.1%}"
            f"{min(r.utilization for r in group):>8.1%}"
            f"{max(r.utilization for r in group):>8.1%}"
            f"{mean(r.solve_ms for r in group):>10.0f}"
            f"{sum(1 for r in group if r.violations):>9}"
        )
    return "\n".join(lines)


def write_csv(rows: list[Row], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["config", "set", "instance", "boxes", "placed",
             "utilization", "solve_ms", "violations"]
        )
        for row in rows:
            writer.writerow([
                row.config, row.set_name, row.instance, row.boxes, row.placed,
                f"{row.utilization:.6f}", row.solve_ms, row.violations,
            ])
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the LoadZa solver")
    parser.add_argument("--sets", nargs="+", default=[f"BR{n}" for n in range(1, 8)],
                        choices=sorted(SETS))
    parser.add_argument("--configs", nargs="+", default=["baseline"],
                        choices=sorted(CONFIGS))
    parser.add_argument("--limit", type=int, default=None,
                        help="use only the first N instances of each set")
    parser.add_argument("--skip-malformed", action="store_true",
                        help="drop source records that do not parse (thpack9 has one)")
    parser.add_argument("--out", type=Path,
                        default=Path("bench/results/bench.csv"))
    args = parser.parse_args()

    rows: list[Row] = []
    for config_name in args.configs:
        for set_name in args.sets:
            dataset = load_set(set_name, strict=not args.skip_malformed)
            if dataset.skipped:
                print(f"  {set_name}: skipped malformed instances "
                      f"{list(dataset.skipped)}")
            instances = list(dataset.instances)
            if args.limit is not None:
                instances = instances[: args.limit]
            for instance in instances:
                rows.append(run_instance(instance, config_name))
            done = [r for r in rows if r.config == config_name and r.set_name == set_name]
            print(f"  {config_name:<12}{set_name:<6}"
                  f"{len(done):>4} instances  mean "
                  f"{mean(r.utilization for r in done):.1%}", flush=True)

    print()
    print(summarise(rows))
    print()
    print(f"rows written to {write_csv(rows, args.out)}")

    invalid = sum(1 for r in rows if r.violations)
    if invalid:
        print(f"WARNING: {invalid} plans failed validation")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
