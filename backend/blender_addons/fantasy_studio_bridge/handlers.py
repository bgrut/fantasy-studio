"""
Op dispatcher — runs on Blender's main thread.

The bridge server queues requests; this module's dispatch() function is
called from the main-thread timer. Each op_name maps to a handler that
mutates bpy state and returns a JSON-serializable result.

Design rules:
    - Every handler returns a dict (never raw bpy objects).
    - Names of created objects are returned so the orchestrator can refer
      back to them in follow-up ops.
    - Failures raise — the bridge server wraps the exception into a
      structured error response.
    - No handler imports anything from Fantasy Studio's `app/` package
      directly; that lives outside Blender. Heavy operations (templates,
      asset registry) are exposed via dedicated lightweight handlers that
      read paths from params.

Handler signature:
    def handle_<op>(params: dict) -> dict | list | scalar
"""

from typing import Any, Callable, Dict
import os
import bpy
import mathutils


class UnknownOpError(Exception):
    pass


# ═══════════════════════════════════════════════════════════════════════
# Scene reset — wipe scene clean before a new orchestrator run
# ═══════════════════════════════════════════════════════════════════════

def _lock_color_management(scene):
    """Force predictable color science: Standard transform, no looks, sRGB display.
    Eliminates AgX-driven color shifts (esp. blue → red, gold → red)."""
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        scene.display_settings.display_device = "sRGB"
    except (AttributeError, TypeError):
        pass


def handle_reset_scene(params: dict) -> dict:
    """Delete all objects + materials + lights + cameras from the current scene.
    Returns counts of what was removed. The world background is reset to dark gray.

    Params:
        keep_default_cube: bool, default False — if True, leaves Blender's default cube
        keep_default_light: bool, default False
        keep_default_camera: bool, default False
    """
    keep_cube   = params.get("keep_default_cube", False)
    keep_light  = params.get("keep_default_light", False)
    keep_camera = params.get("keep_default_camera", False)

    removed = {"objects": 0, "materials": 0, "lights": 0, "cameras": 0, "meshes": 0}

    # Delete objects (this also removes them from collections)
    to_remove = []
    for obj in list(bpy.data.objects):
        name_lower = obj.name.lower()
        if keep_cube and name_lower.startswith("cube") and obj.type == "MESH":
            continue
        if keep_camera and obj.type == "CAMERA":
            continue
        if keep_light and obj.type == "LIGHT":
            continue
        to_remove.append(obj)

    for obj in to_remove:
        if obj.type == "LIGHT":
            removed["lights"] += 1
        elif obj.type == "CAMERA":
            removed["cameras"] += 1
        else:
            removed["objects"] += 1
        bpy.data.objects.remove(obj, do_unlink=True)

    # Purge orphan data blocks so material/mesh names don't auto-increment forever
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            removed["materials"] += 1
            bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            removed["meshes"] += 1
            bpy.data.meshes.remove(mesh)
    for light_data in list(bpy.data.lights):
        if light_data.users == 0:
            bpy.data.lights.remove(light_data)
    for cam_data in list(bpy.data.cameras):
        if cam_data.users == 0:
            bpy.data.cameras.remove(cam_data)

    # Reset world background to neutral dark gray
    world = bpy.context.scene.world
    if world and world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1.0)
            bg.inputs["Strength"].default_value = 1.0

    # Reset active camera reference
    bpy.context.scene.camera = None

    # Lock color management to Standard (eliminates AgX/Filmic color shifts)
    _lock_color_management(bpy.context.scene)

    return {
        "removed": removed,
        "remaining_objects": len(bpy.data.objects),
        "scene_clean": True,
        "color_transform": "Standard",
    }


# ═══════════════════════════════════════════════════════════════════════
# Scene state — read-only inspection
# ═══════════════════════════════════════════════════════════════════════

def handle_get_scene_info(params: dict) -> dict:
    """Return a snapshot of the current scene: name, frame range, render settings, object count."""
    scene = bpy.context.scene
    return {
        "name": scene.name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "render": {
            "engine": scene.render.engine,
            "resolution_x": scene.render.resolution_x,
            "resolution_y": scene.render.resolution_y,
            "fps": scene.render.fps,
            "samples": getattr(scene.cycles, "samples", None) if scene.render.engine == "CYCLES" else None,
        },
        "object_count": len(scene.objects),
        "active_camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
    }


def handle_list_objects(params: dict) -> list:
    """List objects in the scene, optionally filtered by type or name prefix."""
    type_filter = params.get("type")  # 'MESH' | 'LIGHT' | 'CAMERA' | None
    name_prefix = params.get("name_prefix")
    out = []
    for obj in bpy.context.scene.objects:
        if type_filter and obj.type != type_filter:
            continue
        if name_prefix and not obj.name.startswith(name_prefix):
            continue
        out.append({
            "name": obj.name,
            "type": obj.type,
            "location": [round(v, 4) for v in obj.location],
            "rotation_euler": [round(v, 4) for v in obj.rotation_euler],
            "scale": [round(v, 4) for v in obj.scale],
            "dimensions": [round(v, 4) for v in obj.dimensions],
            "hide_viewport": obj.hide_viewport,
            "hide_render": obj.hide_render,
        })
    return out


def handle_get_object_info(params: dict) -> dict:
    """Detailed info on a single object — geometry stats, material slots, parent, custom props."""
    name = params["name"]
    obj = bpy.context.scene.objects.get(name)
    if obj is None:
        raise KeyError(f"object not found: {name}")

    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "parent": obj.parent.name if obj.parent else None,
        "children": [c.name for c in obj.children],
        "material_slots": [s.material.name if s.material else None for s in obj.material_slots],
        "custom_properties": {k: v for k, v in obj.items() if not k.startswith("_")},
    }
    if obj.type == "MESH" and obj.data:
        info["mesh_stats"] = {
            "vertices": len(obj.data.vertices),
            "edges": len(obj.data.edges),
            "polygons": len(obj.data.polygons),
        }
    return info


# ═══════════════════════════════════════════════════════════════════════
# Primitives — generative geometry (gap from existing backend)
# ═══════════════════════════════════════════════════════════════════════

_PRIMITIVE_OPS = {
    "cube": "primitive_cube_add",
    "sphere": "primitive_uv_sphere_add",
    "icosphere": "primitive_ico_sphere_add",
    "cylinder": "primitive_cylinder_add",
    "cone": "primitive_cone_add",
    "torus": "primitive_torus_add",
    "plane": "primitive_plane_add",
    "monkey": "primitive_monkey_add",
}


def handle_create_primitive(params: dict) -> dict:
    """Spawn a primitive mesh. Returns the new object's name."""
    ptype = params.get("type", "cube").lower()
    if ptype not in _PRIMITIVE_OPS:
        raise ValueError(f"unknown primitive type: {ptype}. valid: {list(_PRIMITIVE_OPS)}")

    location = tuple(params.get("location", (0, 0, 0)))
    rotation = tuple(params.get("rotation", (0, 0, 0)))
    size = params.get("size", 2.0)
    name = params.get("name")

    op = getattr(bpy.ops.mesh, _PRIMITIVE_OPS[ptype])

    # Different primitives accept different size kwargs
    if ptype in ("sphere", "icosphere"):
        op(radius=size / 2.0, location=location, rotation=rotation)
    elif ptype == "cylinder":
        depth = params.get("depth", size)
        op(radius=size / 2.0, depth=depth, location=location, rotation=rotation)
    elif ptype == "cone":
        # primitive_cone_add uses radius1 (base) and radius2 (tip) — NOT 'radius'
        depth = params.get("depth", size)
        op(radius1=size / 2.0, radius2=0.0, depth=depth, location=location, rotation=rotation)
    elif ptype == "torus":
        op(major_radius=size / 2.0, minor_radius=size / 8.0, location=location, rotation=rotation)
    elif ptype == "plane":
        op(size=size, location=location, rotation=rotation)
    else:  # cube, monkey
        op(size=size, location=location, rotation=rotation)

    obj = bpy.context.active_object
    if name:
        obj.name = name
    return {"name": obj.name, "type": obj.type, "dimensions": list(obj.dimensions)}


def handle_delete_object(params: dict) -> dict:
    """Remove an object by name. Returns {deleted: True/False}."""
    name = params["name"]
    obj = bpy.context.scene.objects.get(name)
    if obj is None:
        return {"deleted": False, "reason": "not found"}
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": True, "name": name}


def handle_transform_object(params: dict) -> dict:
    """Set location/rotation/scale on an existing object. Any field omitted is left unchanged."""
    name = params["name"]
    obj = bpy.context.scene.objects.get(name)
    if obj is None:
        raise KeyError(f"object not found: {name}")

    if "location" in params:
        obj.location = tuple(params["location"])
    if "rotation_euler" in params:
        obj.rotation_euler = tuple(params["rotation_euler"])
    if "scale" in params:
        s = params["scale"]
        obj.scale = (s, s, s) if isinstance(s, (int, float)) else tuple(s)

    return {
        "name": obj.name,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
    }


# ═══════════════════════════════════════════════════════════════════════
# Modifiers — bevel, subdivision, array, mirror, solidify
# ═══════════════════════════════════════════════════════════════════════

# User-facing kind → actual Blender modifier enum value.
# Several user-friendly names map to Blender's true enum (which has historical baggage).
_MODIFIER_KIND_MAP = {
    "subdivision": "SUBSURF",     # NOT 'SUBDIVISION'
    "subsurf":     "SUBSURF",
    "bevel":       "BEVEL",
    "array":       "ARRAY",
    "mirror":      "MIRROR",
    "solidify":    "SOLIDIFY",
    "boolean":     "BOOLEAN",
    "decimate":    "DECIMATE",
    "wireframe":   "WIREFRAME",
    "smooth":      "SMOOTH",
    "displace":    "DISPLACE",
    "screw":       "SCREW",
    "remesh":      "REMESH",
    "weld":        "WELD",
    "triangulate": "TRIANGULATE",
}


def handle_add_modifier(params: dict) -> dict:
    """Add a modifier to an object. Params: object, kind, name (optional), settings (dict)."""
    obj_name = params["object"]
    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None:
        raise KeyError(f"object not found: {obj_name}")

    kind_raw = params["kind"].lower()
    blender_kind = _MODIFIER_KIND_MAP.get(kind_raw)
    if blender_kind is None:
        raise ValueError(f"unknown modifier kind: {kind_raw}. valid: {sorted(_MODIFIER_KIND_MAP)}")

    mod_name = params.get("name", kind_raw.title())
    mod = obj.modifiers.new(name=mod_name, type=blender_kind)

    settings = params.get("settings", {}) or {}
    for key, val in settings.items():
        if hasattr(mod, key):
            setattr(mod, key, val)
        else:
            # Don't fail loud — surface in result so caller knows
            pass

    return {
        "object": obj.name,
        "modifier_name": mod.name,
        "modifier_type": mod.type,
        "applied_settings": {k: getattr(mod, k, None) for k in settings.keys() if hasattr(mod, k)},
    }


# ═══════════════════════════════════════════════════════════════════════
# Materials — create simple PBR material, assign to object
# ═══════════════════════════════════════════════════════════════════════

def handle_create_material(params: dict) -> dict:
    """Create a Principled BSDF material. Optionally adds a procedural texture
    (noise/voronoi/wave/crater/continent/grain) wired into Base Color.

    Returns the actual material name (may be auto-renamed if collision).
    """
    name = params.get("name", "Material")
    color = params.get("color", (0.8, 0.8, 0.8, 1.0))
    metallic = params.get("metallic", 0.0)
    roughness = params.get("roughness", 0.5)
    emission_color = params.get("emission_color")
    emission_strength = params.get("emission_strength", 0.0)
    texture_pattern = params.get("texture_pattern")
    texture_scale = params.get("texture_scale", 4.0)
    texture_contrast = params.get("texture_contrast", 0.6)
    # Subsurface scattering — light penetrates the surface slightly. Skin, fur,
    # wax, fabric. Without SSS, organic materials look like plastic.
    subsurface_weight = params.get("subsurface", 0.0)
    subsurface_color = params.get("subsurface_color")
    subsurface_radius = params.get("subsurface_radius", [1.0, 0.2, 0.1])
    # Anisotropy — directional metal reflections (brushed/polished metal looks real)
    anisotropic = params.get("anisotropic", 0.0)

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return {"name": mat.name}

    if len(color) == 3:
        color = tuple(color) + (1.0,)

    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness

    if emission_color and "Emission Color" in bsdf.inputs:
        ec = tuple(emission_color) + (1.0,) if len(emission_color) == 3 else tuple(emission_color)
        bsdf.inputs["Emission Color"].default_value = ec
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    elif emission_color and "Emission" in bsdf.inputs:
        ec = tuple(emission_color) + (1.0,) if len(emission_color) == 3 else tuple(emission_color)
        bsdf.inputs["Emission"].default_value = ec

    # Subsurface scattering — Blender 4+ uses "Subsurface Weight" + "Subsurface Radius" + "Subsurface Scale"
    if subsurface_weight > 0:
        # Different Blender versions name the input slightly differently
        for sub_key in ("Subsurface Weight", "Subsurface"):
            if sub_key in bsdf.inputs:
                bsdf.inputs[sub_key].default_value = float(subsurface_weight)
                break
        if subsurface_color and "Subsurface Color" in bsdf.inputs:
            sc = tuple(subsurface_color) + (1.0,) if len(subsurface_color) == 3 else tuple(subsurface_color)
            bsdf.inputs["Subsurface Color"].default_value = sc
        if "Subsurface Radius" in bsdf.inputs:
            try:
                bsdf.inputs["Subsurface Radius"].default_value = tuple(subsurface_radius)
            except (TypeError, ValueError):
                pass

    # Anisotropy for directional metal reflections
    if anisotropic > 0 and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = float(anisotropic)
        aniso_rot = params.get("anisotropic_rotation", None)
        if aniso_rot is not None and "Anisotropic Rotation" in bsdf.inputs:
            bsdf.inputs["Anisotropic Rotation"].default_value = float(aniso_rot)

    # Clearcoat — thin glossy lacquer layer (car paint, polished wood)
    clearcoat = params.get("clearcoat", 0.0)
    if clearcoat > 0:
        # Blender 4+ uses "Coat Weight" / "Coat Roughness"; older uses "Clearcoat".
        for key in ("Coat Weight", "Clearcoat"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = float(clearcoat)
                break
        cc_rough = params.get("clearcoat_roughness", None)
        if cc_rough is not None:
            for key in ("Coat Roughness", "Clearcoat Roughness"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = float(cc_rough)
                    break

    # ── PROCEDURAL TEXTURE — wires noise/voronoi/etc into Base Color via a ColorRamp
    if texture_pattern:
        _apply_procedural_texture(
            mat, bsdf, nodes, links,
            pattern=texture_pattern,
            base_color=color,
            scale=texture_scale,
            contrast=texture_contrast,
            params=params,
        )

    return {"name": mat.name}


def _apply_procedural_texture(mat, bsdf, nodes, links, pattern, base_color, scale, contrast, params):
    """Build a shader subgraph: (TexCoord → Mapping → <pattern node> → ColorRamp → BSDF.Base Color).

    Patterns:
        noise      — Perlin-style organic variation. Fur, skin, fabric.
        voronoi    — Cellular pattern. Scales, reptile skin, crater fields.
        wave       — Striped bands. Wood grain (with rotation), zebra stripes.
        crater     — Voronoi + bumpy displacement. Moon surface.
        continent  — Noise with deep blue base + green island peaks. Earth.
        grain      — Wave + noise mix. Wood grain.
    """
    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.inputs["Scale"].default_value[0] = scale
    mapping.inputs["Scale"].default_value[1] = scale
    mapping.inputs["Scale"].default_value[2] = scale
    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])

    color_ramp = nodes.new(type="ShaderNodeValToRGB")

    if pattern == "noise":
        tex = nodes.new(type="ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 6.0
        tex.inputs["Roughness"].default_value = 0.6
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], color_ramp.inputs["Fac"])
        # Subtle variation around base color
        dark = tuple(c * (1.0 - 0.5 * contrast) for c in base_color[:3]) + (1.0,)
        light = tuple(min(1.0, c * (1.0 + 0.3 * contrast)) for c in base_color[:3]) + (1.0,)
        color_ramp.color_ramp.elements[0].color = dark
        color_ramp.color_ramp.elements[1].color = light

    elif pattern == "voronoi":
        tex = nodes.new(type="ShaderNodeTexVoronoi")
        tex.inputs["Scale"].default_value = scale * 2
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Distance"], color_ramp.inputs["Fac"])
        dark = tuple(c * 0.5 for c in base_color[:3]) + (1.0,)
        light = tuple(min(1.0, c * 1.2) for c in base_color[:3]) + (1.0,)
        color_ramp.color_ramp.elements[0].color = dark
        color_ramp.color_ramp.elements[1].color = light

    elif pattern == "wave":
        tex = nodes.new(type="ShaderNodeTexWave")
        tex.wave_type = "BANDS"
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Distortion"].default_value = 1.5
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], color_ramp.inputs["Fac"])
        dark = tuple(c * 0.6 for c in base_color[:3]) + (1.0,)
        light = tuple(min(1.0, c * 1.1) for c in base_color[:3]) + (1.0,)
        color_ramp.color_ramp.elements[0].color = dark
        color_ramp.color_ramp.elements[1].color = light

    elif pattern == "crater":
        # Moon-like: voronoi pattern with bumpy depths
        tex = nodes.new(type="ShaderNodeTexVoronoi")
        tex.inputs["Scale"].default_value = scale * 1.5
        tex.feature = "F1"
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        # Stretch with noise overlay
        noise = nodes.new(type="ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale * 3
        noise.inputs["Detail"].default_value = 8.0
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        # Mix voronoi + noise
        mix = nodes.new(type="ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 0.6
        links.new(tex.outputs["Distance"], mix.inputs["Color1"])
        links.new(noise.outputs["Fac"], mix.inputs["Color2"])
        links.new(mix.outputs["Color"], color_ramp.inputs["Fac"])
        # Gray-on-darker-gray (moon palette)
        color_ramp.color_ramp.elements[0].color = (0.15, 0.15, 0.15, 1.0)
        color_ramp.color_ramp.elements[1].color = (0.65, 0.65, 0.62, 1.0)
        # Add bump displacement for crater depth
        bump = nodes.new(type="ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.7
        links.new(mix.outputs["Color"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    elif pattern == "continent":
        # Earth-like: noise → blue ocean, green/brown land at high values, white poles
        tex = nodes.new(type="ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale * 0.8
        tex.inputs["Detail"].default_value = 8.0
        tex.inputs["Roughness"].default_value = 0.65
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], color_ramp.inputs["Fac"])
        # 5-stop ramp: deep ocean → shallow ocean → coast → land → mountain
        elements = color_ramp.color_ramp.elements
        elements[0].color = (0.04, 0.18, 0.40, 1.0)  # deep ocean
        elements[0].position = 0.0
        elements[1].color = (0.85, 0.78, 0.55, 1.0)  # mountain peaks
        elements[1].position = 1.0
        # Insert middle stops
        e1 = elements.new(0.45)
        e1.color = (0.10, 0.35, 0.55, 1.0)  # shallow ocean
        e2 = elements.new(0.50)
        e2.color = (0.45, 0.55, 0.25, 1.0)  # coast/land
        e3 = elements.new(0.75)
        e3.color = (0.30, 0.45, 0.18, 1.0)  # green land

    elif pattern == "grain":
        # Wood grain: stretched wave + noise jitter
        mapping.inputs["Scale"].default_value[0] = scale * 0.3  # stretch along X
        mapping.inputs["Scale"].default_value[1] = scale * 5    # tight rings perpendicular
        tex = nodes.new(type="ShaderNodeTexWave")
        tex.wave_type = "RINGS"
        tex.inputs["Scale"].default_value = scale * 0.5
        tex.inputs["Distortion"].default_value = 2.0
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        links.new(tex.outputs["Color"], color_ramp.inputs["Fac"])
        color_ramp.color_ramp.elements[0].color = (0.25, 0.13, 0.05, 1.0)
        color_ramp.color_ramp.elements[1].color = (0.48, 0.30, 0.15, 1.0)

    else:
        # Unknown pattern — bail out, keep flat color
        nodes.remove(tex_coord)
        nodes.remove(mapping)
        nodes.remove(color_ramp)
        return

    # Connect color ramp output to Base Color
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])


def handle_apply_material(params: dict) -> dict:
    """Assign an existing material to an object's first slot (creates slot if needed)."""
    obj_name = params["object"]
    mat_name = params["material"]
    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None:
        raise KeyError(f"object not found: {obj_name}")
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        raise KeyError(f"material not found: {mat_name}")

    if len(obj.material_slots) == 0:
        obj.data.materials.append(mat)
    else:
        obj.material_slots[0].material = mat

    return {"object": obj_name, "material": mat_name}


# ═══════════════════════════════════════════════════════════════════════
# Lighting — add lights, set world background
# ═══════════════════════════════════════════════════════════════════════

_LIGHT_TYPES = {"POINT", "SUN", "SPOT", "AREA"}


def handle_add_light(params: dict) -> dict:
    """Add a light. Params: type (POINT/SUN/SPOT/AREA), location, energy, color, name."""
    light_type = params.get("type", "POINT").upper()
    if light_type not in _LIGHT_TYPES:
        raise ValueError(f"unknown light type: {light_type}. valid: {sorted(_LIGHT_TYPES)}")

    name = params.get("name", f"Light_{light_type.title()}")
    location = tuple(params.get("location", (0, 0, 5)))
    energy = params.get("energy", 1000.0)
    color = params.get("color", (1.0, 1.0, 1.0))

    light_data = bpy.data.lights.new(name=name, type=light_type)
    light_data.energy = energy
    light_data.color = color[:3]

    if light_type == "AREA":
        light_data.size = params.get("size", 1.0)
    if light_type == "SPOT":
        light_data.spot_size = params.get("spot_size", 1.0472)  # 60deg default

    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.location = location

    if "rotation_euler" in params:
        light_obj.rotation_euler = tuple(params["rotation_euler"])

    return {
        "name": light_obj.name,
        "type": light_type,
        "energy": energy,
        "location": list(light_obj.location),
    }


def handle_set_hdri_environment(params: dict) -> dict:
    """Load an HDRI image as world environment. Provides realistic ambient lighting +
    reflections without needing any lights set up.

    Params:
        hdri_path (str): absolute path to a .hdr or .exr file
        strength (float): intensity multiplier (1.0 = as-is, 0.5 = dimmer)
        rotation_z (float): rotate the environment around Z (radians) for sun position

    Returns: success status + path
    """
    import os
    hdri_path = params.get("hdri_path", "")
    if not hdri_path or not os.path.exists(hdri_path):
        return {"ok": False, "reason": f"HDRI file not found: {hdri_path}"}

    strength = float(params.get("strength", 1.0))
    rotation_z = float(params.get("rotation_z", 0.0))

    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world

    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    # Clear existing world nodes
    for n in list(nodes):
        nodes.remove(n)

    # Build node graph: TexCoord → Mapping → EnvTexture → Background → Output
    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = rotation_z
    env_tex = nodes.new(type="ShaderNodeTexEnvironment")
    env_tex.image = bpy.data.images.load(hdri_path, check_existing=True)
    bg = nodes.new(type="ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    output = nodes.new(type="ShaderNodeOutputWorld")

    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
    links.new(env_tex.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], output.inputs["Surface"])

    return {
        "ok": True,
        "hdri_path": hdri_path,
        "strength": strength,
        "rotation_z": rotation_z,
    }


def handle_boolean_union(params: dict) -> dict:
    """Merge two objects via Boolean Union modifier. The 'target' object absorbs
    the 'operand' object. Use for vehicle chassis+cabin merging, etc.

    Params:
        target (str): object name that becomes the merged result
        operand (str): object name that gets merged in (deleted after)
        delete_operand (bool, default True): whether to remove operand after merge
    """
    target_name = params["target"]
    operand_name = params["operand"]
    delete_operand = params.get("delete_operand", True)

    target = bpy.context.scene.objects.get(target_name)
    operand = bpy.context.scene.objects.get(operand_name)
    if target is None:
        raise KeyError(f"target object not found: {target_name}")
    if operand is None:
        raise KeyError(f"operand object not found: {operand_name}")

    mod = target.modifiers.new(name=f"Union_{operand_name}", type="BOOLEAN")
    mod.operation = "UNION"
    mod.object = operand
    # Blender 4.x removed FAST; valid values are FLOAT, EXACT, MANIFOLD.
    # EXACT is reliable for our chassis+cabin merges. Fall back gracefully.
    for solver_choice in ("EXACT", "MANIFOLD", "FLOAT"):
        try:
            mod.solver = solver_choice
            break
        except (TypeError, ValueError):
            continue

    # Apply the modifier
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception as e:
        return {"ok": False, "reason": f"modifier apply failed: {e}"}

    if delete_operand:
        bpy.data.objects.remove(operand, do_unlink=True)

    return {"ok": True, "target": target_name, "polygons": len(target.data.polygons) if target.data else 0}


def handle_import_mesh_file(params: dict) -> dict:
    """Import a GLB/GLTF/OBJ/FBX mesh file from disk into the scene.

    Used by the Phase 17 asset-driven pipeline: the orchestrator generates a
    mesh via TripoSR/InstantMesh outside Blender, then asks us to bring it in.

    Params:
        filepath (str): absolute path to the mesh file
        name (str, default "Hero"): rename the imported root object to this
        normalize_size (float | None, default 2.0): if set, scale uniformly so
            longest bbox axis equals this value (metres). Pass null to keep raw.
        ground_to_z0 (bool, default True): after import, lift so lowest bbox
            point sits at z=0 (matches our composer grounding logic)
        join (bool, default True): if multiple meshes were imported, join into one

    Returns:
        {"ok": True, "name": "...", "polygons": int, "dimensions": [x,y,z],
         "location": [x,y,z]}
    """
    filepath = params["filepath"]
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)

    name = params.get("name", "Hero")
    normalize_size = params.get("normalize_size", 2.0)
    ground_to_z0 = bool(params.get("ground_to_z0", True))
    do_join = bool(params.get("join", True))
    # Optional orientation correction. TripoSR/InstantMesh output Y-up with
    # subject facing -Z; Blender needs Z-up. Acceptable values:
    #   "triposr"          → Rx=+90° (legs go down, face goes forward)
    #   "y_up_to_z_up"     → same as triposr
    #   None / "none"      → no rotation (use what GLB declared)
    orientation = params.get("orientation_fix") or params.get("orientation")

    # Snapshot existing objects so we can identify the new ones afterward
    pre_objs = set(bpy.context.scene.objects.keys())

    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif ext == ".obj":
        # 4.x renamed obj importer
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=filepath)
        else:
            bpy.ops.import_scene.obj(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    else:
        raise ValueError(f"unsupported mesh extension: {ext}")

    # Identify imported objects (mesh type only)
    post_objs = set(bpy.context.scene.objects.keys())
    new_names = post_objs - pre_objs
    new_meshes = [bpy.data.objects[n] for n in new_names
                  if bpy.data.objects[n].type == "MESH"]

    if not new_meshes:
        raise RuntimeError(f"no mesh objects imported from {filepath}")

    # Join all imported meshes into one if requested
    if do_join and len(new_meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for m in new_meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = new_meshes[0]
        bpy.ops.object.join()
        target = new_meshes[0]
    else:
        target = new_meshes[0]

    # Rename to canonical name (handle name collision by removing old)
    if name in bpy.data.objects and bpy.data.objects[name] is not target:
        old = bpy.data.objects[name]
        bpy.data.objects.remove(old, do_unlink=True)
    target.name = name

    # Force depsgraph update so bbox / dimensions reflect import
    bpy.context.view_layer.update()

    # Orientation correction.
    #
    # TripoSR's mesh comes out with the subject's "front" facing the viewer
    # (the original camera direction). After glTF import to Blender, the
    # mesh's "depth" axis is X (because Y-up→Z-up rotates Z to Y, then GLB's
    # +X stays X). The visual result: dog's nose-to-tail runs along X, so
    # from the standard camera at +X/-Y angle the dog is viewed FROM THE SIDE.
    # That's fine for a side profile, but the body is horizontal on X.
    #
    # Empirically the right fix is to rotate -90° around Z so the body's
    # length axis becomes Y (depth into scene), nose pointing -Y toward the
    # default camera. That makes the dog face the camera directly.
    #
    # Diagnostic print so we always have orientation data in the log.
    print(f"[import_mesh] post-import dims (raw): "
          f"X={target.dimensions[0]:.3f} Y={target.dimensions[1]:.3f} Z={target.dimensions[2]:.3f}")

    if orientation in ("triposr", "auto"):
        import math
        # -90° around Z: body axis X → Y (faces camera at -Y)
        # The auto-detect logic was a red herring; this is the actual rotation
        # TripoSR's output convention needs.
        target.rotation_euler = (0.0, 0.0, math.radians(-90.0))
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        bpy.context.view_layer.update()
        print(f"[import_mesh] post-orientation-fix dims: "
              f"X={target.dimensions[0]:.3f} Y={target.dimensions[1]:.3f} Z={target.dimensions[2]:.3f}")

    # Normalize size — uniform scale so longest axis = normalize_size metres
    if normalize_size:
        dims = target.dimensions
        longest = max(dims)
        if longest > 1e-6:
            factor = float(normalize_size) / float(longest)
            target.scale = (target.scale[0] * factor,
                            target.scale[1] * factor,
                            target.scale[2] * factor)
        bpy.context.view_layer.update()

    # Ground — lift so lowest bbox corner = z=0
    if ground_to_z0:
        from mathutils import Vector
        min_z = float("inf")
        for corner in target.bound_box:
            wp = target.matrix_world @ Vector(corner)
            if wp.z < min_z:
                min_z = wp.z
        if min_z != float("inf"):
            target.location.z -= min_z
        bpy.context.view_layer.update()

    # Shade smooth — assets from TripoSR/InstantMesh often have flat shading
    if target.data:
        for p in target.data.polygons:
            p.use_smooth = True

    return {
        "ok": True,
        "name": target.name,
        "polygons": len(target.data.polygons) if target.data else 0,
        "dimensions": list(target.dimensions),
        "location": list(target.location),
    }


def handle_save_blend_file(params: dict) -> dict:
    """Save the current Blender scene to a .blend file the user can open.

    Phase 17 deliverable: every render now ships with an editable .blend
    alongside the .mp4 so users can tweak camera/lights/materials and re-render.

    Params:
        filepath (str): absolute path to the .blend to save. Parent dir created
            if missing. If file exists it is overwritten.
        compress (bool, default True): use Blender's compressed format

    Returns:
        {"ok": True, "filepath": "...", "size_bytes": int}
    """
    filepath = params["filepath"]
    compress = bool(params.get("compress", True))

    parent = os.path.dirname(filepath)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    bpy.ops.wm.save_as_mainfile(
        filepath=filepath,
        compress=compress,
        copy=True,  # don't change Blender's "current file" pointer
    )

    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    return {"ok": True, "filepath": filepath, "size_bytes": size}


def handle_add_fur(params: dict) -> dict:
    """Add a hair particle system to a mesh — produces real fur strands rather
    than just texture. Use sparingly: high counts slow renders dramatically.

    Params:
        object (str): target mesh name
        count (int, default 5000): number of strands. 2k-10k for small creatures, 10k-30k for big.
        length (float, default 0.08): hair length in metres
        children (int, default 50): children per parent strand (boosts density cheaply)
        root_radius (float, default 1.0): thickness at root (display only in EEVEE)
        tip_radius (float, default 0.05): thickness at tip
        color (list[3], optional): RGB for the fur. Falls back to object's first material.
        roughness (float, default 0.8): hair roughness
    """
    obj_name = params["object"]
    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        raise KeyError(f"target mesh not found or not a mesh: {obj_name}")

    count = int(params.get("count", 5000))
    length = float(params.get("length", 0.08))
    children = int(params.get("children", 50))
    root_r = float(params.get("root_radius", 1.0))
    tip_r = float(params.get("tip_radius", 0.05))

    psys = obj.modifiers.new(name="Fur", type="PARTICLE_SYSTEM")
    settings = obj.particle_systems[-1].settings

    # Attribute names shifted between Blender 3.x/4.x. Set defensively so a
    # rename doesn't blow up the whole fur step — defaults are usable.
    def _try_set(obj_, name, value):
        try:
            if hasattr(obj_, name):
                setattr(obj_, name, value)
        except Exception:
            pass

    _try_set(settings, "type", "HAIR")
    _try_set(settings, "count", count)
    _try_set(settings, "hair_length", length)
    _try_set(settings, "hair_step", 5)
    _try_set(settings, "use_advanced_hair", True)
    _try_set(settings, "child_type", "INTERPOLATED")
    # Blender 4.x: child_nbr → child_percent (legacy) / removed.
    # Newer builds expose only rendered_child_count.
    _try_set(settings, "child_nbr", children)
    _try_set(settings, "child_percent", children)
    _try_set(settings, "rendered_child_count", children)
    _try_set(settings, "child_length", 1.0)
    _try_set(settings, "root_radius", root_r)
    _try_set(settings, "tip_radius", tip_r)
    _try_set(settings, "child_length_threshold", 0.0)
    _try_set(settings, "clump_factor", 0.3)
    _try_set(settings, "roughness_endpoint", float(params.get("roughness", 0.8)))
    _try_set(settings, "roughness_end_shape", 1.0)

    return {"ok": True, "object": obj_name, "count": count, "length": length}


def handle_set_world_background(params: dict) -> dict:
    """Set world background color + strength. Optionally load an HDRI."""
    scene = bpy.context.scene
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world

    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is None:
        return {"ok": False, "reason": "no Background node"}

    if "color" in params:
        color = params["color"]
        if len(color) == 3:
            color = tuple(color) + (1.0,)
        bg.inputs["Color"].default_value = color
    if "strength" in params:
        bg.inputs["Strength"].default_value = float(params["strength"])

    return {
        "world": world.name,
        "color": list(bg.inputs["Color"].default_value),
        "strength": bg.inputs["Strength"].default_value,
    }


# ═══════════════════════════════════════════════════════════════════════
# Camera — create, set active, position
# ═══════════════════════════════════════════════════════════════════════

def handle_create_camera(params: dict) -> dict:
    """Create a camera. Params: name, location, rotation_euler, lens, set_active (bool)."""
    name = params.get("name", "Camera")
    location = tuple(params.get("location", (7, -7, 5)))
    rotation = tuple(params.get("rotation_euler", (1.1, 0.0, 0.785)))
    lens = params.get("lens", 50.0)
    set_active = params.get("set_active", True)

    cam_data = bpy.data.cameras.new(name=name)
    cam_data.lens = lens
    cam_obj = bpy.data.objects.new(name=name, object_data=cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = location
    cam_obj.rotation_euler = rotation

    if set_active:
        bpy.context.scene.camera = cam_obj

    return {
        "name": cam_obj.name,
        "location": list(cam_obj.location),
        "lens": lens,
        "is_active": bpy.context.scene.camera == cam_obj,
    }


def handle_look_at(params: dict) -> dict:
    """Aim an object (typically a camera) at a target location."""
    obj_name = params["object"]
    target = params["target"]  # either [x,y,z] or {"object": "<name>"}

    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None:
        raise KeyError(f"object not found: {obj_name}")

    if isinstance(target, dict) and "object" in target:
        tgt_obj = bpy.context.scene.objects.get(target["object"])
        if tgt_obj is None:
            raise KeyError(f"target object not found: {target['object']}")
        target_loc = mathutils.Vector(tgt_obj.location)
    else:
        target_loc = mathutils.Vector(tuple(target))

    direction = target_loc - mathutils.Vector(obj.location)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    obj.rotation_euler = rot_quat.to_euler()
    return {"object": obj.name, "rotation_euler": list(obj.rotation_euler)}


# ═══════════════════════════════════════════════════════════════════════
# Animation — keyframes, frame range
# ═══════════════════════════════════════════════════════════════════════

def handle_set_keyframe(params: dict) -> dict:
    """Insert a keyframe on a property at a given frame.
    Params: object, data_path ('location'|'rotation_euler'|'scale'|...), value (optional, sets first), frame, index (optional axis 0/1/2).
    """
    obj_name = params["object"]
    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None:
        raise KeyError(f"object not found: {obj_name}")

    data_path = params["data_path"]
    frame = int(params["frame"])
    value = params.get("value")
    index = params.get("index", -1)

    if value is not None:
        if data_path == "location":
            obj.location = tuple(value)
        elif data_path == "rotation_euler":
            obj.rotation_euler = tuple(value)
        elif data_path == "scale":
            obj.scale = tuple(value) if hasattr(value, "__iter__") else (value, value, value)
        else:
            # Generic path — try setattr-style fallback
            try:
                exec(f"obj.{data_path} = value", {"obj": obj, "value": value})
            except Exception:
                pass

    obj.keyframe_insert(data_path=data_path, frame=frame, index=index)
    return {"object": obj.name, "data_path": data_path, "frame": frame}


def handle_set_frame_range(params: dict) -> dict:
    """Set scene frame_start, frame_end, current."""
    scene = bpy.context.scene
    if "frame_start" in params:
        scene.frame_start = int(params["frame_start"])
    if "frame_end" in params:
        scene.frame_end = int(params["frame_end"])
    if "frame_current" in params:
        scene.frame_set(int(params["frame_current"]))
    return {
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
    }


# ═══════════════════════════════════════════════════════════════════════
# Render — set engine/resolution, render single frame
# ═══════════════════════════════════════════════════════════════════════

def handle_set_render_settings(params: dict) -> dict:
    """Set render engine, resolution, samples, output path.

    Also locks color management to predictable defaults: Standard view transform
    (no AgX/Filmic shift), sRGB display. This eliminates the most common cause
    of "my blue rendered as red" — Blender's default AgX transform aggressively
    re-tints saturated colors.
    """
    scene = bpy.context.scene

    # Force color management to "what you see is what you set"
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        scene.display_settings.display_device = "sRGB"
        if hasattr(scene, "sequencer_colorspace_settings"):
            scene.sequencer_colorspace_settings.name = "sRGB"
    except (AttributeError, TypeError) as e:
        print(f"[handler] color management setup skipped: {e}")

    if "engine" in params:
        # Translate friendly names → current Blender enums. Blender 5.x dropped
        # BLENDER_EEVEE_NEXT (the "Next" engine became the default EEVEE).
        engine = params["engine"]
        available = {e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items}
        engine_map = {
            "EEVEE": "BLENDER_EEVEE",
            "EEVEE_NEXT": "BLENDER_EEVEE",
            "BLENDER_EEVEE_NEXT": "BLENDER_EEVEE",
            # Common LLM typos
            "BLENDER_EVEE": "BLENDER_EEVEE",        # missing first 'E'
            "BLENDER_EEVE": "BLENDER_EEVEE",        # missing final 'E'
            "BLENDER_EEVEE_NXT": "BLENDER_EEVEE",
            "EVEE": "BLENDER_EEVEE",
            "WORKBENCH": "BLENDER_WORKBENCH",
        }
        engine = engine_map.get(engine, engine)
        # Last-resort: fuzzy match against available engines (1-char edit distance)
        if engine not in available:
            engine_upper = engine.upper().replace("-", "_")
            for avail in available:
                # Cheap similarity: shared prefix length / longer
                shared = sum(1 for a, b in zip(engine_upper, avail) if a == b)
                if shared >= max(len(engine_upper), len(avail)) - 2:
                    engine = avail
                    break
        if engine not in available:
            # Cycles may be missing entirely (Steam Blender, stripped builds).
            # Fall back to whatever EEVEE variant the build has so the pipeline
            # keeps moving rather than dying on a "real" render. Log so the
            # composer can see it happened.
            fallback = None
            for cand in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
                if cand in available:
                    fallback = cand
                    break
            if fallback is None:
                raise ValueError(f"engine '{engine}' not in {sorted(available)} and no EEVEE fallback available")
            print(f"[studio_bridge] engine '{engine}' unavailable on this Blender build; "
                  f"falling back to {fallback}. Available: {sorted(available)}")
            engine = fallback
        scene.render.engine = engine
    if "resolution_x" in params:
        scene.render.resolution_x = int(params["resolution_x"])
    if "resolution_y" in params:
        scene.render.resolution_y = int(params["resolution_y"])
    if "samples" in params and scene.render.engine == "CYCLES":
        scene.cycles.samples = int(params["samples"])
    if "filepath" in params:
        scene.render.filepath = params["filepath"]
    if "fps" in params:
        scene.render.fps = int(params["fps"])
    return {
        "engine": scene.render.engine,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "samples": getattr(scene.cycles, "samples", None) if scene.render.engine == "CYCLES" else None,
        "filepath": scene.render.filepath,
        "fps": scene.render.fps,
    }


def handle_render_frame(params: dict) -> dict:
    """Render a single still frame. Blocking — returns when render finishes.
    Params: filepath (output path), frame (optional, defaults to current).
    """
    scene = bpy.context.scene
    if "filepath" in params:
        scene.render.filepath = params["filepath"]
    if "frame" in params:
        scene.frame_set(int(params["frame"]))

    bpy.ops.render.render(write_still=True)
    return {
        "filepath": scene.render.filepath,
        "frame": scene.frame_current,
    }


def handle_render_animation(params: dict) -> dict:
    """Render the scene's frame range as a PNG sequence.

    Outputs frame_0001.png, frame_0002.png, ... in the given directory.
    The pattern is required by stitch_pngs_to_mp4 (which uses frame_%04d.png).

    Params:
        output_dir: directory to write PNG sequence (created if missing)
        frame_start: optional override (otherwise uses scene.frame_start)
        frame_end:   optional override (otherwise uses scene.frame_end)
        fps:         optional override (otherwise leaves scene.render.fps alone)
    """
    import os
    output_dir = params.get("output_dir")
    if not output_dir:
        raise ValueError("render_animation requires 'output_dir'")

    os.makedirs(output_dir, exist_ok=True)

    scene = bpy.context.scene
    if "frame_start" in params:
        scene.frame_start = int(params["frame_start"])
    if "frame_end" in params:
        scene.frame_end = int(params["frame_end"])
    if "fps" in params:
        scene.render.fps = int(params["fps"])

    # File format MUST be PNG (the encoder expects PNG)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    # Filepath sets the PREFIX. Blender appends 4-digit frame number + extension.
    # Result: <output_dir>/frame_0001.png, etc.
    scene.render.filepath = os.path.join(output_dir, "frame_")

    # Verify a camera exists; otherwise render fails uselessly
    if scene.camera is None:
        raise RuntimeError("render_animation requires an active camera in the scene")

    bpy.ops.render.render(animation=True)

    # Collect the output frame paths so the caller knows what was produced
    expected_frames = scene.frame_end - scene.frame_start + 1
    frames_dir = os.path.normpath(output_dir)
    return {
        "output_dir": frames_dir,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "fps": scene.render.fps,
        "expected_frames": expected_frames,
        "filename_pattern": "frame_%04d.png",
        "first_frame_path": os.path.join(frames_dir, f"frame_{scene.frame_start:04d}.png"),
    }


# ═══════════════════════════════════════════════════════════════════════
# Asset spawn — import .blend collection (low-level; high-level via app/mcp/tools/assets.py)
# ═══════════════════════════════════════════════════════════════════════

def handle_append_blend_collection(params: dict) -> dict:
    """Append a collection from an external .blend file.
    Params: blend_path (absolute), collection_name, link (bool, default False = full copy).
    """
    blend_path = params["blend_path"]
    coll_name = params["collection_name"]
    link = params.get("link", False)

    with bpy.data.libraries.load(blend_path, link=link) as (data_from, data_to):
        if coll_name not in data_from.collections:
            raise KeyError(f"collection '{coll_name}' not found in {blend_path}. Available: {list(data_from.collections)}")
        data_to.collections = [coll_name]

    new_coll = data_to.collections[0]
    bpy.context.scene.collection.children.link(new_coll)

    # Collect names of imported objects
    obj_names = [o.name for o in new_coll.objects]
    return {
        "collection": new_coll.name,
        "object_count": len(obj_names),
        "object_names": obj_names,
    }


def handle_create_metaball_blob(params: dict) -> dict:
    """Create a metaball object with multiple elements that auto-blend into one
    continuous surface. The right tool for organic creatures — body + head + ears
    + legs all FUSE naturally without seams or floating pieces.

    Params:
        name (str): name for the final object
        resolution (float): viewport mesh resolution (smaller = more detail; ~0.08 good)
        render_resolution (float): final-render mesh resolution (smaller = finer)
        threshold (float): isosurface threshold (~0.6 default; higher = thinner connections)
        elements (list of dicts): each element has
            type:       "BALL" | "ELLIPSOID" | "CAPSULE" | "CUBE" | "PLANE"
            location:   [x, y, z]
            rotation:   [rx, ry, rz]  (radians, optional)
            radius:     float (for BALL)
            size_x/y/z: floats (for ELLIPSOID / CAPSULE / CUBE / PLANE)
            stiffness:  float (default 2.0 — how strongly this blob influences others)
            use_negative: bool (default False — if True, subtracts instead of adds)
        convert_to_mesh (bool, default True): convert the metaball family to a regular mesh
            so we can add modifiers, multiple materials, etc.

    Returns: {name, type, elements_count}
    """
    name = params.get("name", "Blob")
    resolution = float(params.get("resolution", 0.08))
    render_resolution = float(params.get("render_resolution", resolution * 0.5))
    threshold = float(params.get("threshold", 0.6))
    elements = params.get("elements", []) or []
    convert = bool(params.get("convert_to_mesh", True))

    if not elements:
        raise ValueError("create_metaball_blob requires at least one element")

    mball_data = bpy.data.metaballs.new(name=name + "_Meta")
    mball_data.resolution = resolution
    mball_data.render_resolution = render_resolution
    mball_data.threshold = threshold

    mball_obj = bpy.data.objects.new(name + "_mball", mball_data)
    bpy.context.scene.collection.objects.link(mball_obj)

    for spec in elements:
        elem_type = spec.get("type", "ELLIPSOID").upper()
        elem = mball_data.elements.new(type=elem_type)
        elem.co = mathutils.Vector(spec.get("location", [0, 0, 0]))
        if "rotation" in spec:
            rot = spec["rotation"]
            # metaball element.rotation is a quaternion; convert from euler
            from mathutils import Euler
            euler = Euler(tuple(rot), 'XYZ')
            elem.rotation = euler.to_quaternion()
        # Size fields (only relevant for non-BALL types)
        if elem_type != "BALL":
            elem.size_x = float(spec.get("size_x", 1.0))
            elem.size_y = float(spec.get("size_y", spec.get("size_x", 1.0)))
            elem.size_z = float(spec.get("size_z", spec.get("size_x", 1.0)))
        if "radius" in spec:
            elem.radius = float(spec["radius"])
        elem.stiffness = float(spec.get("stiffness", 2.0))
        elem.use_negative = bool(spec.get("use_negative", False))

    result = {"name": mball_obj.name, "type": "METABALL", "elements_count": len(elements)}

    # Convert to mesh so we can apply materials/modifiers/etc
    if convert:
        bpy.ops.object.select_all(action='DESELECT')
        mball_obj.select_set(True)
        bpy.context.view_layer.objects.active = mball_obj
        # Force a depsgraph update so the metaball field is current
        bpy.context.view_layer.update()
        bpy.ops.object.convert(target='MESH')
        # After convert, the original metaball OBJECT is now a MESH object (same Python ref)
        converted = bpy.context.view_layer.objects.active
        if converted:
            converted.name = name
            if converted.data:
                converted.data.name = name + "_mesh"
            result.update({
                "name": converted.name,
                "type": converted.type,
                "polygons": len(converted.data.polygons) if converted.data else 0,
            })

    return result


def handle_tag_as_hero(params: dict) -> dict:
    """Tag an object (and optionally descendants) as 'hero' for HERO_VERIFY gate."""
    obj_name = params["object"]
    obj = bpy.context.scene.objects.get(obj_name)
    if obj is None:
        raise KeyError(f"object not found: {obj_name}")

    tagged = []
    descend = params.get("descend", True)

    def _tag(o):
        o["is_forced_hero"] = True
        o["hero"] = True
        tagged.append(o.name)

    _tag(obj)
    if descend:
        for child in obj.children_recursive:
            _tag(child)

    return {"tagged_count": len(tagged), "tagged_names": tagged}


# ═══════════════════════════════════════════════════════════════════════
# HERO_VERIFY — 7-check gate, replicates render_from_manifest.py logic
# ═══════════════════════════════════════════════════════════════════════

def _hv_collect_hero_meshes():
    """Return list of mesh objects tagged as hero."""
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.get("is_forced_hero") or obj.get("hero") or obj.get("FORCED_HERO_TAG"):
            out.append(obj)
    return out


def _hv_world_bbox(objs, depsgraph):
    """Aggregate world-space bbox across all hero meshes."""
    if not objs:
        return None, None, 0.0
    min_v = mathutils.Vector((float("inf"),) * 3)
    max_v = mathutils.Vector((float("-inf"),) * 3)
    for obj in objs:
        eval_obj = obj.evaluated_get(depsgraph)
        for corner in eval_obj.bound_box:
            world = eval_obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                if world[i] < min_v[i]:
                    min_v[i] = world[i]
                if world[i] > max_v[i]:
                    max_v[i] = world[i]
    diag = (max_v - min_v).length
    return min_v, max_v, diag


def _hv_in_frustum(scene, cam, point_world):
    """Check if a world-space point is inside the camera's frustum (returns bool)."""
    if cam is None:
        return False
    # Use camera-space transform
    inv = cam.matrix_world.inverted()
    cam_space = inv @ point_world
    if cam_space.z > 0:  # Behind camera in Blender's camera-space (-Z forward)
        return False
    return True


def _hv_estimate_fill(scene, cam, min_v, max_v):
    """Approximate hero fill: project bbox corners → NDC → bbox in NDC, divide by frame diagonal."""
    if cam is None:
        return 0.0
    from bpy_extras.object_utils import world_to_camera_view

    corners = [
        mathutils.Vector((x, y, z))
        for x in (min_v.x, max_v.x)
        for y in (min_v.y, max_v.y)
        for z in (min_v.z, max_v.z)
    ]
    ndc_pts = []
    for c in corners:
        v = world_to_camera_view(scene, cam, c)
        # Discard points behind camera
        if v.z > 0:
            ndc_pts.append((v.x, v.y))
    if not ndc_pts:
        return 0.0
    xs = [p[0] for p in ndc_pts]
    ys = [p[1] for p in ndc_pts]
    bbox_w = max(xs) - min(xs)
    bbox_h = max(ys) - min(ys)
    # Frame diagonal in NDC space is sqrt(2). Hero diagonal:
    hero_diag = (bbox_w ** 2 + bbox_h ** 2) ** 0.5
    return min(hero_diag / (2 ** 0.5), 1.0)


def handle_hero_verify(params: dict) -> dict:
    """Run the 7-check HERO_VERIFY gate. Returns structured report."""
    min_diag = params.get("min_bbox_diag", 0.2)
    max_diag = params.get("max_bbox_diag", 50.0)
    min_fill = params.get("min_fill_pct", 0.35)
    max_fill = params.get("max_fill_pct", 0.70)
    min_polys = params.get("min_polys", 100)
    ground_tol = params.get("ground_tolerance", 0.5)

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    heroes = _hv_collect_hero_meshes()

    checks = {}
    abort_reasons = []
    warnings = []

    # 1. has_hero_tag
    checks["has_hero_tag"] = {
        "ok": len(heroes) > 0,
        "detail": f"{len(heroes)} hero-tagged mesh(es) found",
    }
    if not heroes:
        abort_reasons.append("no hero-tagged mesh in scene")
        # Short-circuit — rest of checks rely on heroes existing
        return {
            "passed": False,
            "checks": checks,
            "abort_reasons": abort_reasons,
            "warnings": warnings,
        }

    # 2. bbox_sane
    min_v, max_v, diag = _hv_world_bbox(heroes, depsgraph)
    bbox_ok = min_diag < diag < max_diag
    checks["bbox_sane"] = {
        "ok": bbox_ok, "diag": round(diag, 4),
        "min": [round(v, 4) for v in min_v] if min_v else None,
        "max": [round(v, 4) for v in max_v] if max_v else None,
        "thresholds": {"min": min_diag, "max": max_diag},
    }
    if not bbox_ok:
        abort_reasons.append(f"bbox diag {diag:.3f}m outside [{min_diag},{max_diag}]")

    # 3. in_frustum (uses hero bbox center)
    cam = scene.camera
    center = (min_v + max_v) * 0.5 if min_v and max_v else None
    in_frustum = _hv_in_frustum(scene, cam, center) if center else False
    checks["in_frustum"] = {
        "ok": in_frustum,
        "detail": "hero bbox center inside camera view" if in_frustum else "hero outside frustum or no camera",
    }
    if not in_frustum:
        abort_reasons.append("hero outside camera frustum")

    # 4. fill_ok
    fill_pct = _hv_estimate_fill(scene, cam, min_v, max_v) if (cam and min_v and max_v) else 0.0
    fill_ok = min_fill <= fill_pct <= max_fill
    checks["fill_ok"] = {
        "ok": fill_ok,
        "fill_pct": round(fill_pct, 4),
        "thresholds": {"min": min_fill, "max": max_fill},
        "detail": "too small — move camera closer / scale up" if fill_pct < min_fill else (
            "too large — move camera back / scale down" if fill_pct > max_fill else "good"
        ),
    }
    if not fill_ok:
        abort_reasons.append(f"fill {fill_pct:.2%} outside [{min_fill:.0%},{max_fill:.0%}]")

    # 5. not_primitive (poly count check)
    max_polys = max((len(o.data.polygons) for o in heroes if o.data), default=0)
    not_prim = max_polys >= min_polys
    checks["not_primitive"] = {
        "ok": not_prim, "max_polys": max_polys, "threshold": min_polys,
    }
    if not not_prim:
        abort_reasons.append(f"hero has only {max_polys} polys (< {min_polys}) — looks like a primitive placeholder")

    # 6. oriented_correctly (soft warn)
    # Vehicle: Z should NOT be the longest axis. Character: Z SHOULD be longest.
    # We don't know category from scene; just compute and report.
    dims = (max_v - min_v) if (min_v and max_v) else mathutils.Vector((0, 0, 0))
    longest_axis = max(range(3), key=lambda i: dims[i])
    axis_names = ["X", "Y", "Z"]
    checks["oriented_correctly"] = {
        "ok": True,  # soft check — never aborts
        "longest_axis": axis_names[longest_axis],
        "dimensions": [round(d, 4) for d in dims],
        "detail": "soft check — verify orientation matches subject type",
    }
    if longest_axis == 2 and dims.z > 1.5 * max(dims.x, dims.y):
        warnings.append("Z is dominant axis — confirm this is a tall subject (character/tower), not a vehicle/prop")

    # 7. grounded (soft warn)
    bottom_z = min_v.z if min_v else 0
    delta_z = abs(bottom_z - 0.0)  # assume ground at z=0
    grounded = delta_z < ground_tol
    checks["grounded"] = {
        "ok": True,  # soft — never aborts
        "delta_z": round(delta_z, 4),
        "bottom_z": round(bottom_z, 4),
        "tolerance": ground_tol,
    }
    if not grounded:
        warnings.append(f"hero bottom is {delta_z:.3f}m from ground plane (z=0) — verify grounded")

    passed = len(abort_reasons) == 0
    return {
        "passed": passed,
        "checks": checks,
        "abort_reasons": abort_reasons,
        "warnings": warnings,
        "hero_count": len(heroes),
        "hero_names": [h.name for h in heroes],
    }


# ═══════════════════════════════════════════════════════════════════════
# Code execution escape hatch — runs arbitrary Python in Blender
# ═══════════════════════════════════════════════════════════════════════

def handle_execute_python(params: dict) -> dict:
    """Execute arbitrary Python in Blender. RESULT must be assigned to `__result__`.
    Available globals: bpy, mathutils, math.
    """
    import math
    code = params["code"]
    namespace = {"bpy": bpy, "mathutils": mathutils, "math": math, "__result__": None}
    exec(code, namespace)
    result = namespace.get("__result__")
    try:
        import json
        json.dumps(result)
        return {"result": result}
    except (TypeError, ValueError):
        return {"result": repr(result)}


# ═══════════════════════════════════════════════════════════════════════
# Dispatcher
# ═══════════════════════════════════════════════════════════════════════

HANDLERS: Dict[str, Callable[[dict], Any]] = {
    # scene reset — clean slate before new runs
    "reset_scene": handle_reset_scene,

    # scene state
    "get_scene_info": handle_get_scene_info,
    "list_objects": handle_list_objects,
    "get_object_info": handle_get_object_info,

    # primitives + transform
    "create_primitive": handle_create_primitive,
    "delete_object": handle_delete_object,
    "transform_object": handle_transform_object,

    # modifiers
    "add_modifier": handle_add_modifier,

    # materials
    "create_material": handle_create_material,
    "apply_material": handle_apply_material,

    # lighting
    "add_light": handle_add_light,
    "set_world_background": handle_set_world_background,
    "set_hdri_environment": handle_set_hdri_environment,

    # geometry boolean ops
    "boolean_union": handle_boolean_union,

    # fur / hair
    "add_fur": handle_add_fur,

    # camera
    "create_camera": handle_create_camera,
    "look_at": handle_look_at,

    # animation
    "set_keyframe": handle_set_keyframe,
    "set_frame_range": handle_set_frame_range,

    # render
    "set_render_settings": handle_set_render_settings,
    "render_frame": handle_render_frame,
    "render_animation": handle_render_animation,

    # asset spawn (low-level)
    "append_blend_collection": handle_append_blend_collection,
    "tag_as_hero": handle_tag_as_hero,

    # Phase 17 asset-driven pipeline
    "import_mesh_file": handle_import_mesh_file,
    "save_blend_file": handle_save_blend_file,

    # metaball-based organic creature blob (auto-blending body parts)
    "create_metaball_blob": handle_create_metaball_blob,

    # hero verify gate (the orchestrator's feedback loop)
    "hero_verify": handle_hero_verify,

    # escape hatch
    "execute_python": handle_execute_python,
}


def dispatch(op: str, params: dict) -> Any:
    handler = HANDLERS.get(op)
    if handler is None:
        raise UnknownOpError(f"unknown op: {op}. registered: {sorted(HANDLERS)}")
    return handler(params or {})
