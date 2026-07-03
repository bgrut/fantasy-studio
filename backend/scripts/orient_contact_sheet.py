"""
Orientation contact sheet — render all 24 axis-aligned orientations of a mesh
into ONE labeled grid image, so you can pick the correct standing pose by eye.

Why this ends the orientation saga:
  - The TripoSR mesh is now DETERMINISTIC (same bytes every run, thanks to the
    CUDA-determinism work). So whichever orientation looks "standing" here is
    correct FOREVER for that pattern — no agents, no per-render guessing.
  - A cube has exactly 24 axis-aligned orientations. We render all 24 from a
    fixed 3/4 camera (Z-up on screen), number them 1-24, and composite into a
    4x6 grid PNG.
  - You glance at the grid, find the standing dog (say it's #14), and we
    hardcode that rotation in mesh._PATTERN_ORIENTATION for 'quadruped'.

Pure matplotlib render — no Blender bridge, no GPU, no model. Just geometry.

Usage:
    # auto-find the most recent generated asset:
    python scripts/orient_contact_sheet.py

    # or point at a specific GLB:
    python scripts/orient_contact_sheet.py path/to/asset.glb

    # once you pick the right cell, verify it:
    python scripts/orient_contact_sheet.py path/to/asset.glb --show 14
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def all_24_orientations():
    """Return [(label, index, 3x3 rotation matrix)] for the 24 cube orientations."""
    seen = {}
    result = []
    angles = [0, 90, 180, 270]
    idx = 1
    for rx in angles:
        for ry in angles:
            for rz in angles:
                M = np.eye(3)
                for axis, deg in (([1, 0, 0], rx), ([0, 1, 0], ry), ([0, 0, 1], rz)):
                    if deg:
                        r = trimesh.transformations.rotation_matrix(
                            math.radians(deg), axis)[:3, :3]
                        M = r @ M
                key = tuple(np.round(M.flatten()).astype(int))
                if key in seen:
                    continue
                seen[key] = True
                # Build a readable label of the non-zero rotations
                parts = []
                if rx: parts.append(f"x{rx}")
                if ry: parts.append(f"y{ry}")
                if rz: parts.append(f"z{rz}")
                label = "+".join(parts) if parts else "identity"
                result.append((label, idx, M))
                idx += 1
    return result


def _find_latest_glb() -> Path | None:
    renders = BACKEND_ROOT / "renders"
    if not renders.exists():
        return None
    glbs = sorted(renders.rglob("asset_*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return glbs[0] if glbs else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("glb_path", nargs="?", default=None,
                   help="Path to GLB. Omit to auto-use the latest renders/asset_*.glb")
    p.add_argument("--show", type=int, default=None,
                   help="Render ONLY this orientation number (1-24), large, to verify a pick")
    p.add_argument("--out", type=str, default=None, help="Output PNG path")
    args = p.parse_args()

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except Exception as e:
        print(f"ERROR: matplotlib needed. pip install matplotlib  ({e})", file=sys.stderr)
        return 2

    glb_path = Path(args.glb_path) if args.glb_path else _find_latest_glb()
    if glb_path is None or not glb_path.exists():
        print("ERROR: no GLB found. Pass a path or generate an asset first.", file=sys.stderr)
        return 2

    print(f"Loading: {glb_path}")
    mesh = trimesh.load(str(glb_path), force="mesh")
    verts0 = np.array(mesh.vertices, dtype=np.float64)
    faces = np.array(mesh.faces)
    # Center on origin
    verts0 -= verts0.mean(axis=0)

    # FRAME-OFFSET CORRECTION: the GLB this script loads (via trimesh) is in a
    # frame rotated 180° about Y relative to where mesh._apply_pattern_orientation
    # applies its rotation (raw TripoSR mesh, pre-GLB-export). Without this, a
    # cell that looks "standing" here comes out upside-down in Blender. Pre-apply
    # the offset so the cell label you read is DIRECTLY usable as
    # _PATTERN_ORIENTATION[pattern] = (axis, deg).
    _frame_offset = trimesh.transformations.rotation_matrix(
        math.radians(180.0), [0, 1, 0])[:3, :3]
    verts0 = verts0 @ _frame_offset.T

    # Subsample faces for speed if huge (visual only — orientation is unaffected)
    if len(faces) > 8000:
        step = len(faces) // 8000
        faces = faces[::step]
        print(f"  (subsampled to {len(faces)} faces for fast preview)")

    orientations = all_24_orientations()

    def render_one(ax, M, label, index):
        v = verts0 @ M.T
        tris = v[faces]
        coll = Poly3DCollection(tris, alpha=1.0, linewidths=0)
        coll.set_facecolor((0.7, 0.7, 0.72))
        coll.set_edgecolor((0.4, 0.4, 0.4))
        ax.add_collection3d(coll)
        # Fixed 3/4 view, Z up on screen
        ax.view_init(elev=12, azim=-65)
        r = float(np.abs(v).max()) * 0.9
        ax.set_xlim(-r, r); ax.set_ylim(-r, r); ax.set_zlim(-r, r)
        ax.set_box_aspect((1, 1, 1))
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
        ax.set_title(f"#{index}  {label}", fontsize=9)
        # Draw a faint ground plane at min-Z to show "down"
        zmin = v[:, 2].min()
        gx = [-r, r, r, -r]; gy = [-r, -r, r, r]; gz = [zmin] * 4
        ground = Poly3DCollection([list(zip(gx, gy, gz))], alpha=0.12)
        ground.set_facecolor((0.2, 0.5, 0.9))
        ax.add_collection3d(ground)

    if args.show is not None:
        match = [o for o in orientations if o[1] == args.show]
        if not match:
            print(f"ERROR: --show must be 1..24", file=sys.stderr)
            return 2
        label, index, M = match[0]
        fig = plt.figure(figsize=(7, 7))
        ax = fig.add_subplot(111, projection="3d")
        render_one(ax, M, label, index)
        out = Path(args.out) if args.out else BACKEND_ROOT / "renders" / f"orient_show_{index}.png"
        fig.savefig(out, dpi=110, bbox_inches="tight")
        print(f"\n✓ saved → {out}")
        print(f"  Orientation #{index} = rotation '{label}'")
        print(f"  If this is the standing pose, tell Claude: 'use #{index}'")
        return 0

    # Full 4x6 grid
    fig = plt.figure(figsize=(20, 14))
    for label, index, M in orientations:
        ax = fig.add_subplot(4, 6, index, projection="3d")
        render_one(ax, M, label, index)
    fig.suptitle(f"Orientation audit — {glb_path.name}\n"
                 f"Find the cell where the subject STANDS (feet on the blue ground plane), "
                 f"then tell Claude the number.", fontsize=13)
    out = Path(args.out) if args.out else BACKEND_ROOT / "renders" / "orient_contact_sheet.png"
    fig.savefig(out, dpi=90, bbox_inches="tight")
    print(f"\n✓ saved contact sheet → {out}")
    print(f"  Open it, find the standing subject, tell Claude the cell number (1-24).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
