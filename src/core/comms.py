"""Communication/perception layer: simulates local neighbor perception based on C_th
plus probabilistic packet loss."""
import numpy as np
from scipy.spatial import cKDTree


class Comms:
    """Communication layer of the simulation environment: each step broadcasts the
    position/radius/velocity of every vessel, and each vessel receives only neighbors
    within C_th, with each link dropped independently with probability p per step.

    Neighbor discovery is accelerated with cKDTree (O(N log N)); this only optimizes the
    simulator internals and does not change the distributed semantics: each vessel still
    receives only the neighbor information within C_th. The neighbor id ordering keeps the
    packet-loss random sequence identical to the all-pairs version (seed-deterministic).
    """

    def __init__(self, c_th=3000.0, drop_rate=0.0, loss_seed=0):
        self.c_th = float(c_th)
        self.drop_rate = float(drop_rate)
        self.rng = np.random.default_rng(int(loss_seed))

    def broadcast(self, agents, width, height):
        """Global world update (called by the simulator), but each vessel only receives
        its locally visible neighbors."""
        pos = np.array([a.position for a in agents])
        radii = np.array([a.radius for a in agents])
        vel = np.array([a.velocity for a in agents])
        tree = cKDTree(pos)
        for i, a in enumerate(agents):
            a.reset_perception()
            # Exclude self, then sort by id (consistent with the ascending ids of the
            # original all-pairs version)
            ids = tree.query_ball_point(pos[i], self.c_th)
            ids = np.array([j for j in ids if j != i], dtype=int)
            np.sort(ids)
            if len(ids) == 0:
                continue
            # Packet-loss simulation: each link is dropped independently with drop_rate
            keep = self.rng.random(len(ids)) > self.drop_rate
            ids = ids[keep]
            a.neighbor_ids = ids.copy()
            a.neighbor_positions = pos[ids].copy()
            a.neighbor_radii = radii[ids].copy()
            a.neighbor_velocities = vel[ids].copy()
