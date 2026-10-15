"""Statistical significance tests: STAR vs each baseline (paired t-test + Wilcoxon
signed-rank test).

Input: results/suite/all_runs.csv (12 seeds, fixed implementation)
For the benchmark suite, at N=40 and N=100, for each pair (STAR, baseline):
  - paired t-test (same-seed paired design)
  - Wilcoxon signed-rank test (non-parametric robustness)
Output: coverage mean+-std, difference, p-values, significance stars
"""
import os
import pandas as pd
import numpy as np
from scipy import stats

CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results', 'suite', 'all_runs.csv')


def wilcoxon_or_note(x, y):
    """Paired Wilcoxon; returns NaN when all samples are identical (no difference)."""
    d = np.asarray(x) - np.asarray(y)
    if np.allclose(d, 0):
        return float('nan')
    try:
        return stats.wilcoxon(x, y).pvalue
    except ValueError:
        return float('nan')


def test_one(df, n, base):
    """Significance test of STAR vs base at N=n."""
    star = df[(df.suite == 'benchmark') & (df.N == n) & (df.method == 'star')]
    bl = df[(df.suite == 'benchmark') & (df.N == n) & (df.method == base)]
    # Align by seed (paired design)
    star = star.set_index('seed').final_coverage
    bl = bl.set_index('seed').final_coverage
    common = star.index.intersection(bl.index)
    x, y = star[common].to_numpy(), bl[common].to_numpy()
    t, p_t = stats.ttest_rel(x, y)
    p_w = wilcoxon_or_note(x, y)
    return {
        'N': n, 'baseline': base,
        'n_seeds': len(common),
        'star_mean': f'{x.mean():.4f}', 'base_mean': f'{y.mean():.4f}',
        'diff': f'{x.mean()-y.mean():+.4f}',
        't_pvalue': f'{p_t:.4f}', 'wilcoxon_p': f'{p_w:.4f}' if not np.isnan(p_w) else 'n/a',
    }


def main():
    if not os.path.exists(CSV):
        print(f'awaiting results: {CSV} does not exist yet')
        return
    df = pd.read_csv(CSV)
    rows = []
    for n in [40, 100]:
        for base in ['lloyd', 'vfa', 'pso', 'random']:
            rows.append(test_one(df, n, base))
    out = pd.DataFrame(rows)
    # Significance markers
    def star(p):
        if p == 'n/a':
            return '—'
        v = float(p)
        return '***' if v < 0.001 else ('**' if v < 0.01 else ('*' if v < 0.05 else 'ns'))
    out['t_sig'] = out.t_pvalue.apply(star)
    out['w_sig'] = out.wilcoxon_p.apply(star)
    print(out.to_string(index=False))
    out.to_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'results', 'significance_tests.csv'), index=False)
    print('\nsaved: results/significance_tests.csv')


if __name__ == '__main__':
    main()
