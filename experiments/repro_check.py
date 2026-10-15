# -*- coding: utf-8 -*-
"""Reproduction self-check of the submission package: benchmark suite (N=40/100 x 12
seeds x 5 methods).

Reference baseline: v3/results/suite/all_runs.csv (the data source of every number in
the paper).
Run: star_env\Scripts\python.exe experiments/repro_check.py
Output: results/repro_check/benchmark_repro.csv + console comparison summary.
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_v4_experiments as R

SEEDS = [42, 7, 123, 2024, 555, 777, 1000, 2025, 666, 314, 2026, 888]
cfg = R.load_config()
rows = []
t0 = time.time()
for n in (40, 100):
    for sd in SEEDS:
        for m in ('star', 'lloyd', 'vfa', 'pso', 'random'):
            r = R.run_episode(cfg, sd, mode=m, n=n)
            r.pop('curve', None)
            rows.append({'N': n, 'seed': sd, 'method': m, **r})
            print('N=%d seed=%d %-7s cov=%.4f t90=%d (%.0fs)'
                  % (n, sd, m, r['final_coverage'], r['t90'],
                     time.time() - t0), flush=True)

out = HERE.parent / 'results' / 'repro_check'
out.mkdir(parents=True, exist_ok=True)
df = pd.DataFrame(rows)
df.to_csv(out / 'benchmark_repro.csv', index=False)

ref = pd.read_csv(HERE.parent / 'results' / 'suite' / 'all_runs.csv')
ref = ref[(ref.suite == 'benchmark') & (ref.N.isin([40, 100]))]
merge = df.merge(ref, on=['N', 'seed', 'method'], suffixes=('_repro', '_paper'))

print('\n=== STAR benchmark means (paper: 0.9707+-0.0048 @N40 / 0.9998 @N100) ===')
for n in (40, 100):
    for m in ('star', 'lloyd', 'vfa', 'pso', 'random'):
        v = df[(df.N == n) & (df.method == m)]['final_coverage']
        print('N=%d %-7s repro mean=%.4f std=%.4f' % (n, m, v.mean(), v.std()))

print('\n=== max |repro - paper| across 120 runs ===')
for col in ('final_coverage', 't90', 'coverage_auc', 'energy', 'mean_neighbors'):
    d = (merge['%s_repro' % col] - merge['%s_paper' % col]).abs().max()
    print('%-14s max|diff| = %.6f' % (col, d))
fc = (merge['final_coverage_repro'] - merge['final_coverage_paper']).abs()
print('final_coverage exact match runs: %d / %d'
      % ((fc < 1e-9).sum(), len(fc)))
print('elapsed %.0fs' % (time.time() - t0))
