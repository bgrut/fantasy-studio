"""
Inspect a GLB mesh's raw orientation and dimensions.

Tells us conclusively whether TripoSR's output is the source of the
orientation problem or whether it's introduced by Blender's import.

Usage:
    python scripts/inspect_glb.py path/to/asset.glb
    python scripts/inspect_glb.py path/to/asset.glb --rotate x90
    python scripts/inspect_glb.py path/to/asset.glb --rotate y180 --save fixed.glb

Rotation specs: x90, x-90, y180, z-90, etc. Combine with --save to test fixes.
"""

import argparse
import math
import sys
from pathlib import Path

import trimesh
import numpy as np


def _rotation_matrix(spec: str):
    """Parse 'x90' / 'y-180' / 'z45' → 4x4 transform matrix."""
    axis_char = spec[0].lower()
    degrees = float(spec[1:])
    axis = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis_char]
    return trimesh.transformations.rotation_matrix(math.radians(degrees), axis)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("glb_path", type=str)
    p.add_argument("--rotate", action="append", default=[],
                   help="Apply rotation(s). e.g. --rotate x90 --rotate z-90")
    p.add_argument("--save", type=str, default=None,
                   help="Save the (rotated) mesh to a new GLB for visual inspection")
    args = p.parse_args()

    path = Path(args.glb_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    mesh = trimesh.load(str(path), force="mesh")
    print(f"\n── RAW GLB ─────────────────────────────")
    print(f"  file:          {path.name}")
    print(f"  vertices:      {len(mesh.vertices):,}")
    print(f"  faces:         {len(mesh.faces):,}")
    print(f"  bbox min:      [{mesh.bounds[0][0]:+.3f}, {mesh.bounds[0][1]:+.3f}, {mesh.bounds[0][2]:+.3f}]")
    print(f"  bbox max:      [{mesh.bounds[1][0]:+.3f}, {mesh.bounds[1][1]:+.3f}, {mesh.bounds[1][2]:+.3f}]")
    dims = mesh.bounds[1] - mesh.bounds[0]
    print(f"  bbox dims:     X={dims[0]:.3f} Y={dims[1]:.3f} Z={dims[2]:.3f}")
    long_axis = ["X", "Y", "Z"][int(np.argmax(dims))]
    print(f"  longest axis:  {long_axis}")
    print(f"  has vertex colors: {hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None}")

    # Heuristic: for ground-standing subjects, height should be along the
    # "up" axis. If TripoSR/trimesh used Y-up convention, height is along Y.
    # If Z-up, height is along Z.
    if dims[1] > dims[0] and dims[1] > dims[2]:
        guess = "Y-up (mesh is tall along Y) — typical TripoSR/glTF convention"
    elif dims[2] > dims[0] and dims[2] > dims[1]:
        guess = "Z-up (mesh is tall along Z) — typical Blender convention"
    else:
        guess = f"horizontal/laying — long axis is {long_axis}, height ambiguous"
    print(f"  orientation guess: {guess}")

    if args.rotate:
        print(f"\n── APPLYING ROTATIONS ───────────────────")
        for spec in args.rotate:
            print(f"  applying: {spec}")
            mesh.apply_transform(_rotation_matrix(spec))
        dims = mesh.bounds[1] - mesh.bounds[0]
        print(f"  new dims:  X={dims[0]:.3f} Y={dims[1]:.3f} Z={dims[2]:.3f}")
        long_axis = ["X", "Y", "Z"][int(np.argmax(dims))]
        print(f"  new longest axis: {long_axis}")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(str(save_path), file_type="glb")
        print(f"\n✓ saved → {save_path}")
        print(f"  open in Windows 3D Viewer to verify the fix")

    return 0


if __name__ == "__main__":
    sys.exit(main())
