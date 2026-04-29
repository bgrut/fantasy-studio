from __future__ import annotations

from dataclasses import asdict

from .asset_resolver import resolve_scene_assets, bucket_flat_models, _bucket_model
from .asset_fetcher import fetch_missing_assets
from .environment_resolver import determine_ground_type
from .scene_params import extract_scene_params
from .ui_input_mapper import map_ui_payload_to_generation_input
from .prompt_scene_planner import build_scene_plan
from .animation_instruction_builder import build_animation_payload
from .template_family_registry import resolve_template_name

# AI Director — optional, falls back gracefully when LLM is offline
try:
    from .ai_director import direct_scene, project_to_directorial_controls
    _HAS_DIRECTOR = True
except Exception:
    _HAS_DIRECTOR = False

# Round 11: curated asset library as Priority 1
try:
    from .curated_resolver import resolve_hero_from_catalog, find_closest_curated_asset
    _HAS_CURATED = True
except Exception as _e:
    print(f"[ASSET_AGENT] curated_resolver unavailable: {_e}", flush=True)
    _HAS_CURATED = False


# ─────────────────────────────────────────────────────────────────────────
# THE FLOW
# ─────────────────────────────────────────────────────────────────────────
# Every render goes through the same three layers, in order:
#
#   1. resolve_scene_assets(manifest)   — local asset_registry.json lookup
#   2. _inject_curated_hero(...)        — curated catalog (tested==True only)
#   3. fetch_missing_assets(...)        — Sketchfab / PolyHaven fallback
#   4. _inject_curated_fallback(...)    — last-ditch tested curated match
#
# There is no bypass. Explicit template_name selections read from the
# resolved_assets dict the same way auto-selected ones do.


def enrich_manifest_with_assets(manifest: dict) -> dict:
    manifest = dict(manifest)

    # Build normalized UI input from whatever the frontend currently sends
    gen_input = map_ui_payload_to_generation_input(manifest)

    # Build semantic scene plan from prompt + UI controls + references
    scene_plan = build_scene_plan(gen_input)
    manifest["scene_plan"] = asdict(scene_plan)

    # Resolve final template from scene family unless user explicitly forced one
    current_template = str(manifest.get("template_name", "") or "").strip().lower()
    if current_template in ("", "auto"):
        manifest["template_name"] = resolve_template_name(scene_plan.scene_family, fallback="city_loop")

    # Existing scene params still useful for lighting/camera hints
    scene_params = extract_scene_params(manifest)
    scene_params["camera_mode"] = scene_plan.camera_mode
    scene_params["lighting_preset"] = scene_plan.lighting_mode
    scene_params["focal_subject"] = scene_plan.focal_subject
    scene_params["environment"] = scene_plan.environment
    manifest["scene_params"] = scene_params

    # Add animation instructions for templates to consume later
    manifest["animation_instructions"] = build_animation_payload(scene_plan)

    # ── AI Director: produce directorial manifest + project onto controls ─
    # The directorial manifest is preserved in the manifest as
    # "directorial_manifest" so any builder can read camera/lighting/atmosphere
    # decisions from a single source of truth. We also project the manifest
    # down onto the existing directorial_controls dict so the legacy behavior
    # layer (motion_style / camera_style / energy_level) keeps working.
    if _HAS_DIRECTOR:
        try:
            director_input = {
                "scene_family":   scene_plan.scene_family,
                "template_family": scene_plan.scene_family,
                "subject":        scene_plan.focal_subject,
                "focal_subject":  scene_plan.focal_subject,
                "action":         scene_plan.animation_mode,
                "environment":    scene_plan.environment,
                "mood":           scene_plan.mood,
            }
            directorial_manifest = direct_scene(director_input)
            manifest["directorial_manifest"] = directorial_manifest

            projected = project_to_directorial_controls(directorial_manifest)
            existing_controls = dict(manifest.get("directorial_controls") or {})
            # User-supplied controls always win — only fill in keys the user
            # left blank (auto / None).
            for key, value in projected.items():
                if value is None:
                    continue
                if key in existing_controls and existing_controls[key]:
                    continue
                existing_controls[key] = value
            if existing_controls:
                manifest["directorial_controls"] = existing_controls
        except Exception as e:
            print(f"[ASSET_AGENT] AI director step skipped: {e}", flush=True)

    # ── Environment resolution ─────────────────────────────────────────
    sp = manifest["scene_plan"]
    ground_type = determine_ground_type(
        environment=sp.get("environment", ""),
        scene_family=sp.get("scene_family", ""),
        topic=str(manifest.get("topic", "")),
    )
    manifest["environment_ground_type"] = ground_type

    # ── ROLLBACK: always run the full pipeline ─────────────────────────
    # Local registry FIRST (templates read
    # manifest['resolved_assets']['models'][...] to find their hero), then
    # curated injection (tested-only guard still lives inside the helper),
    # then Sketchfab fallback. No bypass, no early returns.
    resolved_assets = resolve_scene_assets(manifest)
    print(
        f"[ASSET_AGENT] local registry resolved: {_summarize_models(resolved_assets)} "
        f"hdris={len(resolved_assets.get('hdris', []))} "
        f"textures={len(resolved_assets.get('textures', []))}",
        flush=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    # UNIFIED LIBRARY RESOLUTION — the fix for the three-stores bypass
    # ══════════════════════════════════════════════════════════════════════
    # Before the rest of the pipeline (curated → Sketchfab → Objaverse)
    # touches the resolved_assets, query the unified library.json for a
    # match.  A match here overrides any registry-supplied hero of the
    # same category.  This is what enables:
    #   1. Diversity rotation (multiple cat entries → different cat each
    #      render) — without this the registry's single cat_02.blend wins
    #      every time.
    #   2. Brand+model specificity ("Porsche 911" queries by brand=porsche
    #      model=911, so Ferrari no longer wins via keyword synonym).
    #   3. Visual-hint discrimination ("orange cat" prefers orange-tagged
    #      library entries when they exist).
    #
    # If the library has zero matches, this block is a no-op and the
    # existing pipeline runs unchanged.
    try:
        # ── forced_hero_id takes priority (Asset Picker UI) ────────
        # When the user explicitly picks an asset from the picker, the
        # frontend posts the library id on the manifest.  The resolver
        # skips auto-matching entirely and uses that specific entry.
        _forced_id = str(manifest.get("forced_hero_id") or "").strip()
        _lib_hero = None
        if _forced_id:
            _lib_hero = _resolve_hero_by_id(_forced_id)
            if _lib_hero:
                print(
                    f"[RESOLVE] forced_hero_id={_forced_id!r} — "
                    f"skipping auto-match",
                    flush=True,
                )
            else:
                print(
                    f"[RESOLVE] forced_hero_id={_forced_id!r} not found "
                    f"in library — falling back to auto-match",
                    flush=True,
                )
        if _lib_hero is None:
            _lib_hero = _resolve_hero_from_library(manifest)
        if _lib_hero:
            _overrode = _inject_library_hero_into_resolved(
                _lib_hero, resolved_assets, manifest,
            )
            if _overrode:
                print(
                    f"[RESOLVE] library hit overrode registry: "
                    f"id={_lib_hero.get('id')!r} "
                    f"path={_lib_hero.get('path')!r} "
                    f"subject={_lib_hero.get('subject')!r}",
                    flush=True,
                )
    except Exception as _res_err:
        print(f"[RESOLVE] library-first resolution failed (non-fatal): {_res_err}", flush=True)

    # ══════════════════════════════════════════════════════════════════════
    # MULTI-ASSET: resolve forced_environment_id
    # ══════════════════════════════════════════════════════════════════════
    # Parallel to forced_hero_id.  When user picks a specific environment
    # in the Asset Picker, we look it up now and stash the resolved record
    # on the manifest — the render script reads it in a dedicated import
    # pass BEFORE hero import, so hero placement can snap to the env's
    # top surface.
    try:
        _forced_env_id = str(manifest.get("forced_environment_id") or "").strip()
        _env_entry: dict | None = None
        if _forced_env_id:
            _env_entry = _resolve_environment_by_id(_forced_env_id)
            if _env_entry:
                print(
                    f"[RESOLVE] forced_environment_id={_forced_env_id!r} -> "
                    f"path={_env_entry['_absolute_path']!r} "
                    f"use_as={_env_entry.get('use_as', 'background_scenery')!r} "
                    f"scale_class={_env_entry.get('scale_class', 'large')!r}",
                    flush=True,
                )
        else:
            # Round 3: no forced env → try auto-pick from prompt.  Only
            # matches when prompt contains an env-indicative keyword
            # (canyon, mountain, city, ...).  Silently bails otherwise.
            _prompt_for_env = " ".join([
                str(manifest.get("topic", "")),
                str(manifest.get("core_objective_prompt", "")),
                str((manifest.get("scene_plan") or {}).get("environment") or ""),
            ])
            _env_entry = auto_pick_environment(_prompt_for_env)
            if _env_entry:
                _forced_env_id = str(_env_entry.get("id") or "")
                manifest["_auto_picked_environment"] = True
                print(
                    f"[RESOLVE] auto-picked environment id={_forced_env_id!r} "
                    f"from prompt keywords",
                    flush=True,
                )
        if _env_entry:
            manifest["forced_environment_path"] = _env_entry["_absolute_path"]
            manifest["forced_environment_entry"] = _env_entry
            # Track in used_assets for credits sidecar
            _used = manifest.setdefault("used_assets", [])
            if _forced_env_id and not any(
                isinstance(u, dict) and u.get("id") == _forced_env_id for u in _used
            ):
                _used.append({"id": _forced_env_id, "role": "environment"})
    except Exception as _env_err:
        print(f"[RESOLVE] forced_environment_id resolution failed (non-fatal): {_env_err}", flush=True)

    # Props are enabled automatically when the prompt mentions a prop
    # context word ("with", "holding", "near", etc.). For simple prompts
    # like "Ferrari racing at sunset", props stay off to keep the scene
    # clean. For contextual prompts like "dog near a campfire", we let
    # the fetcher look up the surrounding objects.
    #
    # SPECIAL CASE: when the user forced a specific library hero via
    # the Asset Picker UI, they explicitly chose their scene subject.
    # We honor that by disabling prop fetch entirely — no surprise
    # Sketchfab downloads adding random fish to a whale shot.  The
    # user gets exactly what they picked, plus world-dev biome scatter.
    _forced_hero_for_props = str(manifest.get("forced_hero_id") or "").strip()
    if _forced_hero_for_props:
        if manifest.get("_enable_prop_fetch"):
            print(
                f"[ASSET_AGENT] prop fetch OVERRIDDEN off — "
                f"forced_hero_id={_forced_hero_for_props!r} is set, "
                f"respecting user's scene intent",
                flush=True,
            )
        else:
            print(
                f"[ASSET_AGENT] prop fetch SKIPPED — "
                f"forced_hero_id={_forced_hero_for_props!r} is set, "
                f"respecting user's scene intent",
                flush=True,
            )
        manifest["_enable_prop_fetch"] = False
    elif "_enable_prop_fetch" not in manifest:
        _prompt_lower = " ".join([
            str(manifest.get("topic", "")),
            str(manifest.get("core_objective_prompt", "")),
        ]).lower()
        _PROP_CONTEXT_KEYWORDS = (
            "with ", "holding ", "riding ", "carrying ", "wearing ",
            "next to ", "beside ", "near ", "in a ", "on a ", "on the ",
            "in the ", "by the ", "at the ",
        )
        _has_prop_context = any(kw in _prompt_lower for kw in _PROP_CONTEXT_KEYWORDS)
        manifest["_enable_prop_fetch"] = _has_prop_context
        if _has_prop_context:
            print(
                f"[ASSET_AGENT] prop fetch AUTO-ENABLED — prompt contains "
                f"contextual object keywords",
                flush=True,
            )

    # Priority 1: curated library (tested entries only; helper enforces).
    _inject_curated_hero(manifest, resolved_assets)

    # Priority 2: Sketchfab fallback for anything still missing.
    fetch = fetch_missing_assets(
        template_name=manifest.get("template_name", ""),
        resolved_assets=resolved_assets,
        manifest=manifest,
    )

    # Post-fetch: ensure models is in bucketed dict form that templates
    # expect. fetch_missing_assets flattens to a list at the end for
    # compatibility; we bucket it back here.
    final_assets = fetch["resolved_assets"]
    raw_models = final_assets.get("models")
    if isinstance(raw_models, list):
        print(f"[ASSET_AGENT] bucketing {len(raw_models)} flat model(s)", flush=True)
        final_assets["models"] = bucket_flat_models(raw_models)
    elif isinstance(raw_models, dict):
        pass  # already bucketed
    else:
        final_assets["models"] = {
            "buildings": [], "characters": [], "cars": [], "vehicles": [],
            "environments": [], "props": [], "products": [], "signs": [],
        }

    if isinstance(final_assets.get("models"), dict):
        print(
            f"[ASSET_AGENT] final bucketed models: {_summarize_models(final_assets)}",
            flush=True,
        )

    # Priority 3: curated fallback when Sketchfab also came back empty.
    _inject_curated_fallback(manifest, final_assets)

    manifest["resolved_assets"] = final_assets
    manifest["fetch_report"] = fetch["report"]

    # ── Extract hero asset metadata for behavior-driven animation + camera ─
    _extract_hero_metadata(manifest, final_assets)

    # ── Default behavior for animal / character heroes ────────────────
    # If the scene plan doesn't specify an animation style and the hero
    # is an animal or character, default to walking/idle so the subject
    # isn't rendered frozen.  Without this, "polar bear in the arctic"
    # gets animation_style="" which falls back to static showcase.
    _sp_default = manifest.get("scene_plan") or {}
    if not _sp_default.get("animation_style"):
        _hero_type_default = str(manifest.get("hero_asset_type") or "").lower()
        _prompt_default = str(manifest.get("topic", "")).lower()
        _ACTION_VERBS = {
            "running": "character_walk",
            "walking": "character_walk",
            "galloping": "character_walk",
            "flying": "character_walk",  # closest profile; bird reuses walk kf
            "swimming": "character_walk",
            "dancing": "character_dance",
            "jumping": "character_walk",
            "driving": "vehicle_drive",
            "racing": "vehicle_drive",
        }
        _inferred_style = None
        for _verb, _style in _ACTION_VERBS.items():
            if _verb in _prompt_default:
                _inferred_style = _style
                break
        if _inferred_style is None:
            if _hero_type_default in ("animal", "character", "creature"):
                _inferred_style = "idle_breathe"
            elif _hero_type_default == "vehicle":
                _inferred_style = "vehicle_drive"
        if _inferred_style:
            _sp_default["animation_style"] = _inferred_style
            manifest["scene_plan"] = _sp_default
            print(
                f"[ASSET_AGENT] defaulted animation_style={_inferred_style!r} "
                f"(hero_type={_hero_type_default!r})",
                flush=True,
            )

    # ══════════════════════════════════════════════════════════════════════
    # V1.3 — Template System v2 dispatcher + executor
    # ══════════════════════════════════════════════════════════════════════
    # Gated behind manifest["_template_v2_enabled"] so production traffic
    # keeps running V1.1 unchanged.  When enabled, we run the dispatcher
    # AFTER hero/env resolution + scene_plan build — at this point the
    # context the dispatcher scores against is complete:
    #   - scene_plan.scene_family is set
    #   - forced_environment_entry is set (if forced or auto-picked)
    #   - hero_asset_type is extracted
    #   - directorial_manifest is populated (LLM camera/shot hints)
    #
    # On a hit, the executor writes preset hints into manifest["scene_plan"]
    # that the existing V1.1 template builders already consume.  On a
    # miss (recipe=None or _default), V1.1 behaviour is preserved.
    if manifest.get("_template_v2_enabled"):
        try:
            from .template_v2 import load_registry, select_recipe, apply_recipe
            _v2_registry = load_registry()
            if _v2_registry.errors:
                for _e in _v2_registry.errors[:5]:
                    print(f"[TEMPLATE_V2] registry warn: {_e}", flush=True)
            _v2_recipe, _v2_score, _v2_debug = select_recipe(manifest, _v2_registry)
            print(
                f"[TEMPLATE_V2_DISPATCH] "
                f"chose={_v2_debug.get('chose')!r} score={_v2_score} "
                f"top={_v2_debug.get('top')}",
                flush=True,
            )
            if _v2_recipe is not None and _v2_recipe.get("name") != "_default":
                apply_recipe(manifest, _v2_recipe, _v2_registry)
            else:
                print(
                    "[TEMPLATE_V2] no specialized recipe matched — "
                    "leaving scene_plan untouched (V1.1 path)",
                    flush=True,
                )
        except Exception as _v2_err:
            import traceback as _v2_tb
            print(f"[TEMPLATE_V2] dispatch failed (non-fatal): {_v2_err}", flush=True)
            print(_v2_tb.format_exc(), flush=True)

    # ── Dedup: remove hero_asset_path duplicates from resolved_assets ─
    # Only dedup if hero_asset_path is definitively set to a real, existing file.
    # Without this guard, the dedup fires before hero_asset_path is set,
    # strips the only vehicle from resolved_assets, and the bucketing step
    # finds no vehicles → falls back to scenic_landscape (the "Ferrari
    # renders mountain scene" bug).
    import os as _os_dedup
    _hero_for_dedup = manifest.get("hero_asset_path")
    if (
        _hero_for_dedup
        and str(_hero_for_dedup).strip() not in ("", "None")
        and _os_dedup.path.exists(str(_hero_for_dedup))
    ):
        _dedup_hero_from_resolved(manifest)
    else:
        print(
            f"[DEDUP] skipping — hero_asset_path is not set or file "
            f"doesn't exist: {_hero_for_dedup!r}",
            flush=True,
        )

    return manifest


def _resolve_environment_by_id(env_id: str) -> dict | None:
    """Look up a library environment entry by id.

    Multi-asset composition path: when user picks a specific environment
    in the Asset Picker UI, we resolve it here and stash the resolved
    record on the manifest for the render script to import as backdrop.

    Returns the library entry (with ``_absolute_path`` populated) or
    None if: id missing, not found, wrong category, or file absent.
    """
    if not env_id:
        return None
    try:
        import json as _json
        from pathlib import Path as _PathR
        root = _PathR(__file__).resolve().parents[2]
        lib_path = root / "app" / "data" / "library.json"
        if not lib_path.exists():
            return None
        data = _json.loads(lib_path.read_text(encoding="utf-8"))
        for a in data.get("assets", []):
            if not isinstance(a, dict):
                continue
            if a.get("id") == env_id:
                if str(a.get("category") or "").lower() != "environment":
                    print(
                        f"[RESOLVE] WARN: forced_environment_id={env_id!r} "
                        f"found but category={a.get('category')!r} "
                        f"(expected 'environment') — ignoring",
                        flush=True,
                    )
                    return None
                p = str(a.get("path") or "")
                if not p:
                    return None
                full = _PathR(p)
                if not full.is_absolute():
                    full = root / p
                if not full.exists():
                    print(
                        f"[RESOLVE] forced_environment_id={env_id!r} "
                        f"but file missing at {full}",
                        flush=True,
                    )
                    return None
                out = dict(a)
                out["_absolute_path"] = str(full)
                return out
    except Exception as e:
        print(f"[RESOLVE] _resolve_environment_by_id failed: {e}", flush=True)
    print(
        f"[RESOLVE] WARN: forced_environment_id={env_id!r} not found "
        f"in library or not an environment entry",
        flush=True,
    )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Round 3 — Auto-Pick Environment From Prompt
# ═══════════════════════════════════════════════════════════════════════════
# When the user has NOT selected an env in the Asset Picker (no
# forced_environment_id), inspect the prompt for env-indicative keywords
# and, when one is found with high confidence, auto-select a matching
# library environment.  This gives "Ferrari in the canyon" a real canyon
# backdrop without requiring the user to pick one manually.
#
# The map goes  prompt_token → canonical_keyword.  canonical_keyword is
# then matched against library entries' subject / subject_tags /
# biome_hints.  3d_terrain + flat_map entries are preferred over
# 3d_small_env (which is really a prop-sized scene).
# ═══════════════════════════════════════════════════════════════════════════

_ENV_KEYWORD_SYNONYMS: dict[str, str] = {
    # canyon / desert family
    "canyon": "canyon", "canyons": "canyon", "gorge": "canyon",
    "ravine": "canyon", "butte": "canyon", "mesa": "canyon",
    "desert": "desert", "deserts": "desert", "dunes": "desert",
    "sahara": "desert", "arid": "desert", "sand": "desert",
    # mountain / alpine
    "mountain": "mountain", "mountains": "mountain", "alpine": "mountain",
    "alps": "mountain", "peak": "mountain", "peaks": "mountain",
    "ridge": "mountain", "summit": "mountain", "hill": "mountain",
    "hills": "mountain",
    # arctic / snow / ice
    "arctic": "arctic", "tundra": "arctic", "snow": "arctic",
    "snowy": "arctic", "ice": "arctic", "icy": "arctic",
    "glacier": "glacier", "glacial": "glacier", "iceland": "iceland",
    "winter": "winter", "frozen": "arctic",
    # city / urban
    "city": "city", "cityscape": "city", "urban": "city",
    "downtown": "city", "skyline": "city", "street": "city",
    "streets": "city", "metropolis": "city",
    "rooftop": "rooftop", "rooftops": "rooftop",
    # forest / nature
    "forest": "forest", "woods": "forest", "woodland": "forest",
    "jungle": "forest", "grove": "forest",
    # castle / medieval
    "castle": "castle", "fortress": "castle", "keep": "castle",
    "citadel": "castle", "medieval": "castle",
    # ocean / coast
    "ocean": "ocean", "sea": "ocean", "coast": "ocean",
    "beach": "ocean", "shore": "ocean",
    # italy / european
    "italy": "italy", "italian": "italy", "tuscany": "italy",
    "european": "european", "europe": "european",
    # storm / sky
    "thunderstorm": "thunderstorm", "storm": "thunderstorm",
    "stormy": "thunderstorm",
    # landscape fallback
    "landscape": "landscape", "countryside": "landscape",
    "fields": "landscape", "meadow": "landscape",
    # road
    "road": "road", "highway": "road", "route": "road",
}


def _extract_env_keyword(prompt: str) -> str | None:
    """Scan prompt for the strongest env keyword; return canonical token
    or None if the prompt doesn't mention any env cue."""
    if not prompt:
        return None
    text = prompt.lower()
    # Tokenize on non-word boundaries so "canyon." / "canyons," match.
    import re as _re
    tokens = _re.findall(r"[a-z]+", text)
    if not tokens:
        return None
    # Match longest/specific first.  We check each token; first hit wins.
    for tok in tokens:
        if tok in _ENV_KEYWORD_SYNONYMS:
            return _ENV_KEYWORD_SYNONYMS[tok]
    return None


def _library_env_entries() -> list[dict]:
    """Return all environment entries from library.json with absolute path
    resolved.  Filters entries whose file is missing."""
    try:
        import json as _json
        from pathlib import Path as _PathR
        root = _PathR(__file__).resolve().parents[2]
        lib_path = root / "app" / "data" / "library.json"
        if not lib_path.exists():
            return []
        data = _json.loads(lib_path.read_text(encoding="utf-8"))
        out: list[dict] = []
        for a in data.get("assets", []):
            if not isinstance(a, dict):
                continue
            if str(a.get("category") or "").lower() != "environment":
                continue
            p = str(a.get("path") or "")
            if not p:
                continue
            full = _PathR(p)
            if not full.is_absolute():
                full = root / p
            if not full.exists():
                continue
            rec = dict(a)
            rec["_absolute_path"] = str(full)
            out.append(rec)
        return out
    except Exception as e:
        print(f"[RESOLVE] _library_env_entries failed: {e}", flush=True)
        return []


def _score_env_entry(entry: dict, keyword: str) -> int:
    """Score a library env entry against a canonical env keyword.
    Higher = better.  Returns 0 if no signal at all."""
    score = 0
    subject = str(entry.get("subject") or "").lower()
    if keyword and keyword == subject:
        score += 100
    elif keyword and keyword in subject:
        score += 60
    for t in (entry.get("subject_tags") or []):
        ts = str(t).lower()
        if ts == keyword:
            score += 40
        elif keyword in ts:
            score += 15
    for b in (entry.get("biome_hints") or []):
        bs = str(b).lower()
        if bs == keyword:
            score += 30
        elif keyword in bs:
            score += 10
    # Shape preference: 3d_terrain > flat_map > 3d_small_env
    shape = str(entry.get("shape_class") or "").lower()
    if shape == "3d_terrain":
        score += 8
    elif shape == "flat_map":
        score += 5
    elif shape == "3d_small_env":
        score += 1
    # Lower use_count = better (rotation)
    try:
        uc = int(entry.get("use_count") or 0)
        score -= min(uc, 10)  # cap penalty
    except Exception:
        pass
    return score


def auto_pick_environment(prompt: str) -> dict | None:
    """Return the best-scoring library env entry for the prompt, or None.

    The match must score > 0 — if the prompt doesn't mention any
    env-indicative keyword, we bail out (no surprise environments).
    """
    keyword = _extract_env_keyword(prompt or "")
    if not keyword:
        return None
    entries = _library_env_entries()
    if not entries:
        return None
    scored = [(e, _score_env_entry(e, keyword)) for e in entries]
    scored = [(e, s) for (e, s) in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda x: -x[1])
    best, best_score = scored[0]
    # V1.3.6 Fix 5: require a strong keyword signal before force-picking
    # an env. Otherwise prompts like "horse in the mountain" silently
    # collapse onto whatever env happens to score 8 from shape bonus
    # alone (e.g. desert). Below threshold → return None so the
    # procedural ENV_PRESET path runs instead.
    MIN_AUTO_PICK_SCORE = 40
    if best_score < MIN_AUTO_PICK_SCORE:
        print(
            f"[RESOLVE] auto-pick env keyword={keyword!r} — best "
            f"candidate id={best.get('id')!r} score={best_score} "
            f"below MIN_AUTO_PICK_SCORE={MIN_AUTO_PICK_SCORE}; "
            f"declining to force-pick (procedural preset will run)",
            flush=True,
        )
        return None
    print(
        f"[RESOLVE] auto-pick env keyword={keyword!r} -> "
        f"id={best.get('id')!r} score={best_score} "
        f"shape={best.get('shape_class')!r}",
        flush=True,
    )
    return best


def _resolve_hero_by_id(asset_id: str) -> dict | None:
    """Look up a library entry by its id and return the record (with an
    ``_absolute_path`` field set) or None if not found / file missing."""
    if not asset_id:
        return None
    try:
        import json as _json
        import os as _os
        from pathlib import Path as _PathR
        root = _PathR(__file__).resolve().parents[2]
        lib_path = root / "app" / "data" / "library.json"
        if not lib_path.exists():
            return None
        data = _json.loads(lib_path.read_text(encoding="utf-8"))
        for a in data.get("assets", []):
            if not isinstance(a, dict):
                continue
            if a.get("id") == asset_id:
                p = str(a.get("path") or "")
                if not p:
                    return None
                full = _PathR(p)
                if not full.is_absolute():
                    full = root / p
                if not full.exists():
                    print(
                        f"[RESOLVE] forced_hero_id={asset_id!r} but file "
                        f"missing at {full}",
                        flush=True,
                    )
                    return None
                out = dict(a)
                out["_absolute_path"] = str(full)
                return out
    except Exception as e:
        print(f"[RESOLVE] _resolve_hero_by_id failed: {e}", flush=True)
    return None


def _resolve_hero_from_library(manifest: dict) -> dict | None:
    """Query the unified library.json for a subject-matching hero.

    Uses brand+model strict filter when the subject is a specific branded
    request (e.g. "porsche 911"), otherwise falls back to permissive
    subject+tag matching with visual-hint bonuses.

    When 3+ tested entries exist, delegates to pick_with_diversity for
    rotation.  Returns the chosen library entry dict or None if no
    match exists on disk.
    """
    sp = manifest.get("scene_plan") or {}
    subject = str(
        sp.get("focal_subject") or sp.get("subject") or ""
    ).strip().lower()
    # Fall back to extracting subject from topic if scene_plan empty
    if not subject:
        subject = str(manifest.get("topic") or "").strip().lower()
    if not subject:
        return None

    # Derive brand/model for specific-subject strict filtering.
    # _is_specific_subject + token maps come from earlier in this module.
    tokens = subject.split()
    brand = next((t for t in tokens if t in _HERO_GATE_BRAND_TOKENS), None)
    model = next(
        (t for t in tokens
         if t in _HERO_GATE_MODEL_INDICATORS or (t.isdigit() and len(t) >= 3)),
        None,
    )

    # Visual hints
    try:
        from .library_curator import extract_visual_hints, query_library_strict
        hints = extract_visual_hints(
            str(manifest.get("topic", ""))
            + " " + str(manifest.get("core_objective_prompt", ""))
        )
    except Exception as _e:
        print(f"[RESOLVE] library import failed: {_e}", flush=True)
        return None

    # Strict brand+model query first
    specific = _is_specific_subject(subject) if brand and model else False
    if specific:
        print(
            f"[RESOLVE] subject={subject!r} specific=True "
            f"brand={brand!r} model={model!r} hints={hints}",
            flush=True,
        )
        hits = query_library_strict(
            subject, brand=brand, model=model,
            visual_hints=hints, quality_filter=["tested", "unverified"],
            limit=10,
        )
    else:
        print(
            f"[RESOLVE] subject={subject!r} specific=False hints={hints}",
            flush=True,
        )
        hits = query_library_strict(
            subject, visual_hints=hints,
            quality_filter=["tested", "unverified"],
            limit=10,
        )

    # Filter to entries whose file actually exists on disk
    import os as _os_r
    from pathlib import Path as _PathR
    _root = _PathR(__file__).resolve().parents[2]
    existing_hits = []
    for h in hits:
        p = h.get("path")
        if not p:
            continue
        # Resolve relative paths against project root
        full = _PathR(p)
        if not full.is_absolute():
            full = _root / p
        if full.exists():
            # Stash resolved absolute path back for downstream use
            h = dict(h)
            h["_absolute_path"] = str(full)
            existing_hits.append(h)

    tested_count = sum(1 for h in existing_hits if h.get("quality") == "tested")
    unverified_count = len(existing_hits) - tested_count
    print(
        f"[RESOLVE] library_hits={len(existing_hits)} "
        f"tested={tested_count} unverified={unverified_count}",
        flush=True,
    )

    if not existing_hits:
        return None

    # Diversity pick
    try:
        from .variant_pool import pick_with_diversity, register_variants, mark_used
        pool_entries = [
            {
                "id":     h.get("id"),
                "uid":    h.get("id"),
                "name":   h.get("subject"),
                "score":  100 if h.get("quality") == "tested" else 50,
                "path":   h.get("path"),
                "tags":   h.get("subject_tags", []),
                "source": h.get("source", "library"),
            }
            for h in existing_hits
        ]
        register_variants(subject, pool_entries)
        chosen_pool = pick_with_diversity(subject, pool_entries)
        if chosen_pool is None:
            # V1.3 final resolver fix: subject filter emptied the pool.
            # Library has no entry that actually matches the requested
            # subject.  Return None so enrich_manifest_with_assets defers
            # to Objaverse / Sketchfab instead of silently grabbing the
            # top cross-subject hit (e.g. cat_03.blend for 'person').
            return None
        # Find the original hit dict for the chosen id
        cid = chosen_pool.get("id")
        chosen = next((h for h in existing_hits if h.get("id") == cid), existing_hits[0])
        mark_used(subject, str(chosen.get("id") or ""))
    except Exception as _de:
        # Exception-path fallback stays — this guards against unexpected
        # runtime errors during diversity pick, NOT against "no subject
        # match" which the None-return path above handles correctly.
        print(f"[RESOLVE] diversity pick failed, using top hit: {_de}", flush=True)
        chosen = existing_hits[0]

    return chosen


def _inject_library_hero_into_resolved(
    lib_hero: dict,
    resolved_assets: dict,
    manifest: dict,
) -> bool:
    """Place a library-resolved hero into resolved_assets.models so the
    existing pipeline picks it up as if the registry had provided it.

    Returns True when injection happened, False otherwise.
    """
    if not lib_hero or not isinstance(resolved_assets, dict):
        return False

    category = str(lib_hero.get("category") or "").lower()
    # Map library category → resolved_assets.models bucket
    bucket_map = {
        "vehicle":     "vehicles",
        "character":   "characters",
        "environment": "environments",
        "prop":        "props",
        "hdri":        None,  # hdris are handled separately
    }
    bucket = bucket_map.get(category)
    if not bucket:
        # Best-effort from subject_tags
        tags = {str(t).lower() for t in (lib_hero.get("subject_tags") or [])}
        if "vehicle" in tags or "car" in tags:
            bucket = "vehicles"
        elif "character" in tags or "animal" in tags:
            bucket = "characters"
        elif "environment" in tags or "building" in tags:
            bucket = "environments"
        else:
            bucket = "characters"  # safe default for unclassified

    models = resolved_assets.setdefault("models", {})
    # If models is a flat list (legacy), bucket it first
    if isinstance(models, list):
        models = bucket_flat_models(models)
        resolved_assets["models"] = models

    # Build a registry-shaped entry from the library entry
    abs_path = lib_hero.get("_absolute_path") or lib_hero.get("path")
    reg_md = lib_hero.get("registry_metadata") or {}
    # Mark the registry entry as forced if the library id matches the
    # user's explicit pick.  Downstream glb_import reads this flag and
    # stamps is_forced_hero=True on every imported mesh so the Hero
    # Tagger's stage-C centroid heuristic short-circuits to the correct
    # cluster even when a prop ends up closer to origin.
    _forced_from_manifest = str(manifest.get("forced_hero_id") or "").strip()
    _is_forced_hero = bool(
        _forced_from_manifest
        and lib_hero.get("id") == _forced_from_manifest
    )
    registry_entry = {
        "id":           lib_hero.get("id"),
        "type":         category if category != "character" else (
            "animal" if "animal" in (lib_hero.get("subject_tags") or []) else "character"
        ),
        "category":     category,  # NEW: expose category so _enforce_scale can read it
        "tags":         list(lib_hero.get("subject_tags") or []),
        "subject_tags": list(lib_hero.get("subject_tags") or []),
        "path":         abs_path,
        "blend_kind":   reg_md.get("blend_kind", "object"),
        "blend_name":   reg_md.get("blend_name"),
        "species":      reg_md.get("species"),
        "is_rigged":    bool(reg_md.get("is_rigged")),
        "has_animation": bool(reg_md.get("has_animation")),
        "scale_class":  lib_hero.get("scale_class", "medium"),
        # Fields used by _extract_hero_metadata
        "name":         lib_hero.get("subject"),
        "subject":      lib_hero.get("subject"),
        "source":       lib_hero.get("source"),
        "score":        100,
        "_from_library": True,
        "_is_forced_hero": _is_forced_hero,
        # V1.2 heal-metadata passthrough: glb_import reads these to apply
        # orientation fix + ground offset after normalization.
        "healer_version":                  lib_hero.get("healer_version"),
        "orientation_issue":               lib_hero.get("orientation_issue"),
        "orientation_fix_rotation_euler":  lib_hero.get("orientation_fix_rotation_euler"),
        "ground_offset_z":                 lib_hero.get("ground_offset_z"),
    }

    # Replace the bucket's contents with this entry as the first item.
    # Keeping registry's own entries as backups is dangerous (two cats
    # in one scene) — we bulldoze the bucket with the library choice.
    models[bucket] = [registry_entry]
    # Stash the library choice on the manifest so post-render can see it
    manifest["_library_hero_entry"] = {
        "id":      lib_hero.get("id"),
        "path":    abs_path,
        "subject": lib_hero.get("subject"),
        "source":  lib_hero.get("source"),
        "quality": lib_hero.get("quality"),
    }
    # Register in used_assets list for credits.txt sidecar
    try:
        from .credits_writer import register_used_asset
        register_used_asset(manifest, lib_hero.get("id"), role="hero")
    except Exception:
        pass
    return True


def _summarize_models(assets: dict) -> dict:
    """Quick {bucket: count} snapshot for logging."""
    models = assets.get("models") if isinstance(assets, dict) else None
    if isinstance(models, dict):
        return {k: len(v) for k, v in models.items() if isinstance(v, list) and v}
    if isinstance(models, list):
        return {"_flat": len(models)}
    return {}


def _dedup_hero_from_resolved(manifest: dict) -> None:
    """
    If hero_asset_path is set, remove that same asset from
    resolved_assets.models buckets to prevent double-import.

    This is the root-cause fix for the "two cars overlaid" bug:
    the synonym system sets hero_asset_path to one car while the
    resolver puts a different (or same) car in the vehicles bucket.
    """
    import os

    hero_path = str(manifest.get("hero_asset_path") or "").strip()
    if not hero_path:
        return

    resolved = manifest.get("resolved_assets")
    if not isinstance(resolved, dict):
        return
    models = resolved.get("models")
    if not isinstance(models, dict):
        return

    hero_norm = os.path.normcase(os.path.normpath(os.path.abspath(hero_path)))
    hero_id = os.path.splitext(os.path.basename(hero_path))[0].lower()

    for bucket_name in ("vehicles", "cars", "characters", "props", "products"):
        bucket = models.get(bucket_name)
        if not isinstance(bucket, list) or not bucket:
            continue
        original_count = len(bucket)

        deduped = []
        for entry in bucket:
            if not isinstance(entry, dict):
                deduped.append(entry)
                continue
            entry_path = str(entry.get("path") or entry.get("local_path") or entry.get("file") or "")
            if entry_path:
                entry_norm = os.path.normcase(os.path.normpath(os.path.abspath(entry_path)))
                if entry_norm == hero_norm:
                    continue  # exact path match — duplicate
            entry_id = str(entry.get("id") or "").lower()
            if entry_id and hero_id and entry_id == hero_id:
                continue  # same asset ID — duplicate
            deduped.append(entry)

        if len(deduped) < original_count:
            models[bucket_name] = deduped
            removed = original_count - len(deduped)
            print(
                f"[DEDUP] removed {removed} duplicate(s) from "
                f"resolved_assets.models.{bucket_name} (matched hero_asset_path)",
                flush=True,
            )


def _has_hero_in_buckets(models: dict) -> bool:
    """True when a character/vehicle/prop bucket already holds something."""
    if not isinstance(models, dict):
        return False
    for bucket in ("characters", "vehicles", "cars", "products", "props"):
        if models.get(bucket):
            return True
    return False


def _has_tested_assets() -> bool:
    """
    True when the curated catalog contains at least one ``tested: true``
    asset. Without this, every auto-registered Sketchfab leftover would
    be treated as a curated hit and overwrite the template's picks.
    """
    if not _HAS_CURATED:
        return False
    try:
        from .curated_resolver import load_catalog
        catalog = load_catalog()
        assets = catalog.get("assets") or []
        return any(
            isinstance(a, dict) and bool(a.get("tested")) for a in assets
        )
    except Exception as e:
        print(f"[ASSET_AGENT] tested-asset check failed: {e}", flush=True)
        return False


def _inject_curated_hero(manifest: dict, resolved_assets: dict) -> None:
    """
    Look up the scene plan's subject in the curated catalog. On a strong
    match, drop the record into the appropriate bucket so the fetcher's
    subject-match gate treats it as already-solved.

    Round 13: the match MUST be marked ``tested: true``. Without that
    flag the catalog is just a list of random Sketchfab downloads that
    happen to live on disk — injecting them degrades quality rather than
    improving it.
    """
    # ── forced_hero_id short-circuit ──────────────────────────────────
    # When the Asset Picker UI forced a specific library entry, the
    # library override has already bulldozed the bucket with the user's
    # pick.  The curated injector must NOT run — otherwise it'd stuff
    # a matching-subject catalog record into the same bucket and win
    # the "pick bucket[0]" race downstream.  See round 10 bug report.
    _forced = str(manifest.get("forced_hero_id") or "").strip()
    if _forced:
        print(
            f"[ASSET_AGENT] curated injector SKIPPED — "
            f"forced_hero_id={_forced!r} is active",
            flush=True,
        )
        return
    if not _HAS_CURATED:
        return
    if not _has_tested_assets():
        print("[ASSET_AGENT] no tested assets in catalog — curated injection disabled", flush=True)
        return
    try:
        record, score = resolve_hero_from_catalog(manifest)
    except Exception as e:
        print(f"[ASSET_AGENT] curated hero lookup failed: {e}", flush=True)
        return
    if not record:
        return
    # Require the underlying catalog entry to be tested.
    curated_meta = record.get("curated_meta") or {}
    if not bool(curated_meta.get("tested")):
        print(
            f"[ASSET_AGENT] curated match {record.get('id')!r} is not marked "
            f"tested — skipping injection (score={score})",
            flush=True,
        )
        return

    models = resolved_assets.setdefault("models", {
        "buildings": [], "characters": [], "cars": [], "vehicles": [],
        "environments": [], "props": [], "products": [], "signs": [],
    })
    # If a hero is already present, prefer curated by replacing the first
    # entry in the matching bucket — curated wins by design in Round 11.
    t = str(record.get("type") or "prop").lower()
    target_bucket = {
        "animal": "characters",
        "character": "characters",
        "vehicle": "vehicles",
        "environment": "environments",
        "prop": "props",
    }.get(t, "props")
    bucket = models.setdefault(target_bucket, [])
    # De-dupe by path so retries don't pile on.
    existing_paths = {str(m.get("path") or "") for m in bucket if isinstance(m, dict)}
    if record.get("path") and str(record["path"]) in existing_paths:
        return
    bucket.insert(0, record)
    print(
        f"[ASSET_AGENT] CURATED HERO injected -> {record.get('id')!r} "
        f"(bucket={target_bucket}, score={score})",
        flush=True,
    )


def _inject_curated_fallback(manifest: dict, final_assets: dict) -> None:
    """
    Last-ditch hero: if Sketchfab also failed, return the closest curated
    asset. Only fires when no hero is present in any hero-eligible bucket
    AND the catalog has tested assets.
    """
    # forced_hero_id short-circuit — user already picked an asset; do
    # not substitute a curated catalog entry as a "fallback".
    _forced = str(manifest.get("forced_hero_id") or "").strip()
    if _forced:
        print(
            f"[ASSET_AGENT] curated fallback SKIPPED — "
            f"forced_hero_id={_forced!r} is active",
            flush=True,
        )
        return
    if not _HAS_CURATED:
        return
    if not _has_tested_assets():
        return
    models = final_assets.get("models") or {}
    if _has_hero_in_buckets(models):
        return

    scene_plan = manifest.get("scene_plan") or {}
    subject = str(
        scene_plan.get("focal_subject")
        or scene_plan.get("subject")
        or manifest.get("topic")
        or ""
    ).strip()
    if not subject:
        return

    asset_type_hint = None
    for key in ("hero_asset_type", "asset_type"):
        v = manifest.get(key)
        if isinstance(v, str) and v.strip():
            asset_type_hint = v
            break

    try:
        match = find_closest_curated_asset(subject, asset_type=asset_type_hint)
    except Exception as e:
        print(f"[ASSET_AGENT] curated fallback failed: {e}", flush=True)
        return
    if not match:
        return
    # Round 13: only fall back to tested catalog entries.
    if not bool(match.get("tested")):
        print(
            f"[ASSET_AGENT] fallback candidate {match.get('id')!r} not tested — "
            f"letting template keep its default",
            flush=True,
        )
        return

    try:
        from .curated_resolver import asset_to_resolver_record
        record = asset_to_resolver_record(match)
    except Exception as e:
        print(f"[ASSET_AGENT] curated fallback adapter failed: {e}", flush=True)
        return
    if not record:
        return

    target_bucket = {
        "animal": "characters",
        "character": "characters",
        "vehicle": "vehicles",
        "environment": "environments",
        "prop": "props",
    }.get(str(record.get("type") or "prop").lower(), "props")
    bucket = final_assets["models"].setdefault(target_bucket, [])
    bucket.insert(0, record)
    print(
        f"[ASSET_AGENT] CURATED FALLBACK injected -> {record.get('id')!r} "
        f"(bucket={target_bucket}) [Sketchfab had no usable hero]",
        flush=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Subject accuracy gate
# ═══════════════════════════════════════════════════════════════════════════

_HERO_GATE_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "at", "and", "or", "with", "to",
    "3d", "model", "low", "high", "poly", "realistic", "cartoon", "free",
    "download", "scene", "asset", "render",
}

# Brand + model tokens for specific-subject detection.  When a subject
# contains BOTH a brand AND a model/variant token, we require both to
# appear in the asset's name/tags — otherwise we risk "Porsche 911" →
# "Porsche Cayenne" acceptance.
_HERO_GATE_BRAND_TOKENS = {
    "porsche", "ferrari", "bmw", "toyota", "ford", "chevrolet", "chevy",
    "mercedes", "audi", "lamborghini", "lambo", "bugatti", "mclaren",
    "aston", "martin", "nissan", "honda", "mazda", "subaru", "lotus",
    "tesla", "dodge", "chrysler", "kia", "hyundai", "volkswagen", "vw",
    "jaguar", "bentley", "rolls", "royce", "koenigsegg", "pagani",
}

_HERO_GATE_MODEL_INDICATORS = {
    "911", "718", "gt3", "gt", "rs", "m3", "m4", "m5", "m8",
    "camry", "corolla", "supra", "miata", "civic", "accord", "integra",
    "mustang", "corvette", "camaro", "challenger", "charger", "f150",
    "huracan", "aventador", "murcielago", "diablo", "countach",
    "chiron", "veyron", "divo",
    "720s", "570s", "p1", "senna", "artura",
    "db11", "vantage", "dbs", "valkyrie",
    "model", "cayman", "taycan", "panamera", "cayenne", "macan",
    "f40", "f50", "enzo", "laferrari", "488", "812",
}


def _is_specific_subject(subject: str) -> bool:
    """Does this subject request specify both a brand and a model/variant?

    "porsche 911"  → True  (brand=porsche + model=911)
    "toyota supra" → True  (brand=toyota + model=supra)
    "cat"          → False (single-token generic)
    "orange cat"   → False (no brand/model — visual hints handle it)
    "911"          → False (no brand present)
    """
    if not subject:
        return False
    tokens = (subject or "").lower().split()
    if len(tokens) < 2:
        return False
    has_brand = any(t in _HERO_GATE_BRAND_TOKENS for t in tokens)
    has_model = any(
        t in _HERO_GATE_MODEL_INDICATORS or t.isdigit() for t in tokens
    )
    return has_brand and has_model


_HERO_GATE_SYNONYMS = {
    "elephant":  ["pachyderm"],
    "hippo":     ["hippopotamus"],
    "cat":       ["kitten", "feline"],
    "dog":       ["puppy", "canine", "hound"],
    "car":       ["automobile", "vehicle", "sedan", "coupe"],
    "racecar":   ["race car", "formula", "f1", "racing car"],
    "porsche":   ["911", "carrera", "cayman", "taycan"],
    "ferrari":   ["f40", "f50", "enzo"],
    "eagle":     ["raptor", "bird of prey"],
    "pelican":   ["seabird"],
    "tiger":     ["big cat"],
    "lion":      ["big cat"],
    "cheetah":   ["big cat"],
    "dinosaur":  ["trex", "t-rex", "rex", "raptor", "sauropod"],
    "polar bear": ["polar", "bear"],
    "bear":      ["grizzly"],
    "wolf":      ["timber wolf"],
    "horse":     ["stallion", "mare", "equine"],
    "robot":     ["droid", "android", "mech"],
}


def _verify_hero_matches_subject(
    hero_asset_path: str,
    subject: str,
    hero_metadata: dict,
) -> tuple[bool, str]:
    """Final check: does this asset actually match the requested subject?

    Returns (matched, reason).  Failures should trigger fallback, not error.
    Checks, in order:
        1. Subject string appears in asset name or curated subject field
        2. Subject tokens intersect asset tags
        3. Subject tokens intersect asset name tokens (with stopword filter)
        4. Synonym map match on asset name or tags
    """
    if not hero_asset_path or not subject:
        return False, "no_subject_or_path"

    s_norm = (subject or "").lower().strip()
    if not s_norm:
        return False, "empty_subject"
    s_tokens = {t for t in s_norm.split() if t not in _HERO_GATE_STOPWORDS}
    if not s_tokens:
        s_tokens = {s_norm}

    md = hero_metadata or {}
    name = str(md.get("name") or md.get("id") or "").lower()
    curated_subject = str(md.get("subject") or "").lower()
    tags = {str(t).lower() for t in (md.get("tags") or [])}
    # Also include the filename's base stem as a weak name signal
    try:
        import os as _os_g
        stem = _os_g.path.splitext(_os_g.path.basename(hero_asset_path))[0].lower()
        if stem:
            name = name + " " + stem
    except Exception:
        pass

    # ── STRICT PATH for brand+model specific subjects ────────────────
    # "porsche 911" must match BOTH tokens.  Prevents Cayenne/Cayman from
    # being accepted as a 911 via brand-token intersection alone.
    if _is_specific_subject(subject):
        haystack = f"{name} {' '.join(tags)} {curated_subject}".lower()
        all_subject_tokens = set((subject or "").lower().split())
        matched = {t for t in all_subject_tokens if t in haystack}
        brand_hit = any(
            t in _HERO_GATE_BRAND_TOKENS and t in matched
            for t in all_subject_tokens
        )
        model_hit = any(
            (t in _HERO_GATE_MODEL_INDICATORS or t.isdigit()) and t in matched
            for t in all_subject_tokens
        )
        if brand_hit and model_hit:
            return True, (
                f"specific_subject_match matched={sorted(matched)}"
            )
        return False, (
            f"specific_subject_needs_brand_and_model "
            f"matched={sorted(matched)} "
            f"brand_hit={brand_hit} model_hit={model_hit}"
        )

    # 1. Direct substring in asset name or curated subject
    if s_norm in name or s_norm in curated_subject:
        return True, f"subject_in_name ('{s_norm}' in asset)"

    # 2. Tag intersection with any subject token
    tag_hits = s_tokens & tags
    if tag_hits:
        return True, f"tag_intersect {sorted(tag_hits)}"

    # 3. Name-token intersection (filter stopwords)
    name_tokens = set(
        t for t in name.replace("_", " ").replace("-", " ").split()
        if t and t not in _HERO_GATE_STOPWORDS
    )
    name_hits = s_tokens & name_tokens
    if name_hits:
        return True, f"name_token_intersect {sorted(name_hits)}"

    # 4. Synonym map
    for key, synonyms in _HERO_GATE_SYNONYMS.items():
        if key in s_norm or key in s_tokens:
            for syn in synonyms:
                syn_l = syn.lower()
                if syn_l in name or syn_l in tags or any(
                    syn_l == t for t in tags
                ):
                    return True, f"synonym_match {key}->{syn_l}"

    return False, (
        f"no_match subject={s_norm!r} "
        f"asset_name={name[:60]!r} "
        f"tags={sorted(tags)[:5]}"
    )


def _build_query_variations(subject: str) -> list:
    """Generate query phrasings to try when the base query fails.

    Used by both Objaverse retry (Tier 2) and Sketchfab multi-query (Tier 3).
    Returns a deduplicated list ordered from most-specific to most-generic.
    """
    if not subject:
        return []
    s_lower = subject.lower().strip()
    variations: list = [s_lower]
    tokens = s_lower.split()

    # Synonym expansion from the gate's synonym map
    for key, syns in _HERO_GATE_SYNONYMS.items():
        if key in s_lower or key in tokens:
            for syn in syns:
                variations.append(str(syn).lower())

    # Single-token fallbacks for multi-token subjects
    if len(tokens) > 1:
        for t in tokens:
            if t not in _HERO_GATE_STOPWORDS and len(t) > 2:
                variations.append(t)

    # Category broadening
    if any(t in _HERO_GATE_BRAND_TOKENS for t in tokens):
        variations.extend(["sports car", "luxury car"])
    if any(t in {"elephant", "hippo", "rhino"} for t in tokens):
        variations.append("large mammal")
    if any(t in {"eagle", "hawk", "falcon", "owl"} for t in tokens):
        variations.extend(["bird of prey", "raptor"])
    if any(t in {"lion", "tiger", "leopard", "cheetah"} for t in tokens):
        variations.append("big cat")

    # Deduplicate while preserving order
    seen: set = set()
    out: list = []
    for v in variations:
        vl = (v or "").strip().lower()
        if vl and vl not in seen:
            seen.add(vl)
            out.append(vl)
    return out


# Category → curated_key mapping for Tier 4 fallback.  Each key maps to
# the *best* generic curated asset we have on disk for that category.
# Values are curated keys lookupable from app/data/curated_assets.json.
_CATEGORY_FALLBACK_MAP: dict = {
    "vehicle":   "ferrari",   # known-good in curated catalog
    "car":       "ferrari",
    "animal":    None,        # no generic animal curated; fall through
    "character": None,
    "bird":      None,
    "mammal":    None,
}


def _infer_category(subject: str) -> str:
    """Best-effort category inference for Tier 4 fallback."""
    if not subject:
        return ""
    s = subject.lower()
    # Vehicles
    if any(t in s for t in (
        "car", "truck", "vehicle", "motorcycle", "porsche", "ferrari",
        "bmw", "mustang", "audi", "lamborghini", "tesla", "toyota",
    )):
        return "vehicle"
    # Animals / birds / mammals
    _ANIMAL_WORDS = (
        "cat", "dog", "horse", "elephant", "lion", "tiger", "bear",
        "wolf", "fox", "deer", "pig", "cow", "sheep", "goat",
        "monkey", "gorilla", "rabbit", "mouse", "rat",
    )
    _BIRD_WORDS = ("eagle", "hawk", "falcon", "owl", "pelican", "parrot", "bird")
    if any(w in s for w in _ANIMAL_WORDS):
        return "animal"
    if any(w in s for w in _BIRD_WORDS):
        return "bird"
    if "robot" in s or "knight" in s or "character" in s:
        return "character"
    return ""


def _find_category_compatible_curated(category: str) -> dict | None:
    """Tier 4 — return a curated-catalog entry for the given category,
    or None if no compatible fallback exists."""
    if not category:
        return None
    key = _CATEGORY_FALLBACK_MAP.get(category)
    if not key:
        return None
    # The existing curated catalog is keyword-indexed.  Try to resolve
    # the key into a real asset path via curated_resolver.
    try:
        from .curated_resolver import resolve_hero_from_catalog
        record = resolve_hero_from_catalog(key)
        if record and record.get("path"):
            return {
                "id":     f"curated_fallback_{category}",
                "path":   str(record.get("path")),
                "name":   str(record.get("name") or key),
                "type":   category,
                "subject": key,
                "tags":   [category, key],
                "source": "curated",
                "score":  50,
            }
    except Exception as _e:
        print(f"[HERO_RESOLVE] category fallback lookup failed: {_e}", flush=True)
    return None


def resolve_hero_with_retry(
    subject: str,
    visual_hints: list | None = None,
    manifest: dict | None = None,
) -> tuple:
    """Multi-tier hero resolution with retry orchestration.

    Returns (chosen_dict, reason_string).  chosen_dict is None only on
    Tier 5 failure.  The caller is responsible for writing the chosen
    dict's path/type/metadata into the manifest.

    Tier 0: query_library (prefer tested + visual-hint-matched)
    Tier 1: Objaverse with original subject
    Tier 2: Objaverse with query variations (synonyms + tokens + broadening)
    Tier 3: Sketchfab multi-query via search_with_fallback_queries
    Tier 4: Category-compatible curated fallback
    Tier 5: FAIL with clear message
    """
    tier_log: list = []
    pool: list = []
    manifest = manifest or {}
    visual_hints = visual_hints or []

    # ── Tier 0: library-first ─────────────────────────────────────────
    try:
        from .library_curator import query_library
        lib_matches = query_library(subject, visual_hints=visual_hints, limit=10)
    except Exception as _le:
        print(f"[HERO_RESOLVE] library query failed: {_le}", flush=True)
        lib_matches = []
    lib_accepted = 0
    import os as _os_r
    for m in lib_matches:
        try:
            mp = str(m.get("path") or "")
            if not mp or not _os_r.path.exists(mp):
                continue
            ok, _rz = _verify_hero_matches_subject(mp, subject, m)
            if ok:
                pool.append(m)
                lib_accepted += 1
        except Exception:
            continue
    tier_log.append(
        f"tier0_library: {lib_accepted} accepted from "
        f"{len(lib_matches)} library matches"
    )
    print(f"[HERO_RESOLVE] {tier_log[-1]}", flush=True)
    if len(pool) >= 3:
        from .variant_pool import pick_with_diversity
        chosen = pick_with_diversity(subject, pool)
        return chosen, f"library_sufficient ({tier_log[-1]})"

    # ── Tier 1: Objaverse with original subject ──────────────────────
    try:
        from . import objaverse_fetcher as _obv
        _obv_results = _obv.search_objaverse(subject, max_results=20) if hasattr(_obv, "search_objaverse") else []
    except Exception as _oe:
        print(f"[HERO_RESOLVE] objaverse search failed: {_oe}", flush=True)
        _obv_results = []
    obv_accepted = 0
    for c in _obv_results:
        try:
            # objaverse search_objaverse returns uid + name; no path yet
            meta = {
                "name":   c.get("name", ""),
                "tags":   c.get("tags", []) or [],
                "subject": subject,
                "uid":    c.get("uid"),
            }
            fake_path = str(c.get("uid") or c.get("name") or "")
            ok, _rz = _verify_hero_matches_subject(fake_path, subject, meta)
            if ok:
                pool.append({
                    "id":     c.get("uid"),
                    "uid":    c.get("uid"),
                    "name":   c.get("name"),
                    "score":  c.get("score", 0),
                    "source": "objaverse",
                    "tags":   c.get("tags", []),
                })
                obv_accepted += 1
        except Exception:
            continue
    tier_log.append(
        f"tier1_objaverse_original: {obv_accepted} accepted from {len(_obv_results)}"
    )
    print(f"[HERO_RESOLVE] {tier_log[-1]}", flush=True)
    if len(pool) >= 3:
        from .variant_pool import pick_with_diversity
        chosen = pick_with_diversity(subject, pool)
        return chosen, f"objaverse_original_sufficient ({'; '.join(tier_log)})"

    # ── Tier 2: Objaverse with query variations ──────────────────────
    variations = _build_query_variations(subject)
    for variation in variations:
        if variation == subject.lower().strip():
            continue  # already covered in Tier 1
        try:
            from . import objaverse_fetcher as _obv2
            v_results = _obv2.search_objaverse(variation, max_results=10) if hasattr(_obv2, "search_objaverse") else []
        except Exception:
            v_results = []
        v_accepted = 0
        for c in v_results:
            meta = {
                "name": c.get("name", ""),
                "tags": c.get("tags", []) or [],
                "subject": subject,
                "uid": c.get("uid"),
            }
            fake_path = str(c.get("uid") or c.get("name") or "")
            # Gate against ORIGINAL subject, not variation
            ok, _rz = _verify_hero_matches_subject(fake_path, subject, meta)
            if ok:
                pool.append({
                    "id":     c.get("uid"),
                    "uid":    c.get("uid"),
                    "name":   c.get("name"),
                    "score":  c.get("score", 0),
                    "source": "objaverse",
                    "tags":   c.get("tags", []),
                })
                v_accepted += 1
        tier_log.append(
            f"tier2_objaverse_variation[{variation!r}]: "
            f"{v_accepted} accepted from {len(v_results)}"
        )
        print(f"[HERO_RESOLVE] {tier_log[-1]}", flush=True)
        if len(pool) >= 3:
            break

    if len(pool) >= 3:
        from .variant_pool import pick_with_diversity
        chosen = pick_with_diversity(subject, pool)
        return chosen, f"objaverse_variations_sufficient ({'; '.join(tier_log)})"

    # ── Tier 3: Sketchfab multi-query ────────────────────────────────
    try:
        from . import sketchfab_fetcher as _sf
        sf_results = _sf.search_with_fallback_queries(
            subject,
            variations,
            top_n=5,
        ) if hasattr(_sf, "search_with_fallback_queries") else []
    except Exception as _se:
        print(f"[HERO_RESOLVE] sketchfab multi-query failed: {_se}", flush=True)
        sf_results = []
    sf_accepted = 0
    for c in sf_results:
        meta = {
            "name":   c.get("name", ""),
            "tags":   c.get("tags", []) or [],
            "subject": subject,
            "uid":    c.get("uid"),
        }
        fake_path = str(c.get("uid") or c.get("name") or "")
        ok, _rz = _verify_hero_matches_subject(fake_path, subject, meta)
        if ok:
            pool.append({
                "id":     c.get("uid"),
                "uid":    c.get("uid"),
                "name":   c.get("name"),
                "score":  c.get("score", 0),
                "source": "sketchfab",
                "tags":   c.get("tags", []),
            })
            sf_accepted += 1
    tier_log.append(
        f"tier3_sketchfab_multi: {sf_accepted} accepted from {len(sf_results)}"
    )
    print(f"[HERO_RESOLVE] {tier_log[-1]}", flush=True)

    if len(pool) >= 1:
        from .variant_pool import pick_with_diversity
        chosen = pick_with_diversity(subject, pool)
        return chosen, (
            f"succeeded_with_pool_size={len(pool)} ({'; '.join(tier_log)})"
        )

    # ── Tier 4: Category-compatible curated fallback ─────────────────
    category = _infer_category(subject)
    fb = _find_category_compatible_curated(category)
    if fb:
        tier_log.append(
            f"tier4_category_fallback: using {fb.get('id')!r} for category={category!r}"
        )
        print(f"[HERO_RESOLVE] {tier_log[-1]}", flush=True)
        return fb, f"category_fallback ({'; '.join(tier_log)})"

    # ── Tier 5: absolute failure ─────────────────────────────────────
    tier_log.append("tier5_exhausted: no library / objaverse / sketchfab / category fallback matched")
    print(
        f"[HERO_RESOLVE] FAILED subject={subject!r} ({'; '.join(tier_log)})",
        flush=True,
    )
    return None, f"exhausted_all_tiers ({'; '.join(tier_log)})"


def _extract_hero_metadata(manifest: dict, final_assets: dict) -> None:
    """
    Populate manifest with hero_asset_* fields that templates,
    animation, and camera systems use for adaptive behavior.

    IMPORTANT: the hero is the CHARACTER / VEHICLE / PROP the viewer is
    meant to watch. Environments are backgrounds — never treat them as
    the hero, even if they're the only model that got downloaded. When
    no real hero exists, leave the hero fields unset so the template
    falls back to its default behaviour instead of orbiting a landscape
    and calling it a star.
    """
    models = final_assets.get("models") or {}
    hero = None

    # ── forced_hero_id short-circuit ──────────────────────────────────
    # If the user picked an asset in the Asset Picker UI, the library
    # bucket has already been bulldozed with that pick by
    # _inject_library_hero_into_resolved.  Skip all the override logic
    # (vehicle synonyms, Objaverse priorities, word-boundary matches)
    # which would otherwise replace the user's pick.  Go straight to
    # the bucket-priority fallback which will grab the forced pick as
    # the first item.
    _forced_id_guard = str(manifest.get("forced_hero_id") or "").strip()
    if _forced_id_guard:
        print(
            f"[ASSET_AGENT] forced_hero_id={_forced_id_guard!r} — "
            f"skipping override logic, using bucket pick directly",
            flush=True,
        )

    # ── Vehicle keyword protection ─────────────────────────────────────
    # Generic vehicle prompts ("sportscar driving at night") MUST use the
    # curated local vehicle instead of an Objaverse model that's likely
    # upside-down or wrong-scale. This check runs BEFORE any Objaverse
    # override so the local Ferrari always wins for car prompts.
    _VEHICLE_SYNONYMS = (
        "car", "sportscar", "sports car", "supercar", "sedan", "coupe",
        "convertible", "racing car", "race car", "racecar", "luxury car",
        "exotic car", "automobile", "vehicle", "sports vehicle",
        "roadster", "hypercar",
        "ferrari", "lamborghini", "porsche", "bmw", "audi", "mustang",
        "corvette", "tesla",
    )
    _sp = manifest.get("scene_plan") or {}
    _subject_raw = str(
        _sp.get("focal_subject") or _sp.get("subject") or ""
    ).strip().lower()

    if not _forced_id_guard and any(kw in _subject_raw for kw in _VEHICLE_SYNONYMS):
        _local_vehicles = []
        if isinstance(models, dict):
            _local_vehicles = (models.get("vehicles") or []) + (models.get("cars") or [])
        if _local_vehicles:
            hero = _local_vehicles[0]
            print(
                f"[ASSET_AGENT] vehicle synonym {_subject_raw!r} -> forcing "
                f"local vehicle {hero.get('name', hero.get('id', ''))!r}",
                flush=True,
            )
            # Spec-format fallback line so tests can verify this path fired
            print(
                f"[ASSET_AGENT] vehicle fallback {_subject_raw!r} -> "
                f"forcing local vehicle "
                f"{hero.get('name', hero.get('id', ''))!r}",
                flush=True,
            )
            # Clear OTHER vehicles from resolved to prevent double-import.
            # The forced hero will be set as hero_asset_path downstream;
            # any other vehicles in the bucket would cause overlays.
            if isinstance(models, dict):
                _hero_path = hero.get("path") or hero.get("file") or ""
                for _bk in ("vehicles", "cars"):
                    _bk_list = models.get(_bk)
                    if isinstance(_bk_list, list) and len(_bk_list) > 1:
                        models[_bk] = [
                            v for v in _bk_list
                            if (v.get("path") or v.get("file") or "") == _hero_path
                        ] or [hero]
                        print(
                            f"[ASSET_AGENT] cleared non-hero vehicles from {_bk} "
                            f"(was {len(_bk_list)}, now {len(models[_bk])})",
                            flush=True,
                        )

    # ── Subject-match override ─────────────────────────────────────────
    # When the Objaverse or Sketchfab fetcher found a model whose name
    # matches the user's subject (e.g. "tulip"), but it got bucketed as
    # "props" while a BMW from the local registry landed in "vehicles",
    # the old bucket-priority order would pick the BMW as hero.

    # Priority 0: check the fetch report for a hero_model_objaverse.
    # This is the model the Objaverse fetcher found specifically for the
    # user's subject. If it exists in any bucket, use it immediately.
    # SKIP if hero already set by vehicle keyword protection above.
    _fetch_report = manifest.get("fetch_report") or {}
    _has_objaverse_hero = False
    for _fr in (_fetch_report.get("fetched") or []):
        if isinstance(_fr, dict) and _fr.get("role") == "hero_model_objaverse":
            _has_objaverse_hero = True
            break

    if (not _forced_id_guard) and hero is None and _has_objaverse_hero and isinstance(models, dict):
        for bucket in ("characters", "vehicles", "cars", "products", "props"):
            for item in (models.get(bucket) or []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("source") or "").lower() == "objaverse":
                    hero = item
                    print(
                        f"[ASSET_AGENT] hero override: Objaverse hero "
                        f"{item.get('name', '?')!r} in {bucket} "
                        f"(Objaverse fetched it for the user's subject)",
                        flush=True,
                    )
                    break
            if hero is not None:
                break

    # Priority 1: word-boundary match between subject words and model
    # names. Extracts individual words from focal_subject / topic so
    # "close up of a tulip" matches a model named "Tulip" via the word
    # "tulip", even when focal_subject is wrong (e.g. "close").
    if (not _forced_id_guard) and hero is None:
        import re as _re
        _STOP_WORDS = {"a", "an", "the", "of", "in", "on", "at", "up",
                        "to", "for", "and", "or", "is", "with", "from",
                        "by", "close", "shot", "scene", "over", "through"}
        _subject_sources = [
            (manifest.get("scene_plan") or {}).get("focal_subject"),
            (manifest.get("scene_plan") or {}).get("subject"),
            manifest.get("topic"),
        ]
        _subject_words: list[str] = []
        for _src in _subject_sources:
            if _src:
                _subject_words.extend(
                    w for w in str(_src).lower().split()
                    if w not in _STOP_WORDS and len(w) > 2
                )
        _seen_w: set[str] = set()
        _unique_words: list[str] = []
        for _w in _subject_words:
            if _w not in _seen_w:
                _seen_w.add(_w)
                _unique_words.append(_w)

        if _unique_words and isinstance(models, dict):
            for _word in _unique_words:
                for bucket in ("characters", "vehicles", "cars", "products", "props"):
                    for item in (models.get(bucket) or []):
                        if not isinstance(item, dict):
                            continue
                        _item_name = str(item.get("name") or "").lower()
                        if _re.search(
                            r"\b" + _re.escape(_word) + r"\b", _item_name
                        ):
                            hero = item
                            print(
                                f"[ASSET_AGENT] hero override: word "
                                f"{_word!r} matched model {_item_name!r} "
                                f"in {bucket} (bypassing bucket priority)",
                                flush=True,
                            )
                            break
                    if hero is not None:
                        break
                if hero is not None:
                    break

    # Fallback: bucket priority (characters > vehicles > cars > products > props).
    # ENVIRONMENTS are intentionally excluded — they are backdrops.
    if hero is None and isinstance(models, dict):
        for bucket in ("characters", "vehicles", "cars", "products", "props"):
            items = models.get(bucket) or []
            if items:
                hero = items[0]
                break
    elif hero is None and isinstance(models, list) and models:
        # Flat list: pick the first non-environment record.
        for item in models:
            if isinstance(item, dict) and str(item.get("type", "")).lower() != "environment":
                hero = item
                break

    # Always seed action from the scene plan, hero or not.
    sp = manifest.get("scene_plan") or {}
    manifest.setdefault("action", sp.get("animation_mode") or "idle")

    if hero is None:
        available = list(models.keys()) if isinstance(models, dict) else type(models).__name__
        print(
            f"[ASSET_AGENT] WARNING: no hero model found in character/vehicle/"
            f"product/prop buckets (available: {available}). "
            f"Template will use its default asset.",
            flush=True,
        )
        manifest["hero_asset_path"] = None
        manifest["hero_asset_type"] = None
        manifest["hero_has_armature"] = False
        manifest["hero_has_animations"] = False
        manifest["hero_scale_class"] = None
        manifest["hero_species"] = None
        return

    # ── Animal type override ──────────────────────────────────────────
    # Objaverse models often lack semantic tags, so animals get bucketed
    # as "props" with prop-sized scaling (0.8m). Check if the subject is
    # a known animal and force the type so downstream sizing is correct.
    _ANIMAL_WORDS = (
        "dog", "cat", "horse", "eagle", "dolphin", "whale", "shark",
        "lion", "tiger", "bear", "wolf", "fox", "deer", "elephant",
        "giraffe", "zebra", "monkey", "gorilla", "cheetah", "leopard",
        "panther", "jaguar", "bird", "hawk", "owl", "parrot", "penguin",
        "pelican", "flamingo", "snake", "lizard", "crocodile", "turtle",
        "frog", "fish", "octopus", "butterfly", "bee", "ant", "spider",
        "dinosaur", "dragon", "unicorn", "phoenix", "rabbit", "hamster",
        "mouse", "rat", "squirrel", "koala", "panda", "rhino", "hippo",
        "cow", "pig", "sheep", "goat", "chicken", "duck", "goose",
        "crab", "lobster", "jellyfish", "stingray", "buffalo", "moose",
        "caribou", "antelope", "gazelle", "chimpanzee", "orangutan",
        "pterodactyl", "trex", "t-rex", "raptor", "brontosaurus",
        "stegosaurus", "mammoth", "saber tooth", "husky",
        "german shepherd", "golden retriever", "poodle", "bulldog",
    )
    _hero_type = str(hero.get("type") or "prop").lower()
    if _hero_type not in ("animal", "character") and _subject_raw:
        if any(animal in _subject_raw for animal in _ANIMAL_WORDS):
            _old_type = hero.get("type", "prop")
            hero["type"] = "animal"
            print(
                f"[ASSET_AGENT] type override: {_subject_raw!r} is an animal "
                f"(was {_old_type!r})",
                flush=True,
            )

    import os as _os_hero
    _raw_hero_path = str(hero.get("path") or hero.get("file") or "").strip()
    if _raw_hero_path and not _os_hero.path.isabs(_raw_hero_path):
        _raw_hero_path = _os_hero.path.abspath(_raw_hero_path)

    # ── Subject accuracy hard gate ────────────────────────────────────
    # The hero must actually match the requested subject.  If it doesn't,
    # we log the mismatch loudly and attempt a library-first fallback
    # before accepting.  A hero that doesn't match the subject is a
    # worse UX than no hero at all — better to fall back to a known-good
    # asset from the curated library than to ship "elephant" and render
    # a prop tree.
    try:
        _gate_ok, _gate_reason = _verify_hero_matches_subject(
            _raw_hero_path, _subject_raw, hero,
        )
        if _gate_ok:
            print(
                f"[HERO_GATE] accepted path={_raw_hero_path!r} "
                f"subject={_subject_raw!r} reason={_gate_reason}",
                flush=True,
            )
        else:
            print(
                f"[HERO_GATE] REJECTED path={_raw_hero_path!r} "
                f"subject={_subject_raw!r} reason={_gate_reason}",
                flush=True,
            )
            # Multi-tier retry orchestration — try library, Objaverse
            # variations, Sketchfab multi-query, category fallback before
            # accepting a mismatched hero.
            try:
                from .library_curator import extract_visual_hints
                _hints = extract_visual_hints(
                    str(manifest.get("topic", ""))
                    + " " + str(manifest.get("core_objective_prompt", ""))
                )
                print(
                    f"[HERO_RESOLVE] subject={_subject_raw!r} starting multi-tier retry "
                    f"(visual_hints={_hints})",
                    flush=True,
                )
                _chosen, _reason = resolve_hero_with_retry(
                    _subject_raw, visual_hints=_hints, manifest=manifest,
                )
                if _chosen is not None:
                    _new_path = str(_chosen.get("path") or "")
                    # For Objaverse/Sketchfab, the dict may have uid but no
                    # downloaded path — we only swap to filesystem-ready paths.
                    if _new_path and _os_hero.path.exists(_new_path):
                        print(
                            f"[HERO_RESOLVE] accepted id={_chosen.get('id')!r} "
                            f"path={_new_path!r} source={_chosen.get('source')} "
                            f"reason={_reason}",
                            flush=True,
                        )
                        _raw_hero_path = _new_path
                        hero["path"] = _new_path
                        hero["type"] = _chosen.get("type", hero.get("type", "prop"))
                        hero["subject"] = _chosen.get("subject", _subject_raw)
                        hero["source"] = _chosen.get("source", hero.get("source"))
                    else:
                        # Tier 1-3 returned a candidate without a downloaded
                        # path — the calling site hasn't implemented live
                        # download from uid yet.  Log the hit so we can see
                        # what the retry would have picked, but fall through
                        # to accepting the original mismatched hero for now.
                        print(
                            f"[HERO_RESOLVE] tier-match found but not downloaded "
                            f"(uid={_chosen.get('uid')!r} source={_chosen.get('source')}) "
                            f"— accepting original mismatched hero as fallback; "
                            f"live download-on-retry not yet wired",
                            flush=True,
                        )
                else:
                    print(
                        f"[HERO_RESOLVE] FAILED — no tier produced a match; "
                        f"reason={_reason}",
                        flush=True,
                    )
            except Exception as _retry_err:
                print(f"[HERO_RESOLVE] orchestration failed: {_retry_err}", flush=True)
    except Exception as _gate_err:
        print(f"[HERO_GATE] gate check failed (non-fatal): {_gate_err}", flush=True)

    manifest["hero_asset_path"] = _raw_hero_path
    manifest["hero_asset_type"] = hero.get("type", "prop")
    # Stash rich fetch metadata on the manifest so the post-render hook
    # can populate library.json's visual_descriptors / tags correctly.
    try:
        manifest["hero_fetch_metadata"] = {
            "name":        hero.get("name") or "",
            "description": hero.get("description") or "",
            "tags":        list(hero.get("tags") or []),
            "uid":         hero.get("uid") or hero.get("source_uid"),
            "source":      hero.get("source") or "",
            "score":       hero.get("score"),
            "url":         hero.get("url"),
            "license":     hero.get("license"),
        }
    except Exception:
        pass
    manifest["hero_has_armature"] = bool(hero.get("is_rigged", False))
    manifest["hero_has_animations"] = bool(hero.get("has_animation", False))
    manifest["hero_scale_class"] = hero.get("scale_class", "medium")
    manifest["hero_species"] = hero.get("species")
    # Blender-side fallback candidates — if the primary hero fails mesh
    # validation (flat card, placeholder), render_from_manifest iterates these.
    manifest["hero_candidates"] = hero.get("hero_candidates") or []

    print(
        f"[ASSET_AGENT] hero: path={manifest['hero_asset_path']} "
        f"type={manifest['hero_asset_type']} "
        f"armature={manifest['hero_has_armature']} "
        f"animated={manifest['hero_has_animations']} "
        f"action={manifest.get('action')}",
        flush=True,
    )
