"""Distributed Lloyd: local truncated Voronoi centroid iteration.

Each vessel builds a locally truncated Euclidean Voronoi cell using only its neighbors
(within C_th) and moves toward the cell centroid. It converges to a local approximate
centroidal Voronoi configuration (not the global Lloyd solution).
"""
import numpy as np
from ..local_laguerre import _halfplane
from shapely.geometry import box


class _ZeroRadiiCell:
    """Local cell approximation (Euclidean), independent of global information."""
    def __init__(self, polygon, centroid):
        self.polygon = polygon
        self.centroid = centroid


def _local_euclidean_cell(agent, width, height):
    """Build the local Euclidean cell: half-plane clipping with neighbors only."""
    roi = box(0.0, 0.0, width, height)
    xi = agent.position
    poly = roi
    nb_pos = agent.neighbor_positions
    nb_rad = agent.neighbor_radii
    for j in range(len(nb_pos)):
        xj = nb_pos[j]
        rj = nb_rad[j]
        hp = _halfplane(xi, 0.0, xj, 0.0)  # Euclidean: radii ignored
        newp = poly.intersection(hp)
        if newp.is_empty:
            break
        poly = newp
    if poly.is_empty or poly.area < 1e-6:
        return _ZeroRadiiCell(None, xi.copy())
    if poly.geom_type == 'MultiPolygon':
        poly = max(poly.geoms, key=lambda g: g.area)
    return _ZeroRadiiCell(poly, np.array(poly.centroid.coords[0]))


def lloyd_forces(agents, width, height, gain=0.5, drag=0.5):
    forces = np.zeros((len(agents), 2))
    for i, a in enumerate(agents):
        cell = _local_euclidean_cell(a, width, height)
        F = gain * (cell.centroid - a.position)
        F -= drag * a.velocity
        forces[i] = F
    return forces


def stage_lloyd(sim, dt, steps, gain=0.5, drag=0.5):
    for _ in range(steps):
        f = lloyd_forces(sim.agents, sim.width, sim.height, gain, drag)
        sim.step(f, dt)
    return sim
