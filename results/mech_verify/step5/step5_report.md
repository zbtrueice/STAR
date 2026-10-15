# Step 5 — Mechanism working-domain verdict report: Fluid ≠ dense-init regularizer? Hole Fill's irreplaceable region

Date: 2026-09-27 · Scripts: `v3/run_step5.py` / `v3/make_figures_step5.py`
(non-invasive, import the locked v3)
Config: `v3/configs/step5.yaml` · Data: `results/mech_verify/step5/` · Figures:
`figures/mech_verify/step5/`
Design: paired seeds (F4: 5 seeds; H4: 3 seeds), no algorithm changes, no parameter
tuning, algorithms use no global information, baselines unchanged. The Fluid arm uses the
current force-calibrated config (k=1.9367e6).

---

## F4 — Dense Initialization Robustness (N=40 × cluster radius{500,1000,1500} × 5 seeds × 2 arms)

| cr(m) | Arm | cov | T50 | T90 | t>1000 | t>2000 | t>3000 | ov@120 | cr@120 | gap | energy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | VEVF | 0.944 | **127** | **230** | 30 | **76** | **123** | **1.68** | **2989** | 175 | **198** |
| 500 | F(cal)+V | **0.958** | 196 | 295 | 30 | 150 | 190 | 4.92 | 1430 | **155** | 230 |
| 1000 | VEVF | 0.946 | **108** | **216** | 1 | **51** | **100** | **1.30** | **3474** | 178 | **199** |
| 1000 | F(cal)+V | **0.958** | 195 | 296 | 1 | 147 | 188 | 4.80 | 1502 | **157** | 219 |
| 1500 | VEVF | **0.960** | **90** | **189** | 0 | **30** | **74** | **0.97** | **4039** | **156** | **197** |
| 1500 | F(cal)+V | 0.956 | 193 | 294 | 0 | 139 | 186 | 4.57 | 1666 | 166 | 205 |

**Core question: does Fluid reduce early crowding? — No.** Under the equal-step-count
criterion:
- Escape speed: VEVF alone breaks through the 2000 m cluster radius in 30-76 steps, while
  the Fluid arm needs 139-150 steps (after the 120-step fluid stage, VEVF still has to run
  another 20-30 steps); VEVF is also ~65 steps faster at breaking 3000 m.
- At the end of the fluid stage (step 120), the Fluid arm's cluster radius is only
  1430-1666 m with overlap still as high as 4.6-4.9; at the same step count the VEVF arm
  has already reached 2989-4039 m with overlap 0.97-1.68 — **VEVF's vertex/centroid forces
  are themselves a faster de-crowding operator**. The fluid's "diffusion" only achieves a
  small fraction of VEVF's expansion within the 120-step budget.
- The only tie is at the 1000 m threshold (the fluid arm starts dense, the SPH pressure
  releases immediately, but the magnitude is small).

**Final coverage and gap** (consistent with F2): at cr≤1000 the fluid gives +0.012~0.014
cov and −20 m gap; at cr=1500 the benefit disappears (−0.004). T90 is +60~110 steps and
energy +8~16% everywhere.

**F4 verdict**: **Fluid is not a dense-initialization regularizer** — it does not reduce
early crowding (VEVF de-crowds faster at equal step counts); its entire value is only the
small final-state quality gain (cov/gap) at cr≲1000 m, paid for with T90 and energy. The
hypothesis "fluid = dense-launch regularization" is rejected.

---

## H4 — Communication-Isolated Hole (N=40 × 3 seeds, deployment = pure-VEVF stable layout)

Construction: greedily remove the agents nearest to the hole centre from a stable layout
until the **nearest remaining agent is > C_th=3000 m from the hole centre** (measured
3092-3392 m); 11-15 vehicles removed, a hole of 19.4-23.8 km² injected (equivalent
diameter ~5.0-5.5 km), and the remaining vehicles form a communication ring around the
hole (posterior connected-component count = 1; the "subgroup" manifests as ring arcs).
Recovery phase 300 steps.

| seed | removed | nearest | Arm | Detection | Recovery steps | Success | Residual (km²) | final cov | energy |
|---|---|---|---|---|---|---|---|---|---|
| 42 | 14 | 3209 | OFF | 0 | 69 | ✅ | **1.44** | **0.8875** | **102.6** |
| 42 | | | ON | 1.00 | 70 | ✅ | 1.56 | 0.8831 | 118.7 |
| 7 | 11 | 3392 | OFF | 0 | 132 | ❌ | 6.19 | 0.8175 | 119.5 |
| 7 | | | ON | 1.00 | **112** | ✅ | **4.62** | **0.8450** | 132.3 |
| 123 | 15 | 3092 | OFF | 0 | −1 | ❌ | 5.94 | 0.7850 | 94.1 |
| 123 | | | ON | 1.00 | **109** | ✅ | **4.38** | **0.8113** | 107.6 |

**Findings**:
1. **Detection rate 100% (ON for all 3 seeds × 300 steps)**: although the hole centre lies
   beyond every vehicle's sensing/communication range, the rim vehicles still discover the
   near end of the hole within their own r_eff=min(search_radius, C_th) window — purely
   local detection still holds for communication-isolated holes.
2. **Paired result 2:0**: for seed7 and seed123, **OFF fails to recover (300-step residual
   5.9-6.2 km²) while ON succeeds (109-112 steps, residual 4.4-4.6 km², final cov
   +0.026/+0.028)**. Mechanism: VEVF local cells do extend into the hole (cells are not
   truncated by C_th), producing slow encroachment, but the direction of the
   vertex/centroid forces is unstable at the hole edge; the hole-fill "nearest uncovered
   point" target force provides a persistent recovery bias pointing into the hole.
3. **OFF can also win one**: for seed42 (the lightest isolation and relatively small hole),
   OFF is faster with less residual — when redundancy is sufficient, VEVF cleans up by
   itself, and hole-fill instead introduces f_max conflict (+16 energy, residual 1.44→1.56).
4. Cost: ON energy +12~14 (the hole force does work), consistent with the conflict finding
   of H3.

**H4 verdict**: **Hole Fill's irreplaceable working region = communication-isolated /
large-scale coverage defects** (hole centre beyond C_th, VEVF cell encroachment stuck or
directionally unstable). In this region OFF fails 2/3 while ON fails 0/3; on small holes
with sufficient redundancy (seed42 type) Hole Fill gives no net benefit. Combined with H2
(N=20 low redundancy: both arms fail; N≥30: residual cleanup): **the complete working-
domain profile of Hole Fill = medium-or-higher redundancy + defect scale beyond VEVF's
local recovery capability**.

---

## Combined conclusion (mechanism working-domain map from Step 4 + Step 5)

| Mechanism | Effective working region | Irreplaceability evidence | Ineffective/negative region |
|---|---|---|---|
| **Fluid (calibrated)** | extremely dense launches cr≲1000 m: final cov +0.012-0.014, gap −20 m | **none** — F4 proves its early de-crowding is slower than VEVF, not a regularizer; H4 has no fluid arm | cr≥1500 m (cov ≤0); T90 +60-110 steps everywhere; early crowding not reduced but increased (ov@120 4.6-4.9 vs 1.0-1.7) |
| **Hole Fill** | ① communication-isolated / large-scale holes (H4: 2/3 OFF failures vs 0/3) ② medium-high redundancy residual cleanup (H2 N≥30: residual −11~43%) | **yes** — H4 is the only scenario where OFF fails systematically; 100% detection and locality hold | low-redundancy large holes (H2 N=20: both arms fail); sufficient-redundancy small holes (seed42 type: +16 energy, no net benefit) |

**Implications for the paper narrative**:
1. If "fluid self-diffusion" is kept, it can only be stated in the terms of
   **cr≲1000 m extremely dense launches + final-state quality**; one may not claim faster
   deployment or reduced early crowding.
2. **Hole Fill gains an empirically supported selling point**: it is irreplaceable for
   communication-isolated defects (a real failure mode of distributed deployment —
   subgroups losing contact, uncovered intermediate regions). The paper should rewrite
   hole-fill's motivation from "generic hole patching" to "communication-isolated defect
   recovery"; H4 can be added as a new experimental figure.
3. The working-region boundaries of both mechanisms are determined by **density/
   redundancy** (the SPH ρ>ρ₀ gate and the hole-fill trigger window), self-consistent with
   their purely local implementations — this can be written into the discussion as a
   systematic "mechanism-working-region matching" argument.

## Artifacts
- `results/mech_verify/step5/`: F4_dense_init.csv(+timeseries),
  H4_isolated_hole.csv(+timeseries), progress.log
- `figures/mech_verify/step5/`: Fig_F4.png, Fig_H4.png
