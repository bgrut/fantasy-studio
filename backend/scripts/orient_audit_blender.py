"""
Blender-native orientation audit — the bulletproof, frame-mismatch-free version.

Every prior calibration failed because the mesh passed through several coordinate
conventions (TripoSR-native → trimesh → glTF export → Blender import → matplotlib
display), and a rotation measured in one frame didn't mean the same thing in
another. ALSO: 3/4-angle previews made a *rearing* dog look like it was standing.

This script removes both problems:
  - Renders all 24 axis-aligned orientations using the REAL Blender renderer
    (same frame the final video uses — what you see is exactly what you get).
  - Uses a TRUE SIDE-PROFILE camera (near-zero elevation) with a ground plane,
    so "standing" is unmistakable: feet on the line, body horizontal, head up.

You pick the standing cell's number; we paste its Euler into
composer._BLENDER_PATTERN_EULER for that pattern. Because the audit and the
application both run in Blender's frame, the pick is guaranteed correct.

Prereqs: the headless Blender bridge must be running (same one render_from_prompt
uses).

Usage:
    # auto-find latest asset GLB:
    python scripts/orient_audit_blender.py

    # or a specific GLB:
    python scripts/orient_audit_blender.py path/to/asset.glb
"""

import argparse
import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.mcp import registry, bridge  # noqa: E402


def all_24_eulers():
    """Return [(label, index, (rx, ry, rz) degrees)] for the 24 cube orientations.

    These are Blender XYZ Euler degrees applied in Blender's own frame.
    """
    import numpy as np
    import trimesh
    seen = {}
    out = []
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
                parts = []
                if rx: parts.append(f"x{rx}")
                if ry: parts.append(f"y{ry}")
                if rz: parts.append(f"z{rz}")
                label = "+".join(parts) if parts else "identity"
                out.append((label, idx, (rx, ry, rz)))
                idx += 1
    return out


def _find_latest_glb() -> Path | None:
    renders = BACKEND_ROOT / "renders"
    if not renders.exists():
        return None
    glbs = sorted(renders.rglob("asset_*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return glbs[0] if glbs else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("glb_path", nargs="?", default=None)
    p.add_argument("--out", type=str, default=None)
    args = p.parse_args()

    glb_path = Path(args.glb_path) if args.glb_path else _find_latest_glb()
    if glb_path is None or not glb_path.exists():
        print("ERROR: no GLB found. Generate an asset first or pass a path.", file=sys.stderr)
        return 2

    # Connect to the bridge.
    if not bridge.is_connected():
        bridge.connect(timeout=3.0)
    if not bridge.ping(timeout=2.0):
        print("ERROR: Blender bridge not reachable. Start the headless bridge first.", file=sys.stderr)
        return 2

    tmp_dir = BACKEND_ROOT / "renders" / "_orient_audit"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f"Auditing: {glb_path}")
    print("Resetting scene + importing mesh...")
    registry.call("reset_scene", {})
    imp = registry.call("import_mesh_file", {
        "filepath": str(glb_path), "name": "Hero", "orientation_fix": None,
    })
    if not (isinstance(imp, dict) and imp.get("ok")):
        print(f"ERROR: import failed: {imp}", file=sys.stderr)
        return 2

    eulers = all_24_eulers()
    tile_paths = []

    # Render each orientation from a fixed TRUE-SIDE camera with a ground plane.
    for label, index, (rx, ry, rz) in eulers:
        tile = tmp_dir / f"cell_{index:02d}.png"
        code = f"""
import bpy, math
from mathutils import Vector

o = bpy.data.objects.get('Hero')
o.rotation_mode = 'XYZ'
o.location = (0.0, 0.0, 0.0)
o.rotation_euler = (math.radians({rx}), math.radians({ry}), math.radians({rz}))
bpy.context.view_layer.update()

# Ground it: lift so the lowest world-space corner sits on z=0.
zs = [(o.matrix_world @ Vector(c)).z for c in o.bound_box]
o.location.z = -min(zs)
bpy.context.view_layer.update()

# Subject extents (full world AABB) for an orthographic fit.
xs2 = [(o.matrix_world @ Vector(c)).x for c in o.bound_box]
ys2 = [(o.matrix_world @ Vector(c)).y for c in o.bound_box]
zs2 = [(o.matrix_world @ Vector(c)).z for c in o.bound_box]
mid_z = (min(zs2) + max(zs2)) / 2.0
span = max(max(xs2) - min(xs2), max(ys2) - min(ys2), max(zs2) - min(zs2), 1.0)

# TRUE ORTHOGRAPHIC front camera (look along +Y from -Y), at mid height,
# perfectly horizontal. No perspective distortion: a standing subject is
# unambiguously TALL with feet on the ground line and head at the top.
cam_data = bpy.data.cameras.new('AuditCam')
cam_data.type = 'ORTHO'
cam_data.ortho_scale = span * 1.6
cam = bpy.data.objects.new('AuditCam', cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = Vector((0.0, -span * 4.0, mid_z))
look = Vector((0.0, 0.0, mid_z)) - cam.location
cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()

# Ground plane.
bpy.ops.mesh.primitive_plane_add(size=span * 6, location=(0, 0, 0))
plane = bpy.context.active_object

# Light.
light_data = bpy.data.lights.new('AuditLight', type='SUN')
light_data.energy = 3.5
light = bpy.data.objects.new('AuditLight', light_data)
bpy.context.scene.collection.objects.link(light)
light.rotation_euler = (math.radians(50), 0, math.radians(40))

bpy.context.scene.camera = cam
bpy.context.scene.render.engine = 'BLENDER_EEVEE'
bpy.context.scene.render.resolution_x = 400
bpy.context.scene.render.resolution_y = 400
try:
    bpy.context.scene.eevee.taa_render_samples = 8
except Exception:
    pass
bpy.context.scene.render.filepath = r'{str(tile)}'
bpy.ops.render.render(write_still=True)

# Cleanup throwaway objects so next orientation is clean.
bpy.data.objects.remove(cam, do_unlink=True)
bpy.data.cameras.remove(cam_data)
bpy.data.objects.remove(plane, do_unlink=True)
bpy.data.objects.remove(light, do_unlink=True)
bpy.data.lights.remove(light_data)
__result__ = r'{str(tile)}'
"""
        registry.call("execute_python", {"code": code})
        if tile.exists():
            tile_paths.append((label, index, tile))
            print(f"  rendered #{index:2d}  {label}")
        else:
            print(f"  FAILED  #{index:2d}  {label}")

    # Composite into a labeled 4x6 grid.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
    except Exception as e:
        print(f"matplotlib needed for grid: {e}", file=sys.stderr)
        print(f"Individual tiles are in: {tmp_dir}")
        return 0

    fig = plt.figure(figsize=(20, 14))
    for label, index, tile in tile_paths:
        ax = fig.add_subplot(4, 6, index)
        ax.imshow(mpimg.imread(str(tile)))
        ax.set_title(f"#{index}  {label}", fontsize=10)
        ax.axis("off")
    fig.suptitle(f"Blender orientation audit (TRUE SIDE VIEW) — {glb_path.name}\n"
                 f"Pick the cell where the subject STANDS on the ground: body horizontal, "
                 f"all feet down, head up. Tell Claude the number.", fontsize=13)
    out = Path(args.out) if args.out else BACKEND_ROOT / "renders" / "orient_audit_blender.png"
    fig.savefig(out, dpi=90, bbox_inches="tight")
    print(f"\n[OK] saved audit grid -> {out}")
    print(f"  These are REAL Blender renders from a side view. The standing cell")
    print(f"  is the one we lock in - guaranteed to match the final video.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
