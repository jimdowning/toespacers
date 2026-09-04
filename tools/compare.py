"""Geometrically compare the parametric recreation against the original mesh
straight out of the source .3mf.

Usage:
    python compare.py path/to/original.3mf 3D/Objects/object_1.model ../outputs/output_left.stl
"""
import numpy as np
import trimesh
from parse_mesh import parse_3mf_object
import sys

def load_orig(archive_path, object_path, z_shift):
    v, t = parse_3mf_object(archive_path, object_path)
    v = v.copy()
    v[:, 2] += z_shift  # put the plate's bottom face at z=0, matching generate.py's output
    return trimesh.Trimesh(vertices=v, faces=t, process=False)

def main(archive_path, object_path, gen_path):
    v, _ = parse_3mf_object(archive_path, object_path)
    z_shift = -v[:, 2].min()
    orig = load_orig(archive_path, object_path, z_shift)
    gen = trimesh.load(gen_path, process=True)
    print(f"orig: watertight={orig.is_watertight} volume={orig.volume:.2f} bbox={orig.bounds.tolist()}")
    print(f"gen:  watertight={gen.is_watertight} volume={gen.volume:.2f} bbox={gen.bounds.tolist()}")
    print(f"volume ratio gen/orig = {gen.volume/orig.volume:.4f}")

    pts_o, _ = trimesh.sample.sample_surface(orig, 20000, seed=0)
    _, dist_o2g, _ = gen.nearest.on_surface(pts_o)
    pts_g, _ = trimesh.sample.sample_surface(gen, 20000, seed=0)
    _, dist_g2o, _ = orig.nearest.on_surface(pts_g)

    print(f"\norig->gen surface distance: mean={dist_o2g.mean():.4f} median={np.median(dist_o2g):.4f} "
          f"p95={np.percentile(dist_o2g,95):.4f} max={dist_o2g.max():.4f}")
    print(f"gen->orig surface distance: mean={dist_g2o.mean():.4f} median={np.median(dist_g2o):.4f} "
          f"p95={np.percentile(dist_g2o,95):.4f} max={dist_g2o.max():.4f}")

    worst_idx = np.argsort(-dist_o2g)[:5]
    print("\nworst orig->gen points:")
    for i in worst_idx:
        print(f"  pt={pts_o[i]}  dist={dist_o2g[i]:.3f}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
