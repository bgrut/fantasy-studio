from __future__ import annotations

from math import radians

from ..scene.animation_ops import animate_subject_group, animate_by_behavior
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    all_object_names,
    import_and_place_asset_group,
    frame_camera_to_meshes,
    target_size_for_asset,
    _get_depsgraph,
    ensure_hdri_world,
    ensure_world_background,
    ensure_scene_look,
    add_atmosphere_box,
    filter_useful_meshes,
    resolve_hdri_from_manifest,
)
from ..scene.materials import assign_material

# Preset system -- optional, backward-compatible
try:
    from ..scene.cinematic_presets import (
        apply_camera_preset,
        apply_lighting_preset,
        apply_environment_preset,
    )
    _HAS_PRESETS = True
except ImportError:
    _HAS_PRESETS = False

# Quality evaluation -- optional
try:
    from ..scene.quality_eval import evaluate_scene, log_evaluation
    _HAS_EVAL = True
except ImportError:
    _HAS_EVAL = False


_CREATURE_SPECIES_SIZE: dict[str, float] = {
    "whale":    7.5,
    "shark":    3.0,
    "fish":     0.6,
    "creature": 1.8,
}
_CREATURE_TARGET_DEFAULT = 1.8

_CREATURE_SLOTS = [
    ( 0.0,  0.0,  1.8),
    (-3.0,  1.8,  2.4),
    ( 3.0, -1.4,  1.5),
    (-2.0, -2.8,  2.8),
    ( 2.0,  2.8,  2.5),
]

_SWIM_STAGGER_FRAMES = 12


def _add_area_light(bpy, location, rotation_deg, energy, color, size=8.0):
    """Fallback lighting when preset system is unavailable."""
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
    """Legacy 3-light underwater rig."""
    _add_area_light(bpy, (0, 0, 12),   (0,   0,  0),  5000, (0.10, 0.40, 0.90), 14)
    _add_area_light(bpy, (-8, -4, 5),  (60,  0,  45), 2500, (0.05, 0.70, 0.85),  8)
    _add_area_light(bpy, (4,  10, 3),  (80,  0, -30), 1800, (0.00, 0.50, 0.65),  6)


def _make_ocean_floor_material(bpy, name: str = "OceanFloor"):
    """Tropical-ocean floor material. Previous version was near-pitch-black
    (0.05, 0.12, 0.20), which combined with heavy volumetrics rendered as
    grainy noise instead of visible water. Brighter base + slightly less
    rough now reads as submerged sand/water without washing out."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf   = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.08, 0.32, 0.48, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.75

    mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def _make_ocean_surface_material(bpy, name: str = "OceanSurface"):
    """Translucent, slightly-reflective water surface seen from below.
    Cheap trick: a low-alpha blue plane overhead fakes the 'looking up
    into the water' read even without caustics."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    nodes = mat.node_tree.nodes
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf   = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value  = (0.22, 0.58, 0.78, 1.0)
    bsdf.inputs["Roughness"].default_value   = 0.18
    try:
        bsdf.inputs["Alpha"].default_value   = 0.55
    except Exception:
        pass
    try:
        bsdf.inputs["Transmission"].default_value = 0.55
    except Exception:
        pass

    mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def _create_camera(bpy, scene, location=(0, -15, 2.8), lens=55):
    from math import radians as r
    bpy.ops.object.camera_add(
        location=location,
        rotation=(r(77), 0, 0),
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
    start = cam.location.copy()
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (start.x + 1.0, start.y + 1.8, start.z - 0.15)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.location = start


def build_ocean_scene(bpy, manifest: dict, scene) -> None:
    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[OCEAN] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[OCEAN] using legacy hardcoded setup", flush=True)

    # ── Environment (ground + HDRI + atmosphere) ───────────────────────
    if use_presets:
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "underwater_haze"),
            ground_name="OceanFloor",
            ground_location=(0, 0, -1.2),
        )
        # Subtle volumetric for submerged feel. Previous density (0.008)
        # combined with the preset's own haze rendered as noise — we
        # back it off to 0.0025 and lighten the tint so the creature and
        # camera aim actually read through the water instead of being
        # lost in a blue fog.
        add_atmosphere_box(
            bpy, location=(0, 0, 0), scale=(30, 20, 10),
            density=0.0025, color=(0.14, 0.42, 0.62, 1.0),
            name="OceanDeepHaze",
        )
    else:
        # Legacy path
        ensure_scene_look(scene, exposure=-0.12)
        _resolved_hdri = resolve_hdri_from_manifest(manifest, "")
        _OCEAN_HDRI_CANDIDATES = [
            _resolved_hdri,
            "assets/hdris/ocean_blue_01.exr",
            "assets/hdris/docklands_02_4k.exr",
            "assets/hdris/shanghai_bund_4k.exr",
        ]
        hdri_used = False
        for hdri_path in _OCEAN_HDRI_CANDIDATES:
            if not hdri_path:
                continue
            hdri_used = ensure_hdri_world(bpy, scene, hdri_path, strength=1.15)
            if hdri_used:
                break
        if not hdri_used:
            # Bright tropical-ocean fallback. Previous colour
            # (0.03, 0.08, 0.12) + strength 0.9 produced near-black
            # surround that volumetrics then sampled into grainy noise.
            ensure_world_background(scene, strength=1.4, color=(0.10, 0.36, 0.62, 1.0))

        bpy.ops.mesh.primitive_plane_add(location=(0, 0, -1.2))
        floor = bpy.context.object
        floor.scale = (70, 70, 1)
        floor["is_ground"] = True
        floor["is_template"] = True
        assign_material(floor, _make_ocean_floor_material(bpy))

        # Water surface overhead — reads as 'looking up through water'
        # so the dolphin is obviously submerged instead of floating in void.
        try:
            bpy.ops.mesh.primitive_plane_add(location=(0, 0, 8.0))
            surface = bpy.context.object
            surface.name = "OceanSurface"
            surface.scale = (60, 60, 1)
            assign_material(surface, _make_ocean_surface_material(bpy))
        except Exception as _e:
            print(f"[OCEAN] surface plane skipped: {_e}", flush=True)

        add_atmosphere_box(bpy, location=(0, 6, 3.0), scale=(22, 12, 7), density=0.005, name="OceanAtmosphere")

    resolved     = manifest.get("resolved_assets",     {}) or {}
    models       = resolved.get("models", {}) or {}
    creatures    = models.get("characters", []) or []
    animation_mode = (manifest.get("scene_plan", {}) or {}).get("animation_mode", "swim_school")

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "underwater_depth"))
    else:
        _setup_ocean_lighting(bpy)

    # ── Creatures (family-specific logic -- must stay) ──────────────────
    creature_instances: list[list] = []
    creature_all_meshes: list = []

    for idx, asset in enumerate(creatures[:5]):
        slot = _CREATURE_SLOTS[idx]

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
        if species == "whale":
            target_size = max(target_size, 7.5)

        before_names = all_object_names(bpy)
        ok, meshes = import_hero_asset_group(
            bpy, import_asset, asset,
            target_center=(slot[0], slot[1] + 1.8, slot[2]),
            target_size=target_size,
            ground_z=slot[2],
            axis_mode="max",
        )

        if ok and meshes:
            probe = probe_imported_objects(bpy, before_names)
            instance_roots = probe.all_roots if probe.all_roots else meshes
            creature_instances.append(instance_roots)
            creature_all_meshes.extend(meshes)

    # ── Dynamic hero fallback ──────────────────────────────────────────
    # If hero_asset_path wasn't in ``characters`` (e.g. an ``animal``
    # record that the asset agent routed elsewhere), pull it in now.
    try:
        from ..scene.glb_import import import_hero_asset_path_fallback
        _already = {a.get("path") for a in creatures[:5] if isinstance(a, dict)}
        _hero_meshes = import_hero_asset_path_fallback(
            bpy, manifest,
            target_center=(0.0, 2.0, 2.0),
            ground_z=0.0,
            already_imported_paths=_already,
        )
        if _hero_meshes:
            creature_all_meshes.extend(_hero_meshes)
            creature_instances.append(_hero_meshes)
            print(f"[OCEAN] dynamic hero imported: +{len(_hero_meshes)} mesh(es)", flush=True)
    except Exception as _hf_e:
        print(f"[OCEAN] hero fallback error (non-fatal): {_hf_e}", flush=True)

    if creature_instances:
        # Try behavior-driven animation first (handles downloaded assets)
        _behavior_anim = False
        if manifest.get("hero_asset_type"):
            _behavior_anim = animate_by_behavior(
                bpy,
                instances=creature_instances,
                manifest=manifest,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=_SWIM_STAGGER_FRAMES,
            )

        if not _behavior_anim:
            animate_subject_group(
                bpy,
                instances=creature_instances,
                action="swim",
                mode=animation_mode,
                frame_end=scene.frame_end,
                stagger_frames=_SWIM_STAGGER_FRAMES,
                scene_plan=scene_plan,
            )

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        cam, cam_target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "underwater_drift"),
            subject_center=(0, 2.0, 2.0),
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        depsgraph = _get_depsgraph(bpy)

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 2.0, 2.2))
        cam_target = bpy.context.object
        cam_target.name = "OceanCameraTarget"

        cam = _create_camera(bpy, scene, location=(0, -15, 2.8))
        _look_at(cam, cam_target)

    if creature_all_meshes:
        depsgraph = _get_depsgraph(bpy)
        useful_creatures = filter_useful_meshes(creature_all_meshes)
        if not useful_creatures:
            useful_creatures = creature_all_meshes
            print("[OCEAN] WARNING: filter_useful_meshes returned empty, using full mesh list", flush=True)
        shot_info = (scene_plan or {}).get("shot_info", {})
        framed = frame_camera_to_meshes(
            scene, cam, cam_target, useful_creatures,
            fill_factor=shot_info.get("fill_factor", 0.88),
            height_bias=shot_info.get("height_bias", 0.52),
            depsgraph=depsgraph,
        )
        if not framed:
            print("[OCEAN] WARNING: frame_camera_to_meshes failed, using safe fallback", flush=True)
            cam.location = (0, -15, 2.8)
            cam_target.location = (0, 2.0, 2.2)

    # ── Directorial behavior execution (subject + camera motion) ──────
    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, cam_target,
                subject_instances=creature_instances if creature_instances else None,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=_SWIM_STAGGER_FRAMES,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[OCEAN] directorial_behavior not available, using legacy", flush=True)

    # Legacy camera animation (only if behavior system not available)
    if not _behavior_executed and not use_presets:
        _animate_camera_drift(cam, scene.frame_end)

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, creature_all_meshes, scene_plan, cam)
        log_evaluation(issues, family="ocean_scene")
