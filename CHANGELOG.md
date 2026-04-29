# Changelog

All notable changes to Fantasy Studio are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 versions are internal milestones during the constraint sprint leading to public V1.0 launch (Mid-May 2026). They're documented here transparently — Fantasy Studio has never been a stealth project.

---

## [Unreleased]

### Planned for V1.0.0 launch (Mid-May 2026)
- Public source release under BSL 1.1
- Marketing website live at [fantasylab.ai](https://fantasylab.ai)
- Patreon launch with premium recipe / asset tier
- Discord community open
- Curated launch gallery (50+ hero renders)
- Onboarding video series

---

## [1.4.3] - 2026-04

### Fixed
- Cast panel viewport sizing — content no longer cut off on standard 13"–14" laptop displays
- Surfaced `.blend` source file export alongside MP4 in the render output panel (previously buried in the file system)

---

## [1.4.2] - 2026-04

### Added
- Curated prompt suggestions surfacing verified-working scenes in the prompt entry empty state
- Scene complexity guardrail — gentle handoff for prompts the V1 single-subject pipeline can't render well, with explicit "this works in V2" messaging
- Empty-state showcase carousel of pre-rendered hero clips so first-touch visitors see what good output looks like before committing to a render

---

## [1.4.1.1] - 2026-04

### Fixed
- **Critical**: duplicate hero asset overlay in vehicle renders. Some `.blend` files (notably `bmw_01.blend`) ship two complete LOD copies under sibling `Sketchfab_model` parents. V1.3.5 transactional dedup correctly merged the parent EMPTYs but the matrix-restore preserved the loser sub-tree's world transforms, leaving identical mesh twins at full authored scale alongside the LAYOUT-scaled keeper. Result was a dual-car render
- Added `[LOD_CLEANUP]` pass post-`[FORCED_HERO_TAG]` that signature-indexes the `is_forced_hero` set `(vert_count, face_count, rounded_world_dims_xyz)` and `hide_render`s any untagged `is_hero` mesh with an exact signature match. Originals preserved (not deleted) for debugging
- Generated `vehicle_lod_audit.json` flagging 13 vehicles in suspicious size band as candidates for the same failure mode

---

## [1.4.1] - 2026-04

### Changed
- Asset scale floor lowered from 0.3m → 0.2m at the HERO_VERIFY gate (`bbox_sane` check). 20cm heroes (small bird, mouse, gem) are legitimate
- `_hero_scale_normalize` inner band: `target * 0.35` → `target * 0.20`. Vehicles in character-scale environments (20–35% band) now render at authored size instead of being force-rescaled up
- `_hero_scale_normalize` outer floor: 0.05m → 0.02m
- `[FORCE_FIX]` trust band: `0.1m..50m` → `0.02m..50m`; TINY trigger likewise
- HERO_VERIFY abort message updated to read `expected 0.2-50m`

### Added
- Library refresh pass — regenerated 14 missing thumbnails, audited 314 entries for empty tags / placeholder subjects (zero found)
- `library_refresh_report.json` and `library_triage_report.json` in `app/data/` documenting state at refresh time
- Triage queue surfaces 14 broken-path entries, 2 unsupported-format HDRIs, 1 heavy-blend timeout for human review

---

## [1.4.0] - 2026-04

### Added
- Frontend "Change cast" library browser with category filters
- Cast panel manual override across hero / environment / prop slots
- ZIP archive ingestion in `tools/downloads_ingestor.py` — Sketchfab and Poly Haven downloads land as `.zip`; the watcher now extracts to `assets/_ingest_staging/`, locates the primary 3D file, delegates to the existing single-file ingest, and quarantines the archive to `_ingest_completed/` or `_ingest_failed/`
- Backfill banner at watcher startup processes pending downloads before steady-state polling
- Nested-archive failure cases surface in `_ingest_failed/` with sibling `.error.txt` traces

### Fixed
- Watcher loop crash on Windows: `glob("*.zip")` and `glob("*.ZIP")` returned the same files (case-insensitive FS), causing the second iteration to crash on `src.stat()` after the first moved the file. Deduped the glob result via `dict.fromkeys` and added a defensive `src.exists()` check pre-stability-probe

---

## [1.3.7] - 2026-04

### Changed
- Library matcher confidence threshold lowered 0.5 → 0.30 (V1.3.6 was over-defensive; legitimate matches were being filtered)
- Subject normalization: 45-entry alias map (plurals → singular, `car` → `vehicle`, `animal` → `character`) plus stopword filter (`a`, `an`, `the`, `of`, …) so `"an elephant"` and `"elephants"` and `"elephant"` all hit the same bucket
- Scoring rubric tightened: 1.0 exact subject (post-normalization) / 0.85 exact tag / 0.40–0.75 partial subject substring / 0.30–0.60 partial tag substring
- Exact-subject short-circuit: top match with score ≥ 0.99 restricts the diversity rotation to exact-only candidates so an *elephant* prompt never falls through to *rhinoceros*
- `[MATCHER]` log line on every pick: `picked=… (score=…, exact_subject) runner_up=… (score=…)` for debug traceability
- BMW orientation overrides updated `[90, 0, 0]` → `[180, 0, 0]` for both `lib_registry_bmw_01` and `lib_bmw_bmw_bmw_m_motorsport_gt_racing` (full flip on X)

### Fixed
- Prompt `"a horse in the desert"` and `"a horse"` now produce identical matches (article stripping)

---

## [1.3.6] - 2026-04

### Added
- Hidden hero-cluster primitive cleanup: post-`[FORCED_HERO_TAG]` sweep of `is_hero=True && !is_forced_hero` MESH objects, hiding low-poly + sphere-like rig-control "orbs" (the `Object_35` chrome sphere in `horse.glb`)
- Per-asset orientation override: `import_rotation_xyz` field in `library.json` applied at import time, with `[ASSET_ORIENT_OVERRIDE]` log
- Two BMW entries flagged with the override
- Library matcher confidence threshold of 0.5 introduced (later lowered in V1.3.7)
- Auto-pick env min-score gate: prompts like *"horse in the mountain"* no longer collapse onto whatever env scores 8 from shape bonus alone

### Fixed
- ENV_PRESET running on top of forced-environment imports caused dual styling (e.g. desert preset color cast over a placed mountain asset). ENV_PRESET now skipped when `forced_environment_id` is set

---

## [1.3.5] - 2026-03

### Fixed
- BLEND_DEDUP triple-write per child invalidated Object refs → StructRNA crash → builder fallback to placeholder scene. Replaced with a 5-phase transactional flow (gather → reparent → settle → restore-matrix → validate → delete) with abort-on-validation-failure
- Vehicle orientation gate: rotate -90°X only when Z is the longest axis. Skip for asset_type `vehicle`. Stops low-and-wide cars getting flipped on import
- Multi-hit raycast for terrain placement: prefers top-facing surface normals (z > 0.1) so heroes don't land on the side of a dune
- Library reclassification: `lib_desert_desert_landscape` shape_class `flat_map` → `3d_terrain`
- HERO_VERIFY gained two structural checks: `oriented_correctly` (hard-fails when bbox.max_axis is wrong for the asset type), `grounded` (warn-only)

---

## [1.3.4] - 2026-03

### Added
- `[FORCED_HERO_TAG]` pre-pass: walks descendants of every `is_hero_root` and stamps `is_forced_hero=True` on mesh descendants within 10m of origin. Replaces fragile per-importer tagging
- `_format_hero_verify_abort` formatter in `app/blender_runner.py` parses `[HERO_VERIFY] ABORT:` and surfaces a structured user-facing error to the API instead of leaking DeprecationWarnings

### Fixed
- CAMERA_DIRECTOR_FINAL static placement was being overridden by tracking keyframes. Now `animation_data_clear()` runs before the director writes, then tracking/orbit re-bakes anchored to the director origin

---

## [1.3.3] - 2026-03

### Added
- HERO_VERIFY render gate: 5 structural checks (`has_hero_tag`, `bbox_sane`, `in_frustum`, `fill_ok`, `not_primitive`) before any frame is rendered
- Closed-loop fill solver in camera director: `distance = hero_h / (2 * target_fill * tan(fov_v/2))`. Subject-fill is now a target, not a guess

---

## [1.3.2] - 2026-03

### Added
- `app/services/camera_director.py` as the single source of truth for hero camera placement
- `_apply_director_to_camera` writer-attempt guard: any post-director write is logged and rejected if it deviates beyond a 0.1m tolerance

---

## [1.3.1] - 2026-03

### Fixed
- Vehicle hero shrink: `_enforce_scale` now skips the shrink path when `_looks_like_vehicle` returns True. Stops BMWs from being scaled from 4.8m to 1.7m when their library `category` happens to be `character/medium`

---

## [1.3.0] - 2026-03

### Added
- Template System v2: 15 named recipes + 16 base/env/comp/lighting/anim/ambient/post layers + weighted dispatcher + executor. Recipes are pure JSON; the executor walks them. Renderer-agnostic by design (Unreal / Godot future possible)
- `app/services/variant_pool.py`: subject-filtered diversity picker that returns None on empty filter (instead of silently picking a wrong-subject random asset)
- Curated injector and prop fetcher gated on `forced_hero_id` so manual cast picks aren't second-guessed

---

## [1.2.0] - 2026-02

### Added
- V1.2 asset healer: `app/services/asset_healer.py` runs once on ingest, computes `orientation_fix_rotation_euler`, `ground_offset_z`, `shape_class`, `provisional_ready`, persists to `library.json`. Originals never modified
- 232 library assets healed and registered in `library.json` at this version

---

## [1.1.0] - 2026-01

### Added
- Recipe-based pipeline foundation
- Asset registry with library matching against subject + tags
- Cycles + Eevee tier selection at render time
- Pipeline trace logging (`[PIPELINE] +N.NNNs STAGE_NAME` markers)
- HDRI library + procedural sky fallback

---

## [1.0.0] - TBD (Mid-May 2026)

- Initial public release under BSL 1.1
- 316-asset curated launch library
- 15 recipes + composable layer system
- Four render tiers (Quick Preview / Polished / High Quality / Final Cinematic)
- Local LLM director (Gemma 3 12B via Ollama) with deterministic fallback
- MP4 + `.blend` + GIF + PNG sequence + `credits.txt` output package
- Frontend cast panel + scene controls + refine panel
- Public docs at github.com/bgrut/fantasy-studio
- Marketing site at fantasylab.ai

[Unreleased]: https://github.com/bgrut/fantasy-studio/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.3
[1.4.2]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.2
[1.4.1.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.1.1
[1.4.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.1
[1.4.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.0
[1.3.7]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.7
[1.3.6]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.6
[1.3.5]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.5
[1.3.4]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.4
[1.3.3]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.3
[1.3.2]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.2
[1.3.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.1
[1.3.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.0
[1.2.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.2.0
[1.1.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.1.0
