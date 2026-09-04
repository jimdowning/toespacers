"""Shaded (not wireframe) top-down + 3/4 render of a generated STL - the
fastest way to eyeball whether the plate outline is actually smooth (a
wireframe render's mesh lines make that hard to judge; flat shading makes
curvature/kinks/spikes obvious).

Usage:
    python render_topdown.py ../outputs/output_left.stl ../outputs/topdown_shaded.png
"""
import sys
import trimesh
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def main(stl_path, out_path):
    m = trimesh.load(stl_path, process=True)
    tris = m.vertices[m.faces]

    # simple flat (Lambertian) shading per face, lit mostly from straight
    # above so a top-down view reads the surface's curvature clearly
    normals = m.face_normals
    light = np.array([0.4, 0.3, 1.0]); light /= np.linalg.norm(light)
    shade = np.clip(normals @ light, 0.0, 1.0) ** 0.7
    colors = np.stack([0.25 + 0.7 * shade] * 3, axis=1)

    bounds = m.bounds
    span = max(bounds[1, 0] - bounds[0, 0], bounds[1, 1] - bounds[0, 1]) * 0.55
    cx, cy = m.centroid[0], m.centroid[1]
    zmax = bounds[1, 2] * 1.1

    fig = plt.figure(figsize=(18, 8))

    ax = fig.add_subplot(1, 2, 1, projection='3d')
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolor='none'))
    ax.set_xlim(cx - span, cx + span); ax.set_ylim(cy - span, cy + span); ax.set_zlim(0, zmax)
    ax.set_box_aspect((1, 1, zmax / (2 * span)))
    ax.view_init(elev=90, azim=-90)
    ax.set_title('Top-down (orthographic-ish), shaded')
    ax.set_axis_off()

    ax2 = fig.add_subplot(1, 2, 2, projection='3d')
    ax2.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolor='none'))
    ax2.set_xlim(cx - span, cx + span); ax2.set_ylim(cy - span, cy + span); ax2.set_zlim(0, zmax)
    ax2.set_box_aspect((1, 1, zmax / (2 * span)))
    ax2.view_init(elev=45, azim=-80)
    ax2.set_title('3/4 view, shaded')
    ax2.set_axis_off()

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print('saved', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
