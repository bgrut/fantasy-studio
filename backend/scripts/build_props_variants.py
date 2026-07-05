"""Quality pack 2: TREE VARIANTS (oak / pine / birch) + bush → assets/props/.

Forests stop being 260 copies of one tree: recipes now mix species. Same
shared-library rule as build_props.py — the video dressing pass scatters the
identical files. CPU-only via the headless bridge; our own geometry.
"""
import sys
from pathlib import Path

B = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(B))
from app.mcp import registry, bridge  # noqa: E402

PROPS = str((B / "assets" / "props")).replace("\\", "/")

CODE = r'''
import bpy, math, json, random
OUT=r"__PROPS__"
import os
os.makedirs(OUT, exist_ok=True)
random.seed(23)

def reset():
    bpy.ops.wm.read_homefile(use_empty=True)

def mat(name, color, rough=0.95):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*color,1.0)
    b.inputs["Roughness"].default_value=rough
    return m

def export(name):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=OUT+"/"+name+".glb", use_selection=True, export_yup=True)

made=[]
# ── OAK: thick short trunk, wide lumpy canopy ────────────────────────────────
reset()
bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=0.24, radius2=0.10, depth=1.9, location=(0,0,0.95))
bpy.context.object.data.materials.append(mat("oak_bark",(0.24,0.16,0.10)))
leaves=mat("oak_leaves",(0.14,0.34,0.11))
for i in range(7):
    a=i/7*2*math.pi; r=0.0 if i==0 else random.uniform(0.5,0.85)
    z=2.3+(0.55 if i==0 else random.uniform(-0.2,0.4))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(0.6,0.95),
        location=(math.cos(a)*r, math.sin(a)*r, z))
    s=bpy.context.object; s.scale=(1.0,1.0,random.uniform(0.75,0.9))
    s.data.materials.append(leaves); bpy.ops.object.shade_smooth()
export("tree_oak"); made.append("tree_oak")
# ── PINE: tall slim trunk, 4 stacked cones ───────────────────────────────────
reset()
bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.14, radius2=0.05, depth=3.4, location=(0,0,1.7))
bpy.context.object.data.materials.append(mat("pine_bark",(0.27,0.18,0.11)))
needles=mat("needles",(0.08,0.26,0.12))
for k in range(4):
    z=1.6+k*0.85; r=1.05-k*0.22
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=r, radius2=0.02, depth=1.15, location=(0,0,z))
    c=bpy.context.object; c.data.materials.append(needles); bpy.ops.object.shade_smooth()
export("tree_pine"); made.append("tree_pine")
# ── BIRCH: pale slender trunk, airy light canopy ─────────────────────────────
reset()
bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.11, radius2=0.05, depth=2.9, location=(0,0,1.45))
bpy.context.object.data.materials.append(mat("birch_bark",(0.82,0.80,0.74),rough=0.8))
bl=mat("birch_leaves",(0.32,0.48,0.16))
for i in range(4):
    a=i/4*2*math.pi; r=0.0 if i==0 else random.uniform(0.3,0.5)
    z=3.0+(0.4 if i==0 else random.uniform(-0.1,0.35))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(0.42,0.6),
        location=(math.cos(a)*r, math.sin(a)*r, z))
    s=bpy.context.object; s.data.materials.append(bl); bpy.ops.object.shade_smooth()
export("tree_birch"); made.append("tree_birch")
# ── BUSH: low clustered shrub (fills the mid-ground) ─────────────────────────
reset()
bm=mat("bush_leaves",(0.13,0.30,0.10))
for i in range(5):
    a=i/5*2*math.pi; r=0.0 if i==0 else random.uniform(0.2,0.38)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(0.28,0.45),
        location=(math.cos(a)*r, math.sin(a)*r, random.uniform(0.22,0.42)))
    s=bpy.context.object; s.scale=(1.0,1.0,0.7)
    s.data.materials.append(bm); bpy.ops.object.shade_smooth()
export("bush"); made.append("bush")
__result__=json.dumps({"ok":True,"made":made,"dir":OUT})
'''

bridge.connect(timeout=8)
r = registry.call("execute_python", {"code": CODE.replace("__PROPS__", PROPS)})
print(r.get("result") if isinstance(r, dict) else r)
