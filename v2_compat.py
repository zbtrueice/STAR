"""v3->v2 metric compatibility: use the global Laguerre diagram for offline
evaluation (same metric definition). The implementation now lives inside the
package (src/algorithms/laguerre.py and src/evaluation/metrics.py), so the
package is self-contained; no external simulator checkout is required."""

import numpy as np
from src.algorithms.laguerre import LaguerreDiagram
from src.evaluation.metrics import fairness_index, minimax_gap

class _SwarmCompat:
    """Make the LaguerreDiagram consume v3 positions/radii."""
    def __init__(self, pos, rad, width, height):
        self._pos = pos; self._rad = rad
        self.width = width; self.height = height
        self.n = len(pos)
    def positions(self): return self._pos
    def radii(self): return self._rad

def v2_diagram(pos, rad, width, height):
    return LaguerreDiagram(_SwarmCompat(pos, rad, width, height))

def v2_fairness(pos, rad, diagram):
    sw = _SwarmCompat(pos, rad, diagram.width, diagram.height)
    return fairness_index(sw, diagram)

def v2_gap(pos, rad, diagram):
    sw = _SwarmCompat(pos, rad, diagram.width, diagram.height)
    return minimax_gap(sw, diagram)

def k90_from_curve(curve):
    """First step at which 90% of the final value is reached (curve includes the
    initial state)."""
    curve = np.asarray(curve, dtype=float)
    if len(curve) < 2: return 0
    target = 0.9 * curve[-1]
    idx = np.where(curve >= target)[0]
    return int(idx[0]) if len(idx) else len(curve)
