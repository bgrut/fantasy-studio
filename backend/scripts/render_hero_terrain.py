"""Hero on real DEM terrain — e.g. a cheetah in a realistic desert.
Builds DEM terrain, drops the hero on it, cinematic medium shot.

Usage: python scripts/render_hero_terrain.py <hero.glb> [preset] [out.png]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator import dem_terrain  # noqa: E402

SCENE = r'''
import bpy, math
from mathutils import Vector
# --- DESERT terrain material ---
ob=bpy.data.objects.get("Terrain")
m=bpy.data.materials.new("Desert"); m.use_nodes=True; nt=m.node_tree
bsdf=nt.nodes.get("Principled BSDF"); bsdf.inputs["Roughness"].default_value=0.96
noise=nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value=22.0
ramp=nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color=(0.6,0.42,0.25,1); ramp.color_ramp.elements[1].color=(0.86,0.71,0.47,1)
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
ob.data.materials.clear(); ob.data.materials.append(m)
# --- HERO: orient + azimuth-normalize + scale to ~1.2 m, sit on terrain centre ---
o=bpy.data.objects.get("Hero"); o.rotation_mode="XYZ"; o.rotation_euler=(0,0,math.radians(90)); bpy.context.view_layer.update()
xs0=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys0=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
if (max(xs0)-min(xs0))>(max(ys0)-min(ys0)):
    o.rotation_euler.z+=math.radians(90); bpy.context.view_layer.update()
dz=o.dimensions.z or 1.0; s=1.2/dz; o.scale=(s,s,s); bpy.context.view_layer.update()
# terrain height at origin (centre) via raycast down
hit,loc,nrm,idx,obj,mw = bpy.context.scene.ray_cast(bpy.context.view_layer.depsgraph, Vector((0,0,500)), Vector((0,0,-1)))
ground_z = loc.z if hit else 0.0
zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location=(0,0,ground_z-min(zs)+0.02); bpy.context.view_layer.update()
# tan cheetah-ish material
hm=bpy.data.materials.new("HeroTan"); hm.use_nodes=True
hn=hm.node_tree; hb=hn.nodes.get("Principled BSDF"); hb.inputs["Roughness"].default_value=0.7
sp=hn.nodes.new("ShaderNodeTexNoise"); sp.inputs["Scale"].default_value=80.0
sr=hn.nodes.new("ShaderNodeValToRGB"); sr.color_ramp.elements[0].color=(0.78,0.6,0.32,1); sr.color_ramp.elements[1].color=(0.2,0.13,0.07,1)
sr.color_ramp.elements[0].position=0.55; sr.color_ramp.elements[1].position=0.62
hn.links.new(sp.outputs["Fac"],sr.inputs["Fac"]); hn.links.new(sr.outputs["Color"],hb.inputs["Base Color"])
o.data.materials.clear(); o.data.materials.append(hm)
# --- golden sky + low sun ---
w=bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree
for n in list(wn.nodes): wn.nodes.remove(n)
wo=wn.nodes.new("ShaderNodeOutputWorld"); wb=wn.nodes.new("ShaderNodeBackground")
gd=wn.nodes.new("ShaderNodeTexGradient"); rr=wn.nodes.new("ShaderNodeValToRGB"); mp=wn.nodes.new("ShaderNodeMapping"); tc=wn.nodes.new("ShaderNodeTexCoord")
rr.color_ramp.elements[0].position=0.45; rr.color_ramp.elements[0].color=(0.97,0.74,0.45,1)
rr.color_ramp.elements[1].position=0.62; rr.color_ramp.elements[1].color=(0.5,0.62,0.85,1)
mp.inputs["Rotation"].default_value=(math.radians(90),0,0)
wn.links.new(tc.outputs["Generated"],mp.inputs["Vector"]); wn.links.new(mp.outputs["Vector"],gd.inputs["Vector"])
wn.links.new(gd.outputs["Fac"],rr.inputs["Fac"]); wn.links.new(rr.outputs["Color"],wb.inputs["Color"]); wb.inputs["Strength"].default_value=1.0
wn.links.new(wb.outputs["Background"],wo.inputs["Surface"])
sun=bpy.data.lights.new("Sun",type="SUN"); sun.energy=4.0; sun.color=(1.0,0.78,0.5); sun.angle=math.radians(1.0)
so=bpy.data.objects.new("Sun",sun); bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(68),0,math.radians(118))
# --- CINEMATIC medium shot: close+low on the hero, desert receding behind ---
hz=o.location.z + o.dimensions.z*0.55
cam=bpy.data.cameras.new("Cam"); cam.lens=50.0
co=bpy.data.objects.new("Cam",cam); bpy.context.scene.collection.objects.link(co)
co.location=Vector((2.2,-3.4,hz+0.15)); look=Vector((0,0,hz-0.1))-co.location; co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
cam.dof.use_dof=True; cam.dof.focus_object=o; cam.dof.aperture_fstop=2.8
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=960; sc.render.resolution_y=540
try: sc.view_settings.view_transform="AgX"
except Exception: pass
sc.render.filepath=r"__OUT__"
bpy.ops.render.render(write_still=True)
__result__={"hero_scale":round(s,3),"ground_z":round(ground_z,2)}
'''


def main():
    hero = Path(sys.argv[1]).resolve()
    preset = sys.argv[2] if len(sys.argv) > 2 else "namib_desert"
    out = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else (BACKEND / "renders" / "_hero_terrain.png")
    lat, lon = dem_terrain.TERRAIN_PRESETS[preset]
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})

    class R:
        def run(self, s, o, p, critical=True):
            return registry.call(o, p)
    # Smaller span so the hero reads against gentle foreground relief.
    ext = dem_terrain.build_terrain(R(), lat, lon, BACKEND / "renders",
                                    z=12, crop=80, target_span_m=400.0)
    if not ext:
        print("terrain failed"); return 2
    registry.call("import_mesh_file", {"filepath": str(hero), "name": "Hero", "orientation_fix": None})
    print(registry.call("execute_python", {"code": SCENE.replace("__OUT__", str(out.as_posix()))}), flush=True)
    print("exists:", out.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
