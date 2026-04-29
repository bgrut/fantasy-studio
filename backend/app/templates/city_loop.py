from __future__ import annotations

from math import radians, tan, atan
from mathutils import Vector

from ..scene.materials import make_dark_gloss_material, make_wet_road_material, assign_material
from ..scene.billboards import add_simple_billboard
from ..scene.blender_asset_ops import import_asset

try:
    from ..scene.cinematic_presets import (
        apply_camera_preset,
        apply_lighting_preset,
        apply_environment_preset,
    )
    _HAS_PRESETS = True
except ImportError:
    _HAS_PRESETS = False


def _all_object_names(bpy):
    return set(obj.name for obj in bpy.data.objects)


def _new_roots(bpy, before_names: set[str]):
    new_objs = [obj for obj in bpy.data.objects if obj.name not in before_names]
    roots = [obj for obj in new_objs if obj.parent is None]
    return roots if roots else new_objs


def _mesh_descendants(root_objs):
    result = []
    seen = set()

    def walk(obj):
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


def _bounds_world(objs):
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    if not meshes:
        return None, None

    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))

    for obj in meshes:
        for corner in obj.bound_box:
            wc = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, wc.x)
            mins.y = min(mins.y, wc.y)
            mins.z = min(mins.z, wc.z)
            maxs.x = max(maxs.x, wc.x)
            maxs.y = max(maxs.y, wc.y)
            maxs.z = max(maxs.z, wc.z)

    return mins, maxs


def _set_world(scene, strength=1.4, color=(0.05, 0.065, 0.09, 1.0)):
    if scene.world is None:
        return
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    bg = nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = color
        bg.inputs[1].default_value = strength


def _add_area_light(bpy, location, rotation_deg, energy, color, size=8.0):
    bpy.ops.object.light_add(
        type='AREA',
        location=location,
        rotation=tuple(radians(v) for v in rotation_deg)
    )
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'RECTANGLE'
    light.data.size = size
    light.data.size_y = size
    return light


def _add_sun(bpy, rotation_deg=(55, 0, 18), energy=1.0):
    bpy.ops.object.light_add(
        type='SUN',
        location=(0, 0, 20),
        rotation=tuple(radians(v) for v in rotation_deg)
    )
    light = bpy.context.object
    light.data.energy = energy
    return light


def _create_camera(bpy, scene, location=(0, -24, 10), rotation=(1.15, 0, 0), lens=55):
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


def _normalize_root_group(bpy, root_objs, target_center=(0, 18, 0), target_size=20.0, ground_z=0.0):
    if not root_objs:
        return False

    meshes = _mesh_descendants(root_objs)
    if not meshes:
        print("DEBUG normalize: no mesh descendants found", flush=True)
        return False

    mins, maxs = _bounds_world(meshes)
    if mins is None or maxs is None:
        return False

    size = maxs - mins
    max_dim = max(size.x, size.y, size.z, 0.001)
    scale_factor = target_size / max_dim

    print(f"DEBUG normalize pre size={size} max_dim={max_dim} scale={scale_factor}", flush=True)

    for obj in root_objs:
        obj.scale = tuple(v * scale_factor for v in obj.scale)

    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action='DESELECT')
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
            print(f"DEBUG transform_apply failed: {e}", flush=True)

    bpy.context.view_layer.update()

    meshes = _mesh_descendants(root_objs)
    mins2, maxs2 = _bounds_world(meshes)
    if mins2 is None or maxs2 is None:
        return False

    center2 = (mins2 + maxs2) * 0.5
    dx = target_center[0] - center2.x
    dy = target_center[1] - center2.y
    dz = ground_z - mins2.z

    for obj in root_objs:
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz

    bpy.context.view_layer.update()

    meshes = _mesh_descendants(root_objs)
    mins3, maxs3 = _bounds_world(meshes)
    size3 = maxs3 - mins3 if mins3 is not None and maxs3 is not None else "unknown"
    print(f"DEBUG normalize post size={size3} moved_center={target_center}", flush=True)

    return True


def _frame_objects_with_camera(scene, cam, target, meshes, fill_factor=0.52, height_bias=0.42):
    mins, maxs = _bounds_world(meshes)
    if mins is None or maxs is None:
        return False

    size = maxs - mins
    center = (mins + maxs) * 0.5

    target.location = (center.x, center.y, mins.z + size.z * height_bias)

    largest_dim = max(size.x, size.y, size.z, 0.001)
    lens_mm = cam.data.lens if cam.data.lens > 0 else 55.0
    sensor_mm = cam.data.sensor_width if cam.data.sensor_width > 0 else 36.0
    fov = 2.0 * atan((sensor_mm * 0.5) / lens_mm)

    distance = (largest_dim * fill_factor) / max(0.1, 2.0 * tan(fov * 0.5))
    distance = max(distance, 10.0)

    cam.location = (
        center.x - distance * 0.18,
        center.y - distance,
        mins.z + size.z * 0.44 + 3.0
    )

    print(
        f"DEBUG auto-frame center={center} size={size} lens={lens_mm} distance={distance} cam={cam.location}",
        flush=True
    )
    return True


def _animate_drone_push(cam, frame_end, start_loc, end_loc):
    cam.location = start_loc
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = end_loc
    cam.keyframe_insert(data_path="location", frame=frame_end)


def _add_background_tower(bpy, location, scale, mat):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.scale = scale
    assign_material(obj, mat)
    return obj


def _add_depth_skyline(bpy, mat):
    objs = []
    bg_specs = [
        ((-42, 46, 10), (4, 4, 20)),
        ((-28, 52, 13), (5, 5, 26)),
        ((-12, 48, 11), (4, 4, 22)),
        ((8, 50, 12), (5, 5, 24)),
        ((24, 53, 14), (6, 6, 28)),
        ((40, 46, 10), (4, 4, 20)),
    ]
    for pos, scale in bg_specs:
        objs.append(_add_background_tower(bpy, pos, scale, mat))
    return objs


def _add_foreground_silhouettes(bpy, mat):
    objs = []
    fg_specs = [
        ((-16, -2, 1.2), (3.0, 1.2, 2.4)),
        ((14, 0, 1.0), (2.6, 1.0, 2.0)),
    ]
    for pos, scale in fg_specs:
        objs.append(_add_background_tower(bpy, pos, scale, mat))
    return objs


def build_city_loop(bpy, manifest, scene):
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 32
    if hasattr(scene, "view_settings"):
        scene.view_settings.exposure = 1.1

    # V1.3 Bug 2 gate — skip synthetic city furniture when a forced env
    # asset is providing the real backdrop.  The 160x160 GroundPlane,
    # depth skyline towers, foreground silhouettes, and fallback cube
    # buildings are all env-scale geometry that would occlude the env.
    # The hero car / billboards / vehicle-scale props stay — only
    # environment geometry is suppressed.
    has_forced_env = bool(
        manifest.get("forced_environment_path")
        or manifest.get("forced_environment_id")
        or manifest.get("_auto_picked_environment")
    )
    if has_forced_env:
        print(
            "[CITY] forced env active — GroundPlane, skyline towers, "
            "foreground silhouettes, fallback tower cubes will be SKIPPED",
            flush=True,
        )

    # ── Check for scene_plan from director ─────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[CITY] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[CITY] using legacy hardcoded setup", flush=True)

    _set_world(scene, strength=1.5, color=(0.05, 0.065, 0.09, 1.0))

    # Lights
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "neon_city"))
    else:
        _add_area_light(bpy, (0, -18, 16), (68, 0, 0), 20000, (1, 1, 1), 18)
        _add_area_light(bpy, (-18, -2, 12), (70, 0, 58), 11000, (0.30, 0.72, 1.0), 12)
        _add_area_light(bpy, (18, -2, 11), (70, 0, -58), 10000, (1.0, 0.30, 0.90), 12)
        _add_sun(bpy, energy=0.9)

    # Ground / city base
    tower_mat = make_dark_gloss_material(bpy, name="TowerDark")
    if not has_forced_env:
        if use_presets:
            apply_environment_preset(
                bpy, scene,
                scene_plan.get("environment_preset", "city_fog"),
                ground_name="GroundPlane",
            )
        bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
        ground = bpy.context.object
        ground.name = "GroundPlane"
        ground.scale = (160, 160, 1)
        ground["is_ground"] = True
        ground["is_template"] = True
        assign_material(ground, make_wet_road_material(bpy, name="WetRoad"))

        # Background skyline / depth
        _add_depth_skyline(bpy, tower_mat)
        _add_foreground_silhouettes(bpy, tower_mat)
    else:
        print("[CITY] SKIPPING GroundPlane + depth skyline + foreground silhouettes — forced env active", flush=True)

    resolved = manifest.get("resolved_assets", {}) or {}
    models = resolved.get("models", {}) or {}
    building_assets = models.get("buildings", []) or []
    car_assets = models.get("cars", []) or []
    sign_assets = models.get("signs", []) or []

    print(f"DEBUG resolved building_assets={building_assets}", flush=True)
    print(f"DEBUG resolved car_assets={car_assets}", flush=True)
    print(f"DEBUG resolved sign_assets={sign_assets}", flush=True)

    imported_any_buildings = False
    imported_any_cars = False
    city_meshes = []
    car_meshes = []

    if building_assets:
        before = _all_object_names(bpy)
        ok = import_asset(bpy, building_assets[0])
        imported_roots = _new_roots(bpy, before)
        print(f"DEBUG building import ok={ok} new_root_count={len(imported_roots)} names={[o.name for o in imported_roots[:20]]}", flush=True)
        if ok and imported_roots:
            imported_any_buildings = _normalize_root_group(
                bpy,
                imported_roots,
                target_center=(0, 24, 0),
                target_size=220.0,
                ground_z=0.0
            )
            city_meshes = _mesh_descendants(imported_roots)
            print(f"DEBUG building normalize success={imported_any_buildings} city_mesh_count={len(city_meshes)}", flush=True)

    if not imported_any_buildings and not has_forced_env:
        print("DEBUG using fallback buildings", flush=True)
        fallback = []
        positions = [(-16, 18, 5), (-9, 20, 6), (-2, 18, 7), (6, 21, 6), (14, 18, 5)]
        scales = [(2, 2, 10), (2, 2, 13), (2, 2, 15), (2, 2, 12), (2, 2, 10)]
        for pos, scale in zip(positions, scales):
            bpy.ops.mesh.primitive_cube_add(location=pos)
            tower = bpy.context.object
            tower.scale = scale
            assign_material(tower, tower_mat)
            fallback.append(tower)
        city_meshes = fallback
    elif not imported_any_buildings and has_forced_env:
        print("[CITY] SKIPPING fallback tower cubes — forced env active", flush=True)

    # ── Hero car import: prefer manifest hero_asset_path, then cars bucket ──
    # Check if hero was already imported (dedup guard)
    _existing_heroes = [o for o in bpy.data.objects if o.get("is_hero", False)]
    if _existing_heroes:
        print(f"[CITY] hero already in scene ({len(_existing_heroes)} objs) — skipping car import", flush=True)
        car_meshes = [o for o in _existing_heroes if o.type == "MESH"]
        imported_any_cars = bool(car_meshes)

    if not imported_any_cars:
        # Priority: hero_asset_path > cars bucket
        import os as _os
        _hero_path = str(manifest.get("hero_asset_path") or "").strip()
        _use_hero_path = _hero_path and _os.path.exists(_hero_path)

        if _use_hero_path:
            print(f"[CITY] using manifest hero_asset_path for car: {_hero_path}", flush=True)
            before = _all_object_names(bpy)
            ok = import_asset(bpy, {"path": _hero_path})
            imported_roots = _new_roots(bpy, before)
            if ok and imported_roots:
                imported_any_cars = _normalize_root_group(
                    bpy, imported_roots,
                    target_center=(0, -14.0, 0.02), target_size=22.0, ground_z=0.02,
                )
                car_meshes = _mesh_descendants(imported_roots)
                for _obj in car_meshes:
                    _obj["is_hero"] = True
        elif car_assets:
            before = _all_object_names(bpy)
            ok = import_asset(bpy, car_assets[0])
            imported_roots = _new_roots(bpy, before)
            print(f"DEBUG car import ok={ok} new_root_count={len(imported_roots)} names={[o.name for o in imported_roots[:20]]}", flush=True)
            if ok and imported_roots:
                imported_any_cars = _normalize_root_group(
                    bpy, imported_roots,
                    target_center=(0, -14.0, 0.02), target_size=22.0, ground_z=0.02,
                )
                car_meshes = _mesh_descendants(imported_roots)
                for _obj in car_meshes:
                    _obj["is_hero"] = True
                print(f"DEBUG car normalize success={imported_any_cars} car_mesh_count={len(car_meshes)}", flush=True)

    if not imported_any_cars:
        print("DEBUG using fallback car", flush=True)
        bpy.ops.mesh.primitive_cube_add(location=(0, -10.0, 0.8))
        car = bpy.context.object
        car.scale = (3.5, 1.6, 0.8)
        car["is_hero"] = True
        assign_material(car, tower_mat)
        car_meshes = [car]

    # Billboards and city accents
    if not sign_assets:
        add_simple_billboard(bpy, location=(-26, 16, 7), scale=(5.0, 0.1, 2.2), color=(0.20, 0.85, 1.0, 1.0), strength=22.0)
        add_simple_billboard(bpy, location=(24, 18, 8), scale=(5.5, 0.1, 2.4), color=(1.0, 0.20, 0.95, 1.0), strength=22.0)
        add_simple_billboard(bpy, location=(0, 34, 12), scale=(8.0, 0.1, 3.0), color=(0.85, 0.92, 1.0, 1.0), strength=18.0)

    # Camera
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    target = bpy.context.object
    target.name = "CameraTarget"

    if use_presets:
        cam, _cam_target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "hero_push_in"),
            subject_center=(0, 0, 0),
        )
        _look_at(cam, target)
    else:
        cam = _create_camera(bpy, scene, location=(0, -28, 12), rotation=(1.10, 0, 0), lens=55)
        _look_at(cam, target)

    meshes_to_frame = city_meshes if city_meshes else car_meshes
    _frame_objects_with_camera(scene, cam, target, meshes_to_frame, fill_factor=0.52, height_bias=0.42)

    # ── Directorial behavior execution (subject + camera motion) ──────
    # Collect hero roots for behavior system (top-level parents of car meshes)
    _hero_roots = []
    for _m in car_meshes:
        _root = _m
        while _root.parent is not None:
            _root = _root.parent
        if _root not in _hero_roots:
            _hero_roots.append(_root)

    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, target,
                subject_instances=[_hero_roots] if _hero_roots else None,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[CITY] directorial_behavior not available, using legacy", flush=True)

    # Behavior-driven animation fallback
    if not _behavior_executed and _hero_roots:
        try:
            from ..scene.animation_ops import animate_by_behavior
            _behavior_executed = animate_by_behavior(
                bpy,
                instances=[_hero_roots],
                manifest=manifest,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
        except ImportError:
            pass

    # Legacy camera animation (only if behavior system not available)
    if not _behavior_executed:
        start_loc = Vector(cam.location) + Vector((-8.0, -10.0, 4.0))
        end_loc = Vector(cam.location) + Vector((3.0, 4.0, -1.5))
        _animate_drone_push(cam, scene.frame_end, start_loc, end_loc)

    print(f"[CITY] build complete | behavior={_behavior_executed}", flush=True)
