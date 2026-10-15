"""Local agent: each vessel maintains only its own state; no global information."""
import numpy as np


class Agent:
    """Independent agent per vessel. Perceives only neighbors within the communication
    radius (injected via the comms layer)."""

    def __init__(self, idx, position, radius, v_max=200.0, energy=100.0,
                 seed=0):
        self.id = int(idx)
        self.position = np.asarray(position, dtype=float)
        self.velocity = np.zeros(2)
        self.radius = float(radius)
        self.v_max = float(v_max)
        self.energy = float(energy)
        self.capability = None
        self.seed = int(seed)
        self.rng = np.random.default_rng(int(seed))
        self.force = np.zeros(2)
        # Local perception cache (filled by comms.broadcast)
        self.neighbor_ids = np.zeros(0, dtype=int)
        self.neighbor_positions = np.zeros((0, 2))
        self.neighbor_radii = np.zeros(0)
        self.neighbor_velocities = np.zeros((0, 2))

    def reset_perception(self):
        self.neighbor_ids = np.zeros(0, dtype=int)
        self.neighbor_positions = np.zeros((0, 2))
        self.neighbor_radii = np.zeros(0)
        self.neighbor_velocities = np.zeros((0, 2))

    def move(self, force, dt):
        """Euler integration + velocity clamp + energy consumption."""
        force = np.asarray(force, dtype=float)
        self.force = force
        self.velocity += force * dt
        sp = np.linalg.norm(self.velocity)
        if sp > self.v_max:
            self.velocity *= self.v_max / sp
        self.position += self.velocity * dt
        self.energy -= np.linalg.norm(self.velocity) * dt * 0.001
        if self.energy < 0.0:
            self.energy = 0.0

    def clamp_to(self, width, height):
        """ROI boundary constraint (local constraint; no global information)."""
        m = self.radius * 0.5
        self.position[0] = min(max(self.position[0], m), width - m)
        self.position[1] = min(max(self.position[1], m), height - m)
