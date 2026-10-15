# Mechanism correctness audit (before fix) — code_audit_before.md

Date: 2026-09-25 · Audited object: `v3/` (locked distributed version) · Purpose: fix the
Fluid / Simulator timing / phase recording / Hole Fill implementation issues so that the
code is consistent with the algorithm design

---

## 0. Actual code paths

| Component | File | Key function/class |
|---|---|---|
| Agent (local agent) | `v3/core/agent.py` | `Agent` (neighbor_* perception caches filled by comms), `move()` (Euler integration + v_max clamping), `clamp_to()` |
| Communication layer | `v3/core/comms.py` | `Comms.broadcast()`: cKDTree neighbor discovery -> per-link Bernoulli packet loss -> fills neighbor_ids/positions/radii/velocities |
| Simulator | `v3/core/simulator.py` | `Simulator.step(forces, dt)`: **first** `comms.broadcast` **then** `update(forces)`; `update()` calls `move` + `clamp_to` |
| Fluid | `v3/algorithms/fluid.py` | `compute_local_density()`, `fluid_forces()` |
| Hole Fill | `v3/algorithms/hole_fill.py` | `_local_uncovered_targets()`, `hole_fill_forces()` |
| VEVF | `v3/algorithms/vevf.py` | `vevf_forces()` (local Laguerre cell minimax/centroid/edge forces) |
| Stage composition | `v3/run_experiments.py` (`run_star`) | Fluid 120 steps -> VEVF+HoleFill 280 steps |
| Experiment entry (six suites / published data) | `v3/run_suites.py` (`run_episode`) | Same `sim.step(force,...)` calling pattern |
| Metrics | `v3/evaluation/metrics.py` | `coverage_ratio`, `MetricsRecorder` (only initial/final snapshots) |
| Config | `v3/configs/default.yaml` | fluid / vevf / hole_fill / simulation / communication |

---

## 1. Simulator timing defect (confirmed)

**Current** (`simulator.py:40-43`):

```python
def step(self, forces, dt):
    self.comms.broadcast(...)   # broadcast happens inside step
    self.update(forces, dt)
```

But all callers (`run_experiments.run_star`, `run_suites.run_episode`) use:

```python
sim.step(fluid_forces(agents, ...), dt)   # compute forces first, then step
```

Consequence chain:
1. **First step**: when `fluid_forces` is called before step 1, the agents' perception caches
   are empty (zero-initialised in `Agent.__init__`), so the force is only drag+boundary and
   the crowded initial cluster is completely invisible;
2. **Later steps**: forces use the neighbor positions **broadcast on the previous step**
   (1-step stale) — `broadcast` runs inside `step`, after the force computation, so the cache
   is only refreshed afterwards;
3. **Protocol requirement**: broadcast current state -> compute force -> integrate ->
   (broadcast on the next step). The current implementation is compute (using the stale
   cache) -> broadcast -> integrate.

**Proposed change**:
- Split out public methods `broadcast()` and `integrate(forces, dt)` on `Simulator`;
- Keep `step(forces, dt)` (= broadcast + integrate); **the four baseline files stay
  unchanged** (they call `sim.step` internally; the timing is fixed automatically and the
  change is beneficial to them in the same direction);
- The STAR path (`run_experiments.run_star`, `run_suites.run_episode`) becomes explicit
  `sim.broadcast()` -> compute forces -> `sim.integrate(F, dt)`; still exactly one broadcast
  per step (the packet-loss RNG consumption count is unchanged).

---

## 2. Fluid mechanism defect (confirmed)

`fluid.py:33-73` actually executes:

```python
rho_i = compute_local_density(a, params)   # computed but never used
shape = (1 - q)**2
mag = params.k_fluid * shape               # constant-gain distance repulsion
F += (mag/dist) * d_hat
```

Issue list:
- **rho_i is dead code**: computed and discarded; `rest_density` never participates in the
  force (no gating, no pressure);
- **Not a density->pressure->force mechanism**: the force is independent of density; the
  density dependence is only the emergent effect of "crowded -> more neighbors -> more
  summed terms";
- **Asymmetric**: no pairwise symmetric form, no action-reaction guarantee;
- Viscosity / drag / boundary are kept (by design) but not reported separately.

**Proposed change** (keep the `fluid_forces(agents, params, width, height)` interface,
add an optional `return_debug` parameter):
- `rho_i = Σ_j m_j W(r_ij,h)` (cubic spline, `interaction_radius` = smoothing length h,
  m_j = 1);
- `p_i = k_fluid · max(rho_i/rest_density − 1, 0)` (rest_density genuinely enters the
  pressure; ρ≤ρ₀ gives zero pressure -> self-terminating diffusion);
- **Distributed estimation of neighbor pressure**: `rho_j` is estimated from i's local
  viewpoint (`rho_j ≈ W(d_ij) + Σ_{k∈N_i,k≠j} W(|x_j−x_k|)`, using only neighbor_positions,
  no extra communication content; a code comment explains the meaning of this approximation);
- Symmetric pressure force: `F_pres_i = −Σ_j m_j (p_i+p_j)/(2 ρ_j) ∇W_ij`, with ∇W the
  analytic cubic-spline gradient (`dW/dq = (−3q+2.25q²)/(πh²)`, direction `(x_i−x_j)/r`;
  since dW/dq<0, the force direction is **repulsive**; verify with a pair probe);
- Numerical guards: `dist ≥ eps`, `ρ_j ≥ W(0)>0` (guaranteed by the self-term), empty
  neighborhoods skip the pressure term;
- Viscosity (XSPH) / drag / boundary kept and **reported per term**;
- `return_debug=True` returns mean/max of rho/pressure/each force component.

**Known risk (must be reported honestly in the regression)**: implementing the above
directly with m=1 and h=1500 m, the pressure-acceleration magnitude is ~10⁻³–10⁻¹ (rough
estimate in §9), far smaller than the old heuristic (~3.5), so the Fluid stage may barely
move. **No parameter tuning**: measure with a force probe first, then give the dimensional
analysis conclusion and an optional calibration suggestion in the regression report
(decision left to the user).

---

## 3. Phase-recording defect (confirmed)

- `MetricsRecorder.snapshot` records only at step 0 and the last step (`run_star` and
  `run_episode` both use `snapshot(0)` + `snapshot(-1)`);
- The intermediate behaviour of the 120-step Fluid stage is completely unobservable (the
  coverage curve is recorded by `run_episode`, but NN distance / cluster radius / force
  statistics etc. are not recorded).

**Proposed change**: extend `MetricsRecorder` (no separate new system):
- Add `phase(tag, sim, stats=None)`: records coverage, mean NN distance, NN CV (std/mean),
  cluster radius (position std and max distance from centroid), mean/max displacement
  (since the previous phase), mean speed, energy, optional mean/max force;
- `run_star` / `run_episode` record at least the three phases `initial` / `fluid_end` /
  `final`; accumulate force statistics per step in the Fluid stage; keep the final-state
  metrics after the VEVF stage ends.

---

## 4. Hole Fill defect (confirmed)

`hole_fill.py` current state and issues:

| # | Issue | Code location | Current state |
|---|---|---|---|
| 4.1 | **All vehicles search unconditionally** (no force even when there is no candidate, but the search itself is not gated by a trigger and the window is unrelated to communication) | first loop of `hole_fill_forces` | every vehicle runs a full-window search every time |
| 4.2 | **Search window exceeds the communication radius**: `half = grid_res*6 = 3000 m` **square** window, corner 4243 m from the vehicle > C_th=3000 m; targets can lie outside the communication range | `_local_uncovered_targets` | `half = grid_res * 6.0` hard-coded |
| 4.3 | **grid_res is not controllable outside the config** (it is in the config but there is no candidate-count record and no resolution statement for the coverage check) | — | no artifact-guard statement, no candidate counting |
| 4.4 | **Coarse conflict resolution**: only gives up when "the neighbor's target is < 0.3·radius from this target" and "the neighbor is closer"; no stable tie-break; the same hole can attract many non-nearest vehicles simultaneously (if their nearest targets differ but the physical hole region is the same) | second loop | `a.radius*0.3` threshold, `d2 < d` |
| 4.5 | The force has `f_max` (good), but there is no maximum search distance (same root cause as 4.2), no debug output, no per-step recording | — | — |

**Proposed change**:
- Add `enabled` (config); strictly zero force when False;
- **effective_search_radius = min(search_radius(config), communication.radius)**, and the
  search window becomes **circular** (candidate criterion `||p − x_i|| ≤ r_eff`), fully
  excluding targets outside the communication range;
- Trigger condition = a local coverage deficit exists (i.e. some grid sample point inside
  the effective radius is covered by neither self nor neighbors); this condition is at the
  same time the search result, so vehicles without a deficit skip at zero cost (quick
  pre-check: skip when there is no deficit inside the own sensing disk and the neighbors'
  coverage union covers the sampled ring; implemented simply as skipping when the candidate
  count is 0 — distributed, no global coverage map; commented in the code);
- Candidate count, number of active vehicles, selected-target distance, and force
  mean/max can be recorded per step (`return_debug`);
- Enhanced conflict resolution: for a selected hole, check whether neighbors selected the
  same/nearby hole (threshold `conflict_radius`, default 0.3·self.radius keeping current
  behaviour, configurable); if a neighbor is closer -> this vehicle gives up; equal
  distance -> **stable tie-break (smaller agent id wins)**; each hole is served only by the
  nearest vehicle;
- Grid-sampling artefacts: the coverage check uses a strict inequality and records
  grid_res; comments explain the meaning of the sampling resolution (candidate points are
  samples on the grid_res grid, not a continuous-domain guarantee).

---

## 5. Stage-composition check (confirmed, no major change needed)

- `run_star` / `run_episode`: the Fluid stage only adds `fluid_forces`; the VEVF stage adds
  `vevf_forces + hole_fill_forces`; no fluid residue in the VEVF stage, no hole-fill mixed
  into the Fluid stage ✅;
- But in the `use_fluid=False` ablation path, `use_holefill` is still True by default —
  semantically correct (hole-fill belongs to the VEVF stage);
- Proposed addition: stage logging (`[FLUID]/[VEVF]/[HOLE]`), silent by default and only
  printed in debug mode.

---

## 6. Parameter/config gaps

| Parameter | Current state | Proposed change |
|---|---|---|
| `fluid.interaction_radius/k_fluid/rest_density/viscosity/drag/boundary_k` | already in config; rest_density is a dead parameter | keep names; rest_density becomes genuinely effective |
| `hole_fill.enabled` | **missing** (no switch) | add, default true |
| `hole_fill.grid_res` | already present | keep |
| `hole_fill.k_target/f_max` | already present | keep |
| `hole_fill.search_radius` | **missing** (half=grid_res*6 hard-coded) | add; code uses `effective = min(search_radius, communication.radius)` |
| `hole_fill.conflict_radius` | **missing** (0.3·radius hard-coded) | add optional; default None -> keep 0.3·self.radius |
| `simulation.fluid_steps/evfa_steps/timestep` | already present | keep |

Compatibility: `HoleFillParams(**{k: h_cfg[k] for k in h_cfg})` expands the full config
into the constructor -> every new config key must have a same-named parameter in
`HoleFillParams` (provided with a default value).

---

## 7. Baselines (confirmed unchanged)

`algorithms/baselines/{random,vfa,lloyd,pso}.py` are all standalone `stage_*` functions
that call `sim.step(f, dt)` internally. **Zero modification to the four files.** The timing
fix inside `Simulator.step` is an equivalent timing correction for the baselines (they also
benefit from "current-step neighbors"); it is a simulator semantic fix rather than an
algorithm change — assess its impact separately in the regression report.

---

## 8. Test and regression plan

- Add `v3/tests/test_mechanism.py`: Fluid 6 items / Simulator 2 items / HoleFill 5 items
  (list in the task spec);
- Regression: `v3/run_mechanism_regression.py --tag before|after` — 5 methods ×
  N{40,100} × drop{0,0.3} × seeds{42,7,123}; metrics: final_coverage / k90 / energy /
  fairness (v2 same-calibre Laguerre Jain) / gap (v2 same-calibre minimax gap);
- Order: unit tests -> small smoke (N=40 single-seed STAR + lloyd once each) -> full
  `after` regression -> item-by-item comparison with `before`.

---

## 9. Rough Fluid dimensional estimate (pre-fix prediction, for regression comparison)

- W(0) = 1/(πh²) = 1.42e-7; rest_density=1.4e-6 ≈ 10×W(0), i.e. "rest density ≈ 9-10
  effective neighbors";
- Initial cluster (std=750 m, N=40): ρ_i ≈ 4e-6, ρ/ρ₀ ≈ 2.9 -> p_i ≈ 350×1.9 ≈ 670;
- Single-neighbor pressure acceleration ≈ (p_i+p_j)/(2ρ_j)·|∇W| ≈ 1.7e8 × 6.6e-11 ≈
  0.011 m/s² (∇W = |dW/dq|/h);
- After isotropic cancellation among 35 neighbors, the net force is ~0.1 in magnitude ->
  120-step displacement ~10-100 m (old heuristic ~700 m).
- **Conclusion**: a literal implementation may make the Fluid stage almost static. This is
  a dimensional issue (SPH absolute force scaling depends on the mass unit), not a code
  bug. The regression report will give force-probe measurements, an old/new force
  distribution comparison, and a calibration suggestion derived from the dimensional
  analysis (**not applied by default**, awaiting the user's decision).

---

## 10. Proposed change-location list (file level)

| File | Change |
|---|---|
| `core/simulator.py` | split out `broadcast()`/`integrate()`; `step()` = broadcast+integrate (signature unchanged) |
| `algorithms/fluid.py` | density->pressure->symmetric-pressure-force refactor; `return_debug`; numerical guards; comments |
| `algorithms/hole_fill.py` | `enabled/search_radius/conflict_radius`; circular effective window ≤ C_th; trigger; tie-break; `return_debug` |
| `evaluation/metrics.py` | extend `MetricsRecorder.phase()` (NN distance/CV/cluster radius/displacement/force statistics) |
| `run_experiments.py` | `run_star`: broadcast->force->integrate; three-phase recording; stage logging (debug) |
| `run_suites.py` | same timing fix in the `run_episode` STAR path; phase recording (incremental fields, compatible) |
| `configs/default.yaml` | hole_fill: enabled/search_radius/conflict_radius |
| `tests/test_mechanism.py` | add 13 unit tests |
| (prior incremental change already done) `run_suites.py` | return value adds `positions/radii` fields (for regression comparison; does not affect dynamics) |
