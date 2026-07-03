"""Prototype a cinematic hero-in-city shot: hero in the foreground, OSM skyline
clearly behind, low wide camera, atmospheric haze. Validates the framing/balance
before wiring into the composer.

Usage: python scripts/city_scene_test.py <hero.glb> [out.png]
"""
import sys
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402
from app.orchestrator import osm_city  # noqa: E402


def main():
    hero = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "_cityscene.png")
    if not hero or not hero.exists():
        print("ERROR: pass a hero .glb", file=sys.stderr); return 2

    osm = BACKEND / "renders" / "_blosm_cache" / "osm" / "map.osm"
    data = osm_city.parse_osm(osm)
    jp = BACKEND / "renders" / "_city_data.json"
    jp.write_text(json.dumps({"buildings": data["buildings"]}), encoding="utf-8")

    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {"filepath": str(hero), "name": "Hero", "orientation_fix": None})

    code = CODE.replace("__JP__", str(jp.as_posix())).replace("__OUT__", str(out.as_posix()))
    print(registry.call("execute_python", {"code": code}), flush=True)
    print("exists:", out.exists())
    return 0


CODE = r'''
import bpy, json, math
from mathutils import Vector
o=bpy.data.objects.get("Hero"); o.rotation_mode="XYZ"
o.rotation_euler=(0,0,math.radians(90)); bpy.context.view_layer.update()
xs0=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys0=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
if (max(xs0)-min(xs0))>(max(ys0)-min(ys0)):
    o.rotation_euler.z+=math.radians(90); bpy.context.view_layer.update()
dz=o.dimensions.z or 1.0; s=0.8/dz; o.scale=(s,s,s); bpy.context.view_layer.update()
zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location=(0,0,-min(zs)); bpy.context.view_layer.update()
hm=bpy.data.materials.new("HeroBrown"); hm.use_nodes=True
hm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.33,0.2,0.11,1)
o.data.materials.clear(); o.data.materials.append(hm)
data=json.load(open(r"__JP__"))
verts=[]; faces=[]
for b in data["buildings"]:
    fp=b["footprint"]; h=b["height"]; N=len(fp); base=len(verts)
    for (x,y) in fp: verts.append((x,y,0.0))
    for (x,y) in fp: verts.append((x,y,h))
    for i in range(N):
        j=(i+1)%N; faces.append((base+i,base+j,base+N+j,base+N+i))
    faces.append(tuple(base+N+i for i in range(N)))
me=bpy.data.meshes.new("CityMesh"); me.from_pydata(verts,[],faces); me.update()
city=bpy.data.objects.new("City",me); bpy.context.scene.collection.objects.link(city)
cm=bpy.data.materials.new("Concrete"); cm.use_nodes=True
cb=cm.node_tree.nodes.get("Principled BSDF"); cb.inputs["Base Color"].default_value=(0.5,0.5,0.52,1); cb.inputs["Roughness"].default_value=0.9
me.materials.append(cm)
cy_min=min(v[1] for v in verts); cx_mid=(min(v[0] for v in verts)+max(v[0] for v in verts))/2
# Bring the city's NEAR edge to ~10 m behind the hero so buildings loom large.
city.location.x=-cx_mid; city.location.y=10.0-cy_min; bpy.context.view_layer.update()
bpy.ops.mesh.primitive_plane_add(size=4000, location=(0,200,0)); gp=bpy.context.active_object
gm=bpy.data.materials.new("Street"); gm.use_nodes=True; gm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.16,0.16,0.18,1); gp.data.materials.append(gm)
# Golden-hour key (strong, low, raking for long building shadows) + soft fill.
sun=bpy.data.lights.new("Sun",type="SUN"); sun.energy=4.5; sun.color=(1.0,0.78,0.52); sun.angle=math.radians(2)
so=bpy.data.objects.new("Sun",sun); bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(62),0,math.radians(115))
w=bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree
bg=wn.nodes.get("Background"); bg.inputs[0].default_value=(0.62,0.7,0.82,1); bg.inputs[1].default_value=1.3
# Atmospheric haze via Mist pass mixed in post would be ideal; for now a bright
# hazy sky + distance-fading handled by a large faint fog plane is omitted to
# avoid EEVEE world-volume black-render quirks. Depth still reads via the sky.
cam=bpy.data.cameras.new("Cam"); cam.lens=28.0
co=bpy.data.objects.new("Cam",cam); bpy.context.scene.collection.objects.link(co)
# Close + low, slight up-tilt: hero fills the foreground, skyline rises behind.
co.location=Vector((0.65,-1.35,0.42)); look=Vector((0,0.15,0.5))-co.location; co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=640; sc.render.resolution_y=400
try: sc.view_settings.view_transform="AgX"
except Exception: pass
try: sc.eevee.use_volumetric_lights=True
except Exception: pass
sc.render.filepath=r"__OUT__"
bpy.ops.render.render(write_still=True)
__result__={"buildings":len(data["buildings"]),"hero_scale":round(s,3)}
'''

if __name__ == "__main__":
    sys.exit(main())
