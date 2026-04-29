from __future__ import annotations

from math import radians

from ..scene.animation_ops import animate_subject_group, apply_animation_instructions
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.layout_ops import (
    all_object_names,
    import_and_place_asset_group,
    frame_camera_to_meshes,
    combined_meshes,
)
from ..scene.materials import make_wet_road_material, make_dark_gloss_material, assign_material

# ---------------------------------------------------------------------------
# Per-species target sizes in Blender units (≈ metres).
# Cats are small quadrupeds; do not flatten them to human scale.
# ---------------------------------------------------------------------------
_SPECIES_TARGET_SIZE: dict[str, float] = {
    "cat":       0.45,
    "cats":      0.45,
    "dog":       0.65,
    "bear":      1.30,
    "yeti":      2.20,
    "human":     1.80,
    "person":    1.80,
    "character": 1.80,
}

# Horizontal spacing between character slots (metres)
_SPECIES_SPACING: dict[str, float] = {
    "cat":       0.90,
    "cats":      0.90,
    "dog":       1.00,
    "bear":      1.50,
    "yeti":      2.20,
    "human":     1.40,
    "person":    1.40,
    "character": 1.40,
}

# Default camera fill fraction: lower = more breathing room
_FILL_FACTOR: dict[str, float] = {
    1: 0.65,   # single subject — tighter on one character
    2: 0.72,   # dialogue pair
    3: 0.78,   # performance trio
}
_FILL_FACTOR_DEFAULT = 0.78

# Camera height-bias: fraction of subject bbox height where look-at target sits
_HEIGHT_BIAS_DIALOGUE    = 0.60   # look slightly higher for talking humans
_HEIGHT_BIAS_PERFORMANCE = 0.52   # mid-body for dancing


# ---------------------------------------------------------------------------
# Helpers: read hints written by prompt_scene_planner into debug_notes
# ---------------------------------------------------------------------------

def _parse_hints(manifest: dict) -> dict:
    """
    Extract structured hints written into scene_plan.debug_notes by the planner.
    Returns a dict with keys: scale, spacing, count, species.
    """
    hints: dict = {
        "scale":   None,
        "spacing": None,
        "count":   None,
        "species": "character",
    }
    debug_notes = (
        manifest.get("scene_plan", {}) or {}
    ).get("debug_notes", []) or []

    for note in debug_notes:
        if note.startswith("subject_scale_hint="):
            try:
                hints["scale"] = float(note.split("=", 1)[1])
            except ValueError:
                pass
        elif note.startswith("subject_spacing_hint="):
            try:
                hints["spacing"] = float(note.split("=", 1)[1])
            except ValueError:
                pass
        elif note.startswith("subject_count="):
            try:
                hints["count"] = int(note.split("=", 1)[1])
            except ValueError:
                pass
        elif note.startswith("subject_species="):
            hints["species"] = note.split("=", 1)[1].strip()

    return hints


def _character_target_size(hints: dict) -> float:
    """Return the target size for characters, preferring planner hints."""
    if hints["scale"] is not None:
        return float(hints["scale"])
    return _SPECIES_TARGET_SIZE.get(hints["species"], 1.80)


def _character_spacing(hints: dict) -> float:
    if hints["spacing"] is not None:
        return float(hints["spacing"])
    return _SPECIES_SPACING.get(hints["species"], 1.40)


def _character_count(hints: dict, characters_available: int) -> int:
    """
    Use the planner's requested count; cap to available assets.
    Minimum 1.
    """
    requested = hints["count"] if hints["count"] is not None else characters_available
    return max(1, min(requested, characters_available))


def _build_character_slots(count: int, spacing: float, depth_y: float = 0.0) -> list[tuple]:
    """
    Generate evenly-spaced X positions centred on the origin.
    Adds slight depth variation so characters aren't in a perfectly flat line.
    """
    if count == 1:
        return [(0.0, depth_y, 0.0)]

    total_width = spacing * (count - 1)
    start_x = -total_width / 2.0

    slots = []
    for i in range(count):
        x = start_x + i * spacing
        # Slight arc in depth: middle char is slightly forward
        arc_y = depth_y - (abs(i - (count - 1) / 2.0) * 0.15)
        slots.append((x, arc_y, 0.0))
    return slots


# ---------------------------------------------------------------------------
# Lighting
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


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _create_camera(bpy, scene, location=(0, -8, 4), rotation=(1.2, 0, 0), lens=45):
    bpy.ops.object.camera_add(location=location, rotation=rotation)
    cam = bpy.context.object
    cam.data.lens = lens
    scene.camera = cam
    return cam


def _look_at(cam, target_obj):
    constraint = cam.constraints.new(type="TRACK_TO")
    constraint.target = target_obj
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"


def _animate_camera_push(cam, frame_end: int) -> None:
    """
    Slow push toward the subject.
    In Blender's default -Y-forward camera convention, decreasing Y moves toward
    the subject (subject is at Y=0, camera starts at negative Y).
    """
    start_loc = cam.location.copy()
    cam.location = start_loc
    cam.keyframe_insert(data_path="location", frame=1)

    push_amount = 1.2   # metres to push in over the clip
    cam.location = (
        start_loc.x,
        start_loc.y + push_amount,   # move toward subject (less negative Y)
        start_loc.z - 0.15,          # subtle downward drift for dynamism
    )
    cam.keyframe_insert(data_path="location", frame=frame_end)

    # Restore so scene is in the start position after keyframing
    cam.location = start_loc


# ---------------------------------------------------------------------------
# Fallback geometry
# ---------------------------------------------------------------------------

def _add_fallback_buildings(bpy, tower_mat) -> list:
    """
    Two box-buildings placed behind the stage.
    Cube primitive pivot is at centre, so location.z = half_height.
    """
    meshes = []
    configs = [
        {"loc": (-6.0, 12.0, 0.0), "scale": (1.8, 1.8, 7.0)},
        {"loc": ( 5.0, 14.0, 0.0), "scale": (2.2, 2.0, 9.0)},
    ]
    for cfg in configs:
        half_h = cfg["scale"][2]
        location = (cfg["loc"][0], cfg["loc"][1], half_h)  # pivot at centre → base at z=0
        bpy.ops.mesh.primitive_cube_add(location=location)
        obj = bpy.context.object
        obj.scale = cfg["scale"]
        assign_material(obj, tower_mat)
        meshes.append(obj)
    return meshes


def _add_fallback_character(bpy, slot, mat) -> list:
    """
    Simple capsule-like stand-in: a UV sphere for head + cylinder for body.
    Returns list of mesh objects.
    """
    x, y, _ = slot
    meshes = []

    # Body
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.22, depth=1.10,
        location=(x, y, 0.55),
    )
    body = bpy.context.object
    assign_material(body, mat)
    meshes.append(body)

    # Head
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.18,
        location=(x, y, 1.28),
    )
    head = bpy.context.object
    assign_material(head, mat)
    meshes.append(head)

    return meshes


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_street_scene(bpy, manifest: dict, scene) -> None:
    resolved = manifest.get("resolved_assets", {}) or {}
    instructions = manifest.get("animation_instructions", []) or []
    models = resolved.get("models", {}) or {}

    characters = models.get("characters", []) or []
    buildings  = models.get("buildings",  []) or []
    props      = models.get("props",      []) or []

    # Read planner hints (species, scale, count, spacing)
    hints = _parse_hints(manifest)
    char_size    = _character_target_size(hints)
    char_spacing = _character_spacing(hints)
    char_count   = _character_count(hints, len(characters))
    species      = hints["species"]
    animation_mode = (manifest.get("scene_plan", {}) or {}).get("animation_mode", "character_performance")

    print(
        f"DEBUG street_scene | species={species} count={char_count} "
        f"target_size={char_size} spacing={char_spacing}",
        flush=True,
    )

    # ── Ground ────────────────────────────────────────────────────────────
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
    ground = bpy.context.object
    ground.scale = (40, 40, 1)
    assign_material(ground, make_wet_road_material(bpy, name="StreetWetRoad"))

    # ── Lighting ──────────────────────────────────────────────────────────
    _add_area_light(bpy, (0, -6, 8),    (70,  0,   0), 10000, (1.00, 1.00, 1.00), 10)
    _add_area_light(bpy, (-6, 0, 6),    (75,  0,  45),  6000, (0.25, 0.75, 1.00),  7)
    _add_area_light(bpy, ( 6, 0, 6),    (75,  0, -45),  6000, (1.00, 0.25, 0.85),  7)

    # ── Background buildings ───────────────────────────────────────────────
    building_meshes: list = []
    for idx, asset in enumerate(buildings[:2]):
        offset_x = (idx * 10.0) - 5.0
        ok, meshes = import_and_place_asset_group(
            bpy, import_asset, asset,
            target_center=(offset_x, 13.0 + idx * 2.0, 0.0),
            target_size=18.0,
            ground_z=0.0,
            axis_mode="height",
        )
        if ok:
            building_meshes.extend(meshes)

    if not building_meshes:
        tower_mat = make_dark_gloss_material(bpy, name="StreetFallbackTower")
        building_meshes = _add_fallback_buildings(bpy, tower_mat)

    # ── Characters ────────────────────────────────────────────────────────
    character_slots   = _build_character_slots(char_count, char_spacing, depth_y=0.2)
    character_meshes: list      = []
    character_instances: list[list] = []   # one list of root objs per instance
    fallback_needed: list[int]  = []

    for i, asset in enumerate(characters[:char_count]):
        slot = character_slots[i]
        before_names = all_object_names(bpy)
        ok, meshes = import_and_place_asset_group(
            bpy, import_asset, asset,
            target_center=slot,
            target_size=char_size,
            ground_z=0.0,
            axis_mode="height",
        )
        if ok and meshes:
            probe = probe_imported_objects(bpy, before_names)
            instance_roots = probe.all_roots if probe.all_roots else meshes
            character_instances.append(instance_roots)
            character_meshes.extend(meshes)
        else:
            fallback_needed.append(i)

    # Fill slots that had no resolved asset with fallback stand-ins
    for i in range(len(characters), char_count):
        fallback_needed.append(i)

    if fallback_needed:
        fallback_mat = make_dark_gloss_material(bpy, name="StreetFallbackChar")
        for i in fallback_needed:
            if i < len(character_slots):
                meshes = _add_fallback_character(bpy, character_slots[i], fallback_mat)
                character_meshes.extend(meshes)
                # Fallback stand-ins are unrigged meshes — treat each as its own instance
                character_instances.append(meshes)

    # ── Props ─────────────────────────────────────────────────────────────
    prop_meshes: list = []
    prop_slots = [(-5.5, 2.5, 0.0), (5.5, 2.5, 0.0)]
    for asset, slot in zip(props[:2], prop_slots):
        ok, meshes = import_and_place_asset_group(
            bpy, import_asset, asset,
            target_center=slot,
            target_size=1.20,
            ground_z=0.0,
            axis_mode="max",
        )
        if ok:
            prop_meshes.extend(meshes)

    # ── Camera setup ──────────────────────────────────────────────────────
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, char_size * 0.5))
    cam_target = bpy.context.object
    cam_target.name = "StreetCameraTarget"

    # Initial camera position — will be overridden by frame_camera_to_meshes
    cam = _create_camera(bpy, scene, location=(0, -8, char_size * 0.5), rotation=(1.15, 0, 0), lens=45)
    _look_at(cam, cam_target)

    # Choose fill factor and height bias based on count and animation mode
    fill = _FILL_FACTOR.get(char_count, _FILL_FACTOR_DEFAULT)
    height_bias = (
        _HEIGHT_BIAS_DIALOGUE
        if "dialogue" in animation_mode or "talk" in animation_mode
        else _HEIGHT_BIAS_PERFORMANCE
    )

    # Side offset: push camera slightly left for 2-char dialogue scenes
    side_offset = -0.3 if char_count == 2 else 0.0

    # Frame on character meshes; fallback to full composition only if truly empty
    subject_meshes = character_meshes if character_meshes else combined_meshes(prop_meshes)
    if subject_meshes:
        frame_camera_to_meshes(
            scene, cam, cam_target, subject_meshes,
            fill_factor=fill,
            height_bias=height_bias,
            side_offset=side_offset,
        )
    else:
        # Last resort: frame on buildings but warn
        print("DEBUG street_scene: no character or prop meshes — framing on buildings", flush=True)
        frame_camera_to_meshes(
            scene, cam, cam_target,
            combined_meshes(building_meshes),
            fill_factor=0.55,
            height_bias=0.35,
        )

    # Animate camera push
    _animate_camera_push(cam, scene.frame_end)

    # ── Animate characters (rig-aware, staggered) ─────────────────────────
    # Determine primary action from instructions list
    primary_action = "dance"
    for inst in instructions:
        a = inst.get("action", "")
        if a in ("dance", "talk", "bounce", "sway"):
            primary_action = a
            break

    # Quadrupeds get a compound bounce+sway instead of a single profile
    is_quadruped = species in ("cat", "cats", "dog", "bear")

    if character_instances:
        # Stagger interval scales with character spacing
        stagger = max(4, int(char_spacing * 6))

        if is_quadruped and primary_action == "dance":
            from ..scene.animation_ops import (
                _fallback_bounce, _fallback_sway,
                find_armatures, find_mesh_roots,
            )
            for idx, instance_roots in enumerate(character_instances):
                arms    = find_armatures(instance_roots)
                targets = arms if arms else find_mesh_roots(instance_roots)
                offset  = idx * stagger
                _fallback_bounce(targets, frame_end=scene.frame_end, offset=offset,
                                 amplitude=0.08, period=16)
                _fallback_sway(targets, frame_end=scene.frame_end, offset=offset,
                               amplitude_deg=12.0, period=22)
        else:
            animate_subject_group(
                bpy,
                instances=character_instances,
                action=primary_action,
                mode=animation_mode,
                frame_end=scene.frame_end,
                stagger_frames=stagger,
            )

    # Pass through any non-character instructions (environment, props, etc.)
    non_char_instructions = [
        inst for inst in instructions
        if inst.get("subject", "") not in ("characters", "performers", species)
    ]
    if non_char_instructions:
        apply_animation_instructions(non_char_instructions, frame_end=scene.frame_end)