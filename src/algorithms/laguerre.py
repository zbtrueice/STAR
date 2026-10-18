"""Global Laguerre (power) diagram, used for offline evaluation metrics.

This module implements the full power diagram of a swarm clipped to the ROI,
as described in Section 3.3 of the manuscript.  Each USV ``i`` at ``x_i`` with
sensing radius ``r_i`` owns the cell

    V_i = { p : ||p - x_i||^2 - r_i^2  <=  ||p - x_j||^2 - r_j^2   for all j },

i.e. all points whose Laguerre (power) distance to ``i`` is minimal.  The
bisector of two sites is an Apollonius circle/line.

Implementation
--------------
The power diagram is computed via Aurenhammer's lifting: sites are lifted to
``q_i = (x_i, y_i, x_i^2 + y_i^2 - r_i^2)``; facets of the LOWER hull of the
lifted points project to the *regular triangulation* (weighted Delaunay),
which is the straight dual of the power diagram.  Two sites linked by a
regular-triangulation edge are exactly the sites whose power cells share an
edge, so each cell is the intersection of a handful of halfplanes (one per
power-neighbor) clipped to the ROI box — done with shapely.

Sites whose power cell is empty (dominated by a stronger neighbor) do not
appear on the lower hull and are reported with ``polygon is None``.

This module also provides the per-cell *MiniMax point*: the center of the
minimum enclosing circle of the cell polygon (Welzl's algorithm) — the
position from which a USV minimizes the worst-case distance to any point of
its cell (Section 3.4 of the manuscript).

Note: the distributed controller never computes this global diagram; it is an
offline evaluation instrument only (Section 3.5).
"""

import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon, box


# ----------------------------------------------------------------------
def laguerre_distance(point, usv):
    """Power distance  d_L(p, i) = ||p - x_i||^2 - r_i^2."""
    return float(np.sum((np.asarray(point) - usv.position) ** 2) - usv.radius ** 2)


def power_distance_matrix(grid, pos, radii):
    """Vectorized  G x N  matrix of power distances (grid: M x 2)."""
    diff = grid[:, None, :] - pos[None, :, :]
    return np.einsum('gmw,gmw->gm', diff, diff) - (radii ** 2)[None, :]


def assign_cells(grid, swarm):
    """Assign each grid point to the USV with minimal Laguerre distance."""
    P = power_distance_matrix(np.asarray(grid), swarm.positions(), swarm.radii())
    return np.argmin(P, axis=1)


def power_adjacency(pos, radii):
    """Site pairs whose power cells can share an edge.

    Uses Aurenhammer lifting on *normalized* coordinates: sites are mapped to
    the unit square and lifted to  q_i = (x, y, |x|^2 - r^2/s^2)  with s the
    normalization scale (power diagrams are invariant under uniform scaling).
    Normalization fixes the catastrophic conditioning that broke the raw-scale
    hull (|x|^2 ~ 1e8 vs r^2 ~ 1e6 made QHull facet normals numerically zero).
    Lower-hull facets of the lifted points give the regular triangulation —
    exactly the straight-line dual of the power diagram.

    For safety, each site additionally keeps its k=6 nearest sites (by power
    distance at its own location) as candidates; redundant halfplanes are
    harmless (they just don't bind).
    """
    n = len(pos)
    if n == 1:
        return [set()]
    adj = [set() for _ in range(n)]

    span = pos.max(axis=0) - pos.min(axis=0)
    s = float(span.max()) if span.max() > 0 else 1.0
    xy = (pos - pos.min(axis=0)) / s
    z = np.sum(xy**2, axis=1) - (radii / s) ** 2
    lifted = np.column_stack([xy, z])

    if n == 2:
        adj[0].add(1); adj[1].add(0)
    elif n == 3:
        for i in range(3):
            adj[i] |= set(range(3)) - {i}
    else:
        try:
            hull = ConvexHull(lifted, qhull_options='Pp')
            for simplex, eq in zip(hull.simplices, hull.equations):
                if eq[2] < -1e-12:            # lower hull facet
                    i, j, k = (int(v) for v in simplex)
                    adj[i] |= {j, k}; adj[j] |= {i, k}; adj[k] |= {i, j}
        except Exception:
            pass  # degenerate layout — fall through to kNN candidates only

    # kNN candidates by power distance evaluated at each site's own position
    d = ((pos[:, None, :] - pos[None, :, :]) ** 2).sum(-1)
    power_at = d - (radii ** 2)[None, :]
    k = min(n - 1, 6)
    for j in range(n):
        for i in np.argsort(power_at[j])[:k + 1]:
            i = int(i)
            if i != j:
                adj[j].add(i); adj[i].add(j)
    return adj


# ----------------------------------------------------------------------
def minimum_enclosing_circle(points):
    """Welzl's MEC — returns (center, radius). Exact for polygon vertices."""
    pts = np.asarray(points, dtype=float)
    if len(pts) == 0:
        return np.zeros(2), 0.0
    if len(pts) <= 2:
        c = pts.mean(axis=0) if len(pts) == 2 else pts[0]
        return c.copy(), float(np.linalg.norm(pts - c, axis=1).max())
    rng = np.random.default_rng(12345)
    shuffled = pts[rng.permutation(len(pts))].tolist()

    def circle2(a, b):
        c = (np.asarray(a) + np.asarray(b)) / 2.0
        r = np.linalg.norm(np.asarray(a) - c)
        return c, r

    def circle3(a, b, c):
        a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
        d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-12:
            return None
        ux = ((a[0]**2 + a[1]**2) * (b[1] - c[1])
              + (b[0]**2 + b[1]**2) * (c[1] - a[1])
              + (c[0]**2 + c[1]**2) * (a[1] - b[1])) / d
        uy = ((a[0]**2 + a[1]**2) * (c[0] - b[0])
              + (b[0]**2 + b[1]**2) * (a[0] - c[0])
              + (c[0]**2 + c[1]**2) * (b[0] - a[0])) / d
        center = np.array([ux, uy])
        return center, float(np.linalg.norm(a - center))

    def in_circle(circ, p, eps=1e-9):
        return circ is not None and np.linalg.norm(np.asarray(p) - circ[0]) <= circ[1] + eps

    def welzl(P, R):
        if not P or len(R) == 3:
            if len(R) == 0:
                return (np.zeros(2), 0.0)
            if len(R) == 1:
                return (np.asarray(R[0], dtype=float), 0.0)
            if len(R) == 2:
                return circle2(R[0], R[1])
            # 3 boundary points: try pairs first (right triangle case)
            for keep in ((0, 1), (0, 2), (1, 2)):
                c2 = circle2(R[keep[0]], R[keep[1]])
                if all(in_circle(c2, q) for q in R):
                    return c2
            return circle3(R[0], R[1], R[2])
        p = P[-1]
        P = P[:-1]
        circ = welzl(P, R)
        if in_circle(circ, p):
            return circ
        return welzl(P, R + [p])

    center, radius = welzl(shuffled, [])
    return center, radius


# ----------------------------------------------------------------------
class LaguerreDiagram:
    """Power diagram of a swarm clipped to the rectangular ROI."""

    def __init__(self, swarm, guard_margin=None):
        self.swarm = swarm
        self.pos = swarm.positions().copy()
        self.radii = swarm.radii().copy()
        self.width, self.height = swarm.width, swarm.height
        m = guard_margin if guard_margin is not None else 0.02 * max(swarm.width, swarm.height)
        self.roi = box(0.0, 0.0, swarm.width, swarm.height)
        # filled by compute()
        self.polygons = [None] * swarm.n
        self.areas = np.zeros(swarm.n)
        self.centroids = np.zeros((swarm.n, 2))
        self.minimax = np.zeros((swarm.n, 2))
        self.covering_radius = np.zeros(swarm.n)  # worst distance cell -> site
        self.adjacency = [set() for _ in range(swarm.n)]
        self.empty_cells = []
        self._compute()

    # ------------------------------------------------------------------
    def _compute(self):
        n = self.swarm.n
        adj = power_adjacency(self.pos, self.radii)
        self.adjacency = adj

        for i in range(n):
            poly = self.roi
            for j in sorted(adj[i]):
                a, b = self._bisector(i, j)
                poly = poly.intersection(self._halfplane(a, b))
                if poly.is_empty:
                    break
            self.polygons[i] = None if (poly.is_empty or poly.area < 1e-6) else poly
        self._repair_overlaps()
        self._finalize_cells()

    # ------------------------------------------------------------------
    def _bisector(self, i, j):
        """Halfplane  a.p <= b  keeps cell of ``i`` against site ``j``."""
        xi, ri = self.pos[i], self.radii[i]
        xj, rj = self.pos[j], self.radii[j]
        a = 2.0 * (xj - xi)
        b = (xj @ xj - rj * rj) - (xi @ xi - ri * ri)
        return a, b

    # ------------------------------------------------------------------
    def _repair_overlaps(self, max_passes=8, area_eps=1.0):
        """Exact fix-up: far sites can be power neighbors without being kNN
        (Delaunay adjacency is not a subgraph of the k-NN graph), so initial
        candidates can miss a bisector — detected as cell overlap and repaired
        by clipping the offending pairs, iterated until no overlaps remain."""
        for _ in range(max_passes):
            fixed = False
            for i in range(self.swarm.n):
                pa = self.polygons[i]
                if pa is None:
                    continue
                for j in range(i + 1, self.swarm.n):
                    pb = self.polygons[j]
                    if pb is None:
                        continue
                    bia, bib = pa.bounds, pb.bounds
                    if (bia[2] <= bib[0] or bib[2] <= bia[0]
                            or bia[3] <= bib[1] or bib[3] <= bia[1]):
                        continue
                    if pa.intersection(pb).area <= area_eps:
                        continue
                    aij, bij = self._bisector(i, j)
                    ci = pa.intersection(self._halfplane(aij, bij))
                    cj = pb.intersection(self._halfplane(-aij, -bij))
                    self.polygons[i] = ci if not ci.is_empty else None
                    self.polygons[j] = cj if not cj.is_empty else None
                    self.adjacency[i].add(j)
                    self.adjacency[j].add(i)
                    pa = self.polygons[i]
                    pb = self.polygons[j]
                    fixed = True
                    if pa is None:
                        break
            if not fixed:
                break

    # ------------------------------------------------------------------
    def _finalize_cells(self):
        """(Re)compute area / centroid / minimax / covering radius per cell."""
        self.areas = np.zeros(self.swarm.n)
        self.centroids = np.zeros((self.swarm.n, 2))
        self.minimax = np.zeros((self.swarm.n, 2))
        self.covering_radius = np.zeros(self.swarm.n)
        self.empty_cells = []
        for i, poly in enumerate(self.polygons):
            if poly is None or poly.is_empty or poly.area < 1e-6:
                self.polygons[i] = None
                self.empty_cells.append(i)
                continue
            if poly.geom_type == 'MultiPolygon':
                poly = max(poly.geoms, key=lambda g: g.area)
                self.polygons[i] = poly
            self.areas[i] = poly.area
            self.centroids[i] = np.array(poly.centroid.coords[0])
            verts = np.asarray(poly.exterior.coords)
            mm, _ = minimum_enclosing_circle(verts[:-1] if len(verts) > 1 else verts)
            self.minimax[i] = mm
            self.covering_radius[i] = float(
                np.linalg.norm(verts - self.pos[i], axis=1).max())

    # ------------------------------------------------------------------
    @staticmethod
    def _halfplane(a, b, reach=3.0e6):
        a = np.asarray(a, dtype=float)
        nrm = np.linalg.norm(a)
        if nrm < 1e-12:
            return box(-reach, -reach, reach, reach) if b >= 0 else Polygon()
        # closest point of the line a.p = b to the origin, then big square
        p0 = a * (b / (nrm * nrm))              # projection of origin
        t = np.array([-a[1], a[0]]) / nrm       # line direction
        p1, p2 = p0 + reach * t, p0 - reach * t
        # third/fourth corners pushed into the feasible side (-a direction)
        off = -a / nrm * reach
        return Polygon([p1, p2, p2 + off, p1 + off])

    # ------------------------------------------------------------------
    def cell_of(self, i):
        return self.polygons[i]

    def summary(self):
        return {
            'n': self.swarm.n,
            'n_empty': len(self.empty_cells),
            'total_area': float(self.areas.sum()),
            'roi_area': float(self.width * self.height),
            'mean_covering_radius': float(self.covering_radius.mean()),
            'max_covering_radius': float(self.covering_radius.max()),
        }
