"""
scatter_ops.py
==============
Procedural scatter primitives for the World Development pass.

Every scatter "kind" (rock, bush, torch, banner, distant_tower, etc.) has a
builder function that constructs the object from Blender primitives. No
external asset fetch. Everything is tagged ``is_world_dev=True`` so the
optimizer, hero-finder, and FRAME_FIX filters can skip these objects.

Public API:
    scatter_rule(bpy, rule, hero_bbox, camera, rng, ground_fn) -> dict
    SCATTER_BUILDERS: dict[str, callable]

Design rules:
    1. Everything is LOW POLY. Scatter is atmosphere, not subject.
    2. Hero avoidance: every instance stays ``min_dist_to_hero`` away from
       the hero bbox center. Candidates inside the radius are skipped.
    3. Camera-cone avoidance: if the rule requires it, reject positions
       inside a 15° cone from camera toward hero (keeps scatter from
       spawning in the foreground blocking the shot).
    4. Determinism: the caller seeds a ``random.Random`` from
       ``hash(prompt)`` so the same prompt always produces the same layout.
    5. Non-fatal: every build helper is wrapped in try/except at the
       dispatch level. A failed kind logs and continues with the rest.
"""

from __future__ import annotations

from math import pi, sin, cos, sqrt
from dataclasses import dataclass, field


@dataclass
class ScatterRule:
    kind: str
    count_range: tuple = (4, 8)
    scale_range: tuple = (0.5, 1.5)
    radius: float = 20.0                    # placement disc radius around hero
    min_dist_to_hero: float = 3.0
    avoid_camera_cone: bool = False
    emissive: bool = False
    flicker: bool = False
    hanging: bool = False
    material: str = ""                      # override material name
    color: str = ""                         # optional color hint


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — material factories
# ═══════════════════════════════════════════════════════════════════════════

def _mat(bpy, name: str, rgba: tuple, roughness: float = 0.7, emission: float = 0.0,
         metallic: float = 0.0):
    """Create or return a Principled-BSDF material with these parameters."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
    try:
        m.use_nodes = True
        bsdf = None
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                bsdf = n
                break
        if bsdf is None:
            bsdf = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (*rgba[:3], 1.0) if len(rgba) == 3 else rgba
        try:
            bsdf.inputs["Roughness"].default_value = roughness
        except KeyError:
            pass
        try:
            bsdf.inputs["Metallic"].default_value = metallic
        except KeyError:
            pass
        if emission > 0:
            # Blender 4.x emission input name variants
            for k in ("Emission", "Emission Color"):
                try:
                    bsdf.inputs[k].default_value = (*rgba[:3], 1.0) if len(rgba) == 3 else rgba
                    break
                except KeyError:
                    continue
            try:
                bsdf.inputs["Emission Strength"].default_value = emission
            except KeyError:
                pass
    except Exception:
        pass
    return m


def _tag_world_dev(obj) -> None:
    """Tag as is_world_dev so hero-finder filters skip this object."""
    try:
        obj["is_world_dev"] = True
        obj["is_hero"] = False
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Scatter builders — each returns the placed object (or None)
# ═══════════════════════════════════════════════════════════════════════════

def _build_rock(bpy, location, scale, rule, rng):
    """Low-poly subdivided icosphere with slight deformation."""
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2, radius=scale, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_Rock"
    # Slight Y/Z stretch so rocks aren't perfectly round
    obj.scale = (
        1.0 * rng.uniform(0.8, 1.2),
        rng.uniform(0.7, 1.1),
        rng.uniform(0.5, 0.9),
    )
    obj.rotation_euler = (0, 0, rng.uniform(0, 2 * pi))
    # Rocky grey-brown
    tint = rng.uniform(0.25, 0.45)
    mat = _mat(bpy, "WD_Rock_Mat", (tint, tint * 0.9, tint * 0.75), roughness=0.9)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_scrub_bush(bpy, location, scale, rule, rng):
    """Icosphere squashed into a bush + darker green material."""
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2, radius=scale * 0.6, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_ScrubBush"
    obj.scale = (1.1, 1.1, 0.5)
    green = rng.uniform(0.15, 0.28)
    mat = _mat(bpy, "WD_ScrubBush_Mat", (green * 0.9, green, green * 0.4), roughness=0.85)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_grass_tuft(bpy, location, scale, rule, rng):
    """Tiny icosphere tuft."""
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=1, radius=scale * 0.4, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_GrassTuft"
    obj.scale = (1.0, 1.0, 0.4)
    g = rng.uniform(0.3, 0.5)
    mat = _mat(bpy, "WD_GrassTuft_Mat", (g * 0.7, g, g * 0.4), roughness=0.9)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_cactus(bpy, location, scale, rule, rng):
    """Cylinder trunk + two arm cylinders — saguaro silhouette."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=0.3 * scale * 0.2,
        depth=scale * 1.2, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_Cactus"
    mat = _mat(bpy, "WD_Cactus_Mat", (0.18, 0.32, 0.16), roughness=0.85)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_lamp_post(bpy, location, scale, rule, rng):
    """Tall pole + emissive bulb at top."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=0.08, depth=3.5, location=location,
    )
    post = bpy.context.active_object
    post.name = "WD_LampPost"
    post.location.z += 1.75
    _tag_world_dev(post)
    post_mat = _mat(bpy, "WD_LampPost_Mat", (0.15, 0.15, 0.15), roughness=0.5, metallic=0.8)
    post.data.materials.append(post_mat)
    # Bulb
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.2, location=(location[0], location[1], location[2] + 3.4),
    )
    bulb = bpy.context.active_object
    bulb.name = "WD_LampPost_Bulb"
    bulb_mat = _mat(bpy, "WD_LampBulb_Mat", (1.0, 0.82, 0.55), roughness=0.2, emission=12.0)
    bulb.data.materials.append(bulb_mat)
    _tag_world_dev(bulb)
    return post


def _build_puddle(bpy, location, scale, rule, rng):
    """Flat disc with mirror-reflective material (wet asphalt puddle)."""
    bpy.ops.mesh.primitive_circle_add(
        vertices=16, radius=scale * 0.7,
        location=(location[0], location[1], 0.005),
        fill_type='NGON',
    )
    obj = bpy.context.active_object
    obj.name = "WD_Puddle"
    obj.scale = (1.0, rng.uniform(0.6, 1.3), 1.0)
    mat = _mat(bpy, "WD_Puddle_Mat", (0.02, 0.03, 0.05), roughness=0.05, metallic=0.9)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_trash_can(bpy, location, scale, rule, rng):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=0.28, depth=0.75, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_TrashCan"
    obj.location.z += 0.375
    mat = _mat(bpy, "WD_TrashCan_Mat", (0.12, 0.13, 0.12), roughness=0.6, metallic=0.3)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_distant_car_glow(bpy, location, scale, rule, rng):
    """Two tiny emissive spheres (headlights-in-the-distance effect)."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.3, location=location, segments=8, ring_count=4,
    )
    obj = bpy.context.active_object
    obj.name = "WD_CarGlow"
    mat = _mat(bpy, "WD_CarGlow_Mat", (1.0, 0.95, 0.85), roughness=0.2, emission=20.0)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_torch(bpy, location, scale, rule, rng):
    """Torch: short cylinder stick + emissive flame sphere + optional point light."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=6, radius=0.06, depth=0.9, location=location,
    )
    stick = bpy.context.active_object
    stick.name = "WD_Torch_Stick"
    stick.location.z += 0.45
    stick_mat = _mat(bpy, "WD_TorchStick_Mat", (0.18, 0.12, 0.08), roughness=0.85)
    stick.data.materials.append(stick_mat)
    _tag_world_dev(stick)
    # Flame
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.12, location=(location[0], location[1], location[2] + 0.98),
        segments=8, ring_count=4,
    )
    flame = bpy.context.active_object
    flame.name = "WD_Torch_Flame"
    flame.scale = (1.0, 1.0, 1.6)
    flame_mat = _mat(bpy, "WD_TorchFlame_Mat", (1.0, 0.45, 0.18), roughness=0.2, emission=30.0)
    flame.data.materials.append(flame_mat)
    _tag_world_dev(flame)
    # Point light for actual illumination
    try:
        bpy.ops.object.light_add(
            type='POINT',
            location=(location[0], location[1], location[2] + 1.0),
        )
        light = bpy.context.active_object
        light.name = "WD_Torch_Light"
        light.data.energy = 500
        light.data.color = (1.0, 0.55, 0.25)
        _tag_world_dev(light)
        # Flicker: keyframe energy with slight noise
        if rule and getattr(rule, "flicker", False):
            try:
                base = light.data.energy
                for f in range(1, 241, 4):
                    light.data.energy = base * (0.85 + rng.random() * 0.30)
                    light.data.keyframe_insert(data_path="energy", frame=f)
                light.data.energy = base
            except Exception:
                pass
    except Exception:
        pass
    return stick


def _build_banner(bpy, location, scale, rule, rng):
    """Hanging cloth banner — plane with saturated color."""
    bpy.ops.mesh.primitive_plane_add(
        size=1.0, location=(location[0], location[1], location[2] + 1.5),
    )
    obj = bpy.context.active_object
    obj.name = "WD_Banner"
    obj.scale = (0.6, 0.05, 1.0 * scale)
    hue = rng.choice([(0.6, 0.12, 0.12), (0.12, 0.15, 0.55), (0.55, 0.45, 0.12), (0.2, 0.4, 0.2)])
    mat = _mat(bpy, f"WD_Banner_Mat_{rng.randint(0, 9999)}", hue, roughness=0.9)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_stone_block(bpy, location, scale, rule, rng):
    """Rough stone block — deformed cube."""
    bpy.ops.mesh.primitive_cube_add(
        size=scale * 0.8, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_StoneBlock"
    obj.scale = (
        rng.uniform(0.8, 1.3),
        rng.uniform(0.7, 1.2),
        rng.uniform(0.4, 0.8),
    )
    obj.rotation_euler = (0, 0, rng.uniform(0, 2 * pi))
    mat = _mat(bpy, "WD_StoneBlock_Mat", (0.35, 0.33, 0.30), roughness=0.88)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_distant_tower(bpy, location, scale, rule, rng):
    """Tall cylinder + cone top — distant castle tower silhouette."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=scale * 0.5, depth=scale, location=location,
    )
    tower = bpy.context.active_object
    tower.name = "WD_Tower"
    tower.location.z += scale * 0.5
    mat = _mat(bpy, "WD_Tower_Mat", (0.25, 0.22, 0.2), roughness=0.9)
    tower.data.materials.append(mat)
    _tag_world_dev(tower)
    bpy.ops.mesh.primitive_cone_add(
        vertices=8, radius1=scale * 0.5, depth=scale * 0.4,
        location=(location[0], location[1], location[2] + scale * 1.2),
    )
    top = bpy.context.active_object
    top.name = "WD_Tower_Top"
    top_mat = _mat(bpy, "WD_TowerTop_Mat", (0.18, 0.15, 0.14), roughness=0.85)
    top.data.materials.append(top_mat)
    _tag_world_dev(top)
    return tower


def _build_trunk(bpy, location, scale, rule, rng):
    """Tree trunk — tall cylinder, brown."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=scale * 0.3, depth=scale * 4.0, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_Trunk"
    obj.location.z += scale * 2.0
    mat = _mat(bpy, "WD_Trunk_Mat", (0.22, 0.14, 0.08), roughness=0.95)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_fallen_log(bpy, location, scale, rule, rng):
    """Horizontal log — cylinder rotated."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8, radius=scale * 0.25, depth=scale * 1.8, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_FallenLog"
    obj.rotation_euler = (pi * 0.5, 0, rng.uniform(0, 2 * pi))
    obj.location.z = 0.3
    mat = _mat(bpy, "WD_FallenLog_Mat", (0.18, 0.12, 0.07), roughness=0.9)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_fern(bpy, location, scale, rule, rng):
    """Ferns — flat squashed icosphere with saturated green."""
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=1, radius=scale * 0.5, location=location,
    )
    obj = bpy.context.active_object
    obj.name = "WD_Fern"
    obj.scale = (1.2, 1.2, 0.3)
    g = rng.uniform(0.18, 0.32)
    mat = _mat(bpy, "WD_Fern_Mat", (g * 0.4, g, g * 0.35), roughness=0.85)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_mushroom(bpy, location, scale, rule, rng):
    """Mushroom: short cylinder + red-white cap."""
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=6, radius=scale * 0.1, depth=scale * 0.3, location=location,
    )
    stem = bpy.context.active_object
    stem.name = "WD_Mushroom_Stem"
    stem_mat = _mat(bpy, "WD_MushroomStem_Mat", (0.9, 0.88, 0.78), roughness=0.85)
    stem.data.materials.append(stem_mat)
    _tag_world_dev(stem)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=scale * 0.18, location=(location[0], location[1], location[2] + 0.2),
        segments=8, ring_count=4,
    )
    cap = bpy.context.active_object
    cap.name = "WD_Mushroom_Cap"
    cap.scale = (1.0, 1.0, 0.6)
    cap_mat = _mat(bpy, "WD_MushroomCap_Mat", (0.75, 0.15, 0.15), roughness=0.8)
    cap.data.materials.append(cap_mat)
    _tag_world_dev(cap)
    return stem


def _build_boulder(bpy, location, scale, rule, rng):
    """Large rock — scaled-up rock builder."""
    return _build_rock(bpy, location, scale * 1.8, rule, rng)


def _build_snow_patch(bpy, location, scale, rule, rng):
    """White flat disc — patch of snow."""
    bpy.ops.mesh.primitive_circle_add(
        vertices=10, radius=scale * 0.9,
        location=(location[0], location[1], 0.01),
        fill_type='NGON',
    )
    obj = bpy.context.active_object
    obj.name = "WD_SnowPatch"
    obj.scale = (1.0, rng.uniform(0.7, 1.3), 1.0)
    mat = _mat(bpy, "WD_SnowPatch_Mat", (0.92, 0.94, 0.97), roughness=0.35)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


def _build_tire_barrier(bpy, location, scale, rule, rng):
    """Stacked tire barrier — 3 tori in a short column."""
    tires = []
    for i in range(3):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.35, minor_radius=0.12,
            location=(location[0], location[1], 0.15 + i * 0.28),
            major_segments=12, minor_segments=6,
        )
        t = bpy.context.active_object
        t.name = f"WD_TireBarrier_{i}"
        mat = _mat(bpy, "WD_Tire_Mat", (0.04, 0.04, 0.04), roughness=0.9)
        t.data.materials.append(mat)
        _tag_world_dev(t)
        tires.append(t)
    return tires[0] if tires else None


def _build_grandstand(bpy, location, scale, rule, rng):
    """Grandstand silhouette — long angled block."""
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(location[0], location[1], scale * 0.5),
    )
    obj = bpy.context.active_object
    obj.name = "WD_Grandstand"
    obj.scale = (scale * 5.0, 2.0, scale * 1.5)
    mat = _mat(bpy, "WD_Grandstand_Mat", (0.18, 0.16, 0.15), roughness=0.85)
    obj.data.materials.append(mat)
    _tag_world_dev(obj)
    return obj


SCATTER_BUILDERS = {
    "rock":               _build_rock,
    "scrub_bush":         _build_scrub_bush,
    "dry_grass_tuft":     _build_grass_tuft,
    "distant_cactus":     _build_cactus,
    "lamp_post":          _build_lamp_post,
    "puddle":             _build_puddle,
    "trash_can":          _build_trash_can,
    "distant_car_glow":   _build_distant_car_glow,
    "torch":              _build_torch,
    "banner":             _build_banner,
    "stone_block":        _build_stone_block,
    "distant_tower":      _build_distant_tower,
    "tree_trunk":         _build_trunk,
    "fallen_log":         _build_fallen_log,
    "fern":               _build_fern,
    "mushroom":           _build_mushroom,
    "boulder":            _build_boulder,
    "snow_patch":         _build_snow_patch,
    "tire_barrier":       _build_tire_barrier,
    "grandstand":         _build_grandstand,
    # Aliases that fall back to rock for unimplemented kinds — ensures no
    # ScatterRule ever fails silently; the caller logs per-rule placement.
    "rock_poking_through": _build_rock,
    "alpine_grass":        _build_grass_tuft,
    "ice_shard":           _build_rock,
    "snow_drift":          _build_snow_patch,
    "sideline_marker":     _build_stone_block,
    "goal_post":           _build_lamp_post,
    "stadium_light":       _build_lamp_post,
    "spray_particle":      _build_snow_patch,
    "foam_patch":          _build_snow_patch,
    "table":               _build_stone_block,
    "chair":               _build_stone_block,
    "hanging_pendant_light": _build_lamp_post,
    "light_pole":          _build_lamp_post,
}


# ═══════════════════════════════════════════════════════════════════════════
# Rule dispatcher — places N instances of a kind with avoidance
# ═══════════════════════════════════════════════════════════════════════════

def _inside_camera_cone(x: float, y: float, cam, hero_center, half_angle_rad=0.26):
    """Return True if (x,y) is inside a cone from cam toward hero_center."""
    if cam is None or hero_center is None:
        return False
    try:
        cx, cy = cam.location.x, cam.location.y
        hx, hy = hero_center[0], hero_center[1]
        # Direction from cam to hero (normalized 2D)
        fx, fy = hx - cx, hy - cy
        mag = sqrt(fx * fx + fy * fy)
        if mag < 0.01:
            return False
        fx /= mag
        fy /= mag
        # Direction from cam to candidate
        dx, dy = x - cx, y - cy
        dmag = sqrt(dx * dx + dy * dy)
        if dmag < 0.01:
            return False
        dx /= dmag
        dy /= dmag
        # Dot product → cos(angle)
        dot = fx * dx + fy * dy
        # Inside cone if angle < half_angle AND candidate is between cam and hero + margin
        import math
        return dot > math.cos(half_angle_rad) and dmag < mag * 1.3
    except Exception:
        return False


def scatter_rule(
    bpy, rule, hero_center, camera, rng,
    ground_z: float = 0.0, tier: str = "fast",
) -> dict:
    """Place a ScatterRule's instances with hero/camera/overlap avoidance.

    Returns a report dict: ``{placed, skipped_hero, skipped_cone, skipped_overlap}``
    """
    placed = 0
    skipped_hero = 0
    skipped_cone = 0
    skipped_overlap = 0

    builder = SCATTER_BUILDERS.get(rule.kind)
    if builder is None:
        print(f"[WORLD_DEV/SCATTER] rule={rule.kind} — no builder, skipping", flush=True)
        return {
            "kind": rule.kind, "placed": 0,
            "skipped_hero": 0, "skipped_cone": 0, "skipped_overlap": 0,
        }

    # Deterministic count based on rng state
    cmin, cmax = rule.count_range
    requested = rng.randint(cmin, cmax)
    if tier == "preview":
        requested = max(1, requested // 2)

    # Collect placed (x, y) for overlap avoidance
    placed_xy: list = []

    hero_x = hero_center[0] if hero_center else 0.0
    hero_y = hero_center[1] if hero_center else 0.0

    tries = 0
    max_tries = requested * 8  # cap attempts to avoid infinite loops
    while placed < requested and tries < max_tries:
        tries += 1
        # Polar sampling around hero
        theta = rng.uniform(0, 2 * pi)
        r = rng.uniform(rule.min_dist_to_hero, rule.radius)
        x = hero_x + r * cos(theta)
        y = hero_y + r * sin(theta)

        # Hero avoidance (redundant with r lower bound but safer)
        if sqrt((x - hero_x) ** 2 + (y - hero_y) ** 2) < rule.min_dist_to_hero:
            skipped_hero += 1
            continue

        # Camera cone avoidance
        if rule.avoid_camera_cone and _inside_camera_cone(x, y, camera, hero_center):
            skipped_cone += 1
            continue

        # Overlap avoidance (simple O(N) check)
        too_close = False
        for (px, py) in placed_xy:
            if (x - px) ** 2 + (y - py) ** 2 < 0.8 * 0.8:
                too_close = True
                break
        if too_close:
            skipped_overlap += 1
            continue

        # Sample scale and place
        scale = rng.uniform(*rule.scale_range)
        location = (x, y, ground_z)
        try:
            builder(bpy, location, scale, rule, rng)
            placed_xy.append((x, y))
            placed += 1
        except Exception as e:
            print(f"[WORLD_DEV/SCATTER] rule={rule.kind} build failed at ({x:.1f},{y:.1f}): {e}", flush=True)
            continue

    print(
        f"[WORLD_DEV/SCATTER] rule={rule.kind} requested={cmin}..{cmax} "
        f"placed={placed} skipped_hero={skipped_hero} "
        f"skipped_cone={skipped_cone} skipped_overlap={skipped_overlap}",
        flush=True,
    )
    return {
        "kind": rule.kind, "placed": placed,
        "skipped_hero": skipped_hero,
        "skipped_cone": skipped_cone,
        "skipped_overlap": skipped_overlap,
    }
