from __future__ import annotations

from math import atan, tan
from mathutils import Vector

# ---------------------------------------------------------------------------
# Per-asset-type normalization: which axis governs target_size.
# "max"   → keep current behaviour (longest dimension = target_size)
# "height"→ z-axis drives scale (characters, trees, poles)
# "width" → x-axis drives scale (flat ground planes, roads)
# ---------------------------------------------------------------------------
_AXIS_MODE: dict[str, str] = {
    "character": "height",
    "building":  "height",
    "prop":      "max",
    "car":       "max",
    "product":   "max",
    "plane":     "width",
}

# Default target sizes per asset type (Blender units ≈ metres).
# Callers can override these; they serve as sane starting points.
ASSET_TYPE_DEFAULTS: dict[str, float] = {
    "character": 1.80,   # human-scale; override per species in street_scene
    "building":  18.0,
    "prop":      1.20,
    "car":       4.50,
    "product":   0.25,
}


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


def bounds_world(objs) -> tuple:
    """Return (mins, maxs) as Vector over all MESH objects, or (None, None)."""
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    if not meshes:
        return None, None

    mins = Vector((1e9,  1e9,  1e9))
    maxs = Vector((-1e9, -1e9, -1e9))

    for obj in meshes:
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
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
    Pick the dimension that drives scale based on axis_mode.
    'height' → z, 'width' → x, 'max' → largest of all three.
    Falls back to max if the governing axis is near-zero.
    """
    if axis_mode == "height":
        dim = size.z
    elif axis_mode == "width":
        dim = size.x
    else:
        dim = max(size.x, size.y, size.z)

    # If the preferred axis is degenerate, fall back to largest dim
    if dim < 0.001:
        dim = max(size.x, size.y, size.z, 0.001)
    return max(dim, 0.001)


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
    then ground-anchor them (bottom face at ground_z) and translate to target_center.

    axis_mode: 'height' | 'width' | 'max'  (see _governing_dim)
    """
    meshes = mesh_descendants(root_objs)
    if not meshes:
        return False, []

    mins, maxs = bounds_world(meshes)
    if mins is None:
        return False, []

    size = maxs - mins
    gov_dim = _governing_dim(size, axis_mode)
    scale_factor = target_size / gov_dim

    for obj in root_objs:
        obj.scale = tuple(v * scale_factor for v in obj.scale)

    bpy.context.view_layer.update()

    # Bake scale so subsequent bounds queries are accurate
    bpy.ops.object.select_all(action="DESELECT")
    for obj in root_objs:
        try:
            obj.select_set(True)
        except Exception:
            pass
    if root_objs:
        bpy.context.view_layer.objects.active = root_objs[0]
        try:
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        except Exception as e:
            print(f"DEBUG normalize_root_group: transform_apply failed: {e}", flush=True)

    bpy.context.view_layer.update()

    # Re-query bounds after bake; if bake failed, this still gives
    # post-scale bounds rather than pre-scale bounds
    meshes = mesh_descendants(root_objs)
    mins2, maxs2 = bounds_world(meshes)
    if mins2 is None:
        return False, []

    center2 = (mins2 + maxs2) * 0.5
    dx = target_center[0] - center2.x
    dy = target_center[1] - center2.y
    dz = ground_z - mins2.z   # pin bottom face to ground_z

    for obj in root_objs:
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz

    bpy.context.view_layer.update()
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
    Pass axis_mode to control which axis drives scale (see normalize_root_group).
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
) -> bool:
    """
    Position cam so that the horizontal spread of meshes fills the frame
    at fill_factor coverage.  Camera height tracks the actual subject midpoint
    rather than a hardcoded offset.

    fill_factor: 0.80 leaves comfortable breathing room (was 0.95 — too tight)
    height_bias: fraction of bbox height where the look-at target is placed
    min_distance: never pull camera closer than this (prevents extreme macro)
    """
    mins, maxs = bounds_world(meshes)
    if mins is None:
        return False

    size = maxs - mins
    center = (mins + maxs) * 0.5

    # Look-at target sits at height_bias fraction of the bounding box height
    target_z = mins.z + size.z * height_bias
    target.location = (center.x, center.y, target_z)

    # Use the camera's actual lens/sensor to compute horizontal FOV
    lens_mm   = max(cam.data.lens,         1.0)
    sensor_mm = max(cam.data.sensor_width, 1.0)
    h_fov = 2.0 * atan((sensor_mm * 0.5) / lens_mm)

    # Drive distance from the HORIZONTAL spread of subjects (x dimension)
    # so a wide group of three cats stays in frame rather than being clipped.
    # Use max(x_span, z_span) so we don't under-frame a tall single subject.
    frame_span = max(size.x, size.z, 0.001)
    distance = (frame_span / fill_factor) / max(0.001, 2.0 * tan(h_fov * 0.5))
    distance = max(distance, min_distance)

    # Camera height sits at the vertical midpoint of the subjects
    cam_z = mins.z + size.z * 0.5

    cam.location = (
        center.x + side_offset,
        center.y - distance,
        cam_z,
    )

    print(
        f"DEBUG frame_camera | center={center} size={size} "
        f"frame_span={frame_span:.2f} distance={distance:.2f} cam={cam.location}",
        flush=True,
    )
    return True


def combined_meshes(*groups) -> list:
    out: list = []
    for g in groups:
        out.extend(g or [])
    return out
