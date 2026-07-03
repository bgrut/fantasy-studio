import sys, glob
from pathlib import Path
B=Path("C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend"); sys.path.insert(0,str(B))
from app.mcp import registry, bridge
from app.orchestrator import motion_rig, composer
bridge.connect(timeout=5); registry.call("reset_scene",{})
registry.call("import_mesh_file",{"filepath":str(B/"renders/anim_20260612_143453_a_man_walking_his_dog_through_a_park/asset_1434533722.glb"),
 "name":"Hero","normalize_size":1.75,"ground_to_z0":True,"join":True,"orientation_fix":None})
class R:
    def run(self,s,o,p,critical=True): return registry.call(o,p)
registry.call("execute_python",{"code":r'''
import bpy, math
from mathutils import Vector
o=bpy.data.objects.get("Hero"); o.rotation_mode='XYZ'; bpy.context.view_layer.update()
xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
if (max(xs)-min(xs))>(max(ys)-min(ys)):
    o.rotation_euler.z+=math.radians(90.0); bpy.context.view_layer.update()
__result__="az"
'''})
refpng = glob.glob(str(B/"renders/anim_20260612_143453_a_man_walking_his_dog_through_a_park/reference_*.png"))[0]
composer._orient_hero_by_reference(R(),"Hero",refpng,B/"renders",min_iou=0.0,wheels_down=False,
        candidates=[(0,0,0),(180,0,0),(0,180,0),(0,0,180)],verbose=False)
# DOG: import + stage + gait (exact e2e order)
dog = sorted(glob.glob(str(B/"renders/_actor_cache/*.glb")))[0]
registry.call("import_mesh_file",{"filepath":dog,"name":"Actor2","normalize_size":1.0,"ground_to_z0":True,"join":True,"orientation_fix":None})
stage = composer._ACTOR_STAGE_CODE.replace("__HERO__","Hero").replace("__ACTOR__","Actor2")
registry.call("execute_python",{"code":stage})
motion_rig.build_skeletal_gait(R(),"Actor2","quadruped",28,24,track_camera=False,verbose=False)
# MAN gait
code = (motion_rig._BIPED_GAIT.replace("__HERO__","Hero").replace("__TOTAL__","28")
        .replace("__STRIDE__","28").replace("__TRACK__","False").replace("__FPSV__","24").replace("__WIDE__","1.0"))
r = registry.call("execute_python",{"code":code})
print("man rig:", str(r)[:220])
registry.call("execute_python",{"code":r'''
import bpy, math
from mathutils import Vector
sun=bpy.data.lights.new("S",type="SUN"); sun.energy=4; so=bpy.data.objects.new("S",sun)
bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(55),0,math.radians(35))
cam=bpy.data.cameras.new("C"); cam.lens=45; co=bpy.data.objects.new("C",cam); bpy.context.scene.collection.objects.link(co)
sc=bpy.context.scene; sc.camera=co; sc.render.engine="BLENDER_EEVEE"
sc.render.resolution_x=720; sc.render.resolution_y=540
sc.frame_set(15)
co.location=Vector((0.6,-3.6,1.0)); look=Vector((0.6,0,0.8))-co.location
co.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
sc.render.filepath=r"C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend/renders/_order_f15.png"
bpy.ops.render.render(write_still=True)
__result__="ok"
'''})
print("rendered")
