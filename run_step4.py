# -*- coding: utf-8 -*-
"""run_step4.py -- Step 4 operating-regime experiments (non-invasive runner).

Based on the corrected locked v3 code and the methodology of results/mech_verify/,
explores the effective operating regimes of the two mechanisms:

  F2  Dense-cluster Fluid test    N=40, cluster radii 500/1000/1500/2000 m; VEVF vs
                                  Fluid+VEVF
  F3  Communication-loss test     N=40, packet loss 0/10/30/50/70%; VEVF vs Fluid+VEVF
  H2  Hole operating regime       N=20/30/40, hole diameters 500-2500 m, positions
                                  center/boundary/sparse_edge; Hole OFF vs ON
  H3  Hole force-conflict test    fixed layout/hole/seed; only sweeps
                                  hole_fill.f_max = 50-600

Design decisions (consistent with mech_verify):
- The Fluid+VEVF arm runs both the "literal k=350 (config default)" and the
  "force-calibrated k=1.9367e6" configurations, so that a force-scaling issue is not
  misdiagnosed as a mechanism failure (see mech_verify Step 1/2). F2/F3 primary
  comparisons use the calibrated version.
- Both arms of F2/F3 disable hole filling (use_holefill=False) to isolate the
  independent contribution of the fluid.
- H2/H3 deployment = a pure VEVF stable layout (use_fluid=False, use_holefill=False);
  the hole-recovery baseline OFF=VEVF, ON=VEVF+hole_fill, a clean pairing.
- All parameters come from configs/step4.yaml (stacked on default.yaml); nothing is
  hard-coded; no algorithm file is modified.

Data -> results/mech_verify/step4/ ; figures -> figures/mech_verify/step4/ .
Usage:
  python run_step4.py --stage f2 [--seed 42]   # single-seed debugging
  python run_step4.py --stage all
"""
import argparse
import copy
import csv
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
from run_suites import load_config, _grid, create_agents, run_episode  # noqa: E402
from core import Simulator, Agent  # noqa: E402
from algorithms.fluid import FluidParams, fluid_forces  # noqa: E402
from algorithms.vevf import VEVFParams, vevf_forces  # noqa: E402
from algorithms.hole_fill import HoleFillParams, hole_fill_forces  # noqa: E402
from evaluation.metrics import coverage_ratio  # noqa: E402
from v2_compat import v2_diagram, v2_fairness, v2_gap  # noqa: E402

OUT = ROOT / "results" / "mech_verify" / "step4"
FIG = ROOT / "figures" / "mech_verify" / "step4"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

CAL_KFLUID = 1.9367e6


def log(msg):
    line = "[%.1f] %s" % (time.time(), msg)
    print(line, flush=True)
    with open(OUT / "progress.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_step4_config():
    cfg = load_config()                       # default.yaml
    p = ROOT / "configs" / "step4.yaml"
    with open(p, "r", encoding="utf-8") as f:
        extra = yaml.safe_load(f)
    cfg.update(extra)                         # stack the step4 section
    return cfg


def fp_from(cfg):
    c = cfg["fluid"]
    return FluidParams(**{k: c[k] for k in
                          ("interaction_radius", "k_fluid", "rest_density",
                           "viscosity", "drag", "boundary_k")})


def vp_from(cfg):
    c = cfg["vevf"]
    return VEVFParams(**{k: c[k] for k in c})


def hp_from(cfg):
    c = cfg["hole_fill"]
    return HoleFillParams(**{k: c[k] for k in c})


# --------------------------------------------------------------------------- #
#  Layout / metric utilities
# --------------------------------------------------------------------------- #
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


def dense_cluster_agents(n, cfg, seed, cluster_radius_m):
    """Dense-launch cluster layout: initial positions drawn uniformly in a disk centered
    at the ROI center with radius cluster_radius_m, then normalized so that the initial
    cluster_radius_max equals the target radius. Only the initial layout changes; no
    algorithm modification."""
    u, e = cfg["usv"], cfg["environment"]
    rng = np.random.default_rng(seed)
    nh = round(n * u["high_ratio"]); nm = round(n * u["medium_ratio"])
    nl = n - nh - nm
    radii = ([u["high_radius"]] * nh + [u["medium_radius"]] * nm + [u["low_radius"]] * nl)
    ang = rng.uniform(0, 2 * np.pi, n)
    rr = float(cluster_radius_m) * np.sqrt(rng.uniform(0, 1, n))   # area-uniform disk
    pos = np.column_stack([e["width"] / 2 + rr * np.cos(ang),
                           e["height"] / 2 + rr * np.sin(ang)])
    # Normalize so that max radius == target
    c = np.linalg.norm(pos - np.array([e["width"] / 2, e["height"] / 2]), axis=1)
    s = float(cluster_radius_m) / max(c.max(), 1e-9)
    pos = np.array([e["width"] / 2, e["height"] / 2]) + s * (pos - np.array(
        [e["width"] / 2, e["height"] / 2]))
    return [Agent(i, np.array(pos[i], copy=True), radii[i],
                  v_max=u["v_max"], seed=seed + i) for i in range(n)]


def grid_mesh(cfg, res=None):
    e = cfg["environment"]
    res = res or e.get("metric_grid", 250.0)
    xs = np.arange(res / 2, e["width"], res)
    ys = np.arange(res / 2, e["height"], res)
    gx, gy = np.meshgrid(xs, ys)
    return xs, ys, np.column_stack([gx.ravel(), gy.ravel()]), (gx, gy)


def covered_mask(sim, grid):
    pos = sim.positions(); rad = sim.radii()
    d2 = np.sum((grid[:, None, :] - pos[None, :, :]) ** 2, axis=2)
    return (d2 < (rad ** 2)[None, :]).any(axis=1)


def zone_uncovered_metrics(sim, grid, gx, gy, center, zone_r, res):
    """Uncovered grid-point area inside the zone / area of the largest uncovered
    connected component / equivalent diameter."""
    cov = covered_mask(sim, grid)
    unc = (~cov)
    in_zone = np.sum((np.column_stack([gx.ravel(), gy.ravel()]) - center) ** 2,
                     axis=1) <= zone_r ** 2
    area = int((unc & in_zone).sum()) * res * res
    from scipy import ndimage
    zb = (gx >= (center[0] - zone_r)) & (gx <= (center[0] + zone_r))
    yb = (gy >= (center[1] - zone_r)) & (gy <= (center[1] + zone_r))
    m = (~cov).reshape(gx.shape) & (zb & yb)
    lab, k = ndimage.label(m)
    max_comp = 0.0
    if k > 0:
        sizes = ndimage.sum(m, lab, range(1, k + 1))
        max_comp = float(sizes.max()) * res * res
    diam = 2.0 * np.sqrt(max_comp / np.pi) if max_comp > 0 else 0.0
    return area, max_comp, diam


def t_hit(ts, target):
    """ts: [(step, coverage, ...), ...]; returns the first step with coverage >= target,
    or -1 if never reached."""
    for rec in ts:
        if rec[1] >= target:
            return int(rec[0])
    return -1


# --------------------------------------------------------------------------- #
#  F2 -- Dense-cluster Fluid test
# --------------------------------------------------------------------------- #
def drive_episode(sim, agents, cfg, arm, record_every=5):
    """VEVF-only or Fluid(literal/calibrated)+VEVF; returns the time series + final
    metrics.
    arm: 'vevf' | 'fluid_lit' | 'fluid_cal'"""
    sc = cfg["simulation"]; e = cfg["environment"]
    n_fluid = sc["fluid_steps"]; n_evfa = sc["evfa_steps"]; dt = sc["timestep"]
    g = _grid(cfg, e.get("metric_grid", 250.0))
    ts = []
    total = 0

    def snap():
        cr_max, cr_mean = cluster_radius(sim)
        nn_m, nn_cv = nn_stats(sim)
        ts.append((total, coverage_ratio(sim, g), cr_max, cr_mean, nn_m, nn_cv))

    snap()
    if arm in ("fluid_lit", "fluid_cal"):
        fp = fp_from(cfg)
        sim.broadcast()
        for _ in range(n_fluid):
            F = fluid_forces(agents, fp, e["width"], e["height"])
            sim.integrate(F, dt)
            sim.broadcast()
            total += 1
            if total % record_every == 0:
                snap()
    vp = vp_from(cfg)
    for _ in range(n_evfa):
        F = vevf_forces(agents, vp, e["width"], e["height"], weighted=True)
        sim.integrate(F, dt)
        sim.broadcast()
        total += 1
        if total % record_every == 0:
            snap()
    snap()                                    # final state (guarantees last-step coverage)
    pos = sim.positions(); rad = sim.radii()
    d = v2_diagram(pos, rad, e["width"], e["height"])
    gap = v2_gap(pos, rad, d)
    energy = float(sum(100.0 - a.energy for a in agents))
    return ts, gap, energy


def run_f2(cfg, seeds):
    s4 = cfg["step4"]
    radii = s4["cluster_radii_m"]
    arms = {"vevf": None, "fluid_lit": cfg["fluid"]["k_fluid"], "fluid_cal": CAL_KFLUID}
    n = s4["f2_n"]; rec = s4["record_every"]
    rows = []
    ts_rows = []
    for cr in radii:
        for sd in seeds:
            for aname, k in arms.items():
                c2 = copy.deepcopy(cfg)
                if k is not None:
                    c2["fluid"]["k_fluid"] = k
                agents = dense_cluster_agents(n, c2, sd, cr)
                sim = Simulator(agents, width=c2["environment"]["width"],
                                height=c2["environment"]["height"],
                                c_th=c2["communication"]["radius"],
                                drop_rate=0.0, loss_seed=sd)
                ts, gap, energy = drive_episode(sim, agents, c2, aname, rec)
                final_cov = ts[-1][1]
                t50 = t_hit(ts, s4["t50_target"])
                t90 = t_hit(ts, s4["target_coverage"])
                rows.append({
                    "cluster_radius": cr, "seed": sd, "arm": aname,
                    "method": "Fluid+VEVF" if aname.startswith("fluid") else "VEVF",
                    "k_fluid": c2["fluid"]["k_fluid"],
                    "final_coverage": final_cov, "T50": t50, "T90": t90,
                    "gap_m": gap, "energy": energy,
                    "cr0": ts[0][2], "cr1": ts[-1][2],
                    "nn0": ts[0][4], "nn1": ts[-1][4],
                })
                for step, cv, crmax, crmean, nnm, nncv in ts:
                    ts_rows.append({"cluster_radius": cr, "seed": sd, "arm": aname,
                                    "step": step, "coverage": cv,
                                    "cluster_radius_max": crmax,
                                    "cluster_radius_mean": crmean,
                                    "nn_mean": nnm, "nn_cv": nncv})
                log(f"F2 cr={cr} seed={sd} {aname}: cov {final_cov:.3f} "
                    f"T50 {t50} T90 {t90} gap {gap:.0f}m")
    write_csv("F2_dense_cluster.csv", rows)
    write_csv("F2_dense_cluster_timeseries.csv", ts_rows)
    log("F2 done")


# --------------------------------------------------------------------------- #
#  F3 -- Communication-loss test
# --------------------------------------------------------------------------- #
def run_f3(cfg, seeds):
    s4 = cfg["step4"]
    drops = s4["packet_loss"]
    arms = {"vevf": None, "fluid_lit": cfg["fluid"]["k_fluid"], "fluid_cal": CAL_KFLUID}
    n = s4["f3_n"]
    rows = []
    for dp in drops:
        for sd in seeds:
            for aname, k in arms.items():
                c2 = copy.deepcopy(cfg)
                if k is not None:
                    c2["fluid"]["k_fluid"] = k
                # F3 uses the standard dense-launch layout (create_agents, same
                # definition as the paper packet-loss suite) for cross-experiment
                # comparability; both arms share the same layout and seed (paired
                # comparison).
                agents = create_agents(n, c2, sd)
                sim = Simulator(agents, width=c2["environment"]["width"],
                                height=c2["environment"]["height"],
                                c_th=c2["communication"]["radius"],
                                drop_rate=dp, loss_seed=sd)
                ts, gap, energy = drive_episode(sim, agents, c2, aname)
                final_cov = ts[-1][1]
                t90 = t_hit(ts, s4["target_coverage"])
                rows.append({
                    "packet_loss": dp, "seed": sd, "arm": aname,
                    "method": "Fluid+VEVF" if aname.startswith("fluid") else "VEVF",
                    "k_fluid": c2["fluid"]["k_fluid"],
                    "final_coverage": final_cov, "T90": t90, "gap_m": gap,
                    "energy": energy, "failed": int(t90 == -1),
                })
                log(f"F3 drop={dp} seed={sd} {aname}: cov {final_cov:.3f} "
                    f"T90 {t90} gap {gap:.0f}m")
    write_csv("F3_packet_loss.csv", rows)
    # Aggregation: failure rate = fraction of seeds not reaching T90 under this
    # condition (packet loss x arm)
    summ = []
    for dp in drops:
        for aname in arms:
            rs = [r for r in rows if r["packet_loss"] == dp and r["arm"] == aname]
            summ.append({
                "packet_loss": dp, "arm": aname,
                "failure_rate": float(np.mean([r["failed"] for r in rs])),
                "mean_coverage": float(np.mean([r["final_coverage"] for r in rs])),
                "mean_T90": float(np.mean([r["T90"] for r in rs])),
                "mean_gap_m": float(np.mean([r["gap_m"] for r in rs])),
            })
    write_csv("F3_packet_loss_summary.csv", summ)
    log("F3 done")


# --------------------------------------------------------------------------- #
#  H2/H3 shared: stable deployment + hole injection + recovery
# --------------------------------------------------------------------------- #
def deploy_stable_vevf(cfg, seed, n):
    """Pure VEVF stable layout (no fluid, no hole filling), serving as a clean baseline
    for hole recovery."""
    r = run_episode(cfg, seed, mode="star", n=n, use_fluid=False,
                    use_vevf=True, use_holefill=False, record_every=5)
    return np.array([np.array(p, copy=True) for p in r["positions"]]), \
        np.array([float(x) for x in r["radii"]]), r["final_coverage"]


def rebuild(keep_pos, keep_rad, cfg, sd):
    """Rebuild the sim from the retained positions; note that Agent.__init__ does not
    copy views, so explicit copies are required."""
    e = cfg["environment"]; com = cfg["communication"]
    agents = [Agent(0, np.array(keep_pos[i], dtype=float, copy=True),
                    float(keep_rad[i]), v_max=cfg["usv"]["v_max"],
                    seed=sd * 1000 + i) for i in range(len(keep_pos))]
    return Simulator(agents, width=e["width"], height=e["height"],
                     c_th=com["radius"], drop_rate=0.0, loss_seed=sd)


def inject_hole(pos, rad, cfg, sd, center, target_diam, max_removed,
                grid, gx, gy, res):
    """Greedily remove the vessels nearest the hole center until the largest uncovered
    component diameter in the zone reaches >= target (capped at max_removed).
    Returns (post-injection sim, removed count, injected hole area, injected largest
    component, achieved diameter, zone_r)."""
    zone_r = max(float(target_diam), 1000.0)
    removed = []
    d_last = 0.0
    for _ in range(max_removed):
        cand = [i for i in range(len(pos)) if i not in removed]
        if not cand:
            break
        dd = np.linalg.norm(pos[np.array(cand)] - center, axis=1)
        rem = cand[int(np.argmin(dd))]
        removed.append(rem)
        keep = [i for i in range(len(pos)) if i not in removed]
        sim_tmp = rebuild(np.array(pos)[keep], np.array(rad)[keep], cfg, sd)
        sim_tmp.broadcast()
        _, _, d_ = zone_uncovered_metrics(sim_tmp, grid, gx, gy, center, zone_r, res)
        d_last = d_
        if d_ >= target_diam:
            break
    keep = [i for i in range(len(pos)) if i not in removed]
    sim = rebuild(np.array(pos)[keep], np.array(rad)[keep], cfg, sd)
    sim.broadcast()
    inj_area, inj_comp, _ = zone_uncovered_metrics(sim, grid, gx, gy, center, zone_r, res)
    return sim, len(removed), inj_area, inj_comp, d_last, zone_r


def recover(cfg, sim, hp_v, T, center, zone_r, inj_area, grid, gx, gy, res,
            track_series=True):
    """VEVF(+hole_fill) recovery phase; returns (summary dict, series list)."""
    e = cfg["environment"]; com = cfg["communication"]
    vp = vp_from(cfg); dt = cfg["simulation"]["timestep"]
    series = []
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
        if track_series:
            series.append((t, coverage_ratio(sim, grid), ar, comp, active))
        if t_rec is None and inj_area > 0 and ar <= cfg["step4"]["recovery_frac"] * inj_area:
            t_rec = t
    ar, comp, _ = zone_uncovered_metrics(sim, grid, gx, gy, center, zone_r, res)
    energy = float(sum(100.0 - a.energy for a in sim.agents))
    return {
        "recovery_time": -1 if t_rec is None else t_rec,
        "final_hole_area": ar, "final_largest_comp": comp,
        "final_coverage": coverage_ratio(sim, grid),
        "energy": energy,
        "detection_rate": float(active_sum) / T,
    }, series


def count_oscillations(areas, drop_thresh, rise_thresh):
    """Oscillation: the hole area drops clearly from a peak (> drop) and then rises
    clearly again (> rise). Each peak -> trough -> peak triple is judged."""
    a = list(areas)
    if len(a) < 4:
        return 0
    ext = []
    for i in range(1, len(a) - 1):
        if a[i] > a[i - 1] and a[i] >= a[i + 1]:
            ext.append((i, "peak"))
        elif a[i] < a[i - 1] and a[i] <= a[i + 1]:
            ext.append((i, "trough"))
    cnt = 0
    for k in range(len(ext) - 2):
        e0, e1, e2 = ext[k], ext[k + 1], ext[k + 2]
        if e0[1] == "peak" and e1[1] == "trough" and e2[1] == "peak":
            drop = (a[e0[0]] - a[e1[0]]) / max(a[e0[0]], 1e-9)
            rise = (a[e2[0]] - a[e1[0]]) / max(a[e1[0]], 1e-9)
            if drop > drop_thresh and rise > rise_thresh:
                cnt += 1
    return cnt


# --------------------------------------------------------------------------- #
#  H2 -- Hole operating regime
# --------------------------------------------------------------------------- #
def run_h2(cfg, seeds):
    s4 = cfg["step4"]
    res = cfg["environment"].get("metric_grid", 250.0)
    xs, ys, grid, (gx, gy) = grid_mesh(cfg, res)
    rows = []
    ts_rows = []
    for n in s4["hole_n"]:
        for sd in seeds:
            pos, rad, cov_stable = deploy_stable_vevf(cfg, sd, n)
            log(f"H2 deploy n{n} seed{sd}: stable cov {cov_stable:.4f}")
            for pname, pcenter in s4["hole_positions"].items():
                center = np.array(pcenter, dtype=float)
                for tgt in s4["hole_diameters_m"]:
                    inj_sim, nrem, inj_area, inj_comp, achd, zone_r = inject_hole(
                        pos, rad, cfg, sd, center, tgt, s4["max_removed_agents"],
                        grid, gx, gy, res)
                    hp0 = hp_from(cfg)
                    for variant in ("off", "on"):
                        hp_v = copy.deepcopy(hp0)
                        if variant == "off":
                            hp_v.enabled = False
                        sim = rebuild([np.array(a.position, copy=True)
                                       for a in inj_sim.agents],
                                      [a.radius for a in inj_sim.agents], cfg, sd)
                        sim.broadcast()
                        summ, series = recover(
                            cfg, sim, hp_v, s4["recover_steps"], center, zone_r,
                            inj_area, grid, gx, gy, res)
                        rows.append({
                            "N": n, "seed": sd, "position": pname,
                            "target_diam": tgt, "achieved_diam": achd,
                            "n_removed": nrem, "variant": variant,
                            "inj_hole_area": inj_area, "inj_largest_comp": inj_comp,
                            **summ,
                        })
                        for t, cv, ar, comp, act in series:
                            ts_rows.append({"N": n, "seed": sd, "position": pname,
                                            "target_diam": tgt, "variant": variant,
                                            "step": t, "coverage": cv,
                                            "hole_area": ar, "largest_comp": comp,
                                            "active": act})
                        log(f"H2 n{n} seed{sd} {pname} tgt{tgt} rem{nrem} "
                            f"achd {achd:.0f} {variant}: cov {summ['final_coverage']:.3f} "
                            f"rec {summ['recovery_time']} det {summ['detection_rate']:.2f}")
    write_csv("H2_operating_regime.csv", rows)
    write_csv("H2_operating_regime_timeseries.csv", ts_rows)
    log("H2 done")


# --------------------------------------------------------------------------- #
#  H3 -- Hole force-conflict test
# --------------------------------------------------------------------------- #
def run_h3(cfg):
    s4 = cfg["step4"]
    sd = s4["h3_seed"]; n = s4["h3_n"]
    res = cfg["environment"].get("metric_grid", 250.0)
    xs, ys, grid, (gx, gy) = grid_mesh(cfg, res)
    pos, rad, cov_stable = deploy_stable_vevf(cfg, sd, n)
    center = np.array(s4["hole_positions"][s4["h3_position"]], dtype=float)
    tgt = s4["h3_diameter_m"]
    inj_sim, nrem, inj_area, inj_comp, achd, zone_r = inject_hole(
        pos, rad, cfg, sd, center, tgt, s4["max_removed_agents"], grid, gx, gy, res)
    log(f"H3 deploy n{n} seed{sd} stable {cov_stable:.4f}; inject d~{achd:.0f} "
        f"area {inj_area}")
    rows = []
    for fmax in s4["h3_fmax_list"]:
        hp_v = hp_from(cfg)
        hp_v.f_max = float(fmax)
        sim = rebuild([np.array(a.position, copy=True) for a in inj_sim.agents],
                      [a.radius for a in inj_sim.agents], cfg, sd)
        sim.broadcast()
        summ, series = recover(cfg, sim, hp_v, s4["recover_steps"], center, zone_r,
                               inj_area, grid, gx, gy, res)
        areas = [ar for _, _, ar, _, _ in series]
        osc = count_oscillations(areas, s4["oscillation_drop_thresh"],
                                 s4["oscillation_rise_thresh"])
        rows.append({"hole_fmax": fmax, "seed": sd, "N": n,
                     "target_diam": tgt, "achieved_diam": achd,
                     "n_removed": nrem, "inj_hole_area": inj_area,
                     **summ, "oscillation_count": osc})
        log(f"H3 fmax={fmax}: rec {summ['recovery_time']} res {summ['final_hole_area']} "
            f"cov {summ['final_coverage']:.3f} osc {osc}")
    write_csv("H3_force_sweep.csv", rows)
    log("H3 done")


# --------------------------------------------------------------------------- #
#  main
# --------------------------------------------------------------------------- #
def write_csv(name, rows):
    if not rows:
        return
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log(f"wrote {name} ({len(rows)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["f2", "f3", "h2", "h3", "all"],
                    default="all")
    ap.add_argument("--seed", type=int, default=None, help="debug: run only this seed")
    a = ap.parse_args()
    cfg = load_step4_config()
    s4 = cfg["step4"]
    seeds = [a.seed] if a.seed is not None else s4["seeds"]
    t0 = time.time()
    if a.stage in ("f2", "all"):
        run_f2(cfg, seeds)
    if a.stage in ("f3", "all"):
        run_f3(cfg, seeds)
    if a.stage in ("h2", "all"):
        run_h2(cfg, s4["h2_seeds"] if a.seed is None else seeds)
    if a.stage in ("h3", "all"):
        run_h3(cfg)
    log("ALL DONE (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
