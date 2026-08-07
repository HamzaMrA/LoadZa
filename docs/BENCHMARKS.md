# Benchmark results

Instances come from the OR-Library container loading files (`thpack1`–`thpack9`).
They are not committed — fetch them once and every later run is reproducible
against the checksums in `bench/datasets/CHECKSUMS.txt`:

```bash
python -m tools.fetch_datasets
python -m bench.run_bench                       # BR1..BR7, default config
python -m bench.run_bench --configs baseline layer contact --limit 25
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

## Source data defect

Three records in `thpack9.txt` (instances 18, 19, 20) are missing a vertical
flag and cannot be read as the format documents. The parser refuses them by
default; `--skip-malformed` drops those three and reports their numbers. They
are never patched — guessing which flag went missing would put an invented
instance into a results table. `test_the_small_set_still_has_its_upstream_defect`
fails if OR-Library ever corrects the file.
