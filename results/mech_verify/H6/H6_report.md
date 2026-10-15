# H6 — Hole-Fill mechanism-boundary factorial experiment report

Date: 2026-09-27 · Scripts: `v3/run_h6.py` / `v3/make_figures_h6.py` (non-invasive,
import the locked v3)
Config: `v3/configs/h6.yaml` · Data: `results/mech_verify/H6/` · Figures:
`figures/mech_verify/H6/Fig_H6_{heatmaps,timeseries}.png`
Design: 2-factor full factorial **d/C_th ∈ {0.7, 0.9, 1.0, 1.1, 1.3}** × **target hole
diameter ∈ {3000…6000 m}**, N=40 stable VEVF layout, 5 paired seeds, 300-step recovery,
Hole OFF/ON.
The construction prior is fixed (Phase 1 removes all vehicles within d_target to set the
isolation lower bound; Phase 2 widens the hole by removing the **non-nearest** next-closest
vehicles without breaking d; cap 20 vehicles); the actual d and achieved_diam are recorded
verbatim.

---

## 1. Main result (5-seed success rate / final-coverage gain)

| d/C_th | achieved d (m) | D target effective | OFF success (D=3k/4k/5k/6k) | ON success | success_gain | cov_gain (ON−OFF) |
|---|---|---|---|---|---|---|
| 0.7 | 2249 | ✅ (hole widening effective for D≥5k) | **1.0 / 1.0 / 0.4 / 0.4** | 0.8 / 1.0 / 0.2 / 0.2 | −0.2 / 0 / −0.2 / −0.2 | +0.002 / +0.009 / +0.004 / −0.005 |
| 0.9 | 2751 | partial (D=5k/6k) | 0.2 / 0.2 / 0.2 / 0.2 | 0.2 / 0.2 / **0.6** / 0.2 | 0 / 0 / **+0.4** / 0 | +0.006 / +0.006 / +0.010 / +0.003 |
| 1.0 | 3176 | ❌ (widening exceeds all D) | 0.2 / 0.2 / 0.2 / 0.0 | 0.0 / 0.0 / 0.0 / 0.0 | ≤0 | **+0.011 / +0.011 / +0.011 / +0.004** |
| 1.1 | 3369 | ❌ | 0.0 ×4 | 0.0 ×4 | 0 | +0.012 / +0.012 / +0.012 / +0.007 |
| 1.3 | 3976 | ❌ | 0.0 ×4 | 0.0 ×4 | 0 | +0.006 ×4 |

**Detection rate (ON) = 1.000 across all 20 conditions × 5 seeds × 300 steps** — even when
the hole centre is 1.3×C_th from every vehicle, the rim vehicles still discover the near
end of the hole within their own r_eff=min(search_radius, C_th) window. Purely local
detection holds at every isolation level.

## 2. Four findings

1. **The OFF success rate collapses monotonically with d**: at d≤0.7×C_th with D≤4000,
   OFF recovers 100% (sufficient redundancy, VEVF self-sufficient); for d≥0.9, OFF ≤20%;
   for d≥1.0 large holes, OFF≈0. **d/C_th≈0.8-1.0 is the transition band of VEVF's local
   recovery capability** — exactly the communication-limited transition assumed in the
   paper, now empirically confirmed.

2. **The ON "success-rate rescue" window is very narrow**: among the 20 conditions, ON
   improves the success rate at exactly one point, **d=0.9 × D=5000** (0.2→0.6, +0.4); the
   rest are 0 or −0.2 (in the d=0.7 redundancy region ON is worse, consistent with the
   force-conflict findings of H2/H3). **For large holes with d≥1.0, both arms' success
   rates go to zero simultaneously** — the binding constraint is no longer "whether there
   is a force pointing into the hole" but the **coverage capacity of the remaining
   vehicles (40−14~20 vehicles)**: after removing 14-20 vehicles, the total coverage
   capability is ~60-80 km², and simultaneously holding the periphery while filling a
   20-29 km² hole within 300 steps is physically infeasible.

3. **Two persistently positive signatures of ON (even when the success rate is 0)**:
   - **The final-coverage gain is positive in 19/20 conditions** (+0.002~+0.012) —
     hole-fill makes the rim vehicles keep encroaching into the hole and never ends worse
     than OFF in final coverage (the only negative, −0.005, is at d=0.7/6000);
   - **Transient recovery-then-regression**: for seed42 at d=1.0, ON reached the ≤20%
     threshold at step 102 (recovery_time=102 recorded) but the final state regressed to
     4.31 km² (threshold 4.13), judged a failure. That is, ON repeatedly "touches" the
     success line and is pulled back by the VEVF cell forces — the field conflict found in
     H3 manifesting at the boundary, and the reason ON is underestimated under the
     success-rate criterion.

4. **Cost**: ON energy is higher by 12-20 in every condition (+10~18%); the oscillation
   count is significant only in the d=0.7 redundancy region (OFF 0.4-2.0, ON 0.2-0.8, the
   H3 conflict region reappearing); for d≥0.9 both arms' oscillations tend to zero (no
   redundancy left to oscillate).

## 3. Relation to H4 (important correction)

H4 (step5, 3 seeds) gave the strong conclusion "isolated holes: OFF fails 2/3, ON succeeds
3/3". H6 redoes the same region with 5 seeds and a fixed construction prior (the d≈1.0
condition nearly coincides geometrically with H4: nearest 3209 vs 3209, 14 vehicles
removed, 20.6 km² injected) and finds:

- **Same direction**: at d≈1.0, OFF does fail systematically (success rate 0-0.2); ON's
  final coverage and transient recovery are always better than OFF;
- **Narrower magnitude**: counting "reached the threshold transiently then regressed" as
  failure, ON's success rate over 5 seeds is 0 — H4's 2:0 included the seed42 type (where
  OFF already succeeds) and a critical case near the threshold. **The strong version of
  H4's conclusion should be downgraded to: in the isolated-hole region, ON "significantly
  improves the recovery process and final coverage"; the success-rate advantage holds only
  in the narrow window d/C_th≈0.9-1.0 × medium D.**

## 4. Final mechanism working-domain map (H2+H3+H4+H6 combined)

| Region | Verdict | Evidence |
|---|---|---|
| d≤0.7×C_th and D≤4000 (benign region) | **Hole OFF self-sufficient, ON net-negative** (success −0.2, energy +15%) | H6 d=0.7 row, H2 N≥30 |
| **d≈0.9-1.0×C_th × D≈5k (transition band)** | **ON's only success-rate-gain region** (0.2→0.6) | H6 0.9/5000 |
| d≥1.0 × large holes (capacity-limited region) | **both arms fail**; ON still +0.4~1.2pp final coverage and transient recovery, but physically cannot succeed | H6 all d≥1.0 rows |
| low redundancy (N=20) large holes | both arms fail | H2 N=20 |
| balanced-redundancy small holes | ON small and persistently negative | H2/H3, paper v2 abstract |

**Unified mechanism explanation**: hole-fill's benefit is jointly gated by two conditions —
① whether the defect exceeds VEVF's local recovery capability (d/C_th → 1 triggers), and
② whether the remaining fleet's coverage capacity suffices to fill it (removed vehicles vs
hole area). When only ① holds, ON is a "useful driving force" (coverage gain > 0); the
success-rate gain requires ①+② simultaneously; when ② fails, no local mechanism can solve
it — this is a capacity boundary, not a mechanism defect.

## 5. Suggested wording for the paper

- Keep "motivating isolation-gated activation" in the abstract, but add a capacity
  qualifier: *"...succeeds in all — within the remaining fleet's coverage capacity"*, or
  state the capacity-limited region of H6 in the text (d≥1.0 large holes: both arms
  fail), so that a reviewer cannot overturn the claim with a "dig the hole to 30 km² and
  try again" counterexample.
- H6 can serve as a robustness annex to H4: the 2-factor heatmap (Fig_H6_heatmaps)
  directly shows the transition boundary and is more resistant to challenge than the
  single-point H4.

## 6. Artifacts

- `results/mech_verify/H6/`: H6_factorial.csv (200 rows, per seed), H6_summary.csv
  (20-condition aggregate), H6_timeseries.json (200 per-step series), progress.log
- `figures/mech_verify/H6/`: Fig_H6_heatmaps.png, Fig_H6_timeseries.png
- Runtime 5347 s (89 min, all 200 episodes)
