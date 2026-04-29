"""
scene_keyword_guarantor.py
==========================
When the user prompt mentions specific outdoor scene elements (ocean,
mountain, forest, trees, desert, beach) but no complex environment
model was fetched, synthesize stylized procedural geometry so the scene
actually LOOKS like what the prompt described.

Why this matters: the user asks for "horse galloping through mountains"
— if we fail to download a mountain HDRI / model, the render shows a
gray road. This module notices "mountains" in the prompt and spawns a
ring of stylized mountain cones in the distance.

Runs AFTER the complex environment importer. Safe no-op when:
 - A complex environment model is already imported (environment_* objects exist)
 - No scene-element keywords are present
 - The keyword's geometry was already placed by a template

Intentionally Blender-only (imports bpy at call time). Never raises.
"""
from __future__ import annotations

from math import cos, sin, pi
import random


# Keyword → builder function name (resolved below).
_KEYWORDS = (
    "ocean",  "sea",    "beach",
    "mountain", "mountains",
    "forest", "woods",  "trees",  "jungle",
    "desert", "dunes",
    "river",  "lake",   "pond",
    "canyon",
    "field",  "meadow", "grassland", "plains",
    "snow",   "tundra", "ice",
)


def _prompt_blob(manifest: dict) -> str:
    parts = []
    for k in ("topic", "prompt", "user_prompt"):
        v = manifest.get(k)
        if v:
            parts.append(str(v))
    recipe = manifest.get("scene_recipe") or {}
    env = recipe.get("environment") or {}
    for k in ("type", "style", "description"):
        v = env.get(k)
        if v:
            parts.append(str(v))
    plan = manifest.get("_scene_plan") or {}
    for k in ("environment", "environment_preset", "setting"):
        v = plan.get(k)
        if v:
            parts.append(str(v))
    return " ".join(parts).lower()


def _has_complex_environment(bpy) -> bool:
    """True if the complex env importer already placed a large scene model."""
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        if obj.name.lower().startswith("environment_"):
            return True
    return False


def _has_named_prefix(bpy, prefix: str) -> bool:
    for obj in bpy.data.objects:
        if obj.name.startswith(prefix):
            return True
    return False


# ═════════════════════════════════════════════════════════════════════════
# Geometry builders
# ═════════════════════════════════════════════════════════════════════════

def _make_simple_mat(bpy, name: str, color, roughness=0.7, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = metallic
    except Exception:
        pass
    return mat


def _build_mountains(bpy) -> int:
    """A ring of stylized mountain cones on the horizon."""
    if _has_named_prefix(bpy, "environment_mountain_"):
        return 0
    mat_rock = _make_simple_mat(bpy, "env_mountain_mat", (0.35, 0.32, 0.28), roughness=0.85)
    mat_snow = _make_simple_mat(bpy, "env_mountain_snow", (0.95, 0.97, 1.0), roughness=0.4)
    count = 12
    radius = 80.0
    built = 0
    rnd = random.Random(42)
    for i in range(count):
        angle = (i / count) * 2 * pi
        # Jitter radius/height so mountains read as natural.
        r = radius * (0.8 + rnd.random() * 0.6)
        x = r * cos(angle)
        y = r * sin(angle)
        h = 16.0 + rnd.random() * 22.0
        base_r = 10.0 + rnd.random() * 8.0
        try:
            bpy.ops.mesh.primitive_cone_add(
                radius1=base_r, radius2=0.0, depth=h,
                location=(x, y, h * 0.5),
            )
            m = bpy.context.object
            m.name = f"environment_mountain_{i}"
            if m.data.materials:
                m.data.materials[0] = mat_rock
            else:
                m.data.materials.append(mat_rock)
            built += 1
            # Snow cap — smaller cone at the top.
            if h > 24 and rnd.random() > 0.35:
                snow_h = h * 0.25
                bpy.ops.mesh.primitive_cone_add(
                    radius1=base_r * 0.35, radius2=0.0, depth=snow_h,
                    location=(x, y, h - snow_h * 0.5 + 0.5),
                )
                s = bpy.context.object
                s.name = f"environment_mountain_snow_{i}"
                if s.data.materials:
                    s.data.materials[0] = mat_snow
                else:
                    s.data.materials.append(mat_snow)
                built += 1
        except Exception as e:
            print(f"[SCENE_KW] mountain {i} failed: {e}", flush=True)
    print(f"[SCENE_KW] mountains: built {built} objects", flush=True)
    return built


def _build_ocean(bpy) -> int:
    """A massive flat blue plane around the scene — stand-in ocean."""
    if _has_named_prefix(bpy, "environment_ocean"):
        return 0
    mat = _make_simple_mat(bpy, "env_ocean_mat", (0.04, 0.18, 0.38), roughness=0.15, metallic=0.05)
    try:
        bpy.ops.mesh.primitive_plane_add(size=500.0, location=(0, 0, -0.05))
        o = bpy.context.object
        o.name = "environment_ocean"
        if o.data.materials:
            o.data.materials[0] = mat
        else:
            o.data.materials.append(mat)
        print("[SCENE_KW] ocean: built 1 object", flush=True)
        return 1
    except Exception as e:
        print(f"[SCENE_KW] ocean failed: {e}", flush=True)
        return 0


def _build_trees(bpy, count=14, radius_range=(25.0, 65.0)) -> int:
    """Scatter stylized tree-cones (trunk cylinder + foliage cone)."""
    if _has_named_prefix(bpy, "environment_tree_"):
        return 0
    trunk_mat = _make_simple_mat(bpy, "env_trunk_mat", (0.23, 0.14, 0.08), roughness=0.85)
    leaves_mat = _make_simple_mat(bpy, "env_leaves_mat", (0.12, 0.35, 0.15), roughness=0.7)
    built = 0
    rnd = random.Random(7)
    for i in range(count):
        angle = rnd.random() * 2 * pi
        r = radius_range[0] + rnd.random() * (radius_range[1] - radius_range[0])
        x = r * cos(angle)
        y = r * sin(angle)
        trunk_h = 2.0 + rnd.random() * 3.0
        foliage_h = 3.0 + rnd.random() * 4.0
        try:
            bpy.ops.mesh.primitive_cylinder_add(
                radius=0.35, depth=trunk_h, location=(x, y, trunk_h * 0.5),
            )
            t = bpy.context.object
            t.name = f"environment_tree_trunk_{i}"
            if t.data.materials:
                t.data.materials[0] = trunk_mat
            else:
                t.data.materials.append(trunk_mat)
            bpy.ops.mesh.primitive_cone_add(
                radius1=1.4 + rnd.random() * 0.6, radius2=0.0, depth=foliage_h,
                location=(x, y, trunk_h + foliage_h * 0.5),
            )
            f = bpy.context.object
            f.name = f"environment_tree_leaves_{i}"
            if f.data.materials:
                f.data.materials[0] = leaves_mat
            else:
                f.data.materials.append(leaves_mat)
            built += 2
        except Exception as e:
            print(f"[SCENE_KW] tree {i} failed: {e}", flush=True)
    print(f"[SCENE_KW] trees: built {built} objects", flush=True)
    return built


def _build_desert_dunes(bpy) -> int:
    """Rolling sand dunes as low flat spheres."""
    if _has_named_prefix(bpy, "environment_dune_"):
        return 0
    mat = _make_simple_mat(bpy, "env_dune_mat", (0.85, 0.7, 0.45), roughness=0.85)
    rnd = random.Random(11)
    built = 0
    for i in range(18):
        angle = rnd.random() * 2 * pi
        r = 30 + rnd.random() * 40
        x = r * cos(angle)
        y = r * sin(angle)
        sx = 8 + rnd.random() * 6
        sy = 8 + rnd.random() * 6
        sz = 1.5 + rnd.random() * 2.5
        try:
            bpy.ops.mesh.primitive_uv_sphere_add(location=(x, y, 0))
            d = bpy.context.object
            d.name = f"environment_dune_{i}"
            d.scale = (sx, sy, sz)
            if d.data.materials:
                d.data.materials[0] = mat
            else:
                d.data.materials.append(mat)
            built += 1
        except Exception as e:
            print(f"[SCENE_KW] dune {i} failed: {e}", flush=True)
    print(f"[SCENE_KW] dunes: built {built} objects", flush=True)
    return built


def _build_snow_field(bpy) -> int:
    if _has_named_prefix(bpy, "environment_snow"):
        return 0
    mat = _make_simple_mat(bpy, "env_snow_mat", (0.95, 0.96, 1.0), roughness=0.35)
    try:
        bpy.ops.mesh.primitive_plane_add(size=400.0, location=(0, 0, -0.02))
        p = bpy.context.object
        p.name = "environment_snow_field"
        if p.data.materials:
            p.data.materials[0] = mat
        else:
            p.data.materials.append(mat)
        print("[SCENE_KW] snow field: built 1 object", flush=True)
        return 1
    except Exception as e:
        print(f"[SCENE_KW] snow field failed: {e}", flush=True)
        return 0


# ═════════════════════════════════════════════════════════════════════════
# Public entry point
# ═════════════════════════════════════════════════════════════════════════

def guarantee_scene_keywords(bpy, manifest: dict) -> dict:
    """
    Inspect the manifest's prompt + scene fields for scene-element
    keywords and synthesize matching procedural geometry if the scene
    doesn't already have it.

    Skips entirely if a complex environment model is present (a real
    stadium / restaurant already set the stage).

    Returns a dict {keyword: objects_built} for telemetry.
    """
    built: dict[str, int] = {}
    try:
        if _has_complex_environment(bpy):
            print("[SCENE_KW] complex env present — skipping keyword guarantor", flush=True)
            return built

        blob = _prompt_blob(manifest)
        if not blob.strip():
            return built

        # Explicit matching (longest-first for "mountains" > "mount")
        # but these are unique enough that direct "in blob" is fine.
        if "mountain" in blob:
            n = _build_mountains(bpy)
            if n:
                built["mountains"] = n
        if any(k in blob for k in ("ocean", "sea ", "beach", "shoreline", "underwater")):
            n = _build_ocean(bpy)
            if n:
                built["ocean"] = n
        if any(k in blob for k in ("forest", "woods", "jungle")):
            n = _build_trees(bpy, count=22, radius_range=(18.0, 55.0))
            if n:
                built["forest"] = n
        elif "tree" in blob or "trees" in blob:
            n = _build_trees(bpy, count=10, radius_range=(25.0, 60.0))
            if n:
                built["trees"] = n
        if any(k in blob for k in ("desert", "dunes", "sahara")):
            n = _build_desert_dunes(bpy)
            if n:
                built["desert"] = n
        if any(k in blob for k in ("snow", "arctic", "tundra", "glacier")):
            n = _build_snow_field(bpy)
            if n:
                built["snow"] = n
        # "park" and "field"/"meadow" -> trees
        if "park" in blob and "trees" not in built and "forest" not in built:
            n = _build_trees(bpy, count=8, radius_range=(18.0, 45.0))
            if n:
                built["park_trees"] = n

        if built:
            print(f"[SCENE_KW] guarantor built: {built}", flush=True)
        else:
            print("[SCENE_KW] no scene keywords detected — skipping", flush=True)
    except Exception as e:
        print(f"[SCENE_KW] guarantor crashed (non-fatal): {e}", flush=True)
    return built
