# -*- coding: utf-8 -*-
"""Bit-level diff between two baseline-config regression JSON dumps.

Usage: python reg_diff.py [before.json] [after.json]
Default: reg_results_before.json reg_results_after.json (same directory).
Prints the number of differing fields / final positions and the verdict.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
bpath = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'reg_results_before.json'
apath = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / 'reg_results_after.json'

b = json.load(open(bpath, encoding='utf-8'))
a = json.load(open(apath, encoding='utf-8'))

assert len(b) == len(a) == 12, (len(b), len(a))
fields = ['final_coverage', 't90', 'coverage_auc', 'energy', 'energy_final',
          'mean_neighbors', 'neighbor_fraction']

n_diff = 0
for rb, ra in zip(b, a):
    assert rb['seed'] == ra['seed'] and rb['method'] == ra['method']
    for f in fields:
        if repr(rb[f]) != repr(ra[f]):
            n_diff += 1
            print('DIFF %s seed=%s %s: before=%r after=%r' % (rb['method'], rb['seed'], f, rb[f], ra[f]))
    pb, pa = rb['positions'], ra['positions']
    if len(pb) != len(pa):
        n_diff += 1
        print('DIFF %s seed=%s positions length' % (rb['method'], rb['seed']))
    else:
        for i, (qb, qa) in enumerate(zip(pb, pa)):
            for k in range(2):
                if repr(qb[k]) != repr(qa[k]):
                    n_diff += 1
                    print('DIFF %s seed=%s pos[%d][%d]: %r vs %r' % (rb['method'], rb['seed'], i, k, qb[k], qa[k]))

print('total field/position diffs: %d' % n_diff)
print('RESULT:', 'BIT-IDENTICAL' if n_diff == 0 else 'NOT IDENTICAL')
