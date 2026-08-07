# LoadZa

3D container loading optimisation. Given a list of goods and a vehicle, LoadZa
computes a **physically valid** placement for every box — position, orientation
and loading order — then visualises it and prints a loading plan.

The underlying problem is the **Container Loading Problem (CLP)**, a
constrained 3D bin packing problem. It is NP-hard: there is no practical exact
solver, so LoadZa combines a constructive heuristic with a metaheuristic
improvement pass and measures the result against published benchmark data.

> Status: **F1 complete** — the extreme-point solver runs and enforces
> K1–K4. Baseline: 80.5% volume utilisation on a 234-item carton load in
> 152 ms. The independent validator lands in F2, so plans are *not* yet
> formally verified.

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

## Layout

```
core/      domain model, geometry, solver, validator, metrics  (pure Python)
tools/     command line utilities, synthetic job generator
tests/     pytest suite
bench/     benchmark datasets and runner                        (F3)
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

pytest
```

Available vehicles: `TIR-1360` (13.6 m curtainside semi-trailer), `CNT-20DV`,
`CNT-40DV`, `CNT-40HC` (20 ft / 40 ft / 40 ft high cube containers).

## Data

**No customer or production data is used.** Every job is synthetic, produced by
a seeded RNG from a catalogue of standard unit loads (Euro pallets, industrial
pallets, cartons, drums). Vehicle dimensions are published container and trailer
specifications. Benchmark inputs come from the public OR-Library CLP datasets.

## Roadmap

| Phase | Contents | State |
|---|---|---|
| F0 | Domain model, catalogue, JSON format, job generator | done |
| F1 | Extreme-point placement heuristic, CLI solver | done |
| F2 | Independent validator, property-based tests | next |
| F3 | Benchmark datasets, baseline measurement | |
| F4 | Realism constraints (K4–K8) | |
| F5 | Simulated annealing improvement pass | |
| F6 | FastAPI service, SQLite persistence | |
| F7 | React + three.js viewer with load-order animation | |

## Baseline results

First-fit, volume-decreasing item order, support constraint on. Synthetic demo
jobs; benchmark results against published datasets arrive in F3.

| Job | Volume | Placed | Time |
|---|---|---|---|
| 20 ft container, cartons | 80.5% | 161 / 234 | 152 ms |
| 40 ft high cube, pallets | 51.8% | 36 / 48 | 7 ms |
| 13.6 m trailer, mixed | 61.2% | 102 / 102 | 34 ms |

Three things these numbers hide, and none of them are solver quality:

- **A load is either volume-bound or weight-bound.** The pallet job stops at
  67% payload but only 52% volume because a 1450 mm pallet cannot be stacked
  twice under a 2698 mm ceiling — that ceiling is physics, not a bad plan. The
  trailer job stops at 95% payload with the vehicle a third empty. Reading
  volume utilisation alone rewards the wrong thing.
- **Corner selection barely matters here.** Deepest-left, layer-first and
  maximum-contact land within 0.5% of each other, because settling collapses
  candidates onto the same resting place. Item ordering is worth 13% by
  comparison, which is where the F5 improvement pass will search.
- **The support constraint costs 2.3%** on cartons and nothing on pallets.
  Published CLP results usually do not enforce it, so any comparison has to say
  whether it was on.

## Licence

MIT.
