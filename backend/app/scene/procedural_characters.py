"""
procedural_characters.py
========================
Primitive-based stand-in characters used when the asset pipeline
couldn't find a real 3D model for the subject. Better-than-empty
fallback: a stylized, recognizable silhouette so the viewer immediately
understands "this is the chef / horse / eagle / robot" even if the mesh
is a collection of cubes and spheres.

Classifications are keyword-driven and intentionally loose — the goal
is a confident guess, not a perfect match. The stand-in inherits:
  - A subject-appropriate material palette
  - A body plan that matches the subject category
  - A scale consistent with layout_ops.SCALE_CLASS_SIZE

All objects are named with an ``hero_proc_`` prefix so downstream
helpers (framing guarantor, lighting booster) recognize them as hero
geometry, NOT environment.

Intentionally Blender-only: imports ``bpy`` at call-time and never
raises to caller — any failure returns [] and the caller falls back to
the branded placeholder cube.
"""
from __future__ import annotations

from math import pi, cos, sin


# ═════════════════════════════════════════════════════════════════════════
# Subject classification
# ═════════════════════════════════════════════════════════════════════════

# Keyword → body plan category. First match wins (longest-key first).
_SUBJECT_TO_PLAN: dict[str, str] = {
    # Humanoids (people + occupations)
    "chef": "humanoid_chef",
    "cook": "humanoid_chef",
    "baker": "humanoid_chef",
    "ninja": "humanoid_ninja",
    "astronaut": "humanoid_astronaut",
    "knight": "humanoid_knight",
    "soldier": "humanoid_soldier",
    "pirate": "humanoid_pirate",
    "wizard": "humanoid_wizard",
    "dancer": "humanoid_default",
    "musician": "humanoid_default",
    "athlete": "humanoid_default",
    "doctor": "humanoid_default",
    "man": "humanoid_default",
    "woman": "humanoid_default",
    "person": "humanoid_default",
    "character": "humanoid_default",

    # Robots / sci-fi
    "robot": "robot",
    "android": "robot",
    "mech": "robot",
    "cyborg": "robot",
    "droid": "robot",
    "alien": "alien",

    # Quadrupeds
    "horse": "quadruped_large",
    "stallion": "quadruped_large",
    "pony": "quadruped_small",
    "cow": "quadruped_large",
    "bull": "quadruped_large",
    "dog": "quadruped_medium",
    "cat": "quadruped_small",
    "wolf": "quadruped_medium",
    "fox": "quadruped_small",
    "bear": "quadruped_large",
    "tiger": "quadruped_medium",
    "lion": "quadruped_medium",
    "deer": "quadruped_medium",
    "elephant": "quadruped_xlarge",
    "rhino": "quadruped_xlarge",
    "giraffe": "quadruped_xlarge",

    # Birds
    "eagle": "bird_large",
    "hawk": "bird_large",
    "falcon": "bird_medium",
    "owl": "bird_medium",
    "parrot": "bird_medium",
    "crow": "bird_small",
    "raven": "bird_small",
    "bird": "bird_medium",
    "dragon": "dragon",

    # Aquatic
    "dolphin": "aquatic_streamlined",
    "whale": "aquatic_streamlined",
    "shark": "aquatic_streamlined",
    "fish": "aquatic_streamlined",
    "octopus": "aquatic_blob",

    # Vehicles
    "ferrari": "vehicle_sports",
    "lamborghini": "vehicle_sports",
    "porsche": "vehicle_sports",
    "sports car": "vehicle_sports",
    "car": "vehicle_sedan",
    "truck": "vehicle_truck",
    "motorcycle": "vehicle_bike",
    "bike": "vehicle_bike",
    "plane": "vehicle_plane",
    "airplane": "vehicle_plane",
    "helicopter": "vehicle_helicopter",
    "spaceship": "vehicle_spaceship",
    "boat": "vehicle_boat",
    "ship": "vehicle_boat",

    # Food / weird
    "pickle": "food_elongated",
    "donut": "food_ring",
    "pizza": "food_flat",
    "burger": "food_stack",
}

# Palette per plan — (base_color RGB, metallic, roughness).
_PALETTE: dict[str, tuple[tuple[float, float, float], float, float]] = {
    "humanoid_default":   ((0.35, 0.42, 0.55), 0.05, 0.6),
    "humanoid_chef":      ((0.95, 0.95, 0.95), 0.0, 0.55),   # chef's whites
    "humanoid_ninja":     ((0.10, 0.10, 0.12), 0.05, 0.4),
    "humanoid_astronaut": ((0.92, 0.92, 0.95), 0.15, 0.35),
    "humanoid_knight":    ((0.70, 0.72, 0.78), 0.85, 0.22),
    "humanoid_soldier":   ((0.30, 0.35, 0.22), 0.0, 0.6),    # fatigues
    "humanoid_pirate":    ((0.35, 0.22, 0.18), 0.0, 0.55),
    "humanoid_wizard":    ((0.25, 0.15, 0.45), 0.05, 0.45),
    "robot":              ((0.55, 0.6, 0.65), 0.9, 0.18),
    "alien":              ((0.2, 0.85, 0.45), 0.25, 0.35),
    "quadruped_small":    ((0.55, 0.45, 0.3), 0.0, 0.6),
    "quadruped_medium":   ((0.45, 0.32, 0.2), 0.0, 0.6),
    "quadruped_large":    ((0.3, 0.22, 0.14), 0.0, 0.65),
    "quadruped_xlarge":   ((0.4, 0.4, 0.4), 0.0, 0.7),
    "bird_small":         ((0.12, 0.12, 0.12), 0.0, 0.5),
    "bird_medium":        ((0.45, 0.3, 0.15), 0.0, 0.55),
    "bird_large":         ((0.25, 0.18, 0.1), 0.0, 0.55),
    "dragon":             ((0.6, 0.15, 0.12), 0.25, 0.3),
    "aquatic_streamlined": ((0.25, 0.45, 0.65), 0.1, 0.3),
    "aquatic_blob":       ((0.6, 0.25, 0.45), 0.05, 0.4),
    "vehicle_sports":     ((0.85, 0.05, 0.05), 0.85, 0.12),   # Ferrari red
    "vehicle_sedan":      ((0.18, 0.22, 0.3), 0.6, 0.2),
    "vehicle_truck":      ((0.2, 0.35, 0.25), 0.2, 0.45),
    "vehicle_bike":       ((0.15, 0.15, 0.15), 0.7, 0.2),
    "vehicle_plane":      ((0.9, 0.9, 0.9), 0.6, 0.25),
    "vehicle_helicopter": ((0.3, 0.4, 0.25), 0.4, 0.3),
    "vehicle_spaceship":  ((0.55, 0.6, 0.7), 0.95, 0.1),
    "vehicle_boat":       ((0.9, 0.9, 0.9), 0.1, 0.4),
    "food_elongated":     ((0.25, 0.6, 0.15), 0.0, 0.35),
    "food_ring":          ((0.92, 0.78, 0.55), 0.0, 0.45),
    "food_flat":          ((0.88, 0.65, 0.3), 0.0, 0.5),
    "food_stack":         ((0.5, 0.3, 0.15), 0.0, 0.55),
}


def _classify_subject(subject: str) -> str:
    """Pick a body plan for the subject string. Default = humanoid."""
    if not subject:
        return "humanoid_default"
    text = str(subject).lower()
    # Longest-match first so "sports car" beats "car".
    for key in sorted(_SUBJECT_TO_PLAN, key=len, reverse=True):
        if key in text:
            return _SUBJECT_TO_PLAN[key]
    return "humanoid_default"


# ═════════════════════════════════════════════════════════════════════════
# Material helper
# ═════════════════════════════════════════════════════════════════════════

def _make_material(bpy, plan: str, name: str):
    """Create a principled BSDF material from the plan's palette."""
    palette = _PALETTE.get(plan, _PALETTE["humanoid_default"])
    color, metallic, roughness = palette
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            bsdf.inputs["Metallic"].default_value = metallic
            bsdf.inputs["Roughness"].default_value = roughness
    except Exception:
        pass
    return mat


def _set_material(obj, mat):
    if not obj or not mat:
        return
    if obj.data is None or not hasattr(obj.data, "materials"):
        return
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def _add_cube(bpy, name, loc, scale):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return obj


def _add_sphere(bpy, name, loc, scale):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return obj


def _add_cyl(bpy, name, loc, scale):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return obj


# ═════════════════════════════════════════════════════════════════════════
# Body-plan builders — each returns list of created root objects
# ═════════════════════════════════════════════════════════════════════════

def _build_humanoid(bpy, mat, name_prefix: str, accent_mat=None) -> list:
    """Simple humanoid: torso + head + 2 arms + 2 legs (all cubes)."""
    objs = []
    # Torso
    torso = _add_cube(bpy, f"{name_prefix}_torso", (0, 0, 1.1), (0.45, 0.25, 0.6))
    _set_material(torso, mat)
    objs.append(torso)
    # Head
    head = _add_sphere(bpy, f"{name_prefix}_head", (0, 0, 1.75), (0.22, 0.22, 0.22))
    _set_material(head, accent_mat or mat)
    objs.append(head)
    # Arms
    for side, x in (("L", -0.55), ("R", 0.55)):
        arm = _add_cube(bpy, f"{name_prefix}_arm_{side}", (x, 0, 1.1), (0.12, 0.12, 0.55))
        _set_material(arm, mat)
        objs.append(arm)
    # Legs
    for side, x in (("L", -0.2), ("R", 0.2)):
        leg = _add_cube(bpy, f"{name_prefix}_leg_{side}", (x, 0, 0.35), (0.16, 0.16, 0.7))
        _set_material(leg, mat)
        objs.append(leg)
    return objs


def _build_humanoid_chef(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "humanoid_chef", f"{prefix}_mat")
    skin = _make_material(bpy, "humanoid_default", f"{prefix}_skin")
    # Override skin to a warm tone
    try:
        bsdf = skin.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.95, 0.78, 0.65, 1.0)
    except Exception:
        pass
    objs = _build_humanoid(bpy, mat, prefix, accent_mat=skin)
    # Chef's hat: tall cylinder on head
    hat = _add_cyl(bpy, f"{prefix}_hat", (0, 0, 2.15), (0.22, 0.22, 0.35))
    _set_material(hat, mat)
    objs.append(hat)
    return objs


def _build_humanoid_ninja(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "humanoid_ninja", f"{prefix}_mat")
    return _build_humanoid(bpy, mat, prefix)


def _build_robot(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "robot", f"{prefix}_mat")
    accent = _make_material(bpy, "alien", f"{prefix}_eye")  # green "eye"
    objs = []
    # Boxy torso
    torso = _add_cube(bpy, f"{prefix}_torso", (0, 0, 1.1), (0.55, 0.35, 0.7))
    _set_material(torso, mat)
    objs.append(torso)
    # Head: boxy
    head = _add_cube(bpy, f"{prefix}_head", (0, 0, 1.85), (0.35, 0.3, 0.3))
    _set_material(head, mat)
    objs.append(head)
    # Eye: small glowing sphere
    eye = _add_sphere(bpy, f"{prefix}_eye", (0, -0.25, 1.85), (0.07, 0.07, 0.07))
    _set_material(eye, accent)
    objs.append(eye)
    # Cylindrical arms
    for side, x in (("L", -0.65), ("R", 0.65)):
        arm = _add_cyl(bpy, f"{prefix}_arm_{side}", (x, 0, 1.1), (0.14, 0.14, 0.65))
        _set_material(arm, mat)
        objs.append(arm)
    # Cylindrical legs
    for side, x in (("L", -0.22), ("R", 0.22)):
        leg = _add_cyl(bpy, f"{prefix}_leg_{side}", (x, 0, 0.4), (0.18, 0.18, 0.8))
        _set_material(leg, mat)
        objs.append(leg)
    return objs


def _build_quadruped(bpy, prefix: str, plan: str, body_scale=1.0) -> list:
    mat = _make_material(bpy, plan, f"{prefix}_mat")
    objs = []
    # Body: elongated ellipsoid
    body = _add_sphere(bpy, f"{prefix}_body", (0, 0, 0.8 * body_scale),
                       (0.8 * body_scale, 0.4 * body_scale, 0.35 * body_scale))
    _set_material(body, mat)
    objs.append(body)
    # Head: smaller sphere forward
    head = _add_sphere(bpy, f"{prefix}_head", (0.9 * body_scale, 0, 0.95 * body_scale),
                       (0.25 * body_scale, 0.22 * body_scale, 0.22 * body_scale))
    _set_material(head, mat)
    objs.append(head)
    # 4 legs (cylinders) at body corners
    for (nm, x, y) in (
        ("fl", 0.55, -0.3), ("fr", 0.55, 0.3),
        ("bl", -0.55, -0.3), ("br", -0.55, 0.3),
    ):
        leg = _add_cyl(bpy, f"{prefix}_leg_{nm}",
                       (x * body_scale, y * body_scale, 0.35 * body_scale),
                       (0.09 * body_scale, 0.09 * body_scale, 0.7 * body_scale))
        _set_material(leg, mat)
        objs.append(leg)
    # Tail
    tail = _add_cyl(bpy, f"{prefix}_tail",
                    (-0.95 * body_scale, 0, 0.9 * body_scale),
                    (0.05 * body_scale, 0.05 * body_scale, 0.35 * body_scale))
    tail.rotation_euler = (0, pi / 2.5, 0)
    _set_material(tail, mat)
    objs.append(tail)
    return objs


def _build_bird(bpy, prefix: str, plan: str, scale=1.0) -> list:
    mat = _make_material(bpy, plan, f"{prefix}_mat")
    objs = []
    # Body
    body = _add_sphere(bpy, f"{prefix}_body", (0, 0, 3.0),
                       (0.55 * scale, 0.3 * scale, 0.3 * scale))
    _set_material(body, mat)
    objs.append(body)
    # Head
    head = _add_sphere(bpy, f"{prefix}_head", (0.5 * scale, 0, 3.25),
                       (0.18 * scale, 0.18 * scale, 0.18 * scale))
    _set_material(head, mat)
    objs.append(head)
    # Beak (small cone-ish)
    beak = _add_cube(bpy, f"{prefix}_beak", (0.72 * scale, 0, 3.2),
                     (0.12 * scale, 0.06 * scale, 0.06 * scale))
    beak_mat = _make_material(bpy, "food_ring", f"{prefix}_beak_mat")
    _set_material(beak, beak_mat)
    objs.append(beak)
    # Wings — two angled flat planes
    for side, y_sign in (("L", -1), ("R", 1)):
        wing = _add_cube(bpy, f"{prefix}_wing_{side}",
                         (0, y_sign * 0.55 * scale, 3.0),
                         (0.4 * scale, 0.6 * scale, 0.04 * scale))
        wing.rotation_euler = (0, 0, y_sign * 0.3)
        _set_material(wing, mat)
        objs.append(wing)
    return objs


def _build_dragon(bpy, prefix: str) -> list:
    # Same body-plan as bird but bigger & meaner colors; add horns.
    mat = _make_material(bpy, "dragon", f"{prefix}_mat")
    objs = []
    body = _add_sphere(bpy, f"{prefix}_body", (0, 0, 2.5), (1.2, 0.55, 0.6))
    _set_material(body, mat)
    objs.append(body)
    head = _add_sphere(bpy, f"{prefix}_head", (1.15, 0, 2.9), (0.35, 0.3, 0.28))
    _set_material(head, mat)
    objs.append(head)
    for side, y_sign in (("L", -1), ("R", 1)):
        wing = _add_cube(bpy, f"{prefix}_wing_{side}", (0, y_sign * 1.1, 2.8),
                         (0.8, 1.4, 0.05))
        wing.rotation_euler = (0, 0, y_sign * 0.35)
        _set_material(wing, mat)
        objs.append(wing)
    # Horns
    for side, x_off in (("L", -0.08), ("R", 0.08)):
        horn = _add_cube(bpy, f"{prefix}_horn_{side}",
                         (1.35 + x_off, x_off * 2, 3.1),
                         (0.04, 0.04, 0.22))
        _set_material(horn, mat)
        objs.append(horn)
    return objs


def _build_aquatic_streamlined(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "aquatic_streamlined", f"{prefix}_mat")
    objs = []
    # Main elongated body
    body = _add_sphere(bpy, f"{prefix}_body", (0, 0, 1.5), (1.2, 0.32, 0.4))
    _set_material(body, mat)
    objs.append(body)
    # Tail fin — flat cube angled up
    tail = _add_cube(bpy, f"{prefix}_tail", (-1.25, 0, 1.5), (0.08, 0.6, 0.35))
    _set_material(tail, mat)
    objs.append(tail)
    # Dorsal fin
    fin = _add_cube(bpy, f"{prefix}_fin", (0, 0, 1.95), (0.4, 0.05, 0.28))
    _set_material(fin, mat)
    objs.append(fin)
    return objs


def _build_vehicle_sports(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "vehicle_sports", f"{prefix}_mat")
    glass = _make_material(bpy, "humanoid_default", f"{prefix}_glass")
    try:
        bsdf = glass.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.05, 0.07, 0.1, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.05
        bsdf.inputs["Metallic"].default_value = 0.1
    except Exception:
        pass
    wheel_mat = _make_material(bpy, "humanoid_ninja", f"{prefix}_wheel")
    objs = []
    # Main chassis — long flat cube
    chassis = _add_cube(bpy, f"{prefix}_chassis", (0, 0, 0.55), (2.4, 1.0, 0.25))
    _set_material(chassis, mat)
    objs.append(chassis)
    # Cabin — shorter on top
    cabin = _add_cube(bpy, f"{prefix}_cabin", (0, 0, 0.95), (1.2, 0.9, 0.3))
    _set_material(cabin, glass)
    objs.append(cabin)
    # 4 wheels
    for (nm, x, y) in (
        ("fl", 1.25, -0.55), ("fr", 1.25, 0.55),
        ("rl", -1.25, -0.55), ("rr", -1.25, 0.55),
    ):
        wheel = _add_cyl(bpy, f"{prefix}_wheel_{nm}", (x, y, 0.35),
                         (0.4, 0.4, 0.25))
        wheel.rotation_euler = (pi / 2, 0, 0)
        _set_material(wheel, wheel_mat)
        objs.append(wheel)
    return objs


def _build_vehicle_generic(bpy, prefix: str, plan: str) -> list:
    """Bigger/simpler chassis for sedan/truck/bike."""
    mat = _make_material(bpy, plan, f"{prefix}_mat")
    objs = []
    if plan == "vehicle_bike":
        body = _add_cube(bpy, f"{prefix}_body", (0, 0, 0.7), (1.2, 0.2, 0.25))
        _set_material(body, mat)
        objs.append(body)
        for (nm, x) in (("f", 0.9), ("r", -0.9)):
            w = _add_cyl(bpy, f"{prefix}_wheel_{nm}", (x, 0, 0.4), (0.45, 0.45, 0.15))
            w.rotation_euler = (pi / 2, 0, 0)
            _set_material(w, mat)
            objs.append(w)
        return objs
    # sedan / truck
    chassis = _add_cube(bpy, f"{prefix}_chassis", (0, 0, 0.7), (2.2, 1.1, 0.4))
    _set_material(chassis, mat)
    objs.append(chassis)
    cabin = _add_cube(bpy, f"{prefix}_cabin", (0.1, 0, 1.15), (1.4, 1.0, 0.45))
    _set_material(cabin, mat)
    objs.append(cabin)
    wheel_mat = _make_material(bpy, "humanoid_ninja", f"{prefix}_wheel")
    for (nm, x, y) in (
        ("fl", 1.15, -0.65), ("fr", 1.15, 0.65),
        ("rl", -1.15, -0.65), ("rr", -1.15, 0.65),
    ):
        w = _add_cyl(bpy, f"{prefix}_wheel_{nm}", (x, y, 0.4), (0.42, 0.42, 0.22))
        w.rotation_euler = (pi / 2, 0, 0)
        _set_material(w, wheel_mat)
        objs.append(w)
    return objs


def _build_vehicle_plane(bpy, prefix: str) -> list:
    mat = _make_material(bpy, "vehicle_plane", f"{prefix}_mat")
    objs = []
    body = _add_cyl(bpy, f"{prefix}_fuselage", (0, 0, 2.5), (0.35, 0.35, 2.2))
    body.rotation_euler = (pi / 2, 0, 0)
    _set_material(body, mat)
    objs.append(body)
    wings = _add_cube(bpy, f"{prefix}_wings", (0, 0, 2.5), (0.15, 2.8, 0.08))
    _set_material(wings, mat)
    objs.append(wings)
    tail = _add_cube(bpy, f"{prefix}_tail", (0, -1.8, 2.7), (0.08, 0.5, 0.45))
    _set_material(tail, mat)
    objs.append(tail)
    return objs


def _build_food(bpy, prefix: str, plan: str) -> list:
    mat = _make_material(bpy, plan, f"{prefix}_mat")
    if plan == "food_elongated":  # pickle-shape
        obj = _add_sphere(bpy, f"{prefix}_body", (0, 0, 1.0), (1.5, 0.35, 0.35))
        _set_material(obj, mat)
        return [obj]
    if plan == "food_ring":  # donut
        try:
            bpy.ops.mesh.primitive_torus_add(
                location=(0, 0, 0.5),
                major_radius=0.8, minor_radius=0.3,
            )
            obj = bpy.context.object
            obj.name = f"{prefix}_body"
            _set_material(obj, mat)
            return [obj]
        except Exception:
            pass
    if plan == "food_flat":  # pizza
        obj = _add_cyl(bpy, f"{prefix}_body", (0, 0, 0.08), (1.0, 1.0, 0.08))
        _set_material(obj, mat)
        return [obj]
    # food_stack (burger) — three layers
    objs = []
    for i, (h, scale) in enumerate([(0.15, 1.0), (0.35, 0.95), (0.55, 1.0)]):
        o = _add_cyl(bpy, f"{prefix}_layer{i}", (0, 0, h), (scale, scale, 0.12))
        _set_material(o, mat)
        objs.append(o)
    return objs


# ═════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════

# Size multipliers per plan so the stand-in fills the hero slot with the
# expected scale (normalized against ~1.8m human).
_PLAN_TARGET_HEIGHT: dict[str, float] = {
    "humanoid_default":    1.8,
    "humanoid_chef":       1.9,
    "humanoid_ninja":      1.8,
    "humanoid_astronaut":  1.9,
    "humanoid_knight":     1.95,
    "humanoid_soldier":    1.85,
    "humanoid_pirate":     1.8,
    "humanoid_wizard":     1.9,
    "robot":               2.2,
    "alien":               2.0,
    "quadruped_small":     0.5,
    "quadruped_medium":    1.2,
    "quadruped_large":     1.8,
    "quadruped_xlarge":    3.5,
    "bird_small":          0.3,
    "bird_medium":         0.9,
    "bird_large":          1.4,
    "dragon":              4.0,
    "aquatic_streamlined": 2.5,
    "aquatic_blob":        1.5,
    "vehicle_sports":      1.2,   # height of a sports car
    "vehicle_sedan":       1.5,
    "vehicle_truck":       2.5,
    "vehicle_bike":        1.2,
    "vehicle_plane":       4.0,   # includes wing span
    "vehicle_helicopter":  3.0,
    "vehicle_spaceship":   3.5,
    "vehicle_boat":        2.5,
    "food_elongated":      0.5,
    "food_ring":           0.25,
    "food_flat":           0.15,
    "food_stack":          0.6,
}


def build_procedural_hero(bpy, subject: str, center=(0.0, 0.0, 0.0)) -> list:
    """
    Spawn a primitive-based stand-in for ``subject`` centered at ``center``.
    Returns the list of created objects (all tagged with ``hero_proc_``
    prefix so downstream helpers recognize them as hero geometry).

    Returns [] on any failure.
    """
    try:
        plan = _classify_subject(subject)
        prefix = f"hero_proc_{plan}"

        # Build per plan.
        if plan.startswith("humanoid_"):
            if plan == "humanoid_chef":
                objs = _build_humanoid_chef(bpy, prefix)
            elif plan == "humanoid_ninja":
                objs = _build_humanoid_ninja(bpy, prefix)
            else:
                mat = _make_material(bpy, plan, f"{prefix}_mat")
                skin = _make_material(bpy, "humanoid_default", f"{prefix}_skin")
                try:
                    bsdf = skin.node_tree.nodes.get("Principled BSDF")
                    bsdf.inputs["Base Color"].default_value = (0.95, 0.78, 0.65, 1.0)
                except Exception:
                    pass
                objs = _build_humanoid(bpy, mat, prefix, accent_mat=skin)
        elif plan == "robot":
            objs = _build_robot(bpy, prefix)
        elif plan == "alien":
            mat = _make_material(bpy, plan, f"{prefix}_mat")
            objs = _build_humanoid(bpy, mat, prefix)
        elif plan.startswith("quadruped_"):
            scale_map = {"quadruped_small": 0.45, "quadruped_medium": 0.8,
                         "quadruped_large": 1.1, "quadruped_xlarge": 1.8}
            objs = _build_quadruped(bpy, prefix, plan, body_scale=scale_map.get(plan, 1.0))
        elif plan.startswith("bird_"):
            scale_map = {"bird_small": 0.35, "bird_medium": 0.8, "bird_large": 1.3}
            objs = _build_bird(bpy, prefix, plan, scale=scale_map.get(plan, 1.0))
        elif plan == "dragon":
            objs = _build_dragon(bpy, prefix)
        elif plan == "aquatic_streamlined":
            objs = _build_aquatic_streamlined(bpy, prefix)
        elif plan == "aquatic_blob":
            mat = _make_material(bpy, plan, f"{prefix}_mat")
            o = _add_sphere(bpy, f"{prefix}_body", (0, 0, 0.8), (1.0, 1.0, 0.6))
            _set_material(o, mat)
            objs = [o]
        elif plan == "vehicle_sports":
            objs = _build_vehicle_sports(bpy, prefix)
        elif plan in ("vehicle_sedan", "vehicle_truck", "vehicle_bike"):
            objs = _build_vehicle_generic(bpy, prefix, plan)
        elif plan == "vehicle_plane":
            objs = _build_vehicle_plane(bpy, prefix)
        elif plan == "vehicle_helicopter":
            objs = _build_vehicle_plane(bpy, prefix)  # close enough
        elif plan == "vehicle_spaceship":
            objs = _build_vehicle_plane(bpy, prefix)
        elif plan == "vehicle_boat":
            mat = _make_material(bpy, plan, f"{prefix}_mat")
            hull = _add_cube(bpy, f"{prefix}_hull", (0, 0, 0.5), (2.0, 0.7, 0.4))
            _set_material(hull, mat)
            objs = [hull]
        elif plan.startswith("food_"):
            objs = _build_food(bpy, prefix, plan)
        else:
            objs = []

        # Translate whole group to ``center``.
        if objs:
            cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
            for o in objs:
                try:
                    o.location = (o.location.x + cx, o.location.y + cy, o.location.z + cz)
                except Exception:
                    pass

        print(
            f"[PROC_HERO] built plan={plan} for subject={subject!r} "
            f"({len(objs)} objects)",
            flush=True,
        )
        return objs
    except Exception as e:
        print(f"[PROC_HERO] build failed for subject={subject!r}: {e}", flush=True)
        return []


def boost_materials_for_low_light(objects, intensity: float = 0.20) -> int:
    """
    Add a subtle self-illumination to each object's materials so stylized
    procedural stand-ins read at night / dusk when the environment is
    dim. Without this, a dark-metallic Ferrari stand-in disappears into
    a dark street, because Principled BSDF reflections alone need real
    HDRI light to bounce — which night doesn't have.

    Emission color = base color, emission strength = intensity. Safe on
    any Blender 3.x/4.x Principled node (falls through on missing inputs).
    Returns the number of materials touched.
    """
    touched = 0
    for obj in objects or []:
        try:
            if obj is None:
                continue
            if not hasattr(obj, "data") or obj.data is None:
                continue
            if not hasattr(obj.data, "materials"):
                continue
            for mat in obj.data.materials:
                if not mat or not getattr(mat, "use_nodes", False):
                    continue
                try:
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                except Exception:
                    bsdf = None
                if not bsdf:
                    continue
                try:
                    base = bsdf.inputs["Base Color"].default_value
                    # Blender 4.x uses "Emission Color"; 3.x uses "Emission".
                    emi_color = bsdf.inputs.get("Emission Color")
                    if emi_color is None:
                        emi_color = bsdf.inputs.get("Emission")
                    if emi_color is not None:
                        emi_color.default_value = (base[0], base[1], base[2], 1.0)
                    strength = bsdf.inputs.get("Emission Strength")
                    if strength is not None:
                        strength.default_value = float(intensity)
                    touched += 1
                except Exception:
                    pass
        except Exception:
            pass
    return touched
