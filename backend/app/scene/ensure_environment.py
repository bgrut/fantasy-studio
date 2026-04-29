from __future__ import annotations

"""
ensure_environment.py
=====================
Round 12 SAFETY NET — guarantees every render has sky + ground + lights +
atmosphere even when the template forgot to set them up.

Runs AFTER ``build_environment_layers`` in ``render_from_manifest.py``.
The Round 9/10 environment helpers do most of the real work; this module
exists for the residual cases where they didn't (or when a template runs
its own environment path that skips them).

Contract
--------
- NEVER removes existing scene objects.
- Each helper is opt-in: the orchestrator inspects the scene first and
  only acts when the relevant element is missing.
- Failure of any individual helper is logged and tolerated — the render
  must still run.

Public API
----------
- ``ensure_environment(bpy, scene, manifest, hero_objects=None)`` →ï¸ dict
  Returns a small report describing which gap-fills fired.
"""

from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HDRI_DIR = _PROJECT_ROOT / "assets" / "hdri"


# ═══════════════════════════════════════════════════════════════════════════
# Detection helpers
# ═══════════════════════════════════════════════════════════════════════════

def _world_has_sky(bpy) -> bool:
    """True when the world has a meaningful sky shader (not flat gray)."""
    world = bpy.context.scene.world
    if not world:
        return False
    if not world.use_nodes or not world.node_tree:
        return False

    for node in world.node_tree.nodes:
        # Real environment texture or procedural sky always counts.
        if node.bl_idname in ("ShaderNodeTexEnvironment", "ShaderNodeTexSky"):
            if node.bl_idname == "ShaderNodeTexEnvironment":
                # Only counts when an image is actually loaded.
                if getattr(node, "image", None) is not None:
                    return True
            else:
                return True

    # Plain Background node with non-default color/strength counts too.
    bg = world.node_tree.nodes.get("Background")
    if bg:
        try:
            color = bg.inputs[0].default_value
            strength = bg.inputs[1].default_value
            r, g, b = color[0], color[1], color[2]
            # Default Blender world is (0.05, 0.05, 0.05). Anything brighter
            # or any non-grayscale tint counts as intentional sky.
            if max(r, g, b) > 0.08:
                return True
            if abs(r - g) > 0.02 or abs(g - b) > 0.02:
                return True
            if strength > 1.1:
                return True
        except Exception:
            pass
    return False


def _scene_has_ground(bpy) -> bool:
    """True when there is a ground-like mesh near z=0.

    Checks ``is_ground`` custom property first (set by templates), then
    falls back to name heuristic + dimension check.
    """
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        # Fast path: template explicitly tagged the object
        try:
            if obj.get("is_ground"):
                return True
        except Exception:
            pass
        lname = obj.name.lower()
        if any(tok in lname for tok in ("ground", "floor", "plane", "terrain", "road", "street")):
            return True
        try:
            dx, dy, dz = obj.dimensions
        except Exception:
            continue
        if dx > 10 and dy > 10 and abs(obj.location.z) < 1.5:
            return True
    return False


def _scene_has_lights(bpy) -> bool:
    return any(o.type == "LIGHT" for o in bpy.data.objects)


def _scene_has_atmosphere(bpy) -> bool:
    for obj in bpy.data.objects:
        lname = obj.name.lower()
        if any(tok in lname for tok in ("atmosphere", "fog", "haze", "volume")):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Sky
# ═══════════════════════════════════════════════════════════════════════════

_TIME_KEYWORDS: dict[str, list[str]] = {
    "dawn":         ["dawn", "sunrise", "morning", "early"],
    "morning":      ["morning", "bright", "clear", "blue"],
    "midday":       ["midday", "noon", "blue", "clear", "sunny", "bright", "day"],
    "afternoon":    ["afternoon", "day", "sunny", "blue"],
    "golden_hour":  ["golden", "sunset", "warm", "evening", "golden_hour"],
    "sunset":       ["sunset", "dusk", "orange", "warm", "evening"],
    "dusk":         ["dusk", "twilight", "evening", "blue_hour"],
    "night":        ["night", "dark", "stars", "city_night", "moon"],
}

_SKY_COLORS: dict[str, tuple[float, float, float, float]] = {
    "dawn":        (0.80, 0.60, 0.50, 1.0),
    "morning":     (0.50, 0.65, 0.85, 1.0),
    "midday":      (0.40, 0.55, 0.80, 1.0),
    "afternoon":   (0.45, 0.60, 0.82, 1.0),
    "golden_hour": (0.90, 0.70, 0.40, 1.0),
    "sunset":      (0.90, 0.50, 0.30, 1.0),
    "dusk":        (0.30, 0.30, 0.50, 1.0),
    "night":       (0.05, 0.05, 0.15, 1.0),
}


def _pick_best_hdri(hdri_files: list[Path], time_of_day: str) -> Path | None:
    if not hdri_files:
        return None
    keywords = _TIME_KEYWORDS.get(time_of_day, ["day", "blue", "clear"])
    scored: list[tuple[int, Path]] = []
    for f in hdri_files:
        name = f.stem.lower()
        score = sum(1 for kw in keywords if kw in name)
        scored.append((score, f))
    scored.sort(key=lambda pair: (-pair[0], pair[1].name.lower()))
    return scored[0][1]


def _load_hdri_world(bpy, hdri_path: str, strength: float = 1.0) -> bool:
    """Replace the world shader with HDRI → Background → Output."""
    try:
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world

        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links

        for n in list(nodes):
            nodes.remove(n)

        tex = nodes.new("ShaderNodeTexEnvironment")
        bg = nodes.new("ShaderNodeBackground")
        out = nodes.new("ShaderNodeOutputWorld")

        try:
            img = bpy.data.images.load(hdri_path, check_existing=True)
            tex.image = img
        except Exception as e:
            print(f"[ENV_SAFETY] HDRI image load failed ({hdri_path}): {e}", flush=True)
            return False

        bg.inputs[1].default_value = strength
        links.new(tex.outputs[0], bg.inputs[0])
        links.new(bg.outputs[0], out.inputs[0])
        print(f"[ENV_SAFETY] loaded HDRI: {hdri_path}", flush=True)
        return True
    except Exception as e:
        print(f"[ENV_SAFETY] _load_hdri_world failed: {e}", flush=True)
        return False


def _create_procedural_sky(bpy, manifest: dict) -> bool:
    """Solid-color world keyed to time_of_day. Last-ditch fallback."""
    try:
        time = (
            (manifest.get("scene_plan") or {}).get("time_of_day")
            or (manifest.get("_scene_plan") or {}).get("time_of_day")
            or "midday"
        )
        color = _SKY_COLORS.get(str(time), _SKY_COLORS["midday"])

        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        world.use_nodes = True

        nodes = world.node_tree.nodes
        bg = nodes.get("Background")
        if not bg:
            bg = nodes.new("ShaderNodeBackground")
        bg.inputs[0].default_value = color
        bg.inputs[1].default_value = 1.5

        out = nodes.get("World Output")
        if not out:
            out = nodes.new("ShaderNodeOutputWorld")
        if not bg.outputs[0].is_linked:
            world.node_tree.links.new(bg.outputs[0], out.inputs[0])

        print(f"[ENV_SAFETY] procedural sky for {time}: {color[:3]}", flush=True)
        return True
    except Exception as e:
        print(f"[ENV_SAFETY] procedural sky failed: {e}", flush=True)
        return False


def _ensure_sky(bpy, manifest: dict) -> str:
    """Returns 'present' / 'hdri' / 'procedural' / 'failed'."""
    if _world_has_sky(bpy):
        return "present"

    print("[ENV_SAFETY] no sky detected — searching for HDRI", flush=True)

    # 1. Manifest-provided HDRI path (set by env recipe / fetcher).
    hdri_path: str | None = None
    candidate = manifest.get("environment_hdri_path")
    if candidate and Path(candidate).exists():
        hdri_path = str(candidate)

    # 2. resolved_assets HDRIs (already fetched by asset pipeline).
    if not hdri_path:
        resolved = manifest.get("resolved_assets") or {}
        for h in resolved.get("hdris") or []:
            p = h.get("path") if isinstance(h, dict) else None
            if p and Path(p).exists():
                hdri_path = str(p)
                break

    # 3. Local HDRI folder scan.
    if not hdri_path and _HDRI_DIR.exists():
        files = list(_HDRI_DIR.glob("*.hdr")) + list(_HDRI_DIR.glob("*.exr"))
        time = (
            (manifest.get("scene_plan") or {}).get("time_of_day")
            or (manifest.get("_scene_plan") or {}).get("time_of_day")
            or "midday"
        )
        best = _pick_best_hdri(files, str(time))
        if best:
            hdri_path = str(best)
            print(f"[ENV_SAFETY] local HDRI matched ({time}): {best.name}", flush=True)

    if hdri_path and _load_hdri_world(bpy, hdri_path):
        return "hdri"

    # 4. Procedural fallback.
    if _create_procedural_sky(bpy, manifest):
        return "procedural"
    return "failed"


# ═══════════════════════════════════════════════════════════════════════════
# Ground
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_ground(bpy, manifest: dict) -> bool:
    if _scene_has_ground(bpy):
        return False
    try:
        ground_type = str(manifest.get("environment_ground_type") or "terrain_ground")
        bpy.ops.mesh.primitive_plane_add(size=200, location=(0.0, 0.0, 0.0))
        ground = bpy.context.active_object
        if ground is None:
            return False
        ground.name = "Environment_Ground"
        ground["is_ground"] = True

        # Try recipe-driven PBR ground, then environment_ops, then flat fallback.
        _mat_applied = False
        try:
            from .materials import make_ground_material_from_recipe
            _recipe = manifest.get("scene_recipe") or {}
            _recipe_ground = (_recipe.get("ground") or {}).get("type", ground_type)
            mat = make_ground_material_from_recipe(bpy, _recipe_ground)
            ground.data.materials.append(mat)
            _mat_applied = True
            print(f"[ENV_SAFETY] PBR ground material: {_recipe_ground}", flush=True)
        except Exception as e:
            print(f"[ENV_SAFETY] PBR ground material failed ({e})", flush=True)

        if not _mat_applied:
            try:
                from .environment_ops import apply_ground_material
                scene = bpy.context.scene
                apply_ground_material(bpy, scene, ground_type)
                _mat_applied = True
            except Exception as e:
                print(f"[ENV_SAFETY] environment_ops ground failed ({e})", flush=True)

        if not _mat_applied:
            mat = bpy.data.materials.new("Environment_Ground_Mat")
            mat.use_nodes = True
            principled = mat.node_tree.nodes.get("Principled BSDF")
            if principled:
                principled.inputs["Base Color"].default_value = (0.18, 0.20, 0.18, 1.0)
                principled.inputs["Roughness"].default_value = 0.85
            ground.data.materials.append(mat)

        print(f"[ENV_SAFETY] added safety ground plane (type={ground_type})", flush=True)
        return True
    except Exception as e:
        print(f"[ENV_SAFETY] ground plane creation failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Lighting
# ═══════════════════════════════════════════════════════════════════════════

def _hero_center(hero_objects) -> tuple[float, float, float]:
    if not hero_objects:
        return (0.0, 0.0, 1.0)
    xs, ys, zs = [], [], []
    for obj in hero_objects:
        try:
            xs.append(obj.location.x)
            ys.append(obj.location.y)
            zs.append(obj.location.z)
        except Exception:
            continue
    if not xs:
        return (0.0, 0.0, 1.0)
    return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))


def _ensure_lights(bpy, manifest: dict, hero_objects=None) -> int:
    if _scene_has_lights(bpy):
        return 0
    try:
        from mathutils import Vector
    except Exception as e:
        print(f"[ENV_SAFETY] mathutils unavailable for lighting: {e}", flush=True)
        return 0

    cx, cy, cz = _hero_center(hero_objects)
    sp = manifest.get("scene_plan") or manifest.get("_scene_plan") or {}
    time = str(sp.get("time_of_day") or "midday")

    is_warm = time in ("golden_hour", "sunset", "dawn")
    is_night = time in ("night", "dusk")

    key_energy = 100 if is_night else 300
    key_color = (
        (1.0, 0.85, 0.65) if is_warm
        else (0.4, 0.45, 0.6) if is_night
        else (1.0, 0.98, 0.95)
    )
    fill_color = (0.8, 0.85, 1.0)

    placements = [
        ("Key_Light",  (cx + 5.0, cy - 5.0, cz + 6.0), key_energy,        3.0, key_color),
        ("Fill_Light", (cx - 4.0, cy - 3.0, cz + 3.0), key_energy * 0.3,  5.0, fill_color),
        ("Rim_Light",  (cx + 2.0, cy + 6.0, cz + 4.0), key_energy * 0.6,  2.0, key_color),
    ]
    added = 0
    for name, loc, energy, size, color in placements:
        try:
            bpy.ops.object.light_add(type="AREA", location=loc)
            light = bpy.context.active_object
            light.name = name
            light.data.energy = energy
            light.data.size = size
            light.data.color = color
            target = Vector((cx, cy, cz)) - light.location
            light.rotation_euler = target.to_track_quat("-Z", "Y").to_euler()
            added += 1
        except Exception as e:
            print(f"[ENV_SAFETY] {name} placement failed: {e}", flush=True)

    if added:
        print(
            f"[ENV_SAFETY] 3-point lighting added ({added} lights, time={time})",
            flush=True,
        )
    return added


# ═══════════════════════════════════════════════════════════════════════════
# Atmosphere
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_atmosphere(bpy, manifest: dict) -> bool:
    if _scene_has_atmosphere(bpy):
        return False
    try:
        bpy.ops.mesh.primitive_cube_add(size=100, location=(0.0, 0.0, 25.0))
        vol = bpy.context.active_object
        if vol is None:
            return False
        vol.name = "Atmosphere_Volume"
        vol.display_type = "WIRE"
        try:
            vol.hide_select = True
        except Exception:
            pass

        mat = bpy.data.materials.new("Atmosphere_Volume_Mat")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        for n in list(nodes):
            nodes.remove(n)
        out = nodes.new("ShaderNodeOutputMaterial")
        scatter = nodes.new("ShaderNodeVolumeScatter")
        scatter.inputs["Density"].default_value = 0.003
        scatter.inputs["Color"].default_value = (0.85, 0.88, 0.95, 1.0)
        links.new(scatter.outputs["Volume"], out.inputs["Volume"])
        vol.data.materials.append(mat)

        print("[ENV_SAFETY] subtle atmosphere volume added", flush=True)
        return True
    except Exception as e:
        print(f"[ENV_SAFETY] atmosphere creation failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def ensure_environment(bpy, scene, manifest: dict, hero_objects=None) -> dict[str, Any]:
    """
    Mandatory environment safety net. Inspects the scene; only fills gaps.
    Returns a small report so render_from_manifest can log it.
    """
    report: dict[str, Any] = {
        "sky":        "skipped",
        "ground":     False,
        "lights":     0,
        "atmosphere": False,
    }
    try:
        report["sky"] = _ensure_sky(bpy, manifest)
    except Exception as e:
        print(f"[ENV_SAFETY] sky stage exception: {e}", flush=True)
    try:
        report["ground"] = _ensure_ground(bpy, manifest)
    except Exception as e:
        print(f"[ENV_SAFETY] ground stage exception: {e}", flush=True)
    try:
        report["lights"] = _ensure_lights(bpy, manifest, hero_objects=hero_objects)
    except Exception as e:
        print(f"[ENV_SAFETY] lights stage exception: {e}", flush=True)
    try:
        report["atmosphere"] = _ensure_atmosphere(bpy, manifest)
    except Exception as e:
        print(f"[ENV_SAFETY] atmosphere stage exception: {e}", flush=True)

    print(
        f"[ENV_SAFETY] report: sky={report['sky']} ground={report['ground']} "
        f"lights+={report['lights']} atmos={report['atmosphere']}",
        flush=True,
    )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# Director controls
# ═══════════════════════════════════════════════════════════════════════════

def apply_directorial_controls(bpy, scene, manifest: dict) -> dict[str, Any]:
    """
    Project the user's directorial control choices onto the scene. The
    director projection layer in asset_agent.py already filled
    manifest['directorial_controls']; this function makes sure the values
    actually move pixels at render time.

    What this does today:
      - mood   -> stamped into scene_plan.mood (templates already react to it)
      - energy -> stamped into manifest['energy_level']
      - lighting_preset -> tweaks key/fill/rim energies if those lights exist
      - camera_style -> stamped into manifest['camera_style']
    """
    report: dict[str, Any] = {"applied": []}
    controls = manifest.get("directorial_controls") or {}
    if not isinstance(controls, dict) or not controls:
        return report

    try:
        camera_style = controls.get("camera_style")
        if camera_style:
            manifest["camera_style"] = camera_style
            report["applied"].append(f"camera_style={camera_style}")

        mood = controls.get("mood")
        if mood:
            sp = manifest.setdefault("scene_plan", {})
            if isinstance(sp, dict):
                sp["mood"] = mood
            report["applied"].append(f"mood={mood}")

        energy = controls.get("energy_level")
        if energy:
            manifest["energy_level"] = energy
            report["applied"].append(f"energy_level={energy}")

        preset = controls.get("lighting_preset")
        if preset:
            multiplier = {
                "low_key":     0.5,
                "moody":       0.6,
                "natural":     1.0,
                "high_key":    1.6,
                "dramatic":    1.3,
                "soft":        0.85,
                "harsh":       1.4,
            }.get(str(preset).lower(), 1.0)
            adjusted = 0
            for obj in bpy.data.objects:
                if obj.type != "LIGHT":
                    continue
                lname = obj.name.lower()
                if not any(tag in lname for tag in ("key", "fill", "rim", "sun", "area")):
                    continue
                try:
                    obj.data.energy *= multiplier
                    adjusted += 1
                except Exception:
                    continue
            report["applied"].append(f"lighting_preset={preset}(x{multiplier:.2f},{adjusted} lights)")
    except Exception as e:
        print(f"[DIRECTOR] control application failed: {e}", flush=True)

    if report["applied"]:
        print(f"[DIRECTOR] controls applied: {', '.join(report['applied'])}", flush=True)
    return report


__all__ = ["ensure_environment", "apply_directorial_controls"]
