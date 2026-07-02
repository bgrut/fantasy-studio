"""One-time builder: procedural park props (tree/rock/lamp) → assets/props/*.glb.

SHARED library (docs/game_engine_plan.md shared-enhancement rule): the game
exporter scatters these in playable worlds AND the video composer's dressing
pass imports the same files — one prop set, two backends. CPU-only via the
headless bridge; our own geometry, commercial-safe.
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
random.seed(11)

def reset():
    bpy.ops.wm.read_homefile(use_empty=True)

def mat(name, color, rough=0.9, emit=None):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*color,1.0)
    b.inputs["Roughness"].default_value=rough
    if emit:
        try:
            b.inputs["Emission Color"].default_value=(*emit,1.0)
            b.inputs["Emission Strength"].default_value=6.0
        except Exception: pass
    return m

def export(name):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=OUT+"/"+name+".glb", use_selection=True, export_yup=True)

made=[]
# ── TREE: tapered trunk + clustered canopy, gentle irregularity ─────────────
reset()
bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.16, radius2=0.07, depth=2.2, location=(0,0,1.1))
trunk=bpy.context.object; trunk.data.materials.append(mat("bark",(0.28,0.19,0.12)))
canopy=mat("leaves",(0.16,0.38,0.14),rough=1.0)
for i in range(5):
    a=i/5*2*math.pi; r=0.45 if i else 0.0
    z=2.4+(0.5 if i==0 else random.uniform(-0.15,0.35))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(0.55,0.8),
        location=(math.cos(a)*r, math.sin(a)*r, z))
    s=bpy.context.object; s.data.materials.append(canopy)
    bpy.ops.object.shade_smooth()
export("tree"); made.append("tree")
# ── ROCK: displaced icosphere ────────────────────────────────────────────────
reset()
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.5, location=(0,0,0.32))
rock=bpy.context.object; rock.scale=(1.3,1.0,0.65)
d=rock.modifiers.new("d","DISPLACE"); t=bpy.data.textures.new("n","VORONOI"); t.noise_scale=0.55
d.texture=t; d.strength=0.35
bpy.ops.object.modifier_apply(modifier="d")
rock.data.materials.append(mat("stone",(0.42,0.41,0.38),rough=1.0))
bpy.ops.object.shade_smooth()
export("rock"); made.append("rock")
# ── LAMP: pole + emissive head (night scenes glow) ───────────────────────────
reset()
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.05, depth=3.4, location=(0,0,1.7))
pole=bpy.context.object; pole.data.materials.append(mat("iron",(0.08,0.08,0.09),rough=0.5))
bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.16, location=(0,0,3.5))
head=bpy.context.object; head.data.materials.append(mat("bulb",(1.0,0.93,0.75),rough=0.3,emit=(1.0,0.9,0.7)))
export("lamp"); made.append("lamp")
__result__=json.dumps({"ok":True,"made":made,"dir":OUT})
'''

bridge.connect(timeout=8)
r = registry.call("execute_python", {"code": CODE.replace("__PROPS__", PROPS)})
print(r.get("result") if isinstance(r, dict) else r)
