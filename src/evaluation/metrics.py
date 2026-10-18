"""Evaluation metrics (same definitions as v2; compatible with the Simulator
interface)."""
import numpy as np


def fairness_index(swarm, diagram=None):
    """Jain fairness of Laguerre cell areas vs sensing areas (target: r^2).

    Allocation fairness J (Section 3.6 of the manuscript): each USV's
    allocated responsibility is its (non-empty) power-cell area, and its
    sensing demand is the squared sensing radius r_i^2, scaled to the same
    total.  J is the Jain index of the ratio (cell area / demand):
    1.0 means every active USV carries exactly its demand-proportional load.
    Only USVs with a non-empty power cell carry allocated load; empty-cell
    USVs are sensing-redundant (their load is 0 by design, not unfairness)
    and are excluded (Section 3.6).
    """
    if diagram is None:
        return 0.0
    active = diagram.areas > 1e-6
    if not active.any():
        return 0.0
    areas = diagram.areas[active]
    demand = (swarm.radii() ** 2)[active]
    demand = demand / demand.sum() * areas.sum()
    x = areas / np.maximum(demand, 1e-9)
    return float((x.sum() ** 2) / (len(x) * (x ** 2).sum())) if len(x) else 0.0


def minimax_gap(swarm, diagram):
    """Mean over USVs of (worst distance from site to its cell) - radius.

    0 means every cell is fully covered by its owner's sensing disk.
    Empty-cell USVs are excluded (no cell -> no gap).
    """
    active = diagram.covering_radius > 0.0
    if not active.any():
        return 0.0
    gap = diagram.covering_radius[active] - swarm.radii()[active]
    return float(np.maximum(gap, 0.0).mean())


def energy(sim):
    return sum(100.0 - a.energy for a in sim.agents)


def mean_motion(history):
    hist = np.asarray(history)
    if len(hist) < 2:
        return 0.0
    return float(np.mean(np.linalg.norm(hist[1:] - hist[:-1], axis=-1)))


def coverage_ratio(sim, grid=None, grid_res=250.0):
    if grid is None:
        xs = np.linspace(grid_res / 2, sim.width - grid_res / 2,
                         int(sim.width / grid_res))
        ys = np.linspace(grid_res / 2, sim.height - grid_res / 2,
                         int(sim.height / grid_res))
        xx, yy = np.meshgrid(xs, ys)
        grid = np.column_stack([xx.ravel(), yy.ravel()])
    pos = sim.positions()
    rad = sim.radii()
    covered = np.zeros(len(grid), dtype=bool)
    chunk = 2_000_000 // max(len(pos), 1)
    for s in range(0, len(grid), max(chunk, 1)):
        g = grid[s:s + max(chunk, 1)]
        d2 = ((g[:, None, :] - pos[None, :, :]) ** 2).sum(-1)
        covered[s:s + len(g)] = (d2 <= (rad ** 2)[None, :]).any(axis=1)
    return float(covered.mean())


class MetricsRecorder:
    def __init__(self, sim, grid_res=250.0):
        xs = np.linspace(grid_res / 2, sim.width - grid_res / 2,
                         int(sim.width / grid_res))
        ys = np.linspace(grid_res / 2, sim.height - grid_res / 2,
                         int(sim.height / grid_res))
        xx, yy = np.meshgrid(xs, ys)
        self.grid = np.column_stack([xx.ravel(), yy.ravel()])
        self.frames = []
        self.coverage = []
        self.energy_used = []
        self.mean_speed = []
        self.phases = {}
        self._last_positions = None

    def snapshot(self, step, sim):
        self.frames.append(sim.positions().copy())
        self.coverage.append(coverage_ratio(sim, self.grid))
        self.energy_used.append(energy(sim))
        self.mean_speed.append(sim.mean_speed())

    @staticmethod
    def _nn_stats(sim):
        """Mean nearest-neighbor distance and its CV (post-hoc evaluation statistics,
        not algorithm inputs)."""
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

    @staticmethod
    def _cluster_radius(sim):
        pos = sim.positions()
        cent = pos.mean(axis=0)
        return float(np.linalg.norm(pos - cent, axis=1).max())

    def phase(self, tag, sim, force_mean=None, force_max=None):
        """Record extended metrics for an explicit phase (initial / fluid_end / final,
        ...)."""
        nn_m, nn_cv = self._nn_stats(sim)
        pos = sim.positions()
        disp_m = disp_max = None
        if self._last_positions is not None:
            dv = np.linalg.norm(pos - self._last_positions, axis=1)
            disp_m, disp_max = float(dv.mean()), float(dv.max())
        self._last_positions = pos.copy()
        self.phases[tag] = {
            "coverage": coverage_ratio(sim, self.grid),
            "energy": energy(sim),
            "mean_speed": sim.mean_speed(),
            "nn_dist_mean": nn_m,
            "nn_dist_cv": nn_cv,
            "cluster_radius_max": self._cluster_radius(sim),
            "displacement_mean": disp_m,
            "displacement_max": disp_max,
            "force_mean": force_mean,
            "force_max": force_max,
        }
        return self.phases[tag]

    def summary(self, last_k=20):
        k = max(1, len(self.coverage) - last_k)
        return {
            'final_coverage': self.coverage[-1] if self.coverage else None,
            'settled_coverage': float(np.mean(self.coverage[-k:])) if self.coverage else None,
            'energy_used': self.energy_used[-1] if self.energy_used else None,
            'final_mean_speed': self.mean_speed[-1] if self.mean_speed else None,
            'n_frames': len(self.frames),
            'phases': self.phases,
        }
