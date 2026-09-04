"""Default per-post silhouette profiles, factored out of configs/*.json.

Each profile is a list of [height_fraction, radius_scale] points tracing a
post's silhouette from the plate (h=0) to its tip (h=1), radius as a
multiple of the waist radius - see README ("Fitting your feet: what to
edit") for what the shape means. These started as a reverse-engineering of
the original mesh (tools/extract_profiles.py + tools/derive_config.py,
verified against it - see README, "Verifying the recreation"), with two
deliberate deviations since, both per-post affine rescales of the measured
curve that keep the waist (r=1.0, unaffected either way) and the taper
either side of it smooth:
- the base flare (the point nearest h=0, where the post meets the plate)
  was rescaled from the original's ~2.1-2.4x the waist radius down to a
  flat 1.5x, each point between h=0 and the waist scaled toward 1.0 by the
  same factor.
- the cap bulge above the waist (needed for TPU's flex - see README, "How
  the shape works") was rescaled so its own peak, whatever height fraction
  it actually occurs at, also lands on exactly 1.5x - matching the base -
  instead of the original's ~1.55-1.77x; every point between the waist and
  the peak scaled the same way. The final [1.0, 0.0] point (the dome tip)
  is untouched, still an exact point.
Not something to hand-tune day-to-day, so this lives here rather than being
repeated in every configs/*.json file. A config can still set an explicit
`profile` per-post to override this (e.g. for deliberate reshaping);
generate.py and plate_outline.py both fall back to this module via
get_profile() whenever a post has none of its own.
"""

DEFAULT_PROFILES = {
    'post_A_arch': [
        [0.0009, 1.5],
        [0.083, 1.2985],
        [0.1697, 1.1718],
        [0.2701, 1.0789],
        [0.3841, 1.0195],
        [0.4434, 1.0048],
        [0.5027, 1.0],
        [0.5301, 1.004],
        [0.6168, 1.0345],
        [0.6761, 1.0799],
        [0.7856, 1.2227],
        [0.9179, 1.4941],
        [0.9361, 1.5],
        [0.9681, 1.4759],
        [1.0, 0.0],
    ],
    'post_B': [
        [0.0011, 1.5],
        [0.0486, 1.3799],
        [0.1438, 1.2161],
        [0.2495, 1.1008],
        [0.3763, 1.0242],
        [0.4397, 1.006],
        [0.5032, 1.0],
        [0.5666, 1.0117],
        [0.6353, 1.0515],
        [0.7569, 1.1943],
        [0.9101, 1.5],
        [0.9471, 1.4929],
        [0.9683, 1.4613],
        [1.0, 0.0],
    ],
    'post_C': [
        [0.0012, 1.5],
        [0.0662, 1.3459],
        [0.1726, 1.181],
        [0.2908, 1.071],
        [0.3676, 1.0283],
        [0.4326, 1.0073],
        [0.5035, 1.0],
        [0.5745, 1.0161],
        [0.6395, 1.0581],
        [0.7695, 1.2299],
        [0.8759, 1.4674],
        [0.9054, 1.5],
        [0.9409, 1.489],
        [0.9645, 1.4526],
        [1.0, 0.0],
    ],
    'post_D_pinky': [
        [0.0012, 1.5],
        [0.0957, 1.3027],
        [0.1608, 1.2059],
        [0.2849, 1.0795],
        [0.3794, 1.0264],
        [0.4326, 1.0082],
        [0.5035, 1.0],
        [0.5745, 1.0159],
        [0.6454, 1.0634],
        [0.7163, 1.1438],
        [0.7813, 1.2503],
        [0.9054, 1.5],
        [0.9291, 1.4979],
        [0.9645, 1.4437],
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
