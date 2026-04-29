from __future__ import annotations

"""
product_scene.py
================
Builds a luxury product-shot scene with:
  - studio pedestal scaled relative to the actual product bounds
  - three-point studio lighting
  - product imported and normalized to target size
  - targeted turntable animation (product object only, not pedestal)
  - camera framed on actual product bounds
"""

from math import radians

from ..scene.animation_ops import animate_subject_group
from ..scene.blender_asset_ops import import_asset, probe_imported_objects
from ..scene.glb_import import import_hero_asset_group
from ..scene.layout_ops import (
    all_object_names,
    import_and_place_asset_group,
    frame_camera_to_meshes,
    bounds_world,
    ensure_world_background,
    ensure_hdri_world,
    ensure_scene_look,
    clamp_camera_lens,
    target_size_for_asset,
    add_contact_shadow_gradient,
    add_atmosphere_box,
    _get_depsgraph,
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

# Fallback size when neither scale_class nor type is set in the registry.
_PRODUCT_TARGET_DEFAULT = 0.25


# ---------------------------------------------------------------------------
# Materials (family-specific -- always used)
# ---------------------------------------------------------------------------

def _make_pedestal_material(bpy, name: str = "PedestalMatte"):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out  = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.88, 0.88, 0.90, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.18
    bsdf.inputs["Metallic"].default_value   = 0.02
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _make_backdrop_material(bpy, name: str = "StudioBackdrop"):
    """Soft matte white -- not fully white (0.82) to avoid blown-out look."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out  = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.82, 0.82, 0.84, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.92
    bsdf.inputs["Specular IOR Level"].default_value = 0.15
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# Lighting fallback
# ---------------------------------------------------------------------------

def _add_area_light(bpy, location, rotation_deg, energy, color, size=4.0):
    """Fallback lighting when preset system is unavailable."""
    bpy.ops.object.light_add(
        type="AREA",
        location=location,
        rotation=tuple(radians(v) for v in rotation_deg),
    )
    light = bpy.context.object
    light.data.energy = energy
    light.data.color  = color
    light.data.shape  = "RECTANGLE"
    light.data.size   = size
    light.data.size_y = size
    return light


# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def _create_camera(bpy, scene, location=(0, -4, 1.5), lens=80):
    bpy.ops.object.camera_add(
        location=location,
        rotation=(radians(80), 0, 0),
    )
    cam = bpy.context.object
    cam.data.lens = lens
    scene.camera  = cam
    return cam


def _look_at(cam, target_obj):
    c = cam.constraints.new(type="TRACK_TO")
    c.target     = target_obj
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis    = "UP_Y"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_product_scene(bpy, manifest: dict, scene) -> None:
    # ── Check for scene_plan from director ──────────────────────────────
    scene_plan = manifest.get("_scene_plan")
    use_presets = _HAS_PRESETS and scene_plan is not None

    if use_presets:
        print(f"[PRODUCT] using preset system | shot={scene_plan.get('shot_type')}", flush=True)
    else:
        print("[PRODUCT] using legacy hardcoded setup", flush=True)

    # ── Environment (HDRI + atmosphere) ─────────────────────────────────
    # Product scene builds its own infinity cove, so we use the environment
    # preset only for HDRI + atmosphere, not ground.
    if use_presets:
        env_ctx = apply_environment_preset(
            bpy, scene,
            scene_plan.get("environment_preset", "studio_product"),
            ground_name="ProductGroundBase",
        )
    else:
        # Legacy path
        ensure_scene_look(scene, exposure=0.05)
        _hdri_path = resolve_hdri_from_manifest(manifest, "assets/hdris/studio_clean_01.exr")
        hdri_used = ensure_hdri_world(bpy, scene, _hdri_path, strength=0.75)
        if not hdri_used:
            ensure_world_background(scene, strength=1.05, color=(0.88, 0.88, 0.90, 1.0))
        add_atmosphere_box(
            bpy, location=(0, 2.0, 1.0), scale=(5, 4, 3),
            density=0.003, color=(0.75, 0.75, 0.78, 1.0),
            name="ProductStudioAtmo",
        )

    resolved     = manifest.get("resolved_assets",     {}) or {}
    instructions = manifest.get("animation_instructions", []) or []
    models       = resolved.get("models", {}) or {}
    products     = models.get("products", []) or []

    animation_mode = (manifest.get("scene_plan", {}) or {}).get("animation_mode", "product_turntable")

    print(f"[PRODUCT] build_product_scene | products={len(products)} anim={animation_mode}", flush=True)

    # ── Studio backdrop / infinity cove (family-specific -- always) ────
    backdrop_mat = _make_backdrop_material(bpy)

    # Floor
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "ProductFloor"
    floor.scale = (8, 8, 1)
    floor["is_ground"] = True
    floor["is_template"] = True
    assign_material(floor, backdrop_mat)

    # Curved sweep
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=2.5, depth=10.0,
        location=(0, 3.5, 0),
        rotation=(0, radians(90), 0),
    )
    sweep = bpy.context.object
    sweep.name = "ProductSweep"
    assign_material(sweep, backdrop_mat)

    # Back wall
    bpy.ops.mesh.primitive_plane_add(location=(0, 6.0, 3.0))
    back = bpy.context.object
    back.name = "ProductBackWall"
    back.scale = (8, 1, 5)
    back.rotation_euler = (radians(90), 0, 0)
    assign_material(back, backdrop_mat)

    # ── Lighting ────────────────────────────────────────────────────────
    if use_presets:
        apply_lighting_preset(bpy, scene_plan.get("lighting_preset", "product_studio"))
    else:
        # Legacy studio lighting
        _add_area_light(bpy, (-2.5,  -3.0,  3.5), (55,  0,  30), 2500, (1.00, 0.97, 0.92), 4)
        _add_area_light(bpy, ( 2.5,  -2.5,  2.0), (60,  0, -25), 1000, (0.88, 0.92, 1.00), 3)
        _add_area_light(bpy, ( 0.5,   3.0,  2.5), (90,  0,   0),  800, (1.00, 1.00, 1.00), 2)
        _add_area_light(bpy, (0, 0, -0.2), (180, 0, 0), 400, (0.90, 0.92, 1.0), 3)

    # -- Import product (family-specific logic -- must stay) ────────────
    product_instances: list[list] = []
    product_meshes:    list       = []

    if products:
        asset = products[0]
        target_size = target_size_for_asset(asset, fallback=_PRODUCT_TARGET_DEFAULT)

        before_names = all_object_names(bpy)
        ok, meshes = import_hero_asset_group(
            bpy, import_asset, asset,
            target_center=(0.0, 0.0, 0.0),
            target_size=target_size,
            ground_z=0.0,
            axis_mode="max",
        )

        if ok and meshes:
            probe          = probe_imported_objects(bpy, before_names)
            instance_roots = probe.all_roots if probe.all_roots else meshes
            product_instances.append(instance_roots)
            product_meshes.extend(meshes)
            print(f"[PRODUCT] product placed | target_size={target_size}", flush=True)

            # Build pedestal sized relative to actual evaluated product footprint
            depsgraph = _get_depsgraph(bpy)
            mins, maxs = bounds_world(product_meshes, depsgraph)
            if mins is not None:
                footprint_x = max((maxs.x - mins.x) * 1.3, 0.10)
                footprint_y = max((maxs.y - mins.y) * 1.3, 0.10)
                pedestal_h  = max((maxs.z - mins.z) * 0.15, 0.02)
                bpy.ops.mesh.primitive_cylinder_add(
                    location=(0, 0, -pedestal_h * 0.5),
                    radius=max(footprint_x, footprint_y) * 0.6,
                    depth=pedestal_h,
                )
                pedestal = bpy.context.object
                assign_material(pedestal, _make_pedestal_material(bpy))
                print(f"[PRODUCT] pedestal | radius={max(footprint_x, footprint_y)*0.6:.3f} h={pedestal_h:.3f}", flush=True)
        else:
            print("[PRODUCT] product import failed - scene will have empty stage", flush=True)
            bpy.ops.mesh.primitive_cylinder_add(location=(0, 0, -0.05), radius=0.3, depth=0.10)
            pedestal = bpy.context.object
            assign_material(pedestal, _make_pedestal_material(bpy))

    # ── Dynamic hero fallback ──────────────────────────────────────────
    # If hero_asset_path didn't land in the ``products`` bucket (hero type
    # mismatch from the asset agent), pull it in now so the pedestal has
    # a subject instead of sitting empty.
    try:
        from ..scene.glb_import import import_hero_asset_path_fallback
        _already = {a.get("path") for a in products[:1] if isinstance(a, dict)}
        _hero_meshes = import_hero_asset_path_fallback(
            bpy, manifest,
            target_center=(0.0, 0.0, 0.0),
            ground_z=0.0,
            already_imported_paths=_already,
        )
        if _hero_meshes:
            product_meshes.extend(_hero_meshes)
            product_instances.append(_hero_meshes)
            print(f"[PRODUCT] dynamic hero imported: +{len(_hero_meshes)} mesh(es)", flush=True)
    except Exception as _hf_e:
        print(f"[PRODUCT] hero fallback error (non-fatal): {_hf_e}", flush=True)

    # -- Animate product ────────────────────────────────────────────────
    if product_instances and "turntable" in animation_mode:
        animate_subject_group(
            bpy,
            instances=product_instances,
            action="rotate",
            mode=animation_mode,
            frame_end=scene.frame_end,
            stagger_frames=0,
            scene_plan=scene_plan,
        )

    # ── Contact shadow under product ──────────────────────────────────
    add_contact_shadow_gradient(
        bpy, center=(0, 0, 0.002), radius=0.8,
        name="ProductContactShadow",
    )

    # ── Camera ──────────────────────────────────────────────────────────
    if use_presets:
        cam, cam_target = apply_camera_preset(
            bpy, scene,
            scene_plan.get("camera_preset", "cinematic_reveal"),
            subject_center=(0, 0, 0),
            frame_end=scene.frame_end,
        )
    else:
        # Legacy camera setup
        depsgraph = _get_depsgraph(bpy)

        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
        cam_target = bpy.context.object
        cam_target.name = "ProductCameraTarget"

        cam = _create_camera(bpy, scene, location=(-0.4, -3.0, 0.6))
        _look_at(cam, cam_target)

    # Frame tightly on actual product bounds (not pedestal, not backdrop)
    if product_meshes:
        depsgraph = _get_depsgraph(bpy)
        shot_info = (scene_plan or {}).get("shot_info", {})
        framed = frame_camera_to_meshes(
            scene, cam, cam_target, product_meshes,
            fill_factor=shot_info.get("fill_factor", 0.62),
            height_bias=shot_info.get("height_bias", 0.50),
            side_offset=-0.08,
            min_distance=0.6,
            depsgraph=depsgraph,
        )
        if not framed:
            print("[PRODUCT] WARNING: frame_camera_to_meshes failed, using safe fallback", flush=True)
            cam.location = (-0.4, -3.0, 0.6)
            cam_target.location = (0, 0, 0)

    clamp_camera_lens(cam, 85)

    # ── Directorial behavior execution (subject + camera motion) ──────
    _behavior_executed = False
    if scene_plan:
        try:
            from ..scene.directorial_behavior import execute_behavior
            behavior = execute_behavior(
                bpy, scene, cam, cam_target,
                subject_instances=product_instances if product_instances else None,
                scene_plan=scene_plan,
                frame_start=1,
                frame_end=scene.frame_end,
                stagger_frames=0,
            )
            _behavior_executed = True
            scene_plan["_behavior_executed"] = True
        except ImportError:
            print("[PRODUCT] directorial_behavior not available, using legacy", flush=True)

    # Legacy camera animation (only if behavior system not available)
    if not _behavior_executed and not use_presets:
        from ..scene.camera_motion import push_in_camera
        push_in_camera(cam, dx=1.2, dy=0.6, dz=-0.08,
                       frame_start=1, frame_end=scene.frame_end)

    # ── Quality evaluation ──────────────────────────────────────────────
    if _HAS_EVAL:
        issues = evaluate_scene(bpy, scene, product_meshes, scene_plan, cam)
        log_evaluation(issues, family="product_scene")
