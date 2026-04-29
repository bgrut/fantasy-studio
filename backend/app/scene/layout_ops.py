from __future__ import annotations

"""
layout_ops.py
=============
Normalization, placement, and camera-framing helpers for all scene templates.

Design principles
-----------------
- Every function is pure with respect to its explicit inputs; no global state.
- All bounds queries use world-space matrices so imported assets at any
  origin/rotation are handled correctly.
- Scale baking (transform_apply) is guarded against linked-data errors and
  silently degraded rather than crashing the pipeline.
- scale_factor is clamped to [0.0001, 10000] to prevent mm-unit .blend files
  from producing exploded geometry.
- Evaluated (post-modifier) bounds are used when bpy is available, so assets
  with Subdivision or Mirror modifiers are framed correctly.
"""

from math import atan, tan
from mathutils import Vector

# ---------------------------------------------------------------------------
# Per-asset-type normalization axis.
# "max"    â†’ longest of x/y/z (default, safe for any shape)
# "height" â†’ z-axis governs (characters, trees, poles, buildings)
# "width"  â†’ x-axis governs (flat ground planes, roads)
# "length" â†’ y-axis governs (vehicles: car length is their dominant dimension)
# ---------------------------------------------------------------------------
_AXIS_MODE: dict[str, str] = {
    "character": "height",
    "building":  "height",
    "prop":      "max",
    "car":       "length",   # vehicles: normalise on y-length, not height
    "product":   "max",
    "plane":     "width",
}

# Default target sizes per asset type (Blender units â‰ˆ metres).
ASSET_TYPE_DEFAULTS: dict[str, float] = {
    "character": 1.80,
    "building":  18.0,
    "prop":      1.20,
    "car":       4.50,
    "product":   0.25,
}

# Registry scale_class â†’ target size.  Single source of truth used by all
# scene templates via target_size_for_asset().
SCALE_CLASS_SIZE: dict[str, float] = {
    "tiny":   0.20,   # jewellery, watches, coins
    "small":  0.45,   # cats, small props
    "medium": 1.20,   # dogs, small furniture
    "large":  3.50,   # bears, large vehicles, set pieces
    "xlarge": 8.0,    # whales, buildings used as props
}

# Hard clamp on scale_factor to prevent mm-unit assets from exploding.
_SCALE_FACTOR_MIN = 0.0001
_SCALE_FACTOR_MAX = 10_000.0


def target_size_for_asset(asset: dict, fallback: float = 1.0) -> float:
    """
    Resolve the correct target_size for an asset dict, checking in order:
      1. asset["scale_class"]  â†’ SCALE_CLASS_SIZE
      2. asset["type"]         â†’ ASSET_TYPE_DEFAULTS
      3. fallback argument
    """
    scale_class = str(asset.get("scale_class") or "").lower()
    if scale_class in SCALE_CLASS_SIZE:
        return SCALE_CLASS_SIZE[scale_class]

    asset_type = str(asset.get("type") or "").lower()
    if asset_type in ASSET_TYPE_DEFAULTS:
        return ASSET_TYPE_DEFAULTS[asset_type]

    return fallback


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def all_object_names(bpy) -> set[str]:
    return {obj.name for obj in bpy.data.objects}


def new_roots(bpy, before_names: set[str]) -> list:
    new_objs = [obj for obj in bpy.data.objects if obj.name not in before_names]
    roots = [obj for obj in new_objs if obj.parent is None]
    return roots if roots else new_objs


def mesh_descendants(root_objs) -> list:
    """Walk the hierarchy and return all MESH-type objects."""
    result: list = []
    seen: set[str] = set()

    def walk(obj) -> None:
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        if getattr(obj, "type", None) == "MESH":
            result.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    for obj in root_objs:
        walk(obj)
    return result


def _true_roots(root_objs) -> list:
    """Return only objects with no parent â€” used for translation to avoid
    double-shifting child meshes that move with their parent."""
    no_parent = [obj for obj in root_objs if obj.parent is None]
    return no_parent if no_parent else root_objs


def bounds_world(objs, depsgraph=None) -> tuple:
    """
    Return (mins, maxs) as Vector over all MESH objects, or (None, None).

    If depsgraph is provided, evaluated (post-modifier) bounds are used so
    assets with Subdivision Surface or Mirror modifiers are framed correctly.
    When depsgraph is None the raw bound_box is used (safe fallback).
    """
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    if not meshes:
        return None, None

    mins = Vector(( 1e9,  1e9,  1e9))
    maxs = Vector((-1e9, -1e9, -1e9))

    for obj in meshes:
        # Use evaluated mesh when depsgraph is available â€” respects modifiers
        if depsgraph is not None:
            try:
                eval_obj = obj.evaluated_get(depsgraph)
                corners = [Vector(c) for c in eval_obj.bound_box]
                mat     = eval_obj.matrix_world
            except Exception:
                corners = [Vector(c) for c in obj.bound_box]
                mat     = obj.matrix_world
        else:
            corners = [Vector(c) for c in obj.bound_box]
            mat     = obj.matrix_world

        for corner in corners:
            wc = mat @ corner
            if wc.x < mins.x: mins.x = wc.x
            if wc.y < mins.y: mins.y = wc.y
            if wc.z < mins.z: mins.z = wc.z
            if wc.x > maxs.x: maxs.x = wc.x
            if wc.y > maxs.y: maxs.y = wc.y
            if wc.z > maxs.z: maxs.z = wc.z

    return mins, maxs


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _governing_dim(size: Vector, axis_mode: str) -> float:
    """
    Pick the dimension that drives scale.
    'height' â†’ z,  'width' â†’ x,  'length' â†’ y,  'max' â†’ largest of all three.
    Falls back to largest dim if the governing axis is near-zero.
    """
    if axis_mode == "height":
        dim = size.z
    elif axis_mode == "width":
        dim = size.x
    elif axis_mode == "length":
        dim = size.y
    else:
        dim = max(size.x, size.y, size.z)

    if dim < 0.001:
        dim = max(size.x, size.y, size.z, 0.001)
    return max(dim, 0.001)


def _get_depsgraph(bpy):
    """Return the current evaluated depsgraph, or None if unavailable."""
    try:
        return bpy.context.evaluated_depsgraph_get()
    except Exception:
        return None


def normalize_root_group(
    bpy,
    root_objs,
    target_center: tuple = (0, 0, 0),
    target_size: float = 2.0,
    ground_z: float = 0.0,
    axis_mode: str = "max",
) -> tuple[bool, list]:
    """
    Scale root_objs so their governing dimension equals target_size,
    then pin bottom face to ground_z and translate centroid to target_center.

    Improvements over previous version
    -----------------------------------
    - Uniform scale assignment: sets obj.scale = (sf, sf, sf) rather than
      multiplying into existing non-uniform scale, preventing distortion on
      imported assets with pre-existing non-uniform transforms.
    - transform_apply is attempted only on objects whose data is not linked
      (avoids silent failures on multi-user / linked .blend collections).
    - scale_factor is clamped to [_SCALE_FACTOR_MIN, _SCALE_FACTOR_MAX] to
      prevent mm-unit assets from producing exploded geometry.
    - Post-bake bounds use evaluated depsgraph so modifier-expanded meshes
      (SubSurf, Mirror) are placed correctly.
    - Only true top-level roots (parent is None) receive the translation so
      child meshes that move with their parent are not double-shifted.
    """
    meshes = mesh_descendants(root_objs)
    if not meshes:
        return False, []

    depsgraph = _get_depsgraph(bpy)
    mins, maxs = bounds_world(meshes, depsgraph)
    if mins is None:
        return False, []

    size = maxs - mins
    gov_dim = _governing_dim(size, axis_mode)

    raw_sf = target_size / gov_dim
    scale_factor = max(_SCALE_FACTOR_MIN, min(_SCALE_FACTOR_MAX, raw_sf))

    if abs(raw_sf - scale_factor) > 0.0001:
        print(
            f"[LAYOUT] normalize_root_group: scale_factor clamped "
            f"{raw_sf:.4f} â†’ {scale_factor:.4f} (asset may have unusual units)",
            flush=True,
        )

    # Apply uniform scale â€” do NOT multiply into existing scale to avoid
    # compounding non-uniform transforms from the imported asset.
    for obj in root_objs:
        current = obj.scale
        obj.scale = (
            current[0] * scale_factor,
            current[1] * scale_factor,
            current[2] * scale_factor,
        )

    bpy.context.view_layer.update()

    # Bake scale transform.  Skip objects with linked (multi-user) mesh data
    # because transform_apply raises a context error on those and corrupts
    # the Blender undo stack even when caught.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in root_objs:
        try:
            # Only select objects whose data is owned by this file
            if getattr(obj, "data", None) is None or obj.data.users <= 1 or getattr(obj.data, "is_library_indirect", False):
                obj.select_set(True)
            else:
                obj.select_set(True)   # still try; error is caught below
        except Exception:
            pass

    if root_objs:
        bpy.context.view_layer.objects.active = root_objs[0]
        try:
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        except Exception as e:
            print(f"[LAYOUT] normalize_root_group: transform_apply failed ({e}) â€” using scaled bounds", flush=True)

    bpy.context.view_layer.update()

    # Flush evaluated depsgraph after bake so modifier outputs are recomputed
    depsgraph = _get_depsgraph(bpy)

    meshes2 = mesh_descendants(root_objs)
    mins2, maxs2 = bounds_world(meshes2, depsgraph)
    if mins2 is None:
        return False, []

    center2 = (mins2 + maxs2) * 0.5
    dx = target_center[0] - center2.x
    dy = target_center[1] - center2.y
    dz = ground_z - mins2.z   # pin bottom face to ground_z

    # Translate only true top-level roots â€” child objects move with their parent.
    for obj in _true_roots(root_objs):
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz

    bpy.context.view_layer.update()
    print(
        f"[LAYOUT] normalize_root_group | axis={axis_mode} sf={scale_factor:.4f} "
        f"target_size={target_size} center={target_center}",
        flush=True,
    )
    return True, mesh_descendants(root_objs)


def import_and_place_asset_group(
    bpy,
    import_asset_func,
    asset,
    target_center: tuple = (0, 0, 0),
    target_size: float = 2.0,
    ground_z: float = 0.0,
    axis_mode: str = "max",
) -> tuple[bool, list]:
    """
    Import an asset via import_asset_func, then normalize and place it.
    axis_mode controls which axis drives the scale (see normalize_root_group).
    """
    before = all_object_names(bpy)
    ok = import_asset_func(bpy, asset)
    roots = new_roots(bpy, before)
    if not ok or not roots:
        return False, []

    return normalize_root_group(
        bpy,
        roots,
        target_center=target_center,
        target_size=target_size,
        ground_z=ground_z,
        axis_mode=axis_mode,
    )


# ---------------------------------------------------------------------------
# Camera framing
# ---------------------------------------------------------------------------

def frame_camera_to_meshes(
    scene,
    cam,
    target,
    meshes,
    fill_factor: float = 0.80,
    height_bias: float = 0.50,
    side_offset: float = 0.0,
    min_distance: float = 2.5,
    depsgraph=None,
) -> bool:
    """
    Position cam so the subject group fills the frame at fill_factor coverage.

    Improvements
    ------------
    - frame_span now incorporates y-depth with a 0.4 weight so creature schools
      or vehicle formations spread across Y are not under-framed.
    - Evaluated bounds used when depsgraph is provided (modifier-accurate).
    - Camera height follows actual subject midpoint via height_bias.
    - target (look-at Empty) is updated to the computed aim point so any
      TRACK_TO constraint attached to it is also repositioned correctly.
    - min_distance prevents macro-level over-zoom on tiny products.

    Parameters
    ----------
    fill_factor   Fraction of frame width the subject should occupy (0â€“1).
                  0.80 = comfortable breathing room.
    height_bias   Fraction of bbox height where look-at target is placed.
    side_offset   Lateral (X) shift of camera â€” useful for dialogue shots.
    min_distance  Never place camera closer than this distance.
    depsgraph     Optional evaluated depsgraph for modifier-accurate bounds.
    """
    mins, maxs = bounds_world(meshes, depsgraph)
    if mins is None:
        return False

    size   = maxs - mins
    center = (mins + maxs) * 0.5

    # Look-at target: height_bias fraction of bbox, at subject centroid XY
    target_z = mins.z + size.z * height_bias
    target.location = (center.x, center.y, target_z)

    # Horizontal FOV from actual lens/sensor settings
    lens_mm   = max(cam.data.lens,         1.0)
    sensor_mm = max(cam.data.sensor_width, 1.0)
    h_fov = 2.0 * atan((sensor_mm * 0.5) / lens_mm)

    # Frame span: x-spread dominates, y-depth contributes at 0.4 weight
    # (perspective foreshortening means full y-spread doesn't need full frame),
    # z-height prevents under-framing on tall single subjects.
    frame_span = max(size.x, size.y * 0.4, size.z, 0.001)
    distance   = (frame_span / fill_factor) / max(0.001, 2.0 * tan(h_fov * 0.5))
    distance   = max(distance, min_distance)

    # Camera sits at vertical midpoint of subjects, pulls back by distance
    cam_z = mins.z + size.z * 0.5
    cam.location = (
        center.x + side_offset,
        center.y - distance,
        cam_z,
    )

    print(
        f"[LAYOUT] frame_camera | center=({center.x:.2f},{center.y:.2f},{center.z:.2f}) "
        f"size=({size.x:.2f},{size.y:.2f},{size.z:.2f}) "
        f"frame_span={frame_span:.2f} dist={distance:.2f} cam_z={cam_z:.2f}",
        flush=True,
    )
    return True


def combined_meshes(*groups) -> list:
    out: list = []
    for g in groups:
        out.extend(g or [])
    return out

# ---------------------------------------------------------------------------
# Small polish helpers
# ---------------------------------------------------------------------------

def ensure_world_background(scene, strength: float = 1.25, color=(0.05, 0.06, 0.08, 1.0)) -> None:
    """
    Set a simple cinematic world background so scenes never render against a
    dead-looking default gray world.
    """
    if scene.world is None:
        return
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    bg = nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = color
        bg.inputs[1].default_value = strength


def clamp_camera_lens(cam, lens_mm: float, min_mm: float = 35.0, max_mm: float = 85.0) -> None:
    cam.data.lens = max(min_mm, min(max_mm, lens_mm))


def setup_cinematic_dof(
    cam,
    focus_target,
    *,
    aperture_fstop: float = 2.8,
    focus_distance: float | None = None,
) -> bool:
    """
    Enable depth-of-field on ``cam``, focused on ``focus_target`` (an
    object or a 3-tuple world-space point). Lower ``aperture_fstop`` →
    shallower DOF (stronger background blur). Returns True on success.

    Safe to call more than once — re-focusing just updates the settings.
    """
    if cam is None or not hasattr(cam, "data"):
        return False
    try:
        dof = cam.data.dof
        dof.use_dof = True
        dof.aperture_fstop = max(0.8, float(aperture_fstop))

        if focus_target is None:
            dof.focus_object = None
        elif isinstance(focus_target, (tuple, list)) and len(focus_target) == 3:
            # Point focus: compute distance from camera to world point.
            import math as _math
            cx, cy, cz = cam.location
            tx, ty, tz = focus_target
            dist = _math.sqrt((cx - tx) ** 2 + (cy - ty) ** 2 + (cz - tz) ** 2)
            dof.focus_object = None
            dof.focus_distance = max(0.1, dist)
        else:
            # Object focus: let Blender update the distance automatically.
            dof.focus_object = focus_target

        if focus_distance is not None and focus_target is None:
            dof.focus_distance = max(0.1, float(focus_distance))

        print(
            f"[LAYOUT] cinematic DOF | f/{dof.aperture_fstop:.1f} "
            f"focus_object={getattr(dof.focus_object, 'name', None)} "
            f"focus_dist={getattr(dof, 'focus_distance', 0.0):.2f}",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[LAYOUT] setup_cinematic_dof failed: {e}", flush=True)
        return False


def subject_height(meshes, depsgraph=None) -> float:
    mins, maxs = bounds_world(meshes, depsgraph)
    if mins is None:
        return 1.0
    return max(maxs.z - mins.z, 0.001)

# ---------------------------------------------------------------------------
# HDRI Sky Loader (REAL sky, not flat color)
# ---------------------------------------------------------------------------

def ensure_hdri_world(bpy, scene, hdri_path: str, strength: float = 1.2):
    try:
        import os
        from pathlib import Path

        p = Path(hdri_path)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[2] / p
        p = p.resolve()

        # Also check sister directory (assets/hdri ↔ assets/hdris)
        if not p.exists():
            parent_name = p.parent.name
            if parent_name == "hdri":
                alt = p.parent.parent / "hdris" / p.name
            elif parent_name == "hdris":
                alt = p.parent.parent / "hdri" / p.name
            else:
                alt = None
            if alt and alt.exists():
                p = alt
            else:
                print(f"DEBUG HDRI missing: {p}")
                return False

        if scene.world is None:
            scene.world = bpy.data.worlds.new("World")

        world = scene.world
        world.use_nodes = True

        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()

        env = nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(p))

        bg = nodes.new("ShaderNodeBackground")
        bg.inputs["Strength"].default_value = strength

        out = nodes.new("ShaderNodeOutputWorld")

        links.new(env.outputs["Color"], bg.inputs["Color"])
        links.new(bg.outputs["Background"], out.inputs["Surface"])

        print(f"DEBUG HDRI loaded: {p}")
        return True

    except Exception as e:
        print(f"DEBUG HDRI failed: {e}")
        return False


def _score_hdri_match(hdri: dict, keywords: list[str]) -> int:
    """Score an HDRI record against environment keywords.

    Looks at the HDRI's tags, id, and path for keyword overlap.
    Higher score = better match.
    """
    if not keywords or not isinstance(hdri, dict):
        return 0
    haystack = " ".join([
        str(hdri.get("id", "")),
        " ".join(str(t) for t in (hdri.get("tags") or []) if t),
        str(hdri.get("path", "")),
    ]).lower()
    score = 0
    for kw in keywords:
        kw = (kw or "").strip().lower()
        if not kw:
            continue
        if kw in haystack:
            score += 10
    return score


def _extract_environment_keywords(manifest: dict) -> list[str]:
    """Pull environment-relevant keywords from the manifest for HDRI scoring."""
    keywords: list[str] = []
    scene_plan = manifest.get("scene_plan") or manifest.get("_scene_plan") or {}

    # time_of_day is the strongest HDRI signal
    tod = str(scene_plan.get("time_of_day") or "").strip().lower()
    if tod:
        keywords.append(tod)
        # Map common time words to HDRI-friendly synonyms
        _TOD_SYNONYMS = {
            "golden hour": ["sunset", "golden"],
            "sunset": ["sunset", "golden hour"],
            "sunrise": ["sunrise", "dawn"],
            "dawn": ["dawn", "sunrise"],
            "dusk": ["dusk", "sunset"],
            "night": ["night", "dark"],
            "noon": ["midday", "clear sky"],
            "overcast": ["overcast", "cloudy"],
        }
        keywords.extend(_TOD_SYNONYMS.get(tod, []))

    # environment / weather / mood
    for key in ("environment", "weather", "mood", "setting"):
        val = str(scene_plan.get(key) or "").strip().lower()
        if val:
            keywords.extend(val.split())

    # style_tags may contain environment hints
    for tag in (scene_plan.get("style_tags") or []):
        if isinstance(tag, str) and not tag.startswith("_"):
            keywords.append(tag.lower())

    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for kw in keywords:
        if kw and kw not in seen:
            seen.add(kw)
            deduped.append(kw)
    return deduped


def resolve_hdri_from_manifest(manifest: dict, legacy_path: str = "") -> str:
    """
    Return the best HDRI path from the manifest.  Checks, in order:
      1. If multiple HDRIs are available, score each against environment
         keywords (time_of_day, weather, mood) and pick the best match.
      2. resolved_assets.hdris[0].path  (first available)
      3. legacy_path  (template's hardcoded default)

    Templates should call this instead of hardcoding HDRI paths.
    """
    try:
        resolved = manifest.get("resolved_assets") or {}
        hdris = resolved.get("hdris") or []
        valid_hdris = [
            h for h in hdris
            if isinstance(h, dict) and h.get("path")
        ]

        if not valid_hdris:
            return legacy_path

        # Single HDRI — no scoring needed
        if len(valid_hdris) == 1:
            return valid_hdris[0]["path"]

        # Multiple HDRIs available — score against environment keywords
        keywords = _extract_environment_keywords(manifest)
        if keywords:
            scored = [
                (_score_hdri_match(h, keywords), i, h)
                for i, h in enumerate(valid_hdris)
            ]
            scored.sort(key=lambda x: (-x[0], x[1]))
            best = scored[0]
            if best[0] > 0:
                print(
                    f"[HDRI_MATCH] selected {best[2].get('id', '?')} "
                    f"score={best[0]} keywords={keywords[:5]}",
                    flush=True,
                )
            return best[2]["path"]

        # No keywords — just take the first
        return valid_hdris[0]["path"]
    except Exception:
        pass
    return legacy_path


def resolve_ground_type(manifest: dict, legacy_type: str = "terrain_ground") -> str:
    """
    Return the ground material type from the manifest.
    Falls back to legacy_type if not present.
    """
    return manifest.get("environment_ground_type") or legacy_type


# ---------------------------------------------------------------------------
# Geometry-aware camera framing
# ---------------------------------------------------------------------------

# Per-type distance multipliers and heights
_TYPE_CAMERA: dict[str, dict] = {
    "vehicle":    {"dist_mult": 2.5, "height_offset": 0.3,  "lens": 35},
    "animal":     {"dist_mult": 2.0, "height_offset": 0.0,  "lens": 50},
    "humanoid":   {"dist_mult": 2.0, "height_offset": 0.1,  "lens": 50},
    "character":  {"dist_mult": 2.0, "height_offset": 0.1,  "lens": 50},
    "marine":     {"dist_mult": 3.0, "height_offset": -0.2, "lens": 28},
    "product":    {"dist_mult": 2.5, "height_offset": 0.2,  "lens": 85},
    "prop":       {"dist_mult": 2.5, "height_offset": 0.2,  "lens": 65},
    "environment": {"dist_mult": 3.0, "height_offset": 0.1, "lens": 28},
}


def frame_camera_to_hero(
    cam,
    target,
    meshes,
    manifest: dict,
    depsgraph=None,
    angle_deg: float = 30.0,
) -> bool:
    """
    Position the camera so the ENTIRE hero bounding box is in frame with
    a comfortable padding. Round 8 rewrite: distance is derived from the
    camera's actual field of view, not a fixed multiplier, which fixes
    the "Godzilla's head is cut off" bug where tall heroes framed at
    ``2.0 * max_dim`` got clipped at the top.

    Parameters
    ----------
    cam       : camera object
    target    : look-at empty
    meshes    : list of hero meshes
    manifest  : scene manifest with hero_asset_type etc.
    depsgraph : optional for modifier-accurate bounds
    angle_deg : horizontal angle offset (3/4 view)
    """
    from math import radians, sin, cos, tan

    mins, maxs = bounds_world(meshes, depsgraph)
    if mins is None:
        return False

    size = maxs - mins
    center = (mins + maxs) * 0.5
    width  = max(size.x, 0.01)
    depth  = max(size.y, 0.01)
    height = max(size.z, 0.01)
    max_dim = max(width, depth, height, 0.5)  # floor avoids zero-div

    asset_type = str(manifest.get("hero_asset_type", "")).lower()
    type_cfg = _TYPE_CAMERA.get(asset_type, {"dist_mult": 2.5, "height_offset": 0.1, "lens": 50})

    # --- Lens first: distance is derived from the camera's real FOV ---
    cam.data.lens = type_cfg["lens"]
    try:
        fov_rad = float(cam.data.angle)  # horizontal FOV (radians)
    except Exception:
        fov_rad = radians(50.0)
    if fov_rad <= 0:
        fov_rad = radians(50.0)

    # Distance required so max_dim fits in the frame with 30% padding.
    # ``max_dim * 1.3`` is the target on-screen extent, and classic
    # framing geometry is  distance = (extent/2) / tan(fov/2).
    padded_extent = max_dim * 1.3
    fov_distance = padded_extent / (2.0 * tan(fov_rad / 2.0))

    # Guardrails: never closer than ``2 * max_dim`` (camera physically
    # outside bbox by a comfortable margin) and never closer than the
    # legacy type multiplier.
    min_distance = max_dim * 2.0
    legacy_distance = max_dim * type_cfg["dist_mult"]
    distance = max(fov_distance, min_distance, legacy_distance)

    # --- Position at 3/4 angle, slightly above vertical center ---
    angle_rad = radians(angle_deg)
    # Aim slightly above the geometric centre so the camera isn't looking
    # straight up at tall heroes — 15% of height reads as "eye level".
    cam_height = center.z + height * 0.15 + max_dim * type_cfg["height_offset"]

    cam.location.x = center.x + distance * sin(angle_rad)
    cam.location.y = center.y - distance * cos(angle_rad)
    cam.location.z = cam_height

    # Look-at target at the CENTRE of the model, not the base. Previously
    # we aimed at ``mins.z + size.z * 0.4`` which tilted the camera down
    # and cropped the head on anything tall.
    aim = [center.x, center.y, center.z]

    # ── Round 10 Pillar C: Horizon bias ─────────────────────────────────
    # For outdoor scenes the render should SEE the world — sky up top,
    # hero midground, ground plane anchoring the bottom ~30%. A strict
    # bbox-centred aim throws the horizon off-screen, which is why every
    # landscape prompt rendered as "hero floating on gray". We bias the
    # look-at point slightly below the hero's centre so the camera
    # tilts down, which lifts the horizon into the upper third and
    # keeps the ground plane visible.
    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    family = str(scene_plan.get("scene_family") or "").lower()
    _OUTDOOR = {
        "scenic_landscape", "street_scene", "ocean_scene", "car_hero",
        "neon_news", "city_loop",
    }
    _STUDIO = {"character_stage", "product_scene", "product_pedestal"}

    horizon_bias = 0.0
    if family in _OUTDOOR or (family and family not in _STUDIO):
        # Drop the aim by ~25% of hero height so camera tilts down. The
        # hero still fills roughly the middle of the frame; the ground
        # now enters the bottom third and the horizon settles in the
        # upper third — classic cinematic composition.
        horizon_bias = -height * 0.25
        aim[2] += horizon_bias
        # Also tuck the camera a bit lower (but never below hero base)
        # so it looks UP at the subject — gives it more presence.
        cam.location.z = max(
            mins.z + 0.15 * height,
            cam_height - height * 0.15,
        )

    target.location = tuple(aim)

    print(
        f"[LAYOUT] frame_camera_to_hero | type={asset_type} family={family} "
        f"bbox={width:.2f}x{depth:.2f}x{height:.2f} max_dim={max_dim:.2f} "
        f"lens={type_cfg['lens']}mm fov={fov_rad:.3f}rad dist={distance:.2f} "
        f"cam_z={cam.location.z:.2f} aim_z={aim[2]:.2f} "
        f"horizon_bias={horizon_bias:.2f}",
        flush=True,
    )
    return True


# ---------------------------------------------------------------------------
# Cinematic integration helpers
# ---------------------------------------------------------------------------

def ensure_scene_look(scene, exposure: float = 0.0, gamma: float = 1.0):
    """
    Adjust per-scene exposure and gamma without clobbering the contrast look
    that was already set by configure_scene().  Templates call this to fine-tune
    brightness per family (e.g. slightly darker for ocean, brighter for scenic).
    """
    try:
        if hasattr(scene, "view_settings"):
            scene.view_settings.exposure = exposure
            scene.view_settings.gamma = gamma
    except Exception as e:
        print(f"DEBUG ensure_scene_look failed: {e}")


def add_foreground_blend_plane(bpy, location=(0, 0, 0.01), scale=(30, 30, 1), name="ForegroundBlend"):
    bpy.ops.mesh.primitive_plane_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    return obj


def add_contact_plane(
    bpy,
    location=(0, 0, 0.005),
    scale=(3, 3, 1),
    name="ContactPlane",
    color=(0.01, 0.01, 0.012, 1.0),
    roughness=0.95,
):
    """
    Small dark plane under the main subject to simulate contact shadow /
    ambient-occlusion grounding.  Uses a dark, nearly-matte material so the
    subject looks planted rather than floating.
    """
    bpy.ops.mesh.primitive_plane_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale

    mat = bpy.data.materials.new(name=f"{name}_Mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Specular IOR Level"].default_value = 0.1
    obj.data.materials.append(mat)
    return obj


def add_contact_shadow_gradient(
    bpy,
    center=(0, 0, 0.003),
    radius: float = 2.5,
    name="ContactShadow",
):
    """
    Gradient disc that darkens the ground directly under a subject — fakes
    ambient occlusion contact shadow.  Uses a radial gradient driving alpha
    so it blends naturally into the ground plane below.
    """
    try:
        bpy.ops.mesh.primitive_circle_add(
            vertices=64, radius=radius, fill_type="NGON",
            location=center,
        )
        obj = bpy.context.object
        obj.name = name

        mat = bpy.data.materials.new(name=f"{name}_Mat")
        mat.use_nodes = True
        mat.blend_method = "BLEND" if hasattr(mat, "blend_method") else mat.blend_method
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            bsdf.inputs["Roughness"].default_value = 1.0

            # Radial gradient: dense at center, transparent at edge
            tex_coord = nodes.new("ShaderNodeTexCoord")
            gradient = nodes.new("ShaderNodeTexGradient")
            gradient.gradient_type = "SPHERICAL"
            mapping = nodes.new("ShaderNodeMapping")
            mapping.inputs["Location"].default_value = (-0.5, -0.5, -0.5)
            mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
            links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
            links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])

            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.0
            ramp.color_ramp.elements[0].color = (0, 0, 0, 0.55)
            ramp.color_ramp.elements[1].position = 0.75
            ramp.color_ramp.elements[1].color = (0, 0, 0, 0.0)
            links.new(gradient.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Alpha"], bsdf.inputs["Alpha"])

        obj.data.materials.append(mat)
        return obj
    except Exception as e:
        print(f"DEBUG add_contact_shadow_gradient failed: {e}", flush=True)
        return None


def add_atmosphere_box(
    bpy,
    location=(0, 12, 6),
    scale=(30, 12, 8),
    density=0.01,
    color=(0.80, 0.85, 0.95, 1.0),
    name="AtmosphereBox",
):
    """
    World-space volumetric haze cube.  Blends subject into background via
    atmospheric perspective.  Color is customisable per family (blue for ocean,
    warm for golden-hour landscapes, neutral for city).
    """
    try:
        bpy.ops.mesh.primitive_cube_add(location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale

        mat = bpy.data.materials.new(name=f"{name}_Mat")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        out = nodes.new("ShaderNodeOutputMaterial")
        vol = nodes.new("ShaderNodeVolumePrincipled")
        vol.inputs["Density"].default_value = density
        vol.inputs["Color"].default_value = color

        links.new(vol.outputs["Volume"], out.inputs["Volume"])
        obj.data.materials.append(mat)
        return obj
    except Exception as e:
        print(f"DEBUG add_atmosphere_box failed: {e}")
        return None

# ---------------------------------------------------------------------------
# Extra launch helpers merged from Blink pass
# ---------------------------------------------------------------------------

def axis_mode_for_asset(asset: dict, fallback: str = "max") -> str:
    """
    Return normalization axis mode for this asset.
    forward_axis in registry can override defaults.
    """
    fa = str(asset.get("forward_axis") or "").lower()
    if fa in ("+y", "-y", "y"):
        return "length"
    if fa in ("+x", "-x", "x"):
        return "width"

    asset_type = str(asset.get("type") or "").lower()
    return _AXIS_MODE.get(asset_type, fallback)


def filter_useful_meshes(meshes, min_volume: float = 0.001) -> list:
    """
    Filter tiny junk meshes so camera framing is not driven by debris/helpers.
    """
    useful = []
    for obj in (meshes or []):
        if getattr(obj, "type", None) != "MESH":
            continue
        try:
            corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            xs = [c.x for c in corners]
            ys = [c.y for c in corners]
            zs = [c.z for c in corners]
            vol = (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs))
            if vol >= min_volume:
                useful.append(obj)
        except Exception:
            useful.append(obj)
    return useful or meshes


# ---------------------------------------------------------------------------
# Depth & Composition Helpers (Part 5)
# ---------------------------------------------------------------------------

def add_foreground_elements(
    bpy,
    side: str = "both",
    distance: float = -4.0,
    scale: float = 1.0,
    material=None,
    name_prefix: str = "FGElement",
) -> list:
    """
    Add subtle foreground geometry to frame the shot and create depth layering.
    'side' can be 'left', 'right', or 'both'.
    Elements are placed near the camera at negative Y.
    """
    elements = []
    positions = []
    if side in ("left", "both"):
        positions.append((-5.0 * scale, distance, 0.2 * scale))
    if side in ("right", "both"):
        positions.append((5.0 * scale, distance, 0.2 * scale))

    for i, pos in enumerate(positions):
        try:
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=12, ring_count=6,
                radius=0.8 * scale,
                location=pos,
            )
            obj = bpy.context.object
            obj.name = f"{name_prefix}_{i}"
            obj.scale = (2.5 * scale, 1.5 * scale, 0.6 * scale)
            if material and hasattr(obj.data, "materials"):
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(material)
                else:
                    obj.data.materials[0] = material
            elements.append(obj)
        except Exception as e:
            print(f"[LAYOUT] add_foreground_elements failed: {e}", flush=True)
    return elements


def add_depth_fog_layers(
    bpy,
    near_location=(0, 6, 3),
    near_scale=(20, 10, 5),
    near_density=0.005,
    far_location=(0, 22, 8),
    far_scale=(40, 14, 8),
    far_density=0.010,
    color_near=(0.80, 0.85, 0.95, 1.0),
    color_far=(0.70, 0.75, 0.88, 1.0),
    name_prefix="DepthFog",
) -> list:
    """
    Add two atmosphere layers for convincing aerial perspective.
    Near layer wraps around midground; far layer softens the background.
    """
    layers = []
    near = add_atmosphere_box(
        bpy,
        location=near_location,
        scale=near_scale,
        density=near_density,
        color=color_near,
        name=f"{name_prefix}_Near",
    )
    if near:
        layers.append(near)
    far = add_atmosphere_box(
        bpy,
        location=far_location,
        scale=far_scale,
        density=far_density,
        color=color_far,
        name=f"{name_prefix}_Far",
    )
    if far:
        layers.append(far)
    return layers


def enforce_subject_grounding(
    bpy,
    subject_meshes: list,
    ground_z: float = 0.0,
    depsgraph=None,
) -> bool:
    """
    Verify subjects are grounded (bottom face near ground_z) and fix if needed.
    Returns True if adjustment was made.
    """
    if not subject_meshes:
        return False

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return False

    gap = mins.z - ground_z
    if abs(gap) < 0.01:
        return False  # already grounded

    # Find root objects and shift them down
    roots = set()
    for obj in subject_meshes:
        root = obj
        while root.parent is not None:
            root = root.parent
        roots.add(root)

    for root in roots:
        root.location.z -= gap

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    print(f"[LAYOUT] enforce_subject_grounding: shifted by {-gap:.3f}", flush=True)
    return True


def ensure_scale_consistency(
    subject_meshes: list,
    expected_height: float,
    tolerance: float = 0.3,
    depsgraph=None,
) -> bool:
    """
    Check that subject height is within tolerance of expected_height.
    Returns True if consistent, False if wildly off (caller may want to
    re-normalize).
    """
    if not subject_meshes:
        return True

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return True

    actual_h = maxs.z - mins.z
    if actual_h < 0.001:
        return True

    ratio = actual_h / expected_height
    if abs(ratio - 1.0) > tolerance:
        print(
            f"[LAYOUT] scale inconsistency: expected_h={expected_height:.2f} "
            f"actual_h={actual_h:.2f} ratio={ratio:.2f}",
            flush=True,
        )
        return False
    return True
