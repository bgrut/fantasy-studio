from __future__ import annotations

from math import radians
from ..scene.blender_asset_ops import import_asset
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    import_and_place_asset_group,
    frame_camera_to_meshes,
    _get_depsgraph,
    ensure_world_background,
    clamp_camera_lens,
    ensure_hdri_world,
    ensure_scene_look,
    add_foreground_blend_plane,
    add_atmosphere_box,
    resolve_hdri_from_manifest,
)
from ..scene.materials import make_natural_ground_material, assign_material

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


def _add_area_light(bpy, location, rotation_deg, energy, color=(1,1,1), size=8.0):
    """Fallback lighting when preset system is unavailable."""
    bpy.ops.object.light_add(type='AREA', location=location, rotation=tuple(radians(v) for v in rotation_deg))
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'RECTANGLE'
    light.data.size = size
    light.data.size_y = size
    return light


def _add_sun_light(bpy, rotation_deg=(55, 0, -25), energy=4.5, color=(1.0, 0.97, 0.90)):
    """Directional sun -- essential for landscape depth and shadow definition."""
    bpy.ops.object.light_add(
        type='SUN',
        rotation=tuple(radians(v) for v in rotation_deg),
    )
    sun = bpy.context.object
    sun.data.energy = energy
    sun.data.color = color
    sun.data.angle = radians(1.5)
    return sun


def _make_dark_ground_material(bpy, name="ScenicDarkGround"):
    """Darker variant for foreground terrain so it reads as shadow/near ground."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    return make_natural_ground_material(
        bpy, name=name,
        base=(0.14, 0.15, 0.12, 1.0),
        roughness=0.96,
    )


def _add_terrain_hillock(bpy, location, scale, mat, name="Hillock"):
    """Low-poly mound to break the flat ground plane near the camera."""
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=16, ring_count=8,
        radius=1.0, location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign_material(obj, mat)
    return obj


def build_scenic_landscape(bpy, manifest: dict, scene) -> None:
    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[SCENIC] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[SCENIC] using legacy hardcoded setup", flush=True)

    # ── Environment (ground + HDRI + atmosphere) ───────────────────────
    if use_presets:
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "terrain_blend"),
            ground_name="ScenicGround",
        )
        ground_mat = env_ctx.get("ground_mat")
    else:
        # Legacy path
        ensure_scene_look(scene, exposure=0.12)
        _hdri_path = resolve_hdri_from_manifest(manifest, "assets/hdri/horn-koppe_spring_4k.exr")
        hdri_used = ensure_hdri_world(bpy, scene, _hdri_path, strength=1.25)
        if not hdri_used:
            ensure_world_background(scene, strength=1.35, color=(0.055, 0.065, 0.085, 1.0))

        ground_mat = make_natural_ground_material(bpy, name="ScenicGround")
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        ground = bpy.context.object
        ground.scale = (120, 120, 1)
        ground["is_ground"] = True
        ground["is_template"] = True
        assign_material(ground, ground_mat)

        add_atmosphere_box(
            bpy, location=(0, 6, 3), scale=(30, 10, 5),
            density=0.005, color=(0.82, 0.86, 0.92, 1.0),
            name="ScenicAtmo_Near",
        )
        add_atmosphere_box(
            bpy, location=(0, 22, 8), scale=(50, 16, 12),
            density=0.010, color=(0.78, 0.82, 0.90, 1.0),
            name="ScenicAtmo_Far",
        )

    resolved = (manifest.get("resolved_assets") or {})
    models = (resolved.get("models") or {})
    environments = (models.get("environments") or [])

    # ── Family-specific: terrain breakup (always created) ──────────────
    # These hillocks are essential for the "terrain blend" composition.
    # They mask the flat ground base and mountain footprint.
    if ground_mat is None:
        ground_mat = make_natural_ground_material(bpy, name="ScenicGroundFallback")
    fg_mat = _make_dark_ground_material(bpy, name="ScenicForeground")

    _add_terrain_hillock(bpy, (-6.0, -6.0,  -0.3), (5.0, 3.5, 0.9),  fg_mat, "Hillock_L")
    _add_terrain_hillock(bpy, ( 7.0, -4.0,  -0.4), (4.5, 4.0, 0.7),  fg_mat, "Hillock_R")
    _add_terrain_hillock(bpy, ( 0.0, -8.0,  -0.5), (8.0, 5.0, 0.5),  fg_mat, "Hillock_C")
    # Midground ridge to mask mountain base
    _add_terrain_hillock(bpy, ( 0.0,  6.0,  -0.6), (18.0, 8.0, 1.8), ground_mat, "Ridge_Mid")

    # Foreground blend plane (subtle ground variation)
    fg = add_foreground_blend_plane(bpy, location=(0, -2, 0.01), scale=(50, 14, 1), name="ScenicForegroundBlend")
    assign_material(fg, fg_mat)

    # ── Import environment asset ────────────────────────────────────────
    # Sink mountain well below ground so its base is hidden by terrain and
    # fog rather than sitting visibly on a flat plane.
    env_meshes = []
    for asset in environments[:1]:
        ok, meshes = import_hero_asset_group(
            bpy, import_asset, asset,
            target_center=(0.0, 18.0, 0.0),
            target_size=80.0,
            ground_z=-4.0,        # sink deep -- ridge + fog hide the base
            axis_mode="height",
            tag_as_hero=False,    # mountain is backdrop, not the hero
        )
        if ok and meshes:
            env_meshes.extend(meshes)

    # ── Un-tag environment meshes ──────────────────────────────────────
    # import_hero_asset_group() tags EVERYTHING it imports as is_hero,
    # but the mountain/terrain is environment backdrop, NOT the hero
    # subject.  Leaving is_hero on 80 m mountain meshes causes:
    #   1. CAMERA_FIX computes hero_size=80 m → camera parks 25-40 m out
    #   2. The actual hero (pelican, horse) is 1.5 m and invisible
    #   3. _collect_tagged_hero_meshes_filtered() may keep mountain chunks
    # Remove is_hero from every object the environment import created so
    # ONLY the actual hero (imported by the fallback below) keeps the tag.
    _env_untagged = 0
    for obj in bpy.data.objects:
        try:
            if obj.get("is_hero", False):
                del obj["is_hero"]
                _env_untagged += 1
        except Exception:
            pass
    if _env_untagged:
        print(
            f"[SCENIC] un-tagged {_env_untagged} environment object(s) "
            f"(is_hero removed — only the actual hero should keep it)",
            flush=True,
        )

    if not env_meshes:
        for pos, scale in [((-8, 18, 6), (10, 7, 14)), ((8, 20, 7), (11, 8, 16))]:
            bpy.ops.mesh.primitive_cube_add(location=pos)
            obj = bpy.context.object
            obj.scale = scale
            assign_material(obj, ground_mat)
            env_meshes.append(obj)

    # ── Dynamic hero fallback ──────────────────────────────────────────
    # scenic_landscape only reads the ``environments`` bucket. When a
    # prompt like "pelican on a rock" routes here, the pelican lands in
    # ``characters`` / ``animals`` and would never be imported without
    # this fallback. Placed in the mid-foreground so the establishing
    # drone shot actually has a subject.
    try:
        from ..scene.glb_import import import_hero_asset_path_fallback
        _already = {a.get("path") for a in environments[:1] if isinstance(a, dict)}
        _hero_meshes = import_hero_asset_path_fallback(
            bpy, manifest,
            target_center=(0.0, 4.0, 0.0),
            ground_z=0.0,
            already_imported_paths=_already,
        )
        if _hero_meshes:
            env_meshes.extend(_hero_meshes)
            print(f"[SCENIC] dynamic hero imported: +{len(_hero_meshes)} mesh(es)", flush=True)
    except Exception as _hf_e:
        print(f"[SCENIC] hero fallback error (non-fatal): {_hf_e}", flush=True)

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "sunset_landscape"))
    else:
        # Legacy golden-hour lighting
        _add_sun_light(bpy, rotation_deg=(55, 0, -25), energy=4.5, color=(1.0, 0.95, 0.88))
        _add_area_light(bpy, (0, -10, 14), (60, 0, 0), 7000, (1.0, 0.96, 0.92), 14)
        _add_area_light(bpy, (-12, -2, 8), (70, 0, 35), 3500, (0.75, 0.82, 1.0), 10)
        _add_area_light(bpy, (0, 35, 12), (110, 0, 0), 5000, (1.0, 0.92, 0.80), 18)

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        cam, target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "wide_establishing"),
            subject_center=(0, 14.0, 0),
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 14.0, 6.0))
        target = bpy.context.object
        target.name = "ScenicCameraTarget"

        bpy.ops.object.camera_add(location=(0, -28, 6.5), rotation=(1.25, 0, 0))
        cam = bpy.context.object
        clamp_camera_lens(cam, 32)  # wider lens for establishing drone shot
        scene.camera = cam

        c = cam.constraints.new(type='TRACK_TO')
        c.target = target
        c.track_axis = 'TRACK_NEGATIVE_Z'
        c.up_axis = 'UP_Y'

    depsgraph = _get_depsgraph(bpy)
    shot_info = (scene_plan or {}).get("shot_info", {})
    framed = frame_camera_to_meshes(
        scene, cam, target, env_meshes,
        fill_factor=shot_info.get("fill_factor", 0.45),
        height_bias=shot_info.get("height_bias", 0.40),
        side_offset=0.0,
        depsgraph=depsgraph,
    )
    if not framed:
        # Fallback: safe position looking at mountain area
        print("[SCENIC] WARNING: frame_camera_to_meshes failed, using safe fallback", flush=True)
        cam.location = (0, -28, 6.5)
        target.location = (0, 14.0, 6.0)

    # ── Directorial behavior execution (subject + camera motion) ──────
    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, target,
                subject_instances=None,  # environments have no animated subjects
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[SCENIC] directorial_behavior not available, using legacy", flush=True)

    # Legacy camera animation (only if behavior system not available)
    if not _behavior_executed and not use_presets:
        from ..scene.camera_motion import push_in_camera
        # Slow arc dolly-out for drone establishing shot feel
        push_in_camera(cam, dx=3.0, dy=-4.0, dz=2.5,
                       frame_start=1, frame_end=scene.frame_end)

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, env_meshes, scene_plan, cam)
        log_evaluation(issues, family="scenic_landscape")
