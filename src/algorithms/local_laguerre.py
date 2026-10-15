"""Local Laguerre cell (fully distributed version).

Each vessel builds its own cell using only neighbors within the communication radius
(neighbor_positions/radii):
V_i = ROI (intersection) over j in neighbors of {p : ||p-x_i||^2 - r_i^2 <= ||p-x_j||^2 - r_j^2}
Only neighbors that actually constrain the cell are kept (a neighbor is kept only if the
clipping is non-empty). The centroid and the MiniMax point (center of the minimal enclosing
circle, Welch linear implementation) are computed for the local cell.
"""
import numpy as np
from shapely.geometry import Polygon, box


def _halfplane(xi, ri, xj, rj, reach=3.0e6):
    """Half-plane keeping p that satisfies |p-xi|^2 - ri^2 <= |p-xj|^2 - rj^2."""
    a = 2.0 * (xj - xi)
    b = (xj @ xj - rj * rj) - (xi @ xi - ri * ri)
    nrm = np.linalg.norm(a)
    if nrm < 1e-12:
        return box(-reach, -reach, reach, reach) if b >= 0 else Polygon()
    p0 = a * (b / (nrm * nrm))
    t = np.array([-a[1], a[0]]) / nrm
    p1, p2 = p0 + reach * t, p0 - reach * t
    off = -a / nrm * reach
    return Polygon([p1, p2, p2 + off, p1 + off])


def _minimax(points):
    """Linear-scan minimal enclosing circle (approximate -- accurate enough for small
    cells)."""
    pts = np.asarray(points, dtype=float)
    if len(pts) == 0:
        return np.zeros(2)
    if len(pts) <= 2:
        c = pts.mean(axis=0) if len(pts) == 2 else pts[0]
        return c
    # Initialize from the midpoint of the two farthest points, then expand iteratively
    center = pts.mean(axis=0)
    for _ in range(3):
        d = np.linalg.norm(pts - center, axis=1)
        if d.max() == 0:
            break
        far = pts[np.argmax(d)]
        # Move the center outward along the far-center direction
        vec = far - center
        dist = np.linalg.norm(vec)
        shift = (dist - d.max()) / (2 * dist) if dist > 0 else 0
        center = center + shift * vec
    return center


class LocalLaguerreCell:
    """Result container for the local cell of a single vessel."""

    def __init__(self, polygon, centroid, minimax, covering_radius, empty):
        self.polygon = polygon
        self.centroid = centroid
        self.minimax = minimax
        self.covering_radius = covering_radius
        self.empty = empty


def local_cell_for(agent, width, height, weighted=True):
    """Build the local cell for a single vessel (neighbor information only).
    Returns a LocalLaguerreCell.

    weighted=True  -> Laguerre cell (uses neighbor radii,
                      |p-xi|^2 - ri^2 <= |p-xj|^2 - rj^2)
    weighted=False -> Euclidean cell (radii ignored; used for the -Laguerre ablation
                      experiment)
    """
    roi = box(0.0, 0.0, width, height)
    xi = agent.position
    ri = agent.radius if weighted else 0.0
    poly = roi
    nb_pos = agent.neighbor_positions
    nb_rad = agent.neighbor_radii
    # Neighbors sorted by ascending distance: clipping by near neighbors first closes the
    # cell faster and reduces shapely calls (semantics unchanged)
    if len(nb_pos) > 1:
        dist = np.sum((nb_pos - xi) ** 2, axis=1)
        order = np.argsort(dist)
        nb_pos = nb_pos[order]
        nb_rad = nb_rad[order]
    for j in range(len(nb_pos)):
        xj = nb_pos[j]
        rj = nb_rad[j] if weighted else 0.0
        hp = _halfplane(xi, ri, xj, rj)
        newp = poly.intersection(hp)
        if newp.is_empty:
            break
        poly = newp
    if poly.is_empty or poly.area < 1e-6:
        return LocalLaguerreCell(None, xi.copy(), xi.copy(), 0.0, True)
    if poly.geom_type == 'MultiPolygon':
        poly = max(poly.geoms, key=lambda g: g.area)
    centroid = np.array(poly.centroid.coords[0])
    verts = np.asarray(poly.exterior.coords)[:-1]
    mm = _minimax(verts)
    cover = float(np.linalg.norm(verts - xi, axis=1).max()) if len(verts) else 0.0
    return LocalLaguerreCell(poly, centroid, mm, cover, False)
