# Unit test report — unit_test_report.md

Date: 2026-09-25 · Test file: `v3/tests/test_mechanism.py` (13 items) · Run:
`python tests/test_mechanism.py` (also compatible with pytest)

## Result: 13/13 passed

| # | Test | What is verified | Result |
|---|---|---|---|
| 1 | `test_fluid_no_neighbors_zero_pressure` | no neighbors -> rho=W(0), pressure force=0, total force=0 (at rest) | PASS |
| 2 | `test_fluid_close_pair_repulsion` | two vehicles in the compressed state (ρ>ρ₀) -> mutual **repulsive** pressure force, correct direction (each moves away from the other) | PASS |
| 3 | `test_fluid_force_decreases_with_distance` | increasing distance -> decreasing pressure force (verified on the monotonic branch of the kernel gradient q>2/3; force=0 at q≥1) | PASS |
| 4 | `test_fluid_no_negative_pressure` | ρ<ρ₀ -> pressure is identically 0, no attractive force | PASS |
| 5 | `test_fluid_action_reaction` | two vehicles satisfy action-reaction strictly (the neighbor-density estimate is exact for two vehicles) | PASS |
| 6 | `test_fluid_rest_density_changes_response` | changing rest_density changes the pressure response (pressure present at ρ₀=2e-7; pressure=0 at ρ₀=1e-3) | PASS |
| 7 | `test_simulator_broadcast_before_force` | broadcast refreshes the perception cache; without broadcast after manually moving, the cache stays stale; after broadcast it is current | PASS |
| 8 | `test_simulator_star_protocol_first_step` | STAR protocol first step: broadcast->force->integrate; **nonzero repulsion is produced on the first step** (old implementation had an empty cache -> zero force); vehicles are pushed apart after integrate | PASS |
| 9 | `test_holefill_no_local_hole_zero_force` | no local deficit -> hole force=0, active=0 | PASS |
| 10 | `test_holefill_activates_on_hole` | local deficit present -> at least one vehicle activates hole fill and force>0 | PASS |
| 11 | `test_holefill_candidates_within_comm_radius` | all candidate points satisfy ‖p−x_i‖ ≤ min(search_radius, C_th) (search_radius=∞ used to verify the C_th hard cap) | PASS |
| 12 | `test_holefill_conflict_resolution` | multiple vehicles facing the same hole: only the eligible vehicle serves it (conflict resolution + tie-break) | PASS |
| 13 | `test_holefill_enabled_false_strict_zero` | enabled=false -> force strictly 0 (both debug and non-debug interfaces) | PASS |

## Mechanism facts confirmed by the tests (recorded for reference)

1. **The density estimate is exact for a two-vehicle system** (`rho_j_est` equals the true
   value), so action-reaction holds strictly; with more vehicles the neighbor density is a
   local-viewpoint estimate (underestimating j's contribution outside the communication
   range), a controlled approximation of symmetry.
2. **|∇W| of the cubic spline kernel peaks at q=2/3**, so "increasing distance -> decreasing
   force" holds monotonically only on the q>2/3 branch; this is an intrinsic property of
   the kernel shape, not an implementation error. Test #3 verifies on the monotonic branch
   accordingly and additionally checks q≥1 -> zero force.
3. **The production default rest_density=1.4e-6 ≈ 10 effective-neighbor equivalents**
   (W(0)=1.42e-7): an isolated two-vehicle system (ρ≈2.75e-7) is not compressed and the
   pressure is zero — this is designed behaviour (rest_density decides "how crowded counts
   as compressed"); the tests explicitly set rest_density to enter the compression regime.
4. **The first-step zero-force issue is eliminated**: test #8 proves that on the first step
   (after broadcast) neighbors are perceived and the correct repulsive force is produced.
