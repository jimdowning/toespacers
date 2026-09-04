"""Derive an editable config.json (plus default_profiles.py) from a
profiles.json produced by extract_profiles.py.

Usage:
    python derive_config.py profiles.json ../configs/config.json ../default_profiles.py
"""
import json
import sys
import numpy as np
from rdp import rdp

names = ['post_A_arch', 'post_B', 'post_C', 'post_D_pinky']


def format_default_profiles(profiles):
    """Render `profiles` (name -> [[h, r], ...]) as the body of
    default_profiles.py - see that module's own docstring/get_profile() for
    why the profile lives there instead of in configs/*.json."""
    lines = [
        '"""Default per-post silhouette profiles, factored out of configs/*.json.',
        '',
        "Each profile is a list of [height_fraction, radius_scale] points tracing a",
        "post's silhouette from the plate (h=0) to its tip (h=1), radius as a",
        'multiple of the waist radius - see README ("Fitting your feet: what to',
        'edit") for what the shape means. These were reverse-engineered from the',
        'original mesh (tools/extract_profiles.py + tools/derive_config.py) and',
        'verified against it (see README, "Verifying the recreation") - not',
        'something to hand-tune, so they live here rather than being repeated in',
        'every configs/*.json file. A config can still set an explicit `profile`',
        'per-post to override this (e.g. for deliberate reshaping); generate.py and',
        'plate_outline.py both fall back to this module via get_profile() whenever',
        'a post has none of its own.',
        '"""',
        '',
        'DEFAULT_PROFILES = {',
    ]
    for name, prof in profiles.items():
        lines.append(f'    {name!r}: [')
        for h, r in prof:
            lines.append(f'        [{h}, {r}],')
        lines.append('    ],')
    lines += [
        '}',
        '',
        '',
        'def get_profile(post):',
        '    """A post\'s profile: its own `profile` key if it set one, else the',
        '    default for its `name`. Raises a clear error for a post that has',
        '    neither, rather than a bare KeyError deep inside a loft/outline call."""',
        '    if "profile" in post:',
        '        return post["profile"]',
        '    try:',
        '        return DEFAULT_PROFILES[post["name"]]',
        '    except KeyError:',
        '        raise KeyError(',
        '            f"post {post.get(\'name\')!r} has no \'profile\' in its config entry "',
        '            f"and no default in default_profiles.DEFAULT_PROFILES ({sorted(DEFAULT_PROFILES)}) - "',
        '            f"add an explicit \'profile\' array for it, or use one of those names"',
        '        ) from None',
        '',
    ]
    return '\n'.join(lines)


def derive(data):
    plate_top_z = data['zmin'] + data['plate_thickness']

    # sort tallest-first (arch post is tallest, pinky-side post is shortest
    # in this design, but that's just a property of THIS shoe - not assumed
    # elsewhere)
    tracks = sorted(data['tracks'], key=lambda t: -max(p[0] for p in t['points']))

    posts = []
    profiles = {}
    for name, t in zip(names, tracks):
        pts = t['points']
        zs = np.array([p[0] for p in pts])
        # NOTE: use rmin/rmax (direct centroid->boundary distances), not a
        # covariance-eigenvalue ellipse fit - the latter only recovers the
        # true radius up to a constant that depends on the (unknown) angular
        # distribution of boundary points, and was verified here to overstate
        # radius by sqrt(2) (2x area/volume) for these particular sections.
        rmin = np.array([p[1]['rmin'] for p in pts])
        rmax = np.array([p[1]['rmax'] for p in pts])
        cx = np.array([p[1]['cx'] for p in pts])
        cy = np.array([p[1]['cy'] for p in pts])
        r = (rmin + rmax) / 2.0

        apex_z = zs[-1]  # last successfully separated slice; a hair short of
                          # the true apex point, close enough (<0.1mm)
        height = apex_z - plate_top_z
        h = (zs - plate_top_z) / height
        i_waist = np.argmin(r)
        waist_r = r[i_waist]
        r_scale = r / waist_r

        curve = list(zip(h.tolist(), r_scale.tolist()))
        simplified = rdp(curve, epsilon=0.01)
        if not any(abs(p[0] - h[i_waist]) < 1e-6 for p in simplified):
            simplified.append([float(h[i_waist]), 1.0])
        # drop near-h=1.0 point(s) (never quite reaches the true apex) and
        # replace with a clean synthetic apex
        simplified = [p for p in simplified if p[0] < 0.999]
        simplified.sort(key=lambda p: p[0])
        simplified.append([1.0, 0.0])

        profiles[name] = [[round(hh, 4), round(rr, 4)] for hh, rr in simplified]
        posts.append(dict(
            name=name,
            x=round(float(cx.mean()), 3),
            y=round(float(cy.mean()), 3),
            waist_rx=round(float(waist_r), 3),
            waist_ry=round(float(waist_r), 3),  # source design is circular; free to diverge
            height=round(float(height), 3),
        ))
        print(f"{name}: n_profile_pts={len(simplified)} height={height:.3f} "
              f"waist_r={waist_r:.3f} x={cx.mean():.2f} y={cy.mean():.2f}")

    # Note: the plate outline is NOT derived here. generate.py computes it at
    # build time from the post layout (see ../plate_outline.py: the convex
    # hull of a circle at each post) so it always fits the posts, however
    # they're later edited - `margin` below is its only tunable.
    # `plate_outline_raw` in profiles.json (the traced outline of the source
    # mesh) is left unused; it was a source of bugs when baked into
    # config.json statically (an edited post layout no longer matched it),
    # and it isn't needed for anything now.
    config = dict(
        units='mm',
        plate=dict(thickness=round(data['plate_thickness'], 4), margin=4.0),
        posts=posts,
    )
    return config, profiles


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    data = json.load(open(sys.argv[1]))
    config, profiles = derive(data)
    with open(sys.argv[2], 'w') as f:
        json.dump(config, f, indent=1)
        f.write('\n')
    print(f"wrote {sys.argv[2]}")
    with open(sys.argv[3], 'w') as f:
        f.write(format_default_profiles(profiles))
    print(f"wrote {sys.argv[3]}")
