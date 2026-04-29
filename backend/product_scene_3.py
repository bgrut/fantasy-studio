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
from ..scene.layout_ops import (
    all_object_names,
    import_and_place_asset_group,
    frame_camera_to_meshes,
    bounds_world,
)
from ..scene.materials import assign_material

# ---------------------------------------------------------------------------
# Scale class → target size (Blender units ≈ metres)
# "tiny" = jewellery/watch range
# ---------------------------------------------------------------------------
_SCALE_CLASS_SIZE: dict[str, float] = {
    "tiny":   0.20,
    "small":  0.35,
    "medium": 0.60,
    "large":  1.20,
}
_PRODUCT_TARGET_DEFAULT = 0.25


# ---------------------------------------------------------------------------
# Materials
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
    bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.30
    bsdf.inputs["Metallic"].default_value   = 0.05
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _make_backdrop_material(bpy, name: str = "StudioBackdrop"):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out  = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value  = 1.0
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

def _add_area_light(bpy, location, rotation_deg, energy, color, size=4.0):
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


def _setup_studio_lighting(bpy) -> None:
    # Key light — warm white, slightly above and left
    _add_area_light(bpy, (-2.5,  -3.0,  3.5), (55,  0,  30), 2500, (1.00, 0.97, 0.92), 4)
    # Fill light — cool white, right, lower energy
    _add_area_light(bpy, ( 2.5,  -2.5,  2.0), (60,  0, -25), 1000, (0.88, 0.92, 1.00), 3)
    # Rim / back light — narrow, behind subject
    _add_area_light(bpy, ( 0.5,   3.0,  2.5), (90,  0,   0),  800, (1.00, 1.00, 1.00), 2)


# ---------------------------------------------------------------------------
# Camera
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


def _animate_camera_orbit(cam, frame_end: int) -> None:
    """Slow orbital creep around the product."""
    start = cam.location.copy()
    cam.keyframe_insert(data_path="location", frame=1)
    # Move slightly left and push in
    cam.location = (start.x - 0.6, start.y + 0.4, start.z - 0.05)
    cam.keyframe_insert(data_path="location", frame=frame_end)
    cam.location = start


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_product_scene(bpy, manifest: dict, scene) -> None:
    resolved     = manifest.get("resolved_assets",     {}) or {}
    instructions = manifest.get("animation_instructions", []) or []
    models       = resolved.get("models", {}) or {}
    products     = models.get("products", []) or []

    animation_mode = (manifest.get("scene_plan", {}) or {}).get("animation_mode", "product_turntable")

    print(f"[PRODUCT] build_product_scene | products={len(products)} anim={animation_mode}", flush=True)

    # ── Studio backdrop (curved infinity cove) ────────────────────────────
    # Vertical back wall
    bpy.ops.mesh.primitive_plane_add(location=(0, 2.5, 1.5))
    back = bpy.context.object
    back.scale = (4, 4, 1)
    back.rotation_euler = (radians(90), 0, 0)
    assign_material(back, _make_backdrop_material(bpy))

    # Floor
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
    floor = bpy.context.object
    floor.scale = (4, 4, 1)
    assign_material(floor, _make_backdrop_material(bpy))

    # ── Lighting ──────────────────────────────────────────────────────────
    _setup_studio_lighting(bpy)

    # ── Import product ────────────────────────────────────────────────────
    product_instances: list[list] = []
    product_meshes:    list       = []

    if products:
        asset = products[0]

        # Determine scale from registry scale_class or default
        scale_class = str(asset.get("scale_class") or "").lower()
        target_size = _SCALE_CLASS_SIZE.get(scale_class, _PRODUCT_TARGET_DEFAULT)

        before_names = all_object_names(bpy)
        ok, meshes = import_and_place_asset_group(
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
            print(f"[PRODUCT] product placed | scale_class={scale_class} target_size={target_size}", flush=True)

            # Build pedestal sized relative to actual product footprint
            mins, maxs = bounds_world(product_meshes)
            if mins is not None:
                footprint_x = max((maxs.x - mins.x) * 1.3, 0.10)
                footprint_y = max((maxs.y - mins.y) * 1.3, 0.10)
                pedestal_h  = max((maxs.z - mins.z) * 0.15, 0.02)
                # Pedestal top surface at z=0, so pedestal center at -half_height
                bpy.ops.mesh.primitive_cylinder_add(
                    location=(0, 0, -pedestal_h * 0.5),
                    radius=max(footprint_x, footprint_y) * 0.6,
                    depth=pedestal_h,
                )
                pedestal = bpy.context.object
                assign_material(pedestal, _make_pedestal_material(bpy))
                print(f"[PRODUCT] pedestal | radius={max(footprint_x, footprint_y)*0.6:.3f} h={pedestal_h:.3f}", flush=True)
        else:
            print("[PRODUCT] product import failed — scene will have empty stage", flush=True)
            # Fallback pedestal at default size
            bpy.ops.mesh.primitive_cylinder_add(location=(0, 0, -0.05), radius=0.3, depth=0.10)
            pedestal = bpy.context.object
            assign_material(pedestal, _make_pedestal_material(bpy))

    # ── Animate product ───────────────────────────────────────────────────
    if product_instances and "turntable" in animation_mode:
        animate_subject_group(
            bpy,
            instances=product_instances,
            action="rotate",
            mode=animation_mode,
            frame_end=scene.frame_end,
            stagger_frames=0,  # only one product, no stagger needed
        )

    # ── Camera ────────────────────────────────────────────────────────────
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
    cam_target = bpy.context.object
    cam_target.name = "ProductCameraTarget"

    cam = _create_camera(bpy, scene, location=(0, -3.5, 0.5))
    _look_at(cam, cam_target)

    # Frame tightly on actual product bounds (not pedestal, not backdrop)
    if product_meshes:
        frame_camera_to_meshes(
            scene, cam, cam_target, product_meshes,
            fill_factor=0.68,
            height_bias=0.55,
            min_distance=0.8,
        )

    _animate_camera_orbit(cam, scene.frame_end)
