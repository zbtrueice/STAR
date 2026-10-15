# -*- coding: utf-8 -*-
"""MechVerify -- Fluid / Hole-Fill mechanism verification experiments (non-invasive
runner).

Step 0  probe     audit probe of the force terms / magnitudes / trigger / window
                  (read-only; prints to stdout + data block of step0_audit.md)
Step 1  fluid     fluid stage only: Fluid OFF vs ON (literal k=350) vs ON (calibrated
                  k=1.9367e6), N=20/40/60/80/100 x 3 seeds; NN distance/CV, cluster
                  radius, coverage, redundancy, force, displacement
Step 2  ablation  2x2: A(noF+noV) B(F) C(V) D(F+V) (hole filling off); N=40/100 x 3
                  seeds; plus E=calibrated F+V (N=40, force-scale control); phases
                  initial/fluid_end/final are recorded
Step 3  hole      after a stable layout, remove 1-3 vessels to create a known hole;
                  HoleFill ON vs OFF; N=40 x 3 seeds, target diameters 500-2000 m;
                  coverage/hole area/largest uncovered connected component/recovery
                  time/energy/detection rate

NON-INVASIVE: only imports the locked v3 core/algorithms/baselines; modifies no locked
file.
Data -> v3/results/mech_verify/ ; figures -> v3/figures/mech_verify/.
"""
import argparse
import copy
import json
import os
import sys
import time
import csv
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from run_suites import load_config, create_agents, _grid, run_episode  # noqa: E402
from core import Simulator, Agent  # noqa: E402
from algorithms.fluid import FluidParams, fluid_forces, compute_local_density  # noqa: E402
from algorithms.vevf import VEVFParams, vevf_forces  # noqa: E402
from algorithms.hole_fill import HoleFillParams, hole_fill_forces, _local_uncovered_targets  # noqa: E402
from evaluation.metrics import coverage_ratio, MetricsRecorder  # noqa: E402
from v2_compat import v2_diagram, v2_fairness, v2_gap  # noqa: E402

OUT = ROOT / "results" / "mech_verify"
FIG = ROOT / "figures" / "mech_verify"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

SEEDS = (42, 7, 123)
NS_FLUID = (20, 40, 60, 80, 100)
HOLE_DIAM = (500, 750, 1000, 1250, 1500, 2000)
CAL_KFLUID = 1.9367e6          # force-calibrated version (old/new force mean ratio 5533,
                               # not metric fitting)
T_RECOVER = 200                # Step-3 recovery-phase steps


def log(msg):
    line = "[%.1f] %s" % (time.time(), msg)
    print(line, flush=True)
    with open(OUT / "progress.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_cfg(k_fluid=None):
    cfg = load_config()
    if k_fluid is not None:
        cfg["fluid"]["k_fluid"] = float(k_fluid)
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


def make_sim(cfg, seed, n, drop_rate=0.0):
    e = cfg["environment"]
    com = cfg["communication"]
    agents = create_agents(n, cfg, seed)
    sim = Simulator(agents, width=e["width"], height=e["height"],
                    c_th=com["radius"], drop_rate=drop_rate, loss_seed=seed)
    return sim, agents


# --------------------------------------------------------------------------- #
#  Metric utilities
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
    cv = float(nn.std() / m) if m > 1e-9 else 0.0
    return m, cv


def cluster_radius(sim):
    pos = sim.positions()
    cent = pos.mean(axis=0)
    r = np.linalg.norm(pos - cent, axis=1)
    return float(r.max()), float(r.mean())


def redundancy(sim, grid):
    """(sum of grid points covered by each vessel - union points) / union points."""
    pos = sim.positions()
    rad = sim.radii()
    n = len(pos)
    d2 = np.sum((grid[:, None, :] - pos[None, :, :]) ** 2, axis=2)
    per = (d2 < (rad ** 2)[None, :]).sum(axis=0)
    union = (d2 < (rad ** 2)[None, :]).any(axis=1)
    u = int(union.sum())
    if u <= 0:
        return 0.0
    return float((float(per.sum()) - u) / u)


def coverage(sim, grid):
    return coverage_ratio(sim, grid)


# --------------------------------------------------------------------------- #
#  Step 0 -- audit probe (read-only)
# --------------------------------------------------------------------------- #
def probe(cfg):
    """Measure the actual magnitudes of the fluid force components and the HoleFill
    window/trigger at the dense-launch state (N=40 seed 42)."""
    e = cfg["environment"]
    out = {"N": 40, "seed": 42}
    sim, agents = make_sim(cfg, 42, 40)
    sim.broadcast()                       # first step: refresh the cache before force computation
    g = _grid(cfg, e.get("metric_grid", 250.0))
    h = cfg["fluid"]["interaction_radius"]
    w0 = 1.0 / (np.pi * h * h)
    out["W0"] = w0
    out["rest_density"] = cfg["fluid"]["rest_density"]
    out["rest_density_over_W0"] = cfg["fluid"]["rest_density"] / w0
    rhos = [compute_local_density(a, fp_from(cfg)) for a in agents]
    out["rho_mean"] = float(np.mean(rhos))
    out["rho_max"] = float(np.max(rhos))
    out["rho/rho0_mean"] = float(np.mean(rhos) / cfg["fluid"]["rest_density"])
    out["rho/rho0_max"] = float(np.max(rhos) / cfg["fluid"]["rest_density"])
    out["n_neighbors_mean"] = float(np.mean([len(a.neighbor_ids) for a in agents]))

    for label, k in [("literal", cfg["fluid"]["k_fluid"]),
                     ("calibrated", CAL_KFLUID)]:
        c2 = copy.deepcopy(cfg)
        c2["fluid"]["k_fluid"] = k
        F, dbg = fluid_forces(agents, fp_from(c2), e["width"], e["height"],
                              return_debug=True)
        # Velocity increment achievable per step (dt = 0.1)
        dt = cfg["simulation"]["timestep"]
        dv = np.linalg.norm(F, axis=1) * dt
        out[f"{label}_k"] = k
        for kk in ("pressure_force_mean", "pressure_force_max",
                   "viscosity_force_mean", "drag_force_mean",
                   "boundary_force_mean", "total_force_mean", "total_force_max",
                   "rho_mean", "pressure_mean", "pressure_max"):
            out[f"{label}_{kk}"] = dbg[kk]
        out[f"{label}_dv_step_mean"] = float(dv.mean())
        out[f"{label}_dv_step_max"] = float(dv.max())
        out[f"{label}_steps_to_vmax_mean"] = (
            float(cfg["usv"]["v_max"] / max(dv.mean(), 1e-12)))

    # HoleFill: window / trigger / candidates
    hp = hp_from(cfg)
    r_eff = hp.effective_search_radius(cfg["communication"]["radius"])
    out["holefill_effective_search_radius"] = r_eff
    out["holefill_search_radius_cfg"] = hp.search_radius
    out["holefill_c_th"] = cfg["communication"]["radius"]
    out["holefill_grid_res"] = hp.grid_res
    # Launch-cluster state: uncovered grid points inside the window (should be ~0; the
    # cluster is fully covered)
    n_cand = [_local_uncovered_targets(a, e["width"], e["height"],
                                       hp.grid_res, r_eff).shape[0]
              for a in agents]
    out["holefill_candidates_launch_mean"] = float(np.mean(n_cand))
    out["holefill_candidates_launch_max"] = int(np.max(n_cand))
    # Artificial hole: mark the area around the window center as "uncovered" to test
    # whether the trigger fires (mimicking post-removal)
    np.savez(OUT / "probe_state.npz", pos=sim.positions(), rad=sim.radii())
    (OUT / "step0_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log("probe done")
    return out


# --------------------------------------------------------------------------- #
#  Step 1 -- Fluid-only
# --------------------------------------------------------------------------- #
def step_fluid(cfg, seed, n, arm, record_every=5):
    """Run the fluid stage only (no VEVF/HoleFill). arm: off|on|cal. Returns the time
    series + final values."""
    k = CAL_KFLUID if arm == "cal" else cfg["fluid"]["k_fluid"]
    if arm == "off":
        k = None                       # zero-force stepping (positions unchanged)
    c2 = copy.deepcopy(cfg)
    if k is not None:
        c2["fluid"]["k_fluid"] = k
    fp = fp_from(c2)
    e = c2["environment"]
    sc = c2["simulation"]
    n_fluid = sc["fluid_steps"]
    dt = sc["timestep"]
    sim, agents = make_sim(c2, seed, n)
    sim.broadcast()
    g = _grid(c2, e.get("metric_grid", 250.0))
    launch = sim.positions().copy()

    ts = []
    def snap(t):
        nn_m, nn_cv = nn_stats(sim)
        cr_max, cr_mean = cluster_radius(sim)
        ts.append({
            "step": t, "nn_mean": nn_m, "nn_cv": nn_cv,
            "cluster_radius_max": cr_max, "cluster_radius_mean": cr_mean,
            "coverage": coverage(sim, g), "redundancy": redundancy(sim, g),
            "disp_mean": float(np.linalg.norm(sim.positions() - launch, axis=1).mean()),
            "disp_max": float(np.linalg.norm(sim.positions() - launch, axis=1).max()),
            "force_mean": fmean, "force_max": fmax,
        })

    fmean = fmax = 0.0
    snap(0)
    for st in range(n_fluid):
        if arm == "off":
            F = np.zeros((len(agents), 2))
        else:
            F = fluid_forces(agents, fp, e["width"], e["height"])
        if arm != "off":
            norms = np.linalg.norm(F, axis=1)
            fmean, fmax = float(norms.mean()), float(norms.max())
        sim.integrate(F, dt)
        sim.broadcast()
        if (st + 1) % record_every == 0 or st == n_fluid - 1:
            snap(st + 1)
    return ts, launch


def run_step1(cfg):
    rows = []
    ts_rows = []
    for n in NS_FLUID:
        for sd in SEEDS:
            for arm in ("off", "on", "cal"):
                ts, launch = step_fluid(cfg, sd, n, arm)
                t0, t1 = ts[0], ts[-1]
                rows.append({
                    "N": n, "seed": sd, "arm": arm,
                    "nn0": t0["nn_mean"], "nn1": t1["nn_mean"],
                    "nn_cv0": t0["nn_cv"], "nn_cv1": t1["nn_cv"],
                    "cluster_r0": t0["cluster_radius_max"],
                    "cluster_r1": t1["cluster_radius_max"],
                    "cov0": t0["coverage"], "cov1": t1["coverage"],
                    "red0": t0["redundancy"], "red1": t1["redundancy"],
                    "disp_mean": t1["disp_mean"], "disp_max": t1["disp_max"],
                    "force_mean": t1["force_mean"], "force_max": t1["force_max"],
                    "n_fluid": len(ts) - 1,
                })
                for r in ts:
                    ts_rows.append({"N": n, "seed": sd, "arm": arm, **r})
                log(f"s1 n{n} seed{sd} {arm}: cov {t0['coverage']:.3f}->{t1['coverage']:.3f} "
                    f"nn {t0['nn_mean']:.0f}->{t1['nn_mean']:.0f} disp_m {t1['disp_mean']:.0f}m "
                    f"f_m {t1['force_mean']:.3g}")
    with open(OUT / "s1_fluid_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(OUT / "s1_fluid_timeseries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ts_rows[0].keys()))
        w.writeheader(); w.writerows(ts_rows)
    # Summary JSON: means across seeds per N x arm
    summ = {}
    for n in NS_FLUID:
        for arm in ("off", "on", "cal"):
            rs = [r for r in rows if r["N"] == n and r["arm"] == arm]
            m = {k: float(np.mean([r[k] for r in rs])) for k in
                 ("nn1", "nn_cv1", "cluster_r1", "cov1", "red1",
                  "disp_mean", "disp_max", "force_mean", "force_max")}
            m0 = {k: float(np.mean([r[k] for r in rs])) for k in
                  ("nn0", "nn_cv0", "cluster_r0", "cov0", "red0")}
            summ[f"n{n}_{arm}"] = {"launch": m0, "fluid_end": m}
    (OUT / "s1_fluid_summary.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")
    log("step1 done")
    return summ


# --------------------------------------------------------------------------- #
#  Step 2 -- 2x2 ablation
# --------------------------------------------------------------------------- #
COMBOS = {
    "A_noF_noV": dict(use_fluid=False, use_vevf=False),
    "B_F_only":  dict(use_fluid=True,  use_vevf=False),
    "C_V_only":  dict(use_fluid=False, use_vevf=True),
    "D_F_V":     dict(use_fluid=True,  use_vevf=True),
}


def run_step2(cfg):
    rows = []
    curve_rows = []
    combos = dict(COMBOS)
    combos["E_calF_V"] = dict(use_fluid=True, use_vevf=True, k_fluid=CAL_KFLUID)
    for n in (40, 100):
        for sd in SEEDS:
            for cname, ckw in combos.items():
                if n == 100 and cname == "E_calF_V":
                    continue                      # E runs at N=40 only (control)
                c2 = copy.deepcopy(cfg)
                if ckw.get("k_fluid"):
                    c2["fluid"]["k_fluid"] = ckw["k_fluid"]
                r = run_episode(c2, sd, mode="star", n=n, use_fluid=ckw["use_fluid"],
                                use_vevf=ckw["use_vevf"], use_holefill=False,
                                record_every=5)
                pos = np.asarray(r["positions"]); rad = np.asarray(r["radii"])
                d = v2_diagram(pos, rad, 10000.0, 10000.0)
                fair = v2_fairness(pos, rad, d)
                gap = v2_gap(pos, rad, d)
                ph = r["phases"]
                rows.append({
                    "combo": cname, "N": n, "seed": sd,
                    "final_coverage": r["final_coverage"], "t90": r["t90"],
                    "auc": r["coverage_auc"], "energy_final": r["energy_final"],
                    "fairness": fair, "gap_m": gap,
                    "cov_initial": ph.get("initial", {}).get("coverage"),
                    "cov_fluid_end": ph.get("fluid_end", {}).get("coverage"),
                    "cov_final": ph.get("final", {}).get("coverage"),
                    "nn_initial": ph.get("initial", {}).get("nn_dist_mean"),
                    "nn_final": ph.get("final", {}).get("nn_dist_mean"),
                    "cluster_initial": ph.get("initial", {}).get("cluster_radius_max"),
                    "cluster_final": ph.get("final", {}).get("cluster_radius_max"),
                    "disp_fluid": ph.get("fluid_end", {}).get("displacement_mean"),
                    "disp_final": ph.get("final", {}).get("displacement_mean"),
                })
                curve = np.asarray(r["curve"])
                for t, v in enumerate(curve):
                    curve_rows.append({"combo": cname, "N": n, "seed": sd,
                                       "step": t * 5, "coverage": v})
                log(f"s2 {cname} n{n} seed{sd}: cov {r['final_coverage']:.4f} "
                    f"t90 {r['t90']} fair {fair:.3f} gap {gap:.1f}")
    with open(OUT / "s2_ablation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(OUT / "s2_ablation_curves.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(curve_rows[0].keys()))
        w.writeheader(); w.writerows(curve_rows)
    # Summary JSON
    summ = {}
    for n in (40, 100):
        for cname in (combos.keys() if n == 40 else
                      ("A_noF_noV", "B_F_only", "C_V_only", "D_F_V")):
            rs = [r for r in rows if r["combo"] == cname and r["N"] == n]
            m = {k: float(np.mean([r[k] for r in rs])) for k in
                 ("final_coverage", "t90", "fairness", "gap_m", "energy_final",
                  "cov_initial", "cov_final")}
            fe = [r["cov_fluid_end"] for r in rs if r["cov_fluid_end"] is not None]
            m["cov_fluid_end"] = float(np.mean(fe)) if fe else None
            summ[f"n{n}_{cname}"] = m
    (OUT / "s2_ablation.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")
    log("step2 done")
    return summ


# --------------------------------------------------------------------------- #
#  Step 3 -- artificial Hole Recovery
# --------------------------------------------------------------------------- #
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
    """Area of uncovered grid points in the zone / largest connected component
    (equivalent diameter) / diameter."""
    cov = covered_mask(sim, grid)
    unc = (~cov)
    area = 0
    diam = 0.0
    max_comp = 0.0
    gx2 = gx; gy2 = gy
    in_zone = np.sum((np.column_stack([gx2.ravel(), gy2.ravel()]) - center) ** 2,
                     axis=1) <= zone_r ** 2
    area = int((unc & in_zone).sum()) * res * res
    # 8-connected components (within the zone bounding box)
    from scipy import ndimage
    zb = (gx2 >= (center[0] - zone_r)) & (gx2 <= (center[0] + zone_r))
    yb = (gy2 >= (center[1] - zone_r)) & (gy2 <= (center[1] + zone_r))
    m = (~cov).reshape(gx2.shape) & (zb & yb)
    lab, k = ndimage.label(m)
    if k > 0:
        sizes = ndimage.sum(m, lab, range(1, k + 1))
        max_comp = float(sizes.max()) * res * res
        diam = 2.0 * np.sqrt(max_comp / np.pi)
    return area, max_comp, diam


def deploy_stable(cfg, seed, n=40):
    """Run the current algorithm (fluid+vevf+holefill) to a stable layout and save the
    final state."""
    r = run_episode(cfg, seed, mode="star", n=n, use_holefill=True, record_every=5)
    return np.asarray(r["positions"]), np.asarray(r["radii"]), r["final_coverage"]


def run_step3(cfg):
    e = cfg["environment"]
    res = e.get("metric_grid", 250.0)
    xs, ys, grid, (gx, gy) = grid_mesh(cfg, res)
    com = cfg["communication"]
    vp = vp_from(cfg)
    hp = hp_from(cfg)
    dt = cfg["simulation"]["timestep"]

    def rebuild(keep_pos, keep_rad, sd):
        # Note: Agent.__init__ uses np.asarray, which does not copy float64 views; an
        # explicit copy is required, otherwise agent movement during the recovery phase
        # writes back into keep_pos in place (aliasing contaminates later variants /
        # layouts)
        agents = [Agent(0, np.array(keep_pos[i], dtype=float, copy=True),
                        keep_rad[i], v_max=cfg["usv"]["v_max"],
                        seed=sd * 1000 + i) for i in range(len(keep_pos))]
        return Simulator(agents, width=e["width"], height=e["height"],
                         c_th=com["radius"], drop_rate=0.0, loss_seed=sd)

    rows = []
    ts_rows = []
    seeds3 = (tuple(int(x) for x in os.environ["MECH_SEEDS"].split(","))
              if os.environ.get("MECH_SEEDS") else SEEDS)
    for sd in seeds3:
        pos, rad, cov_stable = deploy_stable(cfg, sd, 40)
        log(f"s3 seed{sd}: stable cov {cov_stable:.4f}")
        np.savez(OUT / f"s3_layout_seed{sd}.npz", pos=pos, rad=rad)
        center = np.array([e["width"] / 2, e["height"] / 2])
        for target_d in HOLE_DIAM:
            zone_r = max(float(target_d), 1000.0)
            # Greedy removal: nearest to the anchor point, until the largest uncovered
            # component equivalent diameter in the zone reaches >= target (cap 3 vessels)
            removed = []
            achieved_d = 0.0
            for _ in range(3):
                cand = [i for i in range(len(pos)) if i not in removed]
                d = np.linalg.norm(pos[np.array(cand)] - center, axis=1)
                rem = cand[int(np.argmin(d))]
                removed.append(rem)
                keep_pos = np.array([pos[i] for i in range(len(pos)) if i not in removed])
                keep_rad = np.array([rad[i] for i in range(len(pos)) if i not in removed])
                sim_tmp = rebuild(keep_pos, keep_rad, sd)
                sim_tmp.broadcast()
                a_, c_, d_ = zone_uncovered_metrics(sim_tmp, grid, gx, gy,
                                                    center, zone_r, res)
                if d_ >= target_d:
                    break
                achieved_d = d_
            n_removed = len(removed)
            achieved_d = max(achieved_d, d_)
            keep_pos = np.array([pos[i] for i in range(len(pos)) if i not in removed])
            keep_rad = np.array([rad[i] for i in range(len(pos)) if i not in removed])
            inj_sim = rebuild(keep_pos, keep_rad, sd)
            inj_sim.broadcast()
            inj_area, inj_comp, _ = zone_uncovered_metrics(inj_sim, grid, gx, gy,
                                                           center, zone_r, res)
            for variant in ("off", "on"):
                hp_v = copy.deepcopy(hp)
                if variant == "off":
                    hp_v.enabled = False
                sim = rebuild(keep_pos, keep_rad, sd)
                sim.broadcast()
                rec_series = []
                detected_steps = 0
                t_rec = None
                for t in range(T_RECOVER):
                    f = vevf_forces(sim.agents, vp, e["width"], e["height"],
                                    weighted=True)
                    dbg = None
                    if hp_v.enabled:
                        fh, dbg = hole_fill_forces(sim.agents, hp_v, e["width"],
                                                   e["height"], c_th=com["radius"],
                                                   return_debug=True)
                        f = f + fh
                    sim.integrate(f, dt)
                    sim.broadcast()
                    ar, comp, dm = zone_uncovered_metrics(sim, grid, gx, gy,
                                                          center, zone_r, res)
                    active = dbg["hole_active_agents"] if dbg else 0
                    if active >= 1:
                        detected_steps += 1
                    rec_series.append((t, coverage(sim, grid), ar, comp, active))
                    if t_rec is None and ar <= 0.2 * inj_area:
                        t_rec = t
                ar, comp, dm = zone_uncovered_metrics(sim, grid, gx, gy,
                                                      center, zone_r, res)
                energy_used = sum(100.0 - a.energy for a in sim.agents)
                rows.append({
                    "seed": sd, "target_diam": target_d, "achieved_diam": achieved_d,
                    "n_removed": n_removed, "variant": variant,
                    "inj_hole_area": inj_area, "inj_largest_comp": inj_comp,
                    "final_coverage": coverage(sim, grid),
                    "final_hole_area": ar, "final_largest_comp": comp,
                    "recovery_time": -1 if t_rec is None else t_rec,
                    "energy_final": energy_used,
                    "detection_rate": float(detected_steps) / T_RECOVER,
                })
                for t, cv, ar, comp, act in rec_series:
                    ts_rows.append({"seed": sd, "target_diam": target_d,
                                    "variant": variant, "step": t,
                                    "coverage": cv, "hole_area": ar,
                                    "largest_comp": comp, "active": act})
                log(f"s3 seed{sd} tgt{target_d} rem{n_removed} achd {achieved_d:.0f} "
                    f"{variant}: final_cov {coverage(sim, grid):.3f} rec_time "
                    f"{t_rec} det {detected_steps}")
    with open(OUT / "s3_hole.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    with open(OUT / "s3_hole_timeseries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ts_rows[0].keys()))
        w.writeheader(); w.writerows(ts_rows)
    summ = {}
    for tgt in HOLE_DIAM:
        for var in ("off", "on"):
            rs = [r for r in rows if r["target_diam"] == tgt and r["variant"] == var]
            m = {k: float(np.mean([r[k] for r in rs])) for k in
                 ("achieved_diam", "final_coverage", "final_hole_area",
                  "final_largest_comp", "recovery_time", "energy_final",
                  "detection_rate")}
            m["n_removed_mean"] = float(np.mean([r["n_removed"] for r in rs]))
            summ[f"t{tgt}_{var}"] = m
    (OUT / "s3_hole.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")
    log("step3 done")
    return summ


# --------------------------------------------------------------------------- #
#  main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["probe", "1", "2", "3"], required=True)
    ap.add_argument("--seed", type=int, default=None, help="debug: run a single seed")
    a = ap.parse_args()
    cfg = load_config()
    if a.stage == "probe":
        p = probe(cfg)
        print(json.dumps(p, ensure_ascii=False, indent=2))
        (OUT / "step0_audit_probe.json").write_text(
            json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if a.stage == "1":
        run_step1(cfg)
    elif a.stage == "2":
        run_step2(cfg)
    elif a.stage == "3":
        run_step3(cfg)


if __name__ == "__main__":
    main()
