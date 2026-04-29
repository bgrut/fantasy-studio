from __future__ import annotations

"""
environment_ops.py
==================
Round 9 Pillar 2: rich environment layers.

Most templates produce a hero object floating in a mostly-empty scene —
correct topology, but visually flat and far from "professional CGI".
This module provides gap-filler helpers that add:

  * Atmospheric fog/volume scatter tuned to the mood + time-of-day.
  * Classical 3-point lighting (key + fill + rim) when the scene has
    fewer than three lights.
  * A soft contact shadow under the hero so it reads as "on the ground"
    instead of "sitting in space".
  * Preset ground materials (asphalt, grass, concrete, sand, etc.).
  * ``build_environment_layers(...)`` orchestrator for all of the above.

Design rule: NEVER clobber a template's deliberate choice. Every helper
first checks what's already there and only fills gaps. If the scene
already has three lights, ``setup_cinematic_lighting`` is a no-op.
"""

import math
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Mood / time-of-day palette
# ═══════════════════════════════════════════════════════════════════════════
#
# Values are (color_rgb, fog_density, key_intensity_mul, ambient_color).
# Kept intentionally narrow — fine-tuning happens in HDRI selection.

_MOOD_PRESETS: dict[str, dict] = {
    "day":       {"fog": 0.003, "key_color": (1.0, 0.96, 0.88), "fill_color": (0.80, 0.88, 1.0),  "key_mul": 1.0,  "fog_color": (0.80, 0.88, 1.0)},
    "night":     {"fog": 0.012, "key_color": (0.50, 0.60, 1.00), "fill_color": (0.30, 0.35, 0.60), "key_mul": 0.55, "fog_color": (0.06, 0.08, 0.18)},
    "sunset":    {"fog": 0.006, "key_color": (1.0, 0.65, 0.35),  "fill_color": (0.55, 0.40, 0.65), "key_mul": 0.85, "fog_color": (0.95, 0.60, 0.40)},
    "sunrise":   {"fog": 0.008, "key_color": (1.0, 0.72, 0.50),  "fill_color": (0.60, 0.55, 0.75), "key_mul": 0.80, "fog_color": (0.90, 0.70, 0.55)},
    "overcast":  {"fog": 0.010, "key_color": (0.90, 0.92, 0.95), "fill_color": (0.75, 0.78, 0.85), "key_mul": 0.70, "fog_color": (0.70, 0.72, 0.78)},
    "foggy":     {"fog": 0.030, "key_color": (0.90, 0.92, 0.95), "fill_color": (0.75, 0.78, 0.82), "key_mul": 0.55, "fog_color": (0.78, 0.80, 0.85)},
    "studio":    {"fog": 0.000, "key_color": (1.0, 1.0, 1.0),    "fill_color": (0.85, 0.90, 1.0),  "key_mul": 1.1,  "fog_color": (0.50, 0.50, 0.55)},
    "moody":     {"fog": 0.018, "key_color": (0.60, 0.65, 0.90), "fill_color": (0.25, 0.28, 0.45), "key_mul": 0.60, "fog_color": (0.08, 0.10, 0.15)},
}

_TOD_ALIASES: dict[str, str] = {
    "dawn":        "sunrise",
    "morning":     "day",
    "noon":        "day",
    "afternoon":   "day",
    "dusk":        "sunset",
    "evening":     "sunset",
    "golden_hour": "sunset",
    "golden hour": "sunset",
    "midnight":    "night",
    "dark":        "night",
}


def _resolve_mood_preset(mood: str, time_of_day: str) -> dict:
    key = (time_of_day or "").strip().lower()
    key = _TOD_ALIASES.get(key, key)
    if key in _MOOD_PRESETS:
        return _MOOD_PRESETS[key]
    m = (mood or "").strip().lower()
    m = _TOD_ALIASES.get(m, m)
    if m in _MOOD_PRESETS:
        return _MOOD_PRESETS[m]
    return _MOOD_PRESETS["day"]


# ═══════════════════════════════════════════════════════════════════════════
# Atmosphere — volume scatter in the World shader
# ═══════════════════════════════════════════════════════════════════════════

def add_atmosphere(bpy, scene, mood: str = "", time_of_day: str = "") -> bool:
    """
    Add a subtle volume-scatter layer to the world shader so light has
    something to interact with. Skips when the world already has a
    ``ShaderNodeVolumeScatter`` (a template already set its own fog).
    Returns True iff we added a volume.
    """
    preset = _resolve_mood_preset(mood, time_of_day)
    density = preset["fog"]
    if density <= 0:
        return False  # studio / clean look — no fog wanted

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links

    # Skip if a volume scatter is already wired into World Output.
    for n in nodes:
        if n.bl_idname == "ShaderNodeVolumeScatter":
            return False

    # Find or create the world output, keeping any existing surface.
    out_node = next((n for n in nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
    if out_node is None:
        out_node = nodes.new(type="ShaderNodeOutputWorld")
        out_node.location = (400, 0)

    vol = nodes.new(type="ShaderNodeVolumeScatter")
    vol.inputs["Color"].default_value = (*preset["fog_color"], 1.0)
    vol.inputs["Density"].default_value = density
    try:
        vol.inputs["Anisotropy"].default_value = 0.25
    except (KeyError, TypeError):
        pass
    vol.location = (200, -200)
    links.new(vol.outputs["Volume"], out_node.inputs["Volume"])
    print(
        f"[ENV] atmosphere: density={density} color={preset['fog_color']} "
        f"mood={mood!r} tod={time_of_day!r}",
        flush=True,
    )
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 3-point lighting
# ═══════════════════════════════════════════════════════════════════════════

def _existing_lights(bpy) -> list:
    return [obj for obj in bpy.data.objects if obj.type == "LIGHT"]


def setup_cinematic_lighting(
    bpy, scene, mood: str = "", time_of_day: str = "",
    hero_location=(0.0, 0.0, 0.0),
) -> int:
    """
    Ensure classical 3-point lighting is present (key + fill + rim).
    Only adds lights the scene is missing — already-placed template
    lights are preserved. Returns the number of lights added.
    """
    preset = _resolve_mood_preset(mood, time_of_day)
    mul = preset["key_mul"]
    existing = _existing_lights(bpy)
    existing_count = len(existing)
    if existing_count >= 3:
        # Template already rigged its own 3-point — don't double up.
        return 0

    hx, hy, hz = hero_location
    added = 0

    def _add(name: str, loc, energy, color, size=3.0, rot=(0, 0, 0)) -> None:
        nonlocal added
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.color = color
        try:
            light.data.shape = "SQUARE"
            light.data.size = size
        except AttributeError:
            pass
        light.rotation_euler = rot
        added += 1

    # Pick slots to fill. Label by role so operators/debug can tell what
    # was added. Rotate lights to point roughly at hero_location.
    need = 3 - existing_count
    slots = [
        ("CinematicKey",  (hx + 4.0, hy - 4.0, hz + 4.0), 2000.0 * mul, preset["key_color"],  4.0, (math.radians(55), 0, math.radians(45))),
        ("CinematicFill", (hx - 3.5, hy - 2.5, hz + 2.5), 700.0 * mul,  preset["fill_color"], 5.0, (math.radians(65), 0, math.radians(-35))),
        ("CinematicRim",  (hx + 0.0, hy + 5.0, hz + 4.0), 1500.0 * mul, (1.0, 1.0, 1.0),       3.0, (math.radians(115), 0, math.radians(180))),
    ]
    for slot in slots[:need]:
        _add(*slot)

    if added:
        print(f"[ENV] 3-point lighting: added {added} lights (had {existing_count})", flush=True)
    return added


# ═══════════════════════════════════════════════════════════════════════════
# Contact shadow
# ═══════════════════════════════════════════════════════════════════════════

def _hero_bbox_world(hero_objs) -> tuple[tuple[float, float, float], float] | None:
    """Return (center_world_xyz, max_xy_extent) across hero meshes."""
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for obj in hero_objs:
        if obj is None or not hasattr(obj, "bound_box"):
            continue
        try:
            mw = obj.matrix_world
            for corner in obj.bound_box:
                v = mw @ _as_vec(obj, corner)
                xs.append(v.x); ys.append(v.y); zs.append(v.z)
        except Exception:
            continue
    if not xs:
        return None
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = min(zs)  # floor of bounds
    ext = max(max(xs) - min(xs), max(ys) - min(ys))
    return ((cx, cy, cz), ext)


def _as_vec(obj, corner):
    # corner is an mathutils.Vector equivalent in bpy; this wraps so we
    # can call matrix_world @ corner safely even for Blender stubs.
    try:
        from mathutils import Vector  # type: ignore
        return Vector(corner)
    except Exception:
        return corner


def add_contact_shadow(bpy, hero_objects) -> bool:
    """
    Drop a dark, low-roughness disc just above the ground under the hero
    to simulate an ambient-occlusion contact shadow. Harmless in empty
    scenes — silently no-ops if hero_objects is missing/empty.
    """
    if not hero_objects:
        return False
    info = _hero_bbox_world(hero_objects)
    if info is None:
        return False
    (cx, cy, cz), ext = info
    radius = max(0.4, ext * 0.6)

    # Skip if we already added one (rebuilds/re-runs).
    for obj in bpy.data.objects:
        if obj.name.startswith("ContactShadow"):
            return False

    bpy.ops.mesh.primitive_circle_add(
        vertices=48, radius=radius, location=(cx, cy, cz + 0.01), fill_type="NGON",
    )
    disc = bpy.context.object
    disc.name = "ContactShadow"
    # Ensure it sorts as non-hero (underscore prefix hides from outliner selection).
    mat = bpy.data.materials.new("ContactShadowMat")
    mat.use_nodes = True
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            try:
                bsdf.inputs["Alpha"].default_value = 0.55
            except KeyError:
                pass
            try:
                bsdf.inputs["Roughness"].default_value = 1.0
            except KeyError:
                pass
        mat.blend_method = "BLEND"
    except Exception as e:
        print(f"[ENV] contact-shadow material setup failed: {e}", flush=True)
    disc.data.materials.append(mat)
    print(f"[ENV] contact shadow added at ({cx:.2f}, {cy:.2f}, {cz:.2f}) radius={radius:.2f}", flush=True)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Ground material presets
# ═══════════════════════════════════════════════════════════════════════════

_GROUND_PRESETS: dict[str, dict] = {
    "road_asphalt":  {"color": (0.06, 0.06, 0.07, 1.0), "roughness": 0.78, "metallic": 0.0,  "specular": 0.35},
    "concrete":      {"color": (0.45, 0.44, 0.43, 1.0), "roughness": 0.85, "metallic": 0.0,  "specular": 0.25},
    "terrain_ground":{"color": (0.28, 0.22, 0.16, 1.0), "roughness": 0.95, "metallic": 0.0,  "specular": 0.20},
    "grass":         {"color": (0.16, 0.36, 0.12, 1.0), "roughness": 0.92, "metallic": 0.0,  "specular": 0.20},
    "sand":          {"color": (0.82, 0.73, 0.54, 1.0), "roughness": 0.90, "metallic": 0.0,  "specular": 0.30},
    "snow":          {"color": (0.93, 0.95, 0.98, 1.0), "roughness": 0.70, "metallic": 0.0,  "specular": 0.50},
    "water_surface": {"color": (0.05, 0.15, 0.25, 1.0), "roughness": 0.05, "metallic": 0.0,  "specular": 1.0},
    "studio_floor":  {"color": (0.85, 0.85, 0.85, 1.0), "roughness": 0.50, "metallic": 0.0,  "specular": 0.50},
}


def _find_ground_object(bpy):
    """Find the most plausible ground object (named ground/floor/road/etc)."""
    names = ("groundplane", "ground", "floor", "road", "street", "terrain", "backdrop", "plane")
    best = None
    best_score = -1.0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        lname = obj.name.lower()
        hit = any(n in lname for n in names)
        if not hit:
            continue
        # Prefer the largest by bounding box extent.
        try:
            xs = [c[0] for c in obj.bound_box]
            ys = [c[1] for c in obj.bound_box]
            ext = (max(xs) - min(xs)) * (max(ys) - min(ys)) * max(abs(obj.scale.x), 1.0) * max(abs(obj.scale.y), 1.0)
        except Exception:
            ext = 0.0
        if ext > best_score:
            best_score = ext
            best = obj
    return best


def apply_ground_material(bpy, scene, ground_type: str) -> bool:
    """
    Apply a preset material to the main ground object. If the preset is
    unknown or there's no ground, silently no-ops. Preserves existing
    non-default materials (don't stomp a template that already dressed
    its road with a texture).
    """
    preset = _GROUND_PRESETS.get((ground_type or "").lower())
    if not preset:
        return False
    ground = _find_ground_object(bpy)
    if ground is None:
        return False

    # If there's already a material with non-generic name, leave it.
    existing = [s.material for s in ground.material_slots if s.material]
    for mat in existing:
        if not any(mat.name.lower().startswith(p) for p in ("material", "default", "generic", "plane")):
            return False  # template already dressed it

    mat = bpy.data.materials.new(f"Ground_{ground_type}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return False
    bsdf.inputs["Base Color"].default_value = preset["color"]
    try:
        bsdf.inputs["Roughness"].default_value = preset["roughness"]
    except KeyError:
        pass
    try:
        bsdf.inputs["Metallic"].default_value = preset["metallic"]
    except KeyError:
        pass
    for sp_key in ("Specular", "Specular IOR Level"):
        try:
            bsdf.inputs[sp_key].default_value = preset["specular"]
            break
        except KeyError:
            continue

    if ground.data.materials:
        ground.data.materials[0] = mat
    else:
        ground.data.materials.append(mat)
    print(f"[ENV] ground material: {ground_type} -> {ground.name}", flush=True)
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Landscape guarantor — ground scale, distant hills, cyc-wall
# ═══════════════════════════════════════════════════════════════════════════
#
# Round 10 Pillar B. The gray-void problem isn't just the sky — even when
# a ground plane exists, it's often only 10x10 units and sits below the
# camera's cropped framing, so the render has no horizon line. Here we
# (1) scale the existing ground up to at least 120x120 so it reaches
# the horizon, (2) add silhouette geometry for outdoor families, and
# (3) add a cyc-wall curve for studio/product/character_stage.

_OUTDOOR_FAMILIES = {
    "scenic_landscape", "street_scene", "ocean_scene", "car_hero",
    "neon_news", "city_loop",
}
_STUDIO_FAMILIES = {
    "character_stage", "product_scene", "product_pedestal",
}


def _ensure_ground_plane_scale(bpy, min_extent: float = 120.0) -> bool:
    """
    If the scene has a ground plane and it's smaller than ``min_extent``
    in either horizontal dimension, scale it up so the horizon meets
    the sky instead of ending mid-frame. Returns True iff we rescaled.
    """
    ground = _find_ground_object(bpy)
    if ground is None:
        return False
    try:
        xs = [c[0] for c in ground.bound_box]
        ys = [c[1] for c in ground.bound_box]
        local_x = max(xs) - min(xs)
        local_y = max(ys) - min(ys)
        world_x = local_x * abs(ground.scale.x)
        world_y = local_y * abs(ground.scale.y)
        if world_x >= min_extent and world_y >= min_extent:
            return False
        # Scale up proportionally to at least min_extent.
        needed_x = min_extent / max(world_x, 0.001)
        needed_y = min_extent / max(world_y, 0.001)
        factor = max(needed_x, needed_y, 1.0)
        if factor <= 1.01:
            return False
        ground.scale.x *= factor
        ground.scale.y *= factor
        print(
            f"[ENV] rescaled ground {ground.name!r} by {factor:.2f}x "
            f"(to ~{world_x * factor:.0f}x{world_y * factor:.0f})",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[ENV] _ensure_ground_plane_scale failed: {e}", flush=True)
        return False


def _add_distant_hills(bpy, mood: str = "", time_of_day: str = "") -> int:
    """
    Add a ring of low-poly procedural hills roughly 60 units out so the
    horizon has silhouette interest instead of a flat stripe. Skips if
    ``DistantHills_*`` geometry already exists. Returns count added.
    """
    for obj in bpy.data.objects:
        if obj.name.startswith("DistantHills"):
            return 0

    preset = _resolve_mood_preset(mood, time_of_day)
    # Muted horizon colour — slightly cooler than the fog so hills recede.
    fog = preset["fog_color"]
    hill_color = (
        max(0.0, fog[0] * 0.55 + 0.08),
        max(0.0, fog[1] * 0.55 + 0.08),
        max(0.0, fog[2] * 0.55 + 0.10),
        1.0,
    )
    mat = bpy.data.materials.new("DistantHillsMat")
    mat.use_nodes = True
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = hill_color
            try:
                bsdf.inputs["Roughness"].default_value = 1.0
            except KeyError:
                pass
            try:
                bsdf.inputs["Specular IOR Level"].default_value = 0.05
            except KeyError:
                try:
                    bsdf.inputs["Specular"].default_value = 0.05
                except KeyError:
                    pass
    except Exception as e:
        print(f"[ENV] hill material setup failed: {e}", flush=True)

    added = 0
    # 6 hill clumps around the camera, offset angularly.
    import math as _m
    positions = [
        (60, 0, 0),
        (42, 42, 0),
        (0, 60, 0),
        (-42, 42, 0),
        (-60, 0, 0),
        (-42, -42, 0),
    ]
    for i, (x, y, z) in enumerate(positions):
        try:
            # Low-poly subdivided plane we'll push up into a bump.
            bpy.ops.mesh.primitive_ico_sphere_add(
                subdivisions=2, radius=9.0, location=(x, y, z + 2.5),
            )
            hill = bpy.context.object
            hill.name = f"DistantHills_{i}"
            # Squash vertically so it's a low rolling hill, not a sphere.
            hill.scale = (1.6, 1.6, 0.35)
            # Sink the bottom slightly below the ground so no seam shows.
            hill.location.z = -1.0
            # Rotate randomly around Z so silhouettes don't repeat.
            hill.rotation_euler = (0, 0, _m.radians(i * 37.0))
            hill.data.materials.append(mat)
            added += 1
        except Exception as e:
            print(f"[ENV] distant hill {i} failed: {e}", flush=True)

    if added:
        print(f"[ENV] added {added} distant hill silhouettes", flush=True)
    return added


def _add_cyc_wall(bpy) -> bool:
    """
    Add a curved cyclorama wall behind the subject for studio shots so
    there's a clean infinity backdrop instead of raw world colour.
    Returns True iff added.
    """
    for obj in bpy.data.objects:
        if obj.name.startswith("CycWall"):
            return False
    try:
        bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0, 12.0, 10.0))
        wall = bpy.context.object
        wall.name = "CycWall"
        wall.rotation_euler = (math.radians(90), 0, 0)
        wall.scale = (1.5, 0.5, 1.0)
        mat = bpy.data.materials.new("CycWallMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.18, 0.19, 0.22, 1.0)
            try:
                bsdf.inputs["Roughness"].default_value = 0.85
            except KeyError:
                pass
        wall.data.materials.append(mat)
        print("[ENV] added cyc-wall backdrop", flush=True)
        return True
    except Exception as e:
        print(f"[ENV] cyc-wall add failed: {e}", flush=True)
        return False


def ensure_ground_and_horizon(
    bpy, scene, manifest: dict, mood: str = "", time_of_day: str = "",
) -> dict:
    """
    Guarantee the scene has a horizon line. For outdoor families: expand
    ground + add distant hills. For studio families: add a cyc-wall.
    """
    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    family = str(scene_plan.get("scene_family") or "").lower()
    report: dict[str, Any] = {
        "ground_rescaled": False,
        "hills_added": 0,
        "cyc_wall_added": False,
    }

    if family in _OUTDOOR_FAMILIES or (
        family not in _STUDIO_FAMILIES and family != ""
    ):
        # Default to "outdoor" when family is unknown — outdoor is the
        # safer fallback visually (most prompts are outdoor).
        report["ground_rescaled"] = _ensure_ground_plane_scale(bpy)
        report["hills_added"] = _add_distant_hills(bpy, mood=mood, time_of_day=time_of_day)
    elif family in _STUDIO_FAMILIES:
        report["cyc_wall_added"] = _add_cyc_wall(bpy)
    else:
        # No family — still try the ground rescale as a cheap safety net.
        report["ground_rescaled"] = _ensure_ground_plane_scale(bpy)

    return report


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def _infer_ground_type(manifest: dict) -> str | None:
    """Pick a ground preset from manifest / scene_plan hints."""
    explicit = manifest.get("environment_ground_type")
    if explicit and isinstance(explicit, str):
        return explicit.lower()
    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    family = str(scene_plan.get("scene_family") or "").lower()
    env = str(scene_plan.get("environment") or "").lower()
    text = f"{family} {env}"
    if any(w in text for w in ("street", "city", "road", "highway", "urban")):
        return "road_asphalt"
    if any(w in text for w in ("park", "meadow", "grass", "garden", "lawn")):
        return "grass"
    if any(w in text for w in ("desert", "dune", "beach", "sand")):
        return "sand"
    if any(w in text for w in ("snow", "arctic", "winter", "ice")):
        return "snow"
    if any(w in text for w in ("ocean", "sea", "water", "lake", "river", "underwater")):
        return "water_surface"
    if any(w in text for w in ("studio", "pedestal", "product")):
        return "studio_floor"
    if any(w in text for w in ("mountain", "forest", "landscape", "scenic")):
        return "terrain_ground"
    return None


def build_environment_layers(
    bpy, scene, manifest: dict, hero_objects: list | None = None,
) -> dict:
    """
    Top-level orchestrator. Adds any missing cinematic environment
    layers — atmosphere, 3-point lighting, ground material, contact
    shadow — without overwriting template-provided assets.

    Returns a report dict describing what was added.
    """
    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    mood = str(scene_plan.get("mood") or manifest.get("mood") or "")
    tod = str(scene_plan.get("time_of_day") or manifest.get("time_of_day") or "")

    report: dict[str, Any] = {
        "atmosphere": False,
        "lights_added": 0,
        "ground_material": None,
        "contact_shadow": False,
    }

    try:
        report["atmosphere"] = add_atmosphere(bpy, scene, mood=mood, time_of_day=tod)
    except Exception as e:
        print(f"[ENV] add_atmosphere failed (non-fatal): {e}", flush=True)

    # Estimate hero location for lighting aim.
    hero_loc = (0.0, 0.0, 0.0)
    if hero_objects:
        info = _hero_bbox_world(hero_objects)
        if info:
            hero_loc = info[0]
    try:
        report["lights_added"] = setup_cinematic_lighting(
            bpy, scene, mood=mood, time_of_day=tod, hero_location=hero_loc,
        )
    except Exception as e:
        print(f"[ENV] setup_cinematic_lighting failed (non-fatal): {e}", flush=True)

    ground_type = _infer_ground_type(manifest)
    if ground_type:
        try:
            applied = apply_ground_material(bpy, scene, ground_type)
            report["ground_material"] = ground_type if applied else None
        except Exception as e:
            print(f"[ENV] apply_ground_material failed (non-fatal): {e}", flush=True)

    # Round 10 Pillar B: guarantee a horizon line (ground rescale +
    # distant hills for outdoor, cyc-wall for studio).
    try:
        landscape = ensure_ground_and_horizon(
            bpy, scene, manifest, mood=mood, time_of_day=tod,
        )
        report.update({
            "ground_rescaled": landscape.get("ground_rescaled", False),
            "hills_added":     landscape.get("hills_added", 0),
            "cyc_wall_added":  landscape.get("cyc_wall_added", False),
        })
    except Exception as e:
        print(f"[ENV] ensure_ground_and_horizon failed (non-fatal): {e}", flush=True)

    if hero_objects:
        try:
            report["contact_shadow"] = add_contact_shadow(bpy, hero_objects)
        except Exception as e:
            print(f"[ENV] add_contact_shadow failed (non-fatal): {e}", flush=True)

    print(
        f"[ENV] build_environment_layers report: atmos={report['atmosphere']} "
        f"lights+{report['lights_added']} ground={report['ground_material']} "
        f"contact={report['contact_shadow']}",
        flush=True,
    )
    return report
