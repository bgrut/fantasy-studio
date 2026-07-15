"""Tree quality v3 (2026-07-15 user feedback: "trees can use some work").

Replaces the sphere-blob trees with proper stylized silhouettes:
- noise-DISPLACED canopies (lumpy organic outlines, not smooth ico-balls)
- bent, tapered trunks with a root flare
- visible branch cones reaching into the canopy
- birch bark bands; pine gets 6 drooping irregular layers
- two-tone leaf materials for depth (runtime adds per-instance jitter)

Standalone (no bridge): blender --background --python build_props_v3.py
Writes the SAME filenames games already scatter (assets/props/tree_*.glb, bush).
"""
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector, noise

OUT = str(Path(__file__).resolve().parent.parent / "assets" / "props")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, rough=0.95):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m


def displace(obj, amp=0.16, freq=2.6, seed_off=0.0):
    """Noise-displace along normals — smooth balls become organic lumps."""
    me = obj.data
    for v in me.vertices:
        p = (obj.matrix_world @ v.co) * freq
        n = noise.noise(Vector((p.x + seed_off, p.y + seed_off, p.z)))
        v.co += v.normal * (n * amp)


def canopy_blob(loc, radius, mtl, squash=0.82, amp=0.18):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=loc)
    s = bpy.context.object
    s.scale = (1.0, 1.0, squash)
    bpy.ops.object.transform_apply(scale=True)
    displace(s, amp=amp * radius, freq=2.2 / max(radius, 0.3),
             seed_off=random.uniform(0, 40))
    s.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return s


def trunk(height, r_base, r_top, mtl, bend=0.10, verts=12):
    """Tapered trunk with a gentle bend and a root flare."""
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r_base, radius2=r_top,
                                    depth=height, location=(0, 0, height / 2))
    t = bpy.context.object
    ba = random.uniform(0, 2 * math.pi)
    for v in t.data.vertices:
        z01 = (v.co.z + height / 2) / height          # 0 root -> 1 top
        # bend: quadratic lean that grows with height
        v.co.x += math.cos(ba) * bend * height * z01 * z01
        v.co.y += math.sin(ba) * bend * height * z01 * z01
        # root flare: bottom 12% widens outward
        if z01 < 0.12:
            f = 1.0 + (0.12 - z01) * 4.5
            v.co.x *= f
            v.co.y *= f
    t.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return t


def branch(mtl, z, length, ang, pitch=0.9, r=0.05):
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=r, radius2=0.015, depth=length)
    b = bpy.context.object
    b.rotation_euler = (pitch, 0, ang)
    b.location = (math.cos(ang + math.pi / 2) * length * 0.28,
                  math.sin(ang + math.pi / 2) * length * 0.28, z)
    b.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return b


def export(name):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=OUT + "/" + name + ".glb",
                              use_selection=True, export_yup=True)
    print("WROTE", name)


random.seed(23)

# ── OAK: stout bent trunk, 3 branches, lumpy two-tone crown ─────────────────
reset()
bark = mat("oak_bark", (0.23, 0.15, 0.09))
leaves_a = mat("oak_leaves", (0.13, 0.32, 0.10))
leaves_b = mat("oak_leaves_lit", (0.20, 0.42, 0.13))
trunk(2.1, 0.26, 0.12, bark, bend=0.14)
for k in range(3):
    branch(bark, z=1.5 + k * 0.28, length=0.9 - k * 0.15,
           ang=k * 2.1 + 0.6, pitch=1.05)
for i in range(8):
    a = i / 8 * 2 * math.pi
    r = 0.0 if i == 0 else random.uniform(0.45, 0.85)
    z = 2.45 + (0.6 if i == 0 else random.uniform(-0.25, 0.45))
    canopy_blob((math.cos(a) * r, math.sin(a) * r, z),
                random.uniform(0.55, 0.95),
                leaves_a if i % 3 else leaves_b, amp=0.22)
export("tree_oak")

# ── PINE: tall trunk, 6 drooping irregular layers, dark-to-lit gradient ─────
reset()
pbark = mat("pine_bark", (0.26, 0.17, 0.10))
trunk(3.8, 0.16, 0.04, pbark, bend=0.05, verts=10)
for k in range(6):
    z = 1.35 + k * 0.62
    r = 1.25 - k * 0.175
    g = 0.20 + k * 0.022                              # lighter toward the top
    nm = mat(f"needles{k}", (0.07, g, 0.11))
    bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=r, radius2=0.02,
                                    depth=1.05, location=(0, 0, z))
    c = bpy.context.object
    # irregular rim + droop: pine skirts sag, they aren't party hats
    for v in c.data.vertices:
        if v.co.z < 0:                                # rim verts
            rr = math.hypot(v.co.x, v.co.y)
            j = 1.0 + (noise.noise(Vector((v.co.x * 3, v.co.y * 3, k * 9.7))) * 0.18)
            v.co.x *= j
            v.co.y *= j
            v.co.z -= rr * 0.22                       # droop
    c.rotation_euler = (0, 0, k * 0.5)
    c.data.materials.append(nm)
    bpy.ops.object.shade_smooth()
export("tree_pine")

# ── BIRCH: slender pale trunk with dark bands, airy displaced crown ─────────
reset()
bbark = mat("birch_bark", (0.84, 0.82, 0.76), rough=0.8)
band = mat("birch_band", (0.12, 0.11, 0.10))
trunk(3.1, 0.12, 0.05, bbark, bend=0.10, verts=10)
for k in range(4):                                    # bark bands
    z = 0.5 + k * 0.62
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.118 - k * 0.016,
                                        depth=0.07, location=(0, 0, z))
    bpy.context.object.data.materials.append(band)
bl_a = mat("birch_leaves", (0.30, 0.46, 0.15))
bl_b = mat("birch_leaves_lit", (0.42, 0.56, 0.20))
for i in range(5):
    a = i / 5 * 2 * math.pi
    r = 0.0 if i == 0 else random.uniform(0.28, 0.55)
    z = 3.05 + (0.45 if i == 0 else random.uniform(-0.15, 0.4))
    canopy_blob((math.cos(a) * r, math.sin(a) * r, z),
                random.uniform(0.4, 0.62),
                bl_a if i % 2 else bl_b, squash=0.9, amp=0.2)
export("tree_birch")

# ── BUSH: displaced low shrub ────────────────────────────────────────────────
reset()
bm_a = mat("bush_leaves", (0.12, 0.28, 0.09))
bm_b = mat("bush_leaves_lit", (0.18, 0.36, 0.12))
for i in range(6):
    a = i / 6 * 2 * math.pi
    r = 0.0 if i == 0 else random.uniform(0.18, 0.4)
    canopy_blob((math.cos(a) * r, math.sin(a) * r, random.uniform(0.2, 0.42)),
                random.uniform(0.26, 0.44),
                bm_a if i % 2 else bm_b, squash=0.68, amp=0.2)
export("bush")

print("PROPS V3 DONE")
sys.stdout.flush()
