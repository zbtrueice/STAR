# -*- coding: utf-8 -*-
"""run_f6.py -- F6 Fluid parameter robustness experiment (non-invasive runner).

Question: does the F4 conclusion (Fluid gives only a small final coverage/gap gain and
increases T90 and energy) depend on the single parameter point k_fluid = 1.9367e6?

Design:
  - Fix N=40, cluster_radius in {500,1000} m, paired seeds {42,7,123}; initialization /
    step budget / VEVF / baseline are exactly the same as F4 (reuses the run_step5
    driving definition).
  - k arms: 0 (= VEVF-only baseline, no fluid stage), 0.5x, 1.0x, 2.0x times 1.9367e6.
    No search over other parameters, no result-based parameter selection, no
    modification of the Fluid/VEVF implementation.
  - Each combination records final_coverage / T50 / T90 / gap_m / energy_final /
    overlap@120 / cluster_radius@120 / fluid_end_coverage / oscillation_count
    (definition identical to H3: one oscillation per peak-drop > 25% followed by a
    rise > 10% of coverage(t)), plus the actual fluid-stage force magnitudes mean / max /
    95th percentile (pooled per-agent force norms).
  - Summary reports mean +- SD and keeps the per-seed data; for each k arm the paired
    differences vs VEVF-only (Delta coverage / Delta T90 / Delta gap / Delta energy)
    are computed.

Data -> results/mech_verify/F6/ ; figures -> figures/mech_verify/F6/ .
Usage:  python run_f6.py [--seed 42]
"""
import argparse
import copy
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from core import Simulator  # noqa: E402
from algorithms.fluid import fluid_forces  # noqa: E402
from algorithms.vevf import vevf_forces  # noqa: E402
from evaluation.metrics import coverage_ratio  # noqa: E402
from run_step4 import (  # noqa: E402
    CAL_KFLUID, fp_from, vp_from, dense_cluster_agents, grid_mesh, t_hit,
    count_oscillations, load_step4_config,
)
from run_step5 import (  # noqa: E402  reuse the F4 metric definitions
    load_step5_config, nn_stats, cluster_radius, redundancy, at_step,
)
from v2_compat import v2_diagram, v2_gap  # noqa: E402

OUT = ROOT / "results" / "mech_verify" / "F6"
FIG = ROOT / "figures" / "mech_verify" / "F6"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)


def log(msg):
    line = "[%.1f] %s" % (time.time(), msg)
    print(line, flush=True)
    with open(OUT / "progress.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_csv(name, rows):
    if not rows:
        return
    fieldnames = []
    for r in rows:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    log(f"wrote {name} ({len(rows)} rows)")


def load_f6_config():
    cfg = load_step5_config()                 # default + step4 + step5
    p = ROOT / "configs" / "f6.yaml"
    import yaml
    with open(p, "r", encoding="utf-8") as f:
        cfg.update(yaml.safe_load(f))
    return cfg


# --------------------------------------------------------------------------- #
def drive_f6_episode(sim, agents, cfg, k_fluid, record_every, g):
    """k_fluid=None -> VEVF-only (no fluid stage); otherwise Fluid(k)+VEVF.
    Returns (ts, gap, energy, force_stats); ts rows = (step, cov, cr_max, cr_mean, nn,
    overlap)."""
    sc = cfg["simulation"]; e = cfg["environment"]
    n_fluid = sc["fluid_steps"]; n_evfa = sc["evfa_steps"]; dt = sc["timestep"]
    vp = vp_from(cfg)
    ts = []
    total = 0
    force_norms = []                          # per-agent force norms of the fluid stage
                                               # (pooled)

    def snap():
        cr_max, cr_mean = cluster_radius(sim)
        nn_m, _ = nn_stats(sim)
        ts.append((total, coverage_ratio(sim, g), cr_max, cr_mean, nn_m,
                   redundancy(sim, g)))

    snap()
    if k_fluid is not None:
        fp = fp_from(cfg)
        sim.broadcast()
        for _ in range(n_fluid):
            F = fluid_forces(agents, fp, e["width"], e["height"])
            force_norms.extend(np.linalg.norm(F, axis=1).tolist())
            sim.integrate(F, dt)
            sim.broadcast()
            total += 1
            if total % record_every == 0:
                snap()
    for _ in range(n_evfa):
        F = vevf_forces(agents, vp, e["width"], e["height"], weighted=True)
        sim.integrate(F, dt)
        sim.broadcast()
        total += 1
        if total % record_every == 0:
            snap()
    snap()
    pos = sim.positions(); rad = sim.radii()
    d = v2_diagram(pos, rad, e["width"], e["height"])
    gap = v2_gap(pos, rad, d)
    energy = float(sum(100.0 - a.energy for a in agents))
    if force_norms:
        fstats = {"force_mean": float(np.mean(force_norms)),
                  "force_max": float(np.max(force_norms)),
                  "force_p95": float(np.percentile(force_norms, 95))}
    else:
        fstats = {"force_mean": None, "force_max": None, "force_p95": None}
    return ts, gap, energy, fstats


def build_summary(rows):
    """mean +- SD + paired differences vs VEVF-only."""
    def stats(vals):
        return float(np.mean(vals)), float(np.std(vals))

    f6 = cfg_local["f6"]
    radii = f6["cluster_radii_m"]
    mults = [float(m) for m in f6["k_multipliers"]]
    summary = []
    metric_cols = ["final_coverage", "T50", "T90", "gap_m", "energy_final",
                   "overlap120", "cluster_radius120", "oscillation_count"]
    for cr in radii:
        base = [r for r in rows if int(r["cluster_radius"]) == cr
                and r["arm"] == "vevf_only"]
        for mult in mults:
            arm = "vevf_only" if mult == 0.0 else f"fluid_{mult:g}x"
            rs = [r for r in rows if int(r["cluster_radius"]) == cr
                  and r["arm"] == arm]
            row = {"cluster_radius": cr, "arm": arm, "k_mult": mult, "n": len(rs)}
            for mcol in metric_cols:
                m, s = stats([float(r[mcol]) for r in rs])
                row[f"{mcol}_mean"] = round(m, 5)
                row[f"{mcol}_sd"] = round(s, 5)
            for fcol in ("force_mean", "force_max", "force_p95"):
                vals = [float(r[fcol]) for r in rs
                        if r[fcol] not in ("", None)]
                row[f"{fcol}_mean"] = round(float(np.mean(vals)), 6) if vals else ""
            if mult != 0.0:
                # Paired difference (same seed and cr: fluid arm - vevf_only)
                for mcol in ("final_coverage", "T90", "gap_m", "energy_final"):
                    diffs = [float(rs[i][mcol]) - float(base[i][mcol])
                             for i in range(len(rs))]
                    m, s = stats(diffs)
                    row[f"delta_{mcol}_mean"] = round(m, 5)
                    row[f"delta_{mcol}_sd"] = round(s, 5)
            summary.append(row)
    write_csv("F6_summary.csv", summary)
    return summary


def run_f6(cfg):
    global cfg_local
    cfg_local = cfg
    f6 = cfg["f6"]
    s4 = cfg["step4"]
    radii = f6["cluster_radii_m"]
    seeds = f6["seeds"]
    k_base = float(f6["k_base"])
    mults = [float(m) for m in f6["k_multipliers"]]
    rec = f6["record_every"]
    n = f6["n"]
    e = cfg["environment"]
    _, _, g, _ = grid_mesh(cfg, f6["overlap_grid"])
    fe_step = int(f6["fluid_end_step"])

    rows = []
    ts_json = {}
    for cr in radii:
        for sd in seeds:
            for mult in mults:
                c2 = copy.deepcopy(cfg)
                if mult == 0.0:
                    k = None
                    arm = "vevf_only"
                else:
                    k = k_base * mult
                    c2["fluid"]["k_fluid"] = k
                    arm = f"fluid_{mult:g}x"
                agents = dense_cluster_agents(n, c2, sd, cr)
                sim = Simulator(agents, width=e["width"], height=e["height"],
                                c_th=c2["communication"]["radius"],
                                drop_rate=0.0, loss_seed=sd)
                ts, gap, energy, fstats = drive_f6_episode(sim, agents, c2, k,
                                                           rec, g)
                final_cov = ts[-1][1]
                t50 = t_hit(ts, s4["t50_target"])
                t90 = t_hit(ts, s4["target_coverage"])
                at_fe = at_step(ts, fe_step)
                osc = count_oscillations([r[1] for r in ts],
                                         s4["oscillation_drop_thresh"],
                                         s4["oscillation_rise_thresh"])
                rows.append({
                    "cluster_radius": cr, "seed": sd, "arm": arm,
                    "k_mult": mult,
                    "k_fluid": "" if k is None else k,
                    "method": "VEVF-only" if mult == 0.0 else "Fluid+VEVF",
                    "final_coverage": final_cov, "T50": t50, "T90": t90,
                    "gap_m": gap, "energy_final": energy,
                    "overlap120": at_fe[5], "cluster_radius120": at_fe[2],
                    "cov120": at_fe[1],
                    "fluid_end_coverage": at_fe[1] if k is not None else "",
                    "oscillation_count": osc,
                    "force_mean": fstats["force_mean"],
                    "force_max": fstats["force_max"],
                    "force_p95": fstats["force_p95"],
                })
                ts_json[f"cr{cr}_seed{sd}_{arm}"] = {
                    "step": [int(r[0]) for r in ts],
                    "coverage": [float(r[1]) for r in ts],
                    "cluster_radius_max": [float(r[2]) for r in ts],
                    "cluster_radius_mean": [float(r[3]) for r in ts],
                    "nn_mean": [float(r[4]) for r in ts],
                    "overlap": [float(r[5]) for r in ts],
                }
                log(f"F6 cr={cr} seed={sd} {arm}: cov {final_cov:.4f} T50 {t50} "
                    f"T90 {t90} gap {gap:.0f} E {energy:.0f} "
                    f"ov120 {at_fe[5]:.2f} cr120 {at_fe[2]:.0f} osc {osc} "
                    + ("" if k is None else
                       f"|F| mean {fstats['force_mean']:.3g} max {fstats['force_max']:.3g}"))

    write_csv("F6_parameter_sweep.csv", rows)
    (OUT / "F6_timeseries.json").write_text(
        json.dumps(ts_json, ensure_ascii=False), encoding="utf-8")
    log("wrote F6_timeseries.json")

    summary = build_summary(rows)
    log("F6 done")
    return rows, summary


def main():
    global cfg_local
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="debug: run only this seed")
    ap.add_argument("--summary-only", action="store_true",
                    help="rebuild the summary from an existing F6_parameter_sweep.csv "
                         "(no experiment run)")
    a = ap.parse_args()
    cfg = load_f6_config()
    cfg_local = cfg
    if a.seed is not None:
        cfg["f6"]["seeds"] = [a.seed]
    t0 = time.time()
    if a.summary_only:
        import csv as _csv
        rows = list(_csv.DictReader(open(OUT / "F6_parameter_sweep.csv",
                                         encoding="utf-8")))
        build_summary(rows)
        log("summary rebuilt from CSV (%.0fs)" % (time.time() - t0))
        return
    run_f6(cfg)
    log("ALL DONE (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
