import sys, math
import bpy
from mathutils import Matrix, Vector
argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_glb = argv[0], argv[1]
rx, ry, rz = float(argv[2]), float(argv[3]), float(argv[4])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
R = (Matrix.Rotation(math.radians(rz),4,'Z') @ Matrix.Rotation(math.radians(ry),4,'Y')
     @ Matrix.Rotation(math.radians(rx),4,'X'))
for o in bpy.data.objects:
    if o.parent is None:
        o.matrix_world = R @ o.matrix_world
bpy.context.view_layer.update()
zmin = min((o.matrix_world @ Vector(c)).z for o in bpy.data.objects if o.type=="MESH" for c in o.bound_box)
for o in bpy.data.objects:
    if o.parent is None:
        o.matrix_world = Matrix.Translation((0,0,-zmin)) @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=out_glb, export_yup=True, export_apply=False)
print("APPLIED", rx, ry, rz)
