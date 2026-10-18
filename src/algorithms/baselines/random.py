"""Fully distributed random walk: each vessel moves in an independent random direction."""
import numpy as np
import math


def random_forces(agents, step_size=80.0):
    forces = np.zeros((len(agents), 2))
    for i, a in enumerate(agents):
        th = a.rng.uniform(0.0, 2.0 * math.pi)
        forces[i] = step_size * np.array([np.cos(th), np.sin(th)])
    return forces


def stage_random(sim, dt, steps, step_size=80.0):
    for _ in range(steps):
        f = random_forces(sim.agents, step_size)
        sim.step(f, dt)
    return sim
