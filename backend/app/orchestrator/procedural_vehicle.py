"""Phase 20 — procedural hard-surface VEHICLE for the composer.

Image-to-3D blobs cars and fuses the wheels. For vehicles we build the car
parametrically: a crisp beveled body + glass cabin + lamps + 4 SEPARATE wheels
(so they can actually spin). The builder produces geometry ONLY — the composer
owns the environment, lighting, camera, and motion.

Built for the "look like the reference" roadmap:
  • `dims` lets reference-extracted proportions (body type / ride height / cabin)
    drive the shape later (layer 1);
  • the body stays one clean mesh named `Hero` so the reference photo can be
    texture-projected onto it (layer 2, reuses the multiview texturing).

Convention matches the composer hero: length along Y (front +Y), up Z, and the
WHOLE car grounded so the wheels sit on z=0. Wheels are parented to the body and
named Wheel_FL/FR/BL/BR. Returns {"ok", "hero", "wheels"}.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


_DEFAULT_DIMS = {
    "L": 4.1, "W": 1.70, "body_h": 0.46,
    "wheel_r": 0.44, "wheel_w": 0.30,
    "cab_w_frac": 0.70, "cab_l_frac": 0.38, "cab_h": 0.46,
}


_BUILD_CODE = r'''
import bpy, math, json
from mathutils import Vector

R, G, B = __RGB__
D = json.loads(r"""__DIMS__""")
L=D["L"]; W=D["W"]; body_h=D["body_h"]; wheel_r=D["wheel_r"]; wheel_w=D["wheel_w"]
cab_w=W*D["cab_w_frac"]; cab_l=L*D["cab_l_frac"]; cab_h=D["cab_h"]
axle_z=wheel_r
body_z=axle_z + 0.10 + body_h/2.0
cab_seat_z=body_z + body_h/2.0 + cab_h/2.0 - 0.12

def mat(name, rgb, metal=0.0, rough=0.5, emis=None):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(rgb[0],rgb[1],rgb[2],1)
    b.inputs["Metallic"].default_value=metal; b.inputs["Roughness"].default_value=rough
    if emis is not None:
        try:
            b.inputs["Emission Color"].default_value=(emis[0],emis[1],emis[2],1)
            b.inputs["Emission Strength"].default_value=4.0
        except Exception: pass
    return m

paint=mat("CarPaint",(R,G,B),metal=0.7,rough=0.28)
glass=mat("CarGlass",(0.04,0.05,0.07),metal=0.0,rough=0.08)
rubber=mat("CarTire",(0.03,0.03,0.035),metal=0.0,rough=0.85)
hub=mat("CarHub",(0.6,0.6,0.62),metal=0.9,rough=0.25)
light=mat("CarLight",(1.0,0.9,0.6),emis=(1.0,0.85,0.5))
tail=mat("CarTail",(0.5,0.02,0.02),emis=(1.0,0.05,0.05))

def box(name, sx, sy, sz, loc, material, bevel=0.06):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o=bpy.context.active_object; o.name=name
    o.scale=(sx,sy,sz); bpy.ops.object.transform_apply(scale=True)
    bm=o.modifiers.new("Bevel","BEVEL"); bm.width=bevel; bm.segments=3
    o.data.materials.append(material); bpy.ops.object.shade_smooth()
    return o

def join_into(target, others):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in others: ob.select_set(True)
    target.select_set(True); bpy.context.view_layer.objects.active=target
    bpy.ops.object.join()
    return target

# BODY (Hero) — single rounded hull, with cabin + lamps JOINED in (one rigid mesh,
# no parenting). Body keeps its own material slots after the join.
body=box("Hero", W, L, body_h, (0,0,body_z), paint, bevel=0.16)
cabin=box("CarCabin", cab_w, cab_l, cab_h, (0,-L*0.04,cab_seat_z), glass, bevel=0.12)
lamps=[]
for sy, col in ((+1, light), (-1, tail)):
    for sx in (-1,1):
        lamps.append(box("CarLamp", 0.18, 0.05, 0.09, (sx*W*0.32, sy*(L/2-0.04), body_z+0.02), col, bevel=0.02))
join_into(body, [cabin]+lamps)   # Hero now = body + cabin + lamps

# 4 wheels — each is an INDEPENDENT object (tire + hub joined). No parenting; the
# wheeled-drive motion moves the body and wheels together and spins the wheels in
# place (origin = wheel centre). Avoids all parent-offset / pivot issues.
wheel_names=[]
for fb, wy in (("F", L*0.32), ("B", -L*0.32)):
    for lr, wx in (("L", -(W/2-0.02)), ("R", (W/2-0.02))):
        bpy.ops.mesh.primitive_cylinder_add(radius=wheel_r, depth=wheel_w, location=(wx,wy,axle_z))
        wob=bpy.context.active_object; wob.name="Wheel_"+fb+lr
        wob.rotation_euler=(0,math.radians(90),0); bpy.ops.object.transform_apply(rotation=True)
        wob.data.materials.append(rubber); bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_cylinder_add(radius=wheel_r*0.30, depth=wheel_w*1.04, location=(wx,wy,axle_z))
        hob=bpy.context.active_object
        hob.rotation_euler=(0,math.radians(90),0); bpy.ops.object.transform_apply(rotation=True)
        hob.data.materials.append(hub); bpy.ops.object.shade_smooth()
        join_into(wob, [hob])    # wheel = tire + hub
        # CRITICAL: move the origin to the wheel's geometric centre, else
        # rotation_euler spins the wheel about the world origin (it orbits/flies up).
        bpy.ops.object.select_all(action='DESELECT')
        wob.select_set(True); bpy.context.view_layer.objects.active=wob
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
        wheel_names.append(wob.name)
wheel_names={k:v for k,v in zip(["FL","FR","BL","BR"], wheel_names)} if len(wheel_names)==4 else {str(i):n for i,n in enumerate(wheel_names)}

# GROUND the whole car: lowest wheel point -> z=0 (wheels already sit at axle_z-wheel_r=0)
bpy.context.view_layer.update()
__result__=json.dumps({"ok": True, "hero": body.name, "wheels": list(wheel_names.values())})
'''


def build_vehicle(runner, color_rgb: List[float], dims: Optional[Dict[str, float]] = None,
                  verbose: bool = True) -> Dict[str, Any]:
    """Build a crisp parametric car (Hero body + parented wheels) in the current
    scene. Geometry only. Returns {"ok", "hero", "wheels"} (never raises)."""
    import json as _json
    d = dict(_DEFAULT_DIMS)
    if dims:
        d.update({k: v for k, v in dims.items() if k in _DEFAULT_DIMS})
    rgb = list(color_rgb)[:3] if color_rgb else [0.55, 0.05, 0.06]
    code = (_BUILD_CODE
            .replace("__RGB__", "(" + ",".join(f"{c:.4f}" for c in rgb) + ")")
            .replace("__DIMS__", _json.dumps(d)))
    try:
        res = runner.run("procedural_vehicle", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] procedural vehicle: built '{info.get('hero')}' "
                      f"+ {len(info.get('wheels', []))} wheels")
            return info
        if verbose:
            print(f"[composer] procedural vehicle: failed ({info.get('reason') if info else 'no result'})")
        return {"ok": False}
    except Exception as e:
        if verbose:
            print(f"[composer] procedural vehicle: error ({type(e).__name__}: {e})")
        return {"ok": False}
