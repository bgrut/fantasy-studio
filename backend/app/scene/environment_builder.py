"""
Environment preset builder — applies cinematic environments from JSON config.

Called AFTER the base template has set up the scene, BEFORE safety nets.
Reads from ``app/data/environment_presets.json`` and modifies ground
materials, lighting, atmosphere volumes, and optionally adds background
geometry (columns, walls, stadium stands).

The existing templates (car_hero, scenic_landscape, etc.) continue to
work unchanged — this system enriches them with environment-specific
overrides keyed by prompt keywords.
"""

from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
from typing import Any

_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "environment_presets.json"
_presets_cache: dict | None = None


def load_presets() -> dict[str, Any]:
    """Load environment presets from JSON config (cached after first call)."""
    global _presets_cache
    if _presets_cache is not None:
        return _presets_cache
    if not _PRESETS_PATH.exists():
        _presets_cache = {}
        return _presets_cache
    try:
        with open(_PRESETS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _presets_cache = data.get("presets", {})
    except Exception as e:
        print(f"[ENV_PRESET] failed to load presets: {e}", flush=True)
        _presets_cache = {}
    return _presets_cache


def match_preset(
    prompt_text: str,
    environment_text: str = "",
) -> tuple[str | None, dict | None]:
    """Find the best matching preset for the given prompt.

    Returns ``(preset_name, preset_dict)`` or ``(None, None)`` when no
    preset matches.
    """
    presets = load_presets()
    if not presets:
        return None, None

    combined = f"{prompt_text} {environment_text}".lower()
    best_name: str | None = None
    best_score = 0

    for name, preset in presets.items():
        keywords = preset.get("keywords", [])
        score = 0
        for kw in keywords:
            if kw in combined:
                # Base hit + length bonus (longer keywords are more specific)
                score += 2 + len(kw)
        if score > best_score:
            best_score = score
            best_name = name

    if best_name and best_score > 0:
        return best_name, presets[best_name]
    return None, None


def apply_preset(bpy, preset: dict, scene=None) -> None:
    """Apply an environment preset to the current Blender scene.

    Parameters
    ----------
    bpy : module
        The ``bpy`` module (passed explicitly so this file stays
        import-safe outside Blender).
    preset : dict
        A single preset entry from the JSON config.
    scene : optional
        Blender scene to modify. Defaults to ``bpy.context.scene``.
    """
    if scene is None:
        scene = bpy.context.scene

    print("[ENV_PRESET] applying environment preset", flush=True)

    ground_cfg = preset.get("ground", {})
    if ground_cfg:
        _apply_ground_material(bpy, ground_cfg)

    light_cfg = preset.get("lighting", {})
    if light_cfg:
        _apply_lighting(bpy, light_cfg)

    atmo_cfg = preset.get("atmosphere", {})
    if atmo_cfg:
        _apply_atmosphere(bpy, atmo_cfg)

    bg_cfg = preset.get("background_geo", [])
    if bg_cfg:
        _build_background(bpy, bg_cfg)

    print("[ENV_PRESET] complete", flush=True)


# ── Ground material ──────────────────────────────────────────────────────

_GROUND_NAMES = (
    "ScenicGround", "ScenicGroundFallback", "CarHeroGround", "StageFloor",
    "StreetGround", "OceanFloor", "ProductFloor", "StageGroundBase",
    "ProductGroundBase",
)


def _apply_ground_material(bpy, cfg: dict) -> None:
    color = cfg.get("color", [0.5, 0.5, 0.5])
    roughness = cfg.get("roughness", 0.8)

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.name not in _GROUND_NAMES:
            continue
        if not obj.data.materials:
            mat = bpy.data.materials.new(name="EnvGround")
            obj.data.materials.append(mat)
        else:
            mat = obj.data.materials[0]

        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            bsdf.inputs["Roughness"].default_value = roughness
            print(
                f"[ENV_PRESET] ground material on {obj.name}: "
                f"color={color} roughness={roughness}",
                flush=True,
            )
        break  # only override the first match


# ── Lighting rig ─────────────────────────────────────────────────────────

def _apply_lighting(bpy, cfg: dict) -> None:
    key_energy = cfg.get("key_energy", 4.0)
    key_color = tuple(cfg.get("key_color", [1.0, 0.95, 0.9]))

    lights = [o for o in bpy.context.scene.objects if o.type == "LIGHT"]
    if not lights:
        return

    # Sort by energy descending to identify key / fill / rim
    lights_by_energy = sorted(
        lights, key=lambda l: l.data.energy, reverse=True
    )

    if len(lights_by_energy) >= 1:
        key = lights_by_energy[0]
        key.data.energy = key_energy * 1000
        key.data.color = key_color
        print(
            f"[ENV_PRESET] key light: {key.name} energy={key.data.energy:.0f}",
            flush=True,
        )

    if len(lights_by_energy) >= 2 and "fill_energy" in cfg:
        fill = lights_by_energy[1]
        fill.data.energy = cfg["fill_energy"] * 1000
        fill.data.color = tuple(cfg.get("fill_color", [0.8, 0.85, 1.0]))

    if len(lights_by_energy) >= 3 and "rim_energy" in cfg:
        rim = lights_by_energy[2]
        rim.data.energy = cfg["rim_energy"] * 1000
        rim.data.color = tuple(cfg.get("rim_color", [1.0, 0.9, 0.8]))


# ── Atmosphere ───────────────────────────────────────────────────────────

_ATMO_NAMES = (
    "Atmo_Far", "Atmo_Near", "OceanAtmo", "StageAtmo",
    "Atmosphere_Volume", "OceanDeepHaze", "ProductAtmo",
    "ScenicAtmo_Near", "ScenicAtmo_Far",
)


def _apply_atmosphere(bpy, cfg: dict) -> None:
    density = cfg.get("fog_density", 0.003)
    color = cfg.get("fog_color", [0.8, 0.85, 0.9])

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        if obj.name not in _ATMO_NAMES:
            continue
        if not obj.data.materials:
            continue
        mat = obj.data.materials[0]
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type in ("VOLUME_SCATTER", "PRINCIPLED_VOLUME"):
                d_input = node.inputs.get("Density")
                if d_input is not None:
                    d_input.default_value = density
                c_input = node.inputs.get("Color")
                if c_input is not None:
                    c_input.default_value = (*color, 1.0)

    print(
        f"[ENV_PRESET] atmosphere: density={density} color={color}",
        flush=True,
    )


# ── Background geometry ──────────────────────────────────────────────────

def _build_background(bpy, bg_list: list[dict]) -> None:
    for bg in bg_list:
        geo_type = bg.get("type", "")
        count = bg.get("count", 1)
        distance = bg.get("distance", 20)
        h_range = bg.get("height_range", [5, 10])

        if geo_type == "column":
            _build_columns(bpy, count, distance, h_range)
        elif geo_type == "wall":
            _build_walls(bpy, count, distance, h_range)
        elif geo_type == "stadium_stands":
            _build_stadium_stands(bpy, count, distance, h_range)
        # Other types (tree_trunk, crystal, etc.) are visual suggestions;
        # the HDRI + lighting + ground color do the heavy lifting for now.


def _make_simple_mat(bpy, name: str, color: tuple, roughness: float = 0.9):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def _build_columns(bpy, count: int, distance: float, h_range: list) -> None:
    for i in range(count):
        angle = (i / max(count, 1)) * math.pi * 0.6 + math.pi * 0.2
        x = math.cos(angle) * distance
        y = math.sin(angle) * distance
        h = random.uniform(h_range[0], h_range[1]) if len(h_range) >= 2 else 6.0
        r = h * 0.04

        bpy.ops.mesh.primitive_cylinder_add(
            radius=r, depth=h, location=(x, y, h / 2)
        )
        col = bpy.context.active_object
        col.name = f"env_column_{i}"
        mat = _make_simple_mat(bpy, f"ColumnMat_{i}", (0.25, 0.22, 0.20))
        col.data.materials.append(mat)

    print(f"[ENV_PRESET] built {count} columns at distance={distance}", flush=True)


def _build_walls(bpy, count: int, distance: float, h_range: list) -> None:
    for i in range(count):
        angle = (i / max(count, 1)) * math.pi * 0.5 + math.pi * 0.25
        x = math.cos(angle) * distance
        y = math.sin(angle) * distance
        h = h_range[0] if h_range else 3.0
        w = distance * 0.8

        bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, h / 2))
        wall = bpy.context.active_object
        wall.name = f"env_wall_{i}"
        wall.scale = (w, 0.1, h)
        wall.rotation_euler.z = angle + math.pi

        mat = _make_simple_mat(bpy, f"WallMat_{i}", (0.6, 0.58, 0.55), 0.85)
        wall.data.materials.append(mat)

    print(f"[ENV_PRESET] built {count} walls at distance={distance}", flush=True)


def _build_stadium_stands(
    bpy, count: int, distance: float, h_range: list
) -> None:
    for i in range(count):
        angle = (i / max(count, 1)) * math.pi * 2
        x = math.cos(angle) * distance
        y = math.sin(angle) * distance
        h = h_range[1] if len(h_range) >= 2 else 15
        w = distance * 0.4

        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, h / 2))
        stand = bpy.context.active_object
        stand.name = f"env_stand_{i}"
        stand.scale = (w, w * 0.3, h)
        stand.rotation_euler.z = angle + math.pi

        mat = _make_simple_mat(bpy, f"StandMat_{i}", (0.35, 0.33, 0.30), 0.8)
        stand.data.materials.append(mat)

    print(
        f"[ENV_PRESET] built {count} stadium stands at distance={distance}",
        flush=True,
    )
