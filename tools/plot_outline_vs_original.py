"""2D top-down plot of the ORIGINAL mesh's own plate outline (traced from its
bottom face) against the current config's post footprint circles - this is
what showed the original design is asymmetric (generous toe side, pinched
forefoot side), which motivated the ribbon-sweep outline in plate_outline.py.

Usage:
    python plot_outline_vs_original.py path/to/original.3mf 3D/Objects/object_1.model ../configs/config.json ../outputs/out.png
"""
import sys
import os
import json
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from parse_mesh import parse_3mf_object
from plate_outline import _base_radius


def main(archive_path, object_path, config_path, out_path):
    v, t = parse_3mf_object(archive_path, object_path)
    m = trimesh.Trimesh(vertices=v, faces=t, process=False)
    zmin = m.bounds[0, 2]
    sec = m.section(plane_origin=[0, 0, zmin + 0.05], plane_normal=[0, 0, 1])
    outline = sec.discrete[0][:, :2]

    c = json.load(open(config_path))

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.plot(outline[:, 0], outline[:, 1], '-', lw=1.5)
    ax.fill(outline[:, 0], outline[:, 1], alpha=0.2)
    for p in c['posts']:
        ax.plot(p['x'], p['y'], 'ro')
        ax.annotate(p['name'], (p['x'], p['y']), fontsize=8)
        ax.add_patch(plt.Circle((p['x'], p['y']), _base_radius(p), fill=False, color='red', lw=0.8))
    ax.set_aspect('equal')
    ax.axhline(0, color='gray', lw=0.5)
    ax.axvline(0, color='gray', lw=0.5)
    ax.set_title('Original plate outline (bottom slice) + post base circles')
    plt.savefig(out_path, dpi=140)
    print('saved', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
