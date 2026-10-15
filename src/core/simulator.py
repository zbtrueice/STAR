"""Simulator: sequential stepping with a unified interface.

Timing protocol (mechanism correctness fix, 2026-09-25):
    broadcast current state -> compute force from current neighbors
    -> integrate/update
`step(forces, dt)` keeps the compatible interface (broadcast + integrate) for the
baselines; the STAR path uses the explicit `broadcast()` -> force computation (the
neighbor cache is then guaranteed to be the current step's) -> `integrate()`.
"""
import numpy as np
from .agent import Agent
from .comms import Comms


class Simulator:
    """Unified simulation container; exposes positions()/radii()/n to stay compatible
    with the v2 metrics."""

    def __init__(self, agents, width=10000.0, height=10000.0, c_th=3000.0,
                 drop_rate=0.0, loss_seed=0):
        self.agents = list(agents)
        self.width = float(width)
        self.height = float(height)
        self.comms = Comms(c_th, drop_rate, loss_seed=loss_seed)
        self._pos = None

    @property
    def n(self):
        return len(self.agents)

    def positions(self):
        return np.array([a.position for a in self.agents])

    def radii(self):
        return np.array([a.radius for a in self.agents])

    def velocities(self):
        return np.array([a.velocity for a in self.agents])

    def broadcast(self):
        """Broadcast the current state and refresh the neighbor perception cache of every
        vessel.

        Must be called before any force computation that uses the neighbor_* fields;
        called exactly once per dynamics step (the packet-loss random sequence consumes
        the same number of draws per step).
        """
        self.comms.broadcast(self.agents, self.width, self.height)

    def integrate(self, forces, dt):
        """Apply external forces and integrate (does not refresh perception)."""
        for a, f in zip(self.agents, forces):
            a.move(f, dt)
            a.clamp_to(self.width, self.height)
        self._pos = None

    def update(self, forces, dt):
        """Compatibility alias (= integrate)."""
        self.integrate(forces, dt)

    def mean_speed(self):
        return float(np.mean([np.linalg.norm(a.velocity) for a in self.agents]))

    def step(self, forces, dt):
        """One step: first broadcast the current state, then apply the forces and
        integrate.

        Note: forces should be computed before this call from the cache refreshed by the
        **current-step** broadcast (the STAR path guarantees this explicitly with
        broadcast()/integrate()); this method keeps the legacy behavior for the baselines,
        which compute their forces internally before calling step (based on the previous
        step's cache); the broadcast inside this method guarantees that the cache is the
        current step's when forces are computed on the next call.
        """
        self.broadcast()
        self.integrate(forces, dt)
