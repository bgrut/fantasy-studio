from __future__ import annotations

from math import radians

from ..scene.animation_ops import apply_animation_instructions, animate_subject_group, animate_by_behavior
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    import_and_place_asset_group,
    frame_camera_to_meshes,
    combined_meshes,
    all_object_names,
    _get_depsgraph,
    ensure_world_background,
    ensure_scene_look,
    add_atmosphere_box,
    add_contact_shadow_gradient,
    ensure_hdri_world,
    filter_useful_meshes,
    enforce_subject_grounding,
    resolve_hdri_from_manifest,
    resolve_ground_type,
)
from ..scene.materials import (
    make_automotive_floor_material,
    make_dark_gloss_material,
    assign_material,
)

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


def _prefer_clean_buildings(buildings: list[dict]) -> list[dict]:
    def score(asset: dict):
        path = str(asset.get("path", "")).lower()
        aid = str(asset.get("id", "")).lower()
        if "city_01.blend" in path or aid == "city_01":
            return 100
        if "city_1.blend" in path:
            return 80
        return 0
    return sorted(buildings or [], key=score, reverse=True)


def _add_area_light(bpy, location, rotation_deg, energy, color, size=8.0):
    """Fallback lighting when preset system is unavailable."""
    bpy.ops.object.light_add(
        type='AREA',
        location=location,
        rotation=tuple(radians(v) for v in rotation_deg),
    )
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'RECTANGLE'
    light.data.size = size
    light.data.size_y = size
    return light


def _add_point_light(bpy, location, energy, color, radius=0.15):
    """Small practical light source -- simulates a streetlamp or shop front."""
    bpy.ops.object.light_add(type='POINT', location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shadow_soft_size = radius
    return light


def _create_camera(bpy, scene, location, rotation, lens=50):
    bpy.ops.object.camera_add(location=location, rotation=rotation)
    cam = bpy.context.object
    cam.data.lens = lens
    scene.camera = cam
    return cam


def _look_at(cam, target_obj):
    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = target_obj
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'


def _make_fallback_character(bpy, loc=(0, 0, 0)):
    created = []
    bpy.ops.mesh.primitive_cylinder_add(location=(loc[0], loc[1], loc[2] + 0.45))
    body = bpy.context.object
    body.scale = (0.18, 0.18, 0.45)
    created.append(body)
    bpy.ops.mesh.primitive_uv_sphere_add(location=(loc[0], loc[1], loc[2] + 1.0))
    head = bpy.context.object
    head.scale = (0.18, 0.18, 0.18)
    created.append(head)
    return created


def _add_sidewalk_curbs(bpy, road_width: float = 5.0, depth: float = 40.0, mat=None):
    """Thin raised strips on each side -- breaks the infinite flat plane."""
    curbs = []
    for side in (-1, 1):
        x = side * road_width
        bpy.ops.mesh.primitive_cube_add(location=(x, 8.0, 0.06))
        obj = bpy.context.object
        obj.name = f"Curb_{'L' if side < 0 else 'R'}"
        obj.scale = (0.15, depth, 0.06)
        if mat:
            assign_material(obj, mat)
        curbs.append(obj)
    return curbs


def build_street_scene(bpy, manifest: dict, scene) -> None:
    resolved = manifest.get("resolved_assets", {}) or {}
    instructions = manifest.get("animation_instructions", []) or []
    scene_plan_manifest = manifest.get("scene_plan", {}) or {}
    debug_notes = scene_plan_manifest.get("debug_notes", []) or []

    models = resolved.get("models", {}) or {}
    characters = models.get("characters", []) or []
    buildings = _prefer_clean_buildings(models.get("buildings", []) or [])
    props = models.get("props", []) or []

    # V1.3 Bug 2 gate — when a forced environment is in play, the imported
    # env asset provides the backdrop; this template's synthetic street
    # furniture (ground plane, curbs, buildings, atmosphere boxes) would
    # just occlude / fight that env.  Compute once, consult throughout.
    has_forced_env = bool(
        manifest.get("forced_environment_path")
        or manifest.get("forced_environment_id")
        or manifest.get("_auto_picked_environment")
    )
    if has_forced_env:
        print(
            "[STREET] forced env active — synthetic StreetGround, curbs, "
            "buildings, atmosphere boxes will be SKIPPED",
            flush=True,
        )

    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[STREET] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[STREET] using legacy hardcoded setup", flush=True)

    # ── Environment (ground + HDRI + atmosphere) ───────────────────────
    if use_presets and not has_forced_env:
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "city_fog"),
            ground_name="StreetGround",
        )
    elif not has_forced_env:
        # Legacy path
        ensure_scene_look(scene, exposure=-0.05)
        _hdri_path = resolve_hdri_from_manifest(manifest, "assets/hdri/citrus_orchard_road_puresky_4k.exr")
        hdri_used = ensure_hdri_world(bpy, scene, _hdri_path, strength=1.10)
        if not hdri_used:
            ensure_world_background(scene, strength=1.25, color=(0.05, 0.06, 0.08, 1.0))

        # Wet road for neon reflections
        from ..scene.materials import make_road_asphalt_material
        road_mat = make_road_asphalt_material(bpy, name="StreetRoad", wetness=0.45)
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        ground = bpy.context.object
        ground.name = "StreetGround"
        ground.scale = (100, 100, 1)
        ground["is_ground"] = True
        ground["is_template"] = True
        assign_material(ground, road_mat)

        add_atmosphere_box(
            bpy, location=(0, 4, 2.5), scale=(16, 10, 4),
            density=0.006, color=(0.72, 0.75, 0.85, 1.0),
            name="StreetAtmo_Near",
        )
        add_atmosphere_box(
            bpy, location=(0, 18, 6), scale=(35, 14, 8),
            density=0.010, color=(0.65, 0.68, 0.80, 1.0),
            name="StreetAtmo_Far",
        )
    else:
        # Forced env active: skip all ground/HDRI/atmosphere creation.
        # The forced-env block in render_from_manifest.py owns HDRI selection
        # (via _ENV_HDRI_MAP, Phase 4 in V1.3 Round 1), ground (via the
        # imported env mesh), and atmosphere (via ambient_effects in V1.3
        # recipes).  StreetGround etc. would be redundant + obstructive.
        print("[STREET] SKIPPING synthetic env (ground/HDRI/atmosphere) — forced env active", flush=True)

    # ── Sidewalk curbs + background buildings (env-scale furniture) ────
    sidewalk_mat = make_dark_gloss_material(
        bpy, name="StreetSidewalk",
        base=(0.12, 0.12, 0.13, 1.0), roughness=0.72,
    )

    if not has_forced_env:
        _add_sidewalk_curbs(bpy, road_width=5.5, depth=45.0, mat=sidewalk_mat)

        # ── Buildings -- family-specific placement ─────────────────────
        building_meshes = []
        for asset in buildings[:1]:
            ok, meshes = import_hero_asset_group(
                bpy,
                import_asset,
                asset,
                target_center=(0.0, 10.0, 0.0),
                target_size=24.0,
                ground_z=0.0,
                axis_mode="height",
                tag_as_hero=False,  # buildings are environment, not the hero subject
            )
            if ok:
                building_meshes.extend(meshes)

        if not building_meshes:
            for pos, scale in [((-5, 10, 5), (2.5, 2.0, 10.0)), ((5, 10, 5), (2.5, 2.0, 10.0))]:
                bpy.ops.mesh.primitive_cube_add(location=pos)
                obj = bpy.context.object
                obj.scale = scale
                assign_material(obj, sidewalk_mat)
                building_meshes.append(obj)
    else:
        building_meshes = []  # forced env is the backdrop, no synthetic buildings
        print("[STREET] SKIPPING synthetic curbs + buildings — forced env active", flush=True)

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "neon_city"))
    else:
        # Legacy lighting
        _add_area_light(bpy, (0, -5, 7), (68, 0, 0), 7000, (1.0, 1.0, 1.0), 12)
        _add_area_light(bpy, (-6, 1, 5), (72, 0, 45), 3500, (0.30, 0.70, 1.0), 7)
        _add_area_light(bpy, (6, 1, 5), (72, 0, -45), 3500, (1.0, 0.40, 0.80), 7)
        _add_area_light(bpy, (0, 18, 8), (100, 0, 0), 4000, (0.90, 0.85, 1.0), 14)
        _add_point_light(bpy, (-3.5, 2.0, 3.5), 800, (1.0, 0.85, 0.65), 0.3)
        _add_point_light(bpy, (3.5, 5.0, 3.5), 600, (1.0, 0.90, 0.70), 0.3)

    # ── Characters (family-specific logic -- must stay) ─────────────────
    subject_count = 3
    for note in debug_notes:
        if str(note).startswith("subject_count="):
            try:
                subject_count = max(1, int(str(note).split("=", 1)[1]))
            except Exception:
                pass

    species = "character"
    for note in debug_notes:
        if str(note).startswith("subject_species="):
            species = str(note).split("=", 1)[1].strip().lower()

    if species == "cat":
        char_size = 1.65
        slots = [(-1.6, 1.0, 0.0), (0.0, 1.5, 0.0), (1.6, 0.8, 0.0)]
    else:
        char_size = 1.9
        slots = [(-1.3, 0.8, 0.0), (0.0, 1.2, 0.0), (1.3, 0.8, 0.0)]

    character_meshes = []
    character_instances = []

    for idx in range(subject_count):
        slot = slots[idx] if idx < len(slots) else ((idx - 1) * 1.6, 1.0, 0.0)
        asset = characters[idx] if idx < len(characters) else None

        if asset:
            before_names = all_object_names(bpy)
            ok, meshes = import_hero_asset_group(
                bpy,
                import_asset,
                asset,
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
                continue

        fallback_objs = _make_fallback_character(bpy, loc=slot)
        character_instances.append(fallback_objs)
        character_meshes.extend(fallback_objs)

    # Ensure characters are grounded on the road
    depsgraph = _get_depsgraph(bpy)
    if character_meshes:
        enforce_subject_grounding(bpy, character_meshes, ground_z=0.0, depsgraph=depsgraph)

    # ── Contact shadows under each character ────────────────────────────
    for idx, slot in enumerate(slots[:len(character_instances)]):
        add_contact_shadow_gradient(
            bpy,
            center=(slot[0], slot[1], 0.003),
            radius=0.9 if species == "cat" else 1.1,
            name=f"CharContactShadow_{idx}",
        )

    # ── Props ───────────────────────────────────────────────────────────
    prop_meshes = []
    prop_slots = [(-5.5, 3.0, 0.0), (5.5, 3.0, 0.0)]
    for asset, slot in zip(props[:2], prop_slots):
        ok, meshes = import_hero_asset_group(
            bpy,
            import_asset,
            asset,
            target_center=slot,
            target_size=2.8,
            ground_z=0.0,
            axis_mode="height",
            tag_as_hero=False,  # decorative street props, not the hero
        )
        if ok:
            prop_meshes.extend(meshes)

    # ── Dynamic hero fallback ──────────────────────────────────────────
    # If manifest['hero_asset_path'] didn't land in characters/buildings/
    # props buckets (e.g. hero_asset_type=animal), pull it in now so the
    # scene has a subject. FORCE_FIX downstream sizes + grounds it.
    try:
        from ..scene.glb_import import import_hero_asset_path_fallback
        _already = set()
        for _a in list(characters[:3]) + list(buildings[:1]) + list(props[:2]):
            if isinstance(_a, dict) and _a.get("path"):
                _already.add(_a["path"])
        _hero_meshes = import_hero_asset_path_fallback(
            bpy, manifest,
            target_center=(0.0, 1.2, 0.0),
            ground_z=0.0,
            already_imported_paths=_already,
        )
        if _hero_meshes:
            character_meshes.extend(_hero_meshes)
            character_instances.append(_hero_meshes)
            print(f"[STREET] dynamic hero imported: +{len(_hero_meshes)} mesh(es)", flush=True)
    except Exception as _hf_e:
        print(f"[STREET] hero fallback error (non-fatal): {_hf_e}", flush=True)

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        # Use shot_info for fill_factor if available
        shot_info = scene_plan.get("shot_info", {})
        cam, cam_target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "hero_push_in"),
            subject_center=(0, 1.2, 0),
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 1.2, 0.9))
        cam_target = bpy.context.object
        cam_target.name = "StreetCameraTarget"

        cam = _create_camera(
            bpy, scene,
            location=(-1.2, -7.5, 2.2),
            rotation=(radians(80), 0, radians(-5)),
            lens=45,
        )
        _look_at(cam, cam_target)

    # Frame on characters -- let buildings be background
    depsgraph = _get_depsgraph(bpy)
    framing_meshes = filter_useful_meshes(character_meshes) if character_meshes else combined_meshes(character_meshes, building_meshes)

    shot_info = (scene_plan or {}).get("shot_info", {})
    framed = frame_camera_to_meshes(
        scene,
        cam,
        cam_target,
        framing_meshes,
        fill_factor=shot_info.get("fill_factor", 0.65),
        height_bias=shot_info.get("height_bias", 0.45),
        side_offset=-0.3,
        depsgraph=depsgraph,
    )
    if not framed:
        print("[STREET] WARNING: frame_camera_to_meshes failed, using safe fallback", flush=True)
        cam.location = (-1.2, -7.5, 2.2)
        cam_target.location = (0, 1.2, 0.9)

    # ── Directorial behavior execution (subject + camera motion) ──────
    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, cam_target,
                subject_instances=character_instances if character_instances else None,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8 if species == "cat" else 12,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[STREET] directorial_behavior not available, using legacy", flush=True)

    # Legacy path: only if behavior system not available
    if not _behavior_executed:
        # Legacy camera animation
        if not use_presets:
            from ..scene.camera_motion import push_in_camera
            push_in_camera(cam, dx=1.5, dy=3.5, dz=-0.35,
                           frame_start=1, frame_end=scene.frame_end)

        # Try behavior-driven animation first (uses manifest metadata)
        _behavior_anim = False
        if manifest.get("hero_asset_type") and character_instances:
            _behavior_anim = animate_by_behavior(
                bpy,
                instances=character_instances,
                manifest=manifest,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8 if species == "cat" else 12,
            )

        # Fallback to legacy subject animation
        if not _behavior_anim:
            primary_action = "dance"
            for inst in instructions:
                a = str(inst.get("action", "")).lower()
                if a in ("dance", "talk", "bounce", "sway"):
                    primary_action = a
                    break

            animate_subject_group(
                bpy,
                instances=character_instances,
                action=primary_action,
                mode="character_performance",
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=8 if species == "cat" else 12,
                scene_plan=scene_plan,
            )

    apply_animation_instructions(
        instructions,
        frame_start=1,
        frame_end=scene.frame_end,
    )

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, character_meshes, scene_plan, cam)
        log_evaluation(issues, family="street_scene")
