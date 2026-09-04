"""Render the original mesh next to the parametric recreation for a visual
side-by-side sanity check.

Usage:
    python render_compare.py path/to/original.3mf 3D/Objects/object_1.model ../outputs/output_left.stl ../outputs/out.png
"""
import sys
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from parse_mesh import parse_3mf_object

def load_orig(archive_path, object_path):
    v, t = parse_3mf_object(archive_path, object_path)
    v = v.copy()
    v[:, 2] -= v[:, 2].min()  # bottom of plate at z=0, matching generate.py's output
    return trimesh.Trimesh(vertices=v, faces=t, process=False)

def main(archive_path, object_path, gen_path, out_path):
    orig = load_orig(archive_path, object_path)
    gen = trimesh.load(gen_path, process=True)

    fig = plt.figure(figsize=(14, 7))
    for i, (m, title) in enumerate([(orig, 'Original (from 3MF mesh)'), (gen, 'Parametric recreation')]):
        ax = fig.add_subplot(1, 2, i+1, projection='3d')
        tris = m.vertices[m.faces]
        pc = Poly3DCollection(tris, facecolor=(0.8, 0.8, 0.85), edgecolor=(0.3, 0.3, 0.3), linewidth=0.05)
        ax.add_collection3d(pc)
        ax.set_xlim(-50, 50); ax.set_ylim(-50, 50); ax.set_zlim(0, 25)
        ax.set_box_aspect((100, 100, 25))
        ax.view_init(elev=35, azim=-60)
        ax.set_title(title)
        ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    print('saved', out_path)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
