"""
World Builder — adds cinematic environment layers to every scene.
Runs after template build. Only ADDS elements, never removes or modifies
existing ones.

Every function:
  - Checks whether the element already exists before adding.
  - Writes clear [WORLD] log lines so a render without world build steps
    is obvious in the log.
  - Never touches anything the template owns. If a template has already
    loaded an HDRI, set its own ground material, placed its own key
    light, etc., world_builder leaves it alone and moves on to the next
    layer.

Called from render_from_manifest.py wrapped in try/except so it can
never crash a render.
"""
import bpy
import math
import random
from mathutils import Vector
from pathlib import Path

# Absolute path to assets — Blender subprocess needs this
ASSET_ROOT = Path(r"C:/Users/bgrut/Desktop/FantasyAI/blender-studio-backend/assets")


def build_world(manifest, hero_objects=None):
    """
    Main entry point. Adds environment richness based on scene family and mood.
    Call this in render_from_manifest.py AFTER template build, BEFORE render.

    When `manifest["scene_recipe"]` is present (produced by
    scene_recipe_builder), each step reads hints from it to make smarter
    choices (HDRI keywords, ground override, atmosphere density, compositor
    bloom threshold, vignette, etc.). The recipe only INFORMS — it never
    replaces the existing logic and never overrides what the template set.
    """
    family = manifest.get("template_name") or manifest.get("scene_plan", {}).get("template_family", "street_scene")
    environment = manifest.get("scene_plan", {}).get("environment", "outdoor")
    time_of_day = manifest.get("scene_plan", {}).get("time_of_day", "golden_hour")
    mood = manifest.get("scene_plan", {}).get("mood", "cinematic")

    # V1.3 Bug 2 gate — suppresses synthetic env-scale props when a
    # real env asset was imported by render_from_manifest.
    has_forced_env = bool(
        manifest.get("forced_environment_path")
        or manifest.get("forced_environment_id")
        or manifest.get("_auto_picked_environment")
        or manifest.get("_has_forced_environment")
    )

    recipe = manifest.get("scene_recipe") or {}
    recipe_summary = recipe.get("summary") or {}
    # Recipe summary is authoritative when present (it was built with
    # prompt_intelligence enrichment); fall back to scene_plan values.
    environment = recipe_summary.get("environment") or environment
    time_of_day = recipe_summary.get("time_of_day") or time_of_day
    mood = recipe_summary.get("mood") or mood

    print(
        f"[WORLD] Building world for family={family}, env={environment}, "
        f"time={time_of_day}, mood={mood}, recipe={'yes' if recipe else 'no'}"
    )

    # 1. Ensure strong HDRI sky (not just any HDRI — pick the RIGHT one)
    sky_recipe = recipe.get("sky") or {}
    ensure_cinematic_sky(
        time_of_day,
        environment,
        recipe_hdri_keywords=sky_recipe.get("hdri_keywords") or [],
    )

    # 2. Enhance ground with better material
    ground_recipe = recipe.get("ground") or {}
    enhance_ground(family, environment, recipe_ground=ground_recipe)

    # 3. Add atmospheric depth
    atmo_recipe = recipe.get("atmosphere") or {}
    render_tier = manifest.get("render_tier") or manifest.get("quality_tier") or "standard"
    add_cinematic_atmosphere(time_of_day, mood, recipe_atmosphere=atmo_recipe, render_tier=render_tier)

    # 4. Add 3-point cinematic lighting
    hero_center = get_hero_center(hero_objects) if hero_objects else (0, 0, 1)
    lighting_recipe = recipe.get("lighting") or {}
    ensure_cinematic_lighting(
        hero_center, time_of_day,
        recipe_lighting=lighting_recipe,
    )

    # 5. Add environment-specific props and details
    add_environment_details(family, environment, hero_center, has_forced_env=has_forced_env)

    # 6. Set up compositor for cinematic post-processing
    compositor_recipe = recipe.get("compositor") or {}
    setup_compositor(mood, time_of_day, recipe_compositor=compositor_recipe)

    # 7. LAST STEP: pull the camera back if it was framed too tight on the hero.
    #    Runs after every other element is placed so we know the final scene
    #    bounds. Wrapped in try/except to stay defensive — a framing failure
    #    must not break the render.
    try:
        adjust_camera_framing(manifest, hero_objects)
    except Exception as e:
        print(f"[CAMERA] adjust_camera_framing failed (non-fatal): {e}")

    print(f"[WORLD] World build complete")


def ensure_cinematic_sky(time_of_day, environment, recipe_hdri_keywords=None):
    """
    Load the best matching HDRI for the scene.
    If an HDRI is already loaded by the template, leave it alone.

    `recipe_hdri_keywords` (optional) is a list of extra keywords (from the
    scene recipe) that boost the score of HDRIs whose filename matches them.
    """
    world = bpy.context.scene.world

    # Check if template already loaded an HDRI
    if world and world.use_nodes:
        for node in world.node_tree.nodes:
            if node.type == 'TEX_ENVIRONMENT' and node.image:
                print(f"[WORLD] Sky already set: {node.image.filepath}")
                return  # Template handled it — don't override

    # Find the best HDRI match
    hdri_dir = ASSET_ROOT / "hdri"
    if not hdri_dir.exists():
        print(f"[WORLD] No HDRI directory at {hdri_dir}")
        create_procedural_sky(time_of_day)
        return

    hdri_files = list(hdri_dir.glob("*.hdr")) + list(hdri_dir.glob("*.exr"))
    if not hdri_files:
        print(f"[WORLD] No HDRI files found")
        create_procedural_sky(time_of_day)
        return

    # Score HDRIs by relevance to time_of_day and environment
    best_hdri = score_and_pick_hdri(
        hdri_files, time_of_day, environment,
        extra_keywords=recipe_hdri_keywords or [],
    )
    load_hdri(best_hdri)


def score_and_pick_hdri(hdri_files, time_of_day, environment, extra_keywords=None):
    """Pick the best HDRI based on filename matching.

    Recipe `extra_keywords` (optional) receive a +2 bonus per match on top
    of the time/env scores. Useful when the scene recipe specified
    context-specific keywords like 'stadium' or 'tropical'.
    """
    time_keywords = {
        "dawn": ["dawn", "sunrise", "morning", "early", "pink"],
        "morning": ["morning", "bright", "clear", "blue_sky"],
        "midday": ["midday", "noon", "clear", "blue", "sunny", "bright"],
        "golden_hour": ["golden", "sunset", "warm", "golden_hour", "evening"],
        "sunset": ["sunset", "dusk", "orange", "warm", "evening", "red"],
        "dusk": ["dusk", "twilight", "evening", "blue_hour", "purple"],
        "night": ["night", "dark", "stars", "city_night", "moon", "neon"],
    }

    env_keywords = {
        "city": ["city", "urban", "downtown", "street", "building"],
        "park": ["park", "garden", "green", "nature", "outdoor"],
        "forest": ["forest", "tree", "canopy", "woods", "jungle"],
        "highway": ["road", "highway", "desert", "landscape", "open"],
        "ocean": ["ocean", "sea", "water", "coast", "beach", "tropical"],
        "mountain": ["mountain", "peak", "alpine", "landscape", "panorama"],
        "studio": ["studio", "neutral", "white", "indoor", "soft"],
        "desert": ["desert", "sand", "arid", "dry", "wasteland"],
    }

    time_kw = time_keywords.get(time_of_day, ["blue", "sky"])
    env_kw = env_keywords.get(environment, [])

    extra_kw = [str(k).lower() for k in (extra_keywords or [])]

    scored = []
    for f in hdri_files:
        name = f.stem.lower()
        score = 0
        for kw in time_kw:
            if kw in name:
                score += 3
        for kw in env_kw:
            if kw in name:
                score += 2
        for kw in extra_kw:
            if kw and kw in name:
                score += 2
        scored.append((f, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    chosen = scored[0][0]
    print(
        f"[WORLD] Best HDRI: {chosen.name} (score={scored[0][1]}, "
        f"recipe_kw={extra_kw[:4]})"
    )
    return chosen


def load_hdri(hdri_path):
    """Load an HDRI as world environment."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world

    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    # Don't wipe nodes if template already set something up
    # Just add/replace the environment texture
    tex_node = None
    bg_node = None
    output_node = None

    for n in nodes:
        if n.type == 'TEX_ENVIRONMENT':
            tex_node = n
        elif n.type == 'BACKGROUND':
            bg_node = n
        elif n.type == 'OUTPUT_WORLD':
            output_node = n

    if not tex_node:
        tex_node = nodes.new('ShaderNodeTexEnvironment')
    if not bg_node:
        bg_node = nodes.new('ShaderNodeBackground')
    if not output_node:
        output_node = nodes.new('ShaderNodeOutputWorld')

    try:
        tex_node.image = bpy.data.images.load(str(hdri_path))
        bg_node.inputs[1].default_value = 1.0
        links.new(tex_node.outputs[0], bg_node.inputs[0])
        links.new(bg_node.outputs[0], output_node.inputs[0])
        print(f"[WORLD] HDRI loaded: {hdri_path.name}")
    except Exception as e:
        print(f"[WORLD] HDRI load failed: {e}")
        create_procedural_sky("midday")


def create_procedural_sky(time_of_day):
    """Fallback: create a gradient sky."""
    colors = {
        "dawn": (0.85, 0.65, 0.5, 1),
        "morning": (0.5, 0.65, 0.85, 1),
        "midday": (0.4, 0.55, 0.8, 1),
        "golden_hour": (0.95, 0.75, 0.45, 1),
        "sunset": (0.95, 0.55, 0.3, 1),
        "dusk": (0.3, 0.3, 0.55, 1),
        "night": (0.05, 0.07, 0.15, 1),
    }
    color = colors.get(time_of_day, (0.4, 0.55, 0.8, 1))

    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if not bg:
        bg = world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = color
    bg.inputs[1].default_value = 2.0
    print(f"[WORLD] Procedural sky: {time_of_day} {color[:3]}")


_RECIPE_GROUND_TO_FAMILY: dict[str, str] = {
    # Maps the recipe's `ground.material` tokens onto the existing
    # enhance_ground family presets so we don't have to duplicate the
    # material-node wiring.
    "asphalt":     "car_hero",
    "concrete":    "street_scene",
    "grass":       "scenic_landscape",
    "terrain":     "scenic_landscape",
    "sand":        "scenic_landscape",
    "snow":        "scenic_landscape",
    "water":       "ocean_scene",
    "wood_floor":  "character_stage",
    "tile":        "character_stage",
    "dark_glossy": "character_stage",
    "metal":       "product_scene",
    "studio":      "product_scene",
    "stone_floor": "character_stage",
}


def enhance_ground(family, environment, recipe_ground=None):
    """Improve the ground plane material to match the environment.

    When `recipe_ground` is provided and specifies a material the recipe
    prefers, map it onto the closest family preset so we use the recipe's
    intent instead of the raw template family (useful for complex
    environments like 'stadium' where template family is 'auto' but the
    recipe calls for grass).
    """
    recipe_ground = recipe_ground or {}
    recipe_material = str(recipe_ground.get("material") or "").lower().strip()
    if recipe_material:
        mapped = _RECIPE_GROUND_TO_FAMILY.get(recipe_material)
        if mapped:
            print(f"[WORLD] Ground override from recipe: material={recipe_material} -> family preset={mapped}")
            family = mapped
    # Find existing ground plane
    ground = None
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and ("ground" in obj.name.lower() or "plane" in obj.name.lower() or "floor" in obj.name.lower()):
            if obj.dimensions.x > 10:
                ground = obj
                break

    if not ground:
        # Create a large ground plane if none exists
        bpy.ops.mesh.primitive_plane_add(size=500, location=(0, 0, 0))
        ground = bpy.context.active_object
        ground.name = "World_Ground"

    # Determine material based on family + environment
    material_settings = {
        "car_hero": {"color": (0.06, 0.06, 0.06, 1), "roughness": 0.65, "specular": 0.4, "name": "Asphalt"},
        "street_scene": {"color": (0.12, 0.12, 0.11, 1), "roughness": 0.7, "specular": 0.3, "name": "UrbanGround"},
        "scenic_landscape": {"color": (0.12, 0.22, 0.06, 1), "roughness": 0.95, "specular": 0.05, "name": "Grass"},
        "ocean_scene": {"color": (0.01, 0.05, 0.12, 1), "roughness": 0.05, "specular": 0.9, "name": "OceanFloor"},
        "character_stage": {"color": (0.25, 0.25, 0.25, 1), "roughness": 0.4, "specular": 0.3, "name": "StageFloor"},
        "product_scene": {"color": (0.8, 0.8, 0.8, 1), "roughness": 0.3, "specular": 0.2, "name": "StudioFloor"},
    }

    settings = material_settings.get(family, material_settings["scenic_landscape"])

    # Only apply if ground has no material or has a generic one
    if not ground.data.materials or ground.data.materials[0].name in ["Material", "GroundMaterial", "GroundMat"]:
        mat = bpy.data.materials.new(settings["name"])
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = settings["color"]
            bsdf.inputs["Roughness"].default_value = settings["roughness"]
            # Handle different Blender versions for specular
            for spec_name in ["Specular IOR Level", "Specular"]:
                if spec_name in bsdf.inputs:
                    bsdf.inputs[spec_name].default_value = settings["specular"]
                    break

        if ground.data.materials:
            ground.data.materials[0] = mat
        else:
            ground.data.materials.append(mat)

        print(f"[WORLD] Ground material: {settings['name']}")


def add_cinematic_atmosphere(time_of_day, mood, recipe_atmosphere=None, render_tier=None):
    """Add volumetric fog for depth and cinematic feel.

    When `recipe_atmosphere` provides a density, use it as the base rather
    than the time/mood table. Underwater recipes (type=='underwater') also
    tint the volume toward deep blue-green.

    Skipped entirely for preview tier renders — volumetrics add render time
    and often hurt more than they help at low quality.
    """
    # Skip atmosphere for preview renders — faster and often cleaner.
    if render_tier == "preview":
        print("[WORLD] Skipping atmosphere for preview tier")
        return

    # Check if atmosphere already exists
    for obj in bpy.data.objects:
        if "atmosphere" in obj.name.lower() or "volume" in obj.name.lower() or "fog" in obj.name.lower():
            print("[WORLD] Atmosphere already exists — skipping")
            return

    # Densities halved across the board (Phase K feedback: scenes were
    # drowning in fog — buildings obscured, hero blurred). Atmosphere
    # should add DEPTH not OBSCURE the subject.
    density_map = {
        "dawn":         0.004,   # was 0.008
        "morning":      0.0015,  # was 0.003
        "midday":       0.001,   # was 0.002
        "golden_hour":  0.003,   # was 0.006
        "sunset":       0.004,   # was 0.008
        "dusk":         0.005,   # was 0.01
        "night":        0.006,   # was 0.012
    }

    # Mood boosts also trimmed — "foggy" = 3.0 used to push density to 0.036,
    # which is pea-soup territory. These values still differentiate moods
    # without eating the scene.
    mood_boost = {
        "dramatic": 1.3,   # was 1.5
        "moody":    1.4,   # was 1.8
        "foggy":    2.0,   # was 3.0 — still fogged, but readable
        "misty":    1.7,   # was 2.5
        "cinematic": 1.1,  # was 1.2
        "peaceful": 0.8,
        "clear":    0.4,   # was 0.5
    }

    recipe_atmosphere = recipe_atmosphere or {}
    recipe_density = recipe_atmosphere.get("density")
    is_underwater = recipe_atmosphere.get("type") == "underwater"

    if recipe_density is not None:
        try:
            density = float(recipe_density)
            print(f"[WORLD] Atmosphere density from recipe: {density:.4f}")
        except (TypeError, ValueError):
            density = density_map.get(time_of_day, 0.004) * mood_boost.get(mood, 1.0)
    else:
        base_density = density_map.get(time_of_day, 0.004)
        boost = mood_boost.get(mood, 1.0)
        density = base_density * boost

    # HARD CAP — fog should add depth, not drown the scene. Reduced from
    # 0.01 to 0.004 after continued feedback that scenes were still hazy.
    if density > 0.004:
        print(
            f"[WORLD] Atmosphere density {density:.4f} clamped to 0.004 "
            f"(prevents pea-soup fog)"
        )
        density = 0.004

    # Color based on time (or underwater recipe override)
    color_map = {
        "dawn": (1.0, 0.85, 0.7, 1),
        "golden_hour": (1.0, 0.9, 0.75, 1),
        "sunset": (1.0, 0.8, 0.6, 1),
        "night": (0.25, 0.3, 0.45, 1),
        "midday": (0.85, 0.88, 0.95, 1),
    }
    if is_underwater:
        # Recipe may ship a 3-tuple color; pad to RGBA for the shader input.
        rc = recipe_atmosphere.get("color") or (0.1, 0.3, 0.5)
        if len(rc) == 3:
            color = (float(rc[0]), float(rc[1]), float(rc[2]), 1.0)
        else:
            color = tuple(float(x) for x in rc[:4])
    else:
        color = color_map.get(time_of_day, (0.85, 0.88, 0.95, 1))

    # Volume cube shrunk from 80→50 and raised to z=25. Smaller volume
    # means less fog between camera and hero at ground level. Higher
    # placement concentrates haze overhead for depth without obscuring
    # the hero at eye level.
    bpy.ops.mesh.primitive_cube_add(size=50, location=(0, 0, 25))
    vol = bpy.context.active_object
    vol.name = "World_Atmosphere"
    vol.display_type = 'WIRE'

    mat = bpy.data.materials.new("AtmosphereMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for n in list(nodes):
        nodes.remove(n)

    output = nodes.new("ShaderNodeOutputMaterial")
    scatter = nodes.new("ShaderNodeVolumeScatter")
    scatter.inputs["Density"].default_value = density
    scatter.inputs["Color"].default_value = color
    links.new(scatter.outputs["Volume"], output.inputs["Volume"])
    vol.data.materials.append(mat)

    print(f"[WORLD] Atmosphere: density={density:.4f}, time={time_of_day}, mood={mood}")


def ensure_cinematic_lighting(hero_center, time_of_day, recipe_lighting=None):
    """
    Add 3-point cinematic lighting if no area/sun lights exist.
    Templates that set up their own lights are untouched.

    When `recipe_lighting` is provided it overrides the key-light energy
    and color temperature picks (interior scenes use warmer, lower-energy
    keys, for example).
    """
    existing_lights = [obj for obj in bpy.data.objects if obj.type == 'LIGHT']
    area_or_sun = [l for l in existing_lights if l.data.type in ('AREA', 'SUN')]

    if len(area_or_sun) >= 2:
        print(f"[WORLD] Lighting already set up ({len(area_or_sun)} lights) — skipping")
        return

    cx, cy, cz = hero_center

    warm_times = ["golden_hour", "sunset", "dawn"]
    is_warm = time_of_day in warm_times
    is_night = time_of_day in ["night", "dusk"]

    recipe_lighting = recipe_lighting or {}
    recipe_style = str(recipe_lighting.get("style") or "").lower()
    recipe_color_temp = str(recipe_lighting.get("color_temp") or "").lower()
    recipe_key_energy = recipe_lighting.get("key_energy")

    # Energy: recipe wins if numeric; else time-of-day default.
    if recipe_key_energy is not None:
        try:
            key_energy = float(recipe_key_energy)
        except (TypeError, ValueError):
            key_energy = 80 if is_night else 250
    else:
        key_energy = 80 if is_night else 250

    # Color temp: recipe wins if specified.
    if recipe_color_temp == "warm":
        key_color = (1.0, 0.85, 0.65)
    elif recipe_color_temp == "cool":
        key_color = (0.35, 0.4, 0.55)
    elif recipe_color_temp == "neutral":
        key_color = (1.0, 0.97, 0.93)
    else:
        key_color = (1.0, 0.85, 0.65) if is_warm else (0.35, 0.4, 0.55) if is_night else (1.0, 0.97, 0.93)

    if recipe_style:
        print(f"[WORLD] Lighting recipe: style={recipe_style}, temp={recipe_color_temp}, key_energy={key_energy}")

    # Key light — main illumination
    bpy.ops.object.light_add(type='AREA', location=(cx + 6, cy - 6, cz + 7))
    key = bpy.context.active_object
    key.name = "World_Key_Light"
    key.data.energy = key_energy
    key.data.size = 4.0
    key.data.color = key_color
    direction = Vector((cx, cy, cz)) - key.location
    key.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    # Fill light — softer, opposite side
    bpy.ops.object.light_add(type='AREA', location=(cx - 5, cy - 3, cz + 3))
    fill = bpy.context.active_object
    fill.name = "World_Fill_Light"
    fill.data.energy = key_energy * 0.25
    fill.data.size = 6.0
    fill.data.color = (0.8, 0.85, 1.0)
    direction = Vector((cx, cy, cz)) - fill.location
    fill.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    # Rim light — edge separation
    bpy.ops.object.light_add(type='AREA', location=(cx + 2, cy + 7, cz + 5))
    rim = bpy.context.active_object
    rim.name = "World_Rim_Light"
    rim.data.energy = key_energy * 0.5
    rim.data.size = 2.5
    rim.data.color = key_color
    direction = Vector((cx, cy, cz)) - rim.location
    rim.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    print(f"[WORLD] 3-point lighting: key={key_energy}W, time={time_of_day}")


def add_environment_details(family, environment, hero_center, has_forced_env: bool = False):
    """
    Add procedural environment details using Blender primitives.
    These are simple geometric props that add depth without downloading anything.

    The ``environment`` string carries the prompt-level setting (mountain /
    desert / forest / etc). When it mentions a specific landscape token we
    prefer the matching procedural terrain over the family's default
    fillers so e.g. "eagle over mountains" actually gets mountain terrain
    instead of the scenic_landscape two-sphere filler.

    ``has_forced_env`` (V1.3 Bug 2 gate): when True, skip ALL procedural
    detail creation — the imported environment asset is the backdrop and
    any procedural geometry here would just occlude or compete with it.
    """
    # V1.3 Bug 2 gate — early return before prompt-terrain override AND
    # family branching. Both paths create env-scale geometry that would
    # fight the forced env.
    if has_forced_env:
        print("[WORLD] add_environment_details SKIPPED — forced env active", flush=True)
        return

    cx, cy, cz = hero_center
    env_lower = str(environment or "").lower()

    # Prompt-specific terrain overrides come first so they win regardless
    # of family. Each helper is guarded so a failure here never blocks the
    # family-default fallbacks below.
    terrain_added = False
    try:
        if any(t in env_lower for t in ("mountain", "alpine", "peak", "summit", "snowcap")):
            add_mountain_terrain()
            terrain_added = True
        elif "desert" in env_lower or "dune" in env_lower:
            add_desert_terrain()
            terrain_added = True
        elif "forest" in env_lower or "jungle" in env_lower or "woodland" in env_lower:
            add_forest_trees(hero_center)
            terrain_added = True
    except Exception as e:
        print(f"[WORLD] terrain override failed (non-fatal): {e}")

    if terrain_added:
        return

    if family == "car_hero":
        add_road_details(cx, cy)
    elif family == "street_scene":
        add_urban_details(cx, cy)
    elif family == "scenic_landscape":
        add_nature_details(cx, cy)
    elif family == "ocean_scene":
        pass  # Ocean template handles its own environment
    elif family == "character_stage":
        add_stage_details(cx, cy)
    elif family == "product_scene":
        add_studio_details(cx, cy)


def add_mountain_terrain(distance: float = 60.0, height: float = 30.0, size: float = 220.0):
    """
    Create a subdivided plane with clouds-noise displacement to read as
    distant mountains. Much more convincing than the two-sphere filler
    that ``add_nature_details`` previously used.
    """
    try:
        # Skip if we already built mountains this run.
        if any(o.name.startswith("Mountain_Terrain") for o in bpy.data.objects):
            return
        bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, distance, 0.0))
        terrain = bpy.context.active_object
        terrain.name = "Mountain_Terrain"

        bpy.ops.object.mode_set(mode='EDIT')
        try:
            for _ in range(5):
                bpy.ops.mesh.subdivide()
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

        tex = bpy.data.textures.new("MountainNoise", 'CLOUDS')
        tex.noise_scale = 18.0
        try:
            tex.noise_depth = 3
        except Exception:
            pass
        mod = terrain.modifiers.new("Displace", 'DISPLACE')
        mod.texture = tex
        mod.strength = height
        mod.mid_level = 0.0

        mat = bpy.data.materials.new("MountainMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.22, 0.26, 0.22, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.95
        terrain.data.materials.append(mat)

        # Second, closer ridge for depth layering.
        bpy.ops.mesh.primitive_plane_add(size=size * 0.55, location=(-35.0, distance - 20.0, 0.0))
        ridge = bpy.context.active_object
        ridge.name = "Mountain_Terrain_Ridge"
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            for _ in range(4):
                bpy.ops.mesh.subdivide()
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        tex2 = bpy.data.textures.new("RidgeNoise", 'CLOUDS')
        tex2.noise_scale = 10.0
        mod2 = ridge.modifiers.new("Displace", 'DISPLACE')
        mod2.texture = tex2
        mod2.strength = height * 0.55
        mod2.mid_level = 0.0
        ridge.data.materials.append(mat)

        print(f"[WORLD] mountain terrain added at distance={distance} height={height}")
    except Exception as e:
        print(f"[WORLD] add_mountain_terrain failed: {e}")


def add_desert_terrain(size: float = 180.0, height: float = 6.0):
    """Low dune ripples under the hero for desert prompts."""
    try:
        if any(o.name.startswith("Desert_Terrain") for o in bpy.data.objects):
            return
        bpy.ops.mesh.primitive_plane_add(size=size, location=(0.0, 30.0, -0.15))
        dunes = bpy.context.active_object
        dunes.name = "Desert_Terrain"
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            for _ in range(4):
                bpy.ops.mesh.subdivide()
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        tex = bpy.data.textures.new("DuneNoise", 'CLOUDS')
        tex.noise_scale = 6.5
        mod = dunes.modifiers.new("Displace", 'DISPLACE')
        mod.texture = tex
        mod.strength = height
        mod.mid_level = 0.5
        mat = bpy.data.materials.new("DesertMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.78, 0.60, 0.32, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.9
        dunes.data.materials.append(mat)
        print("[WORLD] desert dunes added")
    except Exception as e:
        print(f"[WORLD] add_desert_terrain failed: {e}")


def add_forest_trees(hero_center):
    """Scatter simple cone trees around the hero for forest prompts."""
    try:
        if any(o.name.startswith("Forest_Tree_") for o in bpy.data.objects):
            return
        cx, cy, _cz = hero_center
        trunk_mat = bpy.data.materials.new("TreeTrunk")
        trunk_mat.use_nodes = True
        b1 = trunk_mat.node_tree.nodes.get("Principled BSDF")
        if b1:
            b1.inputs["Base Color"].default_value = (0.18, 0.10, 0.06, 1.0)
            b1.inputs["Roughness"].default_value = 0.95
        leaf_mat = bpy.data.materials.new("TreeLeaves")
        leaf_mat.use_nodes = True
        b2 = leaf_mat.node_tree.nodes.get("Principled BSDF")
        if b2:
            b2.inputs["Base Color"].default_value = (0.12, 0.32, 0.10, 1.0)
            b2.inputs["Roughness"].default_value = 0.85
        # Two rings of trees: mid and far.
        for i in range(14):
            r = random.uniform(12.0, 28.0)
            theta = random.uniform(0.0, math.tau)
            tx = cx + r * math.cos(theta)
            ty = cy + r * math.sin(theta) + 8.0
            height = random.uniform(6.0, 11.0)
            bpy.ops.mesh.primitive_cylinder_add(
                radius=0.3, depth=height * 0.35,
                location=(tx, ty, height * 0.175),
            )
            trunk = bpy.context.active_object
            trunk.name = f"Forest_Tree_Trunk_{i}"
            trunk.data.materials.append(trunk_mat)
            bpy.ops.mesh.primitive_cone_add(
                radius1=1.6, depth=height * 0.75,
                location=(tx, ty, height * 0.55),
            )
            leaves = bpy.context.active_object
            leaves.name = f"Forest_Tree_Leaves_{i}"
            leaves.data.materials.append(leaf_mat)
        print("[WORLD] forest trees scattered")
    except Exception as e:
        print(f"[WORLD] add_forest_trees failed: {e}")


def add_road_details(cx, cy):
    """Add road markings, barriers, and horizon elements for car scenes."""
    # Road lane markings (simple white strips)
    for i in range(-5, 15, 3):
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(cx, cy + i * 3, 0.005),
            scale=(0.08, 1.0, 0.005)
        )
        marking = bpy.context.active_object
        marking.name = f"Road_Marking_{i}"
        mat = bpy.data.materials.new("RoadMarking")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.85, 1)
            bsdf.inputs["Roughness"].default_value = 0.5
        marking.data.materials.append(mat)

    print(f"[WORLD] Added road details")


def add_urban_details(cx, cy):
    """Add simple urban geometry — distant building silhouettes."""
    building_mat = bpy.data.materials.new("BuildingSilhouette")
    building_mat.use_nodes = True
    bsdf = building_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.15, 0.15, 0.18, 1)
        bsdf.inputs["Roughness"].default_value = 0.8

    # Background buildings
    for i in range(6):
        height = random.uniform(8, 25)
        width = random.uniform(3, 8)
        x_offset = random.uniform(-30, 30)
        y_offset = random.uniform(20, 50)

        bpy.ops.mesh.primitive_cube_add(
            size=1,
            location=(cx + x_offset, cy + y_offset, height / 2),
            scale=(width, width * 0.6, height)
        )
        building = bpy.context.active_object
        building.name = f"Background_Building_{i}"
        building.data.materials.append(building_mat)

    print(f"[WORLD] Added urban background buildings")


def add_nature_details(cx, cy):
    """Add simple nature elements — distant hills, ground variation."""
    # Distant hill (large smooth sphere half-buried)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=80,
        location=(cx + 40, cy + 60, -50),
        segments=24, ring_count=16
    )
    hill = bpy.context.active_object
    hill.name = "Distant_Hill"

    hill_mat = bpy.data.materials.new("HillMaterial")
    hill_mat.use_nodes = True
    bsdf = hill_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.15, 0.28, 0.1, 1)
        bsdf.inputs["Roughness"].default_value = 0.95
    hill.data.materials.append(hill_mat)

    # Second hill for depth
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=100,
        location=(cx - 50, cy + 80, -65),
        segments=24, ring_count=16
    )
    hill2 = bpy.context.active_object
    hill2.name = "Distant_Hill_2"
    hill2.data.materials.append(hill_mat)

    print(f"[WORLD] Added nature details: hills")


def add_stage_details(cx, cy):
    """Add studio stage elements — backdrop, soft floor reflection."""
    # Studio backdrop (large curved plane behind subject)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=30, depth=20,
        location=(cx, cy + 15, 10),
        rotation=(math.radians(90), 0, 0)
    )
    backdrop = bpy.context.active_object
    backdrop.name = "Studio_Backdrop"

    backdrop_mat = bpy.data.materials.new("StudioBackdrop")
    backdrop_mat.use_nodes = True
    bsdf = backdrop_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.3, 0.3, 0.32, 1)
        bsdf.inputs["Roughness"].default_value = 0.5
    backdrop.data.materials.append(backdrop_mat)

    print(f"[WORLD] Added stage backdrop")


def add_studio_details(cx, cy):
    """Add product studio elements."""
    # Simple pedestal
    bpy.ops.mesh.primitive_cylinder_add(
        radius=1.5, depth=0.3,
        location=(cx, cy, 0.15)
    )
    pedestal = bpy.context.active_object
    pedestal.name = "Product_Pedestal"

    ped_mat = bpy.data.materials.new("PedestalMat")
    ped_mat.use_nodes = True
    bsdf = ped_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1)
        bsdf.inputs["Roughness"].default_value = 0.2
    pedestal.data.materials.append(ped_mat)

    print(f"[WORLD] Added product studio pedestal")


def setup_compositor(mood, time_of_day, recipe_compositor=None):
    """
    Enable Blender's compositor for cinematic post-processing.
    Adds: glare/bloom, slight vignette, color management.

    When `recipe_compositor` is provided, `bloom_threshold` and `vignette`
    flags come from the recipe instead of the hard-coded defaults.
    """
    recipe_compositor = recipe_compositor or {}
    recipe_bloom_threshold = recipe_compositor.get("bloom_threshold")
    recipe_vignette_enabled = recipe_compositor.get("vignette")

    bpy.context.scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    nodes = tree.nodes
    links = tree.links

    # Check if compositor is already set up with more than just render layers
    if len(nodes) > 3:
        print("[WORLD] Compositor already configured — skipping")
        return

    # Clear default nodes
    for n in list(nodes):
        nodes.remove(n)

    # Render Layers → Glare → Composite
    rl = nodes.new('CompositorNodeRLayers')
    rl.location = (0, 0)

    glare = nodes.new('CompositorNodeGlare')
    glare.location = (300, 0)
    glare.glare_type = 'FOG_GLOW'
    glare.quality = 'MEDIUM'
    if recipe_bloom_threshold is not None:
        try:
            glare.threshold = float(recipe_bloom_threshold)
        except (TypeError, ValueError):
            glare.threshold = 0.8
    else:
        glare.threshold = 0.8
    glare.size = 6

    # Color balance for cinematic look
    cb = nodes.new('CompositorNodeColorBalance')
    cb.location = (500, 0)
    cb.correction_method = 'LIFT_GAMMA_GAIN'

    if time_of_day in ["golden_hour", "sunset", "dawn"]:
        cb.gain = (1.05, 0.95, 0.85)  # Warm highlights
        cb.lift = (0.95, 0.95, 1.0)   # Cool shadows
    elif time_of_day == "night":
        cb.gain = (0.85, 0.9, 1.1)    # Cool highlights
        cb.lift = (0.9, 0.85, 1.0)    # Slight purple shadows
    else:
        cb.gain = (1.0, 1.0, 1.0)

    # Chain: Render -> Glare -> Color Balance -> (optional Vignette) -> Composite/Viewer
    chain_end = cb

    # Optional recipe-driven vignette via ellipse mask multiplied onto image.
    if recipe_vignette_enabled:
        try:
            mask = nodes.new('CompositorNodeEllipseMask')
            mask.x = 0.5
            mask.y = 0.5
            mask.width = 0.82
            mask.height = 0.82
            mask.location = (500, -300)

            blur = nodes.new('CompositorNodeBlur')
            blur.size_x = 200
            blur.size_y = 200
            blur.use_relative = False
            blur.filter_type = 'FAST_GAUSS'
            blur.location = (700, -300)
            links.new(mask.outputs['Mask'], blur.inputs['Image'])

            vignette_mix = nodes.new('CompositorNodeMixRGB')
            vignette_mix.blend_type = 'MULTIPLY'
            vignette_mix.inputs['Fac'].default_value = 0.35
            vignette_mix.location = (700, 0)
            links.new(cb.outputs['Image'], vignette_mix.inputs[1])
            links.new(blur.outputs['Image'], vignette_mix.inputs[2])
            chain_end = vignette_mix
        except Exception as _ve:
            print(f"[WORLD] Vignette setup skipped: {_ve}")

    composite = nodes.new('CompositorNodeComposite')
    composite.location = (950, 0)

    # Also output to viewer for preview
    viewer = nodes.new('CompositorNodeViewer')
    viewer.location = (950, -200)

    # Link: Render -> Glare -> Color Balance -> [Vignette?] -> Composite
    links.new(rl.outputs['Image'], glare.inputs['Image'])
    links.new(glare.outputs['Image'], cb.inputs['Image'])
    links.new(chain_end.outputs['Image'], composite.inputs['Image'])
    links.new(chain_end.outputs['Image'], viewer.inputs['Image'])

    print(
        f"[WORLD] Compositor: bloom + color grade ({time_of_day})"
        f"{' + vignette' if recipe_vignette_enabled else ''}"
    )


def adjust_camera_framing(manifest, hero_objects):
    """
    Final camera adjustment after all scene elements are placed.
    Ensures the FULL hero is visible with comfortable padding.

    Two operations:
      1) Pull the camera BACK along its current viewing direction if it's
         too close to comfortably fit the hero bounding box at the current
         FOV. Never pushes the camera in.
      2) Pick a sensible focal length per template family if the current
         lens is at an extreme value (likely a default).
    """
    camera = bpy.context.scene.camera
    if not camera:
        print("[CAMERA] No active camera — skipping framing adjust")
        return
    if not hero_objects:
        print("[CAMERA] No hero objects — skipping framing adjust")
        return

    # Gather every world-space corner of every hero bounding box.
    all_coords = []
    for obj in hero_objects:
        if not hasattr(obj, "bound_box") or obj.data is None:
            continue
        for corner in obj.bound_box:
            world_coord = obj.matrix_world @ Vector(corner)
            all_coords.append(world_coord)

    if not all_coords:
        print("[CAMERA] Hero objects had no usable bounds — skipping framing adjust")
        return

    min_x = min(c.x for c in all_coords)
    max_x = max(c.x for c in all_coords)
    min_y = min(c.y for c in all_coords)
    max_y = max(c.y for c in all_coords)
    min_z = min(c.z for c in all_coords)
    max_z = max(c.z for c in all_coords)

    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    max_dim = max(width, depth, height, 0.5)

    center = Vector((
        (min_x + max_x) / 2,
        (min_y + max_y) / 2,
        (min_z + max_z) / 2,
    ))

    # Required distance from camera FOV to fit hero with 40% padding.
    fov = camera.data.angle  # radians
    required_distance = (max_dim * 1.4) / (2 * math.tan(fov / 2))
    required_distance = max(required_distance, max_dim * 2.5)

    current_distance = (camera.location - center).length

    if current_distance < required_distance:
        # Move camera back along its current viewing direction
        direction_vec = camera.location - center
        if direction_vec.length < 1e-4:
            # Camera sitting on top of the hero — pick a default direction.
            direction_vec = Vector((0.0, -1.0, 0.3))
        direction = direction_vec.normalized()
        camera.location = center + direction * required_distance

        # Re-aim at the hero center.
        aim_direction = center - camera.location
        if aim_direction.length > 1e-4:
            camera.rotation_euler = aim_direction.to_track_quat('-Z', 'Y').to_euler()

        print(
            f"[CAMERA] Pulled back: {current_distance:.1f} -> {required_distance:.1f} "
            f"(hero size: {max_dim:.1f})"
        )
    else:
        print(
            f"[CAMERA] Distance OK: {current_distance:.1f} >= {required_distance:.1f}"
        )

    # Family-aware focal length only if the current lens looks like a default
    # / extreme value. Don't override a lens the template explicitly set.
    family = (manifest.get("template_name") or "").lower()
    lens_map = {
        "car_hero":         35,   # Wide automotive feel
        "street_scene":     40,   # Slightly wide for environment context
        "scenic_landscape": 28,   # Wide for landscapes
        "ocean_scene":      35,   # Medium-wide underwater
        "character_stage":  50,   # Portrait-style
        "product_scene":    65,   # Tighter product focus
        "product_pedestal": 65,
    }
    ideal_lens = lens_map.get(family, 40)

    if camera.data.lens < 20 or camera.data.lens > 100:
        camera.data.lens = ideal_lens
        print(f"[CAMERA] Lens adjusted to {ideal_lens}mm for {family or 'default'}")


def get_hero_center(hero_objects):
    """Get the center position of hero objects."""
    if not hero_objects:
        return (0, 0, 1)

    positions = []
    for obj in hero_objects:
        if hasattr(obj, 'location'):
            positions.append(obj.location.copy())

    if not positions:
        return (0, 0, 1)

    avg_x = sum(p.x for p in positions) / len(positions)
    avg_y = sum(p.y for p in positions) / len(positions)
    avg_z = sum(p.z for p in positions) / len(positions)
    return (avg_x, avg_y, max(avg_z, 0.5))
