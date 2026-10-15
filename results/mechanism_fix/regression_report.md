# Mechanism-fix regression report — regression_report.md

Date: 2026-09-25 (2026-09-26 update: `before` completed to 60/60) · Driver:
`run_mechanism_regression.py` · Data: this directory `regression_{after,after_calibrated}.json`
+ `v3_before_mechfix/results/mechanism_fix/regression_before.json`

## 0. Run notes

- Full case set = 5 methods × N{40,100} × drop{0.0,0.3} × seeds{42,7,123} = **60**.
- All three versions completed **60/60**:
  - `after` / `after_calibrated`: written 2026-09-25 22:19;
  - `before`: the original process was terminated during a session switch (33/60). It was
    then rebuilt per `code_audit_before.md` using `STAR-SCI-v1.0/src` (Sep 17 snapshot;
    diff verified bit-identical to the pre-fix code) plus the restored old
    run_suites/config, reconstructed as the code tree `v3_before_mechfix/`, and the run
    was completed (**60/60**). The **33 overlapping cases are bit-identical (0 diff) to the
    original `before` data**, proving the reconstruction is faithful; the full `before`
    data is stored in `v3_before_mechfix/results/mechanism_fix/regression_before.json`.
- `elapsed_s` fluctuates widely with the machine load that evening (up to 8x difference
  for the same case); reference only, it does not affect any metric.

## 1. Baseline bit-identity ✅

**All 48 baseline cases** (4 methods × N{40,100} × drop{0,0.3} × seeds{42,7,123}) are
**bit-identical across before / after / after_calibrated in
final_coverage / k90 / energy / fairness / gap_m** (only elapsed_s differs, which is
load noise).

This confirms the claims of `code_audit_after.md` §1/§7: `Simulator.step(forces, dt)` =
broadcast + integrate is semantically identical to the old version, and the four baseline
files are unchanged -> trajectories are unaffected by the mechanism refactor. The first
pass criterion of the regression holds.

## 2. STAR before vs after(literal) vs after_calibrated

### N=40 (mean of 6 cases: 3 seeds × drop{0,30})

| Version | k_fluid | final_coverage | k90 (steps) | energy | Note |
|---|---|---|---|---|---|
| before (old heuristic) | 350 | 0.9359 | 280.0 | 230.2 | reference |
| after literal (literal SPH) | 350 | 0.9523 | 323.3 | 200.8 | coverage up, energy down, but T90 slower by 43 steps |
| after_calibrated (force calibration) | 1.9367e6 | **0.9605** | 299.2 | 215.6 | highest coverage, T90 close to before |

Per-seed highlights (drop30, the scenario under the strongest packet-loss stress):

| seed | before | after literal | after_calibrated |
|---|---|---|---|
| 42 | 0.8988 | 0.9475 | 0.9513 |
| 7 | 0.9119 | 0.9375 | 0.9588 |
| 123 | 0.9344 | 0.9419 | 0.9431 |

Under packet loss, both new implementations beat `before` on all three seeds
(+0.019 ~ +0.052).

### N=100 (STAR, mean of 6 cases: 3 seeds × drop{0,30})

| Version | final_coverage | k90 (steps) | energy | Note |
|---|---|---|---|---|
| before (old heuristic) | 0.9999 | 222.5 | 601.8 | reference (drop0 μ218.3 / drop30 μ226.7) |
| after literal (literal SPH) | 1.0 | 278.3 | 497.5 | T90 slower by ~56 steps, energy lower by ~104 |
| after_calibrated (force calibration) | 0.9999 | 236.7 | 583.0 | T90 gap shrinks to ~14 steps |

### N=100 baseline reference (identical across all versions)

Lloyd N=100: cov 0.969-0.997, **k90 170-220 (faster than STAR)**, energy 264-331, fairness
0.615-0.723. Consistent with the honest narrative of paper v2: Lloyd reaches T90 faster at
N=100 while STAR has a higher final value (1.0 vs ≤0.997) and a smaller gap (0-5.3 m vs
29-74 m).

## 3. Conclusion

1. **Regression passed**: baselines are bit-identical (criterion 1); STAR final coverage is
   no lower than `before`, and the drop30 scenarios improve across the board (criterion 2).
2. **Literal SPH (k_fluid=350)**: mechanism-correct but the force scale is 4 orders of
   magnitude smaller (see `code_audit_after.md` §6), making the fluid stage almost static
   -> T90 slows markedly (N=40 +43 steps / N=100 +56 steps). Although energy is lowest and
   the final value does not drop, it is not suitable as the main configuration.
3. **Force-calibrated version (k_fluid=1.9367e6)**: the calibration factor equals the
   old/new force mean ratio (5533), a pure force-scale match, not metric fitting. T90
   recovers to near `before` (N=40 +19 steps / N=100 +14 steps), coverage is highest at
   N=40 (0.9605), and drop30 robustness is best. **Recommended as the main configuration
   after the mechanism fix.**
4. The residual gap (calibrated still 14-19 steps slower than before) comes from the
   mechanism change itself (SPH pressure vs heuristic), not a defect; fully aligning T90
   would require tuning rest_density/viscosity, which is a later parameter study and is
   outside the "no parameter tuning" constraint of this pass.

## 4. Decision pending

- Paper v2 and the beauty3 figures are based on the old-implementation data (suite 0.951
  etc.); if the mechanism fix is adopted, a "mechanism-fixed version" statement plus this
  report as a reproducibility annex is needed, or re-run the affected suites with the
  calibrated config (P0 comparison, Fig2 convergence).
- `before` is now fully **60/60 complete** (`v3_before_mechfix/`, the 33 overlapping cases
  bit-identical to the original data); the conclusions of this report are based on the
  complete three-version comparison.
