# Baseline-config refactor regression — `baseline_config_regression/`

**Purpose.** The manuscript states that "all baseline hyperparameters come from
the shared configuration file" (paper §3.5, STAR_OE_submission.tex §3.5). This
statement is now literal: the baseline parameters for Lloyd, VFA, PSO and Random
are defined in `configs/default.yaml` (the `baselines` section) and
`run_suites.py` reads them from that section instead of relying on the module
defaults of `src/algorithms/baselines/*.py`. This directory archives the
regression evidence that the refactor changes **no** simulation behaviour.

**What was changed (tag v1.0.1 of this package):**

- `configs/default.yaml`: added `baselines:` (lloyd / vfa / pso / random),
  values equal to the previous hard-coded module defaults.
- `src/algorithms/baselines/random.py`: `stage_random` gained a
  `step_size=80.0` parameter (previously not externally settable).
- `run_suites.py`: the baseline branch of `run_episode` now constructs
  `VFAParams` / `PSOParams` and the Lloyd gain/drag and Random step size from
  `cfg['baselines']`; configs without the `baselines` section fall back to the
  same module defaults (backwards compatible).

**Regression method.** 4 baselines × 3 seeds {42, 7, 123} × N=40 = 12 runs
through `run_suites.run_episode`. Each run records final coverage, T90, coverage
AUC, energy (episode mean and final), mean neighbours, neighbour fraction and
the full final positions of all 40 USVs.

- `reg_results_before.json` — produced with the **pre-refactor** code (module
  defaults in effect).
- `reg_results_after.json` — produced with the **current** code (parameters
  read from `configs/default.yaml`).

**Result.** `python reg_diff.py` reports **0 differing fields / positions —
BIT-IDENTICAL**.

**Reproduce.** From the package root:

```
python results/repro_check/baseline_config_regression/reg_baseline_config.py
python results/repro_check/baseline_config_regression/reg_diff.py
```

The first command regenerates `reg_results_after.json` (overwrites the archived
copy); the second compares it with the archived `reg_results_before.json` and
must print `RESULT: BIT-IDENTICAL`. Runtime is a few minutes with a standard
Python environment (see `requirements.txt`).
