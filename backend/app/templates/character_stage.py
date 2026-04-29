from __future__ import annotations

from math import radians

from ..scene.animation_ops import animate_subject_group, animate_by_behavior
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    import_and_place_asset_group,
    frame_camera_to_meshes,
    _get_depsgraph,
    all_object_names,
    ensure_world_background,
    ensure_hdri_world,
    ensure_scene_look,
    clamp_camera_lens,
    add_contact_shadow_gradient,
    add_atmosphere_box,
    enforce_subject_grounding,
    resolve_hdri_from_manifest,
)
from ..scene.materials import make_dark_gloss_material, make_studio_cyc_material, assign_material

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


def _add_area_light(bpy, location, rotation_deg, energy, color=(1, 1, 1), size=7.0):
    """Fallback lighting when preset system is unavailable."""
    bpy.ops.object.light_add(type='AREA', location=location, rotation=tuple(radians(v) for v in rotation_deg))
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'RECTANGLE'
    light.data.size = size
    light.data.size_y = size
    return light


def _make_cyc_wall(bpy, mat):
    """
    Curved infinity cove: floor + curved sweep + back wall.
    Eliminates the hard edge between floor and backdrop.
    Family-specific -- always created regardless of preset path.
    """
    parts = []

    # Floor
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "StageFloor"
    floor.scale = (30, 30, 1)
    floor["is_ground"] = True
    floor["is_template"] = True
    assign_material(floor, mat)
    parts.append(floor)

    # Curved sweep (half-cylinder connecting floor to back wall)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=4.0, depth=16.0,
        location=(0, 6.0, 0),
        rotation=(0, radians(90), 0),
    )
    sweep = bpy.context.object
    sweep.name = "StageSweep"
    sweep.scale = (1.0, 1.0, 1.0)
    assign_material(sweep, mat)
    parts.append(sweep)

    # Back wall (tall plane behind the sweep)
    bpy.ops.mesh.primitive_plane_add(location=(0, 10.0, 6.0))
    back = bpy.context.object
    back.name = "StageBackWall"
    back.scale = (16, 1, 8)
    back.rotation_euler = (radians(90), 0, 0)
    assign_material(back, mat)
    parts.append(back)

    return parts


def build_character_stage(bpy, manifest: dict, scene) -> None:
    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[STAGE] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[STAGE] using legacy hardcoded setup", flush=True)

    # ── Environment (HDRI + atmosphere -- but NOT ground, we use cyc wall) ─
    if use_presets:
        # Apply environment for HDRI + atmosphere, but we'll build our own
        # infinity cove on top of whatever ground the preset creates.
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "studio_dark"),
            ground_name="StageGroundBase",
        )
    else:
        # Legacy path
        ensure_scene_look(scene, exposure=0.0)
        _hdri_path = resolve_hdri_from_manifest(manifest, "assets/hdris/studio_small_03_4k.exr")
        hdri_used = ensure_hdri_world(bpy, scene, _hdri_path, strength=0.65)
        if not hdri_used:
            ensure_world_background(scene, strength=1.15, color=(0.06, 0.065, 0.075, 1.0))
        add_atmosphere_box(
            bpy, location=(0, 4, 2.5), scale=(10, 6, 4),
            density=0.004, color=(0.55, 0.55, 0.62, 1.0),
            name="StageAtmosphere",
        )

    resolved = (manifest.get("resolved_assets") or {})
    models = (resolved.get("models") or {})
    chars = (models.get("characters") or [])

    # ── Infinity cove (family-specific -- always created) ──────────────
    cyc_mat = make_dark_gloss_material(
        bpy, name="StageCyc",
        base=(0.05, 0.05, 0.058, 1.0),
        roughness=0.25,
    )
    _make_cyc_wall(bpy, cyc_mat)

    # ── Characters ──────────────────────────────────────────────────────
    slots = [(-1.2, 0.6, 0.0), (0.0, 0.8, 0.0), (1.2, 0.6, 0.0)]
    subject_meshes = []
    instances = []

    for i, asset in enumerate(chars[:3]):
        before = all_object_names(bpy)
        ok, imported = import_hero_asset_group(
            bpy, import_asset, asset,
            target_center=slots[i],
            target_size=1.55,
            ground_z=0.0,
            axis_mode="height",
        )
        if ok and imported:
            probe = probe_imported_objects(bpy, before)
            roots = probe.all_roots if probe.all_roots else imported
            instances.append(roots)
            subject_meshes.extend(imported)

    # ── Dynamic hero fallback ──────────────────────────────────────────
    # If hero_asset_path points to an asset that didn't land in the
    # ``characters`` bucket (e.g. animal/vehicle/prop routed here), pull
    # it in now so the stage has a subject.
    try:
        from ..scene.glb_import import import_hero_asset_path_fallback
        _already = {a.get("path") for a in chars[:3] if isinstance(a, dict)}
        _hero_meshes = import_hero_asset_path_fallback(
            bpy, manifest,
            target_center=(0.0, 0.8, 0.0),
            ground_z=0.0,
            already_imported_paths=_already,
        )
        if _hero_meshes:
            subject_meshes.extend(_hero_meshes)
            instances.append(_hero_meshes)
            print(f"[STAGE] dynamic hero imported: +{len(_hero_meshes)} mesh(es)", flush=True)
    except Exception as _hf_e:
        print(f"[STAGE] hero fallback error (non-fatal): {_hf_e}", flush=True)

    # Fallback stand-in
    if not subject_meshes:
        bpy.ops.mesh.primitive_cylinder_add(location=(0, 0.8, 0.45))
        body = bpy.context.object
        body.scale = (0.20, 0.20, 0.45)
        bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0.8, 1.02))
        head = bpy.context.object
        head.scale = (0.18, 0.18, 0.18)
        subject_meshes.extend([body, head])
        instances.append([body, head])

    # Ensure characters are grounded on studio floor
    depsgraph = _get_depsgraph(bpy)
    if subject_meshes:
        enforce_subject_grounding(bpy, subject_meshes, ground_z=0.0, depsgraph=depsgraph)

    # ── Per-character contact shadows ───────────────────────────────────
    for idx, slot in enumerate(slots[:len(instances)]):
        add_contact_shadow_gradient(
            bpy,
            center=(slot[0], slot[1], 0.003),
            radius=0.85,
            name=f"StageContactShadow_{idx}",
        )

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "studio_five_point"))
    else:
        # Legacy 5-point studio lighting
        _add_area_light(bpy, (0, -4, 7),   (65, 0, 0),    7000, (1.0, 1.0, 1.0),   10)
        _add_area_light(bpy, (-5, 0, 4),   (72, 0, 35),   2800, (0.70, 0.80, 1.0),  7)
        _add_area_light(bpy, (5, 0, 4),    (72, 0, -35),  2800, (1.0, 0.85, 0.90),  7)
        _add_area_light(bpy, (0, 5, 5.5),  (110, 0, 0),   3500, (1.0, 0.98, 0.95),  8)
        _add_area_light(bpy, (0, 0, -0.3), (180, 0, 0),    800, (0.80, 0.85, 1.0),  6)

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        cam, target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "stage_arc"),
            subject_center=(0, 0.7, 0),
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0.7, 0.85))
        target = bpy.context.object
        target.name = "StageCameraTarget"

        bpy.ops.object.camera_add(
            location=(-0.8, -5.5, 2.0),
            rotation=(radians(78), 0, radians(-4)),
        )
        cam = bpy.context.object
        clamp_camera_lens(cam, 65)
        scene.camera = cam

        c = cam.constraints.new(type='TRACK_TO')
        c.target = target
        c.track_axis = 'TRACK_NEGATIVE_Z'
        c.up_axis = 'UP_Y'

    depsgraph = _get_depsgraph(bpy)
    shot_info = (scene_plan or {}).get("shot_info", {})
    framed = frame_camera_to_meshes(
        scene, cam, target, subject_meshes,
        fill_factor=shot_info.get("fill_factor", 0.58),
        height_bias=shot_info.get("height_bias", 0.50),
        side_offset=-0.15,
        depsgraph=depsgraph,
    )
    if not framed:
        print("[STAGE] WARNING: frame_camera_to_meshes failed, using safe fallback", flush=True)
        cam.location = (-0.8, -5.5, 2.0)
        target.location = (0, 0.7, 0.85)

    # ── Directorial behavior execution (subject + camera motion) ──────
    _behavior_executed = False
    if scene_plan and instances:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, target,
                subject_instances=instances,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[STAGE] directorial_behavior not available, using legacy", flush=True)

    # Legacy path: only if behavior system not available
    if not _behavior_executed:
        if not use_presets:
            from ..scene.camera_motion import push_in_camera
            push_in_camera(cam, dx=2.0, dy=1.8, dz=-0.25,
                           frame_start=1, frame_end=scene.frame_end)

        # Try behavior-driven animation first
        _behavior_anim = False
        if manifest.get("hero_asset_type") and instances:
            _behavior_anim = animate_by_behavior(
                bpy,
                instances=instances,
                manifest=manifest,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8,
            )

        if not _behavior_anim and instances:
            chosen_action = "dance" if any(
                str(x.get("action", "")).lower() == "dance"
                for x in (manifest.get("animation_instructions") or [])
            ) else "bounce"

            animate_subject_group(
                bpy,
                instances=instances,
                action=chosen_action,
                mode="idle",
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8,
                scene_plan=scene_plan,
            )

    # Subtle forward drift for all instances (always, adds organic feel)
    if instances:
        for idx, roots in enumerate(instances):
            for obj in roots:
                try:
                    start_loc = obj.location.copy()
                    obj.keyframe_insert(data_path="location", frame=1)
                    obj.location.y = start_loc.y + 0.35 + (idx * 0.08)
                    obj.keyframe_insert(data_path="location", frame=scene.frame_end)
                    obj.location = start_loc
                except Exception:
                    pass

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, subject_meshes, scene_plan, cam)
        log_evaluation(issues, family="character_stage")
