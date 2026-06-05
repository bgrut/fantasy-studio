"""
Fast texture-projection probe — iterate the reference-projection texturing
WITHOUT paying for SDXL + TripoSG each time.

Takes an existing asset GLB + its reference PNG, orients it like the composer
does, applies _apply_reference_texture, and renders a single front-ortho still
so we can eyeball color/face placement and tune flip_u/flip_v.

Usage:
    python scripts/texture_probe.py <asset.glb> <reference.png> [--flip-u] [--flip-v]
    # or auto-find the latest asset+reference pair:
    python scripts/texture_probe.py
"""
import argparse
import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator.composer import (  # noqa: E402
    _apply_reference_texture, _apply_multiview_texture)


class _Shim:
    """Minimal runner shim: composer._apply_reference_texture only needs .run."""
    def run(self, step, op, params, critical=True):
        return registry.call(op, params)


def _find_latest_pair():
    renders = BACKEND_ROOT / "renders"
    glbs = sorted(renders.rglob("asset_*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    for g in glbs:
        ref = next(iter(g.parent.glob("reference_*.png")), None)
        if ref:
            return g, ref
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb", nargs="?", default=None)
    ap.add_argument("ref", nargs="?", default=None)
    ap.add_argument("--flip-u", action="store_true")
    ap.add_argument("--flip-v", action="store_true")
    ap.add_argument("--multiview", action="store_true",
                    help="full hybrid: side + img2img-refined ±Y back-projection")
    ap.add_argument("--subject", default="a brown dog", help="prompt subject for refiner")
    ap.add_argument("--euler", default="0,0,90", help="quadruped triposg default")
    ap.add_argument("--out", default=str(BACKEND_ROOT / "renders" / "_texture_probe.png"))
    args = ap.parse_args()

    glb = Path(args.glb) if args.glb else None
    ref = Path(args.ref) if args.ref else None
    if glb is None or ref is None:
        glb, ref = _find_latest_pair()
    if not glb or not ref or not glb.exists() or not ref.exists():
        print("ERROR: need an asset GLB + reference PNG (none found).", file=sys.stderr)
        return 2
    # Bridge runs in a different cwd — always hand it absolute paths.
    glb = glb.resolve()
    ref = ref.resolve()

    rx, ry, rz = (float(x) for x in args.euler.split(","))
    print(f"GLB: {glb.name}\nREF: {ref.name}\neuler=({rx},{ry},{rz}) flip_u={args.flip_u} flip_v={args.flip_v}")

    if not bridge.is_connected():
        bridge.connect(timeout=3.0)
    if not bridge.ping(timeout=3.0):
        print("ERROR: bridge not reachable.", file=sys.stderr)
        return 2

    print("  [1/5] reset_scene…", flush=True)
    registry.call("reset_scene", {})
    print("  [2/5] import_mesh_file…", flush=True)
    imp = registry.call("import_mesh_file", {"filepath": str(glb), "name": "Hero", "orientation_fix": None})
    if not (isinstance(imp, dict) and imp.get("ok")):
        print(f"ERROR: import failed: {imp}", file=sys.stderr)
        return 2

    # Orient like the composer (no-bake) + ground.
    print("  [3/5] orient+ground…", flush=True)
    registry.call("execute_python", {"code": (
        "import bpy, math\n"
        "from mathutils import Vector\n"
        "o=bpy.data.objects.get('Hero')\n"
        "o.rotation_mode='XYZ'\n"
        f"o.rotation_euler=(math.radians({rx}),math.radians({ry}),math.radians({rz}))\n"
        "bpy.context.view_layer.update()\n"
        "zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]\n"
        "o.location.z-=min(zs)\n"
        "bpy.context.view_layer.update()\n"
    )})

    if args.multiview:
        print("  [4/5] apply_multiview_texture (renders + img2img)…", flush=True)
        slots = {"subject": {"library_query": "dog", "color_name": "brown",
                             "base_pattern": "quadruped"},
                 "scene": {"mood": "golden hour"}}
        ok = _apply_multiview_texture(_Shim(), "Hero", str(ref), slots,
                                      ref.parent, "probe", style="photoreal")
    else:
        print("  [4/5] apply_reference_texture…", flush=True)
        ok = _apply_reference_texture(_Shim(), "Hero", str(ref),
                                      flip_u=args.flip_u, flip_v=args.flip_v)
    print(f"texture applied: {ok}", flush=True)
    print("  [5/5] render stills…", flush=True)

    # Render two ortho stills: SIDE (where the X-projection lands — the money
    # shot) and FRONT. cam_axis: 'side' = look along -X, 'front' = look along +Y.
    out = Path(args.out)
    side_out = out.with_name(out.stem + "_side.png")
    front_out = out.with_name(out.stem + "_front.png")
    for label, cam_loc, fpath in (
        ("side", "Vector((span*4.0, 0.0, midz))", str(side_out)),
        ("front", "Vector((0.0, -span*4.0, midz))", str(front_out)),
    ):
        registry.call("execute_python", {"code": f"""
import bpy, math
from mathutils import Vector
o=bpy.data.objects.get('Hero')
for nm in ('PC','PL'):
    ob=bpy.data.objects.get(nm)
    if ob: bpy.data.objects.remove(ob, do_unlink=True)
xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]
ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
zz=[(o.matrix_world@Vector(c)).z for c in o.bound_box]
span=max(max(xs)-min(xs),max(ys)-min(ys),max(zz)-min(zz),1.0)
midz=(min(zz)+max(zz))/2.0
cd=bpy.data.cameras.new('PC'); cd.type='ORTHO'; cd.ortho_scale=span*1.5
co=bpy.data.objects.new('PC',cd); bpy.context.scene.collection.objects.link(co)
co.location={cam_loc}; look=Vector((0,0,midz))-co.location
co.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
ll=bpy.data.lights.new('PL',type='SUN'); ll.energy=4.0
lo=bpy.data.objects.new('PL',ll); bpy.context.scene.collection.objects.link(lo)
lo.rotation_euler=(math.radians(55),0,math.radians(35))
bpy.context.scene.camera=co
sc=bpy.context.scene
sc.render.engine='BLENDER_EEVEE'
sc.render.resolution_x=640; sc.render.resolution_y=640
try: sc.view_settings.view_transform='AgX'
except Exception: pass
sc.render.filepath=r'{fpath}'
bpy.ops.render.render(write_still=True)
__result__='rendered'
"""})
        print(f"[OK] {label} still -> {fpath}  ({'exists' if Path(fpath).exists() else 'MISSING'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
