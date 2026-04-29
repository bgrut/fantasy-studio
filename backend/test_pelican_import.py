import bpy
import sys

hero_path = r"C:\Users\bgrut\Desktop\FantasyAI\blender-studio-backend\assets\cache\models\objaverse\2350f17e3ef747d785a42a6811786577.glb"

print("=" * 60)
print(f"Testing import of: {hero_path}")
print("=" * 60)

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

before = set(obj.name for obj in bpy.data.objects)
try:
    bpy.ops.import_scene.gltf(filepath=hero_path)
    print("Import SUCCEEDED")
except Exception as e:
    print(f"Import FAILED: {e}")
    import traceback
    traceback.print_exc()

after = set(obj.name for obj in bpy.data.objects)
new_objs = [bpy.data.objects[n] for n in (after - before)]

print(f"\nImported {len(new_objs)} objects:")
for obj in new_objs:
    print(f"  {obj.name}: type={obj.type}, dims={obj.dimensions}, loc={obj.location}")
    if obj.type == 'MESH' and obj.data:
        print(f"    vertices={len(obj.data.vertices)}, materials={len(obj.data.materials)}")

print("=" * 60)
