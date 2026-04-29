from __future__ import annotations

"""
scene_optimizer.py
==================
Post-build scene optimization agent.

Called AFTER a builder constructs the scene, BEFORE rendering begins.
Acts like a senior 3D artist reviewing the scene: removes waste, enforces
light budgets, controls volumetric cost, and verifies grounding.

CRITICAL DESIGN PRINCIPLE:
  The optimizer is CONSERVATIVE.  It only removes objects that are provably
  waste (truly tiny junk meshes, fully hidden objects).  It NEVER removes:
    - the largest meshes (hero subjects, environment anchors)
    - meshes above a safe volume threshold
    - scene infrastructure (grounds, coves, contact shadows, etc.)
    - the camera or its target

  "When in doubt, keep it."

Usage (in render_from_manifest.py):
    from app.scene.scene_optimizer import optimize_scene
    stats = optimize_scene(bpy, scene, quality_tier, scene_plan)
"""

from .layout_ops import bounds_world, _get_depsgraph

# ═══════════════════════════════════════════════════════════════════════════
# Tier-specific budgets -- CONSERVATIVE values
# ═══════════════════════════════════════════════════════════════════════════

_TIER_BUDGETS = {
    "fast": {
        "max_lights": 4,
        "volumetrics_enabled": True,
        "volumetric_density_cap": 0.006,
        "max_material_nodes": 30,
        "mesh_min_volume": 0.0001,
        "decimate_threshold_faces": 100_000,
        "decimate_ratio": 0.6,
        # Protect the top N largest meshes by volume -- NEVER remove these
        "protect_top_n_meshes": 15,
    },
    "standard": {
        "max_lights": 5,
        "volumetrics_enabled": True,
        "volumetric_density_cap": 0.015,
        "max_material_nodes": 60,
        "mesh_min_volume": 0.00005,
        "decimate_threshold_faces": 300_000,
        "decimate_ratio": 0.75,
        "protect_top_n_meshes": 20,
    },
    "ultra": {
        "max_lights": 8,
        "volumetrics_enabled": True,
        "volumetric_density_cap": 0.025,
        "max_material_nodes": 100,
        "mesh_min_volume": 0.00001,
        "decimate_threshold_faces": 500_000,
        "decimate_ratio": 0.85,
        "protect_top_n_meshes": 30,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Protected object detection
# ═══════════════════════════════════════════════════════════════════════════

# Any object whose name starts with one of these is NEVER removed.
# This covers all scene infrastructure created by builders and presets.
_PROTECTED_PREFIXES = (
    # Ground planes, floors, roads
    "Ground", "Floor", "Road", "Terrain",
    # Studio infrastructure
    "Stage", "Product", "Pedestal", "Backdrop", "Sweep", "BackWall", "Cyc",
    # Atmosphere and fog
    "Atmo", "Atmosphere", "Fog", "Haze", "Ocean",
    # Contact shadows and grounding
    "Contact", "Shadow",
    # Foreground elements
    "FG", "Foreground",
    # Terrain features
    "Hillock", "Ridge", "Curb", "Sidewalk",
    # Scene-specific prefixes from builders
    "Scenic", "CarHero", "Street", "Character", "Whale",
    # Camera targets
    "Camera", "Target",
    # Urban / building infrastructure (Cat City Fix)
    "Building", "City", "Skyline", "Tower", "Facade",
    "Window", "Wall", "Roof", "Door",
)

# Families where imported meshes should receive extra protection.
# For these families the optimizer uses a more relaxed decimate ratio
# and protects ALL imported meshes above a tiny threshold.
_URBAN_FAMILIES = {"street_scene", "city_scene", "city_loop"}


def _build_protected_set(bpy, scene, budget: dict, scene_plan: dict | None = None) -> set:
    """
    Build the set of object names that must NEVER be removed.

    Protection sources:
    1. Name-based: objects matching _PROTECTED_PREFIXES
    2. Volume-based: the top N largest meshes (hero subjects + environment)
    3. Camera: the active camera and its constraint targets
    4. Lights: all lights (lighting optimization handles these separately)
    """
    protected = set()

    # 1. Name-based protection
    for obj in bpy.data.objects:
        if any(obj.name.startswith(p) for p in _PROTECTED_PREFIXES):
            protected.add(obj.name)

    # 2. Volume-based protection: keep the largest meshes
    # These are ALWAYS the hero subjects and environment anchors
    mesh_volumes = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            from mathutils import Vector
            corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            xs = [c.x for c in corners]
            ys = [c.y for c in corners]
            zs = [c.z for c in corners]
            vol = (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs))
            mesh_volumes.append((obj.name, vol))
        except Exception:
            # Can't measure = can't prove it's junk = keep it
            protected.add(obj.name)

    # Sort by volume descending, protect the top N
    mesh_volumes.sort(key=lambda x: x[1], reverse=True)
    top_n = budget.get("protect_top_n_meshes", 15)
    for name, vol in mesh_volumes[:top_n]:
        protected.add(name)

    # 3. Camera protection
    if scene.camera:
        protected.add(scene.camera.name)
        for c in scene.camera.constraints:
            if hasattr(c, "target") and c.target:
                protected.add(c.target.name)

    # 4. Light protection (handled by _optimize_lighting, not geometry pass)
    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            protected.add(obj.name)

    # 5. Empty objects used as constraint targets
    for obj in bpy.data.objects:
        if obj.type == "EMPTY":
            protected.add(obj.name)

    # 6. Hero protection: ALL objects with is_hero=True custom property
    #    Hero meshes can be tiny (legs, tail, ears of a small animal) but
    #    must NEVER be removed — they're parts of the main subject.
    _hero_count = 0
    for obj in bpy.data.objects:
        if obj.get("is_hero"):
            protected.add(obj.name)
            _hero_count += 1
    if _hero_count:
        print(f"[OPTIMIZER] hero-protected {_hero_count} is_hero objects", flush=True)

    # 7. Urban family extra protection: protect ALL meshes above a tiny threshold
    #    This prevents building/city sub-meshes from being removed or over-decimated.
    family = (scene_plan or {}).get("scene_family", "")
    if family in _URBAN_FAMILIES:
        for name, vol in mesh_volumes:
            if vol > 0.001:  # anything bigger than a pebble
                protected.add(name)
        print(f"[OPTIMIZER] urban family detected — extra mesh protection applied", flush=True)

    return protected


# ═══════════════════════════════════════════════════════════════════════════
# A. Geometry Optimization (CONSERVATIVE)
# ═══════════════════════════════════════════════════════════════════════════

def _optimize_geometry(bpy, scene, budget: dict, protected: set, scene_plan: dict | None = None) -> dict:
    """
    Remove only truly tiny junk meshes and hidden objects.
    NEVER removes protected objects.
    """
    stats = {"meshes_removed": 0, "meshes_decimated": 0, "meshes_protected": 0,
             "faces_before": 0, "faces_after": 0}
    min_vol = budget["mesh_min_volume"]
    decimate_threshold = budget["decimate_threshold_faces"]
    decimate_ratio = budget["decimate_ratio"]

    all_meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    stats["meshes_protected"] = sum(1 for obj in all_meshes if obj.name in protected)

    # Only remove meshes that are:
    # - NOT protected
    # - below the (very small) volume threshold
    to_remove = []
    for obj in all_meshes:
        if obj.name in protected:
            continue
        # NEVER remove hero meshes — they're parts of the main subject
        if obj.get("is_hero"):
            continue

        try:
            from mathutils import Vector
            corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            xs = [c.x for c in corners]
            ys = [c.y for c in corners]
            zs = [c.z for c in corners]
            vol = (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs))

            if vol < min_vol:
                to_remove.append((obj, vol))
        except Exception:
            pass

    for obj, vol in to_remove:
        print(f"[OPTIMIZER] removing junk mesh: {obj.name} (vol={vol:.6f})", flush=True)
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
            stats["meshes_removed"] += 1
        except Exception:
            pass

    # Remove hidden/non-renderable meshes (but NOT protected or hero ones)
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if obj.name in protected:
            continue
        if obj.get("is_hero"):
            continue
        if obj.hide_render:
            print(f"[OPTIMIZER] removing hidden mesh: {obj.name}", flush=True)
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                stats["meshes_removed"] += 1
            except Exception:
                pass

    # Decimate overly dense meshes (non-destructive, skip protected)
    remaining_meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    for obj in remaining_meshes:
        try:
            if obj.data and hasattr(obj.data, "polygons"):
                face_count = len(obj.data.polygons)
                stats["faces_before"] += face_count
                if face_count > decimate_threshold and obj.name not in protected:
                    # Urban scenes: use relaxed decimate ratio to preserve skyline detail
                    family = (scene_plan or {}).get("scene_family", "")
                    ratio = max(decimate_ratio, 0.85) if family in _URBAN_FAMILIES else decimate_ratio
                    mod = obj.modifiers.new(name="OptDecimate", type="DECIMATE")
                    mod.ratio = ratio
                    mod.use_symmetry = False
                    stats["meshes_decimated"] += 1
                    stats["faces_after"] += int(face_count * decimate_ratio)
                else:
                    stats["faces_after"] += face_count
        except Exception:
            pass

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# B. Lighting Optimization (CONSERVATIVE)
# ═══════════════════════════════════════════════════════════════════════════

def _optimize_lighting(bpy, budget: dict) -> dict:
    """
    Enforce max light count per tier.
    Keeps the strongest lights. Never reduces below 3.
    """
    stats = {"lights_before": 0, "lights_after": 0, "lights_removed": 0}
    max_lights = max(budget["max_lights"], 3)  # never fewer than 3

    all_lights = [obj for obj in bpy.data.objects if obj.type == "LIGHT"]
    stats["lights_before"] = len(all_lights)

    if len(all_lights) <= max_lights:
        stats["lights_after"] = len(all_lights)
        return stats

    # Sort by energy (descending) -- keep the strongest lights
    def light_energy(obj):
        try:
            return obj.data.energy
        except Exception:
            return 0

    all_lights.sort(key=light_energy, reverse=True)

    to_remove = all_lights[max_lights:]

    for obj in to_remove:
        print(f"[OPTIMIZER] removing light: {obj.name} (energy={light_energy(obj):.0f})", flush=True)
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
            stats["lights_removed"] += 1
        except Exception:
            pass

    stats["lights_after"] = len(all_lights) - stats["lights_removed"]
    return stats


# ═══════════════════════════════════════════════════════════════════════════
# C. Volumetric Optimization (CONSERVATIVE — reduce, never remove)
# ═══════════════════════════════════════════════════════════════════════════

def _optimize_volumetrics(bpy, scene, budget: dict) -> dict:
    """
    Control volumetric cost by reducing density.
    NEVER removes volumetric objects — they provide essential atmosphere.
    Even FAST tier keeps volumetrics at reduced density.
    """
    stats = {"volumetrics_capped": 0, "volumetrics_total": 0}

    vol_objects = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        for slot in (obj.material_slots or []):
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == "VOLUME_PRINCIPLED" or node.bl_idname == "ShaderNodeVolumePrincipled":
                    vol_objects.append((obj, node))
                    break

    stats["volumetrics_total"] = len(vol_objects)
    density_cap = budget.get("volumetric_density_cap", 0.010)

    for obj, node in vol_objects:
        try:
            current = node.inputs["Density"].default_value
            if current > density_cap:
                node.inputs["Density"].default_value = density_cap
                stats["volumetrics_capped"] += 1
                print(
                    f"[OPTIMIZER] capped volumetric density: {obj.name} "
                    f"{current:.4f} -> {density_cap:.4f}",
                    flush=True,
                )
        except Exception:
            pass

    # Control volumetric step rate in Cycles (cheaper sampling)
    if hasattr(scene, "cycles"):
        if density_cap <= 0.006:
            # FAST: very coarse volumetric stepping
            scene.cycles.volume_step_rate = 8.0
            scene.cycles.volume_max_steps = 64
        elif density_cap <= 0.015:
            # STANDARD
            scene.cycles.volume_step_rate = 4.0
            scene.cycles.volume_max_steps = 128
        else:
            # ULTRA
            scene.cycles.volume_step_rate = 2.0
            scene.cycles.volume_max_steps = 256

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# D. Material Simplification (CONSERVATIVE — only extreme cases)
# ═══════════════════════════════════════════════════════════════════════════

def _optimize_materials(bpy, budget: dict) -> dict:
    """
    Only simplify materials that are extremely complex (100+ nodes).
    Never touch materials with fewer nodes than the tier threshold.
    Never remove noise/procedural nodes used for roughness variation.
    """
    stats = {"materials_simplified": 0, "materials_total": 0}
    max_nodes = budget["max_material_nodes"]

    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        stats["materials_total"] += 1
        node_count = len(mat.node_tree.nodes)

        # Only touch truly extreme materials (2x the threshold)
        if node_count > max_nodes * 2:
            try:
                nodes = mat.node_tree.nodes

                # Only remove nodes that are:
                # - decorative texture generators
                # - NOT connected to anything essential
                safe_to_remove = {
                    "ShaderNodeTexWave", "ShaderNodeTexMusgrave",
                    "ShaderNodeTexBrick", "ShaderNodeTexChecker",
                }
                # NEVER remove ShaderNodeTexNoise — used for roughness variation
                # NEVER remove ShaderNodeTexVoronoi — used for material detail

                to_remove = []
                for node in list(nodes):
                    if node.bl_idname not in safe_to_remove:
                        continue
                    # Only remove if no outputs are connected
                    has_connections = False
                    for output in node.outputs:
                        if output.links:
                            has_connections = True
                            break
                    if not has_connections:
                        to_remove.append(node)

                for node in to_remove:
                    nodes.remove(node)

                if to_remove:
                    stats["materials_simplified"] += 1
                    print(
                        f"[OPTIMIZER] simplified material: {mat.name} "
                        f"(removed {len(to_remove)} unconnected decorative nodes)",
                        flush=True,
                    )
            except Exception:
                pass

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# E. Post-optimization verification
# ═══════════════════════════════════════════════════════════════════════════

def _verify_scene_integrity(bpy, scene) -> dict:
    """
    Verify the scene is still renderable after optimization.
    Log warnings if critical elements are missing.
    """
    stats = {"has_camera": False, "has_lights": False, "has_meshes": False,
             "mesh_count": 0, "light_count": 0, "warnings": []}

    stats["has_camera"] = scene.camera is not None
    if not stats["has_camera"]:
        stats["warnings"].append("NO CAMERA in scene!")

    lights = [obj for obj in bpy.data.objects if obj.type == "LIGHT"]
    stats["light_count"] = len(lights)
    stats["has_lights"] = len(lights) > 0
    if not stats["has_lights"]:
        stats["warnings"].append("NO LIGHTS in scene!")

    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    stats["mesh_count"] = len(meshes)
    stats["has_meshes"] = len(meshes) > 0
    if not stats["has_meshes"]:
        stats["warnings"].append("NO MESHES in scene!")

    # Check camera has valid target
    if scene.camera:
        for c in scene.camera.constraints:
            if hasattr(c, "target"):
                if c.target is None:
                    stats["warnings"].append("Camera TRACK_TO target is None!")
                elif c.target.name not in {obj.name for obj in bpy.data.objects}:
                    stats["warnings"].append(f"Camera target '{c.target.name}' not found!")

    for w in stats["warnings"]:
        print(f"[OPTIMIZER] CRITICAL WARNING: {w}", flush=True)

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

def optimize_scene(
    bpy,
    scene,
    quality_tier: str = "standard",
    scene_plan: dict | None = None,
) -> dict:
    """
    Run all optimization passes on the built scene.
    CONSERVATIVE by design — only removes provable waste.
    """
    tier = quality_tier.lower()
    budget = _TIER_BUDGETS.get(tier, _TIER_BUDGETS["standard"])

    print(f"[OPTIMIZER] Starting scene optimization | tier={tier}", flush=True)

    # Build protected object set FIRST (pass scene_plan for family-aware protection)
    protected = _build_protected_set(bpy, scene, budget, scene_plan)
    print(f"[OPTIMIZER] Protected objects: {len(protected)}", flush=True)

    # Log hero/environment mesh counts before optimization
    mesh_count_before = sum(1 for obj in bpy.data.objects if obj.type == "MESH")
    light_count_before = sum(1 for obj in bpy.data.objects if obj.type == "LIGHT")

    # Run optimization passes
    geom_stats = _optimize_geometry(bpy, scene, budget, protected, scene_plan)
    light_stats = _optimize_lighting(bpy, budget)
    vol_stats = _optimize_volumetrics(bpy, scene, budget)
    mat_stats = _optimize_materials(bpy, budget)

    # Post-optimization verification
    verify_stats = _verify_scene_integrity(bpy, scene)

    # Force scene update
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    mesh_count_after = sum(1 for obj in bpy.data.objects if obj.type == "MESH")

    stats = {
        "tier": tier,
        "geometry": geom_stats,
        "lighting": light_stats,
        "volumetrics": vol_stats,
        "materials": mat_stats,
        "verification": verify_stats,
    }

    print(
        f"[OPTIMIZER] Complete | "
        f"meshes: {mesh_count_before}->{mesh_count_after} "
        f"(removed={geom_stats['meshes_removed']} protected={geom_stats['meshes_protected']}) "
        f"lights: {light_stats['lights_before']}->{light_stats['lights_after']} "
        f"volumetrics: capped={vol_stats['volumetrics_capped']}/{vol_stats['volumetrics_total']} "
        f"materials: simplified={mat_stats['materials_simplified']}/{mat_stats['materials_total']} "
        f"post-check: meshes={verify_stats['mesh_count']} lights={verify_stats['light_count']} "
        f"warnings={len(verify_stats['warnings'])}",
        flush=True,
    )

    return stats
