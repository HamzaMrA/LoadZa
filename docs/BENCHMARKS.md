# Benchmark results

Instances come from the OR-Library container loading files (`thpack1`–`thpack9`).
They are not committed — fetch them once and every later run is reproducible
against the checksums in `bench/datasets/CHECKSUMS.txt`:

```bash
python -m tools.fetch_datasets
python -m bench.run_bench                       # BR1..BR7, default config
python -m bench.run_bench --configs default dbl contact --limit 25
```

`utilisation` is placed volume over container volume, the measure the CLP
literature reports. Every run is validated; a row that scores well while
emitting overlapping boxes is a bug, not a result. Across every run below,
**0 of 700 plans failed validation**.

## Headline — BR1 to BR7, all 700 instances

| Config | Mean | Min | Max | ms / instance | Invalid |
|---|---|---|---|---|---|
| `dbl` (deep-left-bottom) | 81.6% | 66.9% | 92.8% | 383 | 0 |
| **`layer` (floor-first)** | **82.1%** | 63.9% | 92.6% | 396 | 0 |

Per set, `layer`:

| Set | Box types | Mean | Min | Max |
|---|---|---|---|---|
| BR1 | 3 | 82.0% | 63.9% | 92.6% |
| BR2 | 5 | 82.3% | 71.2% | 89.9% |
| BR3 | 8 | 82.7% | 72.5% | 90.1% |
| BR4 | 10 | 82.3% | 72.1% | 90.2% |
| BR5 | 12 | 82.4% | 72.8% | 88.6% |
| BR6 | 15 | 81.9% | 75.3% | 90.2% |
| BR7 | 20 | 81.2% | 73.5% | 88.1% |

Utilisation drifts down as cargo gets more heterogeneous, which is the expected
shape: more box types means more awkward gaps.

## F5: the improvement pass

Ten instances per set, 70 total, each given an 8 second budget. Paired against
the constructive solver on the same instances.

| | Mean | Median | Min | Max |
|---|---|---|---|---|
| Constructive | 82.3% | | 67.2% | 91.5% |
| **+ annealing, 8 s** | **83.4%** | | **77.1%** | 92.4% |
| Gain | +1.18 pts | +0.68 pts | | +9.84 pts |

**51 instances improved, 19 unchanged, 0 worse.** Never worse is structural,
not luck: the incumbent starts at the constructive plan and the best-so-far is
tracked separately, so a search that finds nothing returns what it began with.

The mean understates what happened. Split the 70 by how well the constructive
solver did:

| | Constructive | Annealed | Gain |
|---|---|---|---|
| Weakest 15 instances | 77.8% | 80.3% | +2.51 pts |
| Strongest 15 instances | 87.2% | 87.5% | +0.31 pts |

**The search is a floor-raiser.** The worst instance in the set goes from 67.2%
to 77.1%. Where the constructive heuristic already packed well there is little
left to find, which is what you would expect and worth stating: a claim of a
uniform gain across all instances would be the suspicious result.

### The annealing schedule does not matter here

Four starting temperatures over the same instances — 0.02, 0.005, 0.001, and
**zero**, which is plain hill climbing:

| Start temperature | Mean gain | Instances improved |
|---|---|---|
| 0.02 | +0.62% | 3 of 8 |
| 0.005 | +0.67% | 3 of 8 |
| 0.001 | +0.67% | 3 of 8 |
| 0 (hill climbing) | +0.67% | 3 of 8 |

Indistinguishable. The reason is the budget: one evaluation is a full solve, so
8 seconds buys 20–90 of them. Escaping local optima is a mechanism for
thousands of cheap steps, and this is not that regime. The honest description
of what ships is "a hill climber with an annealing schedule that currently
earns nothing" — kept because it costs nothing and starts earning the moment
evaluation gets cheaper.

Which is where the effort actually went. The spatial index used a fixed 1000 mm
cell; benchmark containers are 587 units long, so **every box landed in one
bucket and the index degenerated into a linear scan**. Deriving the cell size
from the cargo and replacing per-query set construction with a stamp array cut
the solve from 331 ms to 161 ms with byte-identical results — which doubles the
number of orders the search can try in the same budget.

### Gain against budget

| Budget | Mean gain | Evaluations per instance |
|---|---|---|
| 3 s | +0.41% | 24 |
| 10 s | +0.44% | 64 |
| 30 s | +0.66% | 174 |

Seven times the time for a quarter of a point. Anyone wanting more from this
search should make evaluation cheaper, not wait longer.

## Configuration comparison — 25 instances per set, 175 total

| Config | Mean | ms / instance |
|---|---|---|
| `contact` (max contact area, best-fit) | 82.2% | 574 |
| `layer` (floor-first) | 82.1% | 333 |
| `dbl` (deep-left-bottom) | 81.4% | 356 |
| `best_fit` (`dbl`, scoring every corner) | 81.4% | 443 |
| `area_order` (largest footprint first) | 80.8% | 417 |
| `support` (`dbl` + 70% support rule) | 80.1% | 323 |

`contact` and `layer` are level; `layer` gets there in 58% of the time, so it
is the default.

## What these numbers are not

They are **not** a claim to have reproduced any published result. Comparing
means against a paper requires matching its constraint set — support,
stability, orientation freedom and whether every box must be loaded all differ
between papers, and each costs utilisation. What this harness gives is a
figure computed on the same instances the literature names, so a comparison
can be made honestly once the specific paper's assumptions are read off it.

The gap to published heuristics is the point of phase F5: this is a purely
constructive solver with no improvement pass, and 82% is the bar the simulated
annealing layer has to clear.

## Findings

**A five-instance probe lied.** An early comparison on 10 instances put `layer`
1.7 points ahead of `dbl`. Over the full 700 the gap is 0.5 points. The
instance-to-instance spread on BR1 alone runs from 64% to 93%, so anything
measured on a handful of instances is noise.

**The F1 conclusion about corner selection was wrong.** On three synthetic
demo jobs, `dbl`, `layer` and `contact` produced identical utilisation, and the
note at the time concluded that corner choice does not matter because settling
collapses candidates onto the same resting place. On the benchmark instances it
does matter, consistently. Three hand-made jobs were not a sample.

**Choosing a scorer trades one constraint for another.** On the mixed trailer
job `dbl` leaves the centre of gravity 1894 mm off centre against a 1360 mm
tolerance, and `layer` brings it inside — but `layer` stacks higher and starts
resting weight on fragile crates, which `dbl` did not. Neither is safe by
accident. F4 has to enforce K5 and K7 as constraints rather than hope a
heuristic lands somewhere reasonable.

**The support rule costs 1.3 points** (81.4% → 80.1% on the same 175
instances). Published results usually do not enforce it, so any comparison has
to say whether it was on. All headline figures above have it **off**, matching
the benchmark convention.

## F4: constraints cost nothing here, and that is the point

Adding stacking limits, delivery reach and load balancing left the benchmark
mean unchanged at **82.1%** on the same 175 instances. That is not the
constraints being free — it is these instances not exercising them. BR boxes
carry no stacking rating, every instance is single-drop, and translating a
block along the container cannot change how much of it fits.

Where the constraints bite is on freight that has the properties BR does not
model. On the synthetic three-drop container job:

| | Utilisation | K5 | K8 |
|---|---|---|---|
| F3 solver | 71.6% | 7 violations | 260 violations |
| F4 solver | 64.2% | 0 | 0 |

**Reach costs 7 points of utilisation on that job.** Packing the last stop
deepest forbids using a gap in the wrong region, so fewer boxes fit. A version
of this that cost nothing would mean the constraint was not being applied — a
test asserts the drop is there.

## Lateral balance: a negative result

Lengthwise balance is solved. Translating the finished block centres the
centre of gravity whenever the load is shorter than the vehicle, which it
almost always is, and it cannot break anything because every relative position
is preserved.

Sideways it does not work, because a load usually spans the full width and
there is nowhere to slide. So the side has to be chosen during packing. Two
rules were tried on the four demo jobs:

| Rule | Result |
|---|---|
| Prefer the light side whenever the load leans | Disturbs already-centred loads; one job went from 0 mm to −1 mm but lost 2.6 points of volume |
| Prefer it only past half tolerance, and pick the side that measures better | Fixes one job (−157 → −1 mm), worsens another (−28 → −129 mm), no effect on two |

The second rule is the better one and still not good enough: a greedy choice
cannot see that a locally better side forces later boxes to a worse one. So
`balance_lateral` ships **off**, `K7` sideways stays an open violation on two
of the four demo jobs, and the fix belongs to the F5 search, which optimises
the finished load rather than each box in turn.

Recording this as a result rather than deleting the code: the next person to
reach for a greedy lateral rule should be able to see it was tried.

## Source data defect

Three records in `thpack9.txt` (instances 18, 19, 20) are missing a vertical
flag and cannot be read as the format documents. The parser refuses them by
default; `--skip-malformed` drops those three and reports their numbers. They
are never patched — guessing which flag went missing would put an invented
instance into a results table. `test_the_small_set_still_has_its_upstream_defect`
fails if OR-Library ever corrects the file.
