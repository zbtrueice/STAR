# Mechanism correctness audit (after fix) — code_audit_after.md

Date: 2026-09-25 · Corresponding pre-fix audit: `code_audit_before.md`

## Change overview (minimal, auditable, interface-compatible)

| File | Change | Interface impact |
|---|---|---|
| `core/simulator.py` | split out public methods `broadcast()` / `integrate(forces, dt)`; `step(forces, dt)` = broadcast + integrate (**bit-identical with the old behaviour**); `update()` kept as an alias of `integrate` | non-breaking; zero modification to the four baseline files |
| `algorithms/fluid.py` | rewritten to the density->pressure->force SPH mechanism (see below); new optional parameter `fluid_forces(..., return_debug=False)` | default return value unchanged |
| `algorithms/hole_fill.py` | trigger condition + circular effective search window + enhanced conflict resolution + `return_debug`; `HoleFillParams` gains `enabled/search_radius/conflict_radius` (all with defaults) | positional arguments compatible; new optional kwargs and `c_th` |
| `evaluation/metrics.py` | `MetricsRecorder` gains `phase(tag, sim, ...)` and `summary()['phases']`; new static methods `_nn_stats/_cluster_radius` | existing fields unchanged |
| `run_experiments.py` | `run_star`: explicit broadcast->force->integrate; initial/fluid_end/final three phases; `debug` parameter controls `[FLUID]/[VEVF]/[HOLE]` logging (silent by default); `hole_fill_forces` receives `c_th` | `run_star(cfg, seed, drop_rate)` signature compatible (debug optional) |
| `run_suites.py` | same timing fix in the `run_episode` STAR path + phase recording; return value adds `phases/positions/radii` (purely incremental); baseline branches unchanged | purely incremental |
| `configs/default.yaml` | `hole_fill` gains `enabled: true / search_radius: 3000 / conflict_radius: null` | all old keys kept |
| `tests/test_mechanism.py` | 13 new unit tests | new file |
| `run_mechanism_regression.py` | new regression driver (before/after/after_calibrated) | new file |
| (prior) `run_suites.py` return value `positions/radii` | added before the mechanism fix (final positions needed for regression comparison) | purely incremental |

## 1. Simulator timing (fixed)

New protocol (`run_star` / `run_episode` STAR path):

```
sim.broadcast()                # exactly once per dynamics step; must be done before the first force computation
F = fluid_forces(...)          # based on the current-step neighbor cache
sim.integrate(F, dt)           # integrate
```

- The old defects (empty cache on the first step, 1-step staleness afterwards) are
  eliminated structurally: the calling order guarantees the cache is current when forces
  are computed;
- `step(forces, dt)` is kept and semantically identical to the old version
  (broadcast->integrate), so **the per-step broadcast count and the RNG consumption
  sequence of the baselines are unchanged** (lloyd/vfa/pso/random should be bit-identical
  to `before` in the regression);
- The packet-loss model is unchanged: one `Comms.broadcast` per step (one Bernoulli sample
  per link); only its timing moved to before the force computation.

## 2. Fluid: density-pressure SPH mechanism (implemented)

```
rho_i = W(0) + Σ_j m_j W(r_ij, h)                      # h = interaction_radius, m_j = 1
p_i   = k_fluid · max(rho_i/rest_density − 1, 0)       # rest_density genuinely effective; ρ≤ρ₀ -> p=0
F_i   = −Σ_j m_j (p_i+p_j)/(2ρ_j) ∇W_ij                # symmetric pairwise; ∇W is the analytic gradient
      + XSPH viscosity + quadratic drag + boundary spring  # each term computed independently
```

- **rest_density genuinely participates**: it decides "how crowded counts as
  compressed"; ρ≤ρ₀ gives identically zero pressure (self-terminating diffusion);
- **Neighbor density ρ_j** is estimated from this vehicle's local viewpoint
  (`W(d_ij)+Σ_{k∈N_i,k≠j}W(|x_j−x_k|)`), the communication content is unchanged; for a
  two-vehicle system the estimate is exact -> action-reaction holds strictly (unit test
  #5);
- **Numerical guards**: `dist ≥ eps`, `rho_j ≥ W(0)` (self-term lower bound prevents
  division by zero), empty/non-effective neighborhoods skip the pressure term, and the
  direction vector checks for zero before normalising;
- **Debug output**: `return_debug=True` returns mean/max of
  rho/pressure/pressure_force/viscosity_force/drag_force/boundary_force/total_force;
- All parameters come from the config (`FluidParams` constructed from `cfg['fluid']`), no
  hard-coding.

## 3. Phase recording (implemented)

`MetricsRecorder.phase(tag, sim, force_mean, force_max)` records: coverage, energy,
mean_speed, nn_dist_mean, nn_dist_cv, cluster_radius_max, displacement_mean/max (relative
to the previous phase), force_mean/max. `run_star` and `run_episode` both record
**initial / fluid_end / final** (STAR path); the final-state metrics after the VEVF stage
are kept in `final`. Readable via `run_episode(...)['phases']`.

## 4. Hole Fill (fixed)

- **Trigger**: target search runs only when a local coverage deficit exists inside the
  effective search radius (a grid sample point covered by neither self nor neighbors);
  purely local criterion (self + neighbors' coverage union), no global coverage map
  (requirement of `code_audit_before.md` §4);
- **Search range**: circular window,
  `effective_search_radius = min(search_radius, communication.radius)`
  (`HoleFillParams.effective_search_radius(c_th)`); candidates hard-constrained to
  `‖p−x_i‖ ≤ r_eff`; the old `half = grid_res*6` square window (corner 4243 m > C_th) is
  deprecated;
- **Resolution and artefacts**: `grid_res` is read from the config; the coverage check uses
  the strict inequality `d² < r²` to avoid numerical artefacts of grid points lying exactly
  on the coverage-circle boundary; the docs state explicitly that "candidate points are
  detections in the grid_res sampling sense";
- **Conflict resolution**: the same/nearby hole (`conflict_radius`, default keeps
  0.3·self.radius, configurable) is served by the closer vehicle; equal distance ->
  smaller agent id wins (stable tie-break);
- **Force**: `min(k_target·d, f_max)` + zero-norm guard on the direction; `return_debug`
  outputs hole_candidates / hole_active_agents / selected_target_distance /
  hole_force_mean/max;
- **enabled=false**: strictly zero force (unit test #13).

## 5. Stage composition (confirmed)

STAR = Fluid (fluid_forces only) -> VEVF+HoleFill (vevf_forces + hole_fill_forces
appended). No fluid residue enters the VEVF stage; in the `use_fluid=False` ablation,
hole-fill belongs to the VEVF stage and is unaffected; in the `use_holefill=False`
ablation, the Fluid stage has no hole-fill force at all. Stage logs `[FLUID]/[VEVF]/[HOLE]`
are printed only when `debug=True`.

## 6. Force probe (dimensional measurement, N=40 dense cluster seed42 step0)

| Quantity | Old heuristic | New SPH (k_fluid=350, literal implementation) |
|---|---|---|
| mean‖F‖ | 1088.31 | 0.1967 |
| max‖F‖ | 1963.17 | 0.2801 |
| ρ/ρ₀ (mean/max) | — (ρ did not participate) | 2.16 / 2.84 |
| Ratio | 1 (baseline) | **1.81e-4** |

**Dimensional conclusion**: the absolute scale of the SPH pressure force depends on the
particle mass unit (here m=1, h=1500 m, ρ~1e-6, |∇W|~1e-10/m), so the literal
implementation's pressure acceleration is about 4 orders of magnitude smaller than the old
heuristic -> the Fluid stage is almost static (smoke test: 120-step cumulative displacement
11.2 m vs ~700 m for the old implementation). This is a dimensional property of the
formula, not a code defect.

**Disposition**: following the "no parameter tuning" constraint, the main regression
(`--tag after`) uses the literal k_fluid=350; an additional run
`--tag after_calibrated --k_fluid 1.9367e6` (= 350 × old/new force mean ratio 5533,
**pure force-scale matching, not metric fitting**) is provided for comparison/decision.
Both results are reported verbatim in `regression_report.md`.

## 7. Baselines

`algorithms/baselines/{random,vfa,lloyd,pso}.py` are **unchanged** (empty diff).
`Simulator.step` semantics are preserved -> their trajectories should be bit-identical to
`before` (one of the regression verification items).
