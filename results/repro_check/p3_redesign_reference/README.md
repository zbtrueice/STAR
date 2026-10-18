# P3 fluid-redesign reference data (historical, pre-correction)

This folder archives the reference data behind the "controlled redesign study"
paragraph of the manuscript (Section 4.8, F6 / fluid-redesign evidence).

## Provenance and status

- Source: the **pre-correction implementation** (the v3 repository state in
  which `rest_density` was a dead parameter and the fluid gain was
  `mag = k_fluid * (1-q)^2`, i.e. *un-gated*). The redesign study ran three
  density-gated variants against this historical baseline; **it was not
  re-run on the corrected code**, and its absolute numbers are therefore not
  comparable to the main-text results (as stated in the manuscript).
- Files copied verbatim from the v3 archive:
  - `two_stage_summary.csv` — per-seed (12 seeds, N=40, drop=0) final
    coverage / T90 / C(120) / AUC / energy for `star` (fluid 120 + VEVF 280,
    un-gated historical implementation) and `no_fluid` (VEVF from step 0).
  - `curves_{star,no_fluid}_{seed}.npz` — the underlying coverage curves used
    for the horizon-matched (0-280 step) AUC recomputation.

## Key reference numbers used in the manuscript (recomputed from this folder)

| Metric | un-gated reference (historical `star`) | no-fluid reference |
|---|---|---|
| T90 (steps) | 267.9 ± 9.4 | 192.9 ± 7.2 |
| Final coverage | 0.9581 ± 0.0076 | 0.9555 ± 0.0093 |
| C(120) | 0.334 ± 0.022 | 0.647 ± 0.035 |
| AUC (0-280) | 28.31 (gated_serial) / 51.4 (historical full-horizon 0-400) | 38.6 ± 1.1 |

Manuscript statements verified against this folder + `results/p3_fluid_redesign/results.json`:

- gated-serial T90 261.3 ± 7.4 vs 267.9 ± 9.4 → 6.7 steps earlier (paired).
- C(120) gain Δ=+0.010 (0.3442 vs 0.3340, gated_serial vs historical star).
- parallel vs no-fluid: final 0.944 ± 0.014 vs 0.956 ± 0.009; AUC 34.6 vs 38.6;
  T90 +75.8 steps (268.8 − 192.9).
- minimum inter-USV distance 10.6 m over all redesign runs.

## How to recompute the manuscript numbers

```
python experiments/compute_fairness_12seeds.py   # unrelated; benchmark fairness
python analyze_p0_p3.py                           # original v3 analysis (not in release)
```

In this package the numbers are reproduced directly from this folder with:

```python
import csv, numpy as np
rows = {r["variant"]: r for r in csv.DictReader(open("two_stage_summary.csv"))}
# group by variant, then mean/std over the 12 seeds
```
