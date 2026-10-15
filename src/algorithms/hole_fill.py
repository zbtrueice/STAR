"""Distributed hole filling (fully distributed version): local deficit trigger +
communication-range constraint + conflict resolution.

Mechanism correctness fix (2026-09-25):
- Trigger: a vessel enters hole-target search only if a local coverage deficit exists
  within the effective search radius (grid sample points not covered by itself or its
  neighbors); vessels without a deficit apply zero force and skip. The criterion is purely
  local (own + neighbor coverage) and uses no global coverage map.
- Search extent: a circular window centered on the vessel, of radius
      effective_search_radius = min(search_radius(config), communication.radius)
  Candidates must satisfy ||p - x_i|| <= r_eff -- targets beyond the communication range
  are strictly excluded (the old square window with half = grid_res*6 reached 4243 m at the
  corners, above C_th = 3000 m, and has been removed).
- Resolution: hole detection is defined on the grid_res sampling grid (candidates are grid
  points, not a continuous-domain guarantee); the coverage test uses the strict inequality
  d^2 < r^2 to avoid numerical artifacts when a grid point lies exactly on a coverage-disk
  boundary. The candidate count is returned via the debug output.
- Conflict resolution: for the nearest selected hole, if a neighbor has selected the same or
  a nearby hole (distance < conflict_radius) and is closer to it, this vessel backs off; on
  equal distance the vessel with the smaller agent id wins (stable tie-break). Each local
  hole is therefore handled by the nearest reachable vessel.
- Force: toward the selected target, magnitude min(k_target*d, f_max), with numerical
  protection on the direction (d > eps).
"""
import numpy as np


class HoleFillParams:
    def __init__(self, k_target=500.0, f_max=600.0, grid_res=500.0,
                 enabled=True, search_radius=None, conflict_radius=None):
        self.k_target = float(k_target)
        self.f_max = float(f_max)
        self.grid_res = float(grid_res)
        self.enabled = bool(enabled)
        # None -> no independent cap; only constrained by the communication radius
        self.search_radius = float(search_radius) if search_radius is not None else None
        # None -> legacy behavior 0.3 * self.radius
        self.conflict_radius = (float(conflict_radius)
                                if conflict_radius is not None else None)

    def effective_search_radius(self, c_th):
        """Effective search radius: min(search_radius, communication.radius)."""
        r = self.search_radius
        if c_th is not None:
            r = float(c_th) if r is None else min(r, float(c_th))
        if r is None:
            raise ValueError("effective search radius undefined: "
                             "need search_radius or c_th")
        return r


def _local_uncovered_targets(agent, width, height, grid_res, r_eff):
    """Local uncovered grid sample points inside a circular window of radius r_eff centered
    on the vessel (local information only).

    Coverage test: d^2 < r^2 (strict); sampling resolution grid_res.
    Returns the candidate array (n_cand, 2).
    """
    c = agent.position
    # Grid-aligned square bounding box (minimum extent covering the circular window),
    # then filtered by the circular window
    xs = np.arange(np.floor((c[0] - r_eff) / grid_res) * grid_res,
                   c[0] + r_eff + grid_res, grid_res)
    ys = np.arange(np.floor((c[1] - r_eff) / grid_res) * grid_res,
                   c[1] + r_eff + grid_res, grid_res)
    xs = xs[(xs >= 0.0) & (xs <= width)]
    ys = ys[(ys >= 0.0) & (ys <= height)]
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((0, 2))
    gx, gy = np.meshgrid(xs, ys)
    grid = np.column_stack([gx.ravel(), gy.ravel()])
    # Communication-range circular window constraint (strictly <= r_eff)
    grid = grid[np.sum((grid - c) ** 2, axis=1) <= r_eff ** 2]
    if len(grid) == 0:
        return grid
    # Remove points inside this vessel's own sensing disk (strict inequality avoids
    # boundary artifacts)
    inside = np.sum((grid - c) ** 2, axis=1) < agent.radius ** 2
    grid = grid[~inside]
    # Remove points covered by any neighbor's sensing disk
    if len(grid) == 0:
        return grid
    nb_pos = agent.neighbor_positions
    nb_rad = agent.neighbor_radii
    if len(nb_pos) > 0:
        d2 = np.sum((grid[:, None, :] - nb_pos[None, :, :]) ** 2, axis=2)
        covered = (d2 < (nb_rad ** 2)[None, :]).any(axis=1)
        grid = grid[~covered]
    return grid


def hole_fill_forces(agents, params, width, height, c_th=None,
                     return_debug=False):
    """Compute the hole-filling force for every vessel (subject to the trigger condition,
    the communication range, and conflict resolution).

    c_th: communication radius (from communication.radius); combined with
    params.search_radius via min().
    With return_debug=True it additionally returns a dict: hole_candidates (candidate
    count per vessel), hole_active_agents, selected_target_distance, hole_force_mean/max.
    """
    forces = np.zeros((len(agents), 2))
    dbg = {"hole_candidates": [], "active": [], "target_dist": [],
           "fmax_mag": 0.0}
    if not params.enabled:
        if return_debug:
            return forces, {"hole_candidates": [0] * len(agents),
                            "hole_active_agents": 0,
                            "selected_target_distance": [],
                            "hole_force_mean": 0.0, "hole_force_max": 0.0}
        return forces

    r_eff = params.effective_search_radius(c_th)
    # Pass 1: trigger test + nearest target (trigger = local coverage deficit exists
    # within the effective radius)
    targets = []
    for i, a in enumerate(agents):
        grid = _local_uncovered_targets(a, width, height, params.grid_res, r_eff)
        dbg["hole_candidates"].append(int(len(grid)))
        if len(grid) == 0:
            targets.append(None)          # no local deficit -> no trigger
            continue
        d = np.sqrt(np.sum((grid - a.position) ** 2, axis=1))
        j = int(np.argmin(d))
        targets.append((grid[j], float(d[j])))

    # Pass 2: conflict resolution (based on local neighbor information; stable tie-break:
    # the smaller id takes charge)
    selected = {}
    for i, a in enumerate(agents):
        t = targets[i]
        if t is None:
            dbg["active"].append(0)
            continue
        hole, d = t
        conflict_radius = (params.conflict_radius if params.conflict_radius
                           is not None else 0.3 * a.radius)
        give_up = False
        for j in range(len(a.neighbor_ids)):
            nj = int(a.neighbor_ids[j])
            if nj >= len(targets) or targets[nj] is None:
                continue
            h2, d2 = targets[nj]
            same_hole = np.sum((h2 - hole) ** 2) < conflict_radius ** 2
            # Neighbor is closer -> give up; equally close -> smaller id takes charge
            # (stable tie-break)
            if same_hole and (d2 < d or (d2 == d and nj < i)):
                give_up = True
                break
        dbg["active"].append(0 if give_up else 1)
        if give_up:
            continue
        dirv = hole - a.position
        dn = float(np.linalg.norm(dirv))
        if dn > 1e-6:
            mag = min(params.k_target * dn / 1e3, params.f_max)
            forces[i] += mag * dirv / dn
            dbg["target_dist"].append(float(dn))
            dbg["fmax_mag"] = max(dbg["fmax_mag"], float(mag))

    if return_debug:
        mags = np.linalg.norm(forces, axis=1)
        dbg_out = {"hole_candidates": dbg["hole_candidates"],
                   "hole_active_agents": int(sum(dbg["active"])),
                   "selected_target_distance": dbg["target_dist"],
                   "hole_force_mean": float(mags.mean()),
                   "hole_force_max": float(mags.max())}
        return forces, dbg_out
    return forces
