"""Phase 33 — Scene Dynamics (video side).

The world MOVES now: rain/snow particle weather, a sun that visibly drifts
across sunset/sunrise clips (light + color temperature shift), and wind sway
on the dressing props. The game runtime carries the same trio (points-based
precipitation, prop sway) from the same WorldSpec fields — one dynamics
vocabulary, two backends.

Gated FS_DYNAMICS; isolated; never raises.
"""
import json
import os

_DYNAMICS_CODE = r'''
import bpy, math, json, random
WEATHER="__WEATHER__"; WIND=__WIND__; SUNDRIFT=__SUNDRIFT__
TOTAL=__TOTAL__; SEED=__SEED__
random.seed(SEED)
sc=bpy.context.scene
applied=[]

# ── precipitation: particle system on an emitter plane above the set ────────
if WEATHER in ("rain","snow"):
    bpy.ops.mesh.primitive_plane_add(size=44, location=(0,0,18))
    em=bpy.context.object; em.name="WeatherEmitter"
    em.hide_render=True; em.display_type='WIRE'
    # instanced droplet/flake
    if WEATHER=="rain":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.012, location=(0,0,-40))
        drop=bpy.context.object; drop.name="RainDrop"; drop.scale=(0.35,0.35,3.2)
        mcol=(0.62,0.72,0.85); emis=0.0; count=2400; grav=1.0; life=max(TOTAL,60)
    else:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.02, location=(0,0,-40))
        drop=bpy.context.object; drop.name="SnowFlake"
        mcol=(0.95,0.96,1.0); emis=0.6; count=1600; grav=0.06; life=max(TOTAL*2,120)
    m=bpy.data.materials.new("PrecipMat"); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*mcol,1.0)
    try:
        b.inputs["Emission Color"].default_value=(*mcol,1.0)
        b.inputs["Emission Strength"].default_value=emis
    except Exception: pass
    drop.data.materials.append(m)
    ps=em.modifiers.new("Weather","PARTICLE_SYSTEM").particle_system
    st=ps.settings
    st.count=count; st.frame_start=-40; st.frame_end=TOTAL
    st.lifetime=life; st.emit_from='FACE'; st.physics_type='NEWTON'
    st.render_type='OBJECT'; st.instance_object=drop
    st.particle_size=1.0; st.size_random=0.4
    st.normal_factor=0.0; st.effector_weights.gravity=grav
    st.brownian_factor=0.02 if WEATHER=="rain" else 0.3
    applied.append(WEATHER)
    # wind field pushes both particles and (visually) matches prop sway
    if WIND>0.05:
        bpy.ops.object.effector_add(type='WIND', location=(0,0,6))
        wo=bpy.context.object; wo.rotation_euler=(math.radians(90),0,random.uniform(0,6.283))
        wo.field.strength=WIND*(2.2 if WEATHER=="snow" else 0.9)
        applied.append("windfield")

# ── sun drift: golden-hour clips get a MOVING sun (angle + warmth) ───────────
if SUNDRIFT:
    suns=[o for o in bpy.data.objects if o.type=="LIGHT" and o.data.type=="SUN"]
    if suns:
        s=suns[0]
        r0=list(s.rotation_euler)
        s.rotation_euler=(r0[0],r0[1],r0[2]); s.keyframe_insert("rotation_euler",frame=1)
        s.data.color=(1.0,0.85,0.65); s.data.keyframe_insert("color",frame=1)
        e0=s.data.energy; s.data.keyframe_insert("energy",frame=1)
        s.rotation_euler=(r0[0]+math.radians(9.0),r0[1],r0[2]+math.radians(4.0))
        s.keyframe_insert("rotation_euler",frame=TOTAL)
        s.data.color=(1.0,0.62,0.38); s.data.keyframe_insert("color",frame=TOTAL)
        s.data.energy=e0*0.62; s.data.keyframe_insert("energy",frame=TOTAL)
        applied.append("sundrift")

# ── wind sway on dressing props (gentle rock about the base) ─────────────────
if WIND>0.05:
    roots=[o for o in bpy.data.objects if o.name.startswith("PropRoot")]
    for pr in roots:
        ph=random.uniform(0,6.283); amp=math.radians(1.3)*WIND
        for f in range(1, TOTAL+1, 6):
            t=f/24.0
            pr.rotation_euler.x=math.sin(t*1.1+ph)*amp
            pr.rotation_euler.y=math.sin(t*1.7+ph*2)*amp*0.6
            pr.keyframe_insert("rotation_euler",frame=f)
    if roots: applied.append("sway:%d"%len(roots))
__result__=json.dumps({"ok":True,"applied":applied})
'''

_GOLDEN = ("sunset", "sunrise", "golden hour", "dawn", "dusk")


def build_dynamics(runner, mood: str = "", setting: str = "", weather: str = "",
                   wind: float = 0.5, total_frames: int = 120,
                   seed_key: str = "0", verbose: bool = False) -> bool:
    """Apply weather/sun-drift/sway to the CURRENT Blender scene. Weather can
    be passed explicitly or inferred from mood/setting keywords."""
    if os.environ.get("FS_DYNAMICS", "1") == "0":
        return False
    text = f"{mood} {setting}".lower()
    if not weather:
        if any(w in text for w in ("rain", "storm", "drizzl")):
            weather = "rain"
        elif any(w in text for w in ("snow", "blizzard", "wintry", "winter")):
            weather = "snow"
        else:
            weather = "none"
    sundrift = any(w in text for w in _GOLDEN)
    if weather == "none" and not sundrift and wind < 0.05:
        return False
    import zlib
    seed = zlib.crc32(str(seed_key).encode()) % 100000
    try:
        code = (_DYNAMICS_CODE
                .replace("__WEATHER__", weather)
                .replace("__WIND__", f"{float(wind):.2f}")
                .replace("__SUNDRIFT__", "True" if sundrift else "False")
                .replace("__TOTAL__", str(int(total_frames)))
                .replace("__SEED__", str(seed)))
        res = runner.run("dynamics", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        ok = bool(info and info.get("ok") and info.get("applied"))
        if ok and verbose:
            print(f"[composer] dynamics: {', '.join(info['applied'])}")
        return ok
    except Exception as e:
        if verbose:
            print(f"[composer] dynamics skipped ({type(e).__name__}: {e})")
        return False
