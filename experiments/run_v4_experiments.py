# -*- coding: utf-8 -*-
"""Six-suite experiments of the manuscript version (v4) on the STAR v3
framework.

Follows the experiment_add/STAR_v4 design, implemented on the locked v3
framework:
- Reuses the v3 core (agent/comms/simulator) + algorithms (fluid/local_laguerre/vevf/
  hole_fill) + baselines
- Keeps the v3 three-stage timing (fluid_steps fluid -> evfa_steps VEVF+hole_fill)
- Adds metrics: T90 (absolute coverage 0.90, fixing the v3 relative-k90 bug), neighbor
  fraction, coverage AUC

Six suites (corresponding to paper Figs 2-7):
  E1 benchmark          N=40/100, STAR/Lloyd/VFA/PSO/Random, mean+-SD
  E2 comm_radius        C_th=0.5-5km -> coverage/T90/neighbor_fraction
  E3 packet_loss        0-50% -> coverage/T90/energy
  E4 heterogeneity      homogeneous/mild/medium/strong radius configurations
  E5 scalability        N=20-300 -> coverage + neighbor_fraction
  E6 ablation           STAR/-Fluid/-Laguerre/-VEVF/-HoleFill -> energy-coverage Pareto
"""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                # experiments/
sys.path.insert(0, os.path.dirname(HERE))  # project top level (contains src/ and
                                           # configs/)
from src.core import Agent, Simulator
from src.algorithms.fluid import FluidParams, fluid_forces
from src.algorithms.vevf import VEVFParams, vevf_forces
from src.algorithms.hole_fill import HoleFillParams, hole_fill_forces
from src.algorithms.baselines import random as rand_mod
from src.algorithms.baselines import vfa as vfa_mod
from src.algorithms.baselines import lloyd as lloyd_mod
from src.algorithms.baselines import pso as pso_mod
from src.evaluation.metrics import coverage_ratio

ROOT = Path(__file__).resolve().parent.parent


def load_config(path=None):
    path = path or ROOT / 'configs' / 'default.yaml'
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def create_agents(n, cfg, seed):
    """v3 create_agents (same as run_experiments)."""
    u, e = cfg['usv'], cfg['environment']
    rng = np.random.default_rng(seed)
    nh = round(n * u['high_ratio'])
    nm = round(n * u['medium_ratio'])
    nl = n - nh - nm
    radii = ([u['high_radius']] * nh + [u['medium_radius']] * nm + [u['low_radius']] * nl)
    std = u['cluster_scale'] * min(e['width'], e['height']) / 2.0
    pos = rng.normal(loc=[e['width'] / 2, e['height'] / 2], scale=std, size=(n, 2))
    np.clip(pos, 0.0, [e['width'], e['height']], out=pos)
    return [Agent(i, pos[i], radii[i], v_max=u['v_max'], seed=seed + i) for i in range(n)]


def _grid(cfg, res=None):
    e = cfg['environment']
    res = res or e['metric_grid']
    xs = np.linspace(res / 2, e['width'] - res / 2, int(e['width'] / res))
    ys = np.linspace(res / 2, e['height'] - res / 2, int(e['height'] / res))
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel()])


def _neighbor_stats(agents):
    z = np.array([len(a.neighbor_ids) for a in agents], dtype=float)
    n = len(agents)
    return float(z.mean()), float(z.mean() / max(n - 1, 1))


def run_episode(cfg, seed, mode='star', comm_radius=None, drop_rate=0.0,
                heterogeneity=None, n=None, weighted=True, use_holefill=True,
                use_fluid=True, use_vevf=True, record_every=5,
                metric_grid=None, fluid_steps=None, evfa_steps=None):
    """Run one complete deployment and return a metrics dict (v3 three-stage timing).

    Ablation switches:
      -Fluid:    use_fluid=False
      -Laguerre: weighted=False (Euclidean cells)
      -VEVF:     use_vevf=False
      -HoleFill: use_holefill=False

    metric_grid: coverage grid resolution (m); can be coarsened for large N to speed up
                 (scalability).
    fluid_steps / evfa_steps: override the default step counts (scalability can halve
                 them for large N to control runtime).
    """
    c = copy.deepcopy(cfg)
    e = c['environment']
    u = c['usv']
    sc = c['simulation']
    com = c['communication']
    if n is not None:
        u['number'] = n
    if comm_radius is not None:
        com['radius'] = float(comm_radius)
    if heterogeneity is not None:
        u['high_radius'] = heterogeneity['high_radius']
        u['medium_radius'] = heterogeneity['medium_radius']
        u['low_radius'] = heterogeneity['low_radius']
    n_fluid = fluid_steps if fluid_steps is not None else sc['fluid_steps']
    n_evfa = evfa_steps if evfa_steps is not None else sc['evfa_steps']

    agents = create_agents(u['number'], c, seed)
    sim = Simulator(agents, width=e['width'], height=e['height'],
                    c_th=com['radius'], drop_rate=drop_rate, loss_seed=seed)
    g = _grid(c, metric_grid or e.get('metric_grid', 250.0))
    dt = sc['timestep']
    curve = []
    en_curve = []
    nf_curve = []
    nf_frac_curve = []
    step_ctr = 0

    def snapshot():
        curve.append(coverage_ratio(sim, g))
        en_curve.append(sum(100.0 - a.energy for a in agents))
        m, fr = _neighbor_stats(agents)
        nf_curve.append(m)
        nf_frac_curve.append(fr)

    def maybe_snapshot():
        # Record the global step sequence; one point per record_every steps (including
        # the last step)
        nonlocal step_ctr
        step_ctr += 1
        if step_ctr % record_every == 0:
            snapshot()

    snapshot()
    fp = FluidParams(**{k: c['fluid'][k] for k in c['fluid']
                        if k in ('interaction_radius', 'k_fluid', 'rest_density',
                                 'viscosity', 'drag', 'boundary_k')})
    vp = VEVFParams(**{k: c['vevf'][k] for k in c['vevf']})
    hp = HoleFillParams(**{k: c['hole_fill'][k] for k in c['hole_fill']})

    if mode == 'star':
        # Timing protocol (identical to v3/run_suites.py):
        # broadcast the current state -> compute forces from the current neighbor
        # cache -> integrate -> broadcast again to refresh the cache
        sim.broadcast()          # must broadcast before the first dynamics step
        if use_fluid:
            for _ in range(n_fluid):
                F = fluid_forces(agents, fp, e['width'], e['height'])
                sim.integrate(F, dt)
                sim.broadcast()  # refresh the cache before the next force computation
                maybe_snapshot()
        for _ in range(n_evfa):
            f = np.zeros((len(agents), 2))
            if use_vevf:
                f += vevf_forces(agents, vp, e['width'], e['height'], weighted=weighted)
            if use_holefill:
                f += hole_fill_forces(agents, hp, e['width'], e['height'],
                                      c_th=com['radius'])
            sim.integrate(f, dt)
            sim.broadcast()
            maybe_snapshot()
    else:
        n_steps = n_fluid + n_evfa
        stage = {'random': rand_mod.stage_random,
                 'vfa': vfa_mod.stage_vfa,
                 'lloyd': lloyd_mod.stage_lloyd,
                 'pso': pso_mod.stage_pso}[mode]
        for _ in range(n_steps):
            stage(sim, dt, 1)
            maybe_snapshot()

    snapshot()
    curve = np.asarray(curve)
    target = sc.get('target_coverage', 0.90)
    hit = np.where(curve >= target)[0]
    # curve[i] corresponds to real step i*record_every (curve[0] = step 0)
    t90 = int(hit[0] * record_every) if len(hit) else -1
    return {
        'final_coverage': float(curve[-1]),
        't90': t90,
        'coverage_auc': float(np.trapezoid(curve)),
        'energy': float(np.mean(en_curve)),
        'energy_final': float(en_curve[-1]),
        'mean_neighbors': float(np.mean(nf_curve)),
        'neighbor_fraction': float(np.mean(nf_frac_curve)),
        'curve': curve,
    }


HETERO = {
    'homogeneous': {'high_radius': 1000.0, 'medium_radius': 1000.0, 'low_radius': 1000.0},
    'mild':        {'high_radius': 1200.0, 'medium_radius': 1000.0, 'low_radius': 800.0},
    'medium':      {'high_radius': 1500.0, 'medium_radius': 1000.0, 'low_radius': 500.0},
    'strong':      {'high_radius': 1700.0, 'medium_radius': 1000.0, 'low_radius': 300.0},
}
ABLATIONS = {
    'star':         {},
    'no_fluid':     {'use_fluid': False},
    'no_laguerre':  {'weighted': False},
    'no_vevf':      {'use_vevf': False},
    'no_hole_fill': {'use_holefill': False},
}
# v4 default experiment parameters (do not modify the locked v3 config; may be
# overridden by config['experiment'])
V4_DEFAULTS = {
    'comm_radius_m': [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000],
    'packet_loss': [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
    'scalability_n': [20, 40, 60, 80, 100, 150, 200, 300],
    'target_coverage': 0.90,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--suite', choices=['smoke', 'paper_core', 'all'], default='smoke')
    ap.add_argument('--seeds', nargs='+', type=int, default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    cfg = load_config()
    exp = cfg['experiment']
    for k, v in V4_DEFAULTS.items():
        exp.setdefault(k, v)
    seeds = a.seeds or exp['seeds']
    rows = []
    t0 = time.time()

    if a.suite == 'smoke':
        for sd in seeds[:1]:
            rows.append({'suite': 'benchmark', 'N': 20, 'seed': sd, 'method': 'star',
                         **run_episode(cfg, sd, mode='star', n=20)})
            rows.append({'suite': 'benchmark', 'N': 20, 'seed': sd, 'method': 'lloyd',
                         **run_episode(cfg, sd, mode='lloyd', n=20)})
            rows.append({'suite': 'comm_radius', 'N': 20, 'seed': sd, 'method': 'star',
                         'comm_radius': 3000, **run_episode(cfg, sd, comm_radius=3000, n=20)})
            rows.append({'suite': 'packet_loss', 'N': 20, 'seed': sd, 'method': 'star',
                         'drop': 0.3, **run_episode(cfg, sd, drop_rate=0.3, n=20)})
            rows.append({'suite': 'heterogeneity', 'N': 20, 'seed': sd, 'method': 'medium',
                         **run_episode(cfg, sd, heterogeneity=HETERO['medium'], n=20)})
            rows.append({'suite': 'scalability', 'N': 20, 'seed': sd, 'method': 'star',
                         **run_episode(cfg, sd, n=20)})
            rows.append({'suite': 'ablation', 'N': 20, 'seed': sd, 'method': 'star',
                         **run_episode(cfg, sd, n=20)})
            rows.append({'suite': 'ablation', 'N': 20, 'seed': sd, 'method': 'no_laguerre',
                         **run_episode(cfg, sd, n=20, weighted=False)})
    elif a.suite in ('paper_core', 'all'):
        for n in exp['n_grids']:
            for sd in seeds:
                for m in ['star', 'lloyd', 'vfa', 'pso', 'random']:
                    r = run_episode(cfg, sd, mode=m, n=n)
                    rows.append({'suite': 'benchmark', 'N': n, 'seed': sd, 'method': m,
                                 **{k: v for k, v in r.items() if k != 'curve'}})
                    print('benchmark N=%d seed=%d %s cov=%.3f t90=%d (%.0fs)'
                          % (n, sd, m, r['final_coverage'], r['t90'],
                             time.time() - t0), flush=True)
        n = 40
        for cr in exp['comm_radius_m']:
            for sd in seeds:
                r = run_episode(cfg, sd, comm_radius=cr, n=n)
                rows.append({'suite': 'comm_radius', 'N': n, 'seed': sd, 'method': 'star',
                             'comm_radius': cr, **{k: v for k, v in r.items() if k != 'curve'}})
                print('comm_radius cr=%.0f seed=%d cov=%.3f t90=%d (%.0fs)'
                      % (cr, sd, r['final_coverage'], r['t90'],
                         time.time() - t0), flush=True)
        for dp in exp['packet_loss']:
            for sd in seeds:
                r = run_episode(cfg, sd, drop_rate=dp, n=n)
                rows.append({'suite': 'packet_loss', 'N': n, 'seed': sd, 'method': 'star',
                             'drop': dp, **{k: v for k, v in r.items() if k != 'curve'}})
                print('packet_loss drop=%.1f seed=%d cov=%.3f t90=%d (%.0fs)'
                      % (dp, sd, r['final_coverage'], r['t90'],
                         time.time() - t0), flush=True)
        for hname, hval in HETERO.items():
            for sd in seeds:
                r = run_episode(cfg, sd, heterogeneity=hval, n=n)
                rows.append({'suite': 'heterogeneity', 'N': n, 'seed': sd, 'method': hname,
                             **{k: v for k, v in r.items() if k != 'curve'}})
                print('heterogeneity %s seed=%d cov=%.3f (%.0fs)'
                      % (hname, sd, r['final_coverage'], time.time() - t0), flush=True)
        for nn in exp['scalability_n']:
            if nn >= 150:
                mgrid, every, fs_, es_ = 500.0, 10, 15, 25
            elif nn >= 100:
                mgrid, every, fs_, es_ = 400.0, 10, 40, 80
            else:
                mgrid, every, fs_, es_ = 250.0, 5, None, None
            for sd in seeds:
                r = run_episode(cfg, sd, n=nn, metric_grid=mgrid,
                                record_every=every, fluid_steps=fs_,
                                evfa_steps=es_)
                rows.append({'suite': 'scalability', 'N': nn, 'seed': sd,
                             'method': 'star',
                             **{k: v for k, v in r.items() if k != 'curve'}})
                print('scalability N=%d seed=%d cov=%.3f nf=%.3f (%.0fs)'
                      % (nn, sd, r['final_coverage'], r['neighbor_fraction'],
                         time.time() - t0), flush=True)
        for mname, mcfg in ABLATIONS.items():
            for sd in seeds:
                r = run_episode(cfg, sd, n=n, **mcfg)
                rows.append({'suite': 'ablation', 'N': n, 'seed': sd, 'method': mname,
                             **{k: v for k, v in r.items() if k != 'curve'}})
                print('ablation %s seed=%d cov=%.3f (%.0fs)'
                      % (mname, sd, r['final_coverage'], time.time() - t0), flush=True)
    else:
        raise SystemExit('unknown suite %s' % a.suite)

    out = ROOT / (a.out or 'results/v4')
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / 'all_runs_v4.csv', index=False)
    (out / 'metadata_v4.json').write_text(
        json.dumps({'suite': a.suite, 'seeds': seeds,
                    'elapsed_s': round(time.time() - t0, 1)}, indent=2),
        encoding='utf-8')
    print('saved -> %s (%d runs, %.0fs)' % (out / 'all_runs_v4.csv', len(rows),
                                            time.time() - t0))
    print(df.groupby(['suite', 'method'])['final_coverage'].mean().round(3).to_string())


if __name__ == '__main__':
    main()
