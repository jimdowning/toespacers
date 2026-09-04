"""2D top-down plot of the derived plate outline against each post's own
footprint ellipse - the fastest way to sanity-check plate_outline.py's output
without doing a full 3D build.

Usage:
    python plot_outline.py ../configs/config.json ../outputs/out.png
"""
import sys
import os
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from plate_outline import compute_outline, compute_post_rotations, _base_radii


def main(config_path, out_path):
    c = json.load(open(config_path))
    posts = c['posts']
    rotations = compute_post_rotations(posts)
    outline = compute_outline(posts, rotations=rotations,
                               **{k: v for k, v in c['plate'].items() if k != 'thickness'})
    outline = np.array(outline + [outline[0]])

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.plot(outline[:, 0], outline[:, 1], '-', lw=1.5, color='green')
    ax.fill(outline[:, 0], outline[:, 1], alpha=0.2, color='green')
    for p, theta in zip(posts, rotations):
        ax.plot(p['x'], p['y'], 'ro')
        ax.annotate(p['name'], (p['x'], p['y']), fontsize=8)
        rx, ry = _base_radii(p)
        ax.add_patch(plt.matplotlib.patches.Ellipse((p['x'], p['y']), 2 * rx, 2 * ry, angle=theta,
                                                      fill=False, color='red', lw=0.8))
    ax.set_aspect('equal')
    ax.set_title(f'Derived outline vs post footprints ({config_path})')
    plt.savefig(out_path, dpi=140)
    print('saved', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
