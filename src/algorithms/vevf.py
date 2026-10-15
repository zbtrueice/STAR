"""Local VEVF (fully distributed version): vertex / centroid / edge forces all based on
the local cell."""
import numpy as np
from .local_laguerre import local_cell_for


class VEVFParams:
    def __init__(self, k_vertex=500.0, k_edge=300.0, k_centroid=400.0,
                 f_max=600.0):
        self.k_vertex = float(k_vertex)
        self.k_edge = float(k_edge)
        self.k_centroid = float(k_centroid)
        self.f_max = float(f_max)


def vevf_forces(agents, params, width, height, weighted=True):
    """Compute the local VEVF for every vessel (based on the local cell minimax / centroid
    / edge midpoints).

    With weighted=False the Euclidean cell is used (-Laguerre ablation experiment).
    """
    forces = np.zeros((len(agents), 2))
    for i, a in enumerate(agents):
        cell = local_cell_for(a, width, height, weighted=weighted)
        F = np.zeros(2)
        if not cell.empty:
            # Vertex force -> MiniMax point
            d = cell.minimax - a.position
            dn = np.linalg.norm(d)
            if dn > 1e-6:
                F += min(params.k_vertex * dn / 1e3, params.f_max) * d / dn
            # Centroid spring
            dc = cell.centroid - a.position
            dcn = np.linalg.norm(dc)
            if dcn > 1e-6:
                F += min(params.k_centroid * dcn / 1e3, params.f_max) * dc / dcn
            # Edge force -> midpoint of the farthest edge
            if params.k_edge > 0.0 and cell.polygon is not None:
                coords = np.asarray(cell.polygon.exterior.coords)
                if len(coords) >= 3:
                    mids = 0.5 * (coords[:-1] + coords[1:])
                    far = mids[np.argmax(
                        np.linalg.norm(mids - a.position, axis=1))]
                    de = far - a.position
                    den = np.linalg.norm(de)
                    if den > 1e-6:
                        F += min(params.k_edge * den / 1e3,
                                 params.f_max) * de / den
        forces[i] = F
    return forces
