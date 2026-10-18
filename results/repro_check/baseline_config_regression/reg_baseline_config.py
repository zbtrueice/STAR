# -*- coding: utf-8 -*-
"""Baseline-config regression (self-contained copy for reviewers).

Runs the four baselines (lloyd / vfa / pso / random) x 3 seeds at N=40 through
run_suites.run_episode and dumps full metrics plus final positions to a JSON
file. The package root is located relative to this file, so the script works
from any checkout.

Purpose: prove that moving the baseline hyperparameters into
configs/default.yaml (the `baselines` section) and reading them explicitly in
run_suites.py is a no-behaviour-change refactor. reg_results_before.json in this
directory was produced with the pre-refactor code (the same module defaults);
reg_diff.py must report BIT-IDENTICAL (0 diffs) between the two.

Usage:
    python reg_baseline_config.py [out.json]   # default: reg_results_after.json
    python reg_diff.py [before.json] [after.json]
"""
import sys, os, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent   # release root
HERE = Path(__file__).resolve().parent                        # this script's directory
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
import run_suites as rs

out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / 'reg_results_after.json'
cfg = rs.load_config()
rows = []
for sd in [42, 7, 123]:
    for m in ['lloyd', 'vfa', 'pso', 'random']:
        r = rs.run_episode(cfg, sd, mode=m, n=40)
        rows.append({
            'seed': sd, 'method': m,
            'final_coverage': r['final_coverage'],
            't90': r['t90'],
            'coverage_auc': r['coverage_auc'],
            'energy': r['energy'],
            'energy_final': r['energy_final'],
            'mean_neighbors': r['mean_neighbors'],
            'neighbor_fraction': r['neighbor_fraction'],
            'positions': [[float(v) for v in p] for p in r['positions']],
        })
        print('%s seed=%d cov=%.6f t90=%d' % (m, sd, r['final_coverage'], r['t90']), flush=True)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=1)
print('saved ->', out)
