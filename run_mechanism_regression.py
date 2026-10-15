# -*- coding: utf-8 -*-
"""run_mechanism_regression.py -- driver for the regression comparison before and after
the mechanism fixes.

Runs one complete deployment per 5 methods x N{40,100} x drop{0.0,0.3} x seeds
[42,7,123]:
  - coverage curve (record_every=5) -> final_coverage / k90
  - final energy (path-length proxy)
  - v2-compatible Laguerre fairness / minimax gap (reuses v2_compat)
Usage:
  python run_mechanism_regression.py --tag before
  python run_mechanism_regression.py --tag after
Output: results/mechanism_fix/regression_{tag}.json
"""
import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from run_suites import load_config, run_episode          # noqa: E402
from v2_compat import v2_diagram, v2_fairness, v2_gap    # noqa: E402

OUT = ROOT / "results" / "mechanism_fix"
OUT.mkdir(parents=True, exist_ok=True)
METHODS = ("star", "lloyd", "vfa", "pso", "random")
SEEDS = (42, 7, 123)
NS = (40, 100)
DROPS = (0.0, 0.3)


def jain_cover_fairness(sim, grid_res=250.0):
    """Jain fairness over per-agent covered grid cells (final state; post-hoc
    evaluation statistic)."""
    pos, rad = sim.positions(), sim.radii()
    xs = np.linspace(grid_res / 2, sim.width - grid_res / 2, int(sim.width / grid_res))
    ys = np.linspace(grid_res / 2, sim.height - grid_res / 2, int(sim.height / grid_res))
    gx, gy = np.meshgrid(xs, ys)
    grid = np.column_stack([gx.ravel(), gy.ravel()])
    counts = np.zeros(len(pos))
    for s in range(0, len(grid), 200000 // max(len(pos), 1)):
        g = grid[s:s + max(200000 // max(len(pos), 1), 1)]
        d2 = ((g[:, None, :] - pos[None, :, :]) ** 2).sum(-1)
        counts += (d2 <= (rad ** 2)[None, :]).sum(axis=0)
    if counts.sum() <= 0:
        return 0.0
    return float(counts.sum() ** 2 / (len(counts) * (counts ** 2).sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", choices=["before", "after", "after_calibrated"],
                    required=True)
    ap.add_argument("--k_fluid", type=float, default=None,
                    help="override fluid.k_fluid (force-calibration comparison; the "
                         "calibrated value comes from the force probe, not metric "
                         "fitting. When omitted, the config original value = literal "
                         "implementation is used)")
    a = ap.parse_args()
    cfg = load_config()
    if a.k_fluid is not None:
        cfg['fluid']['k_fluid'] = a.k_fluid
        print(f"[override] fluid.k_fluid = {a.k_fluid}", flush=True)
    out = OUT / f"regression_{a.tag}.json"
    results = {}
    if out.exists():
        with io.open(out, encoding="utf-8") as f:
            results = json.load(f)
        print(f"[resume] {len(results)} existing cases loaded", flush=True)
    for n in NS:
        for seed in SEEDS:
            for drop in DROPS:
                for m in METHODS:
                    key = f"n{n}_seed{seed}_drop{int(drop*100)}_{m}"
                    if key in results:
                        print(f"[{a.tag}] skip {key} (done)", flush=True)
                        continue
                    t0 = time.time()
                    r = run_episode(cfg, seed, mode=m, n=n, drop_rate=drop)
                    curve = np.asarray(r["curve"])
                    hit = np.where(curve >= 0.90)[0]
                    k90 = int(hit[0] * 5) if len(hit) else -1
                    # Final-state fairness/gap (v2-compatible Laguerre diagram)
                    d = v2_diagram(np.asarray(r["positions"]), np.asarray(r["radii"]),
                                   10000.0, 10000.0)
                    fair = v2_fairness(np.asarray(r["positions"]), np.asarray(r["radii"]), d)
                    gap = v2_gap(np.asarray(r["positions"]), np.asarray(r["radii"]), d)
                    rec = {"final_coverage": round(r["final_coverage"], 5),
                           "k90": k90,
                           "energy": round(float(r["energy_final"]), 1),
                           "fairness": round(float(fair), 4),
                           "gap_m": round(float(gap), 1),
                           "elapsed_s": round(time.time() - t0, 1)}
                    results[key] = rec
                    print(f"[{a.tag}] {key}: cov={rec['final_coverage']} k90={k90} "
                          f"fair={rec['fairness']} gap={rec['gap_m']} ({rec['elapsed_s']}s)",
                          flush=True)
                    with io.open(out, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
