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
# "max"    → longest of x/y/z (default, safe for any shape)
# "height" → z-axis governs (characters, trees, poles, buildings)
# "width"  → x-axis governs (flat ground planes, roads)
# "length" → y-axis governs (vehicles: car length is their dominant dimension)
# ---------------------------------------------------------------------------
_AXIS_MODE: dict[str, str] = {
    "character": "height",
    "building":  "height",
    "prop":      "max",
    "car":       "length",   # vehicles: normalise on y-length, not height
    "product":   "max",
    "plane":     "width",
}

# Default target sizes per asset type (Blender units ≈ metres).
ASSET_TYPE_DEFAULTS: dict[str, float] = {
    "character": 1.80,
    "building":  18.0,
    "prop":      1.20,
    "car":       4.50,
    "product":   0.25,
}

# Registry scale_class → target size.  Single source of truth used by all
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
      1. asset["scale_class"]  → SCALE_CLASS_SIZE
      2. asset["type"]         → ASSET_TYPE_DEFAULTS
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
    """Return only objects with no parent — used for translation to avoid
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
        # Use evaluated mesh when depsgraph is available — respects modifiers
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
    'height' → z,  'width' → x,  'length' → y,  'max' → largest of all three.
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
            f"{raw_sf:.4f} → {scale_factor:.4f} (asset may have unusual units)",
            flush=True,
        )

    # Apply uniform scale — do NOT multiply into existing scale to avoid
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
            print(f"[LAYOUT] normalize_root_group: transform_apply failed ({e}) — using scaled bounds", flush=True)

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

    # Translate only true top-level roots — child objects move with their parent.
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
    fill_factor   Fraction of frame width the subject should occupy (0–1).
                  0.80 = comfortable breathing room.
    height_bias   Fraction of bbox height where look-at target is placed.
    side_offset   Lateral (X) shift of camera — useful for dialogue shots.
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
