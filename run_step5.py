# -*- coding: utf-8 -*-
"""run_step5.py -- Step 5 mechanism operating-regime experiments (non-invasive runner).

Goals:
  F4  verify whether Fluid is a dense-initialization regularizer (whether it reduces
      early crowding, not just the final coverage).
  H4  verify whether Hole Fill is effective only for coverage defects that VEVF cannot
      recover: construct a communication-isolated hole -- the distance from the hole
      center to the nearest agent is > C_th, forming an uncovered zone between the
      remaining subgroups that no vessel can directly perceive/communicate to.

Constraints: no modification of the Fluid/Hole Fill algorithms; no tuning; paired
seeds; the algorithms use no global information; baselines unchanged. Reuses the utility
functions of run_step4 (same metric definitions).

Data -> results/mech_verify/step5/ ; figures -> figures/mech_verify/step5/ .
Usage:
  python run_step5.py --stage f4 [--seed 42]
  python run_step5.py --stage all
"""
import argparse
import copy
import csv
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from core import Simulator  # noqa: E402
from algorithms.fluid import fluid_forces  # noqa: E402
from algorithms.vevf import vevf_forces  # noqa: E402
from algorithms.hole_fill import hole_fill_forces  # noqa: E402
from evaluation.metrics import coverage_ratio  # noqa: E402
from run_step4 import (  # noqa: E402  reuse non-invasive utilities (same metric
    # definitions)
    CAL_KFLUID, fp_from, vp_from, hp_from, dense_cluster_agents,
    grid_mesh, zone_uncovered_metrics, rebuild, deploy_stable_vevf, t_hit,
    load_step4_config,
)

OUT = ROOT / "results" / "mech_verify" / "step5"
FIG = ROOT / "figures" / "mech_verify" / "step5"
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


def load_step5_config():
    cfg = load_step4_config()                 # default.yaml + step4.yaml
    p = ROOT / "configs" / "step5.yaml"
    with open(p, "r", encoding="utf-8") as f:
        cfg.update(yaml.safe_load(f))
    return cfg


def nn_stats(sim):
    pos = sim.positions()
    n = len(pos)
    if n < 2:
        return 0.0, 0.0
    d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1)
    m = float(nn.mean())
    return m, float(nn.std() / m) if m > 1e-9 else 0.0


def cluster_radius(sim):
    pos = sim.positions()
    cent = pos.mean(axis=0)
    r = np.linalg.norm(pos - cent, axis=1)
    return float(r.max()), float(r.mean())


def redundancy(sim, grid):
    """Overlap ratio: (sum of grid points covered by each vessel - union) / union.
    > 0 means overlapping coverage exists."""
    pos = sim.positions()
    rad = sim.radii()
    d2 = np.sum((grid[:, None, :] - pos[None, :, :]) ** 2, axis=2)
    per = (d2 < (rad ** 2)[None, :]).sum(axis=0)
    union = (d2 < (rad ** 2)[None, :]).any(axis=1)
    u = int(union.sum())
    if u <= 0:
        return 0.0
    return float((float(per.sum()) - u) / u)


def first_crossing(ts, threshold):
    """ts rows are (step, cov, cr_max, ...); returns the step at which cr_max first
    exceeds the threshold."""
    for rec in ts:
        if rec[2] > threshold:
            return int(rec[0])
    return -1


def at_step(ts, step):
    """Return the ts row whose step exactly equals the given value; otherwise the last
    row."""
    for rec in ts:
        if rec[0] == step:
            return rec
    return ts[-1]


# --------------------------------------------------------------------------- #
#  F4 -- Dense Initialization Robustness
# --------------------------------------------------------------------------- #
def drive_f4_episode(sim, agents, cfg, arm, record_every, g):
    """VEVF-only or Fluid(cal)+VEVF; records coverage/overlap/cluster_radius/NN
    synchronously."""
    sc = cfg["simulation"]; e = cfg["environment"]
    n_fluid = sc["fluid_steps"]; n_evfa = sc["evfa_steps"]; dt = sc["timestep"]
    fp = fp_from(cfg); vp = vp_from(cfg)
    ts = []
    total = 0

    def snap():
        cr_max, cr_mean = cluster_radius(sim)
        nn_m, _ = nn_stats(sim)
        ts.append((total, coverage_ratio(sim, g), cr_max, cr_mean, nn_m,
                   redundancy(sim, g)))

    snap()
    if arm in ("fluid_lit", "fluid_cal"):
        sim.broadcast()
        for _ in range(n_fluid):
            F = fluid_forces(agents, fp, e["width"], e["height"])
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
    from v2_compat import v2_diagram, v2_gap
    pos = sim.positions(); rad = sim.radii()
    d = v2_diagram(pos, rad, e["width"], e["height"])
    gap = v2_gap(pos, rad, d)
    energy = float(sum(100.0 - a.energy for a in agents))
    return ts, gap, energy


def run_f4(cfg, seeds):
    s5 = cfg["step5"]
    radii = s5["cluster_radii_m"]
    thresholds = s5["f4_cr_thresholds"]
    arms = {"vevf": None, "fluid_cal": CAL_KFLUID}
    n = s5["f4_n"]; rec = cfg["step4"]["record_every"]
    e = cfg["environment"]
    _, _, g, _ = grid_mesh(cfg, s5["f4_redundancy_grid"])
    rows = []
    ts_rows = []
    for cr in radii:
        for sd in seeds:
            for aname, k in arms.items():
                c2 = copy.deepcopy(cfg)
                if k is not None:
                    c2["fluid"]["k_fluid"] = k
                agents = dense_cluster_agents(n, c2, sd, cr)
                sim = Simulator(agents, width=e["width"], height=e["height"],
                                c_th=c2["communication"]["radius"],
                                drop_rate=0.0, loss_seed=sd)
                ts, gap, energy = drive_f4_episode(sim, agents, c2, aname, rec, g)
                final_cov = ts[-1][1]
                t50 = t_hit(ts, cfg["step4"]["t50_target"])
                t90 = t_hit(ts, cfg["step4"]["target_coverage"])
                cr_at = {t: first_crossing(ts, t) for t in thresholds}
                fe = at_step(ts, 120)     # fluid_end (at the fixed budget of the
                                          # calibrated fluid stage)
                row = {
                    "cluster_radius": cr, "seed": sd, "arm": aname,
                    "method": "Fluid+VEVF" if aname.startswith("fluid") else "VEVF",
                    "k_fluid": c2["fluid"]["k_fluid"],
                    "final_coverage": final_cov, "T50": t50, "T90": t90,
                    "gap_m": gap, "energy": energy,
                    "cr0": ts[0][2], "cr120": fe[2], "cr1": ts[-1][2],
                    "nn0": ts[0][4], "nn120": fe[4], "nn1": ts[-1][4],
                    "overlap0": ts[0][5], "overlap120": fe[5],
                    "overlap1": ts[-1][5],
                }
                for t in thresholds:
                    row[f"t_cr_gt_{t}"] = cr_at[t]
                rows.append(row)
                for step, cv, crmax, crmean, nnm, oval in ts:
                    ts_rows.append({"cluster_radius": cr, "seed": sd, "arm": aname,
                                    "step": step, "coverage": cv, "overlap": oval,
                                    "cluster_radius_max": crmax,
                                    "cluster_radius_mean": crmean,
                                    "nn_mean": nnm})
                log(f"F4 cr={cr} seed={sd} {aname}: cov {final_cov:.3f} T50 {t50} "
                    f"T90 {t90} ov120 {fe[5]:.2f} cr120 {fe[2]:.0f} "
                    + " ".join(f"t>{t}={cr_at[t]}" for t in thresholds))
    write_csv("F4_dense_init.csv", rows)
    write_csv("F4_dense_init_timeseries.csv", ts_rows)
    log("F4 done")


# --------------------------------------------------------------------------- #
#  H4 -- Communication-Isolated Hole
# --------------------------------------------------------------------------- #
def inject_isolated_hole(pos, rad, cfg, sd, center, iso_dist, grid, gx, gy, res):
    """Remove the vessels nearest the hole center until the nearest remaining agent is
    farther than iso_dist from the center (communication isolation).
    Returns (inj_sim, n_removed, nearest_dist, inj_area, inj_comp, zone_r)."""
    removed = []
    while True:
        cand = [i for i in range(len(pos)) if i not in removed]
        if not cand:
            break
        dd = np.linalg.norm(pos[np.array(cand)] - center, axis=1)
        if dd.min() > iso_dist:
            break
        removed.append(cand[int(np.argmin(dd))])
    keep = [i for i in range(len(pos)) if i not in removed]
    sim = rebuild(np.array(pos)[keep], np.array(rad)[keep], cfg, sd)
    sim.broadcast()
    dd = np.linalg.norm(sim.positions() - center, axis=1)
    zone_r = max(float(iso_dist), 1000.0)
    inj_area, inj_comp, _ = zone_uncovered_metrics(sim, grid, gx, gy, center,
                                                   zone_r, res)
    return sim, len(removed), float(dd.min()), inj_area, inj_comp, zone_r


def n_subgroups(sim, c_th):
    """Number of connected components of the communication graph (post-hoc statistic,
    report only; not used by the algorithm)."""
    pos = sim.positions()
    n = len(pos)
    if n == 0:
        return 0
    adj = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2) <= c_th
    seen = [False] * n
    comps = 0
    for s in range(n):
        if seen[s]:
            continue
        comps += 1
        stack = [s]
        seen[s] = True
        while stack:
            u = stack.pop()
            for v in np.where(adj[u])[0]:
                if not seen[v]:
                    seen[v] = True
                    stack.append(int(v))
    return comps


def run_h4(cfg, seeds):
    s5 = cfg["step5"]
    e = cfg["environment"]; com = cfg["communication"]
    res = e.get("metric_grid", 250.0)
    _, _, grid, (gx, gy) = grid_mesh(cfg, res)
    center = np.array(s5["h4_center"], dtype=float)
    iso_dist = float(s5["h4_isolation_factor"]) * com["radius"]
    T = s5["h4_recover_steps"]
    frac = s5["h4_recovery_frac"]
    n = s5["h4_n"]
    rows = []
    ts_rows = []
    for sd in seeds:
        pos, rad, cov_stable = deploy_stable_vevf(cfg, sd, n)
        inj_sim, nrem, nearest, inj_area, inj_comp, zone_r = inject_isolated_hole(
            pos, rad, cfg, sd, center, iso_dist, grid, gx, gy, res)
        nsg = n_subgroups(inj_sim, com["radius"])
        log(f"H4 seed{sd}: stable {cov_stable:.4f} removed {nrem} "
            f"nearest {nearest:.0f}m (>C_th {com['radius']:.0f}) "
            f"subgroups {nsg} inj_area {inj_area/1e6:.2f} km2")
        for variant in ("off", "on"):
            hp_v = hp_from(cfg)
            if variant == "off":
                hp_v.enabled = False
            sim = rebuild([np.array(a.position, copy=True) for a in inj_sim.agents],
                          [a.radius for a in inj_sim.agents], cfg, sd)
            sim.broadcast()
            series = []
            active_sum = 0
            t_rec = None
            dt = cfg["simulation"]["timestep"]
            for t in range(T):
                f = vevf_forces(sim.agents, vp_from(cfg), e["width"], e["height"],
                                weighted=True)
                dbg = None
                if hp_v.enabled:
                    fh, dbg = hole_fill_forces(sim.agents, hp_v, e["width"],
                                               e["height"], c_th=com["radius"],
                                               return_debug=True)
                    f = f + fh
                sim.integrate(f, dt)
                sim.broadcast()
                ar, comp, _ = zone_uncovered_metrics(sim, grid, gx, gy, center,
                                                     zone_r, res)
                active = dbg["hole_active_agents"] if dbg else 0
                if active >= 1:
                    active_sum += 1
                series.append((t, coverage_ratio(sim, grid), ar, comp, active))
                if t_rec is None and inj_area > 0 and ar <= frac * inj_area:
                    t_rec = t
            ar_f, comp_f, _ = zone_uncovered_metrics(sim, grid, gx, gy, center,
                                                     zone_r, res)
            cov_f = coverage_ratio(sim, grid)
            energy = float(sum(100.0 - a.energy for a in sim.agents))
            success = (ar_f <= frac * inj_area) if inj_area > 0 else True
            rows.append({
                "seed": sd, "N": n, "variant": variant,
                "n_removed": nrem, "n_subgroups": nsg,
                "nearest_agent_dist": nearest, "isolation_target": iso_dist,
                "inj_hole_area": inj_area, "inj_largest_comp": inj_comp,
                "detection_rate": float(active_sum) / T,
                "recovery_time": -1 if t_rec is None else t_rec,
                "recovery_success": int(success),
                "final_hole_area": ar_f, "final_largest_comp": comp_f,
                "final_coverage": cov_f, "energy": energy,
            })
            for t, cv, ar, comp, act in series:
                ts_rows.append({"seed": sd, "variant": variant, "step": t,
                                "coverage": cv, "hole_area": ar,
                                "largest_comp": comp, "active": act})
            log(f"H4 seed{sd} {variant}: det {active_sum/T:.2f} rec {t_rec} "
                f"succ {int(success)} res {ar_f/1e6:.2f} km2 cov {cov_f:.4f}")
    write_csv("H4_isolated_hole.csv", rows)
    write_csv("H4_isolated_hole_timeseries.csv", ts_rows)
    log("H4 done")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["f4", "h4", "all"], default="all")
    ap.add_argument("--seed", type=int, default=None, help="debug: run only this seed")
    a = ap.parse_args()
    cfg = load_step5_config()
    s5 = cfg["step5"]
    seeds = [a.seed] if a.seed is not None else s5["seeds"]
    t0 = time.time()
    if a.stage in ("f4", "all"):
        run_f4(cfg, seeds)
    if a.stage in ("h4", "all"):
        run_h4(cfg, s5["h4_seeds"] if a.seed is None else seeds)
    log("ALL DONE (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
