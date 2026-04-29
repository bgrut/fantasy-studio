from __future__ import annotations

"""
render_from_manifest.py
=======================
Pipeline dispatch hub.  This is the entry point Blender runs via:

    blender --background --python render_from_manifest.py -- <manifest_path>

It reads the manifest JSON, resolves assets if not already resolved,
dispatches to the correct scene template, and renders all frames.

Design principles
-----------------
- Each scene family is routed to its dedicated build_* function.
- If a build function raises an exception it is caught and logged;
  a fallback single-color world is set so the render is never blank gray.
- Manifest is expected to have ``resolved_assets`` already populated
  by the Python caller (blender_runner.py).  If absent, resolve_scene_assets
  is called inline as a safety net.
- Frame range, output path, resolution, and samples are all read from
  the manifest so the caller controls render quality without touching
  this file.
- All six launch-demo families are supported:
    scenic_landscape, car_hero, street_scene, ocean_scene,
    character_stage, product_scene
  Unknown families fall back to character_stage with a warning.
"""

import json
import sys
import traceback
from pathlib import Path


# ---------------------------------------------------------------------------
# Locate project root so relative imports work when invoked via Blender CLI
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]   # project root: two levels above src/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Blender import (guarded so the module can be parsed by static analysers)
# ---------------------------------------------------------------------------

try:
    import bpy  # type: ignore
    _IN_BLENDER = True
except ImportError:
    _IN_BLENDER = False


# ---------------------------------------------------------------------------
# Scene family → builder mapping
# ---------------------------------------------------------------------------

def _import_builders() -> dict:
    """
    Lazy-import all scene template builders.
    Returns a dict of {family_name: build_function}.
    Import errors per-family are caught so a broken template never
    prevents other families from being loaded.
    """
    builders: dict = {}

    _families = [
        ("scenic_landscape", "src.scenic_landscape",   "build_scenic_landscape"),
        ("car_hero",         "src.car_hero",            "build_car_hero"),
        ("street_scene",     "src.street_scene",        "build_street_scene"),
        ("ocean_scene",      "src.ocean_scene",         "build_ocean_scene"),
        ("character_stage",  "src.character_stage",     "build_character_stage"),
        ("product_scene",    "src.product_scene",       "build_product_scene"),
    ]

    for family, module_path, fn_name in _families:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            builders[family] = getattr(mod, fn_name)
            print(f"[DISPATCH] loaded builder: {family}", flush=True)
        except Exception as e:
            print(f"[DISPATCH] WARNING: failed to load {family} builder: {e}", flush=True)

    return builders


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def _load_manifest(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _ensure_resolved(manifest: dict) -> dict:
    """
    If the manifest has no resolved_assets (or they are all empty),
    run asset resolution inline so the templates always have something
    to work with.
    """
    ra = manifest.get("resolved_assets") or {}
    models = ra.get("models") or {}
    has_models = any(models.get(k) for k in ("buildings", "characters", "cars", "products", "props", "environments"))

    if not has_models:
        print("[DISPATCH] resolved_assets empty — running inline resolution", flush=True)
        try:
            from src.asset_resolver import resolve_scene_assets
            manifest["resolved_assets"] = resolve_scene_assets(manifest)
        except Exception as e:
            print(f"[DISPATCH] inline resolution failed: {e}", flush=True)
            manifest.setdefault("resolved_assets", {"models": {}, "hdris": [], "textures": []})

    return manifest


# ---------------------------------------------------------------------------
# Scene setup helpers
# ---------------------------------------------------------------------------

def _configure_render(bpy, manifest: dict) -> None:
    """
    Apply render settings from manifest to bpy.context.scene.
    All settings have safe defaults so missing manifest keys never crash.
    """
    scene = bpy.context.scene
    render = scene.render

    # Frame range
    scene.frame_start = int(manifest.get("frame_start", 1))
    scene.frame_end   = int(manifest.get("frame_end",   120))
    scene.frame_current = scene.frame_start

    # Resolution
    render.resolution_x      = int(manifest.get("resolution_x", 1920))
    render.resolution_y      = int(manifest.get("resolution_y", 1080))
    render.resolution_percentage = 100

    # Output path — caller sets this; we just verify it exists
    output_path = manifest.get("output_path", "")
    if output_path:
        render.filepath = str(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Render engine
    engine = str(manifest.get("render_engine", "CYCLES")).upper()
    if engine in ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        render.engine = engine
    else:
        render.engine = "CYCLES"

    # Samples
    samples = int(manifest.get("samples", 128))
    if render.engine == "CYCLES":
        scene.cycles.samples = samples
        # Use GPU if available, fall back to CPU silently
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "CUDA"
            prefs.get_devices()
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
    else:
        try:
            scene.eevee.taa_render_samples = min(samples, 256)
        except Exception:
            pass

    print(
        f"[DISPATCH] render config | engine={render.engine} "
        f"frames={scene.frame_start}-{scene.frame_end} "
        f"res={render.resolution_x}x{render.resolution_y} "
        f"samples={samples}",
        flush=True,
    )


def _clear_scene(bpy) -> None:
    """Remove all objects/lights/cameras from the default scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # Remove orphan mesh/material data left behind
    for collection in (bpy.data.meshes, bpy.data.materials,
                       bpy.data.cameras, bpy.data.lights):
        for item in list(collection):
            if item.users == 0:
                try:
                    collection.remove(item)
                except Exception:
                    pass


def _set_emergency_fallback(bpy) -> None:
    """
    If the scene builder crashes entirely, set a gradient world and place
    a camera so the render produces at least a non-gray frame.
    """
    scene = bpy.context.scene

    # Dark purple-blue gradient world
    if scene.world is None:
        scene.world = bpy.data.worlds.new("EmergencyWorld")
    w = scene.world
    w.use_nodes = True
    nodes = w.node_tree.nodes
    nodes.clear()
    bg  = nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.04, 0.04, 0.08, 1.0)
    bg.inputs[1].default_value = 1.0
    out = nodes.new("ShaderNodeOutputWorld")
    w.node_tree.links.new(bg.outputs[0], out.inputs[0])

    # Emergency stand-in cube so the frame is not void
    try:
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube = bpy.context.object
        cube.scale = (1, 1, 1)
    except Exception:
        pass

    # Ensure a camera exists
    if scene.camera is None:
        bpy.ops.object.camera_add(location=(0, -8, 3))
        scene.camera = bpy.context.object

    print("[DISPATCH] emergency fallback scene set", flush=True)


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def dispatch(manifest: dict, bpy) -> None:
    """
    Core dispatch logic.  Called by main() after loading the manifest.
    """
    scene_plan = manifest.get("scene_plan") or {}
    family = str(scene_plan.get("template_name") or
                 scene_plan.get("scene_family") or
                 manifest.get("template_name") or
                 "character_stage").lower().strip()

    print(f"[DISPATCH] scene family = {family}", flush=True)

    # Configure render settings before building the scene
    _configure_render(bpy, manifest)

    # Clear default cube / lights / camera
    _clear_scene(bpy)

    scene = bpy.context.scene

    # Load all builders (lazy, per-render)
    builders = _import_builders()

    # Family aliases / normalisation
    _ALIASES: dict[str, str] = {
        "scenic":        "scenic_landscape",
        "landscape":     "scenic_landscape",
        "mountain":      "scenic_landscape",
        "car":           "car_hero",
        "vehicle":       "car_hero",
        "car_scene":     "car_hero",
        "street":        "street_scene",
        "city":          "street_scene",
        "cat_city":      "street_scene",
        "ocean":         "ocean_scene",
        "underwater":    "ocean_scene",
        "whale":         "ocean_scene",
        "character":     "character_stage",
        "stage":         "character_stage",
        "cat_stage":     "character_stage",
        "product":       "product_scene",
        "product_hero":  "product_scene",
    }
    resolved_family = _ALIASES.get(family, family)

    if resolved_family not in builders:
        print(
            f"[DISPATCH] WARNING: unknown family '{resolved_family}' — "
            f"falling back to character_stage",
            flush=True,
        )
        resolved_family = "character_stage"

    build_fn = builders.get(resolved_family)
    if build_fn is None:
        print(
            "[DISPATCH] CRITICAL: no builder available — using emergency fallback",
            flush=True,
        )
        _set_emergency_fallback(bpy)
        return

    # ── Run the scene builder ────────────────────────────────────────────
    try:
        print(f"[DISPATCH] calling {resolved_family} builder …", flush=True)
        build_fn(bpy, manifest, scene)
        print(f"[DISPATCH] {resolved_family} builder completed OK", flush=True)
    except Exception as e:
        print(
            f"[DISPATCH] ERROR in {resolved_family} builder: {e}\n"
            + traceback.format_exc(),
            flush=True,
        )
        _set_emergency_fallback(bpy)

    # ── Ensure a camera is assigned ─────────────────────────────────────
    if scene.camera is None:
        cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
        if cams:
            scene.camera = cams[0]
        else:
            bpy.ops.object.camera_add(location=(0, -8, 3))
            scene.camera = bpy.context.object
        print("[DISPATCH] camera assigned from fallback", flush=True)


# ---------------------------------------------------------------------------
# Render execution
# ---------------------------------------------------------------------------

def render_animation(bpy) -> None:
    """Trigger the full animation render via bpy.ops.render.render."""
    print("[DISPATCH] starting render …", flush=True)
    try:
        bpy.ops.render.render(animation=True, write_still=False)
        print("[DISPATCH] render completed", flush=True)
    except Exception as e:
        print(f"[DISPATCH] render failed: {e}", flush=True)
        # Attempt single-frame fallback
        try:
            bpy.ops.render.render(animation=False, write_still=True)
            print("[DISPATCH] single-frame fallback rendered", flush=True)
        except Exception as e2:
            print(f"[DISPATCH] single-frame fallback also failed: {e2}", flush=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not _IN_BLENDER:
        print("[DISPATCH] Not running inside Blender — aborting.", flush=True)
        return

    # Arguments after '--' are passed to the script
    argv = sys.argv
    try:
        idx = argv.index("--")
        script_args = argv[idx + 1:]
    except ValueError:
        script_args = []

    if not script_args:
        print("[DISPATCH] Usage: blender --background --python render_from_manifest.py -- <manifest_path>", flush=True)
        sys.exit(1)

    manifest_path = script_args[0]
    print(f"[DISPATCH] loading manifest: {manifest_path}", flush=True)

    try:
        manifest = _load_manifest(manifest_path)
    except Exception as e:
        print(f"[DISPATCH] failed to load manifest: {e}", flush=True)
        sys.exit(1)

    manifest = _ensure_resolved(manifest)

    dispatch(manifest, bpy)
    render_animation(bpy)


if __name__ == "__main__":
    main()
