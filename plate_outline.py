"""Derive the plate's boundary outline from the current post layout, instead
of baking a fixed polygon into config.json.

Approach: treat each post as an *ellipse* at the plate (its own elliptical
footprint, `waist_rx`/`waist_ry`, offset outward by a uniform `margin`),
order the posts along the arch, and for each *adjacent* pair take the convex
hull of just those two ellipses - a "stadium" shape: a straight line tangent
to both ellipses on each side, plus a fillet arc at each ellipse wherever the
hull actually turns there. Union all those pairwise stadiums together.

Posts are frequently non-circular (`waist_ry` != `waist_rx` - e.g. a post
that needs to sit wider along the arch than it is tall across it), and their
footprint at the plate is the ellipse `build_post` in generate.py actually
lofts from, not a circle of some averaged radius. Approximating that ellipse
by a circle - as an earlier version of this module did, via a single radius
averaged from rx and ry - undersizes the outline along whichever axis is
larger: if `waist_ry` is e.g. double `waist_rx`, the averaged circle is
smaller than the ellipse along y, and the post's own footprint pokes out
past the plate edge there. Using the actual ellipse (still just offset by a
uniform `margin`, since the desired clearance is uniform, not the post's own
anisotropy) fixes that regardless of how eccentric a post is.

Each post's ellipse is also *rotated* to track the local direction of the
arch (see `compute_post_rotations`), rather than always keeping `waist_rx`
along global +x: an end post points its x-axis along the one edge to its
neighbour, and an interior post bisects the two edges either side of it -
the same "mitre" direction a stroked/offset polyline would turn through at
that vertex. `generate.py`'s `build_post` applies the same rotation to the
post's own 3D loft, so the ellipse this module reasons about is exactly the
post's real footprint, oriented to actually match the toe it's under
instead of an arbitrary global axis.

This is deliberately *not* the convex hull of every ellipse at once - that
would draw a single straight tangent line straight across any post that
happens to sit on the concave (forefoot) side of the arch between its two
neighbours, skipping it entirely. Hulling only adjacent pairs and unioning
keeps the outline hugging the arch, concave side included.

Every post except the two at the very ends of the arch belongs to *two*
pairwise hulls (one with each neighbour), and those two hulls' tangent lines
generally touch that shared ellipse at two different points - the two
neighbours aren't equally sized or equally far away, so there's no reason
the same tangent point would serve both. The union of the two hulls then
meets at a real, sharp point beyond the ellipse instead of smoothly
following its boundary between those two tangent points. Each such point is
squared away afterwards with an exact fillet, using that post's own
(margined, rotated) ellipse shape (see `compute_outline` below) - which is
exactly "where the [tangent-only] hull forms a point, add a fillet shaped
like the adjacent ellipse." For a circular, unrotated post (rx == ry) this
is exactly the old circular fillet; `_elliptical_closing` generalizes it via
an affine coordinate change (see its docstring) rather than by
special-casing the circular/unrotated case.

This also intentionally does not reach for the first/last post's own edge
and extend a tapered tip beyond it (as an earlier version did) - the plate
ends right at the hull, meaning it sits a bit short under the big and little
toe. Living without that overhang is the point of this version; add it back
only if it turns out to matter in practice.

Simpler than an offset curve on principle, not just in code: each piece
unioned in is the hull of two convex shapes, which can't itself produce a
cusp or self-intersection, so there's no failure mode to design around here
(two earlier attempts - a single width-varying spline offset, then a union
of asymmetric per-post "egg" shapes - both had to work around exactly that;
see git-free history in the README). A boolean union of such pieces can
still produce a sharp *inward* (concave) corner where two adjacent stadiums
meet at a shallow angle, but never an outward spike.
"""
import math
import numpy as np
from shapely.geometry import Point
from shapely.affinity import scale as _affine_scale, translate as _affine_translate, rotate as _affine_rotate
from shapely.ops import unary_union
from default_profiles import get_profile


def _order_along_arch(centers):
    """Order post indices along the arch by projecting onto the first
    principal component of the post centers - robust to posts being listed
    in any order in the config. Defines which pairs of posts count as
    "adjacent" for the hull construction above, and which edges
    `compute_post_rotations` measures each post's direction from."""
    c = centers - centers.mean(axis=0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    axis = vt[0]
    proj = c @ axis
    return np.argsort(proj)


def compute_post_rotations(posts):
    """Per-post ellipse rotation, in degrees CCW from +x (build123d's and
    shapely's shared convention for a Z-axis rotation) - how far to turn
    each post's local x-axis (its `waist_rx` direction) away from global +x
    so it tracks the arch instead of a fixed direction. See module
    docstring for the geometric idea.

    - An end post (one neighbour) points its x-axis along the single edge
      to that neighbour.
    - An interior post (two neighbours) points along the *bisector* of the
      edges to its previous and next neighbour - the average of their unit
      directions, i.e. the direction a mitred offset curve would turn
      through at that vertex, so the post's orientation turns smoothly
      along the arch instead of jumping between its two neighbours'
      directions. If those two edges happen to point in exactly opposite
      directions (a degenerate 180-degree turn - not expected for a real
      toe arch), the bisector is undefined; this falls back to the
      incoming edge's direction rather than raising.
    - A single post with no neighbour at all gets 0deg (global +x) - there
      is nothing to align it to.

    An ellipse is symmetric under a 180-degree turn, so the sign ambiguity
    in "which way along the edge" never matters here - only the resulting
    ellipse orientation does.

    Returns a list of angles in the *original* `posts` order (not the
    arch-sorted order), so callers can `zip(posts, compute_post_rotations
    (posts))` directly.
    """
    n = len(posts)
    if n <= 1:
        return [0.0] * n

    centers = np.array([[p['x'], p['y']] for p in posts])
    order = _order_along_arch(centers)
    ordered = centers[order]

    edges = ordered[1:] - ordered[:-1]
    lengths = np.linalg.norm(edges, axis=1, keepdims=True)
    unit_edges = edges / np.where(lengths == 0, 1.0, lengths)

    angles_sorted = [0.0] * n
    for i in range(n):
        if i == 0:
            d = unit_edges[0]
        elif i == n - 1:
            d = unit_edges[-1]
        else:
            d = unit_edges[i - 1] + unit_edges[i]
            d_len = np.linalg.norm(d)
            d = unit_edges[i - 1] if d_len < 1e-9 else d / d_len
        angles_sorted[i] = math.degrees(math.atan2(d[1], d[0]))

    angles = [0.0] * n
    for sorted_pos, orig_idx in enumerate(order):
        angles[orig_idx] = angles_sorted[sorted_pos]
    return angles


def _base_radii(post):
    """Post footprint semi-axes (rx, ry) at h=0 (where it meets the plate).
    Kept as a pair rather than averaged into a single radius - see module
    docstring for why that matters once rx and ry differ noticeably."""
    h0, rscale0 = get_profile(post)[0]
    return rscale0 * post['waist_rx'], rscale0 * post['waist_ry']


def _base_radius(post):
    """Mean of the post's base semi-axes - kept only for the vestigial
    `tools/annotation_overlay.py` and `tools/plot_outline_vs_original.py`
    (see README), which predate the ellipse-aware outline and still plot a
    single reference circle per post. Not used by `compute_outline` itself;
    see `_base_radii` above for the pair this module actually works with."""
    rx, ry = _base_radii(post)
    return (rx + ry) / 2.0


def _ellipse_polygon(cx, cy, rx, ry, theta_deg, quad_segs):
    """Ellipse polygon centered at (cx, cy), with its rx-axis rotated
    `theta_deg` CCW from global +x (see `compute_post_rotations`). Built by
    scaling then rotating a unit-circle polygon (rather than sampling the
    ellipse's own parametric points) so the vertex count and construction
    match `_elliptical_closing` below exactly."""
    unit = Point(0, 0).buffer(1.0, quad_segs=quad_segs)
    ell = _affine_scale(unit, rx, ry, origin=(0, 0))
    ell = _affine_rotate(ell, theta_deg, origin=(0, 0))
    return _affine_translate(ell, cx, cy)


def _elliptical_closing(poly, rx, ry, theta_deg, join_style='round'):
    """Morphological closing of `poly` with an elliptical (rx, ry)
    structuring element rotated `theta_deg` CCW from global +x, wherever
    `poly` currently has that ellipse's worth of boundary to close - the
    ellipse generalization of the circular `poly.buffer(r).buffer(-r)`
    trick used previously.

    Affine maps commute with Minkowski sum/difference, so un-rotating by
    `theta_deg` and then scaling coordinates by (1/rx, 1/ry) turns the
    (rotated) elliptical structuring element into a unit circle, where the
    ordinary circular closing (dilate by 1, erode by 1) applies exactly;
    scaling back by (rx, ry) and re-rotating by `theta_deg` undoes the
    transform. Both steps are linear maps about the same fixed origin, so
    composing them (rotate then scale, and its exact inverse) is itself
    exact - not an approximation stacked on top of the ellipse's own
    polygon faceting. This reduces to the old `poly.buffer(r).buffer(-r)`
    exactly when rx == ry == r (theta_deg is then irrelevant - a circle is
    rotation-invariant).
    """
    normalized = _affine_rotate(poly, -theta_deg, origin=(0, 0))
    normalized = _affine_scale(normalized, 1.0 / rx, 1.0 / ry, origin=(0, 0))
    closed = normalized.buffer(1.0, join_style=join_style).buffer(-1.0, join_style=join_style)
    closed = _affine_scale(closed, rx, ry, origin=(0, 0))
    return _affine_rotate(closed, theta_deg, origin=(0, 0))


def compute_outline(posts, margin=4.0, samples=128, rotations=None):
    """Return an ordered list of (x, y) points (CCW) forming the plate
    outline: the union of pairwise hulls between each adjacent pair of post
    ellipses (post's own elliptical footprint, rotated per
    `compute_post_rotations`, offset outward by `margin`) - see module
    docstring. `margin` is in mm; `samples` is the total number of segments
    used to approximate each post's ellipse (higher = smoother fillet arcs,
    at the cost of more outline points). `rotations`, if given, must be a
    list of per-post degrees in `posts` order, as returned by
    `compute_post_rotations` - pass the same list already computed for
    `build_post` calls to avoid recomputing it; left as None, it's computed
    here from `posts` directly.
    """
    if rotations is None:
        rotations = compute_post_rotations(posts)

    quad_segs = max(1, samples // 4)
    base_radii = [_base_radii(p) for p in posts]
    ellipses = [
        _ellipse_polygon(p['x'], p['y'], rx, ry, theta, quad_segs).buffer(margin, join_style='round')
        for p, (rx, ry), theta in zip(posts, base_radii, rotations)
    ]

    if len(ellipses) == 1:
        poly = ellipses[0]
    else:
        centers = np.array([[p['x'], p['y']] for p in posts])
        order = _order_along_arch(centers)
        pieces = [
            unary_union([ellipses[order[i]], ellipses[order[i + 1]]]).convex_hull
            for i in range(len(order) - 1)
        ]
        poly = unary_union(pieces)

        # Fillet each interior post's junction point (see module docstring)
        # with an exact morphological "closing" at that post's own
        # (margined, rotated) ellipse shape: dilating by the ellipse then
        # eroding by it replaces any concave notch narrower than the
        # ellipse with a true elliptical arc, and leaves every other part
        # of the boundary - already convex, or a wider notch - untouched.
        # The two end posts have only one neighbour each, so they never
        # form this kind of point.
        for idx in order[1:-1]:
            rx, ry = base_radii[idx]
            poly = _elliptical_closing(poly, rx + margin, ry + margin, rotations[idx])

    # Cap the simplify tolerance well below `margin` rather than using a
    # flat 0.02mm: Douglas-Peucker simplification can move the boundary by
    # up to its tolerance in either direction, so a flat 0.02mm tolerance
    # against a smaller margin (an extreme case, but config-4.json's 0.01mm
    # test margin hits it) can eat the entire clearance and then some,
    # pushing the "simplified" boundary back inside a post's own footprint
    # - which then makes the plate/post boolean union degenerate (OCCT
    # fails to triangulate the resulting sliver face). For any normal
    # margin (a few mm) this is well under 0.02mm and changes nothing.
    simplify_tol = min(0.02, margin / 20.0)
    poly = poly.simplify(simplify_tol, preserve_topology=True)

    ccw = poly.exterior.is_ccw
    out = list(poly.exterior.coords)[:-1]
    if not ccw:
        out = out[::-1]
    return [[round(x, 3), round(y, 3)] for x, y in out]
