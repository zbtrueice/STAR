"""Stage 1 -- local compressible-fluid self-diffusion (fully distributed version).

Mechanism correctness fix (2026-09-25): implements a genuine density -> pressure -> force
SPH-style mechanism.

    rho_i = W(0) + Sum_j m_j W(r_ij, h)                     (cubic spline kernel, m_j = 1)
    p_i   = k_fluid * max(rho_i / rest_density - 1, 0)     (rest_density truly participates:
                                                            pressure is zero for rho <= rho0,
                                                            so diffusion self-terminates)
    F_pres_i = -Sum_j m_j * (p_i + p_j) / (2 rho_j) * gradW_ij   (symmetric pairwise pressure)
    F_i      = F_pres + F_visc(XSPH) + F_drag + F_boundary (components computed separately,
                                                            so each can be output for debug)

Distributed-design notes:
- The neighbor density rho_j is estimated from the local view of this vessel:
  rho_j ~= W(d_ij) + Sum_{k in N_i, k != j} W(|x_j - x_k|, h).
  Only neighbor_positions are used (the communicated content is unchanged:
  position / radius / velocity); no global coverage map or extra communication field is
  introduced. This estimate ignores the neighbors of j that lie outside this vessel's
  communication range (which underestimates rho_j); it is the standard approximation
  under a purely distributed constraint, and it is exact for two-vessel systems (the
  estimate then coincides with the true value and action-reaction holds strictly).
- gradW_ij = (dW/dq) * (x_i - x_j) / (h * r_ij), with dW/dq = (-3q + 2.25q^2)/(pi h^2) <= 0
  (q > 0); hence the -gradW term produces a repulsive force pointing from j to i. The more
  compressed the configuration (larger rho), the larger the pressure; pressure is exactly
  zero whenever rho <= rho0.
"""
import numpy as np

_EPS = 1e-9


class FluidParams:
    def __init__(self, interaction_radius=1500.0, k_fluid=350.0,
                 rest_density=1.4e-6, viscosity=25.0, drag=0.06,
                 boundary_k=2.0):
        self.interaction_radius = float(interaction_radius)
        self.k_fluid = float(k_fluid)
        self.rest_density = float(rest_density)
        if self.rest_density <= 0.0:
            raise ValueError("rest_density must be positive")
        self.viscosity = float(viscosity)
        self.drag = float(drag)
        self.boundary_k = float(boundary_k)


def _kernel_and_grad(d, h):
    """Cubic-spline kernel W and its scalar derivative dW/dr (w.r.t. r), given an input
    distance array d (already clipped to [0, h]).

    W(q)  = (1 - 1.5q^2 + 0.75q^3)/(pi h^2)
    dW/dr = dW/dq / h,  dW/dq = (-3q + 2.25q^2)/(pi h^2)   (<= 0, W decreases with r)
    """
    q = np.clip(d / h, 0.0, 1.0)
    w = (1.0 - 1.5 * q ** 2 + 0.75 * q ** 3) / (np.pi * h * h)
    dwdq = (-3.0 * q + 2.25 * q ** 2) / (np.pi * h * h)
    return w, dwdq / h


def compute_local_density(agent, params):
    """Per-vessel local density: rho_i = W(0) + sum_j W(r_ij, h). Includes the self term,
    so an isolated vessel has rho = W(0) > 0."""
    h = params.interaction_radius
    rho = 1.0 / (np.pi * h * h)
    if len(agent.neighbor_positions) == 0:
        return rho
    d = np.linalg.norm(agent.neighbor_positions - agent.position, axis=1)
    inside = d < h
    if not inside.any():
        return rho
    w, _ = _kernel_and_grad(d[inside], h)
    return rho + float(w.sum())


def _estimate_neighbor_density(agent, params):
    """Per-neighbor density estimate from this vessel's local view (distributed
    approximation; see the module docstring).

    Returns (d, w, dWdr, rho_j_est) over the valid neighbors with d < h only.
    """
    h = params.interaction_radius
    nb_pos = agent.neighbor_positions
    d_all = np.linalg.norm(nb_pos - agent.position, axis=1)
    inside = np.where(d_all < h)[0]
    if len(inside) == 0:
        return None
    d = np.maximum(d_all[inside], _EPS)
    w, dWdr = _kernel_and_grad(d, h)
    # rho_j_est = W(0) + W(d_ij) + Sum_{k in N_i, k != j} W(|x_j - x_k|)
    n_in = len(inside)
    rho_j = np.full(n_in, 1.0 / (np.pi * h * h)) + w.copy()
    if n_in > 1:
        pos_in = nb_pos[inside]
        diff = pos_in[:, None, :] - pos_in[None, :, :]
        dist = np.linalg.norm(diff, axis=2)              # (n_in, n_in)
        np.fill_diagonal(dist, np.inf)                   # exclude self-pairs
        mask = dist < h
        w_pair = np.zeros_like(dist)
        if mask.any():
            w_pair[mask] = _kernel_and_grad(dist[mask], h)[0]
        rho_j += w_pair.sum(axis=1)                      # k runs over other neighbors in N_i
    rho_j = np.maximum(rho_j, 1.0 / (np.pi * h * h))     # self-term lower bound, avoids /0
    return d, w, dWdr, rho_j


def _boundary_force(pos, params, width, height):
    F = np.zeros(2)
    if params.boundary_k > 0.0:
        margin = params.interaction_radius * 0.5
        for k, hi in enumerate((width, height)):
            lo_pen = max(margin - pos[k], 0.0)
            hi_pen = max(pos[k] - (hi - margin), 0.0)
            F[k] += params.boundary_k * (lo_pen - hi_pen)
    return F


def fluid_forces(agents, params, width, height, return_debug=False):
    """Compute the fluid force for every vessel: pressure + viscosity + drag + boundary.
    Returns the forces array.

    With return_debug=True it additionally returns a per-component statistics dict
    (rho / pressure / mean, max of each force component).
    """
    n = len(agents)
    forces = np.zeros((n, 2))
    f_pres = np.zeros((n, 2))
    f_visc = np.zeros((n, 2))
    f_bnd = np.zeros((n, 2))
    rho_all = np.zeros(n)
    p_all = np.zeros(n)
    h = params.interaction_radius

    for i, a in enumerate(agents):
        pos, vel = a.position, a.velocity
        rho_i = compute_local_density(a, params)
        rho_all[i] = rho_i
        p_i = params.k_fluid * max(rho_i / params.rest_density - 1.0, 0.0)
        p_all[i] = p_i

        est = _estimate_neighbor_density(a, params)
        if est is not None:
            d, w, dWdr, rho_j = est
            nb_inside = np.where(np.linalg.norm(
                a.neighbor_positions - pos, axis=1) < h)[0]
            nb_vel = a.neighbor_velocities[nb_inside]
            # Direction: x_i - x_j (from the neighbor toward this vessel)
            dvec = (pos - a.neighbor_positions[nb_inside]) / d[:, None]
            # Symmetric pressure force: F = -Sum m_j (p_i+p_j)/(2 rho_j) gradW_ij,
            # with gradW_ij = dW/dr * (x_i-x_j)/r; dW/dr <= 0 -> repulsion (away from
            # the neighbor).
            p_j = params.k_fluid * np.maximum(rho_j / params.rest_density - 1.0, 0.0)
            coef = -(p_i + p_j) / (2.0 * rho_j) * dWdr      # >= 0
            f_pres[i] = (coef[:, None] * dvec).sum(axis=0)
            # XSPH viscosity (consistent with the original version): Sum mu W(q) (v_j - v_i)
            if params.viscosity > 0.0:
                f_visc[i] = ((params.viscosity * w)[:, None]
                             * (nb_vel - vel)).sum(axis=0)
        # Drag + boundary
        f_drag = -params.drag * float(np.linalg.norm(vel)) * vel
        f_bnd[i] = _boundary_force(pos, params, width, height)
        forces[i] = f_pres[i] + f_visc[i] + f_drag + f_bnd[i]

    if return_debug:
        drag_norm = np.array([params.drag * float(np.linalg.norm(a.velocity)) ** 2
                              for a in agents])
        dbg = {
            "rho_mean": float(rho_all.mean()), "rho_max": float(rho_all.max()),
            "pressure_mean": float(p_all.mean()), "pressure_max": float(p_all.max()),
            "pressure_force_mean": float(np.linalg.norm(f_pres, axis=1).mean()),
            "pressure_force_max": float(np.linalg.norm(f_pres, axis=1).max()),
            "viscosity_force_mean": float(np.linalg.norm(f_visc, axis=1).mean()),
            "viscosity_force_max": float(np.linalg.norm(f_visc, axis=1).max()),
            "drag_force_mean": float(drag_norm.mean()),
            "drag_force_max": float(drag_norm.max()),
            "boundary_force_mean": float(np.linalg.norm(f_bnd, axis=1).mean()),
            "boundary_force_max": float(np.linalg.norm(f_bnd, axis=1).max()),
            "total_force_mean": float(np.linalg.norm(forces, axis=1).mean()),
            "total_force_max": float(np.linalg.norm(forces, axis=1).max()),
        }
        return forces, dbg
    return forces
