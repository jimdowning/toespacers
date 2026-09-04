# Parametric toe spacer

A config-driven regeneration of `Fußspreitzer+v2+v4.3mf` (the original was a
raw, non-parametric mesh — no CAD history, no source model, just triangles —
so this reverse-engineers it into an editable form). Written in Python with
[build123d](https://build123d.readthedocs.io/) (a scriptable CAD kernel), not
OpenSCAD, because OpenSCAD isn't installable in this environment (it's a
macOS-only Homebrew cask here, and there's no `apt` sudo access) — build123d
installs cleanly with `pip`.

## Quick start

```bash
./setup.sh                              # one-time: creates venv, installs deps
./run.sh generate.py configs/config.json outputs/output --both
```

This writes `outputs/output_left.stl` and `outputs/output_right.stl`. Import into Bambu
Studio, apply your usual TPU print settings (the original recommends 0.4mm
nozzle, 0.2mm layers, 20-30% infill, 220-240°C), slice, print.

### Fast size-test prints in PLA

The real posts are an hourglass: they flare out again *above* the waist into
a bulging cap before tapering to a dome (see "How the shape works" below).
That bulge is exactly what TPU's flex is for - it lets a toe spread the
posts apart on the way past the widest point - but it makes the post
genuinely wider than the waist gap it's supposed to fit through, which a
rigid filament like PLA can't do at all. `--test-fit` swaps every post's
profile above its own waist for a straight 5mm cylindrical extension at the
waist's own radius, then a plain hemispherical cap of that same radius,
instead of the bulge - so the whole post narrows monotonically from base to
waist, then holds that width for 5mm, then domes off, with nothing to
squeeze past - just a size/placement check, prints fine in PLA:

```bash
./run.sh generate.py configs/config.json outputs/output_test --both --test-fit
```

Same `configs/config.json`, same `x`/`y`/`waist_rx`/`waist_ry` you're validating -
only the profile above the waist changes (and each post ends up shorter,
since it stops at waist-height + 5mm + one waist-radius instead of the full
`height`). The 5mm straight run isn't in the real post at all - it's there
so a caliper or a gauge pin has an unambiguous constant-diameter section to
check the waist size against, rather than only the single point where the
taper bottoms out. Don't judge the actual fit/flex from this print, only
placement and spacing; go back to a plain (non-`--test-fit`) TPU print for
that.

### Printing only some of the posts

`--pillars N` builds only a chosen subset of posts - useful for a same-day
test print of just the ones you're unsure about, without waiting on the
whole plate. `N` is a bitmask over `config['posts']` in listed order: post 1
(the big toe/first toe pillar) is bit value 1, post 2 is bit value 2, post 3
is bit value 4, post 4 is bit value 8, and so on for however many posts the
config has. Add up the values of the posts you want:

```bash
./run.sh generate.py configs/config.json outputs/output --both --pillars 15   # all four posts (default)
./run.sh generate.py configs/config.json outputs/output_ends --both --pillars 9   # posts 1 and 4 only
```

The plate outline is derived from whichever posts are left in, so it
shrinks to fit them (see "How the plate outline works" below) - dropping
posts doesn't leave a plate sized for posts that are no longer there.
Combines freely with `--test-fit`. `--pillars 0` (no posts at all) and any
mask with a bit beyond the number of posts in the config are both rejected
with an error rather than silently doing something odd.

### Generating a ready-to-slice Bambu Studio project

`--bambu` writes `out_prefix.3mf` alongside the STLs - a real Bambu Studio
*project* file, not just a mesh: opening it in Studio offers to load its
print settings directly, rather than starting from whatever profile was
last active, or from a plain-geometry import warning. Both feet share one
plate when combined with `--both`. Sparse infill defaults to gyroid at 10%
(override with `--infill-pattern` / `--infill-density`); every other setting
- printer (Bambu Lab X1 Carbon, 0.4mm nozzle), the TPU filament slot,
0.2mm layers, wall count - is cloned from this project's own reference file
(`../Fußspreitzer+v2+v4.3mf`, a real Bambu Studio project saved by Studio
itself), so it's the same baseline this README already recommends, not a
guess.

```bash
./run.sh generate.py configs/config.json outputs/output --both --bambu
./run.sh generate.py configs/config.json outputs/output --both --bambu --infill-pattern gyroid --infill-density 15%
```

This still needs Bambu Studio itself to actually slice - there's no
supported way to generate finished g-code from the command line here (Bambu
Studio's public build doesn't expose a headless slicing CLI the way
PrusaSlicer/OrcaSlicer do), so opening the project and clicking Slice is
still the last step, just without re-entering any settings by hand first.

The first version of this got two things wrong, both caught by opening the
result in real Bambu Studio: it warned "This file is not from bambulab" and
loaded bare geometry only (no print settings), and it reported 12794 open
edges on one object needing repair. Both are fixed now (see
`bambu_project.py`'s docstring for the full explanation) - in short:

- Studio only offers to load `Metadata/project_settings.config` when it
  recognizes the incoming file as one of its own projects, which turned out
  to need an `Application: BambuStudio-x.x.x.x` metadata tag in
  `3D/3dmodel.model`, *and* each object's mesh living in its own
  `3D/Objects/object_N.model` file referenced via the 3MF Production
  Extension - not inlined directly, which is what the first version did.
- The "open edges" were real, by the letter of the format, even though the
  surface was geometrically continuous: the first version wrote each
  tessellated face's vertices straight through without sharing indices
  between adjacent faces (harmless for STL, which never shares vertices at
  all - but a 3MF *indexed* mesh is expected to actually reuse one vertex
  index at a shared edge, and an edge whose two triangles reference
  different-but-coincident vertices reads as open to an index-based
  checker). Fixed by deduplicating vertices by position before writing each
  mesh - confirmed by counting edges used by only one triangle, both ways:
  in the thousands beforehand, zero after, for every object.

Also added `Metadata/model_settings.config`, assigning every object to
filament slot 7 (`extruder`, matching where the reference project's own
filament list has TPU) - without it Studio defaults every incoming object to
slot 1 regardless of what's actually loaded there.

## Fitting your feet: what to edit

Open `configs/config.json`. Each post has:

```json
{
  "name": "post_A_arch",
  "x": -30.21, "y": -0.77,       "waist_rx": 5.05, "waist_ry": 5.05,
  "height": 21.92,
  "profile": [ ... ]
}
```

- **`x`, `y`** — the post's center, in the plate's local coordinate plane
  (mm). Move a post to shift which two toes it sits between.
- **`waist_rx`, `waist_ry`** — the radius at the post's *narrowest point*
  (the "waist", roughly mid-height — see below), independently in two
  perpendicular directions. Equal values keep it circular like the
  original; make them unequal for an elliptical post (e.g. a wider
  `waist_ry` if a post needs to sit more snugly along one direction than
  the other). **This is the main knob for fitting** — it's where the post
  actually grips your toes. `rx`/`ry` are directions *relative to the
  post*, not fixed to global X/Y — each post is auto-rotated to track the
  local direction of the toe arch (see "How the plate outline works"
  below), so `waist_rx` always ends up pointing roughly along the line
  between neighbouring toes and `waist_ry` across it, whichever way the
  arch is actually turning at that post.
- **`height`** — apex height above the plate. Not in your original ask but
  cheap to expose; shorten/lengthen a post if the fit calls for it.
- **`profile`** — leave this alone for routine fitting. It's a list of
  `[height_fraction, radius_scale]` points describing the post's silhouette
  from the plate (`h=0`) to its rounded tip (`h=1`), as a *multiple of the
  waist radius*. Editing `waist_rx`/`waist_ry` rescales the whole post
  (base flare and cap bulge included) around this fixed shape. Only touch
  `profile` for more advanced reshaping (e.g. a flatter cap, a lower waist).

`plate` also has one outline knob, optional (default shown):

```json
"plate": { "thickness": 1.6, "margin": 4.0 }
```

- **`margin`** — extra rim of plate around every post's own elliptical
  footprint, mm. Uniform all the way round each post (no toe/forefoot
  distinction) - see "How the plate outline works" below.

There's no `outline` field to edit — the plate's boundary is *computed* from
the current posts every time you run `generate.py` (see "How the plate
outline works" below), specifically so that moving, resizing, reordering, or
adding/removing posts always produces a plate that fits them. (An earlier
version baked a fixed outline, traced from the original mesh, into the
config — that broke as soon as a post moved outside it.)

After editing, regenerate:

```bash
./run.sh generate.py configs/config.json outputs/output --both
```

Both feet come from the *same* post list — `generate.py` produces the left
foot as an exact X-mirror of the right, matching how the original file works
(verified: `object_2.model` in the source is a mirror of `object_1.model`
down to sub-percent volume differences). `configs/config.json`'s posts, unmirrored,
are themselves the **right** foot: viewed top-down with +Y toward the toes
and +Z up (this project's coordinate convention throughout), `post_A_arch`
(the big-toe side) sits at -X and `post_D_pinky` at +X - the medial
(big-toe) edge facing the body midline at -X is a right foot's own local
shape, not a left one. (An earlier revision of this README had the two
swapped, which propagated into the output filenames - fixed now, in both
places.)

## How the shape works

Each post is a lofted, roughly-axisymmetric solid: wide flared base merging
into the plate → narrows to the waist (~50% height in the original) → bulges
back out to a rounded cap (~90-95% height) → tapers to a small dome apex.
Think spool/hourglass, not a plain cylinder. `generate.py` builds this as a
sequence of ellipses (from `profile`, scaled by `waist_rx`/`waist_ry`) lofted
with straight (`ruled`) segments between them — a true smooth spline loft was
tried first but overshot past its end sections (bulging past the profile's
own bounds); the ruled loft with ~15 profile points per post tracks the
measured curve closely without that artifact. Posts are sunk 0.5mm into the
plate before the union so they properly fuse into one watertight solid
instead of five separately-closed shells that only touch.

## How the plate outline works

`plate_outline.py` builds the boundary from the post layout, each run, as
the **union of pairwise hulls between each adjacent pair of posts**. Each
post is an *ellipse* (its own elliptical footprint, `waist_rx`/`waist_ry`,
offset outward by `margin`); posts are ordered along the arch, and each
adjacent *pair* (not every post at once) gets the convex hull of just those
two ellipses - a "stadium" shape: a straight line tangent to both ellipses
on each side, plus a fillet arc at each ellipse wherever the hull turns
there. Unioning only adjacent pairs (rather than one hull over every
ellipse) is what makes the outline hug the arch on the concave (forefoot)
side instead of drawing one straight line straight across an interior post.

An earlier version approximated each post by a *circle* of radius averaged
from `waist_rx`/`waist_ry`. That undersizes the outline along whichever axis
is larger - if `waist_ry` is e.g. double `waist_rx`, the averaged circle is
smaller than the post's actual footprint along y, and the post pokes out
past the plate edge there once printed. Using the real ellipse fixes that
regardless of eccentricity, while still only offsetting by a uniform
`margin` (the desired clearance is uniform, not shaped like the post).

Each post's ellipse is also *rotated* to track the local direction of the
arch, rather than always keeping `waist_rx` pinned to global +x - otherwise
an elliptical post only lines up with the toes it's actually between by
coincidence. `compute_post_rotations` (`plate_outline.py`) computes this
from the post layout, the same way the outline itself is derived rather
than stored:
- an **end post** (one neighbour) points `waist_rx` along the single edge
  to that neighbour - e.g. the arch-side post points along the line to its
  one neighbour, and the pinky-side post along the line to *its* one
  neighbour.
- an **interior post** (two neighbours) points along the *bisector* of the
  edges to its previous and next neighbour - the direction a mitred offset
  curve would turn through at that vertex - so the post turns smoothly
  along the arch instead of snapping between its two neighbours' directions.

`generate.py`'s `build_foot` computes this once per foot and feeds the same
angles to both `compute_outline` (so the plate boundary is offset in the
post's actual rotated frame) and each `build_post` call (so the post's own
3D loft is rotated to match) - the two can never disagree about which way a
post is turned. `_ellipse_polygon` and `_elliptical_closing` take the
rotation as an extra affine step (rotate to axis-align, do the usual
scale-based operation, rotate back) rather than hardcoding global-axis
alignment, so this is a strict generalization: a circular post (rotation
has no effect) or a post with `waist_rx == waist_ry` behaves exactly as
before.

Every post except the two at the very ends belongs to two pairwise hulls
(one per neighbour), and those two hulls generally touch that shared
ellipse's own boundary at two different points - nothing requires the two
neighbours to imply the same tangent point. Left alone, the union of the
two hulls meets at a real sharp point just outside the ellipse instead of
following its boundary between the two tangent points. Each such point gets
an exact fillet afterwards, shaped like that post's own (margined) ellipse:
a morphological "closing" with an elliptical structuring element - the
ellipse generalization of the circular `poly.buffer(r).buffer(-r)` trick.
Dilating then eroding by that ellipse replaces any concave notch narrower
than it with a true elliptical arc, and leaves the rest of the boundary
(already convex, or a wider notch elsewhere) alone. `_elliptical_closing` in
`plate_outline.py` implements this via an affine coordinate change (scale by
`1/rx, 1/ry` so the ellipse becomes a unit circle, do the ordinary circular
closing, scale back) rather than special-casing the circular case; for a
circular post (`waist_rx == waist_ry`) it's numerically the same operation
as before. This is exactly "where the hull forms a point, add a fillet
shaped like the adjacent ellipse."

`outputs/outline_2d_reference.png` plots the result against the post footprints,
and `outputs/topdown_shaded.png` renders the resulting solid, shaded (not
wireframe) and from directly above:

```bash
./run.sh tools/plot_outline.py configs/config.json outputs/outline_2d_reference.png
./run.sh tools/render_topdown.py outputs/output_left.stl outputs/topdown_shaded.png
```

This deliberately does not reach past the first/last post's own edge for an
extra tapered tip - the plate ends right at the hull, so it sits a bit short
under the big and little toe compared to the original mesh. Living without
that overhang is the point of this version; it's cheap to regenerate, so
just widen `margin` (or reintroduce a tip extension) if it turns out to
matter once printed.

This is deliberately a much simpler shape than the two earlier, more
elaborate attempts it replaces, both of which chased an asymmetric
"generous on the toe side, tight on the forefoot side" pad instead - both
ran into the same underlying problem: an offset curve `r(s) = p(s) +
w(s)*n(s)` picks up a velocity term from `w'(s)` (the width's rate of
change) on top of the base curve's own tangent, and when the width changes
quickly at the same time the base curve is turning, those two effects
compound into a real fold in the offset curve - not just a self-intersection
but an actual cusp, which then shows up as a sharp spurious spike once the
STL is opened in a real slicer (a shaded, non-wireframe top-down render -
`tools/render_topdown.py` - is what actually reveals this; a wireframe
render hides it). Each piece here (an ellipse, a tangent line, the hull of a
pair) is convex, so it can't itself produce a cusp or a self-intersection -
the only sharp features possible are the per-post junction points described
above, which are handled explicitly and exactly rather than worked around.
The asymmetric shape may be worth revisiting later, but as a boolean union
of per-post shapes (as the second attempt did), not a single swept offset
curve; see git-free history in this README's earlier revisions for both
attempts' full detail if reviving that.

This is also what fixed the bug you hit with `configs/config-2.json`: moving
`post_C` out to `y=25` used to leave it sitting off the edge of the old
static outline; now the plate outline is recomputed from wherever the posts
actually are, so it always encloses them. Confirmed `configs/config.json` and your
mutated `configs/config-2.json` both regenerate as single watertight solids, and
`tools/render_topdown.py` on each shows a clean outline.

## Verifying the recreation

*(Note: this section's numbers predate the plate-outline change above. The
posts themselves are unaffected and still match; the plate footprint is now
intentionally different from the original — convex instead of the original's
sculpted, slightly concave banana — so a fresh volume/surface diff against
the original mesh isn't a meaningful accuracy check for the plate anymore.)*

`configs/config.json`'s posts were *derived from the original mesh* (see
"Re-deriving from a source file" below). `tools/compare.py` checks a
generated STL against the original by sampling each surface and measuring
the distance to the nearest point on the other:

```bash
./run.sh tools/compare.py "../Fußspreitzer+v2+v4.3mf" 3D/Objects/object_1.model outputs/output_left.stl
```

At the point the posts (and the then-static, mesh-traced outline) were
verified: **volume within 2.4%** of the original (11927 mm³ vs 12221 mm³),
**median surface deviation 0.002mm**, **95th percentile ~0.4mm**, worst case
0.67mm localized to the very tip of each post's dome (where the ruled loft's
straight taper meets the original's smooth curvature — cosmetic only, well
under a nozzle's line width). `outputs/verification_render.png` is the side-by-side
render from that check, produced by:

```bash
./run.sh tools/render_compare.py "../Fußspreitzer+v2+v4.3mf" 3D/Objects/object_1.model outputs/output_left.stl outputs/verification_render.png
```

## Re-deriving from a source file

If you ever get a new baseline mesh (a rescan, a different print you want to
crib dimensions from), the whole `configs/config.json` can be rebuilt from it:

```bash
./run.sh tools/extract_profiles.py <file.3mf> 3D/Objects/object_1.model /tmp/profiles.json
./run.sh tools/derive_config.py /tmp/profiles.json configs/config.json
```

`extract_profiles.py` slices the mesh into thin z-layers, tracks each post's
elliptical cross-section (nearest-centroid matching between adjacent layers)
to build a radius-vs-height profile per post, and finds the plate's exact
thickness via binary search on where the cross-section stops being one
merged blob (it also traces the raw plate outline into `plate_outline_raw`,
but that's unused now - see "How the plate outline works" above).
`derive_config.py` turns the post tracks into the `x`/`y`/`waist_rx`/
`waist_ry`/`height`/`profile` structure above, simplifying the profile curve
with Ramer-Douglas-Peucker down to an editable number of points, and fills in
a default `margin` value.

One gotcha hit and fixed here: the first pass at profile extraction fit an
ellipse to each cross-section via the covariance matrix of its boundary
points, then took `axis = 2*sqrt(eigenvalue)`. That's only valid up to a
constant that depends on the boundary points' angular distribution — for
points uniform in angle around a circle of radius R (true here, since the
source mesh's circular facets are evenly spaced), the correct recovery is
`axis = sqrt(2*eigenvalue)`, not `2*sqrt(eigenvalue)`. The bug inflated every
radius by √2, silently doubling every cross-sectional area and post volume
(caught because the reconstructed total volume came out ~70% too large).
`derive_config.py` instead uses the boundary points' direct min/max distance
from the centroid, which matches the true polygon area almost exactly and
sidesteps the assumption entirely.

## Repository layout

```
generate.py, plate_outline.py, bambu_project.py, tools/   code (tracked)
configs/*.json                                             configs (tracked)
milestones/                                                curated builds worth keeping (tracked)
outputs/                                                    generated STL/3MF/PNG (gitignored)
venv/                                                        Python virtualenv (gitignored)
```

`configs/` and `outputs/` are a deliberate split: every config you're
actively fitting against lives in `configs/` and is tracked, but nothing
`generate.py` or `tools/*.py` *produce* is - those are cheap to regenerate
from a config, and git history filling up with every STL from every tweak
isn't useful. If a particular build is worth keeping permanently (a real
print you're happy with, a reference render, a "this is what broke"
snapshot), copy it into `milestones/` and commit it there instead - see
`milestones/README.md`.

## Files

- `generate.py` — the generator; reads a config (e.g. `configs/config.json`),
  writes STL (and optionally a Bambu Studio project - see `bambu_project.py`)
  to wherever you point `out_prefix` (`outputs/...` by convention).
- `plate_outline.py` — derives the plate boundary from the post layout (see
  above); imported by `generate.py`, not run directly.
- `bambu_project.py` — writes a ready-to-slice Bambu Studio project `.3mf`
  (see "Generating a ready-to-slice Bambu Studio project" above); imported
  by `generate.py` under `--bambu`, not run directly.
- `tools/` — the extraction/derivation/verification pipeline described
  throughout this README (`plot_outline_vs_original.py` and
  `annotation_overlay.py` specifically are vestigial, left over from tuning
  the previous, asymmetric outline design this project no longer uses -
  kept only as history).
- `configs/config.json` — the primary config (posts + plate
  thickness/margin), with posts derived from the original file.
  `configs/config-2.json`, `configs/config-3.json`, `configs/config-4.json`
  are variants used while developing/testing the outline and rotation
  logic (see git history and this README's earlier sections for what each
  one exercises).
- `milestones/` — curated builds worth keeping permanently; empty until you
  add something (see "Repository layout" above and `milestones/README.md`).
- `outputs/` — everything `generate.py`/`tools/*.py` generate: STLs, the
  Bambu `.3mf`, and every PNG render/plot this README's examples produce
  (`verification_render.png`, `topdown_shaded.png`,
  `outline_2d_reference.png`, etc.) - gitignored, regenerate any time with
  the commands above.
- `setup.sh`, `run.sh` — environment setup (see below).

## Environment notes

build123d's CAD kernel (OCP/OCCT) needs `libGL` at runtime, which isn't
present on a minimal Linux box. `setup.sh` installs it via Homebrew (`brew
install mesa`) if neither a system copy nor a Homebrew one is found; `run.sh`
points `LD_LIBRARY_PATH` at Homebrew's copy when running any script. If
you're on a machine without Homebrew and hit an OCP import error mentioning
`libGL.so.1`, install your distro's Mesa/OpenGL runtime package instead
(e.g. `sudo apt install libgl1`).
