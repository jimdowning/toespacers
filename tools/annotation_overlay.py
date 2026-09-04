"""Calibrate an annotated screenshot (drawn on a top-down render of a build
from this project) into real-world mm, and plot the annotated curves against
the *current* config's derived outline - see "Tuning the outline shape from
an annotated screenshot" in the README for the method and how to read the
result.

Assumes two annotation colors: blue ("ideal") and orange ("acceptable"),
matching CSS-ish blue/orange (edit BLUE_MASK/ORANGE_MASK below for other
colors). Assumes the screenshot is a near-orthographic top-down view of
`stl_path`, with its own real-world bounding box unaffected by the crop
(fine even if the screenshot is cropped tighter than the STL's bbox on one
axis, as long as it isn't rotated/perspective-distorted much).

Usage:
    python annotation_overlay.py screenshot.png ../outputs/output_left.stl ../configs/config.json ../outputs/out.png
"""
import sys
import os
import json
import numpy as np
import trimesh
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from plate_outline import compute_outline, _base_radius


def extract_mask(arr, color):
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    if color == 'blue':
        return (b > 150) & (b - r > 60) & (b - g > 40)
    if color == 'orange':
        return (r > 180) & (g > 80) & (g < 200) & (r - b > 80) & (r - g > 20)
    raise ValueError(color)


def calibrate(img_path, stl_path):
    im = Image.open(img_path).convert('RGB')
    arr = np.array(im).astype(int)
    gray = arr.mean(axis=2)
    colored = extract_mask(arr, 'blue') | extract_mask(arr, 'orange')
    model_mask = (gray < 243) & ~colored
    ys, xs = np.where(model_mask)
    px0, px1, py0, py1 = xs.min(), xs.max(), ys.min(), ys.max()

    m = trimesh.load(stl_path, process=True)
    wx0, wy0, _ = m.bounds[0]
    wx1, wy1, _ = m.bounds[1]

    px_aspect = (px1 - px0) / (py1 - py0)
    w_aspect = (wx1 - wx0) / (wy1 - wy0)
    print(f'pixel bbox aspect {px_aspect:.4f} vs world bbox aspect {w_aspect:.4f} '
          f'(should be close - if not, this screenshot is not a clean top-down view)')

    sx = (px1 - px0) / (wx1 - wx0)
    sy = (py1 - py0) / (wy1 - wy0)

    def px_to_world(px, py):
        return (px - px0) / sx + wx0, wy1 - (py - py0) / sy

    out = {}
    for color in ('blue', 'orange'):
        mask = extract_mask(arr, color)
        ys, xs = np.where(mask)
        wx, wy = px_to_world(xs, ys)
        out[color] = np.stack([wx, wy], axis=1)
    return out


def main(img_path, stl_path, config_path, out_path):
    curves = calibrate(img_path, stl_path)
    c = json.load(open(config_path))
    outline = np.array(compute_outline(c['posts'], **{k: v for k, v in c['plate'].items() if k != 'thickness'}))
    outline = np.vstack([outline, outline[0]])

    fig, ax = plt.subplots(figsize=(14, 8))
    ax.plot(outline[:, 0], outline[:, 1], '-', color='green', lw=2, label='current outline')
    for color, pts in curves.items():
        ax.scatter(pts[:, 0], pts[:, 1], s=2, color=color, label=color)
    for p in c['posts']:
        ax.plot(p['x'], p['y'], 'k+')
        ax.annotate(p['name'], (p['x'], p['y']), fontsize=8)
        ax.add_patch(plt.Circle((p['x'], p['y']), _base_radius(p), fill=False, color='gray', lw=0.6, ls=':'))
    ax.set_aspect('equal')
    ax.legend()
    ax.set_title('Current outline vs annotated curves (calibrated, world mm)')
    plt.savefig(out_path, dpi=140)
    print('saved', out_path)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
