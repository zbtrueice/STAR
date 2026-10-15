# Step 4 — Operating-Regime experiment report: effective working regions of Fluid and Hole Fill

Date: 2026-09-26 · Scripts: `v3/run_step4.py` / `v3/make_figures_step4.py`
(non-invasive, import the locked v3)
Config: `v3/configs/step4.yaml` (overlaid on default.yaml, no hard-coding) · Data:
`results/mech_verify/step4/`
Figures: `figures/mech_verify/step4/FigF2/FigF3/FigH2/FigH3` · Total runtime 3.8h
(60+75+270+6 runs)

**Methodology**: following mech_verify — the Fluid arm runs the **literal (k=350) +
force-calibrated (k=1.9367e6)** dual configuration; all comparisons use paired seeds;
F2/F3 switch off hole-fill in both arms to isolate the fluid contribution; H2/H3 deploy
with a pure-VEVF stable layout (clean pairing).

---

## F2 — Dense-cluster Fluid test (N=40 × cluster radius{500,1000,1500,2000} × 5 seeds × 3 arms)

| cr (m) | Arm | cov | T50 | T90 | gap(m) | energy |
|---|---|---|---|---|---|---|
| 500 | VEVF | 0.944 | 127 | 230 | 175 | 198 |
| 500 | F(cal)+V | **0.958** | 196 | 295 | **155** | 230 |
| 1000 | VEVF | 0.946 | 108 | 216 | 178 | 199 |
| 1000 | F(cal)+V | **0.958** | 195 | 296 | **157** | 219 |
| 1500 | VEVF | **0.960** | 90 | 189 | 156 | 197 |
| 1500 | F(cal)+V | 0.956 | 193 | 294 | 166 | 205 |
| 2000 | VEVF | **0.962** | 69 | 175 | 158 | 196 |
| 2000 | F(cal)+V | 0.958 | 184 | 282 | 157 | 197 |

(fluid_lit has no mechanism effect and lies between the two; the full table is in the
CSV; T50/T90 are absolute steps, and the fluid arms include the fixed 120-step front end)

**Findings**:
1. **The fluid coverage gain decays monotonically with the launch density**:
   Δcov(cal−V) = +0.014 (cr500) / +0.012 (cr1000) / **−0.004 (cr1500) / −0.004 (cr2000)**.
   The denser the launch, the more useful the fluid — the density-gated SPH pressure only
   produces repulsion in the compressed state (ρ>ρ₀), consistent with the design.
2. **The T90 penalty is density-independent** (fixed 120-step front end + 65-110 steps):
   the fluid is not faster at any cluster radius.
3. **Secondary benefit**: at dense launches (cr≤1000) the minimax gap improves 175→155
   (final-state spatial regularity).
4. **Early-crowding perspective** (cr0→cr1 / nn0→nn1, see timeseries): the calibrated fluid
   does de-cluster quickly in the fluid stage (at cr=500, nn 83→195 m over 20 steps in the
   smoke test; after the full 120 steps nn is markedly above the VEVF arm at the same
   time), but VEVF alone reaches the same expansion within 280 steps — the fluid's
   "de-crowding" is an **accelerator, not a capability**.

**F2 verdict — Fluid's effective working region**: **only extremely dense launches
(cr ≲ 1000 m, i.e. σ ≲ 0.1·L)**, where the benefit takes the form of +0.012~0.014 final
coverage and −20 m gap; at cr ≥ 1500 m the benefit disappears or turns negative. T90 is
penalised across the whole working region.
-> Fluid is a dense-initialization regularizer, **not** a general diffusion accelerator.

---

## F3 — Communication-loss test (N=40 × loss{0,10,30,50,70}% × 5 seeds × 3 arms, standard launch layout)

| drop | VEVF cov | F(cal)+V cov | VEVF gap | F(cal)+V gap | failure(0.90) |
|---|---|---|---|---|---|
| 0.0 | 0.950 | **0.961** | 179 | **149** | 0/0 |
| 0.1 | 0.952 | **0.955** | 173 | 176 | 0/0 |
| 0.3 | 0.927 | **0.932** | 254 | **239** | 0/0 |
| 0.5 | 0.867 | **0.870** | 369 | **354** | **1.0 / 1.0** |
| 0.7 | 0.717 | **0.729** | 632 | **604** | 1.0 / 1.0 |

**Findings**: no failure-cliff difference — all three arms break together at 50% loss
(T90 all −1); the calibrated fluid is slightly better in final coverage at every loss level
(+0.002~+0.011) and slightly better in gap at high loss. The fluid does not change the
**threshold location** of loss robustness; it only gives a small final-value gain inside
and outside the threshold. The T90 penalty also exists (+95~120 steps).

**F3 verdict**: on the loss dimension the fluid's effective working region matches the
no-loss case (small positive final-value contribution); there is no robustness story to
tell.

---

## H2 — Hole operating regime (N{20,30,40} × diameter{500-2500} × location{center/boundary/sparse-edge} × OFF/ON × 3 seeds; 270 runs)

| Location | Detection(ON) | rec OFF | rec ON | Residual OFF (km²) | Residual ON | final cov OFF | final cov ON |
|---|---|---|---|---|---|---|---|
| center | 1.00 | **32.5** | 35.4 | 2.00 | **1.90** | 0.7941 | **0.8046** |
| boundary | 1.00 | **67.6** | 77.2 | 1.60 | **1.46** | 0.7855 | **0.7954** |
| sparse-edge | 1.00 | **76.9** | 80.9 | 1.94 | **1.87** | 0.7885 | **0.7934** |

Aggregated by N:

| N | rec OFF/ON | Residual OFF/ON (km²) | final cov OFF/ON |
|---|---|---|---|
| 20 | 59.0 / 72.7 (only 3/30 recovered) | 3.42 / 3.50 | 0.585 / 0.592 |
| 30 | 64.3 / 77.1 | 1.64 / **1.46** | 0.832 / **0.840** |
| 40 | 54.6 / 58.8 | 0.47 / **0.27** | 0.951 / **0.962** |

**Findings**:
1. **Detection rate 100% (all 270 runs)** — the detection/trigger/communication constraint
   mechanism works completely (echoes Step 3).
2. **Recovery time is systematically slower with ON** (+3~10 steps): the hole force
   competes with the VEVF cell forces and slows the early contraction.
3. **But the residual with ON is markedly smaller and the final coverage higher**:
   at N=40 residual 0.47→0.27 km² (−43%), cov +0.010; at N=30 residual −11%, cov +0.008;
   at N=20 no benefit (the hole is too large, ~2.7-2.8 km equivalent diameter, and neither
   arm can recover it).
4. Location dimension: the ON benefit (residual and cov) at boundary/sparse-edge has the
   same sign as at center — the benefit is mainly determined by **N (redundancy)**; the
   location only affects the recovery difficulty (boundary/sparse is slower).

**H2 verdict — Hole Fill's effective working region**: **medium-to-high redundancy
(N≥30, the 0.83+ coverage plateau in this scenario)**, where the value takes the form of
**residual cleanup** (final residual −11~43%, final coverage +0.008~0.010) at a recovery-
phase cost of +5-15%. At N=20 (near-zero redundancy) both arms fail. -> Hole Fill is a
residual-cleaner, not a recovery-accelerator.

---

## H3 — Hole force-conflict sweep (fixed layout/hole (seed42, center, achieving d≈2092 m)/seed, sweeping only hole_fill.f_max)

| f_max | rec time | Residual (m²) | final cov | energy | oscillation |
|---|---|---|---|---|---|
| 50 | **22** | **125000** | **0.960** | **98.9** | 6 |
| 100 | 22 | 187500 | 0.948 | 101.8 | 8 |
| 200 | 22 | 187500 | 0.956 | 103.6 | **5** |
| 300 | 25 | 187500 | 0.953 | 107.6 | 7 |
| 400 | 25 | 250000 | 0.951 | 113.4 | 8 |
| 600 | 30 | 187500 | 0.953 | 116.0 | 9 |

**Findings**: the larger f_max, the slower the recovery, the higher the energy, and the
more oscillations (9 at 600); small f_max (50-200) dominates in this scenario. This
confirms the Step 3 judgment: **the conflict between the hole force and VEVF grows with
the force magnitude**. Note that this experiment is a working-domain **diagnosis, not
tuning** — the paper/main configuration still uses the config default 600 (the "no
parameter tuning" constraint); the improvement direction indicated by the diagnosis
(lowering f_max or density-gated triggering) is out of scope for this pass.

---

## Combined conclusion: working-region profile of the two mechanisms

| Mechanism | Effective working region | Form of benefit | Cost | Ineffective region |
|---|---|---|---|---|
| **Fluid (calibrated)** | extremely dense launches cr≲1000 m (ρ≫ρ₀) | final cov +0.012-0.014, gap −20 m, early de-clustering | T90 +65-110 steps, energy +8-15% | cr≥1500 m (benefit ≤0); T90 penalised everywhere |
| **Hole Fill** | medium-high redundancy N≥30 (cov plateau ≥0.83) | residual −11~43%, final cov +0.008-0.010, 100% detection | recovery phase +5-15%, conflict with VEVF forces (worse with larger f_max) | N=20 low-redundancy large holes (both arms fail) |

**What the two mechanisms share**: neither is the coverage workhorse (that is VEVF); both
are secondary mechanisms that improve **final-state quality** (regularity/residual) within
their own narrow working regions. This is consistent with the honest narrative of paper v2
(fluid = decoupling front end), and provides direct motivation for H4 (communication-
isolated holes — the scenario VEVF genuinely cannot recover): in H2 the residual left by
VEVF failing to recover at low redundancy (N=20 residual 3.4-3.5 km²) is exactly the
candidate scenario where Hole Fill may be the only irreplaceable component.

## Artifacts
- `results/mech_verify/step4/`: F2_dense_cluster.csv(+timeseries),
  F3_packet_loss.csv(+summary), H2_operating_regime.csv(+timeseries),
  H3_force_sweep.csv, progress.log
- `figures/mech_verify/step4/`: FigF2_dense_cluster.png, FigF3_packet_loss.png,
  FigH2_operating_regime.png, FigH3_force_sweep.png
