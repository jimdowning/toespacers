"""Default per-post silhouette profiles, factored out of configs/*.json.

Each profile is a list of [height_fraction, radius_scale] points tracing a
post's silhouette from the plate (h=0) to its tip (h=1), radius as a
multiple of the waist radius - see README ("Fitting your feet: what to
edit") for what the shape means. These were reverse-engineered from the
original mesh (tools/extract_profiles.py + tools/derive_config.py) and
verified against it (see README, "Verifying the recreation") - not
something to hand-tune, so they live here rather than being repeated in
every configs/*.json file. A config can still set an explicit `profile`
per-post to override this (e.g. for deliberate reshaping); generate.py and
plate_outline.py both fall back to this module via get_profile() whenever
a post has none of its own.
"""

DEFAULT_PROFILES = {
    'post_A_arch': [
        [0.0009, 2.4177],
        [0.083, 1.8463],
        [0.1697, 1.4872],
        [0.2701, 1.2237],
        [0.3841, 1.0554],
        [0.4434, 1.0135],
        [0.5027, 1.0],
        [0.5301, 1.0062],
        [0.6168, 1.0534],
        [0.6761, 1.1235],
        [0.7856, 1.3443],
        [0.9179, 1.7638],
        [0.9361, 1.7729],
        [0.9681, 1.7356],
        [1.0, 0.0],
    ],
    'post_B': [
        [0.0011, 2.192],
        [0.0486, 1.9057],
        [0.1438, 1.5153],
        [0.2495, 1.2403],
        [0.3763, 1.0578],
        [0.4397, 1.0143],
        [0.5032, 1.0],
        [0.5666, 1.0148],
        [0.6353, 1.0649],
        [0.7569, 1.2451],
        [0.9101, 1.6306],
        [0.9471, 1.6216],
        [0.9683, 1.5818],
        [1.0, 0.0],
    ],
    'post_C': [
        [0.0012, 2.101],
        [0.0662, 1.7616],
        [0.1726, 1.3985],
        [0.2908, 1.1563],
        [0.3676, 1.0623],
        [0.4326, 1.0161],
        [0.5035, 1.0],
        [0.5745, 1.0177],
        [0.6395, 1.064],
        [0.7695, 1.2534],
        [0.8759, 1.5153],
        [0.9054, 1.5512],
        [0.9409, 1.5391],
        [0.9645, 1.4989],
        [1.0, 0.0],
    ],
    'post_D_pinky': [
        [0.0012, 2.1467],
        [0.0957, 1.6942],
        [0.1608, 1.4722],
        [0.2849, 1.1824],
        [0.3794, 1.0606],
        [0.4326, 1.0187],
        [0.5035, 1.0],
        [0.5745, 1.0194],
        [0.6454, 1.0775],
        [0.7163, 1.1758],
        [0.7813, 1.3061],
        [0.9054, 1.6114],
        [0.9291, 1.6088],
        [0.9645, 1.5426],
        [1.0, 0.0],
    ],
}


def get_profile(post):
    """A post's profile: its own `profile` key if it set one, else the
    default for its `name`. Raises a clear error for a post that has
    neither, rather than a bare KeyError deep inside a loft/outline call."""
    if "profile" in post:
        return post["profile"]
    try:
        return DEFAULT_PROFILES[post["name"]]
    except KeyError:
        raise KeyError(
            f"post {post.get('name')!r} has no 'profile' in its config entry "
            f"and no default in default_profiles.DEFAULT_PROFILES ({sorted(DEFAULT_PROFILES)}) - "
            f"add an explicit 'profile' array for it, or use one of those names"
        ) from None
