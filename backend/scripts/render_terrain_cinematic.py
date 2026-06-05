"""Cinematic real-DEM terrain shot. Fetches an elevation tile, builds the
terrain, applies a desert sand/rock material + golden light + drone camera.

Usage: python scripts/render_terrain_cinematic.py [preset] [out.png]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator import dem_terrain  # noqa: E402

MAT_CODE = r'''
import bpy, math
ob=bpy.data.objects.get("Terrain")
# Desert sand/rock material: tan base, slope-darkened rock via geometry, noise.
m=bpy.data.materials.new("Desert"); m.use_nodes=True; nt=m.node_tree
bsdf=nt.nodes.get("Principled BSDF"); bsdf.inputs["Roughness"].default_value=0.95
noise=nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value=18.0
ramp=nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color=(0.62,0.44,0.26,1)   # darker sand
ramp.color_ramp.elements[1].color=(0.85,0.7,0.46,1)    # light sand
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
ob.data.materials.clear(); ob.data.materials.append(m)
# golden sky gradient
w=bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree
for n in list(wn.nodes): wn.nodes.remove(n)
out=wn.nodes.new("ShaderNodeOutputWorld"); bgn=wn.nodes.new("ShaderNodeBackground")
grad=wn.nodes.new("ShaderNodeTexGradient"); rr=wn.nodes.new("ShaderNodeValToRGB")
mp=wn.nodes.new("ShaderNodeMapping"); tc=wn.nodes.new("ShaderNodeTexCoord")
rr.color_ramp.elements[0].position=0.42; rr.color_ramp.elements[0].color=(0.95,0.72,0.45,1)
rr.color_ramp.elements[1].position=0.6; rr.color_ramp.elements[1].color=(0.45,0.6,0.85,1)
mp.inputs["Rotation"].default_value=(math.radians(90),0,0)
wn.links.new(tc.outputs["Generated"],mp.inputs["Vector"]); wn.links.new(mp.outputs["Vector"],grad.inputs["Vector"])
wn.links.new(grad.outputs["Fac"],rr.inputs["Fac"]); wn.links.new(rr.outputs["Color"],bgn.inputs["Color"])
bgn.inputs["Strength"].default_value=1.0; wn.links.new(bgn.outputs["Background"],out.inputs["Surface"])
# low golden sun -> long terrain shadows
sun=bpy.data.lights.new("Sun",type="SUN"); sun.energy=4.2; sun.color=(1.0,0.78,0.5); sun.angle=math.radians(1.0)
so=bpy.data.objects.new("Sun",sun); bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(70),0,math.radians(120))
# drone camera low across the terrain
from mathutils import Vector
zs=[(ob.matrix_world@Vector(c)).z for c in ob.bound_box]
span=max(ob.dimensions.x,ob.dimensions.y); top=max(zs)
cam=bpy.data.cameras.new("Cam"); cam.lens=35.0
co=bpy.data.objects.new("Cam",cam); bpy.context.scene.collection.objects.link(co)
co.location=Vector((-span*0.45, -span*0.55, top+span*0.16)); look=Vector((span*0.1, span*0.15, top*0.4))-co.location
co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"
sc.render.resolution_x=960; sc.render.resolution_y=540
try: sc.view_settings.view_transform="AgX"
except Exception: pass
sc.render.filepath=r"__OUT__"
bpy.ops.render.render(write_still=True)
__result__="rendered"
'''


def main():
    preset = sys.argv[1] if len(sys.argv) > 1 else "vermilion_cliffs"
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "_terrain.png")
    lat, lon = dem_terrain.TERRAIN_PRESETS[preset]
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})

    class R:
        def run(self, s, o, p, critical=True):
            return registry.call(o, p)
    ext = dem_terrain.build_terrain(R(), lat, lon, BACKEND / "renders",
                                    z=12, crop=110, target_span_m=900.0)
    if not ext:
        print("terrain build failed"); return 2
    print("terrain extent:", ext)
    registry.call("execute_python", {"code": MAT_CODE.replace("__OUT__", str(out.as_posix()))})
    print("exists:", out.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
