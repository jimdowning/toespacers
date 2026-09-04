"""Parametric toe-spacer generator.

Reads a JSON config (plate settings + per-post x,y,height,waist radii) and
builds a solid model with build123d, exporting STL (and optionally the
mirrored second foot). The plate outline is not stored in the config - it's
derived from the current post layout each run (see plate_outline.py), so
moving/resizing/adding posts always produces a plate that fits them. Each
post's silhouette profile likewise isn't stored in the config - it's looked
up by post name from default_profiles.DEFAULT_PROFILES (see get_profile()
there), since it's reverse-engineered/verified data, not something to
hand-tune per config. A post can still set its own `profile` key to override
the default.

Usage:
    python generate.py config.json out_prefix [--both] [--test-fit] [--pillars N] [--bambu]

--test-fit swaps every post's profile above its own waist (the narrowest
point) for a straight cylindrical extension plus a plain hemispherical cap
of that same radius, instead of the full hourglass bulge - see
`test_fit_profile` below.

--pillars N is a bitmask over `config['posts']` in listed order (post 1 =
big toe/first toe pillar = bit value 1, post 2 = bit value 2, and so on):
15 (1+2+4+8) builds all four posts, 9 (1+8) builds only the first and last.
Defaults to every post. Posts are dropped before the plate outline is
derived, so the plate itself shrinks to fit whichever posts are left in.

--bambu additionally writes `out_prefix.3mf`, a ready-to-slice Bambu Studio
project (both feet on one plate when combined with --both) with sparse
infill preset to gyroid at 10% - see `bambu_project.py`.
"""
import json
import math
import os
import argparse
import build123d as bd
from plate_outline import compute_outline, compute_post_rotations
from bambu_project import write_bambu_project
from default_profiles import get_profile


def build_plate(outline_pts, thickness):
    pts = [(x, y) for x, y in outline_pts]
    face = bd.Polygon(*pts, align=None)
    plate = bd.extrude(face, amount=thickness)
    return plate


EMBED = 0.5  # mm the post's base ring is sunk into the plate, guaranteeing a
             # true volumetric overlap so the boolean union fuses into one
             # watertight shell instead of two solids that merely touch


def build_post(x, y, height, waist_rx, waist_ry, profile, plate_top_z, rotation_deg=0.0):
    """`rotation_deg` turns the post's rx-axis CCW from global +x (about its
    own (x, y) center, same convention as `plate_outline.compute_post_
    rotations`) so the post's elliptical cross-sections - and therefore the
    plate outline built to fit them, see `build_foot` - align with the
    local direction of the arch instead of a fixed global axis. A no-op for
    a circular post (rx == ry), since a circle is rotation-invariant."""
    faces = []
    for i, (h, rscale) in enumerate(profile):
        z = plate_top_z + h * height
        if i == 0:
            z -= EMBED  # sink the base ring into the plate (radius unchanged)
        rx = max(rscale * waist_rx, 0.02)
        ry = max(rscale * waist_ry, 0.02)
        if abs(rx - ry) < 1e-6:
            sk = bd.Circle(rx)
        else:
            sk = bd.Ellipse(rx, ry)
        sk = sk.located(bd.Location((x, y, z), (0, 0, rotation_deg)))
        faces.append(sk.face())
    post = bd.loft(faces, ruled=True)
    return post


def test_fit_profile(profile, height, waist_rx, waist_ry, cylinder_length=5.0, samples=16):
    """Replace everything above the waist (the narrowest point, needed in
    the real TPU print so a toe can flex the post's bulge apart on the way
    past) with a straight `cylinder_length` mm cylindrical extension at the
    waist's own radius, then a plain hemispherical cap of that same radius.

    The result is monotonically narrowing from the base up to the waist,
    then a short straight run, then a smooth dome with no overhang at all
    above it - nothing to deform past, so a size/spacing check prints fine
    in rigid PLA. The cylindrical run gives calipers/gauge pins a section of
    truly constant, unambiguous diameter to check the waist size against,
    rather than only the single point where the taper bottoms out. Returns
    (new_profile, new_height); `height`/`waist_rx`/`waist_ry` are the post's
    existing scalars, `profile` its existing list of
    [height_fraction, radius_scale] points (see plate config docs).
    """
    # the waist is the *first* local minimum: rscale decreases from the
    # base down to it, then rises again into the cap bulge before tapering
    # back down to 0 at the apex - so the profile's plain global minimum is
    # the apex tip, not the waist. Walk forward while still decreasing.
    k = 0
    while k + 1 < len(profile) and profile[k + 1][1] < profile[k][1]:
        k += 1
    h_waist_frac, r_waist_scale = profile[k]
    h_waist = h_waist_frac * height
    r_waist = r_waist_scale * (waist_rx + waist_ry) / 2.0  # mean: the test-fit
    # cylinder is deliberately circular (not elliptical, like the real post),
    # since it's meant to be checked with round calipers/gauge pins

    h_cyl_top = h_waist + cylinder_length
    new_height = h_cyl_top + r_waist
    new_profile = [[hf * height / new_height, rs] for hf, rs in profile[:k + 1]]
    new_profile.append([h_cyl_top / new_height, r_waist_scale])  # straight run, same radius as the waist
    for i in range(1, samples + 1):
        theta = (math.pi / 2) * i / samples
        z = r_waist * math.sin(theta)
        rs = r_waist_scale * math.cos(theta)
        new_profile.append([(h_cyl_top + z) / new_height, rs])
    new_profile[-1][1] = 0.0  # exact apex, matching the full-profile convention
    return new_profile, new_height


def domed_profile(profile, height, waist_rx, waist_ry, samples=16):
    """Replace everything above the cap bulge's own peak (its widest point,
    above the waist) with a proper hemi-ellipsoid dome down to the apex,
    instead of `profile`'s own default ending: a couple of points that
    barely taper before one final straight ruled segment drops almost
    straight to the apex point - close enough to a flat plateau then a cut
    that it visibly reads as a flat top, and costs the print the smooth,
    continuously-curved surface a toe actually cams sideways over (see
    README, "How the shape works", on why the bulge needs to be something a
    toe can flex past at all). Applied to every post's profile at build
    time - not just `test_fit_profile`'s reduced test shape - so it always
    matches that post's own actual `waist_rx`/`waist_ry`, whatever config
    supplies them. Returns (new_profile, new_height); `height`/`waist_rx`/
    `waist_ry` are the post's existing scalars, `profile` its existing list
    of [height_fraction, radius_scale] points (see plate config docs).

    A hemi-ellipsoid, not a hemisphere, for two reasons: its horizontal
    cross-section is already an ellipse (`waist_rx`/`waist_ry` independently,
    same as the rest of the post - see `build_post`) whenever the two
    differ, and its vertical extent is sized off their *mean*, not assumed
    to equal either one - so the dome is only a true hemisphere in the
    circular, `waist_rx == waist_ry` case.

    Sized off the actual mm waist radii (not the profile's fixed height
    budget above the peak, which is normally far too short for a dome that
    wide - see module docstring's dome-sizing note), so this genuinely
    extends the post's total height, the same way `test_fit_profile`
    already extends it to fit its own hemisphere cap.
    """
    # same walk-forward convention as test_fit_profile: rscale decreases
    # from the base to the waist, then rises again into the bulge - so the
    # peak (this function's concern) is the *last* local maximum before the
    # profile's final point (the apex, always r=0, never the peak).
    k = 0
    while k + 1 < len(profile) and profile[k + 1][1] < profile[k][1]:
        k += 1  # k is now the waist index
    i_peak = max(range(k, len(profile) - 1), key=lambda i: profile[i][1])
    h_peak_frac, r_peak_scale = profile[i_peak]
    h_peak = h_peak_frac * height
    r_dome = r_peak_scale * (waist_rx + waist_ry) / 2.0  # mean, matching
    # test_fit_profile's own dome-radius convention (see its docstring)

    new_height = h_peak + r_dome
    new_profile = [[hf * height / new_height, rs] for hf, rs in profile[:i_peak + 1]]
    for i in range(1, samples + 1):
        theta = (math.pi / 2) * i / samples
        z = r_dome * math.sin(theta)
        rs = r_peak_scale * math.cos(theta)
        new_profile.append([(h_peak + z) / new_height, rs])
    new_profile[-1][1] = 0.0  # exact apex, matching the full-profile convention
    return new_profile, new_height


def select_pillars(posts, mask):
    """Keep only the posts selected by `mask`, a bitmask over `posts` in
    list order: bit 0 (value 1) is the first post (the big toe/first toe
    pillar), bit 1 (value 2) the second, and so on - see module docstring.
    `mask=None` keeps every post (the default, equivalent to all bits set).
    """
    if mask is None:
        return posts
    n = len(posts)
    if not (0 <= mask < (1 << n)):
        raise ValueError(f"--pillars {mask} out of range for {n} posts (valid: 0..{(1 << n) - 1})")
    if mask == 0:
        raise ValueError("--pillars 0 selects no posts - nothing to build")
    return [p for i, p in enumerate(posts) if mask & (1 << i)]


def build_foot(config, mirror=False, test_fit=False, pillars=None):
    thickness = config['plate']['thickness']
    plate_cfg = config['plate']

    posts = config['posts']
    if mirror:
        posts = [{**p, 'x': -p['x']} for p in posts]
    posts = select_pillars(posts, pillars)
    # Every post gets its default cone-to-a-point ending swapped for a
    # proper hemi-ellipsoid dome (domed_profile) or, under --test-fit,
    # replaced entirely above the waist (test_fit_profile) - either way,
    # every post ends up with an explicit 'profile'/'height' of its own
    # rather than relying on get_profile()'s default lookup further down.
    new_posts = []
    for p in posts:
        if test_fit:
            profile, height = test_fit_profile(get_profile(p), p['height'], p['waist_rx'], p['waist_ry'])
        else:
            profile, height = domed_profile(get_profile(p), p['height'], p['waist_rx'], p['waist_ry'])
        new_posts.append({**p, 'profile': profile, 'height': height})
    posts = new_posts

    # Each post's ellipse is rotated to track the local direction of the
    # arch (see compute_post_rotations) rather than a fixed global axis;
    # computed once here from the (already-mirrored/selected) post layout
    # and reused for both the outline and each post's own loft below, so
    # the two always agree on which way each post is actually turned.
    rotations = compute_post_rotations(posts)

    # outline is derived from the (already-mirrored, if applicable) post
    # layout, so it always fits - no winding-order mirroring tricks needed.
    outline = compute_outline(
        posts,
        margin=plate_cfg.get('margin', 4.0),
        rotations=rotations,
    )

    part = build_plate(outline, thickness)
    for post, rotation_deg in zip(posts, rotations):
        p = build_post(post['x'], post['y'], post['height'], post['waist_rx'], post['waist_ry'],
                        get_profile(post), thickness, rotation_deg=rotation_deg)
        part = part + p
    return part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('out_prefix')
    ap.add_argument('--both', action='store_true', help='also generate mirrored second foot')
    ap.add_argument('--test-fit', action='store_true',
                     help='truncate every post above its waist to a straight 5mm run plus a hemisphere, '
                          'for a rigid-filament size check')
    ap.add_argument('--pillars', type=lambda s: int(s, 0), default=None,
                     help='bitmask of which posts to build (bit 0 = post 1 = big toe/first toe pillar, etc.); '
                          'default is every post')
    ap.add_argument('--bambu', action='store_true',
                     help="also write out_prefix.3mf, a ready-to-slice Bambu Studio project (both feet on "
                          "one plate when combined with --both) with sparse infill preset per --infill-pattern "
                          "/ --infill-density")
    ap.add_argument('--infill-pattern', default='gyroid', help="--bambu sparse infill pattern (default gyroid)")
    ap.add_argument('--infill-density', default='10%', help="--bambu sparse infill density (default 10%%)")
    args = ap.parse_args()

    config = json.load(open(args.config))

    # config.json's posts are, unmirrored, a RIGHT foot: viewed top-down
    # with +Y toward the toes and +Z up (this project's convention - see
    # "How the plate outline works"), post_A_arch (the big-toe side) sits
    # at -X and post_D_pinky at +X, which is the medial/big-toe edge facing
    # the body midline (-X) - a right foot's own local shape. mirror=True
    # (X negated) is therefore the left foot.
    right = build_foot(config, mirror=False, test_fit=args.test_fit, pillars=args.pillars)
    bd.export_stl(right, f'{args.out_prefix}_right.stl')
    print(f"wrote {args.out_prefix}_right.stl  volume={right.volume:.2f}  bbox={right.bounding_box()}")

    if args.both:
        left = build_foot(config, mirror=True, test_fit=args.test_fit, pillars=args.pillars)
        bd.export_stl(left, f'{args.out_prefix}_left.stl')
        print(f"wrote {args.out_prefix}_left.stl  volume={left.volume:.2f}  bbox={left.bounding_box()}")

    if args.bambu:
        # borrows print settings (printer, filament, layer height, walls,
        # ...) from bambu_a1_mini_tpu_settings.json - a Bambu Lab A1 mini,
        # no AMS, single TPU filament - see bambu_project.py's docstring.
        template = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bambu_a1_mini_tpu_settings.json')
        named_parts = [('toe_spacer_right', right)]
        if args.both:
            named_parts.append(('toe_spacer_left', left))
        out_3mf = f'{args.out_prefix}.3mf'
        write_bambu_project(out_3mf, named_parts, template,
                             sparse_infill_pattern=args.infill_pattern,
                             sparse_infill_density=args.infill_density)
        print(f"wrote {out_3mf}  (Bambu Studio project, sparse infill {args.infill_pattern} {args.infill_density})")


if __name__ == '__main__':
    main()
