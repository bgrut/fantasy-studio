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


_ATTACH_WHEELS_CODE = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO="__HERO__"
o=bpy.data.objects.get(HERO)
out={"ok":False,"reason":""}
try:
    if o is None or o.type!="MESH":
        raise RuntimeError("no hero mesh")
    mw=o.matrix_world
    V=np.array([list(mw@v.co) for v in o.data.vertices], dtype=np.float64)
    X,Y,Z=V[:,0],V[:,1],V[:,2]
    xmin,xmax=X.min(),X.max(); ymin,ymax=Y.min(),Y.max(); zmin,zmax=Z.min(),Z.max()
    cx=(xmin+xmax)/2; cy=(ymin+ymax)/2; W=xmax-xmin; L=ymax-ymin; H=zmax-zmin

    # ── DE-CLAY the body: add a glossy clear-coat car-paint finish so highlights /
    # reflections define the form (matte = clay). Keep base colour from the texture.
    for mat in list(o.data.materials):
        if not mat or not mat.use_nodes: continue
        b=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'), None)
        if b is None: continue
        try: b.inputs["Roughness"].default_value=0.33
        except Exception: pass
        try: b.inputs["Metallic"].default_value=0.15
        except Exception: pass
        for cn in ("Coat Weight","Coat"):
            if cn in b.inputs:
                try: b.inputs[cn].default_value=0.7
                except Exception: pass
                break
        if "Coat Roughness" in b.inputs:
            try: b.inputs["Coat Roughness"].default_value=0.12
            except Exception: pass

    # ── DETECT the mesh's ACTUAL wheel positions (low-vert clusters per corner), then
    # SYMMETRIZE per axle (avg L/R |x|, avg per-axle y) so the four wheels stay
    # matched, and size the crisp wheel ~15% LARGER than the detected one so it fully
    # ENVELOPS the blobby fused original — one seamless wheel visible, exactly where
    # the car's wheel is. (Fixed-fraction placement sat beside the original → double
    # wheels, one not spinning.)
    low = Z < (zmin + 0.32*H)
    det={}
    for fb, ysel in (("F", Y>cy), ("B", Y<=cy)):
        for lr, xsel in (("L", X<=cx), ("R", X>cx)):
            m=low & ysel & xsel
            if int(m.sum())>10:
                det[fb+lr]={"x":float(X[m].mean()),"y":float(Y[m].mean()),
                            "r":float(max((Z[m].max()-Z[m].min())*0.62,1e-3)),
                            "w":float(max(X[m].max()-X[m].min(),1e-3))}
    def _avg(keys,field,default):
        vals=[det[k][field] for k in keys if k in det]
        return (sum(vals)/len(vals)) if vals else default
    wheel_r=_avg(list(det.keys()),"r",0.095*L)
    wheel_r=float(min(max(wheel_r*1.15, 0.06*L), 0.55*H if H>0 else 0.4))   # envelop original
    wheel_w=float(min(max(_avg(list(det.keys()),"w",W*0.14)*1.25, wheel_r*0.55), W*0.45))
    wbx=(sum(abs(det[k]["x"]-cx) for k in det)/len(det)) if det else W*0.40
    fwy=_avg([k for k in det if k.startswith("F")],"y",cy+L*0.32)
    bwy=_avg([k for k in det if k.startswith("B")],"y",cy-L*0.32)
    POS={"FL":(cx-wbx,fwy),"FR":(cx+wbx,fwy),"BL":(cx-wbx,bwy),"BR":(cx+wbx,bwy)}

    rubber=bpy.data.materials.get("HybTire") or bpy.data.materials.new("HybTire")
    rubber.use_nodes=True; rb=rubber.node_tree.nodes.get("Principled BSDF")
    rb.inputs["Base Color"].default_value=(0.022,0.022,0.026,1); rb.inputs["Roughness"].default_value=0.85
    spokem=bpy.data.materials.get("HybSpoke") or bpy.data.materials.new("HybSpoke")
    spokem.use_nodes=True; sb=spokem.node_tree.nodes.get("Principled BSDF")
    sb.inputs["Base Color"].default_value=(0.72,0.73,0.76,1); sb.inputs["Metallic"].default_value=0.95; sb.inputs["Roughness"].default_value=0.22

    # NOTE: in this environment primitive_add(location=L) leaves the object ORIGIN at
    # (0,0,0) with geometry offset to L — so transform_apply(rotation) would rotate
    # about the world origin and fling parts away. We therefore build every part AT
    # THE ORIGIN, rotate there (correct), join, then move the finished wheel to its
    # spot. Origin stays at the wheel's geometric centre => clean in-place spin.
    def cyl0(r,d,material):
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, location=(0,0,0))
        c=bpy.context.active_object; c.rotation_euler=(0,math.radians(90),0)
        bpy.ops.object.transform_apply(rotation=True); c.data.materials.append(material)
        bpy.ops.object.shade_smooth(); return c

    spoke_half=wheel_r*0.66          # spokes stay well INSIDE the tyre radius
    names=[]
    for key,(wx,wy) in POS.items():
        wz=zmin+wheel_r
        wob=cyl0(wheel_r, wheel_w, rubber); wob.name="Wheel_"+key
        parts=[wob]
        for ang in (0,90):           # spoke star (2 bars -> 4 spokes), built at origin
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0,0,0))
            sp=bpy.context.active_object
            sp.scale=(wheel_w*0.9, spoke_half*2.0, wheel_r*0.10)   # X=width, Y=radial, Z=thin
            bpy.ops.object.transform_apply(scale=True)
            sp.rotation_euler=(math.radians(ang),0,0); bpy.ops.object.transform_apply(rotation=True)
            sp.data.materials.append(spokem); parts.append(sp)
        hub=cyl0(wheel_r*0.26, wheel_w*1.06, spokem); parts.append(hub)
        bpy.ops.object.select_all(action='DESELECT')
        for p in parts: p.select_set(True)
        bpy.context.view_layer.objects.active=wob; bpy.ops.object.join()
        wob.location=(wx,wy,wz)      # move finished wheel into place (origin == centre)
        bpy.context.view_layer.update()
        names.append(wob.name)
    out={"ok":len(names)==4,"wheels":names,"wheel_r":round(wheel_r,3)}
    if len(names)!=4: out["reason"]="only %d wheels"%len(names)
    __result__=json.dumps(out)
except Exception as e:
    __result__=json.dumps({"ok":False,"reason":"{}: {}".format(type(e).__name__,e)})
'''


def attach_wheels(runner, hero_name: str, color_rgb: Optional[List[float]] = None,
                  verbose: bool = True) -> Dict[str, Any]:
    """HYBRID: detect the 4 wheel positions on a (TripoSG) car body and attach crisp
    procedural wheels there (independent objects named Wheel_FL/FR/BL/BR, origin at
    centre so they spin in place). Lets the reference-matching body keep its shape +
    texture while gaining real, spinnable wheels. Returns {"ok","wheels"}."""
    import json as _json
    code = _ATTACH_WHEELS_CODE.replace("__HERO__", hero_name)
    try:
        res = runner.run("attach_wheels", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] hybrid vehicle: attached 4 crisp wheels (r={info.get('wheel_r')}) to '{hero_name}'")
            return info
        if verbose:
            print(f"[composer] hybrid vehicle: wheel attach failed ({info.get('reason') if info else 'no result'})")
        return {"ok": False}
    except Exception as e:
        if verbose:
            print(f"[composer] hybrid vehicle: wheel attach error ({type(e).__name__}: {e})")
        return {"ok": False}


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
