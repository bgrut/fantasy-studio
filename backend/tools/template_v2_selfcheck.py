#!/usr/bin/env python3
"""
tools/template_v2_selfcheck.py
==============================
Phase 1 smoke test for the V1.3 Template System v2.

Loads the registry, validates every layer + recipe, then runs a small
set of mock manifests through the dispatcher + executor to prove the
round-trip works end-to-end.

Intentionally free of bpy / Blender — this is a pure-Python unit check
runnable in the backend's normal venv.

Usage:
    python tools/template_v2_selfcheck.py
    python tools/template_v2_selfcheck.py --verbose
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.template_v2 import (  # noqa: E402
    load_registry,
    select_recipe,
    apply_recipe,
    score_recipe,
)

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


# ── mock manifests covering the 3 primary V1.3 scenarios ──────────────

def _env(subject, tags=None, biome=None, shape="3d_terrain"):
    return {
        "subject": subject,
        "subject_tags": tags or [subject],
        "biome_hints": biome or [subject, "outdoor"],
        "shape_class": shape,
    }


MOCK_MANIFESTS = [
    {
        "label": "cat on mountain (Test 1.3.3)",
        "manifest": {
            "topic": "a cat on an epic mountain vista",
            "forced_environment_id": "lib_mountain_italy_mountain_castle_landscape",
            "forced_environment_entry": _env("mountain", ["mountain", "alpine", "landscape"], ["mountain", "outdoor"]),
            "scene_plan": {"scene_family": "scenic_landscape"},
            "hero_asset_type": "animal",
        },
        "expect_recipe": "hero_mountain_establishing",
    },
    {
        "label": "cat in canyon",
        "manifest": {
            "topic": "a cat in a cinematic red canyon",
            "forced_environment_id": "lib_canyon_canyon_landscape",
            "forced_environment_entry": _env("canyon", ["canyon"], ["canyon", "desert"], "flat_map"),
            "hero_asset_type": "animal",
        },
        "expect_recipe": "cat_canyon_cinematic",
    },
    {
        "label": "character desert epic",
        "manifest": {
            "topic": "a lone figure walking across vast dunes",
            "forced_environment_id": "lib_desert_desert_landscape",
            "forced_environment_entry": _env("desert", ["desert", "sand", "dune"], ["desert", "arid"]),
            "hero_asset_type": "character",
        },
        "expect_recipe": "hero_desert_epic",
    },
    {
        "label": "horse galloping through mountains (regression)",
        "manifest": {
            "topic": "a horse galloping through the mountains",
            "forced_environment_entry": _env("mountain", ["mountain", "alpine"]),
            "hero_asset_type": "animal",
        },
        "expect_recipe": "animal_mountain_walk",
    },
    {
        "label": "deer in forest",
        "manifest": {
            "topic": "a deer in a quiet forest clearing",
            "forced_environment_id": "lib_forest_*",
            "forced_environment_entry": _env("forest", ["forest", "woods", "tree"], ["forest", "outdoor"]),
            "hero_asset_type": "animal",
        },
        "expect_recipe": "animal_forest_intimate",
    },
    {
        "label": "robot on night street",
        "manifest": {
            "topic": "a robot walking a cyberpunk street at night",
            "forced_environment_entry": _env("city", ["city", "urban", "street", "cyberpunk"], ["city_night", "city", "urban"]),
            "hero_asset_type": "character",
        },
        "expect_recipe": "robot_city_night",
    },
    {
        "label": "Ferrari in desert",
        "manifest": {
            "topic": "a ferrari drifting across desert dunes",
            "forced_environment_entry": _env("desert", ["desert", "sand", "dune"]),
            "scene_plan": {"scene_family": "car_hero"},
            "hero_asset_type": "vehicle",
        },
        "expect_recipe": "vehicle_desert_hero",
    },
    {
        "label": "Ferrari on mountain road",
        "manifest": {
            "topic": "a ferrari on an alpine mountain pass",
            "forced_environment_entry": _env("mountain", ["mountain", "alpine", "road"]),
            "scene_plan": {"scene_family": "car_hero"},
            "hero_asset_type": "vehicle",
        },
        "expect_recipe": "vehicle_mountain_road",
    },
    {
        "label": "castle hero",
        "manifest": {
            "topic": "a knight in a medieval castle courtyard",
            "forced_environment_entry": _env("castle", ["castle", "medieval", "fortress"], ["castle", "medieval", "fantasy"]),
            "hero_asset_type": "character",
        },
        "expect_recipe": "hero_castle_dramatic",
    },
    {
        "label": "Ferrari alone — no forced env (Test 1.3.1 canary)",
        "manifest": {
            "topic": "ferrari racing at sunset",
            "scene_plan": {"scene_family": "car_hero"},
            "hero_asset_type": "vehicle",
        },
        "expect_recipe": None,  # must fall back to V1.1
    },
    {
        "label": "random abstract prompt",
        "manifest": {
            "topic": "abstract dream sequence",
            "scene_plan": {}
        },
        "expect_recipe": "_default_or_none",
    },
]


def _fail(msg: str) -> None:
    print(f"\033[31m[FAIL]\033[0m {msg}")


def _ok(msg: str) -> None:
    print(f"\033[32m[ OK ]\033[0m {msg}")


def _info(msg: str) -> None:
    print(f"[INFO] {msg}")


def main() -> int:
    print("=" * 70)
    print("V1.3 Template V2 — self-check")
    print("=" * 70)

    # 1) Load registry
    reg = load_registry()
    print()
    _info(reg.summary())

    if reg.errors:
        print("\nRegistry warnings/errors:")
        for e in reg.errors:
            print(f"  - {e}")

    # Must have at least 1 layer per kind hit in the example recipe
    required_layers = [
        ("base", "preview_tier"),
        ("environment", "mountain_vista"),
        ("composition", "establishing_wide"),
        ("lighting", "alpine_cool_daylight"),
        ("animation", "hero_idle_subtle"),
        ("ambient", "fog_atmospheric"),
        ("post", "cinematic_graded"),
    ]
    missing_layers = [(k, n) for k, n in required_layers if reg.get_layer(k, n) is None]
    if missing_layers:
        _fail(f"missing example layers: {missing_layers}")
        return 1
    _ok(f"all {len(required_layers)} example layers loaded")

    if reg.get_recipe("hero_mountain_establishing") is None:
        _fail("example recipe hero_mountain_establishing not loaded")
        return 1
    if reg.get_recipe("_default") is None:
        _fail("_default recipe not loaded")
        return 1
    _ok("example recipe + _default recipe loaded")

    # 2) Dispatch + execute for each mock
    failures = 0
    for case in MOCK_MANIFESTS:
        print("\n" + "-" * 70)
        print(f"Case: {case['label']}")
        recipe, score, debug = select_recipe(dict(case["manifest"]), reg)

        if VERBOSE:
            print(json.dumps(debug, indent=2))
        else:
            print(f"  chose={debug['chose']!r}  top={debug['top']}")

        expect = case["expect_recipe"]
        chosen = debug["chose"]

        if expect == "_default_or_none":
            if chosen in (None, "_default"):
                _ok(f"fallback OK (chose={chosen})")
            else:
                _fail(f"expected None or _default, got {chosen!r}")
                failures += 1
        elif expect is None:
            # V1.1 fallback path — chose must be None or _default
            if chosen in (None, "_default") or (recipe is not None and score < 50):
                _ok(f"V1.1 fallback respected (chose={chosen}, score={score})")
            else:
                _fail(f"expected fallback, but dispatcher confidently chose {chosen!r} score={score}")
                failures += 1
        else:
            if chosen == expect:
                _ok(f"dispatched {chosen!r} score={score}")
            else:
                _fail(f"expected {expect!r}, got {chosen!r} score={score}")
                failures += 1

        # Run executor and check scene_plan was populated
        if recipe is not None:
            mutated = dict(case["manifest"])
            apply_recipe(mutated, recipe, reg, log_prefix="  [V2_TEST]")
            sp = mutated.get("scene_plan") or {}
            wrote = [k for k in ("camera_preset", "lighting_preset",
                                 "environment_preset", "animation_style",
                                 "post_preset") if k in sp]
            if wrote:
                _ok(f"executor wrote {wrote} into scene_plan")
            else:
                if recipe.get("name") == "_default":
                    _ok("executor ran _default (no preset writes expected)")
                else:
                    _fail("executor ran but wrote nothing into scene_plan")
                    failures += 1

    print()
    print("=" * 70)
    if failures:
        _fail(f"{failures} case(s) failed")
        return 1
    _ok("all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
