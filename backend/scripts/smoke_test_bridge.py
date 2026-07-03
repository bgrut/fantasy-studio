"""
Smoke test — verifies the bridge + tool registry end-to-end.

Prerequisites:
    1. Install + enable the fantasy_studio_bridge addon in Blender
       (run scripts/install_bridge_addon.ps1)
    2. Open Blender. The addon auto-starts the bridge on 127.0.0.1:9876.
    3. Run this script: `python scripts/smoke_test_bridge.py`

What it does:
    1. ping → confirms bridge is alive
    2. get_scene_info → reads the default scene
    3. create_primitive → spawns a cube
    4. add_modifier → adds a bevel
    5. create_material + apply_material → red metallic
    6. add_light → SUN at angle
    7. create_camera → from (7,-7,5)
    8. tag the cube as hero (via execute_python escape hatch)
    9. hero_verify → reads the 7-check report
   10. set_render_settings + render_frame → writes to /tmp/test.png

Each step prints PASS/FAIL. Use this as a regression check after edits.
"""

import sys
import time
from pathlib import Path

# Make `app` importable
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.mcp import bridge, registry  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "smoke_test_output"
OUT_DIR.mkdir(exist_ok=True)


def step(name, fn):
    print(f"  [{name}]", end=" ", flush=True)
    t0 = time.time()
    try:
        result = fn()
        dt = time.time() - t0
        print(f"PASS ({dt*1000:.0f}ms)")
        if result is not None:
            print(f"     → {result}")
        return result
    except Exception as e:
        dt = time.time() - t0
        print(f"FAIL ({dt*1000:.0f}ms): {type(e).__name__}: {e}")
        return None


def main():
    print("═" * 70)
    print("Fantasy Studio Bridge — Smoke Test")
    print("═" * 70)

    print(f"\nRegistered tools: {registry.summary()['total']}")
    print(f"Categories: {registry.categories()}\n")

    print("→ Connecting to Blender bridge...")
    if not bridge.wait_until_ready(timeout=10.0):
        print("\n✗ Bridge not responding. Is Blender open with the addon enabled?")
        sys.exit(1)
    print("  ✓ Connected\n")

    print("→ Round-trip ping:")
    step("ping", lambda: registry.call("get_scene_info"))

    print("\n→ Build a minimal scene from scratch:")
    cube = step("create_primitive(cube)",
                lambda: registry.call("create_primitive", {"type": "cube", "name": "TestHero", "location": [0, 0, 1]}))

    step("add_modifier(bevel)",
         lambda: registry.call("add_modifier", {
             "object": "TestHero", "kind": "bevel",
             "settings": {"width": 0.1, "segments": 3},
         }))

    step("add_modifier(subdivision)",
         lambda: registry.call("add_modifier", {
             "object": "TestHero", "kind": "subdivision",
             "settings": {"levels": 2, "render_levels": 2},
         }))

    step("create_material(red metal)",
         lambda: registry.call("create_metal_material", {
             "name": "RedMetal", "color": [0.85, 0.1, 0.1], "polished": True,
         }))

    step("apply_material",
         lambda: registry.call("apply_material", {"object": "TestHero", "material": "RedMetal"}))

    step("apply_three_point_lighting",
         lambda: registry.call("apply_three_point_lighting", {
             "target": [0, 0, 1], "color_temp": "warm",
         }))

    step("create_camera + look_at",
         lambda: registry.call("create_camera", {
             "name": "TestCam", "location": [6, -6, 4],
         }))
    step("look_at hero",
         lambda: registry.call("look_at", {"object": "TestCam", "target": [0, 0, 1]}))

    # Tag hero (needs bridge op, not yet in tools — use escape hatch)
    step("tag TestHero as hero",
         lambda: registry.call("execute_python", {
             "code": "obj = bpy.data.objects.get('TestHero'); obj['is_forced_hero'] = True; obj['hero'] = True; __result__ = obj.name",
         }))

    print("\n→ Verifier loop:")
    verify_result = step("hero_verify",
                         lambda: registry.call("hero_verify"))
    if verify_result:
        passed = verify_result.get("passed")
        marker = "✓" if passed else "✗"
        print(f"     {marker} passed={passed}")
        for name, check in (verify_result.get("checks") or {}).items():
            ok = check.get("ok")
            print(f"        {'✓' if ok else '✗'} {name}: {check}")
        if verify_result.get("abort_reasons"):
            print(f"     abort_reasons: {verify_result['abort_reasons']}")
        if verify_result.get("warnings"):
            print(f"     warnings: {verify_result['warnings']}")

    print("\n→ Render:")
    out_png = str(OUT_DIR / "smoke_test_render.png")
    step("set_render_settings",
         lambda: registry.call("set_render_settings", {
             "engine": "BLENDER_EEVEE_NEXT", "resolution_x": 640, "resolution_y": 360, "samples": 32,
         }))
    step(f"render_frame → {out_png}",
         lambda: registry.call("render_frame", {"filepath": out_png}))

    print("\n→ Template system:")
    step("list_templates", lambda: registry.call("list_templates"))

    print("\n═" * 35)
    print(f"Smoke test complete. Output: {OUT_DIR}")
    print("═" * 70)


if __name__ == "__main__":
    main()
