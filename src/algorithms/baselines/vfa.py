"""Distributed VFA: Coulomb repulsion + attraction to local hole targets (no global
grid)."""
import numpy as np


class VFAParams:
    def __init__(self, k_rep=1.0e8, k_att=2.0, d_th=650.0, f_max=40.0,
                 k_target=300.0, drag=0.3, boundary_k=3.0, grid_res=500.0):
        self.k_rep = float(k_rep)
        self.k_att = float(k_att)
        self.d_th = float(d_th)
        self.f_max = float(f_max)
        self.k_target = float(k_target)
        self.drag = float(drag)
        self.boundary_k = float(boundary_k)
        self.grid_res = float(grid_res)


def _local_holes(agent, width, height, grid_res):
    """Local uncovered points (based on self + neighbors)."""
    c = agent.position
    half = grid_res * 6.0  # sampling window enlarged to 6*500 = 3000 m (C_th scale)
    xs = np.arange(c[0] - half, c[0] + half, grid_res)
    ys = np.arange(c[1] - half, c[1] + half, grid_res)
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((0, 2))
    gx, gy = np.meshgrid(xs, ys)
    grid = np.column_stack([gx.ravel(), gy.ravel()])
    inside = np.sum((grid - c) ** 2, axis=1) <= agent.radius ** 2
    grid = grid[~inside]
    nb_pos = agent.neighbor_positions
    nb_rad = agent.neighbor_radii
    if len(nb_pos) > 0 and len(grid) > 0:
        d2 = np.sum((grid[:, None, :] - nb_pos[None, :, :]) ** 2, axis=2)
        covered = (d2 <= (nb_rad ** 2)[None, :]).any(axis=1)
        grid = grid[~covered]
    return grid


def vfa_forces(agents, params, width, height):
    forces = np.zeros((len(agents), 2))
    for i, a in enumerate(agents):
        F = np.zeros(2)
        # Coulomb repulsion (neighbors)
        nb_pos = a.neighbor_positions
        if len(nb_pos) > 0:
            d = a.position - nb_pos
            dist = np.maximum(np.linalg.norm(d, axis=1), 1.0)
            mag = np.where(dist < params.d_th,
                           params.k_rep / (dist * dist),
                           -params.k_att)
            mag = np.clip(mag, -params.f_max, params.f_max)
            F = F + ((mag / dist)[:, None] * d).sum(axis=0)
        # Local hole target
        holes = _local_holes(a, width, height, params.grid_res)
        if len(holes) > 0:
            dd = np.sum((holes - a.position) ** 2, axis=1)
            j = int(np.argmin(dd))
            dirv = holes[j] - a.position
            dn = np.linalg.norm(dirv)
            if dn > 1e-6:
                F += (params.k_target / dn) * dirv
        # Drag + boundary
        speed = np.linalg.norm(a.velocity)
        F -= params.drag * speed * a.velocity
        if params.boundary_k > 0.0:
            margin = 500.0
            for k, hi in enumerate((width, height)):
                F[k] += params.boundary_k * (max(margin - a.position[k], 0.0)
                                             - max(a.position[k] - (hi - margin), 0.0))
        forces[i] = F
    return forces


def stage_vfa(sim, dt, steps, params=None):
    params = params or VFAParams()
    for _ in range(steps):
        f = vfa_forces(sim.agents, params, sim.width, sim.height)
        sim.step(f, dt)
    return sim
