"""Compute 12-seed allocation-fairness data for the benchmark suite.

The manuscript radar figure (FigR3c) reports allocation fairness J (Jain
index of Laguerre cell areas vs sensing demand, Section 3.6) together with
five other metrics that are all averaged over the full 12-seed benchmark.
Historically the fairness value was only computed for 3 seeds (seeds
42/7/123) by the mechanism-verification pipeline; this script recomputes it
for the full 12-seed benchmark set by re-running each deterministic episode
and evaluating the global power diagram on the final configuration.

Output: results/fairness_gap.json, one record per (N, seed, method):

    key  = "n{N}_seed{S}_drop0_{method}"
    data = {"fairness": J, "gap_m": minimax gap [m],
            "k90": 1 if the 0.90 target was reached else 0,
            "coverage": final coverage, "energy": actuation effort}

The (N, seed, method) grid is read from results/suite/all_runs.csv (the
benchmark suite), so the fairness data covers exactly the same episodes as
the other five radar metrics.  Each episode is re-run deterministically with
the benchmark configuration of run_suites.py (paper_core suite):
run_episode(cfg, seed, mode=method, n=N) with default fluid/VEVF/hole-fill
enabled and the default 250 m evaluation grid.
"""

import sys, json, time, csv
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

import run_suites as rs                      # noqa: E402
from v2_compat import v2_diagram, v2_fairness, v2_gap  # noqa: E402


def benchmark_grid():
    """(N, seed, method) triples of the benchmark suite from all_runs.csv."""
    csv_path = ROOT / 'results' / 'suite' / 'all_runs.csv'
    triples = []
    with open(csv_path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['suite'] == 'benchmark':
                triples.append((int(r['N']), int(r['seed']), r['method']))
    return triples


def main():
    cfg = rs.load_config()
    triples = benchmark_grid()
    out = ROOT / 'results' / 'fairness_gap.json'
    t0 = time.time()
    rows = {}
    for n, sd, m in triples:
        r = rs.run_episode(cfg, sd, mode=m, n=n)
        pos = np.asarray(r['positions'])
        rad = np.asarray(r['radii'])
        d = v2_diagram(pos, rad, 10000.0, 10000.0)
        fair = v2_fairness(pos, rad, d)
        gap = v2_gap(pos, rad, d)
        key = f"n{n}_seed{sd}_drop0_{m}"
        rows[key] = {
            "fairness": round(float(fair), 4),
            "gap_m": round(float(gap), 1),
            "k90": 1 if r['t90'] > 0 else 0,
            "coverage": round(float(r['final_coverage']), 4),
            "energy": round(float(r['energy']), 1),
        }
        print(f"[{time.time()-t0:.0f}s] {key}: fair={fair:.4f} "
              f"gap={gap:.1f} cov={r['final_coverage']:.4f}", flush=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print(f"saved -> {out}  ({len(rows)} records)")


if __name__ == '__main__':
    main()
