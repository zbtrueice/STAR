# F6 — Fluid parameter-robustness report

Date: 2026-09-27 · Scripts: `v3/run_f6.py` / `v3/make_figures_f6.py` (non-invasive,
import the locked v3)
Config: `v3/configs/f6.yaml` (overlaid on default/step4/step5) · Data:
`results/mech_verify/F6/` · Figures: `figures/mech_verify/F6/Fig_F6.png`

**Single question: is the limited benefit and the time/energy cost of Fluid in F4 robust
to the parameter value?**

Design: N=40, cluster_radius ∈ {500,1000} m, paired seeds {42,7,123}; everything else
follows F4 exactly (same initialization, same step budget 120+280, VEVF/hole-fill switches
unchanged). The k arms = VEVF-only (k=0, no fluid stage) and 0.5×/1.0×/2.0× × 1.9367e6.
No other parameters are searched, no tuning, no algorithm changes, no global information.

---

## Summary table (3 seeds, mean ± SD; Δ is the per-seed paired difference relative to
VEVF-only)

### cr = 500 m

| Arm | final cov | T90 | gap (m) | energy | Δcov | ΔT90 | Δgap | ΔE | \|F\| mean / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| VEVF-only | 0.9494±0.010 | 227±2 | 172±17 | 198±3 | — | — | — | — | — |
| 0.5× | 0.9629±0.004 | 302±2 | 160±9 | 229±2 | **+0.0135**±0.013 | +75±4 | −11±26 | +31±3 | 23.2 / 62 / 1.2e3 |
| 1.0× | 0.9602±0.006 | 295±0 | 158±9 | 230±2 | +0.0108±0.007 | +68±2 | −13±8 | +32±2 | 76.1 / 394 / 2.4e3 |
| 2.0× | 0.9552±0.006 | 292±6 | 171±8 | 230±4 | +0.0058±0.015 | +65±4 | −1±21 | +32±4 | 266 / 1.8e3 / 4.7e3 |

### cr = 1000 m

| Arm | final cov | T90 | gap (m) | energy | Δcov | ΔT90 | Δgap | ΔE | \|F\| mean / p95 / max |
|---|---|---|---|---|---|---|---|---|---|
| VEVF-only | 0.9415±0.015 | 218±14 | 183±19 | 198±3 | — | — | — | — | — |
| 0.5× | 0.9529±0.009 | 308±12 | 177±11 | 217±3 | +0.0115±0.009 | +90±8 | −6±8 | +20±0 | 17.6 / 40 / 831 |
| 1.0× | 0.9569±0.007 | 302±6 | 161±6 | 220±2 | +0.0154±0.008 | +83±12 | −21±13 | +22±2 | 29.4 / 91 / 1.7e3 |
| 2.0× | 0.9617±0.008 | 293±2 | 152±18 | 220±3 | **+0.0202**±0.011 | +75±16 | −31±21 | +22±4 | 59.5 / 227 / 3.3e3 |

Per-seed paired Δcov sign (18 combination-seed points): **15 positive / 3 negative**
(negatives: cr500-0.5× seed123 −0.004, cr500-2× seed123 −0.015, cr1000-0.5× seed42
−0.001).
oscillation_count (same definition as H3, applied to coverage(t)): **all zero**.

---

## Five judgments

1. **Is the direction of the final-state benefit stable across k?** — **direction broadly
   consistent but not universal, and small in magnitude**: the means of all 6 (cr,k)
   combinations are positive (+0.006 ~ +0.020), but 3 of the 18 per-seed pairs are
   negative, and the SD of Δcov (0.007-0.015) is of the same order as the mean. The
   directionality holds; the statistical strength is weak (n=3).
2. **Is the coverage/gap improvement always small?** — **yes**. Δcov is at most +0.020;
   Δgap is nominally at most −31 m but its ±21 SD makes it insignificant, and the gap
   benefit vanishes entirely at cr500-2× (−1±21).
3. **Does the T90/energy penalty appear consistently with k?** — **yes, without exception
   for every k>0**: ΔT90 = +65 ~ +90 steps (positive for every per-seed pair), ΔE = +20 ~
   +32. The penalty is **mildly relieved** as k grows (cr500: 75→68→65; cr1000: 90→83→75 —
   larger k -> the fluid stage diffuses more fully -> the VEVF stage starts slightly
   better), but the fixed 120-step fluid budget dominates and the penalty never disappears.
4. **Is there any k that simultaneously improves coverage/gap clearly without increasing
   T90/energy?** — **no**. k=0 (VEVF-only) is the only penalty-free point; every k>0 pays
   ≥+65 steps of T90 and ≥+20 energy.
5. **Is k=1.9367e6 a stable effective interval rather than an isolated point?** — **it is
   a "qualitatively stable interval", but there is no "effective point" inside the
   interval**: the directional conclusion is the same across the whole 0.5×–2× interval
   (small cov/gap benefit + fixed T90/E cost), and 1× is not special. The benefit
   magnitude is **non-monotonic in k** (at cr500, 0.5× is largest +0.0135 and 2× smallest
   +0.0058 — the pressure is so strong that the fluid stage over-expands and the VEVF
   stage must retract; at cr1000 it grows gently with k). The force magnitude grows with k
   but sub-linearly because the swarm expands -> density drops -> the pressure is
   self-limiting (mean 23→76→266 @cr500).

---

## Final answer

**The conclusion of F4 is parameter-robust.** "Fluid gives only a small benefit to the
final coverage/gap (≤0.02 / ≤~20 m, mostly insignificant) while fixedly increasing T90
(+65~90 steps) and energy (+20~32)" holds across the whole scanned interval
0.5×–2.0× × 1.9367e6, and **no k exists for which Fluid simultaneously obtains a
final-state benefit without the time/energy cost**. As agreed, this is reported here
explicitly: **no stable effective interval exists**, and the parameter search is not
extended further. k=1.9367e6 is a qualitatively stable representative point (not an
isolated/artefact point), but the Fluid benefit-cost structure is determined by the
mechanism and the fixed fluid budget, not by the parameter choice.

## Artifacts
- `results/mech_verify/F6/`: F6_parameter_sweep.csv (24 rows, per seed),
  F6_timeseries.json, F6_summary.csv (8 rows mean±SD+paired Δ), progress.log
- `figures/mech_verify/F6/Fig_F6.png` (coverage/T90/gap/energy/force magnitude/Δcov/ΔT90
  vs k)
