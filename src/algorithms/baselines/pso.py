"""Distributed lbest PSO: communication-neighbor topology; no global grid / global
KD-tree.

Each vessel keeps its personal best (pbest, its own historical best position) and each
step exchanges pbest information with its communication neighbors, taking the neighbor
with the best fitness as lbest (neighborhood topology). The fitness is based on the local
hole count.
"""
import numpy as np
from .vfa import _local_holes


class PSOParams:
    def __init__(self, w=0.3, c1=1.2, c2=0.4, v_cap=200.0, grid_res=500.0):
        self.w = float(w)
        self.c1 = float(c1)
        self.c2 = float(c2)
        self.v_cap = float(v_cap)
        self.grid_res = float(grid_res)


def _local_fitness(agent, width, height, grid_res):
    """Local fitness = number of local hole points (larger is better)."""
    holes = _local_holes(agent, width, height, grid_res)
    return len(holes)


def pso_step(sim, params, dt):
    """One PSO step: first broadcast to refresh neighbor perception, then update
    velocity/position (local)."""
    agents = sim.agents
    pos = np.array([a.position for a in agents])
    vel = np.array([a.velocity for a in agents])
    for i, a in enumerate(agents):
        # Initialize the pbest cache (on first call)
        if not hasattr(a, '_pbest'):
            a._pbest = a.position.copy()
            a._pbest_fit = _local_fitness(a, sim.width, sim.height, params.grid_res)
        fit = _local_fitness(a, sim.width, sim.height, params.grid_res)
        if fit > a._pbest_fit:
            a._pbest = a.position.copy()
            a._pbest_fit = fit
        # lbest = best pbest among the communication neighbors
        lbest = a._pbest.copy()
        lbest_fit = a._pbest_fit
        for j in range(len(a.neighbor_ids)):
            nb = a.neighbor_ids[j]
            nb_agent = agents[int(nb)]
            if not hasattr(nb_agent, '_pbest'):
                nb_agent._pbest = nb_agent.position.copy()
                nb_agent._pbest_fit = _local_fitness(
                    nb_agent, sim.width, sim.height, params.grid_res)
            if nb_agent._pbest_fit > lbest_fit:
                lbest = nb_agent._pbest.copy()
                lbest_fit = nb_agent._pbest_fit
        # Cognitive target: nearest hole point (more direct drive; like the per-particle
        # hole assignment of v2)
        cognitive = a._pbest.copy()
        holes = _local_holes(a, sim.width, sim.height, params.grid_res)
        if len(holes) > 0:
            dd = np.sum((holes - a.position) ** 2, axis=1)
            cognitive = holes[int(np.argmin(dd))]
        r1 = a.rng.random(2)
        r2 = a.rng.random(2)
        v_new = (params.w * a.velocity
                 + params.c1 * r1 * (cognitive - a.position)
                 + params.c2 * r2 * (lbest - a.position))
        sp = np.linalg.norm(v_new)
        if sp > params.v_cap:
            v_new *= params.v_cap / sp
        a.velocity = v_new.copy()
    # Positions updated with dt
    for a in agents:
        a.position = a.position + a.velocity * dt
        a.clamp_to(sim.width, sim.height)
        a.energy -= np.linalg.norm(a.velocity) * dt * 0.001
    sim.comms.broadcast(agents, sim.width, sim.height)


def stage_pso(sim, dt, steps, params=None):
    params = params or PSOParams()
    for _ in range(steps):
        sim.comms.broadcast(sim.agents, sim.width, sim.height)
        pso_step(sim, params, dt)
    return sim
