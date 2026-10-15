# Suite old-vs-new calibration comparison table (12 seeds)

- Old calibration = `STAR-SCI-v1.0/results/all_runs_v4.csv` (original 504-row archive;
  old implementation: heuristic fluid + old timing + old hole-fill; scalability uses the
  400-step full-budget protocol). `suite/bak_prefix/` restores this archive in sync.
- New calibration = `suite/all_runs.csv` mechanism-fixed version (SPH fluid k=1.9367e6
  force-calibrated + broadcast/integrate timing + hole-fill fix; baselines bit-reused).
- For scalability N>=100, the new calibration uses the unified 200-step budget of scalfix
  (fluid 60 + evfa 140), which is not directly comparable with the old 400-step protocol
  (see note).

| suite | method | cov old (SD) | cov new (SD) | Δ | T90 old | T90 new |
|---|---|---|---|---|---|---|
| ablation | no_fluid | 0.9555 (0.0089) | 0.9636 (0.0077) | +0.0082 | 193 | 191 |
| ablation | no_hole_fill | 0.9641 (0.0089) | 0.9625 (0.0054) | -0.0016 | 271 | 294 |
| ablation | no_laguerre | 0.9009 (0.0185) | 0.9065 (0.0125) | +0.0056 | 293 | 335 |
| ablation | no_vevf | 0.8396 (0.0324) | 0.9114 (0.0281) | +0.0718 | 305 | 362 |
| ablation | star | 0.9581 (0.0073) | 0.9707 (0.0046) | +0.0126 | 268 | 288 |
| benchmark | lloyd | 0.9290 (0.0547) | 0.9290 (0.0547) | +0.0000 | 216 | 216 |
| benchmark | pso | 0.8719 (0.0955) | 0.8719 (0.0955) | +0.0000 | 265 | 265 |
| benchmark | random | 0.7765 (0.1139) | 0.7765 (0.1139) | +0.0000 | 385 | 385 |
| benchmark | star | 0.9790 (0.0215) | 0.9853 (0.0149) | +0.0063 | 242 | 258 |
| benchmark | vfa | 0.4045 (0.0427) | 0.4045 (0.0427) | +0.0000 | n/a | n/a |
| comm_radius | star | 0.7936 (0.2544) | 0.8146 (0.2573) | +0.0210 | 272 | 289 |
| heterogeneity | homogeneous | 0.9394 (0.0064) | 0.9630 (0.0066) | +0.0236 | 265 | 292 |
| heterogeneity | medium | 0.9581 (0.0073) | 0.9707 (0.0046) | +0.0126 | 268 | 288 |
| heterogeneity | mild | 0.9327 (0.0130) | 0.9613 (0.0080) | +0.0286 | 273 | 296 |
| heterogeneity | strong | 0.9738 (0.0047) | 0.9777 (0.0039) | +0.0039 | 260 | 280 |
| packet_loss | star | 0.9129 (0.0410) | 0.9490 (0.0267) | +0.0361 | 280 | 309 |
| scalability | star | 0.9343 (0.1250) | 0.9396 (0.1182) | +0.0054 | 198 | 204 |

Note: T90 is the mean over seeds that reached the target; for scalability N>=100 the new
calibration T90 is comparable under the same budget.
