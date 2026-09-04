"""Slice a source mesh (a post/plate object read straight out of a .3mf
archive) into thin z-layers to recover per-post radius-vs-height profiles and
the plate outline, ready for derive_config.py.

Usage:
    python extract_profiles.py model.3mf 3D/Objects/object_1.model profiles.json
"""
import numpy as np
import trimesh
from parse_mesh import parse_3mf_object, list_3mf_objects
import sys, json

def load(archive_path, object_path):
    v, t = parse_3mf_object(archive_path, object_path)
    return trimesh.Trimesh(vertices=v, faces=t, process=False)

def ellipse_fit(coords):
    # coords: Nx2, points on loop boundary (polygon vertices, not necessarily uniform)
    cx, cy = coords.mean(axis=0)
    d = coords - [cx, cy]
    cov = (d.T @ d) / len(d)
    evals, evecs = np.linalg.eigh(cov)
    # semi-axes from covariance eigenvalues of a uniform-boundary ellipse: for continuous
    # ellipse boundary parametrized uniformly by angle, var = (a^2+b^2)/4 roughly; but our
    # points are polygon vertices from mesh, roughly uniform in angle since it's a revolve.
    # Use 2*sqrt(eval) as approximation, calibrate later against known circle.
    axes = 2*np.sqrt(np.clip(evals,0,None))
    order = np.argsort(-axes)
    return cx, cy, axes[order[0]], axes[order[1]], evecs[:,order[0]]

def slice_mesh(m, zs):
    out = []
    for z in zs:
        sec = m.section(plane_origin=[0,0,z], plane_normal=[0,0,1])
        loops = []
        if sec is not None:
            for coords3 in sec.discrete:
                coords = coords3[:, :2]
                cx, cy, a, b, dirn = ellipse_fit(coords)
                r = np.sqrt(((coords-[cx,cy])**2).sum(axis=1))
                x = coords[:,0]; y = coords[:,1]
                area = 0.5*abs(np.dot(x, np.roll(y,1)) - np.dot(y, np.roll(x,1)))
                loops.append(dict(cx=cx, cy=cy, a=a, b=b, rmin=r.min(), rmax=r.max(), area=area, n=len(coords)))
        out.append((z, loops))
    return out

def track_posts(slices, min_area_plate=800):
    """Separate the big plate loop from post loops, then track posts across z by nearest centroid."""
    tracks = []  # list of dict(id, points=[(z,loop)...])
    active = {}  # id -> last loop
    next_id = 0
    plate_loops = []
    for z, loops in slices:
        # classify: plate loop has very large area OR rmax > 20
        post_loops = [l for l in loops if l['area'] < min_area_plate and l['rmax'] < 20]
        plate_here = [l for l in loops if l not in post_loops]
        for pl in plate_here:
            plate_loops.append((z, pl))
        matched = set()
        new_active = {}
        for pid, last in list(active.items()):
            # find nearest post_loop to last centroid
            best = None; bestd = 1e9
            for i,l in enumerate(post_loops):
                if i in matched: continue
                d = (l['cx']-last['cx'])**2+(l['cy']-last['cy'])**2
                if d < bestd:
                    bestd = d; best = i
            if best is not None and bestd < 9:  # within 3mm
                matched.add(best)
                new_active[pid] = post_loops[best]
                tracks[pid]['points'].append((z, post_loops[best]))
        for i,l in enumerate(post_loops):
            if i not in matched:
                pid = next_id; next_id += 1
                tracks.append(dict(id=pid, points=[(z,l)]))
                new_active[pid] = l
        active = new_active
    return tracks, plate_loops

def find_plate_top_z(m, lo, hi, iters=40):
    """Binary search the exact z where the cross-section stops being a single
    merged loop (plate) and splits into multiple loops (posts)."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        sec = m.section(plane_origin=[0, 0, mid], plane_normal=[0, 0, 1])
        n = 0 if sec is None else len(sec.discrete)
        if n <= 1:
            lo = mid
        else:
            hi = mid
    return lo


def plate_outline(m, z):
    sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    loops = sec.discrete
    assert len(loops) == 1, f"expected a single plate outline loop at z={z}, got {len(loops)}"
    return loops[0][:, :2]


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        print("objects available in", sys.argv[1] if len(sys.argv) > 1 else '<archive>', ":")
        if len(sys.argv) > 1:
            print(list_3mf_objects(sys.argv[1]))
        sys.exit(1)
    archive_path, object_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    m = load(archive_path, object_path)
    zmin, zmax = m.bounds[:, 2]
    zs = np.arange(zmin+0.02, zmax-0.01, 0.1)
    slices = slice_mesh(m, zs)
    tracks, plate_loops = track_posts(slices)
    tracks = [t for t in tracks if len(t['points']) > 5]
    print(f"Found {len(tracks)} post tracks")
    for t in tracks:
        zs_t = [p[0] for p in t['points']]
        print(f"track {t['id']}: z {min(zs_t):.2f}..{max(zs_t):.2f}  n={len(t['points'])}  cx~{np.mean([p[1]['cx'] for p in t['points']]):.2f} cy~{np.mean([p[1]['cy'] for p in t['points']]):.2f}")

    plate_top_z = find_plate_top_z(m, zmin + 0.1, zmax - 0.1)
    outline = plate_outline(m, zmin + 0.05)
    print(f"plate thickness = {plate_top_z - zmin:.4f} mm, outline has {len(outline)} raw points")

    with open(out_path, 'w') as f:
        json.dump(dict(
            tracks=[dict(id=t['id'], points=[(z, l) for z, l in t['points']]) for t in tracks],
            zmin=zmin, zmax=zmax,
            plate_thickness=plate_top_z - zmin,
            plate_outline_raw=outline.tolist(),
        ), f, indent=1)
