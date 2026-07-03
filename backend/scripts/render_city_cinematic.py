"""Cinematic OSM city / drone shot (no hero), now with procedural window facades
(day glass / night emissive windows). Elevated 3/4 drone camera + golden-hour
(day) or blue-hour (night) raking light.

Usage: python scripts/render_city_cinematic.py [day|night] [out.png]
"""
import sys
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator import osm_city  # noqa: E402


def cam_code(night, out):
    if night:
        sun_e, sun_col, elev, azim = 0.6, (0.5, 0.6, 0.9), 30, 200
        sky_lo, sky_hi = (0.06, 0.07, 0.12), (0.01, 0.01, 0.04)
    else:
        sun_e, sun_col, elev, azim = 4.0, (1.0, 0.74, 0.45), 74, 125
        sky_lo, sky_hi = (0.95, 0.6, 0.32), (0.32, 0.45, 0.72)
    return f'''
import bpy, math
from mathutils import Vector
ob=bpy.data.objects.get("OsmCity")
# ground
xs=[(ob.matrix_world@Vector(c)).x for c in ob.bound_box]; ys=[(ob.matrix_world@Vector(c)).y for c in ob.bound_box]; zs=[(ob.matrix_world@Vector(c)).z for c in ob.bound_box]
cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2; span=max(max(xs)-min(xs),max(ys)-min(ys)); maxh=max(zs)
bpy.ops.mesh.primitive_plane_add(size=span*5, location=(cx,cy,0)); gp=bpy.context.active_object
gm=bpy.data.materials.new("Ground"); gm.use_nodes=True; gm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.1,0.1,0.11,1); gp.data.materials.append(gm)
sun=bpy.data.lights.new("Sun",type="SUN"); sun.energy={sun_e}; sun.color=({sun_col[0]},{sun_col[1]},{sun_col[2]}); sun.angle=math.radians(1.5)
so=bpy.data.objects.new("Sun",sun); bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians({elev}),0,math.radians({azim}))
w=bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree
for n in list(wn.nodes): wn.nodes.remove(n)
out=wn.nodes.new("ShaderNodeOutputWorld"); bgn=wn.nodes.new("ShaderNodeBackground")
grad=wn.nodes.new("ShaderNodeTexGradient"); ramp=wn.nodes.new("ShaderNodeValToRGB"); mapp=wn.nodes.new("ShaderNodeMapping"); texco=wn.nodes.new("ShaderNodeTexCoord")
ramp.color_ramp.elements[0].position=0.35; ramp.color_ramp.elements[0].color=({sky_lo[0]},{sky_lo[1]},{sky_lo[2]},1)
ramp.color_ramp.elements[1].position=0.62; ramp.color_ramp.elements[1].color=({sky_hi[0]},{sky_hi[1]},{sky_hi[2]},1)
mapp.inputs["Rotation"].default_value=(math.radians(90),0,0)
wn.links.new(texco.outputs["Generated"],mapp.inputs["Vector"]); wn.links.new(mapp.outputs["Vector"],grad.inputs["Vector"])
wn.links.new(grad.outputs["Fac"],ramp.inputs["Fac"]); wn.links.new(ramp.outputs["Color"],bgn.inputs["Color"])
bgn.inputs["Strength"].default_value=1.0; wn.links.new(bgn.outputs["Background"],out.inputs["Surface"])
cam=bpy.data.cameras.new("Cam"); cam.lens=42.0
co=bpy.data.objects.new("Cam",cam); bpy.context.scene.collection.objects.link(co)
co.location=Vector((cx - span*0.5, cy - span*0.62, maxh*1.5 + span*0.18))
look=Vector((cx + span*0.05, cy + span*0.05, maxh*0.35))-co.location
co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=960; sc.render.resolution_y=540
try: sc.view_settings.view_transform="AgX"
except Exception: pass
try: sc.eevee.use_bloom=True
except Exception: pass
sc.render.filepath=r"{out}"
bpy.ops.render.render(write_still=True)
__result__="rendered"
'''


def main():
    night = (len(sys.argv) > 1 and sys.argv[1] == "night")
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "_city_cinematic.png")
    data = osm_city.parse_osm(BACKEND / "renders" / "_blosm_cache" / "osm" / "map.osm")
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})

    class R:
        def run(self, s, o, p, critical=True):
            return registry.call(o, p)
    ext = osm_city.build_city(R(), data, BACKEND / "renders", night=night)
    print("city:", ext)
    registry.call("execute_python", {"code": cam_code(night, str(out.as_posix()))})
    print("exists:", out.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
