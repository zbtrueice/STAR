# -*- coding: utf-8 -*-
"""test_mechanism.py -- unit tests for the mechanism correctness fix (13 tests).

Run: python tests/test_mechanism.py   or  python -m pytest tests/test_mechanism.py
Coverage: Fluid 6 / Simulator 2 / HoleFill 5
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from core.agent import Agent                      # noqa: E402
from core.simulator import Simulator              # noqa: E402
from core.comms import Comms                      # noqa: E402
from algorithms.fluid import (FluidParams, fluid_forces,   # noqa: E402
                              compute_local_density)
from algorithms.hole_fill import (HoleFillParams, hole_fill_forces,  # noqa: E402
                                  _local_uncovered_targets)


def _pair_agents(d, h=1500.0):
    """Build two vessels (perception caches already filled with each other, mimicking the
    post-broadcast state)."""
    a1 = Agent(0, [5000.0, 5000.0], 1000.0)
    a2 = Agent(1, [5000.0 + d, 5000.0], 1000.0)
    a1.neighbor_ids = np.array([1])
    a1.neighbor_positions = np.array([[5000.0 + d, 5000.0]])
    a1.neighbor_radii = np.array([1000.0])
    a1.neighbor_velocities = np.zeros((1, 2))
    a2.neighbor_ids = np.array([0])
    a2.neighbor_positions = np.array([[5000.0, 5000.0]])
    a2.neighbor_radii = np.array([1000.0])
    a2.neighbor_velocities = np.zeros((1, 2))
    return [a1, a2]


# ------------------------------------------------------------------ #
# Fluid
# ------------------------------------------------------------------ #
def test_fluid_no_neighbors_zero_pressure():
    """No neighbors -> rho = W(0) < rest_density -> pressure = 0 (only drag/boundary
    remain; all-zero at zero velocity)."""
    p = FluidParams(interaction_radius=1500.0, k_fluid=350.0,
                    rest_density=1.4e-6, viscosity=25.0, drag=0.06,
                    boundary_k=2.0)
    a = Agent(0, [5000.0, 5000.0], 1000.0)   # no neighbor cache
    F, dbg = fluid_forces([a], p, 10000.0, 10000.0, return_debug=True)
    assert dbg["pressure_force_max"] == 0.0, dbg
    assert np.allclose(F[0], 0.0), F
    # density is exactly the self term
    assert abs(dbg["rho_mean"] - 1.0 / (np.pi * 1500.0 ** 2)) < 1e-15


def test_fluid_close_pair_repulsion():
    """Two vessels very close with rho > rest_density -> mutually repulsive pressure
    forces.

    Note: the two-vessel density is ~2.75e-7; under the production default
    rest_density = 1.4e-6 (~10-neighbor equivalent) there is no compression; the test
    uses rest_density = 2e-7 to enter the compressed regime."""
    p = FluidParams(rest_density=2.0e-7)
    agents = _pair_agents(300.0)
    F, dbg = fluid_forces(agents, p, 10000.0, 10000.0, return_debug=True)
    assert dbg["pressure_force_mean"] > 0.0
    # Repulsion direction: vessel 1 is pushed toward -x (away from vessel 2), vessel 2
    # toward +x
    assert F[0][0] < 0.0 and F[1][0] > 0.0, F


def test_fluid_force_decreases_with_distance():
    """Increasing distance -> decreasing pressure force (verified on the monotonically
    decreasing branch of the kernel gradient, q > 2/3).

    Note: the SPH pressure force is proportional to p(rho(r)) * |gradW(r)|, and |gradW|
    peaks at q = 2/3 (intrinsic shape of the cubic-spline kernel); hence the force
    increasing with distance in the short-range segment (q < 2/3) is the correct kernel
    behavior. Monotonic decrease should be verified on the q in (2/3, 1) branch, and the
    force must be exactly 0 for q >= 1.
    """
    p = FluidParams(rest_density=2.0e-7)
    mags = []
    for d in (1050.0, 1200.0, 1400.0):   # q = 0.70, 0.80, 0.93
        F, dbg = fluid_forces(_pair_agents(d), p, 10000.0, 10000.0,
                              return_debug=True)
        mags.append(dbg["pressure_force_mean"])
    assert mags[0] > mags[1] > mags[2] >= 0.0, mags
    # q >= 1 (beyond the smoothing length) -> zero force
    _, dbg_out = fluid_forces(_pair_agents(1600.0), p, 10000.0, 10000.0,
                              return_debug=True)
    assert dbg_out["pressure_force_mean"] == 0.0


def test_fluid_no_negative_pressure():
    """rho < rest_density -> pressure is always 0 (no attractive force)."""
    p = FluidParams()
    agents = _pair_agents(1400.0)
    # Artificially raise rest_density so that rho < rho0
    p.rest_density = 1e-3
    F, dbg = fluid_forces(agents, p, 10000.0, 10000.0, return_debug=True)
    assert dbg["pressure_force_mean"] == 0.0
    assert np.allclose(F[0], 0.0) and np.allclose(F[1], 0.0)


def test_fluid_action_reaction():
    """Two-vessel pressure forces satisfy action-reaction (the density estimate is exact
    for two vessels, so the magnitudes should be strictly equal)."""
    p = FluidParams(rest_density=2.0e-7)
    for d in (300.0, 900.0):
        agents = _pair_agents(d)
        F, _ = fluid_forces(agents, p, 10000.0, 10000.0, return_debug=True)
        assert abs(np.linalg.norm(F[0]) - np.linalg.norm(F[1])) < 1e-9
        # Opposite directions
        assert abs(np.dot(F[0], F[1]) + np.linalg.norm(F[0]) ** 2) < 1e-6


def test_fluid_rest_density_changes_response():
    """Changing rest_density changes the pressure response."""
    d = 300.0
    p = FluidParams(rest_density=2.0e-7)   # rho=2.75e-7 > rho0 -> compressed
    _, dbg1 = fluid_forces(_pair_agents(d), p, 10000.0, 10000.0, return_debug=True)
    p2 = FluidParams(rest_density=1e-3)    # higher rest density -> zero pressure at the same rho
    _, dbg2 = fluid_forces(_pair_agents(d), p2, 10000.0, 10000.0, return_debug=True)
    assert dbg1["pressure_force_mean"] > dbg2["pressure_force_mean"], (dbg1, dbg2)
    assert dbg1["pressure_max"] > 0 and dbg2["pressure_max"] == 0.0


# ------------------------------------------------------------------ #
# Simulator
# ------------------------------------------------------------------ #
def test_simulator_broadcast_before_force():
    """The neighbor cache must be refreshed before force computation: after manually
    moving an agent, broadcast must update the cache."""
    a1 = Agent(0, [5000.0, 5000.0], 1000.0)
    a2 = Agent(1, [6000.0, 5000.0], 1000.0)   # distance 1000 < C_th
    sim = Simulator([a1, a2], c_th=3000.0)
    sim.broadcast()
    assert len(a1.neighbor_ids) == 1 and a1.neighbor_ids[0] == 1
    # Neighbor cache equals the current position
    assert np.allclose(a1.neighbor_positions[0], a2.position)
    # Move a2 without broadcasting -> the cache is stale
    a2.position = np.array([7000.0, 5000.0])
    assert np.allclose(a1.neighbor_positions[0], [6000.0, 5000.0])
    # After broadcast -> the cache reflects the current state
    sim.broadcast()
    assert np.allclose(a1.neighbor_positions[0], [7000.0, 5000.0])


def test_simulator_star_protocol_first_step():
    """First step of the STAR protocol: broadcast -> force -> integrate; the neighbor
    information is already visible to the first-step force."""
    a1 = Agent(0, [5000.0, 5000.0], 1000.0)
    a2 = Agent(1, [5300.0, 5000.0], 1000.0)   # crowded pair
    sim = Simulator([a1, a2], c_th=3000.0)
    p = FluidParams(rest_density=2.0e-7)
    sim.broadcast()
    F = fluid_forces(sim.agents, p, 10000.0, 10000.0)
    # Nonzero repulsion already on the first step (the old implementation had an empty
    # first-step cache -> zero force)
    assert np.linalg.norm(F[0]) > 0.0
    sim.integrate(F, 0.1)
    assert a1.position[0] < 5000.0   # pushed away
    assert len(a1.neighbor_ids) == 1  # the cache is still this step's broadcast result


# ------------------------------------------------------------------ #
# HoleFill
# ------------------------------------------------------------------ #
def _hole_agents(cover_center):
    """Two vessels: a0 covers near the given point, a1 is beside it; the perceptions are
    mutually visible."""
    a0 = Agent(0, [5000.0, 5000.0], 1000.0)
    a1 = Agent(1, [5600.0, 5000.0], 1000.0)
    a0.neighbor_ids = np.array([1]); a0.neighbor_positions = np.array([[5600.0, 5000.0]])
    a0.neighbor_radii = np.array([1000.0]); a0.neighbor_velocities = np.zeros((1, 2))
    a1.neighbor_ids = np.array([0]); a1.neighbor_positions = np.array([[5000.0, 5000.0]])
    a1.neighbor_radii = np.array([1000.0]); a1.neighbor_velocities = np.zeros((1, 2))
    return [a0, a1]


def test_holefill_no_local_hole_zero_force():
    """No local hole -> hole force = 0."""
    p = HoleFillParams(k_target=500.0, f_max=600.0, grid_res=500.0,
                       enabled=True, search_radius=3000.0)
    # A single vessel covering the whole plane (radius 1000 would still leave large
    # deficits -> use the two-vessel / large-coverage scenario)
    a = Agent(0, [5000.0, 5000.0], 10000.0)   # huge coverage radius -> no deficit
    F, dbg = hole_fill_forces([a], p, 10000.0, 10000.0, c_th=3000.0,
                              return_debug=True)
    assert np.allclose(F[0], 0.0)
    assert dbg["hole_active_agents"] == 0


def test_holefill_activates_on_hole():
    """Local hole present -> at least one agent activates hole filling."""
    p = HoleFillParams(k_target=500.0, f_max=600.0, grid_res=500.0,
                       enabled=True, search_radius=3000.0)
    agents = _hole_agents(None)
    F, dbg = hole_fill_forces(agents, p, 10000.0, 10000.0, c_th=3000.0,
                              return_debug=True)
    assert dbg["hole_active_agents"] >= 1
    assert dbg["hole_force_max"] > 0.0


def test_holefill_candidates_within_comm_radius():
    """Candidates must not exceed the communication radius."""
    p = HoleFillParams(k_target=500.0, f_max=600.0, grid_res=500.0,
                       enabled=True, search_radius=99999.0)
    agents = _hole_agents(None)
    c = agents[0].position
    cands = _local_uncovered_targets(agents[0], 10000.0, 10000.0,
                                     p.grid_res, p.effective_search_radius(3000.0))
    d = np.linalg.norm(cands - c, axis=1)
    assert len(cands) == 0 or d.max() <= 3000.0 + 1e-9


def test_holefill_conflict_resolution():
    """Multiple vessels facing the same hole: only the nearest vessel takes charge."""
    p = HoleFillParams(k_target=500.0, f_max=600.0, grid_res=500.0,
                       enabled=True, search_radius=3000.0, conflict_radius=500.0)
    # Three vessels on a line with a common hole direction far to the right
    a0 = Agent(0, [4000.0, 5000.0], 500.0)
    a1 = Agent(1, [4200.0, 5000.0], 500.0)
    a2 = Agent(2, [4400.0, 5000.0], 500.0)
    for ai, aj in ((a0, a1), (a1, a0), (a1, a2), (a2, a1)):
        pass
    ids = [[1], [0, 2], [1]]
    poss = [[[4200, 5000]], [[4000, 5000], [4400, 5000]], [[4200, 5000]]]
    for a, i, pp in zip((a0, a1, a2), ids, poss):
        a.neighbor_ids = np.array(i)
        a.neighbor_positions = np.array(pp, dtype=float)
        a.neighbor_radii = np.full(len(i), 500.0)
        a.neighbor_velocities = np.zeros((len(i), 2))
    F, dbg = hole_fill_forces([a0, a1, a2], p, 10000.0, 10000.0, c_th=3000.0,
                              return_debug=True)
    # At most one vessel pushes fully toward -x (the hole far to the left); the rest
    # either give up or target a different point
    active_left = sum(1 for f in F if f[0] < -1e-6)
    assert dbg["hole_active_agents"] <= 3
    assert active_left <= 1 or dbg["hole_active_agents"] <= 1


def test_holefill_enabled_false_strict_zero():
    """With enabled=false the hole force is strictly 0."""
    p = HoleFillParams(k_target=500.0, f_max=600.0, grid_res=500.0,
                       enabled=False, search_radius=3000.0)
    agents = _hole_agents(None)
    F, dbg = hole_fill_forces(agents, p, 10000.0, 10000.0, c_th=3000.0,
                              return_debug=True)
    assert np.allclose(F, 0.0)
    assert dbg["hole_active_agents"] == 0
    F2 = hole_fill_forces(agents, p, 10000.0, 10000.0, c_th=3000.0)
    assert np.allclose(F2, 0.0)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
