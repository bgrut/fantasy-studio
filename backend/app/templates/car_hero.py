from __future__ import annotations

from math import radians
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    import_and_place_asset_group,
    frame_camera_to_meshes,
    _get_depsgraph,
    ensure_world_background,
    clamp_camera_lens,
    ensure_hdri_world,
    ensure_scene_look,
    add_atmosphere_box,
    add_contact_shadow_gradient,
    filter_useful_meshes,
    axis_mode_for_asset,
    enforce_subject_grounding,
    all_object_names,
    resolve_hdri_from_manifest,
)
from ..scene.materials import (
    make_automotive_floor_material,
    make_road_asphalt_material,
    make_terrain_ground_material,
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


def _add_area_light(bpy, location, rotation_deg, energy, color=(1,1,1), size=7.0):
    """Fallback lighting when preset system is unavailable."""
    bpy.ops.object.light_add(type='AREA', location=location, rotation=tuple(radians(v) for v in rotation_deg))
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'RECTANGLE'
    light.data.size = size
    light.data.size_y = size
    return light


def _add_lane_stripes(bpy, center_x: float = 0.0, y_min: float = -30.0,
                      y_max: float = 80.0, spacing: float = 6.0,
                      stripe_length: float = 2.0, lateral_offset: float = 3.0):
    """
    Add a row of bright lane stripes on either side of the car along Y.
    These create strong parallax cues so forward motion is unambiguous
    even when the camera tracks alongside the vehicle.
    """
    mat = bpy.data.materials.new(name="LaneStripeMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (1.0, 0.95, 0.7, 1.0)
    emit.inputs["Strength"].default_value = 4.0
    links.new(emit.outputs["Emission"], out.inputs["Surface"])

    stripes = []
    y = y_min
    while y < y_max:
        for x_off in (-lateral_offset, lateral_offset):
            bpy.ops.mesh.primitive_plane_add(location=(center_x + x_off, y, 0.005))
            stripe = bpy.context.object
            stripe.scale = (0.18, stripe_length, 1.0)
            stripe.name = f"LaneStripe_{int(y)}_{int(x_off)}"
            if stripe.data.materials:
                stripe.data.materials[0] = mat
            else:
                stripe.data.materials.append(mat)
            stripes.append(stripe)
        y += spacing

    print(f"[CAR_HERO] added {len(stripes)} lane stripes for parallax", flush=True)
    return stripes


def build_car_hero(bpy, manifest: dict, scene) -> None:
    # V1.3 Bug 2 gate — legacy road/terrain/treeline/atmosphere is for
    # unforced Ferrari-style renders; when a forced env is present it
    # provides the backdrop and these would occlude/fight it.  The preset
    # path's CarHeroGround (small reflective plane) stays — it's a
    # platform the car sits on, not environment-scale furniture.
    has_forced_env = bool(
        manifest.get("forced_environment_path")
        or manifest.get("forced_environment_id")
        or manifest.get("_auto_picked_environment")
    )

    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[CAR_HERO] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[CAR_HERO] using legacy hardcoded setup", flush=True)

    # ── Environment (ground + HDRI + atmosphere) ───────────────────────
    if use_presets:
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "reflective_ground"),
            ground_name="CarHeroGround",
        )
    elif has_forced_env:
        # Forced env: skip the entire legacy infrastructure block.
        print(
            "[CAR_HERO] SKIPPING legacy road/terrain/treeline/atmosphere — "
            "forced env active",
            flush=True,
        )
    else:
        # Legacy path — road, terrain, scenery, atmosphere
        ensure_scene_look(scene, exposure=0.05)
        _hdri_path = resolve_hdri_from_manifest(manifest, "assets/hdri/qwantani_moon_noon_puresky_4k.exr")
        hdri_used = ensure_hdri_world(bpy, scene, _hdri_path, strength=1.20)
        if not hdri_used:
            ensure_world_background(scene, strength=1.20, color=(0.05, 0.055, 0.07, 1.0))

        # ── Road surface (long strip aligned to Y axis) ────────────────
        road_mat = make_road_asphalt_material(bpy, name="CarHeroRoad", wetness=0.35)
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        road = bpy.context.object
        road.name = "CarHeroRoad"
        road.scale = (4.0, 120, 1)  # 8m wide, 240m long
        road["is_ground"] = True
        road["is_template"] = True
        assign_material(road, road_mat)

        # ── Terrain ground flanking the road ───────────────────────────
        terrain_mat = make_terrain_ground_material(bpy, name="CarHeroTerrain")
        for x_off, side_name in [(-40, "Left"), (40, "Right")]:
            bpy.ops.mesh.primitive_plane_add(location=(x_off, 0, -0.01))
            terrain = bpy.context.object
            terrain.name = f"CarHeroTerrain{side_name}"
            terrain.scale = (40, 120, 1)
            assign_material(terrain, terrain_mat)

        # ── Simple treeline silhouettes (distant parallax) ─────────────
        try:
            treeline_mat = bpy.data.materials.new(name="TreelineSilhouette")
            treeline_mat.use_nodes = True
            bsdf = treeline_mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.02, 0.04, 0.02, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.95
            for z_idx, (y_pos, scale_x, scale_z) in enumerate([
                (80, 120, 12), (-60, 120, 10), (120, 100, 14),
            ]):
                for x_side in (-55, 55):
                    bpy.ops.mesh.primitive_plane_add(location=(x_side, y_pos, scale_z * 0.5))
                    tree_plane = bpy.context.object
                    tree_plane.scale = (scale_x * 0.3, 0.01, scale_z * 0.5)
                    tree_plane.name = f"Treeline_{z_idx}_{int(x_side)}"
                    assign_material(tree_plane, treeline_mat)
        except Exception as e:
            print(f"[CAR_HERO] treeline silhouettes skipped: {e}", flush=True)

        # ── Atmosphere ─────────────────────────────────────────────────
        add_atmosphere_box(
            bpy, location=(0, 8, 3), scale=(20, 14, 5),
            density=0.005, color=(0.75, 0.78, 0.88, 1.0),
            name="CarHeroAtmo_Near",
        )
        add_atmosphere_box(
            bpy, location=(0, 22, 5), scale=(40, 12, 8),
            density=0.008, color=(0.70, 0.72, 0.82, 1.0),
            name="CarHeroAtmo_Far",
        )

    resolved = (manifest.get("resolved_assets") or {})
    models = (resolved.get("models") or {})

    # ── SINGLE SOURCE OF TRUTH for the hero vehicle ───────────────────
    # Priority: hero_asset_path > resolved_assets vehicles/cars > default
    # Importing from BOTH sources caused the duplicate-car overlay bug:
    # the resolver's match AND the synonym-forced hero both ended up in
    # the scene because they had different paths. Now we pick ONE.
    import os as _os
    vehicles: list = []

    _hero_path = str(manifest.get("hero_asset_path") or "").strip()
    if _hero_path and _os.path.exists(_hero_path):
        # hero_asset_path is the authoritative hero — use it directly
        print(f"[CAR_HERO] importing SINGLE vehicle from hero_asset_path: {_hero_path}", flush=True)
        vehicles = [{"path": _hero_path}]
    else:
        # Fallback: check resolved_assets vehicles + cars buckets
        _raw_vehicles = (models.get("vehicles") or []) + (models.get("cars") or [])
        print(
            f"[CAR_HERO] no hero_asset_path, checking resolved vehicles: {len(_raw_vehicles)} "
            f"(vehicles={len(models.get('vehicles') or [])} "
            f"cars={len(models.get('cars') or [])})",
            flush=True,
        )
        # Dedup by path
        _seen_paths: set = set()
        for _v in _raw_vehicles:
            if not isinstance(_v, dict):
                continue
            _p = _os.path.normcase(_os.path.normpath(
                str(_v.get("path") or _v.get("file") or "")
            ))
            if _p and _p in _seen_paths:
                print(f"[CAR_HERO] skipping duplicate vehicle entry: {_p}", flush=True)
                continue
            if _p:
                _seen_paths.add(_p)
            vehicles.append(_v)
        # Only import ONE vehicle — the first after dedup
        if len(vehicles) > 1:
            print(
                f"[CAR_HERO] WARNING: {len(vehicles)} vehicles after dedup, "
                f"using only first: {vehicles[0].get('path', '?')}",
                flush=True,
            )
            vehicles = vehicles[:1]
        print(f"[CAR_HERO] resolved vehicle count: {len(vehicles)}", flush=True)

    # ── Import vehicle ──────────────────────────────────────────────────
    car_center = (0.0, 5.0, 0.0)
    subject_meshes = []
    subject_roots = []  # true top-level parents (Empty/Armature) for animation

    # Defensive guard: if anything in the scene is already tagged
    # is_hero at this point, some upstream stage (environment preset,
    # shared helper, prior template call) already imported a hero and
    # we must NOT re-import on top of it. Running a second hero import
    # is how the "Ferrari with double wheels" symptom appears — two
    # copies of the .blend land in the scene and the mirrored wheel
    # meshes stack on the originals. The guard makes that regression
    # loudly visible instead of silent.
    existing_hero_objs = [
        o for o in bpy.data.objects if o.get("is_hero", False)
    ]
    if existing_hero_objs:
        print(
            f"[CAR_HERO] hero already tagged in scene "
            f"({len(existing_hero_objs)} obj; first={existing_hero_objs[0].name!r}) "
            f"-- skipping duplicate vehicle import",
            flush=True,
        )
        subject_meshes.extend(
            o for o in existing_hero_objs if o.type == 'MESH'
        )
        subject_roots.extend(existing_hero_objs)
        vehicles = []  # block the import branch below

    if vehicles:
        before_names = all_object_names(bpy)
        # Diagnostic: count meshes before/after the import so a .blend
        # that internally contains duplicate wheel geometry (some
        # Sketchfab Ferrari blends ship mirrored wheels as separate
        # objects instead of instanced copies) is visible in the log.
        _mesh_before = sum(1 for o in bpy.data.objects if o.type == 'MESH')
        _veh_path = str(vehicles[0].get("path") or vehicles[0].get("file") or "?")
        print(f"[CAR_HERO] importing vehicle: {_veh_path}", flush=True)

        ok, imported = import_hero_asset_group(
            bpy, import_asset, vehicles[0],
            target_center=car_center,
            target_size=4.8,
            ground_z=0.0,
            axis_mode=axis_mode_for_asset(vehicles[0], fallback="length"),
        )

        _mesh_after = sum(1 for o in bpy.data.objects if o.type == 'MESH')
        print(
            f"[CAR_HERO] vehicle import complete | meshes {_mesh_before} -> "
            f"{_mesh_after} (+{_mesh_after - _mesh_before})",
            flush=True,
        )

        if ok and imported:
            subject_meshes.extend(imported)
            # Capture the actual top-level roots so motion profiles can
            # animate the WHOLE vehicle, not individual leaf meshes.
            try:
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots:
                    subject_roots.extend(probe.all_roots)
                else:
                    subject_roots.extend(imported)
            except Exception as e:
                print(f"[CAR_HERO] probe failed: {e}, using imported meshes as roots", flush=True)
                subject_roots.extend(imported)

    if not subject_meshes:
        bpy.ops.mesh.primitive_cube_add(location=(car_center[0], car_center[1], 0.7))
        car = bpy.context.object
        car.scale = (1.0, 2.3, 0.65)
        subject_meshes.append(car)
        subject_roots.append(car)

    # Ensure subject is properly grounded
    depsgraph = _get_depsgraph(bpy)
    enforce_subject_grounding(bpy, subject_meshes, ground_z=0.0, depsgraph=depsgraph)

    # ── Contact shadow under the car ────────────────────────────────────
    add_contact_shadow_gradient(
        bpy,
        center=(car_center[0], car_center[1], 0.003),
        radius=3.8,
        name="CarHeroContactShadow",
    )

    # ── Parallax cues (lane stripes) when vehicle is in motion ────────
    # Without these, even a moving car looks stationary on a featureless
    # ground because there's nothing visually flowing past the camera.
    # Skip when a forced env is active — the env itself provides parallax.
    if (
        not has_forced_env
        and scene_plan
        and scene_plan.get("animation_style") in ("vehicle_drive", "vehicle_drift")
    ):
        try:
            _add_lane_stripes(bpy, center_x=car_center[0])
        except Exception as e:
            print(f"[CAR_HERO] lane stripes failed: {e}", flush=True)
    elif has_forced_env:
        print("[CAR_HERO] SKIPPING lane stripes — forced env active", flush=True)

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "studio_automotive"))
    else:
        # Legacy 5-point automotive lighting
        _add_area_light(bpy, (0, 2, 7),   (75, 0, 0),    6000, (1.0, 1.0, 1.0),   12)
        _add_area_light(bpy, (-7, 3, 3),  (60, 0, 50),   2800, (0.65, 0.75, 1.0),  8)
        _add_area_light(bpy, (7, 3, 3),   (60, 0, -50),  2800, (1.0, 0.88, 0.82),  8)
        _add_area_light(bpy, (0, 14, 1.5),(95, 0, 0),    4500, (1.0, 0.95, 0.90), 14)
        _add_area_light(bpy, (0, 5, -0.5),(180, 0, 0),   1200, (0.85, 0.88, 1.0), 10)

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        cam, target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "low_orbit"),
            subject_center=car_center,
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(car_center[0], car_center[1], 0.75))
        target = bpy.context.object
        target.name = "CarHeroCameraTarget"

        bpy.ops.object.camera_add(
            location=(-2.8, -5.5, 1.1),
            rotation=(radians(82), 0, radians(-12)),
        )
        cam = bpy.context.object
        clamp_camera_lens(cam, 65)
        scene.camera = cam

        c = cam.constraints.new(type='TRACK_TO')
        c.target = target
        c.track_axis = 'TRACK_NEGATIVE_Z'
        c.up_axis = 'UP_Y'

    # Frame camera on actual subject bounds
    depsgraph = _get_depsgraph(bpy)
    useful_meshes = filter_useful_meshes(subject_meshes)
    # Safety: if filter removed everything, use original list
    if not useful_meshes:
        useful_meshes = subject_meshes
        print("[CAR_HERO] WARNING: filter_useful_meshes returned empty, using full mesh list", flush=True)

    shot_info = (scene_plan or {}).get("shot_info", {})
    framed = frame_camera_to_meshes(
        scene, cam, target, useful_meshes,
        fill_factor=shot_info.get("fill_factor", 0.72),
        height_bias=shot_info.get("height_bias", 0.38),
        side_offset=-0.4,
        depsgraph=depsgraph,
    )
    if not framed:
        # Fallback: position camera at a safe default looking at car_center
        print("[CAR_HERO] WARNING: frame_camera_to_meshes failed, using safe fallback position", flush=True)
        cam.location = (car_center[0] - 2.8, car_center[1] - 5.5, 1.1)
        target.location = (car_center[0], car_center[1], 0.75)

    # ── Directorial behavior execution (subject + camera motion) ──────
    # Pass the TRUE TOP-LEVEL ROOTS (not leaf meshes) so the motion profile
    # can keyframe the whole vehicle as one unit. This is what makes the
    # car actually translate forward instead of staying stationary.
    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, target,
                subject_instances=[subject_roots] if subject_roots else None,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[CAR_HERO] directorial_behavior not available, using legacy", flush=True)

    # Behavior-driven animation fallback (uses manifest metadata)
    if not _behavior_executed and subject_roots:
        try:
            from ..scene.animation_ops import animate_by_behavior
            _behavior_executed = animate_by_behavior(
                bpy,
                instances=[subject_roots],
                manifest=manifest,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
        except ImportError:
            pass

    # Camera animation (only for legacy path when behavior system not available)
    if not _behavior_executed:
        from ..scene.camera_motion import push_in_camera
        push_in_camera(cam, dx=3.5, dy=2.5, dz=-0.15,
                       frame_start=1, frame_end=scene.frame_end)

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, subject_meshes, scene_plan, cam)
        log_evaluation(issues, family="car_hero")
