# Manifest Schema (canonical reference)

This document describes every field the pipeline reads/writes on the
render manifest dict.  Generated after 8 rounds of surgical edits —
before this, the schema was implicit.

## Required fields (user-supplied)

| Field | Type | Populated by | Description |
|---|---|---|---|
| `project_name` | str | API request | Directory name under `outputs/` |
| `topic` | str | API request | User's free-form prompt ("Ferrari racing at sunset") |
| `render_tier` | str | API request | `preview` / `fast` / `standard` / `cinematic` |
| `template_name` | str | API → `resolve_template_name` | `car_hero`, `character_stage`, etc. |

## Populated during `asset_agent.enrich_manifest_with_assets`

| Field | Type | Description |
|---|---|---|
| `scene_plan` | dict | Semantic scene plan from `prompt_scene_planner` |
| `scene_params` | dict | Legacy camera/lighting hints |
| `animation_instructions` | dict | From `animation_instruction_builder` |
| `directorial_manifest` | dict | AI director output (optional) |
| `directorial_controls` | dict | Projected onto legacy motion_style/camera_style |
| `environment_ground_type` | str | From `determine_ground_type` |
| `resolved_assets` | dict | Bucketed models + hdris + textures |
| `fetch_report` | dict | Sketchfab/Objaverse fetcher telemetry |
| `hero_asset_path` | str (abs) | Absolute path to hero file |
| `hero_asset_type` | str | `animal`, `vehicle`, `character`, `prop` |
| `hero_has_armature` | bool | |
| `hero_has_animations` | bool | |
| `hero_scale_class` | str | `small`/`medium`/`large` |
| `hero_species` | str\|None | Semantic species hint for grounding |
| `hero_candidates` | list[str] | Blender-side fallback candidate paths |
| `hero_fetch_metadata` | dict | Raw fetch metadata (for library promotion) |
| `_library_hero_entry` | dict | Stash: library-resolved hero record |
| `_enable_prop_fetch` | bool | Auto-enabled when prompt has contextual keywords |

## Populated during render (`render_from_manifest.py`)

| Field | Type | Description |
|---|---|---|
| `used_assets` | list[dict] | Each dict: `{id, role}` — populated by `register_used_asset` as each asset is imported.  Consumed by `write_credits_sidecar`. |
| `hero_source_uid` | str | UID from external source (Objaverse/Sketchfab) |

## World Development fields (post `WORLD_DEVELOPMENT` stage)

| Field | Type | Description |
|---|---|---|
| `world_dev_biome` | str | Biome name chosen by classifier |
| `environment_asset_id` | str\|None | Library id of environment asset placed (if any) |

## Internal flags (prefixed with `_`)

| Field | Type | Description |
|---|---|---|
| `_scene_plan` | dict | Legacy alias for `scene_plan` (some older code reads this) |
| `_behavior_executed` | bool | Set by `execute_behavior` to prevent double-animation |
| `_primary_animated_root` | bpy.Object | Runtime: primary hero root for camera tracking |

## Output folder contents (not manifest fields but written by pipeline)

- `blender_render_*.mp4` — primary output
- `credits.txt` — full attribution (round 8)
- `credits_short.txt` — social-media attribution (round 8)
- `pipeline_trace.log` — every log_stage + log marker
- `frame_*.png` — individual frames (cinematic tier keeps; others may purge)

## Unified Library schema (`app/data/library.json`)

Every asset is a single entry:

```jsonc
{
  "id":                 "lib_animal_bengal_cat",
  "path":               "assets/cache/models/characters/bengal_cat.glb",
  "subject":            "cat",
  "subject_tags":       ["cat", "feline", "animal", "pet", "bengal"],
  "visual_descriptors": ["orange", "tabby"],
  "category":           "character",     // character/vehicle/environment/prop/hdri
  "scale_class":        "small",
  "source":             "user_upload",   // curated/user_upload/objaverse/sketchfab/cached
  "quality":            "tested",        // tested/unverified/rejected
  "format":             "glb",           // blend/glb/gltf/fbx/obj
  "use_count":          0,
  "last_used_at":       null,
  "added_at":           1744839600,
  "brand":              null,            // vehicles: "porsche"/"ferrari"/etc
  "model":              null,            // vehicles: "911"/"f40"/etc
  "biome_hints":        [],               // environments: biome tags for world-dev matching
  "use_as":             null,            // environments: background_scenery/skybox/ground_replacement
  "attribution": {
    "author":       "ArtistName",
    "source":       "sketchfab",
    "source_url":   "https://sketchfab.com/3d-models/...",
    "license":      "CC-BY-4.0",
    "license_url":  "https://creativecommons.org/licenses/by/4.0/",
    "title":        "Bengal Cat"
  },
  "needs_attribution": false,
  "notes":            "ingested from inbox/cats/bengal-cat.zip at 1744839600"
}
```

## Log markers glossary (round 1-8)

These log markers identify pipeline stages/events in `pipeline_trace.log`:

- `[ASSET_AGENT]` — asset_agent.enrich_manifest_with_assets (early pipeline)
- `[ASSET_FETCH]` — asset_fetcher (external fetch cascade)
- `[BEHAVIOR]` — directorial_behavior.execute_behavior
- `[BLEND_DEDUP]` / `[GLB_DEDUP]` / `[DEDUP_HERO]` — Sketchfab twin-root dedup
- `[CAMERA_FIX]` / `[FRAME_FIX]` — static framing stages
- `[CAMERA_LOCK]` / `[CAMERA_SAFETY]` — directed-shot camera guards (rounds 6-7)
- `[CONTACT_SHADOW]` / `[CINEMATIC_LIGHTING]` — lighting stages
- `[CREDITS]` — attribution sidecar writer (round 8)
- `[CURATED]` — legacy curated catalog injection (largely superseded by library)
- `[HERO_GATE]` — subject-accuracy verification (round 6)
- `[HERO_RESOLVE]` — multi-tier retry orchestration (round 7)
- `[INGEST]` — bulk-ingest tool (round 7+8)
- `[LIBRARY]` — library curator (promote + query)
- `[MIGRATE]` — one-shot migration (round 7)
- `[OBJAVERSE]` / `[OBJAVERSE_QA]` — Objaverse fetch + vehicle QA
- `[RESOLVE]` — unified library-first resolution (round 7)
- `[SKETCHFAB_MULTI]` — multi-query Sketchfab retry (round 7)
- `[SCENE_CENSUS]` — pre/post FRAME_FIX diagnostic (round 7)
- `[VARIANT_POOL]` / `[VARIANT_DIVERSITY]` — rotation rerank + picker
- `[WORLD_DEV]` — world-development biome pass (round 6)
- `[WORLD_DEV/SCATTER]` / `[WORLD_DEV/SILHOUETTE]` / `[WORLD_DEV/GRADE]` — world-dev sub-stages

## Known deprecations (kept live to avoid breaking callers)

- `_inject_curated_hero` + `_inject_curated_fallback` (asset_agent.py) — superseded by
  `_resolve_hero_from_library` in round 7.  Still runs, but when the library has a
  match it wins first (see `_inject_library_hero_into_resolved`).
- `resolve_scene_assets` (asset_resolver.py) — still runs first; the library-override
  path immediately after it bulldozes the bucket when a library hit exists.  When
  library has full coverage, this function is effectively dead code.
- Vehicle synonym clause in `_extract_hero_metadata` (`vehicle synonym 'X' -> forcing
  local vehicle 'ferrari_01'`) — operates on `resolved_assets.models` after the
  library override; currently a no-op when library has brand+model entries.

## Resolution entry points (6+ functions, needs consolidation post-launch)

| Function | When it fires | What it returns |
|---|---|---|
| `resolve_scene_assets` | Always, early in `enrich_manifest_with_assets` | Bucketed `{models, hdris, textures}` |
| `_resolve_hero_from_library` | Always, right after `resolve_scene_assets` | Single best library entry or None |
| `_inject_library_hero_into_resolved` | Called when `_resolve_hero_from_library` returns a hit | Mutates `resolved_assets.models[bucket]` |
| `_inject_curated_hero` | Always (legacy) | Mutates `resolved_assets.models[bucket]` — blocks if library already injected |
| `_inject_curated_fallback` | After `fetch_missing_assets` if still empty | Mutates `resolved_assets.models[bucket]` |
| `resolve_hero_with_retry` | Only on subject-gate rejection | Returns chosen dict or None |
| `resolve_hero_from_catalog` (curated_resolver.py) | Called by `_inject_curated_hero` | Returns `(record, score)` |

Post-launch refactor goal: collapse to 2 functions — `resolve_hero(manifest)` and
`retry_hero_from_external(manifest, subject, reason)`.
