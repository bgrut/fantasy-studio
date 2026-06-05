"""Cinematic OSM city / drone shot (no hero). Builds the extruded OSM city and
frames it with an elevated 3/4 drone camera + low golden-hour raking light for
long shadows that separate the buildings. Pure establishing shot.

Usage: python scripts/render_city_cinematic.py [out.png]
"""
import sys
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator import osm_city  # noqa: E402

CODE = r'''
import bpy, json, math, random
from mathutils import Vector
random.seed(7)
data=json.load(open(r"__JP__"))
verts=[]; faces=[]; mat_idx=[]
for b in data["buildings"]:
    fp=b["footprint"]; h=b["height"]; N=len(fp); base=len(verts)
    for (x,y) in fp: verts.append((x,y,0.0))
    for (x,y) in fp: verts.append((x,y,h))
    for i in range(N):
        j=(i+1)%N; faces.append((base+i,base+j,base+N+j,base+N+i))
    faces.append(tuple(base+N+i for i in range(N)))
me=bpy.data.meshes.new("CityMesh"); me.from_pydata(verts,[],faces); me.update()
city=bpy.data.objects.new("City",me); bpy.context.scene.collection.objects.link(city)
# A few concrete tones so the skyline isn't a uniform gray mass.
tones=[(0.55,0.54,0.52),(0.62,0.6,0.57),(0.48,0.48,0.5),(0.66,0.62,0.58),(0.5,0.52,0.55)]
for t in tones:
    m=bpy.data.materials.new("C"); m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF"); bs.inputs["Base Color"].default_value=(t[0],t[1],t[2],1); bs.inputs["Roughness"].default_value=0.9
    me.materials.append(m)
# assign a random tone per building face-group (by polygon, roughly)
for p in me.polygons: p.material_index=random.randrange(len(tones))
xs=[v[0] for v in verts]; ys=[v[1] for v in verts]; zs=[v[2] for v in verts]
cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2; span=max(max(xs)-min(xs),max(ys)-min(ys)); maxh=max(zs)
# ground
bpy.ops.mesh.primitive_plane_add(size=span*5, location=(cx,cy,0)); gp=bpy.context.active_object
gm=bpy.data.materials.new("Ground"); gm.use_nodes=True; gm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.13,0.12,0.12,1); gp.data.materials.append(gm)
# LOW golden-hour sun -> long raking shadows
sun=bpy.data.lights.new("Sun",type="SUN"); sun.energy=4.0; sun.color=(1.0,0.74,0.45); sun.angle=math.radians(1.5)
so=bpy.data.objects.new("Sun",sun); bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(74),0,math.radians(125))
# golden sky gradient world
w=bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree
for n in list(wn.nodes): wn.nodes.remove(n)
out=wn.nodes.new("ShaderNodeOutputWorld"); bgn=wn.nodes.new("ShaderNodeBackground")
grad=wn.nodes.new("ShaderNodeTexGradient"); ramp=wn.nodes.new("ShaderNodeValToRGB")
mapp=wn.nodes.new("ShaderNodeMapping"); texco=wn.nodes.new("ShaderNodeTexCoord")
ramp.color_ramp.elements[0].position=0.35; ramp.color_ramp.elements[0].color=(0.95,0.6,0.32,1)
ramp.color_ramp.elements[1].position=0.62; ramp.color_ramp.elements[1].color=(0.32,0.45,0.72,1)
mapp.inputs["Rotation"].default_value=(math.radians(90),0,0)
wn.links.new(texco.outputs["Generated"],mapp.inputs["Vector"]); wn.links.new(mapp.outputs["Vector"],grad.inputs["Vector"])
wn.links.new(grad.outputs["Fac"],ramp.inputs["Fac"]); wn.links.new(ramp.outputs["Color"],bgn.inputs["Color"])
bgn.inputs["Strength"].default_value=1.1; wn.links.new(bgn.outputs["Background"],out.inputs["Surface"])
# DRONE camera: elevated, 3/4, looking down-across the skyline
cam=bpy.data.cameras.new("Cam"); cam.lens=42.0
co=bpy.data.objects.new("Cam",cam); bpy.context.scene.collection.objects.link(co)
co.location=Vector((cx - span*0.5, cy - span*0.62, maxh*1.5 + span*0.18))
look=Vector((cx + span*0.05, cy + span*0.05, maxh*0.35))-co.location
co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"
sc.render.resolution_x=960; sc.render.resolution_y=540
try: sc.view_settings.view_transform="AgX"
except Exception: pass
try:
    sc.eevee.use_gtao=True; sc.eevee.use_bloom=True
except Exception: pass
sc.render.filepath=r"__OUT__"
bpy.ops.render.render(write_still=True)
__result__={"buildings":len(data["buildings"]),"span":round(span),"maxh":round(maxh)}
'''


def main():
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (BACKEND / "renders" / "_city_cinematic.png")
    data = osm_city.parse_osm(BACKEND / "renders" / "_blosm_cache" / "osm" / "map.osm")
    jp = BACKEND / "renders" / "_city_data.json"
    jp.write_text(json.dumps({"buildings": data["buildings"]}), encoding="utf-8")
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    code = CODE.replace("__JP__", str(jp.as_posix())).replace("__OUT__", str(out.as_posix()))
    print(registry.call("execute_python", {"code": code}), flush=True)
    print("exists:", out.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
