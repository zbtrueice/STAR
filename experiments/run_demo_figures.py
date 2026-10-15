# -*- coding: utf-8 -*-
"""
run_demo_figures.py — recording runner for the reviewer-grade "figure pack"
(N4 evolution snapshots, N5 convergence error-shadow, N6 fluid mechanism,
and full-axis baseline sweep curves).

NON-INVASIVE: this module only *imports* the locked v3 core/algorithms/baselines;
it does NOT modify any file under v3/. It drives the identical v3 three-stage
timeline (fluid -> evfa) with the same FluidParams/VEVFParams/HoleFillParams, but
additionally snapshots positions at phase boundaries + records the per-step
coverage curve + captures the fluid-stage trace needed by the mechanism figure.

Data written to v3/results/demo_figs/ (incremental, crash-safe):
  snapshots_{method}_{n}_{seed}.npz     positions at 4 evolution phases      (Fig: N4)
  convergence_{n}_{seed}.npz            per-step coverage curves, all methods (Fig: N5)
  fluxtrace_{n}_{seed}.npz              positions at several fluid steps     (Fig: N6)
  sweep_all.csv                          baseline sweep final metrics         (Fig: comm/packet/scal)
  progress.log                           append-only progress

Usage:
  python run_demo_figures.py --phase gather --n 40 --seeds ...   # R1: N4/N5/N6 data
  python run_demo_figures.py --phase sweep  [--axis all]          # R2: baseline sweeps
"""
import copy
import json
import os
import sys
import time
import csv
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from run_suites import (              # reuse locked primitives, no edits
    load_config, create_agents, _grid, _neighbor_stats,
)
from run_suites import run_episode
from core import Simulator
from algorithms.fluid import FluidParams, fluid_forces
from algorithms.vevf import VEVFParams, vevf_forces
from algorithms.hole_fill import HoleFillParams, hole_fill_forces
from algorithms.baselines import random as _rand, vfa as _vfa, lloyd as _lloyd, pso as _pso
from evaluation.metrics import coverage_ratio

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "results" / "demo_figs"
DEMO.mkdir(parents=True, exist_ok=True)

METHODS = ["star", "lloyd", "vfa", "pso", "random"]
SEEDS12 = [42, 7, 123, 2024, 555, 777, 1000, 2025, 666, 314, 2026, 888]
STAGE = {"random": _rand.stage_random, "vfa": _vfa.stage_vfa,
         "lloyd": _lloyd.stage_lloyd, "pso": _pso.stage_pso}

# phase boundaries on the 400-step axis (fluid 120 / evfa 280) for snapshot figs
PHASES = [(0, "launch"), (40, "fluid"), (120, "fluid_end"), (400, "refined")]


def log(msg):
    line = "[%.1f] %s" % (time.time(), msg)
    print(line, flush=True)
    with open(DEMO / "progress.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# --------------------------------------------------------------------------- #
#  R1 — gather trajectories (N4 snapshots, N5 convergence, N6 fluid trace)
# --------------------------------------------------------------------------- #
def episode_gather(cfg, seed, n, method, record_every=5, fluid_steps=None, evfa_steps=None):
    """Drive one v3 episode while recording snapshots + coverage curve + fluid trace."""
    c = copy.deepcopy(cfg)
    e, u, sc, com = c["environment"], c["usv"], c["simulation"], c["communication"]
    u["number"] = n
    n_fluid = fluid_steps or sc["fluid_steps"]
    n_evfa = evfa_steps or sc["evfa_steps"]
    agents = create_agents(n, c, seed)
    sim = Simulator(agents, width=e["width"], height=e["height"],
                    c_th=com["radius"], drop_rate=0.0, loss_seed=seed)
    g = _grid(c, e.get("metric_grid", 250.0))
    dt = sc["timestep"]

    fp = FluidParams(**{k: c["fluid"][k] for k in
                        ("interaction_radius", "k_fluid", "rest_density",
                         "viscosity", "drag", "boundary_k")})
    vp = VEVFParams(**{k: c["vevf"][k] for k in c["vevf"]})
    hp = HoleFillParams(**{k: c["hole_fill"][k] for k in c["hole_fill"]})

    cov = [coverage_ratio(sim, g)]
    steps = [0]
    snapshots = []       # list of (step, pos)
    fluid_trace = []     # list of (step, pos) during fluid stage (star)
    total = 0

    def at(step):
        return int(step) in {p[0] for p in PHASES}

    # dense launch snapshot
    snapshots.append((0, sim.positions()))

    if method == "star":
        for st in range(n_fluid):
            sim.step(fluid_forces(agents, fp, e["width"], e["height"]), dt)
            total += 1
            if total % record_every == 0:
                cov.append(coverage_ratio(sim, g)); steps.append(total)
            # fluid trace ~ every 20 fluid steps for the mechanism figure
            if st % 20 == 0 or st == n_fluid - 1:
                fluid_trace.append((int(total), sim.positions()))
            if at(total):
                snapshots.append((int(total), sim.positions()))
        for st in range(n_evfa):
            f = np.zeros((len(agents), 2))
            f += vevf_forces(agents, vp, e["width"], e["height"], weighted=True)
            f += hole_fill_forces(agents, hp, e["width"], e["height"])
            sim.step(f, dt)
            total += 1
            if total % record_every == 0:
                cov.append(coverage_ratio(sim, g)); steps.append(total)
            if at(total):
                snapshots.append((int(total), sim.positions()))
    else:
        stage = STAGE[method]
        n_tot = n_fluid + n_evfa
        for _ in range(n_tot):
            stage(sim, dt, 1)
            total += 1
            if total % record_every == 0:
                cov.append(coverage_ratio(sim, g)); steps.append(total)
            if at(total):
                snapshots.append((int(total), sim.positions()))

    # ensure final phase recorded
    if snapshots[-1][0] != 400:
        snapshots.append((400, sim.positions()))

    return steps, cov, snapshots, fluid_trace


def gather(n, seeds):
    cfg = load_config()
    log(f"R1 gather: n={n} seeds={seeds}")
    for sd in seeds:
        per_cov, per_snap, ftrace, ref_steps = {}, {}, None, None
        for m in METHODS:
            steps, cov, snaps, fltr = episode_gather(cfg, sd, n, m)
            per_cov[m] = cov
            per_snap[m] = snaps
            if m == "star":
                ftrace, ref_steps = fltr, steps
            log(f"  n{n} seed{sd} {m}: {len(snaps)} snapshots, {len(cov)} cov-pts")
        # one write per seed: convergence holds ALL methods' curves
        np.savez(DEMO / f"convergence_{n}_{sd}.npz",
                 steps=np.array(ref_steps),
                 cov=np.vstack([per_cov[m] for m in METHODS]),
                 methods=np.array(METHODS))
        for m in METHODS:
            np.savez(DEMO / f"snapshots_{m}_{n}_{sd}.npz",
                     steps=np.array([s for s, _ in per_snap[m]]),
                     pos=np.array([p for _, p in per_snap[m]]))
        if ftrace is not None:
            np.savez(DEMO / f"fluxtrace_{n}_{sd}.npz",
                     steps=np.array([s for s, _ in ftrace]),
                     pos=np.array([p for _, p in ftrace]))
    log("R1 gather done")


# --------------------------------------------------------------------------- #
#  R2 — baseline sweep curves (full-axis, methods over the sim sweep grids)
# --------------------------------------------------------------------------- #
def sweep(cfg, seed, method, comm_radius=None, drop=0.0, n=None,
          metric_grid=None, fluid_steps=None, evfa_steps=None):
    r = run_episode(cfg, seed, mode=method, comm_radius=comm_radius,
                    drop_rate=drop, n=n, metric_grid=metric_grid,
                    fluid_steps=fluid_steps, evfa_steps=evfa_steps)
    return r


def run_sweeps(seeds):
    cfg = load_config()
    methods = ["lloyd", "pso", "vfa", "random"]
    n40 = 40
    comm_radii = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000]
    drops = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    scal_n = [20, 40, 60, 80, 100, 150, 200, 300]
    out_rows = []
    t0 = time.time()

    def add(row):
        out_rows.append(row)
        with open(DEMO / "sweep_all.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            w.writeheader(); w.writerows(out_rows)

    # comm_radius
    for cr in comm_radii:
        for sd in seeds:
            for m in methods:
                r = sweep(cfg, sd, m, comm_radius=cr, n=n40)
                add({"suite": "comm_radius", "N": n40, "seed": sd, "method": m,
                     "comm_radius": cr, "drop": "", **r})
                log(f"  comm cr={cr} N={n40} seed{sd} {m} cov={r['final_coverage']:.3f} "
                    f"({time.time()-t0:.0f}s)")
    # packet_loss
    for dp in drops:
        for sd in seeds:
            for m in methods:
                r = sweep(cfg, sd, m, drop=dp, n=n40)
                add({"suite": "packet_loss", "N": n40, "seed": sd, "method": m,
                     "comm_radius": "", "drop": dp, **r})
                log(f"  pl drop={dp} N={n40} seed{sd} {m} cov={r['final_coverage']:.3f} "
                    f"({time.time()-t0:.0f}s)")
    # scalability (mirror STAR's truncated settings for large N)
    for nn in scal_n:
        if nn >= 150:
            mg, every, fs_, es_ = 500.0, 10, 15, 25
        elif nn >= 100:
            mg, every, fs_, es_ = 400.0, 10, 40, 80
        else:
            mg, every, fs_, es_ = 250.0, 5, None, None
        for sd in seeds:
            for m in methods:
                r = sweep(cfg, sd, m, n=nn, metric_grid=mg,
                          fluid_steps=fs_, evfa_steps=es_)
                add({"suite": "scalability", "N": nn, "seed": sd, "method": m,
                     "comm_radius": "", "drop": "", **r})
                log(f"  scal N={nn} seed{sd} {m} cov={r['final_coverage']:.3f} "
                    f"({time.time()-t0:.0f}s)")
    log("R2 sweep done")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["gather", "sweep"])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seeds", nargs="+", type=int, default=None)
    a = ap.parse_args()
    seeds = a.seeds or SEEDS12
    if a.phase == "gather":
        gather(a.n, seeds)
    else:
        run_sweeps(seeds)