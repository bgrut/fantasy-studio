from __future__ import annotations


def make_emissive_material(bpy, name: str, color=(1.0, 0.0, 1.0, 1.0), strength=8.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    emission = nodes.new(type="ShaderNodeEmission")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def make_dark_gloss_material(bpy, name="DarkGloss", base=(0.03, 0.03, 0.035, 1.0), roughness=0.12):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.7
    return mat


def make_wet_road_material(bpy, name="WetRoad"):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.10
    bsdf.inputs["Specular IOR Level"].default_value = 1.0
    return mat


def make_natural_ground_material(
    bpy,
    name="NaturalGround",
    base=(0.27, 0.29, 0.23, 1.0),
    roughness=0.92,
):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    return mat


def make_studio_cyc_material(
    bpy,
    name="StudioCyc",
    base=(0.83, 0.84, 0.87, 1.0),
    roughness=0.82,
):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    return mat


def make_automotive_floor_material(
    bpy,
    name="AutomotiveFloor",
    base=(0.025, 0.025, 0.03, 1.0),
    roughness=0.35,
):
    """
    Realistic automotive showroom / wet-look tarmac.
    Roughness 0.35 gives a damp road look — reflective enough to catch HDRI
    and car reflections, but not a mirror that competes with the car body.
    Uses noise texture for subtle surface breakup.
    """
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = base
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Specular IOR Level"].default_value = 0.8

        # Noise-driven roughness variation — breaks the perfectly uniform look
        try:
            tex_coord = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 45.0
            noise.inputs["Detail"].default_value = 6.0
            links.new(tex_coord.outputs["Object"], noise.inputs["Vector"])

            ramp = nodes.new("ShaderNodeMapRange")
            ramp.inputs["From Min"].default_value = 0.3
            ramp.inputs["From Max"].default_value = 0.7
            ramp.inputs["To Min"].default_value = roughness - 0.08
            ramp.inputs["To Max"].default_value = roughness + 0.12
            links.new(noise.outputs["Fac"], ramp.inputs["Value"])
            links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
        except Exception:
            pass  # fall back to flat roughness

    return mat


def make_glass_material(bpy, name="GlassDark", base=(0.02, 0.03, 0.05, 1.0), roughness=0.02, transmission=1.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Transmission Weight"].default_value = transmission
    bsdf.inputs["IOR"].default_value = 1.45
    return mat


def make_road_asphalt_material(bpy, name="RoadAsphalt", wetness=0.3):
    """Dark asphalt with configurable wetness/reflection for cinematic roads."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.035, 0.035, 0.04, 1.0)
        bsdf.inputs["Roughness"].default_value = max(0.05, 0.45 - wetness)
        bsdf.inputs["Specular IOR Level"].default_value = 0.6 + wetness
        # Noise for aggregate breakup
        try:
            tc = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 80.0
            noise.inputs["Detail"].default_value = 8.0
            links.new(tc.outputs["Object"], noise.inputs["Vector"])
            ramp = nodes.new("ShaderNodeMapRange")
            ramp.inputs["From Min"].default_value = 0.35
            ramp.inputs["From Max"].default_value = 0.65
            rough = max(0.05, 0.45 - wetness)
            ramp.inputs["To Min"].default_value = rough - 0.05
            ramp.inputs["To Max"].default_value = rough + 0.10
            links.new(noise.outputs["Fac"], ramp.inputs["Value"])
            links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
        except Exception:
            pass
    return mat


def make_terrain_ground_material(bpy, name="TerrainGround", roughness=0.85):
    """Natural earthy ground with subtle noise color variation."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Specular IOR Level"].default_value = 0.15
        try:
            tc = nodes.new("ShaderNodeTexCoord")
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 12.0
            noise.inputs["Detail"].default_value = 5.0
            links.new(tc.outputs["Object"], noise.inputs["Vector"])
            ramp = nodes.new("ShaderNodeColorRamp")
            ramp.color_ramp.elements[0].color = (0.12, 0.14, 0.08, 1.0)
            ramp.color_ramp.elements[1].color = (0.25, 0.28, 0.18, 1.0)
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        except Exception:
            bsdf.inputs["Base Color"].default_value = (0.18, 0.20, 0.13, 1.0)
    return mat


def make_water_surface_material(bpy, name="WaterSurface", roughness=0.08,
                                 color=(0.05, 0.12, 0.18, 1.0)):
    """Reflective water surface for ocean/lake scenes."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Specular IOR Level"].default_value = 1.0
        bsdf.inputs["IOR"].default_value = 1.33
        try:
            bsdf.inputs["Transmission Weight"].default_value = 0.3
        except Exception:
            pass
    return mat


def make_concrete_material(bpy, name="Concrete", roughness=0.7):
    """Urban concrete/pavement material."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.38, 0.37, 0.35, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
    return mat


def make_metal_brushed_material(bpy, name="BrushedMetal", roughness=0.3):
    """Brushed metal for product scenes."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.72, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Specular IOR Level"].default_value = 0.8
    return mat


def assign_material(obj, mat):
    if obj is None or mat is None or not hasattr(obj.data, "materials"):
        return
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat


# ── Recipe-driven PBR ground material ──────────────────────────────────
# Maps scene_recipe ground types to tuned Principled BSDF presets with
# noise-based surface variation for more realistic ground reads.

_GROUND_PRESETS: dict[str, dict] = {
    "grass":          {"base": (0.12, 0.22, 0.06, 1.0), "roughness": 0.95, "specular": 0.1},
    "sand":           {"base": (0.60, 0.52, 0.35, 1.0), "roughness": 0.98, "specular": 0.05},
    "concrete":       {"base": (0.35, 0.34, 0.33, 1.0), "roughness": 0.88, "specular": 0.25},
    "asphalt":        {"base": (0.06, 0.06, 0.07, 1.0), "roughness": 0.65, "specular": 0.4},
    "wet_asphalt":    {"base": (0.04, 0.04, 0.05, 1.0), "roughness": 0.12, "specular": 0.9},
    "dirt":           {"base": (0.22, 0.16, 0.10, 1.0), "roughness": 0.95, "specular": 0.08},
    "snow":           {"base": (0.85, 0.88, 0.92, 1.0), "roughness": 0.80, "specular": 0.15},
    "rock":           {"base": (0.25, 0.23, 0.21, 1.0), "roughness": 0.92, "specular": 0.2},
    "water":          {"base": (0.02, 0.08, 0.15, 1.0), "roughness": 0.05, "specular": 1.0},
    "wood":           {"base": (0.30, 0.20, 0.10, 1.0), "roughness": 0.75, "specular": 0.15},
    "studio":         {"base": (0.83, 0.84, 0.87, 1.0), "roughness": 0.82, "specular": 0.35},
    "terrain_ground": {"base": (0.27, 0.29, 0.23, 1.0), "roughness": 0.92, "specular": 0.2},
}


def make_ground_material_from_recipe(bpy, ground_type: str, name: str = ""):
    """Create a PBR ground material based on the scene recipe's ground type.

    Uses Principled BSDF with a noise texture for surface variation.
    Falls back to ``terrain_ground`` for unknown types.
    """
    preset = _GROUND_PRESETS.get(ground_type, _GROUND_PRESETS["terrain_ground"])
    mat_name = name or f"PBR_Ground_{ground_type}"

    existing = bpy.data.materials.get(mat_name)
    if existing:
        return existing

    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        return mat

    bsdf.inputs["Base Color"].default_value = preset["base"]
    bsdf.inputs["Roughness"].default_value = preset["roughness"]
    try:
        bsdf.inputs["Specular IOR Level"].default_value = preset["specular"]
    except Exception:
        pass

    # Add noise texture for surface variation (breaks up flat reads)
    try:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 12.0
        noise.inputs["Detail"].default_value = 8.0
        noise.inputs["Roughness"].default_value = 0.6
        noise.location = (-400, -200)

        # Mix noise into roughness for subtle surface detail
        map_range = nodes.new("ShaderNodeMapRange")
        map_range.inputs["From Min"].default_value = 0.0
        map_range.inputs["From Max"].default_value = 1.0
        base_rough = preset["roughness"]
        map_range.inputs["To Min"].default_value = max(0.0, base_rough - 0.08)
        map_range.inputs["To Max"].default_value = min(1.0, base_rough + 0.08)
        map_range.location = (-200, -200)

        links.new(noise.outputs["Fac"], map_range.inputs["Value"])
        links.new(map_range.outputs["Result"], bsdf.inputs["Roughness"])
    except Exception:
        pass  # Noise variation is optional polish

    return mat
