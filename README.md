# LoadZa

3D container loading optimisation. Given a list of goods and a vehicle, LoadZa
computes a **physically valid** placement for every box — position, orientation
and loading order — then visualises it and prints a loading plan.

The underlying problem is the **Container Loading Problem (CLP)**, a
constrained 3D bin packing problem. It is NP-hard: there is no practical exact
solver, so LoadZa combines a constructive heuristic with a metaheuristic
improvement pass and measures the result against published benchmark data.

> Status: **F5 complete** — constructive solver, constraint enforcement, an
> independent validator and an annealing pass over item orders.
> **82.1% mean volume utilisation across all 700 BR1–BR7 instances**, rising to
> **83.4% with an 8 second search**, 0 invalid plans throughout.
> Full numbers in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Why it is not a packing toy

| Concern | How it is handled |
|---|---|
| Boxes must not overlap or leave the vehicle | Exact integer AABB tests, no floating point geometry |
| Boxes must not float | Support ratio check: ≥70% of a footprint must rest on something |
| Stacks must not crush the bottom box | Recursive weight chain against each type's stacking limit |
| The trailer must not be lopsided | Centre-of-gravity offset checked against lateral and lengthwise tolerances |
| Multi-drop unloading | LIFO reachability: stop *n* must not be buried behind stop *n+1* |
| "Is the answer any good?" | Independent validator + benchmark runs on Bischoff & Ratcliff / Loh & Nee data |

The validator is a separate module from the solver on purpose. A solver that
grades its own output hides its bugs.

## Constraints

| ID | Constraint |
|---|---|
| K1 | No two boxes overlap |
| K2 | Every box stays inside the loading space |
| K3 | Total weight ≤ vehicle payload |
| K4 | Support ratio ≥ threshold (nothing floats) |
| K5 | Weight above a box ≤ its stacking limit |
| K6 | Orientation limits (fragile, this-side-up) |
| K7 | Centre of gravity within tolerance |
| K8 | Multi-drop LIFO reachability |

K1–K3 are hard: violating them makes a plan invalid. K4–K8 are realism
constraints and may also be handled as penalties.

All eight are checked by `core/validator.py`, which shares no code with the
solver — it recomputes overlap, support and load transfer from the placement
coordinates with plain nested loops. A shared helper would let one bug pass
both the solver and its own audit.

What the solver guarantees, and what it does not:

| | K1 | K2 | K3 | K4 | K5 | K6 | K7 | K8 |
|---|---|---|---|---|---|---|---|---|
| enforced by the solver | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | part | ✓ |
| checked by the validator | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

The constraints are handled by three different mechanisms, because they are
three different kinds of thing:

- **Local** — K1, K2, K3, K4, K6 are decided by looking at one candidate
  position, so they are filters inside the placement loop.
- **Cumulative** — K5 and K8 depend on what is already loaded. The solver
  carries a running load figure per box, pushed down the support tree in
  proportion to contact area, and packs delivery stops in reverse order so the
  first drop finishes nearest the doors.
- **Global** — K7 is a property of the finished load; no greedy filter can
  enforce it. The whole packed block is translated along the vehicle
  afterwards, which moves the centre of gravity without disturbing a single
  relative position.

**K7 is only half solved, and deliberately so.** Translation fixes the
lengthwise balance whenever there is free length, which in practice is always.
Sideways there is usually no free width, so the residual lean has to be
decided during packing — and a greedy side-choice rule measurably makes some
loads worse while fixing others. `balance_lateral` exists, defaults off, and
the honest result is written up in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).
Lateral balance is a job for the F5 global search.

## Layout

```
core/      domain model, geometry, solver, improvement, validator  (pure Python)
tools/     command line utilities, synthetic job generator
tests/     pytest suite
bench/     OR-Library instance parser and benchmark runner
app/       FastAPI service and reporting                        (F6)
web/       React + three.js viewer                              (F7)
data/demo/ generated example jobs
docs/      notes, screenshots
```

`core/` never imports from `app/` or `web/`. It has no third-party runtime
dependencies, so benchmarks run without a web server and the solver stays
portable.

## Conventions

- **Millimetres and grams, integers only.** Floating point geometry produces
  overlap tests that are almost right, which is worse than useless.
- **Origin at the front-left-bottom corner** — the closed end, furthest from
  the doors. `x` runs along the length towards the doors, `y` across the width,
  `z` up. Filling outwards from the origin therefore fills the deep end first,
  which is how a trailer is actually loaded.
- **Orientation names read in axis order.** `LWH` means length→x, width→y,
  height→z; `WLH` is the same box turned 90° about the vertical axis.
- Frozen dataclasses everywhere; the solver replaces rather than mutates.

## Quick start

```bash
git clone <repo-url> && cd LoadZa
python -m pip install -e ".[dev]"

# generate a synthetic job (13.6 m curtainside, mixed freight, 5% over-supplied)
python -m tools.gen_demo --vehicle TIR-1360 --mix mixed --fill 1.05 --seed 42

# solve it
python -m tools.solve data/demo/TIR-1360-mixed-s42.json

# audit the result, then draw it (needs the viz extra)
python -m tools.validate data/demo/TIR-1360-mixed-s42.json \
    data/plans/TIR-1360-mixed-s42-dbl-first_fit.json --explain 5
python -m tools.view data/demo/TIR-1360-mixed-s42.json \
    data/plans/TIR-1360-mixed-s42-dbl-first_fit.json

# spend 20 seconds searching item orders for a better plan
python -m tools.improve data/demo/TIR-1360-mixed-s42.json --seconds 20

# benchmark against the published instances
python -m tools.fetch_datasets
python -m bench.run_bench --limit 10
python -m bench.run_bench --limit 10 --anneal-seconds 8

pytest
```

![Side and top view of a three-stop container load](docs/CNT-40DV-3stop-s77-layer-first_fit.png)

A three-drop load, coloured by delivery stop. The last stop is packed deepest
and the first finishes at the doors, so nothing has to be unloaded twice. The
header line is the validator's verdict, not the solver's own.

Available vehicles: `TIR-1360` (13.6 m curtainside semi-trailer), `CNT-20DV`,
`CNT-40DV`, `CNT-40HC` (20 ft / 40 ft / 40 ft high cube containers).

## Data

**No customer or production data is used.** Every job is synthetic, produced by
a seeded RNG from a catalogue of standard unit loads (Euro pallets, industrial
pallets, cartons, drums). Vehicle dimensions are published container and trailer
specifications.

Benchmark inputs are the public OR-Library CLP datasets. They are not
committed — `python -m tools.fetch_datasets` downloads them once and records
their SHA-256 in `bench/datasets/CHECKSUMS.txt`, which *is* committed, so the
numbers above stay reproducible without redistributing someone else's research
data. Nothing needs a network after that first fetch.

## Roadmap

| Phase | Contents | State |
|---|---|---|
| F0 | Domain model, catalogue, JSON format, job generator | done |
| F1 | Extreme-point placement heuristic, CLI solver | done |
| F2 | Independent validator, property tests, schematic renderer | done |
| F3 | Benchmark harness over BR1–BR7, LN and the small set | done |
| F4 | Stacking limits, delivery reach, load balancing | done |
| F5 | Simulated annealing over item orders | done |
| F6 | FastAPI service, SQLite persistence | next |
| F7 | React + three.js viewer with load-order animation | |

## Results

**BR1–BR7, all 700 published instances, 0 invalid plans:**

| Config | Mean utilisation | ms / instance |
|---|---|---|
| `layer` (default) | **82.1%** | 161 |
| `dbl` | 81.6% | 383 |

**With the annealing pass**, on 70 of those instances at 8 seconds each, paired
against the same instances solved once:

| | Mean | Min | Improved | Worse |
|---|---|---|---|---|
| Constructive | 82.3% | 67.2% | | |
| + annealing | **83.4%** | **77.1%** | 51 of 70 | **0** |

The mean gain is +1.18 points and the median +0.68, but the minimum moves ten.
The search is a floor-raiser: it finds most of its value on the instances the
constructive heuristic packed badly, and almost nothing on the ones it already
packed well. Never-worse is structural — the best-so-far starts at the
constructive plan.

Per-set figures, the temperature study (annealing is currently
indistinguishable from hill climbing, and why), and what these numbers do *not*
claim are in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

On the synthetic demo jobs:

| Job | Volume | Placed | Time |
|---|---|---|---|
| 20 ft container, cartons | 80.5% | 161 / 234 | 152 ms |
| 40 ft high cube, pallets | 51.8% | 36 / 48 | 7 ms |
| 13.6 m trailer, mixed | 61.2% | 102 / 102 | 34 ms |

Two things those demo numbers hide, neither of them solver quality:

- **A load is either volume-bound or weight-bound.** The pallet job stops at
  67% payload but only 52% volume because a 1450 mm pallet cannot be stacked
  twice under a 2698 mm ceiling — that ceiling is physics, not a bad plan. The
  trailer job stops at 95% payload with the vehicle a third empty. Reading
  volume utilisation alone rewards the wrong thing.
- **Three jobs are not a sample.** All three scorers scored identically on
  them, and the conclusion drawn at the time — that corner selection does not
  matter — did not survive contact with 700 benchmark instances. It does
  matter, consistently.

## Licence

MIT.
