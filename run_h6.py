# -*- coding: utf-8 -*-
"""run_h6.py -- H6 Hole-Fill mechanism boundary factorial experiment (non-invasive
runner).

Goal: verify whether the benefit of Hole Fill is triggered by "coverage defects beyond
local VEVF recovery / communication range", i.e., whether there is a
communication-limited regime and a transition around d/C_th ~= 1.

Factor design (N=40, stable VEVF layout, paired seeds, Hole OFF/ON):
  A: d/C_th in {0.7, 0.9, 1.0, 1.1, 1.3}   (distance from the nearest remaining agent to
                                            the hole center / communication radius)
  B: target hole diameter in {3000, 4000, 5000, 6000} m

Construction (deterministic, fixed a priori; not adjusted to results):
  Phase 1 (fix d): remove all vessels within d_target of the hole center -> the nearest
                   remaining agent is at distance >= d_target.
  Phase 2 (expand the hole, preserving d): repeatedly remove the vessel that is the
    second-nearest to the hole center (excluding the current nearest), until the largest
    uncovered component equivalent diameter reaches the target; never remove the argmin,
    so d stays unchanged throughout.
  Each combination records the actual achieved_d and nearest_agent_distance (when the
  target is unreachable the actual values are reported honestly, not replaced by the
  target values).

Constraints: no algorithm modification; baselines untouched; hole filling uses no global
information (the injection construction is experimenter behavior, same definition as
H2/H4); no tuning; paired seeds.

Data -> results/mech_verify/H6/ ; figures -> figures/mech_verify/H6/ .
Usage: python run_h6.py [--seed 42]  (single-seed debugging; no argument runs all 5
seeds)
"""
import argparse
import copy
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from core import Simulator  # noqa: E402
from algorithms.vevf import vevf_forces  # noqa: E402
from algorithms.hole_fill import hole_fill_forces  # noqa: E402
from evaluation.metrics import coverage_ratio  # noqa: E402
from run_step4 import (  # noqa: E402  reuse non-invasive utilities (same metric
    # definitions)
    hp_from, vp_from, grid_mesh, zone_uncovered_metrics, rebuild,
    deploy_stable_vevf, count_oscillations, load_step4_config,
)

OUT = ROOT / "results" / "mech_verify" / "H6"
FIG = ROOT / "figures" / "mech_verify" / "H6"
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
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log(f"wrote {name} ({len(rows)} rows)")


def load_h6_config():
    cfg = load_step4_config()                 # default + step4 (recovery period/threshold
                                               # defaults)
    p = ROOT / "configs" / "h6.yaml"
    with open(p, "r", encoding="utf-8") as f:
        cfg.update(yaml.safe_load(f))
    return cfg


# --------------------------------------------------------------------------- #
#  Hole injection: decouple d from the hole size
# --------------------------------------------------------------------------- #
def inject_h6_hole(pos, rad, cfg, sd, center, d_target, D_target,
                   grid, gx, gy, res):
    """Returns (inj_sim, info dict). info contains the actual d / achieved_diam /
    n_removed, etc."""
    h6 = cfg["h6"]
    pos = np.asarray(pos, dtype=float)
    rad = np.asarray(rad, dtype=float)
    dists = np.linalg.norm(pos - center, axis=1)
    removed = set()

    # Phase 1 -- remove all vessels within d_target (fix the isolation lower bound)
    for i in np.argsort(dists):
        if dists[i] < d_target:
            removed.add(int(i))
        else:
            break

    def keep_idx():
        return [i for i in range(len(pos)) if i not in removed]

    def measure():
        keep = keep_idx()
        sim = rebuild(pos[keep], rad[keep], cfg, sd)
        sim.broadcast()
        dd = np.linalg.norm(sim.positions() - center, axis=1)
        actual_d = float(dd.min())
        zone_r = actual_d + h6["zone_margin"]
        ar, comp, diam = zone_uncovered_metrics(sim, grid, gx, gy, center,
                                                zone_r, res)
        return sim, actual_d, zone_r, ar, comp, diam

    sim, actual_d, zone_r, ar, comp, diam = measure()
    n_phase1 = len(removed)

    # Phase 2 -- expand the hole: remove the second-nearest vessel (not the nearest)
    # until the target is reached / no progress / cap
    n_extra = 0
    prev_diam = diam
    last_removed = None
    while (diam < D_target and n_extra < h6["phase2_max_extra"]
           and len(removed) < h6["max_removed_total"]):
        cand = [i for i in keep_idx()]
        dd_all = np.linalg.norm(pos[cand] - center, axis=1)
        j_nearest = int(np.argmin(dd_all))
        cand = [i for k, i in enumerate(cand) if k != j_nearest]   # protect the nearest
        if not cand:
            break
        dd2 = np.linalg.norm(pos[cand] - center, axis=1)
        last_removed = int(cand[int(np.argmin(dd2))])
        removed.add(last_removed)
        n_extra += 1
        sim, actual_d, zone_r, ar, comp, diam = measure()
        if diam <= prev_diam + 1.0:        # no progress -> the target is physically
                                           # unreachable: roll back and stop
            removed.discard(last_removed)
            n_extra -= 1
            diam = prev_diam
            break
        prev_diam = diam

    sim, actual_d, zone_r, inj_area, inj_comp, inj_diam = measure()
    info = {
        "n_removed": len(removed), "n_phase1": n_phase1, "n_phase2": max(n_extra, 0),
        "d_target": float(d_target), "nearest_agent_dist": actual_d,
        "d_over_cth_actual": actual_d / float(cfg["communication"]["radius"]),
        "D_target": float(D_target), "achieved_diam": float(inj_diam),
        "inj_hole_area": float(inj_area), "inj_largest_comp": float(inj_comp),
        "zone_r": float(zone_r),
    }
    return sim, info


# --------------------------------------------------------------------------- #
#  Recovery phase (same protocol as H4: VEVF(+hole_fill), paired)
# --------------------------------------------------------------------------- #
def recover_h6(cfg, sim, variant, T, center, zone_r, inj_area, grid, gx, gy, res):
    e = cfg["environment"]; com = cfg["communication"]
    vp = vp_from(cfg); hp_v = hp_from(cfg)
    dt = cfg["simulation"]["timestep"]
    if variant == "off":
        hp_v.enabled = False
    series = {"steps": [], "hole_area": [], "largest_comp": [],
              "coverage": [], "active": []}
    active_sum = 0
    t_rec = None
    for t in range(T):
        f = vevf_forces(sim.agents, vp, e["width"], e["height"], weighted=True)
        dbg = None
        if hp_v.enabled:
            fh, dbg = hole_fill_forces(sim.agents, hp_v, e["width"], e["height"],
                                       c_th=com["radius"], return_debug=True)
            f = f + fh
        sim.integrate(f, dt)
        sim.broadcast()
        ar, comp, _ = zone_uncovered_metrics(sim, grid, gx, gy, center, zone_r, res)
        active = dbg["hole_active_agents"] if dbg else 0
        if active >= 1:
            active_sum += 1
        series["steps"].append(t)
        series["hole_area"].append(round(ar))
        series["largest_comp"].append(round(comp))
        series["coverage"].append(round(coverage_ratio(sim, grid), 4))
        series["active"].append(int(active))
        if t_rec is None and inj_area > 0 and ar <= cfg["h6"]["recovery_frac"] * inj_area:
            t_rec = t
    ar_f, comp_f, _ = zone_uncovered_metrics(sim, grid, gx, gy, center, zone_r, res)
    return {
        "detection_rate": round(float(active_sum) / T, 4),
        "recovery_time": -1 if t_rec is None else t_rec,
        "recovery_success": int(ar_f <= cfg["h6"]["recovery_frac"] * inj_area)
        if inj_area > 0 else 1,
        "final_hole_area": float(ar_f), "final_largest_comp": float(comp_f),
        "final_coverage": round(coverage_ratio(sim, grid), 5),
        "energy": round(float(sum(100.0 - a.energy for a in sim.agents)), 2),
        "oscillation_count": count_oscillations(
            series["hole_area"],
            cfg["step4"]["oscillation_drop_thresh"],
            cfg["step4"]["oscillation_rise_thresh"]),
    }, series


# --------------------------------------------------------------------------- #
def run_h6(cfg, seeds):
    h6 = cfg["h6"]
    e = cfg["environment"]; com = cfg["communication"]
    res = e.get("metric_grid", 250.0)
    _, _, grid, (gx, gy) = grid_mesh(cfg, res)
    center = np.array(h6["center"], dtype=float)
    T = h6["recover_steps"]
    rows = []
    series_all = []
    for sd in seeds:
        pos, rad, cov_stable = deploy_stable_vevf(cfg, sd, h6["n"])
        log(f"H6 seed{sd}: stable cov {cov_stable:.4f}")
        for ratio in h6["d_ratios"]:
            d_target = float(ratio) * com["radius"]
            for D_target in h6["hole_diameters_m"]:
                inj_sim, info = inject_h6_hole(pos, rad, cfg, sd, center,
                                               d_target, D_target, grid, gx, gy, res)
                log(f"H6 seed{sd} ratio{ratio} D{D_target}: removed {info['n_removed']} "
                    f"(p1 {info['n_phase1']} p2 {info['n_phase2']}) actual_d "
                    f"{info['nearest_agent_dist']:.0f}m ({info['d_over_cth_actual']:.2f} Cth) "
                    f"achieved_diam {info['achieved_diam']:.0f}m area "
                    f"{info['inj_hole_area']/1e6:.1f}km2")
                for variant in ("off", "on"):
                    sim = rebuild([np.array(a.position, copy=True) for a in inj_sim.agents],
                                  [a.radius for a in inj_sim.agents], cfg, sd)
                    sim.broadcast()
                    summ, series = recover_h6(cfg, sim, variant, T, center,
                                              info["zone_r"], info["inj_hole_area"],
                                              grid, gx, gy, res)
                    rows.append({
                        "seed": sd, "N": h6["n"], "d_ratio_target": ratio,
                        "D_target": D_target, "variant": variant,
                        **info, **summ,
                    })
                    series_all.append({
                        "seed": sd, "d_ratio_target": ratio, "D_target": D_target,
                        "variant": variant,
                        "nearest_agent_dist": info["nearest_agent_dist"],
                        "achieved_diam": info["achieved_diam"], **series,
                    })
                    log(f"  {variant}: det {summ['detection_rate']:.2f} "
                        f"rec {summ['recovery_time']} succ {summ['recovery_success']} "
                        f"res {summ['final_hole_area']/1e6:.2f}km2 "
                        f"cov {summ['final_coverage']:.4f} osc {summ['oscillation_count']}")
    write_csv("H6_factorial.csv", rows)
    with open(OUT / "H6_timeseries.json", "w", encoding="utf-8") as f:
        json.dump({"meta": {"seeds": seeds, "n": h6["n"],
                            "d_ratios": h6["d_ratios"],
                            "hole_diameters_m": h6["hole_diameters_m"],
                            "recover_steps": T,
                            "c_th": com["radius"]},
                   "series": series_all}, f, ensure_ascii=False)
    log(f"wrote H6_timeseries.json ({len(series_all)} series)")

    # Aggregated summary: one row per (d_ratio, D_target), OFF/ON comparison
    summ_rows = []
    for ratio in h6["d_ratios"]:
        for D_target in h6["hole_diameters_m"]:
            row = {"d_ratio_target": ratio, "D_target": D_target}
            for var, tag in (("off", "OFF"), ("on", "ON")):
                rs = [r for r in rows if r["d_ratio_target"] == ratio
                      and r["D_target"] == D_target and r["variant"] == var]
                if not rs:
                    continue
                succ = [r for r in rs if r["recovery_success"] == 1]
                row[f"success_rate_{tag}"] = round(float(np.mean(
                    [r["recovery_success"] for r in rs])), 3)
                row[f"failure_rate_{tag}"] = round(1.0 - row[f"success_rate_{tag}"], 3)
                row[f"recovery_time_{tag}"] = round(float(np.mean(
                    [r["recovery_time"] for r in succ])) if succ else -1, 1)
                row[f"final_hole_area_{tag}"] = round(float(np.mean(
                    [r["final_hole_area"] for r in rs])), 1)
                row[f"final_coverage_{tag}"] = round(float(np.mean(
                    [r["final_coverage"] for r in rs])), 5)
                row[f"detection_rate_{tag}"] = round(float(np.mean(
                    [r["detection_rate"] for r in rs])), 3)
                row[f"energy_{tag}"] = round(float(np.mean(
                    [r["energy"] for r in rs])), 2)
                row[f"nearest_agent_dist_{tag}"] = round(float(np.mean(
                    [r["nearest_agent_dist"] for r in rs])), 1)
                row[f"achieved_diam_{tag}"] = round(float(np.mean(
                    [r["achieved_diam"] for r in rs])), 1)
                row[f"oscillation_{tag}"] = round(float(np.mean(
                    [r["oscillation_count"] for r in rs])), 2)
            if "final_coverage_ON" in row and "final_coverage_OFF" in row:
                row["coverage_gain_ON_minus_OFF"] = round(
                    row["final_coverage_ON"] - row["final_coverage_OFF"], 5)
                row["success_gain_ON_minus_OFF"] = round(
                    row["success_rate_ON"] - row["success_rate_OFF"], 3)
                if row["recovery_time_ON"] > 0 and row["recovery_time_OFF"] > 0:
                    row["recovery_time_diff_ON_minus_OFF"] = round(
                        row["recovery_time_ON"] - row["recovery_time_OFF"], 1)
                else:
                    row["recovery_time_diff_ON_minus_OFF"] = None
            summ_rows.append(row)
    write_csv("H6_summary.csv", summ_rows)
    log("H6 done")
    return rows, summ_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="debug: run only this seed")
    a = ap.parse_args()
    cfg = load_h6_config()
    seeds = [a.seed] if a.seed is not None else cfg["h6"]["seeds"]
    t0 = time.time()
    run_h6(cfg, seeds)
    log("ALL DONE (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
