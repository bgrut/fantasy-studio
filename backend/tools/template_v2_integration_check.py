#!/usr/bin/env python3
"""
tools/template_v2_integration_check.py
======================================
Phase 4 integration check — simulates the exact manifest shape that
``asset_agent.enrich_manifest_with_assets`` builds at dispatch-time,
runs the V1.3 dispatcher+executor over it, and proves the written
scene_plan is what V1.1 template builders expect to consume.

Does NOT run Blender. This is a pure-Python verification that the
bridge between V1.3 (recipe data) and V1.1 (preset consumers) is
intact.

Run:
    python tools/template_v2_integration_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.template_v2 import load_registry, select_recipe, apply_recipe  # noqa: E402


def _ok(msg): print(f"\033[32m[ OK ]\033[0m {msg}")
def _fail(msg): print(f"\033[31m[FAIL]\033[0m {msg}")


def _enriched_manifest_shape(topic, env_subject=None, hero_cat="animal", family="scenic_landscape"):
    """Mirror the manifest shape that enrich_manifest_with_assets has
    already produced by the time the V2 dispatcher hook runs."""
    env_entry = None
    if env_subject:
        env_entry = {
            "id": f"lib_{env_subject}_test",
            "subject": env_subject,
            "subject_tags": [env_subject, "environment"],
            "biome_hints": [env_subject, "outdoor"],
            "shape_class": "3d_terrain",
            "_absolute_path": f"/fake/{env_subject}.glb",
        }
    return {
        "topic": topic,
        "core_objective_prompt": topic,
        "template_name": "auto",
        "render_tier": "preview",
        "scene_plan": {
            "scene_family": family,
            "template_name": "",
            "environment": env_subject or "generic",
            "subject_type": hero_cat,
            "focal_subject": "test",
            "camera_mode": "push_in",
            "lighting_mode": "cinematic_default",
        },
        "hero_asset_type": hero_cat,
        "forced_environment_id": env_entry["id"] if env_entry else None,
        "forced_environment_entry": env_entry,
        "_template_v2_enabled": True,
        "directorial_manifest": {
            "camera": {"style": "wide", "shot_type": "establishing"},
        },
    }


def main() -> int:
    print("=" * 70)
    print("V1.3 Template V2 — Phase 4 integration check")
    print("=" * 70)

    reg = load_registry()
    print(f"Registry: {reg.summary()}\n")

    # The three contracts we want to prove.
    test_cases = [
        {
            "label": "cat on mountain — expect hero_mountain_establishing",
            "manifest": _enriched_manifest_shape(
                "a cat on an epic mountain",
                env_subject="mountain",
                hero_cat="animal",
                family="scenic_landscape",
            ),
            "expect_preset_fields": ["camera_preset", "lighting_preset",
                                      "environment_preset", "animation_style",
                                      "post_preset"],
            "expect_recipe": "hero_mountain_establishing",
        },
        {
            "label": "Ferrari no env — expect V1.1 fallback (no preset writes)",
            "manifest": {
                "topic": "ferrari racing at sunset",
                "scene_plan": {"scene_family": "car_hero"},
                "hero_asset_type": "vehicle",
                "_template_v2_enabled": True,
            },
            "expect_preset_fields": [],  # None written by V2
            "expect_recipe": None,
        },
        {
            "label": "Flag OFF — V2 must not run",
            "manifest": {
                "topic": "a cat on an epic mountain",
                "forced_environment_id": "lib_mountain_test",
                "forced_environment_entry": {
                    "subject": "mountain", "subject_tags": ["mountain"],
                    "biome_hints": ["mountain"],
                },
                "scene_plan": {"scene_family": "scenic_landscape"},
                "hero_asset_type": "animal",
                "_template_v2_enabled": False,
            },
            "expect_preset_fields": [],
            "expect_recipe": None,
        },
    ]

    failures = 0
    for case in test_cases:
        print(f"--- {case['label']}")
        manifest = case["manifest"]
        before_keys = set((manifest.get("scene_plan") or {}).keys())

        # Honour flag exactly like asset_agent does
        if manifest.get("_template_v2_enabled"):
            recipe, score, debug = select_recipe(manifest, reg)
            if recipe is not None and recipe.get("name") != "_default":
                apply_recipe(manifest, recipe, reg, log_prefix="    [V2]")
                got_recipe = recipe.get("name")
            else:
                got_recipe = None
        else:
            print("    (flag OFF — V2 skipped)")
            got_recipe = None

        after_sp = manifest.get("scene_plan") or {}
        new_keys = [k for k in case["expect_preset_fields"] if k in after_sp]

        # Verify recipe choice
        if case["expect_recipe"] is None:
            if got_recipe is None:
                _ok(f"no recipe dispatched (as expected)")
            else:
                _fail(f"expected no recipe, got {got_recipe!r}")
                failures += 1
        else:
            if got_recipe == case["expect_recipe"]:
                _ok(f"dispatched {got_recipe!r}")
            else:
                _fail(f"expected {case['expect_recipe']!r}, got {got_recipe!r}")
                failures += 1

        # Verify preset fields written
        if case["expect_preset_fields"]:
            if set(new_keys) == set(case["expect_preset_fields"]):
                _ok(f"scene_plan now has all expected preset fields: {new_keys}")
            else:
                missing = set(case["expect_preset_fields"]) - set(new_keys)
                _fail(f"missing preset fields in scene_plan: {missing}")
                failures += 1
        else:
            # Expect no V2-written preset fields
            v2_written = [k for k in ("camera_preset", "lighting_preset",
                                       "environment_preset", "animation_style",
                                       "post_preset") if k in after_sp]
            if not v2_written:
                _ok("no V2 preset writes (V1.1 path preserved)")
            else:
                _fail(f"V2 wrote into scene_plan when it shouldn't have: {v2_written}")
                failures += 1

        # Verify V1.1-facing contract: the existing cinematic_presets.apply_*
        # helpers read these exact keys. If we wrote anything, it must be a
        # valid known preset name.
        if after_sp.get("camera_preset"):
            from app.scene.cinematic_presets import CAMERA_PRESETS, LIGHTING_PRESETS, ENVIRONMENT_PRESETS
            cp = after_sp["camera_preset"]
            if cp in CAMERA_PRESETS:
                _ok(f"camera_preset={cp!r} is a valid V1.1 preset")
            else:
                _fail(f"camera_preset={cp!r} is NOT in V1.1 CAMERA_PRESETS — V1.1 will crash")
                failures += 1
            lp = after_sp.get("lighting_preset")
            if lp and lp in LIGHTING_PRESETS:
                _ok(f"lighting_preset={lp!r} is a valid V1.1 preset")
            elif lp:
                _fail(f"lighting_preset={lp!r} is NOT in V1.1 LIGHTING_PRESETS")
                failures += 1
            ep = after_sp.get("environment_preset")
            if ep and ep in ENVIRONMENT_PRESETS:
                _ok(f"environment_preset={ep!r} is a valid V1.1 preset")
            elif ep:
                _fail(f"environment_preset={ep!r} is NOT in V1.1 ENVIRONMENT_PRESETS")
                failures += 1

        print()

    print("=" * 70)
    if failures:
        _fail(f"{failures} case(s) failed")
        return 1
    _ok("all integration checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
