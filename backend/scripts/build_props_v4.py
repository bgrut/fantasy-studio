"""Scenery realism v4 (2026-07-15): REAL-WORLD SCALE trees + building + castle.

v3 trees were ~3.5 m — knee-high next to a wolf, toy-like next to a hunter.
v4: oak ~8 m, pine ~11 m, birch ~7 m, denser displaced crowns with 3-tone
foliage. building.glb gets a window grid + door + roof overhang; NEW
castle.glb: keep + 4 battlement towers + curtain walls + gate.

Standalone: blender --background --python build_props_v4.py
Writes the same filenames games scatter (assets/props/*.glb).
"""
import math
import random
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
    for v in obj.data.vertices:
        p = (obj.matrix_world @ v.co) * freq
        n = noise.noise(Vector((p.x + seed_off, p.y + seed_off, p.z)))
        v.co += v.normal * (n * amp)


def canopy_blob(loc, radius, mtl, squash=0.82, amp=0.2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=radius, location=loc)
    s = bpy.context.object
    s.scale = (1.0, 1.0, squash)
    bpy.ops.object.transform_apply(scale=True)
    displace(s, amp=amp * radius, freq=2.0 / max(radius, 0.3),
             seed_off=random.uniform(0, 40))
    s.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return s


def trunk(height, r_base, r_top, mtl, bend=0.10, verts=12):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r_base, radius2=r_top,
                                    depth=height, location=(0, 0, height / 2))
    t = bpy.context.object
    ba = random.uniform(0, 2 * math.pi)
    for v in t.data.vertices:
        z01 = (v.co.z + height / 2) / height
        v.co.x += math.cos(ba) * bend * height * z01 * z01
        v.co.y += math.sin(ba) * bend * height * z01 * z01
        if z01 < 0.10:
            f = 1.0 + (0.10 - z01) * 5.0
            v.co.x *= f
            v.co.y *= f
    t.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return t


def branch(mtl, z, length, ang, pitch=0.95, r=0.09):
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=r, radius2=0.02, depth=length)
    b = bpy.context.object
    b.rotation_euler = (pitch, 0, ang)
    b.location = (math.cos(ang + math.pi / 2) * length * 0.30,
                  math.sin(ang + math.pi / 2) * length * 0.30, z)
    b.data.materials.append(mtl)
    bpy.ops.object.shade_smooth()
    return b


def export(name):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=OUT + "/" + name + ".glb",
                              use_selection=True, export_yup=True)
    print("WROTE", name)


random.seed(41)

# ── OAK ~8 m: bent trunk, 4 branches, 14-blob 3-tone crown ──────────────────
reset()
bark = mat("oak_bark", (0.21, 0.14, 0.08))
oakA = mat("oak_dark", (0.09, 0.24, 0.07))
oakB = mat("oak_mid", (0.13, 0.32, 0.10))
oakC = mat("oak_lit", (0.20, 0.42, 0.13))
trunk(4.6, 0.45, 0.22, bark, bend=0.12)
for k in range(4):
    branch(bark, z=3.2 + k * 0.5, length=1.8 - k * 0.25,
           ang=k * 1.9 + 0.6, pitch=1.1, r=0.12)
for i in range(14):
    a = i / 14 * 2 * math.pi
    r = 0.0 if i < 2 else random.uniform(0.9, 2.1)
    z = 5.6 + (1.2 if i < 2 else random.uniform(-0.6, 1.1))
    canopy_blob((math.cos(a) * r, math.sin(a) * r, z),
                random.uniform(1.0, 1.7),
                (oakA, oakB, oakC)[i % 3], amp=0.24)
export("tree_oak")

# ── PINE ~11 m: 7 drooping irregular layers, dark-to-lit ────────────────────
reset()
pbark = mat("pine_bark", (0.24, 0.15, 0.09))
trunk(10.5, 0.34, 0.06, pbark, bend=0.04, verts=10)
for k in range(7):
    z = 3.4 + k * 1.15
    r = 3.0 - k * 0.37
    g = 0.17 + k * 0.02
    nm = mat(f"needles{k}", (0.05, g, 0.09))
    bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=r, radius2=0.04,
                                    depth=2.0, location=(0, 0, z))
    c = bpy.context.object
    for v in c.data.vertices:
        if v.co.z < 0:
            rr = math.hypot(v.co.x, v.co.y)
            j = 1.0 + (noise.noise(Vector((v.co.x * 2, v.co.y * 2, k * 9.7))) * 0.20)
            v.co.x *= j
            v.co.y *= j
            v.co.z -= rr * 0.24
    c.rotation_euler = (0, 0, k * 0.55)
    c.data.materials.append(nm)
    bpy.ops.object.shade_smooth()
export("tree_pine")

# ── BIRCH ~7 m: pale banded trunk, airy 3-tone crown ────────────────────────
reset()
bbark = mat("birch_bark", (0.84, 0.82, 0.76), rough=0.8)
band = mat("birch_band", (0.12, 0.11, 0.10))
trunk(6.8, 0.22, 0.09, bbark, bend=0.09, verts=10)
for k in range(6):
    z = 0.9 + k * 0.95
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.215 - k * 0.02,
                                        depth=0.12, location=(0, 0, z))
    bpy.context.object.data.materials.append(band)
bl_a = mat("birch_leaves", (0.26, 0.42, 0.13))
bl_b = mat("birch_lit", (0.40, 0.54, 0.18))
for i in range(8):
    a = i / 8 * 2 * math.pi
    r = 0.0 if i < 2 else random.uniform(0.5, 1.2)
    z = 6.6 + (0.9 if i < 2 else random.uniform(-0.4, 0.9))
    canopy_blob((math.cos(a) * r, math.sin(a) * r, z),
                random.uniform(0.7, 1.1),
                bl_a if i % 2 else bl_b, squash=0.9, amp=0.22)
export("tree_birch")

# ── BUILDING: window grid + door + roof overhang ────────────────────────────
reset()
wall = mat("wall", (0.68, 0.62, 0.54), rough=0.9)
winm = mat("window", (0.30, 0.42, 0.52), rough=0.25)
doorm = mat("door", (0.26, 0.17, 0.10))
roofm = mat("roof", (0.32, 0.16, 0.12))
W, D, H = 7.0, 6.0, 8.5
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, H / 2))
b = bpy.context.object
b.scale = (W, D, H)
bpy.ops.object.transform_apply(scale=True)
b.data.materials.append(wall)
for fy, sy in ((D / 2 + 0.03, 1), (-D / 2 - 0.03, -1)):     # window grids, front/back
    for gx in range(3):
        for gz in range(3):
            bpy.ops.mesh.primitive_cube_add(size=1,
                location=((gx - 1) * 1.9, fy, 2.3 + gz * 2.2))
            w = bpy.context.object
            w.scale = (1.0, 0.06, 1.3)
            bpy.ops.object.transform_apply(scale=True)
            w.data.materials.append(winm)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, D / 2 + 0.04, 1.15))
d = bpy.context.object
d.scale = (1.3, 0.08, 2.3)
bpy.ops.object.transform_apply(scale=True)
d.data.materials.append(doorm)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, H + 0.25))
r = bpy.context.object
r.scale = (W + 0.9, D + 0.9, 0.5)
bpy.ops.object.transform_apply(scale=True)
r.data.materials.append(roofm)
export("building")

# ── CASTLE: keep + 4 towers + battlement walls + gate ───────────────────────
reset()
stone = mat("stone", (0.44, 0.42, 0.39), rough=0.95)
sdark = mat("stone_dark", (0.30, 0.28, 0.26))
roofc = mat("cone_roof", (0.25, 0.28, 0.42))
S = 11.0                                              # wall half-span
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 5.5))   # central keep
k = bpy.context.object
k.scale = (8, 8, 11)
bpy.ops.object.transform_apply(scale=True)
k.data.materials.append(stone)
slit = mat("slit", (0.06, 0.05, 0.05))
for fy, ax in ((4.05, 0), (-4.05, 0), (4.05, 1), (-4.05, 1)):   # keep window slits
    for gx in range(2):
        for gz in range(3):
            loc = ((gx - 0.5) * 3.2, fy, 3.4 + gz * 2.8) if ax == 0 else (fy, (gx - 0.5) * 3.2, 3.4 + gz * 2.8)
            bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
            w = bpy.context.object
            w.scale = (0.45, 0.12, 1.3) if ax == 0 else (0.12, 0.45, 1.3)
            bpy.ops.object.transform_apply(scale=True)
            w.data.materials.append(slit)
for tx, ty in ((S, S), (-S, S), (S, -S), (-S, -S)):   # corner towers
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=2.2, depth=13,
                                        location=(tx, ty, 6.5))
    t = bpy.context.object
    t.data.materials.append(stone)
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=2.7, radius2=0.1,
                                    depth=3.2, location=(tx, ty, 14.6))
    bpy.context.object.data.materials.append(roofc)
    for m in range(8):                                # battlement merlons
        a = m / 8 * 2 * math.pi
        bpy.ops.mesh.primitive_cube_add(size=1,
            location=(tx + math.cos(a) * 2.2, ty + math.sin(a) * 2.2, 13.3))
        mm = bpy.context.object
        mm.scale = (0.55, 0.55, 0.7)
        bpy.ops.object.transform_apply(scale=True)
        mm.data.materials.append(sdark)
for wx, wy, wl, rot in ((0, S, S * 2 - 3, 0), (0, -S, S * 2 - 3, 0),
                        (S, 0, S * 2 - 3, math.pi / 2), (-S, 0, S * 2 - 3, math.pi / 2)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(wx, wy, 4.0))
    w = bpy.context.object
    w.scale = (wl, 1.6, 8.0)
    w.rotation_euler = (0, 0, rot)
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    w.data.materials.append(stone)
    n = int(wl / 1.6)
    for m in range(n):                                # wall-top crenellation
        off = (m - (n - 1) / 2) * 1.6
        lx = wx + (off if rot == 0 else 0)
        ly = wy + (0 if rot == 0 else off)
        if m % 2 == 0:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(lx, ly, 8.5))
            c = bpy.context.object
            c.scale = (0.8 if rot == 0 else 1.7, 1.7 if rot == 0 else 0.8, 1.0)
            bpy.ops.object.transform_apply(scale=True)
            c.data.materials.append(sdark)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, S, 2.4))   # gate
g = bpy.context.object
g.scale = (3.2, 1.8, 4.8)
bpy.ops.object.transform_apply(scale=True)
g.data.materials.append(sdark)
export("castle")

print("PROPS V4 DONE")

# ── STUMP: cut trunk with growth-ring top ───────────────────────────────────
reset()
sbark = mat("wood_bark", (0.24, 0.16, 0.10))
sring = mat("wood_rings", (0.55, 0.42, 0.26), rough=0.85)
bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.42, depth=0.6, location=(0, 0, 0.3))
st = bpy.context.object
for v in st.data.vertices:
    if v.co.z < 0.2:
        f = 1.0 + (0.2 - v.co.z) * 0.6
        v.co.x *= f; v.co.y *= f
st.data.materials.append(sbark)
bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.40, depth=0.04, location=(0, 0, 0.61))
bpy.context.object.data.materials.append(sring)
export("stump")

# ── LOG: fallen trunk, slight taper, moss top ───────────────────────────────
reset()
lbark = mat("wood_bark", (0.26, 0.17, 0.11))
moss = mat("moss_leaves", (0.16, 0.34, 0.12))
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.30, depth=2.6, location=(0, 0, 0.3))
lg = bpy.context.object
lg.rotation_euler = (0, math.radians(90), 0)
bpy.ops.object.transform_apply(rotation=True)
for v in lg.data.vertices:
    v.co.y *= 1.0 + noise.noise(Vector((v.co.x * 2, 0, 0))) * 0.1
lg.data.materials.append(lbark)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.56))
mz = bpy.context.object
mz.scale = (1.1, 0.24, 0.05)
bpy.ops.object.transform_apply(scale=True)
displace(mz, amp=0.05, freq=4.0)
mz.data.materials.append(moss)
export("log")

# ── FLOWERS: grass tuft with colored blossom heads ──────────────────────────
reset()
fstem = mat("flower_stem", (0.20, 0.38, 0.12))
for ci, cc in enumerate(((0.85, 0.25, 0.3), (0.92, 0.78, 0.2), (0.75, 0.5, 0.9))):
    fpet = mat(f"petal{ci}", cc, rough=0.7)
    for k in range(3):
        a = (ci * 3 + k) / 9 * 2 * math.pi
        r = 0.08 + random.uniform(0, 0.22)
        h = 0.22 + random.uniform(0, 0.16)
        bpy.ops.mesh.primitive_cylinder_add(vertices=5, radius=0.012, depth=h,
            location=(math.cos(a) * r, math.sin(a) * r, h / 2))
        bpy.context.object.data.materials.append(fstem)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.05,
            location=(math.cos(a) * r, math.sin(a) * r, h + 0.03))
        bpy.context.object.data.materials.append(fpet)
export("flowers")

# ── MUSHROOM: cluster of 3 toadstools ───────────────────────────────────────
reset()
mstem = mat("mush_stem", (0.85, 0.80, 0.72), rough=0.8)
mcap = mat("mush_cap", (0.62, 0.22, 0.16), rough=0.7)
for k in range(3):
    a = k / 3 * 2 * math.pi
    r = 0.0 if k == 0 else 0.16
    sc = 1.0 if k == 0 else 0.65
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.035 * sc, depth=0.16 * sc,
        location=(math.cos(a) * r, math.sin(a) * r, 0.08 * sc))
    bpy.context.object.data.materials.append(mstem)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.09 * sc,
        location=(math.cos(a) * r, math.sin(a) * r, 0.17 * sc))
    cp = bpy.context.object
    cp.scale = (1, 1, 0.55)
    bpy.ops.object.transform_apply(scale=True)
    cp.data.materials.append(mcap)
    bpy.ops.object.shade_smooth()
export("mushroom")
