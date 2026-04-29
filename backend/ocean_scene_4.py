from __future__ import annotations

"""
ocean_scene.py
==============
Builds an underwater/ocean scene with:
  - ocean floor plane + optional texture
  - scatter-placed creatures with correct scaling
  - per-creature swim animation (rig-aware, staggered)
  - underwater lighting (blue key + caustic rim)
  - camera framed on the actual creature bounds
"""

from math import radians

from ..scene.animation_ops import animate_subject_group
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.layout_ops import (
    all_object_names,
    import_and_place_asset_group,
    frame_camera_to_meshes,
    bounds_world,
    combined_meshes,
    target_size_for_asset,
    _get_depsgraph,
)
from ..scene.materials import assign_material

# Species fallback sizes used only when scale_class is absent from the registry.
# Prefer target_size_for_asset() which reads scale_class first.
_CREATURE_SPECIES_SIZE: dict[str, float] = {
    "whale":    6.0,
    "shark":    3.0,
    "fish":     0.5,
    "creature": 1.5,
}
_CREATURE_TARGET_DEFAULT = 1.5

# Scatter layout: positions for up to 5 creatures in a loose school formation
# (X, Y, Z) — Z > 0 means above the ocean floor, giving depth to the scene
_CREATURE_SLOTS = [
    ( 0.0,  0.0,  1.5),
    (-2.5,  1.5,  2.2),
    ( 2.5, -1.0,  1.0),
    (-1.5, -2.5,  3.0),
    ( 2.0,  2.5,  2.5),
]

# Stagger offset between creatures so they don't all start swimming in sync
_SWIM_STAGGER_FRAMES = 12


# ---------------------------------------------------------------------------
# Lighting helpers
# ---------------------------------------------------------------------------

def _add_area_light(bpy, location, rotation_deg, energy, color, size=8.0):
    bpy.ops.object.light_add(
        type="AREA",
        location=location,
        rotation=tuple(radians(v) for v in rotation_deg),
    )
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = "RECTANGLE"
    light.data.size = size
    light.data.size_y = size
    return light


def _setup_ocean_lighting(bpy) -> None:
    # Blue key light from above (simulates surface light shaft)
    _add_area_light(bpy, (0, 0, 12),   (0,   0,  0),  8000, (0.10, 0.40, 0.90), 14)
    # Cyan fill from camera-left
    _add_area_light(bpy, (-8, -4, 5),  (60,  0,  45), 4000, (0.05, 0.70, 0.85),  8)
    # Deep teal rim from behind subjects
    _add_area_light(bpy, (4,  10, 3),  (80,  0, -30), 3000, (0.00, 0.50, 0.65),  6)


# ---------------------------------------------------------------------------
# Ocean floor material (simple procedural blue-grey)
# ---------------------------------------------------------------------------

def _make_ocean_floor_material(bpy, name: str = "OceanFloor"):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf   = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.05, 0.12, 0.20, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.85

    mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _create_camera(bpy, scene, location=(0, -12, 3), lens=40):
    from math import radians as r
    bpy.ops.object.camera_add(
        location=location,
        rotation=(r(75), 0, 0),
    )
    cam = bpy.context.object
    cam.data.lens = lens
    scene.camera = cam
    return cam


def _look_at(cam, target_obj):
    c = cam.constraints.new(type="TRACK_TO")
    c.target     = target_obj
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis    = "UP_Y"


def _animate_camera_drift(cam, frame_end: int) -> None:
    """Slow lateral drift + subtle push — underwater camera feel."""
    start = cam.location.copy()
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (start.x + 1.5, start.y + 1.0, start.z - 0.3)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.location = start


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_ocean_scene(bpy, manifest: dict, scene) -> None:
    resolved     = manifest.get("resolved_assets",     {}) or {}
    instructions = manifest.get("animation_instructions", []) or []
    models       = resolved.get("models", {}) or {}
    creatures    = models.get("characters", []) or []

    animation_mode = (manifest.get("scene_plan", {}) or {}).get("animation_mode", "swim_school")

    print(f"[OCEAN] build_ocean_scene | creatures={len(creatures)} anim={animation_mode}", flush=True)

    # ── Ocean floor ───────────────────────────────────────────────────────
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, -1.0))
    floor = bpy.context.object
    floor.scale = (60, 60, 1)
    assign_material(floor, _make_ocean_floor_material(bpy))

    # ── Lighting ──────────────────────────────────────────────────────────
    _setup_ocean_lighting(bpy)

    # ── Import and place creatures ────────────────────────────────────────
    creature_instances: list[list] = []   # one list of root objs per creature
    creature_all_meshes: list      = []

    for idx, asset in enumerate(creatures[:5]):
        slot = _CREATURE_SLOTS[idx]

        # Resolve target size: scale_class from registry takes priority,
        # then species tag fallback, then per-species default.
        species = str(asset.get("species") or "").lower()
        if not species:
            tag_set = {str(t).lower() for t in asset.get("tags", []) or []}
            for sp in ("whale", "shark", "fish"):
                if sp in tag_set:
                    species = sp
                    break
        target_size = target_size_for_asset(
            asset,
            fallback=_CREATURE_SPECIES_SIZE.get(species, _CREATURE_TARGET_DEFAULT),
        )

        before_names = all_object_names(bpy)
        ok, meshes = import_and_place_asset_group(
            bpy, import_asset, asset,
            target_center=slot,
            target_size=target_size,
            ground_z=slot[2],       # float creatures at their Z slot height
            axis_mode="max",
        )

        if ok and meshes:
            probe   = probe_imported_objects(bpy, before_names)
            # Root objects for this instance = all new roots
            instance_roots = probe.all_roots if probe.all_roots else meshes
            creature_instances.append(instance_roots)
            creature_all_meshes.extend(meshes)
            print(f"[OCEAN] creature {idx} placed | species={species} size={target_size} slot={slot}", flush=True)
        else:
            print(f"[OCEAN] creature {idx} import failed — skipping", flush=True)

    # ── Animate creatures ─────────────────────────────────────────────────
    if creature_instances:
        animate_subject_group(
            bpy,
            instances=creature_instances,
            action="swim",
            mode=animation_mode,
            frame_end=scene.frame_end,
            stagger_frames=_SWIM_STAGGER_FRAMES,
        )

    # ── Camera ────────────────────────────────────────────────────────────
    depsgraph = _get_depsgraph(bpy)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 2.0))
    cam_target = bpy.context.object
    cam_target.name = "OceanCameraTarget"

    cam = _create_camera(bpy, scene, location=(0, -12, 2.5))
    _look_at(cam, cam_target)

    # Frame on actual creature bounds if available
    if creature_all_meshes:
        frame_camera_to_meshes(
            scene, cam, cam_target, creature_all_meshes,
            fill_factor=0.72,
            height_bias=0.50,
            depsgraph=depsgraph,
        )

    _animate_camera_drift(cam, scene.frame_end)
