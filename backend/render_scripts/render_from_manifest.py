import sys as _sys_sentinel
print("========================================", flush=True)
print("[RENDER_SCRIPT] render_from_manifest.py STARTED", flush=True)
print(f"[RENDER_SCRIPT] argv = {_sys_sentinel.argv!r}", flush=True)
print("========================================", flush=True)

import bpy
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ══════════════════════════════════════════════════════════════════════
# V1.3.2 — camera director integration
# ══════════════════════════════════════════════════════════════════════
# The director (app/services/camera_director.py) is the single
# authoritative source of hero-camera placement.  The V1.3.1 bucket
# helper `_pick_camera_distance_for_hero` that used to live here has
# been DELETED — every camera-touching stage now defers to the director.

# Recipe → director shot profile.  Used by every camera-touching stage
# so the director's decision is consistent across the pipeline.
_RECIPE_TO_SHOT_PROFILE: dict[str, str] = {
    "cat_canyon_cinematic":       "low_wide_dramatic",
    "hero_mountain_establishing": "wide_establishing",
    "hero_desert_epic":           "epic_pullback",
    "hero_forest_intimate":       "intimate_three_quarter",
    "hero_castle_dramatic":       "low_wide_dramatic",
    "animal_mountain_walk":       "wide_establishing",
    "animal_forest_intimate":     "intimate_three_quarter",
    "hero_city_street_night":     "hero_push_in",
    "hero_city_day":              "intimate_three_quarter",
    "hero_ocean_horizon":         "epic_pullback",
    "vehicle_desert_hero":        "low_wide_dramatic",
    "vehicle_street_chase":       "hero_push_in",
    "vehicle_mountain_road":      "epic_pullback",
    "robot_city_night":           "low_wide_dramatic",
    "multi_character_stage":      "intimate_three_quarter",
}


# ══════════════════════════════════════════════════════════════════════
# V1.3.3 Fix C — HERO_VERIFY gate
# ══════════════════════════════════════════════════════════════════════
# Last-chance pre-render verification.  Five checks; on hard failure
# writes a debug snapshot + exits non-zero so a bad render is never
# produced.  On soft (fill-only) failure retries the director once
# before giving up.

def _hero_verify_collect_meshes():
    """Return mesh objects with is_hero or is_forced_hero tags."""
    out = []
    try:
        for o in bpy.data.objects:
            try:
                if o.type != "MESH":
                    continue
                if o.get("is_hero", False) or o.get("is_forced_hero", False):
                    out.append(o)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _hero_verify_world_bbox(meshes):
    """Return (min_xyz, max_xyz, diag_m) or None."""
    if not meshes:
        return None
    try:
        from mathutils import Vector as _HVVec
        coords = []
        for o in meshes:
            try:
                mw = o.matrix_world
                for c in o.bound_box:
                    coords.append(mw @ _HVVec(c))
            except Exception:
                pass
        if not coords:
            return None
        mn = (
            min(c.x for c in coords),
            min(c.y for c in coords),
            min(c.z for c in coords),
        )
        mx = (
            max(c.x for c in coords),
            max(c.y for c in coords),
            max(c.z for c in coords),
        )
        diag = (
            (mx[0] - mn[0]) ** 2
            + (mx[1] - mn[1]) ** 2
            + (mx[2] - mn[2]) ** 2
        ) ** 0.5
        return mn, mx, diag
    except Exception:
        return None


def _hero_verify_in_frustum(scene, cam, point_world) -> bool:
    """True if ``point_world`` falls within camera's frustum at frame 0."""
    if cam is None or scene is None:
        return False
    try:
        from bpy_extras.object_utils import world_to_camera_view
        from mathutils import Vector as _HVVec
        co = world_to_camera_view(scene, cam, _HVVec(point_world))
        # co.x and co.y in [0,1] = inside; co.z > 0 = in front of camera
        return 0.0 <= co.x <= 1.0 and 0.0 <= co.y <= 1.0 and co.z > 0.0
    except Exception:
        return False


def _hero_verify_estimate_fill(scene, cam, hero_bbox) -> float:
    """Approximate vertical-fill fraction (0..1) of hero in frame."""
    if cam is None or hero_bbox is None:
        return 0.0
    try:
        import math
        mn, mx, _diag = hero_bbox
        hero_h = max(0.001, mx[2] - mn[2])
        center = (
            (mn[0] + mx[0]) * 0.5,
            (mn[1] + mx[1]) * 0.5,
            (mn[2] + mx[2]) * 0.5,
        )
        dx = center[0] - cam.location.x
        dy = center[1] - cam.location.y
        dz = center[2] - cam.location.z
        distance = max(0.001, (dx * dx + dy * dy + dz * dz) ** 0.5)
        # Use camera's actual lens; assume 24mm sensor_height (Blender default)
        lens = float(cam.data.lens) if cam.data and cam.data.lens else 50.0
        sensor_h = 24.0
        try:
            sensor_h = float(cam.data.sensor_height) if cam.data.sensor_height else 24.0
        except Exception:
            pass
        fov_v = 2.0 * math.atan(sensor_h / (2.0 * lens))
        frame_h_at_dist = 2.0 * distance * math.tan(fov_v / 2.0)
        return hero_h / max(frame_h_at_dist, 0.001)
    except Exception:
        return 0.0


def _hero_verify_max_polys(meshes) -> int:
    n = 0
    for o in meshes:
        try:
            n = max(n, len(o.data.polygons))
        except Exception:
            pass
    return n


def _hero_verify_gate(manifest: dict, retry_allowed: bool = True) -> tuple:
    """Run the 5 checks. Return (pass, reasons_dict)."""
    scene = bpy.context.scene
    cam = scene.camera
    meshes = _hero_verify_collect_meshes()

    checks: dict = {
        "has_hero_tag":      bool(meshes),
        "bbox_sane":         False,
        "in_frustum":        False,
        "fill_ok":           False,
        "not_primitive":     False,
        # V1.3.5 Fix 4 — structural checks
        "oriented_correctly": True,   # default-pass; fail only on hard signal
        "grounded":           True,   # warn-only; never blocks render
    }

    bbox = _hero_verify_world_bbox(meshes)
    diag = bbox[2] if bbox else 0.0
    # V1.4.1 floor decision: lower bound dropped 0.3m → 0.2m. A 20cm
    # hero (small bird, mouse, gem, jewellery) is a legitimate scene
    # subject, and many imported assets land in the 0.20–0.30m band
    # before the framing pass scales them up. Do NOT re-tighten this
    # without a concrete regression case. Upper bound stays at 50m.
    checks["bbox_sane"] = bool(bbox) and 0.2 < diag < 50.0

    if bbox and cam:
        center_world = (
            (bbox[0][0] + bbox[1][0]) * 0.5,
            (bbox[0][1] + bbox[1][1]) * 0.5,
            (bbox[0][2] + bbox[1][2]) * 0.5,
        )
        # Sample at frame_start so dynamic heroes are checked at the
        # camera's first-frame position.
        try:
            scene.frame_set(scene.frame_start)
            bpy.context.view_layer.update()
        except Exception:
            pass
        checks["in_frustum"] = _hero_verify_in_frustum(scene, cam, center_world)
        fill = _hero_verify_estimate_fill(scene, cam, bbox)
        checks["fill_ok"] = 0.35 <= fill <= 0.70
    else:
        fill = 0.0

    poly_max = _hero_verify_max_polys(meshes)
    checks["not_primitive"] = poly_max > 100

    # ── V1.3.5 Fix 4: orientation check ──────────────────────────────
    # For vehicles: longest axis should be Y (forward) or X (when shot
    # from behind / front).  Z should NOT be the longest.  A vehicle
    # with longest_axis == Z is on its end — render aborted.
    # For characters / animals: Z should be the longest (stand upright).
    # If a "character" has longest_axis Y or X, it's lying down — warn
    # but don't abort (some recipes intentionally ground heroes).
    _orient_axis_max = "?"
    _orient_expected_for_type = "?"
    _orient_subject_type = "?"
    if bbox:
        try:
            mn, mx, _diag = bbox
            ax = {
                "X": mx[0] - mn[0],
                "Y": mx[1] - mn[1],
                "Z": mx[2] - mn[2],
            }
            _orient_axis_max = max(ax, key=ax.get)
            _orient_subject_type = str(
                manifest.get("hero_asset_type")
                or (manifest.get("scene_plan") or {}).get("subject_type")
                or "character"
            ).lower()
            _vehicle_kinds = {"vehicle", "car", "truck", "motorcycle", "bike", "van"}
            _upright_kinds = {"character", "humanoid", "creature", "animal"}
            if _orient_subject_type in _vehicle_kinds:
                _orient_expected_for_type = "Y_or_X"
                # Vehicle is broken if Z is the longest dimension
                if _orient_axis_max == "Z":
                    checks["oriented_correctly"] = False
            elif _orient_subject_type in _upright_kinds:
                _orient_expected_for_type = "Z"
                # Upright subjects: warn (not abort) when not standing.
                # We only flip the gate when it's CLEARLY laid down
                # (height < 30% of longest horizontal); soft cases pass.
                if _orient_axis_max != "Z":
                    _h = ax["Z"]
                    _max_horiz = max(ax["X"], ax["Y"])
                    if _h > 0 and _max_horiz > 0 and _h < 0.30 * _max_horiz:
                        checks["oriented_correctly"] = False
        except Exception:
            pass

    # ── V1.3.5 Fix 4: ground-contact check (warn-only) ──────────────
    # Hero bottom should be within 0.5m of nearest env mesh's top at
    # the hero's XY.  A floating hero is logged but not blocked
    # (legitimate flying/swimming subjects exist).
    _ground_gap_m = None
    if bbox:
        try:
            from mathutils import Vector as _GVec
            mn, mx, _diag = bbox
            hero_bottom_z = mn[2]
            hero_cx = (mn[0] + mx[0]) * 0.5
            hero_cy = (mn[1] + mx[1]) * 0.5
            # Cast straight down at hero center XY against env meshes
            env_top_z = None
            for o in bpy.data.objects:
                if o.type != "MESH":
                    continue
                if not o.get("is_environment", False):
                    continue
                try:
                    mw_inv = o.matrix_world.inverted()
                    local_o = mw_inv @ _GVec((hero_cx, hero_cy, 1000.0))
                    local_d = (mw_inv.to_3x3() @ _GVec((0.0, 0.0, -1.0))).normalized()
                    hit, loc, nrm, _idx = o.ray_cast(local_o, local_d)
                    if hit:
                        world_hit = (o.matrix_world @ loc).z
                        if env_top_z is None or world_hit > env_top_z:
                            env_top_z = world_hit
                except Exception:
                    pass
            if env_top_z is not None:
                _ground_gap_m = abs(hero_bottom_z - env_top_z)
                if _ground_gap_m > 0.5:
                    # Soft gate: log mismatch but stay True so render proceeds
                    print(
                        f"[HERO_VERIFY] grounded WARN: hero bottom z={hero_bottom_z:.3f}, "
                        f"env top z={env_top_z:.3f}, gap={_ground_gap_m:.2f}m "
                        f"(expected <0.5m for ground-based hero)",
                        flush=True,
                    )
        except Exception:
            pass

    print(
        f"[HERO_VERIFY] checks: "
        f"has_hero_tag={checks['has_hero_tag']} "
        f"bbox_sane={checks['bbox_sane']} (diag={diag:.2f}m) "
        f"in_frustum={checks['in_frustum']} "
        f"fill_ok={checks['fill_ok']} (fill={fill:.0%}) "
        f"not_primitive={checks['not_primitive']} (max_polys={poly_max}) "
        f"oriented_correctly={checks['oriented_correctly']} "
        f"(axis_max={_orient_axis_max}, expected={_orient_expected_for_type}, "
        f"type={_orient_subject_type}) "
        f"grounded={checks['grounded']} "
        f"(gap={_ground_gap_m if _ground_gap_m is not None else 'n/a'}m)",
        flush=True,
    )

    if all(checks.values()):
        print("[HERO_VERIFY] PASS", flush=True)
        return True, {}

    failed = [k for k, v in checks.items() if not v]

    # Retry path: only fill_ok failed AND we have a usable bbox + cam
    fill_only_failure = (failed == ["fill_ok"]) and bbox and cam
    if retry_allowed and fill_only_failure:
        print(
            f"[HERO_VERIFY] RETRY — fill={fill:.2%} outside 35-70% range; "
            f"calling director once more with actual frame_start bbox",
            flush=True,
        )
        try:
            _retry_profile = _director_profile_for_manifest(manifest)
            _apply_director_to_camera(
                cam, (bbox[0], bbox[1]), _retry_profile, manifest, "HERO_VERIFY_RETRY",
            )
        except Exception as _retry_err:
            print(f"[HERO_VERIFY] retry call failed: {_retry_err}", flush=True)
        # Re-check fill (only)
        fill2 = _hero_verify_estimate_fill(scene, cam, bbox)
        if 0.35 <= fill2 <= 0.70:
            print(
                f"[HERO_VERIFY] PASS after retry (fill {fill:.0%} -> {fill2:.0%})",
                flush=True,
            )
            return True, {}
        print(
            f"[HERO_VERIFY] retry insufficient (fill {fill:.0%} -> {fill2:.0%})",
            flush=True,
        )
        failed = ["fill_ok"]

    return False, {
        "failed_checks": failed,
        "bbox_diag":     diag,
        "fill":          fill,
        "max_polys":     poly_max,
        "checks":        checks,
    }


def _hero_verify_abort(manifest: dict, reasons: dict) -> None:
    """Write a debug snapshot then sys.exit(2)."""
    import json as _hva_json
    import time as _hva_time
    import traceback as _hva_tb

    try:
        debug_dir = ROOT / "outputs" / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        ts = _hva_time.strftime("%Y%m%d_%H%M%S")
        blend_path = debug_dir / f"hero_verify_abort_{ts}.blend"
        json_path = debug_dir / f"hero_verify_abort_{ts}.json"

        snapshot = {
            "abort_reason":         "HERO_VERIFY checks did not pass",
            "failed_checks":        reasons.get("failed_checks"),
            "bbox_diag_m":          reasons.get("bbox_diag"),
            "fill_pct":             round(reasons.get("fill", 0.0) * 100.0, 1),
            "max_polys":            reasons.get("max_polys"),
            "checks":               reasons.get("checks"),
            "manifest_topic":       manifest.get("topic"),
            "manifest_template":    manifest.get("template_name"),
            "manifest_recipe":      manifest.get("_template_v2_recipe"),
            "forced_hero_id":       manifest.get("forced_hero_id"),
            "forced_environment_id": manifest.get("forced_environment_id"),
            "timestamp":            ts,
        }
        try:
            json_path.write_text(_hva_json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception:
            pass

        try:
            bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), copy=True)
        except Exception as _save_err:
            print(
                f"[HERO_VERIFY] blend snapshot save failed: {_save_err}",
                flush=True,
            )

        print(
            f"[HERO_VERIFY] ABORT: {reasons.get('failed_checks')} | "
            f"diag={reasons.get('bbox_diag', 0.0):.2f}m "
            f"fill={reasons.get('fill', 0.0):.0%} "
            f"polys={reasons.get('max_polys')}",
            flush=True,
        )
        print(
            f"[HERO_VERIFY] debug snapshot: {blend_path.name} + {json_path.name} "
            f"in {debug_dir}",
            flush=True,
        )
    except Exception as _abort_err:
        print(f"[HERO_VERIFY] abort writer crashed: {_abort_err}", flush=True)
        print(_hva_tb.format_exc(), flush=True)

    sys.exit(2)


def _director_profile_for_manifest(manifest: dict, default: str = "hero_push_in") -> str:
    """Pick the best director shot profile for this render, given the
    V1.3 recipe name (when present) or template_name as fallback."""
    recipe = str(manifest.get("_template_v2_recipe") or "").lower()
    if recipe and recipe in _RECIPE_TO_SHOT_PROFILE:
        return _RECIPE_TO_SHOT_PROFILE[recipe]
    # Template-name fallback (no V1.3 recipe or unknown)
    tmpl = str(manifest.get("template_name") or "").lower()
    _tmpl_fallback = {
        "scenic_landscape": "wide_establishing",
        "street_scene":     "hero_push_in",
        "car_hero":         "low_wide_dramatic",
        "character_stage":  "intimate_three_quarter",
        "ocean_scene":      "epic_pullback",
        "product_scene":    "intimate_three_quarter",
    }
    return _tmpl_fallback.get(tmpl, default)


def _apply_director_to_camera(cam, hero_bbox, shot_profile, manifest, stage_label):
    """V1.3.2 single-point-of-entry for camera placement.

    Calls the director, then applies its output to the scene camera:
      - sets location
      - sets lens
      - aims via Vector.to_track_quat for precise rotation
      - updates view_layer
      - logs one `[CAMERA_DIRECTOR]` line with full details

    ``hero_bbox`` is ``((min_x,min_y,min_z),(max_x,max_y,max_z))``.
    ``shot_profile`` is one of the director's named profiles.
    ``stage_label`` is the old stage name (CAMERA_ENV_ADJUSTED etc.)
    printed for backwards-compat log grep.

    Returns the director's CameraPlacement dataclass so callers can
    propagate derived values (distance, lens, etc.).
    """
    try:
        from app.services.camera_director import place_hero_camera
        from mathutils import Vector as _DirVec
    except Exception as _imp_err:
        print(f"[CAMERA_DIRECTOR] import failed (non-fatal): {_imp_err}", flush=True)
        return None

    # Aspect from scene render settings
    try:
        _scene = bpy.context.scene
        _aspect = (_scene.render.resolution_x, _scene.render.resolution_y)
    except Exception:
        _aspect = (9, 16)

    placement = place_hero_camera(hero_bbox, shot_profile, _aspect)

    try:
        cam.location = placement.location
        cam.data.lens = float(placement.lens_mm)
        # Precise aim via bpy math
        mn, mx = hero_bbox
        hero_center = _DirVec((
            (mn[0] + mx[0]) * 0.5,
            (mn[1] + mx[1]) * 0.5,
            (mn[2] + mx[2]) * 0.5,
        ))
        # Aim slightly above geometric center for natural shoulder/head
        # framing
        _aim_target = _DirVec((
            hero_center.x,
            hero_center.y,
            hero_center.z + (mx[2] - mn[2]) * 0.15,
        ))
        _aim_dir = _aim_target - _DirVec(placement.location)
        if _aim_dir.length > 0.001:
            cam.rotation_euler = _aim_dir.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
    except Exception as _ap_err:
        print(f"[CAMERA_DIRECTOR] apply failed (non-fatal): {_ap_err}", flush=True)

    # Hero bbox summary for log readability
    _bw = mx[0] - mn[0]
    _bd = mx[1] - mn[1]
    _bh = mx[2] - mn[2]
    print(
        f"[CAMERA_DIRECTOR] hero_bbox={_bw:.2f}x{_bd:.2f}x{_bh:.2f}m "
        f"profile={shot_profile} aspect={_aspect[0]}:{_aspect[1]} "
        f"-> cam=({placement.location[0]:.2f},{placement.location[1]:.2f},"
        f"{placement.location[2]:.2f}) lens={placement.lens_mm:.0f}mm "
        f"subject_fills={placement.subject_fill_pct}% "
        f"notes='{placement.framing_notes}' [called-from={stage_label}]",
        flush=True,
    )
    return placement

from app.templates.city_loop import build_city_loop
from app.templates.product_pedestal import build_product_pedestal
from app.templates.neon_news import build_neon_news
from app.templates.street_scene import build_street_scene
from app.templates.product_scene import build_product_scene
from app.templates.ocean_scene import build_ocean_scene
from app.templates.scenic_landscape import build_scenic_landscape
from app.templates.car_hero import build_car_hero
from app.templates.character_stage import build_character_stage

# Bulletproof asset-import utilities (verify_asset_file, resolve_asset_path,
# clean_default_primitives, import_hero_asset).
try:
    from app.scene.asset_import import (
        verify_asset_file,
        resolve_asset_path,
        clean_default_primitives,
        ensure_scene_basics,
        import_hero_asset,
    )
    _HAS_ASSET_IMPORT = True
except ImportError as e:
    print(f"DEBUG asset_import helpers unavailable: {e}", flush=True)
    _HAS_ASSET_IMPORT = False

# Round 9 Pillar 2/3 cinematic gap-fillers: atmosphere, 3-point lighting,
# contact shadow, ground material, and cinematic DOF. All are optional
# and fail-silent — render must still run without them.
try:
    from app.scene.environment_ops import build_environment_layers
    _HAS_ENV_OPS = True
except ImportError as e:
    print(f"DEBUG environment_ops unavailable: {e}", flush=True)
    _HAS_ENV_OPS = False

# Round 12 safety net: guarantees sky + ground + lights + atmosphere even
# when the template / build_environment_layers left gaps.
try:
    from app.scene.ensure_environment import (
        ensure_environment as _ensure_environment_safety_net,
        apply_directorial_controls as _apply_directorial_controls,
    )
    _HAS_ENV_SAFETY = True
except ImportError as e:
    print(f"DEBUG ensure_environment unavailable: {e}", flush=True)
    _HAS_ENV_SAFETY = False

try:
    from app.scene.layout_ops import setup_cinematic_dof
    _HAS_DOF = True
except ImportError as e:
    print(f"DEBUG setup_cinematic_dof unavailable: {e}", flush=True)
    _HAS_DOF = False

# Scene Director -- produces structured scene_plan from manifest
try:
    from app.scene.scene_director import direct_scene
    _HAS_DIRECTOR = True
except ImportError:
    _HAS_DIRECTOR = False

# Scene Recipe Builder -- decomposes prompt into structured layers
# (hero / env / ground / sky / atmosphere / lighting / camera / props /
# compositor). Pure data, no Blender imports. world_builder reads the
# attached recipe to make smarter HDRI / ground / atmosphere choices.
try:
    from app.services.scene_recipe_builder import build_scene_recipe
    _HAS_RECIPE = True
except ImportError as e:
    print(f"DEBUG scene_recipe_builder unavailable: {e}", flush=True)
    _HAS_RECIPE = False

# Scene Optimizer -- removes waste after scene construction
try:
    from app.scene.scene_optimizer import optimize_scene
    _HAS_OPTIMIZER = True
except ImportError:
    _HAS_OPTIMIZER = False

# Render Budget -- enforces predictable render times per tier
try:
    from app.render.render_budget import apply_render_budget
    _HAS_BUDGET = True
except ImportError:
    _HAS_BUDGET = False

# Scene keyword guarantor — synthesizes stylized mountains / ocean / trees /
# dunes / snow when the prompt names them but no complex env was fetched.
try:
    from app.scene.scene_keyword_guarantor import guarantee_scene_keywords
    _HAS_KW_GUARANTOR = True
except ImportError as e:
    print(f"DEBUG scene_keyword_guarantor unavailable: {e}", flush=True)
    _HAS_KW_GUARANTOR = False

# Cinematic Post-Processing Pipeline — mood-based compositor with
# DoF, bloom, vignette, color grading, film grain, atmospheric fog,
# and lens distortion.  Replaces the basic setup_compositor() for
# tiers that benefit from the full pipeline.
try:
    from app.scene.cinematic_compositor import (
        build_cinematic_compositor,
        infer_mood,
    )
    _HAS_CINEMATIC_COMPOSITOR = True
except ImportError as e:
    print(f"DEBUG cinematic_compositor unavailable: {e}", flush=True)
    _HAS_CINEMATIC_COMPOSITOR = False

# Cinematic 3-point lighting — mood-based key/fill/rim from scene_recipe
try:
    from app.scene.cinematic_lighting import apply_cinematic_lighting
    _HAS_CINEMATIC_LIGHTING = True
except ImportError as e:
    print(f"DEBUG cinematic_lighting unavailable: {e}", flush=True)
    _HAS_CINEMATIC_LIGHTING = False


def args_after_double_dash():
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Missing args after --")
    return argv[argv.index("--") + 1:]


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def _apply_healed_transforms(obj_root, entry: dict, role: str = "asset") -> None:
    """V1.2 runtime applier: read orientation_fix_rotation_euler and
    ground_offset_z from a library entry and apply them to ``obj_root``.

    Non-destructive to the source asset — we only manipulate the
    Blender object's transform after import.  Safe no-op when the entry
    has no healing metadata (pre-heal assets).
    """
    if obj_root is None or not isinstance(entry, dict):
        return
    try:
        from mathutils import Euler as _HealEuler  # type: ignore
    except Exception:
        _HealEuler = None
    try:
        rot_fix = entry.get("orientation_fix_rotation_euler")
        if rot_fix and isinstance(rot_fix, (list, tuple)) and len(rot_fix) >= 3:
            try:
                # Compose with any existing rotation rather than replacing it
                # — some templates apply their own rotation first.
                rx, ry, rz = float(rot_fix[0]), float(rot_fix[1]), float(rot_fix[2])
                obj_root.rotation_euler = (
                    obj_root.rotation_euler.x + rx,
                    obj_root.rotation_euler.y + ry,
                    obj_root.rotation_euler.z + rz,
                )
                print(
                    f"[HEAL_APPLY] {role} rotation_fix=({rx:.3f},{ry:.3f},{rz:.3f}) "
                    f"(issue={entry.get('orientation_issue')!r})",
                    flush=True,
                )
            except Exception as _rot_err:
                print(f"[HEAL_APPLY] rotation apply failed: {_rot_err}", flush=True)

        ground_z = entry.get("ground_offset_z")
        if ground_z is not None:
            try:
                gz = float(ground_z)
                # Snap bottom to z=0: shift up by -ground_offset_z
                if abs(gz) > 1e-4:
                    obj_root.location.z -= gz
                    print(
                        f"[HEAL_APPLY] {role} ground_offset_z={gz:.3f} applied",
                        flush=True,
                    )
            except Exception as _gz_err:
                print(f"[HEAL_APPLY] ground_offset apply failed: {_gz_err}", flush=True)
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
    except Exception as _outer:
        print(f"[HEAL_APPLY] outer failure (non-fatal): {_outer}", flush=True)


def load_manifest(path_str: str):
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Manifest file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8-sig"))


_RENDER_TIERS = {
    # PREVIEW: Eevee real-time path. Used for the conversational iterate
    # loop -- target is < 30s end-to-end on a workstation GPU.
    "preview": {
        "engine": "BLENDER_EEVEE",
        "samples": 16,
        "adaptive_threshold": 0.10,
        "use_denoising": False,
        "max_bounces": 2,
        "transparent_max_bounces": 1,
        "compositor": "none",
    },
    "fast": {
        "engine": "CYCLES",
        "samples": 32,
        "adaptive_threshold": 0.08,
        "use_denoising": True,
        "max_bounces": 4,
        "transparent_max_bounces": 2,
        "compositor": "minimal",
    },
    "standard": {
        "engine": "CYCLES",
        "samples": 128,
        "adaptive_threshold": 0.03,
        "use_denoising": True,
        "max_bounces": 6,
        "transparent_max_bounces": 4,
        "compositor": "cinematic",
    },
    "ultra": {
        "engine": "CYCLES",
        "samples": 256,
        "adaptive_threshold": 0.01,
        "use_denoising": True,
        "max_bounces": 8,
        "transparent_max_bounces": 6,
        "compositor": "cinematic",
    },
    # CINEMATIC: hero deliverables — pushed to near-production-grade for
    # the "always-shareable" target. Adds motion blur, Blackman-Harris
    # pixel filter, 150% resolution scale, and heavier GI/caustics.
    "cinematic": {
        "engine": "CYCLES",
        "samples": 1024,
        "adaptive_threshold": 0.003,
        "use_denoising": True,
        "max_bounces": 16,
        "transparent_max_bounces": 12,
        "compositor": "cinematic",
        # Cinematic-only upgrades consumed by configure_scene():
        "motion_blur": True,
        "motion_blur_shutter": 0.5,
        "resolution_scale": 150,        # percent (renders 1.5x, output stays at set res)
        "pixel_filter": "BLACKMAN_HARRIS",
        "pixel_filter_width": 1.5,
        "use_caustics": True,
        "volume_step_rate": 0.25,
        "exposure_boost": 0.15,         # subtle lift on cinematic tier
    },
}


def _resolve_tier_name(manifest: dict) -> str:
    """
    Determine which render tier to apply.

    Precedence:
        1. manifest['render_tier']  (new in WS5)
        2. manifest['quality_tier'] (legacy field)
        3. 'standard'
    """
    raw = manifest.get("render_tier") or manifest.get("quality_tier") or "standard"
    name = str(raw).strip().lower()
    # legacy synonyms
    if name in ("high", "hi"):
        name = "standard"
    if name not in _RENDER_TIERS:
        name = "standard"
    return name


def setup_compositor(scene, tier: str = "standard"):
    """
    Build compositor node tree.
    - none: skip the compositor entirely (preview tier)
    - minimal: glare only (fast preview)
    - cinematic: glare + lens distortion + vignette + color balance
    """
    mode = _RENDER_TIERS.get(tier, _RENDER_TIERS["standard"])["compositor"]
    if mode == "none":
        try:
            scene.use_nodes = False
        except Exception:
            pass
        print(f"DEBUG compositor disabled: tier={tier}", flush=True)
        return

    try:
        scene.use_nodes = True
        nt = scene.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()

        rl = nodes.new("CompositorNodeRLayers")
        rl.location = (0, 0)

        # --- Glare / bloom ---
        glare = nodes.new("CompositorNodeGlare")
        glare.glare_type = "FOG_GLOW"
        glare.quality = "LOW" if tier == "fast" else "MEDIUM"
        glare.threshold = 0.85
        glare.size = 6
        glare.location = (300, 0)
        links.new(rl.outputs["Image"], glare.inputs["Image"])

        last_output = glare.outputs["Image"]

        if mode == "cinematic":
            # --- Lens distortion (subtle barrel) ---
            lens = nodes.new("CompositorNodeLensdist")
            lens.inputs["Distort"].default_value = 0.005
            lens.inputs["Dispersion"].default_value = 0.003
            lens.use_fit = True
            lens.location = (550, 0)
            links.new(last_output, lens.inputs["Image"])
            last_output = lens.outputs["Image"]

            # --- Color balance (lift/gamma/gain for filmic polish) ---
            cb = nodes.new("CompositorNodeColorBalance")
            cb.correction_method = "LIFT_GAMMA_GAIN"
            # Warm shadows, neutral mids, slightly cool highlights
            cb.lift = (0.97, 0.97, 1.0)
            cb.gamma = (1.0, 1.0, 1.0)
            cb.gain = (1.02, 1.01, 0.99)
            cb.location = (800, 0)
            links.new(last_output, cb.inputs["Image"])
            last_output = cb.outputs["Image"]

            # --- Vignette via Ellipse Mask + Mix ---
            try:
                mask = nodes.new("CompositorNodeEllipseMask")
                mask.x = 0.5
                mask.y = 0.5
                mask.width = 0.82
                mask.height = 0.82
                mask.location = (800, -300)

                blur = nodes.new("CompositorNodeBlur")
                blur.size_x = 220
                blur.size_y = 220
                blur.use_relative = False
                blur.filter_type = "FAST_GAUSS"
                blur.location = (1050, -300)
                links.new(mask.outputs["Mask"], blur.inputs["Image"])

                mix = nodes.new("CompositorNodeMixRGB")
                mix.blend_type = "MULTIPLY"
                mix.inputs["Fac"].default_value = 0.35
                mix.location = (1100, 0)
                links.new(last_output, mix.inputs[1])
                links.new(blur.outputs["Image"], mix.inputs[2])
                last_output = mix.outputs["Image"]
            except Exception as ve:
                print(f"DEBUG vignette setup skipped: {ve}", flush=True)

        comp = nodes.new("CompositorNodeComposite")
        comp.location = (1400, 0)
        links.new(last_output, comp.inputs["Image"])

        print(f"DEBUG compositor built: tier={tier} mode={mode}", flush=True)

    except Exception as e:
        print(f"DEBUG compositor setup failed: {e}", flush=True)


def configure_scene(scene, manifest):
    tier = _resolve_tier_name(manifest)
    tier_cfg = _RENDER_TIERS[tier]
    engine = tier_cfg.get("engine", "CYCLES")

    # WS5: Eevee fast-pass for the conversational preview tier. Newer Blender
    # builds (4.2+) renamed the engine to BLENDER_EEVEE_NEXT — try the legacy
    # id first, then fall back so we work across builds.
    if engine == "BLENDER_EEVEE":
        try:
            scene.render.engine = "BLENDER_EEVEE"
        except Exception:
            try:
                scene.render.engine = "BLENDER_EEVEE_NEXT"
            except Exception:
                scene.render.engine = "CYCLES"
    else:
        scene.render.engine = "CYCLES"

    scene.render.resolution_x = manifest["output_resolution"]["width"]
    scene.render.resolution_y = manifest["output_resolution"]["height"]
    scene.render.fps = int(manifest.get("fps", 24))
    scene.frame_start = 1
    scene.frame_end = int(manifest.get("duration_seconds", 12)) * scene.render.fps
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False

    if scene.render.engine.startswith("BLENDER_EEVEE"):
        # Eevee tuning for fast preview path
        try:
            eevee = scene.eevee
            eevee.taa_render_samples = max(8, int(tier_cfg.get("samples", 16)))
            eevee.use_bloom = True
            eevee.use_ssr = False
            eevee.use_volumetric_lights = False
            eevee.use_motion_blur = False
        except Exception as e:
            print(f"DEBUG eevee tuning skipped: {e}", flush=True)
    elif hasattr(scene, "cycles"):
        scene.cycles.samples = tier_cfg["samples"]
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = tier_cfg["adaptive_threshold"]
        scene.cycles.use_denoising = tier_cfg["use_denoising"]
        scene.cycles.max_bounces = tier_cfg["max_bounces"]
        scene.cycles.transparent_max_bounces = tier_cfg["transparent_max_bounces"]

        # ── Cinematic-tier cinematic-quality extras ────────────────────────
        # All wrapped in try/except because Blender moves these API names
        # around across versions; we never want to crash a render over a
        # missing quality knob.
        if tier_cfg.get("use_caustics"):
            try:
                scene.cycles.caustics_reflective = True
                scene.cycles.caustics_refractive = True
            except Exception:
                pass
        if tier_cfg.get("volume_step_rate"):
            try:
                scene.cycles.volume_step_rate = float(tier_cfg["volume_step_rate"])
            except Exception:
                pass
        pf = tier_cfg.get("pixel_filter")
        if pf:
            try:
                scene.cycles.pixel_filter_type = pf
            except Exception:
                pass
        pfw = tier_cfg.get("pixel_filter_width")
        if pfw:
            try:
                scene.cycles.filter_width = float(pfw)
            except Exception:
                pass

    # ── Motion blur ────────────────────────────────────────────────────
    # Applies to both Cycles and Eevee paths (render.use_motion_blur covers
    # Cycles; Eevee uses scene.eevee.use_motion_blur set above for preview).
    if tier_cfg.get("motion_blur"):
        try:
            scene.render.use_motion_blur = True
            scene.render.motion_blur_shutter = float(tier_cfg.get("motion_blur_shutter", 0.5))
        except Exception:
            pass

    # ── Resolution scale (supersampling) for cinematic tier ───────────
    # scene.render.resolution_percentage doesn't change the output dims,
    # it just renders at a higher internal resolution, so a 1080p output
    # becomes 1620p-sampled-and-downrez for much cleaner edges.
    rs = tier_cfg.get("resolution_scale")
    if rs:
        try:
            scene.render.resolution_percentage = int(rs)
        except Exception:
            pass

    # ── Exposure boost (cinematic feels more dramatic) ─────────────────
    eb = tier_cfg.get("exposure_boost")
    if eb:
        try:
            scene.view_settings.exposure = float(scene.view_settings.exposure) + float(eb)
        except Exception:
            pass

    # Color management — AgX with Medium Contrast is the cinematic baseline.
    # Templates can override exposure via ensure_scene_look() but we keep the
    # look transform here so there is always a contrast curve applied.
    try:
        scene.view_settings.view_transform = "AgX"
    except Exception:
        pass
    try:
        scene.view_settings.look = "AgX - Medium Contrast"
    except Exception:
        try:
            scene.view_settings.look = "Medium Contrast"
        except Exception:
            pass

    setup_compositor(scene, tier=tier)
    print(
        f"DEBUG configure_scene: tier={tier} engine={scene.render.engine} "
        f"samples={tier_cfg['samples']} res={scene.render.resolution_x}x{scene.render.resolution_y}",
        flush=True,
    )


def build_fallback_scene(bpy, scene):
    bpy.ops.mesh.primitive_plane_add(location=(0, 0, 0))
    ground = bpy.context.object
    ground.scale = (20, 20, 1)
    ground.name = "GroundPlane"  # protected from clean_default_primitives

    bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0, 1.2))
    sphere = bpy.context.object
    sphere.name = "HeroPlaceholder"  # protected; signals the fallback

    bpy.ops.object.light_add(type='AREA', location=(0, -6, 5))
    light = bpy.context.object
    light.data.energy = 4000

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 1))
    target = bpy.context.object

    bpy.ops.object.camera_add(location=(0, -8, 3.2), rotation=(1.20, 0, 0))
    cam = bpy.context.object
    cam.data.lens = 55
    scene.camera = cam

    c = cam.constraints.new(type='TRACK_TO')
    c.target = target
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'


def main():
    import time as _time

    render_log: list[dict] = []
    _t0 = _time.monotonic()

    def log_stage(stage_name: str, details: str = ""):
        elapsed = _time.monotonic() - _t0
        entry = {"stage": stage_name, "t": round(elapsed, 3), "details": details}
        render_log.append(entry)
        print(f"[PIPELINE] +{elapsed:7.3f}s  {stage_name}  {details}", flush=True)

    log_stage("MAIN_START")

    output_path_str, manifest_path_str = args_after_double_dash()
    output_path = Path(output_path_str)
    manifest = load_manifest(manifest_path_str)
    log_stage("MANIFEST_LOADED", f"template={manifest.get('template_name')}")

    print(f"DEBUG manifest path={manifest_path_str}", flush=True)
    print(f"DEBUG template={manifest.get('template_name')}", flush=True)
    print(f"DEBUG hero_asset_path={manifest.get('hero_asset_path', 'NOT SET')}", flush=True)
    print(f"DEBUG hero_asset_type={manifest.get('hero_asset_type', 'NOT SET')}", flush=True)
    print(f"DEBUG environment_ground_type={manifest.get('environment_ground_type', 'NOT SET')}", flush=True)
    print(f"DEBUG action={manifest.get('action', 'NOT SET')}", flush=True)

    # ── FIX 6: Absolute path resolution + file verification ────────────
    # Blender runs as a subprocess with an unknown CWD, so every asset
    # path that templates will open MUST be absolute. Also verify the
    # hero file looks like a real 3D asset before we hand it off — if
    # the download was corrupted or still a ZIP the error is much
    # louder here than inside Blender's GLTF importer.
    if _HAS_ASSET_IMPORT:
        raw_hero = manifest.get("hero_asset_path")
        if raw_hero:
            abs_hero = resolve_asset_path(raw_hero)
            manifest["hero_asset_path"] = abs_hero
            print(f"DEBUG resolved hero_asset_path -> {abs_hero}", flush=True)
            ok, msg = verify_asset_file(abs_hero)
            print(f"DEBUG hero asset verification: {msg}", flush=True)
            if not ok:
                print(
                    "DEBUG hero asset failed verification — templates will fall back to defaults.",
                    flush=True,
                )
                # Keep hero_asset_path so templates can log the failure,
                # but blank out the type so behavior dispatch skips it.
                manifest["hero_asset_type"] = None
                manifest["hero_has_armature"] = False
                manifest["hero_has_animations"] = False

        # Also resolve any paths inside resolved_assets so blend_asset_ops
        # doesn't have to guess.
        _ra = manifest.get("resolved_assets") or {}
        _models = _ra.get("models")
        if isinstance(_models, dict):
            for bucket, items in _models.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and item.get("path"):
                        item["path"] = resolve_asset_path(item["path"]) or item["path"]
        elif isinstance(_models, list):
            for item in _models:
                if isinstance(item, dict) and item.get("path"):
                    item["path"] = resolve_asset_path(item["path"]) or item["path"]

    # Log resolved_assets model buckets
    _ra = manifest.get("resolved_assets") or {}
    _ra_models = _ra.get("models") or {}
    if isinstance(_ra_models, dict):
        _counts = {k: len(v) for k, v in _ra_models.items() if isinstance(v, list) and v}
        print(f"DEBUG resolved_assets models: {_counts}", flush=True)
    elif isinstance(_ra_models, list):
        print(f"DEBUG resolved_assets models: {len(_ra_models)} flat items", flush=True)
    print(f"DEBUG resolved_assets hdris={len(_ra.get('hdris', []))}", flush=True)

    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene, manifest)
    log_stage("SCENE_CONFIGURED")

    output_dir = output_path.parent / output_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output_dir / "frame_")

    template = str(manifest.get("template_name", "neon_news")).lower()

    # ── Diagnostic: manifest snapshot right before template dispatch ────
    # Prints a truncated (first 200 chars per value) JSON view of the
    # manifest so we can see exactly what the template receives.
    try:
        _snapshot = {k: str(v)[:200] for k, v in manifest.items()}
        print(
            f"[RENDER] MANIFEST PASSED TO TEMPLATE: "
            f"{json.dumps(_snapshot, indent=2, ensure_ascii=False)}",
            flush=True,
        )
    except Exception as _e:
        print(f"[RENDER] manifest snapshot failed (non-fatal): {_e}", flush=True)

    # ── Scene Director: produce scene_plan and attach to manifest ───────
    # Builders that support scene_plan will read it from manifest["_scene_plan"].
    # Backward compatibility: if director is unavailable or fails, builders
    # fall back to their existing hardcoded logic.
    if _HAS_DIRECTOR:
        try:
            scene_plan = direct_scene(manifest)
            manifest["_scene_plan"] = scene_plan
            log_stage("SCENE_PLAN", f"family={scene_plan.get('scene_family')}")
            print(f"DEBUG scene_plan attached: family={scene_plan.get('scene_family')}", flush=True)
        except Exception as e:
            print(f"DEBUG scene_director failed, builders use defaults: {e}", flush=True)
            manifest["_scene_plan"] = None
    else:
        manifest["_scene_plan"] = None

    # ── Scene Recipe: decompose prompt into structured layers ───────────
    # Pure data. world_builder reads manifest["scene_recipe"] to make smart
    # HDRI / ground / atmosphere / lighting / compositor choices. Never
    # overrides what the template already set — the recipe only INFORMS.
    if _HAS_RECIPE:
        try:
            # Normalize a loose dict for the recipe builder from manifest +
            # director plan + prompt_intelligence enrichment. The recipe
            # builder tolerates missing keys.
            _director_plan = manifest.get("_scene_plan") or {}
            _prompt_text = manifest.get("topic") or manifest.get("prompt") or ""
            _recipe_inputs: dict = {
                "focal_subject": _director_plan.get("focal_subject", ""),
                "subject":       _director_plan.get("focal_subject", ""),
                "environment":   (
                    _director_plan.get("environment")
                    or _director_plan.get("environment_preset")
                    or manifest.get("environment_ground_type")
                    or ""
                ),
                "animation_mode": _director_plan.get("animation_style", "idle"),
                "action":         _director_plan.get("animation_style", "idle"),
                "mood":           manifest.get("mood") or _director_plan.get("mood", "cinematic"),
                "time_of_day":    manifest.get("time_of_day", ""),
            }
            # Enrich with prompt_intelligence so "sunset", "night", "rain",
            # "park" etc. populate fields the director didn't supply.
            try:
                from app.services.prompt_intelligence import enrich_scene_plan
                _recipe_inputs = enrich_scene_plan(_prompt_text, _recipe_inputs)
                # enrich_scene_plan uses "environment_type" — mirror into
                # the field the recipe builder reads.
                if _recipe_inputs.get("environment_type") and not _recipe_inputs.get("environment"):
                    _recipe_inputs["environment"] = _recipe_inputs["environment_type"]
                if _recipe_inputs.get("animation") and not _recipe_inputs.get("action"):
                    _recipe_inputs["action"] = _recipe_inputs["animation"]
            except Exception as _e:
                print(f"[RECIPE] prompt_intelligence skipped: {_e}", flush=True)

            recipe = build_scene_recipe(_prompt_text, _recipe_inputs, manifest)
            manifest["scene_recipe"] = recipe
            log_stage("RECIPE_BUILT", f"env={recipe.get('summary', {}).get('environment')}")
            _sum = recipe.get("summary", {})
            print(
                f"[RECIPE] built: subject={_sum.get('subject')!r} "
                f"env={_sum.get('environment')!r} "
                f"action={_sum.get('action')!r} "
                f"time={_sum.get('time_of_day')!r} "
                f"mood={_sum.get('mood')!r} "
                f"hdri_kw={recipe.get('sky', {}).get('hdri_keywords', [])[:4]}",
                flush=True,
            )
        except Exception as e:
            print(f"[RECIPE] build_scene_recipe failed (non-fatal): {e}", flush=True)
            manifest["scene_recipe"] = None
    else:
        manifest["scene_recipe"] = None

    log_stage("TEMPLATE_DISPATCH", f"template={template}")
    try:
        if template == "city_loop":
            build_city_loop(bpy, manifest, scene)
        elif template in ("product_pedestal", "product_scene"):
            build_product_pedestal(bpy, manifest, scene) if template == "product_pedestal" else build_product_scene(bpy, manifest, scene)
        elif template == "street_scene":
            build_street_scene(bpy, manifest, scene)
        elif template == "ocean_scene":
            build_ocean_scene(bpy, manifest, scene)
        elif template == "scenic_landscape":
            build_scenic_landscape(bpy, manifest, scene)
        elif template == "car_hero":
            build_car_hero(bpy, manifest, scene)
        elif template == "character_stage":
            build_character_stage(bpy, manifest, scene)
        else:
            build_neon_news(bpy, manifest, scene)
    except Exception as e:
        print(f"DEBUG builder failed, using fallback scene: {e}", flush=True)
        build_fallback_scene(bpy, scene)
    log_stage("TEMPLATE_COMPLETE")

    # ══════════════════════════════════════════════════════════════════════
    # MULTI-ASSET COMPOSITION — import forced environment + place hero
    # ══════════════════════════════════════════════════════════════════════
    # Runs after the template has placed the hero but BEFORE ensure_basics /
    # world_dev scatter / framing.  When manifest["forced_environment_id"]
    # is set (resolved by asset_agent), import the environment asset as
    # a tagged-NOT-hero backdrop, scale to target, compute ground top Z,
    # then translate the hero so its bottom sits on that ground.  When no
    # forced_environment_id is present, this block is an entirely silent
    # no-op — Ferrari/existing flows unchanged.
    _env_ground_top_z = 0.0
    _forced_env_active = False
    try:
        _forced_env_path = str(manifest.get("forced_environment_path") or "").strip()
        _forced_env_entry = manifest.get("forced_environment_entry") or {}
        if _forced_env_path and _forced_env_entry:
            _forced_env_active = True
            _forced_env_use_as = str(_forced_env_entry.get("use_as") or "background_scenery").lower()
            _forced_env_scale_class = str(_forced_env_entry.get("scale_class") or "large").lower()

            # Env scale targets raised to feel cinematic — a 60m canyon
            # reads as a small prop behind a cat; a 200m canyon reads as
            # landscape. Flat-map detection (below) independently rescues
            # 2D satellite textures by repurposing them as ground tiles.
            _ENV_SCALE_TARGETS = {
                # background scenery — need to feel vast
                ("background_scenery", "small"):    40.0,
                ("background_scenery", "medium"):  100.0,
                ("background_scenery", "large"):   200.0,
                ("background_scenery", "huge"):    400.0,
                ("background_scenery", "xlarge"): 300.0,
                # ground replacement — large flat surface extending to horizon
                ("ground_replacement", "small"):    80.0,
                ("ground_replacement", "medium"):  150.0,
                ("ground_replacement", "large"):   300.0,
                ("ground_replacement", "huge"):    500.0,
                ("ground_replacement", "xlarge"): 300.0,
                # skybox — always max
                ("skybox",             "huge"):    500.0,
                ("skybox",             "large"):   350.0,
            }
            _env_target_size = _ENV_SCALE_TARGETS.get(
                (_forced_env_use_as, _forced_env_scale_class), 200.0,
            )

            print(
                f"[ENVIRONMENT] importing forced environment: {_forced_env_path}",
                flush=True,
            )
            print(
                f"[ENVIRONMENT] use_as={_forced_env_use_as!r} "
                f"scale_class={_forced_env_scale_class!r} "
                f"target_size={_env_target_size}m",
                flush=True,
            )

            # Snapshot scene object names BEFORE import so we can identify
            # everything the import produced.
            _before_env = {o.name for o in bpy.data.objects}
            _env_ext = os.path.splitext(_forced_env_path)[1].lower()
            try:
                if _env_ext in (".glb", ".gltf"):
                    bpy.ops.import_scene.gltf(filepath=_forced_env_path)
                elif _env_ext == ".fbx":
                    bpy.ops.import_scene.fbx(filepath=_forced_env_path)
                elif _env_ext == ".obj":
                    try:
                        bpy.ops.wm.obj_import(filepath=_forced_env_path)
                    except AttributeError:
                        bpy.ops.import_scene.obj(filepath=_forced_env_path)
                elif _env_ext == ".blend":
                    with bpy.data.libraries.load(_forced_env_path, link=False) as (_src, _dst):
                        _dst.objects = list(_src.objects)
                    for _o in _dst.objects:
                        if _o is not None:
                            bpy.context.collection.objects.link(_o)
                else:
                    print(f"[ENVIRONMENT] WARN: unsupported format {_env_ext!r}", flush=True)
                    _forced_env_active = False
            except Exception as _env_imp_err:
                import traceback as _env_tb
                print(f"[ENVIRONMENT] import failed: {_env_imp_err}", flush=True)
                print(_env_tb.format_exc(), flush=True)
                _forced_env_active = False

            if _forced_env_active:
                _env_new_names = {o.name for o in bpy.data.objects} - _before_env
                _env_new_objects = [
                    bpy.data.objects[n] for n in _env_new_names
                    if n in bpy.data.objects
                ]
                _env_meshes = [o for o in _env_new_objects if o.type == "MESH"]
                _env_parentless = [o for o in _env_new_objects if o.parent is None]

                # Tag as environment — NOT hero.  Prevents hero tagger /
                # FRAME_FIX / CAMERA_FIX from framing canyon walls.
                for _o in _env_new_objects:
                    try:
                        _o["is_environment"] = True
                        _o["is_forced_environment"] = True
                        _o["is_world_dev"] = True  # downstream hero-filter skip
                        _o["is_hero"] = False
                    except Exception:
                        pass

                # V1.2 heal-apply: rotation + ground_offset from library entry.
                # Done BEFORE scale so healed orientation propagates into the
                # subsequent bbox measurements and ground_top_z computation.
                try:
                    for _root in _env_parentless:
                        _apply_healed_transforms(_root, _forced_env_entry, role="environment")
                except Exception as _heal_env_err:
                    print(f"[HEAL_APPLY] env heal failed: {_heal_env_err}", flush=True)

                # Combined world-space bbox of all imported meshes
                from mathutils import Vector as _EnvVec
                _env_coords = []
                for _em in _env_meshes:
                    try:
                        mw = _em.matrix_world
                        for _c in _em.bound_box:
                            _env_coords.append(mw @ _EnvVec(_c))
                    except Exception:
                        pass

                if _env_coords and _env_parentless:
                    _env_mn = _EnvVec((
                        min(c.x for c in _env_coords),
                        min(c.y for c in _env_coords),
                        min(c.z for c in _env_coords),
                    ))
                    _env_mx = _EnvVec((
                        max(c.x for c in _env_coords),
                        max(c.y for c in _env_coords),
                        max(c.z for c in _env_coords),
                    ))
                    _env_bbox_w = _env_mx.x - _env_mn.x
                    _env_bbox_d = _env_mx.y - _env_mn.y
                    _env_bbox_h = _env_mx.z - _env_mn.z
                    _env_current = max(_env_bbox_w, _env_bbox_d, _env_bbox_h, 0.001)

                    # ── Flat-map detection (per-mesh + metadata-first) ──
                    # PRIORITY 1: library.json metadata set by the one-off
                    # classifier script — trusted source, avoids runtime
                    # analysis.  PRIORITY 2: per-mesh thinness check — the
                    # UNION bbox is unreliable because stacked flat planes
                    # report tall union bboxes even though each plane is
                    # paper-thin.  Check the MAJORITY of individual meshes.
                    _env_horiz_extent = max(_env_bbox_w, _env_bbox_d, 0.001)
                    _shape_class_meta = str(_forced_env_entry.get("shape_class") or "").strip().lower()
                    _is_flat_map = False
                    _flat_src = ""
                    if _shape_class_meta:
                        _is_flat_map = (_shape_class_meta == "flat_map")
                        _flat_src = f"library_metadata={_shape_class_meta!r}"
                        print(
                            f"[ENVIRONMENT] library metadata: "
                            f"shape_class={_shape_class_meta!r}",
                            flush=True,
                        )
                    else:
                        # Per-mesh thinness — classifies on majority vote.
                        # A mesh is "flat" when its thinnest dim is < 10%
                        # of its largest.
                        _flat_n = 0
                        _total_n = 0
                        for _em in _env_meshes:
                            try:
                                _em_dims = list(_em.dimensions)
                            except Exception:
                                continue
                            if not _em_dims or max(_em_dims) < 0.001:
                                continue
                            _total_n += 1
                            _sd = sorted(_em_dims)
                            if _sd[0] / max(_sd[2], 0.001) < 0.10:
                                _flat_n += 1
                        if _total_n > 0:
                            _flat_frac = _flat_n / _total_n
                            _is_flat_map = _flat_frac >= 0.60
                            _flat_src = (
                                f"per_mesh_check={_flat_n}/{_total_n} "
                                f"flat_planes (threshold=60%)"
                            )
                            print(
                                f"[ENVIRONMENT] shape analysis: "
                                f"{_flat_n}/{_total_n} meshes are flat planes "
                                f"(threshold: 60%) -> "
                                f"{'FLAT' if _is_flat_map else '3D'}",
                                flush=True,
                            )
                        else:
                            _flat_src = "no_meshes_analyzed"
                            print(
                                "[ENVIRONMENT] shape analysis: no analyzable meshes",
                                flush=True,
                            )

                    if _is_flat_map:
                        # ── Repurpose as oversized ground texture tile ─
                        # Previous implementation just multiplied
                        # ``_er.scale`` on each parentless root.  In
                        # practice, Sketchfab flat-maps use nested parent
                        # hierarchies where local-space dimensions don't
                        # reflect the world-scale change — downstream
                        # `obj.dimensions` still reads the pre-scale
                        # value, and `bound_box` re-computation returns
                        # zero because Blender caches local values.
                        #
                        # Fix: use ``bpy.ops.object.transform_apply`` to
                        # BAKE the scale into mesh data so every
                        # downstream query sees the correct size.  Then
                        # detect the flat axis and rotate the plane to
                        # lay horizontal (lots of satellite-map glbs
                        # come oriented Y-up or X-up — if we don't
                        # rotate, the ground is a vertical billboard).
                        print(
                            f"[ENVIRONMENT] WARN: "
                            f"{_forced_env_entry.get('id')!r} classified as "
                            f"flat 2D map ({_flat_src}) — "
                            f"repurposing as 200m ground texture",
                            flush=True,
                        )

                        _env_ground_target = 200.0

                        # 1. Measure WORLD-SPACE vertices (not bound_box)
                        # so we capture actual rendered geometry, including
                        # parent-transform effects.
                        _flat_world_coords = []
                        for _em in _env_meshes:
                            try:
                                mw = _em.matrix_world
                                if _em.data and hasattr(_em.data, "vertices"):
                                    for _v in _em.data.vertices:
                                        _flat_world_coords.append(mw @ _v.co)
                            except Exception:
                                pass
                        if not _flat_world_coords:
                            # Fallback to bound_box if vertex access fails
                            for _em in _env_meshes:
                                try:
                                    mw = _em.matrix_world
                                    for _c in _em.bound_box:
                                        _flat_world_coords.append(mw @ _EnvVec(_c))
                                except Exception:
                                    pass

                        if _flat_world_coords:
                            _flat_w = max(c.x for c in _flat_world_coords) - min(c.x for c in _flat_world_coords)
                            _flat_d = max(c.y for c in _flat_world_coords) - min(c.y for c in _flat_world_coords)
                            _flat_h = max(c.z for c in _flat_world_coords) - min(c.z for c in _flat_world_coords)
                            print(
                                f"[ENVIRONMENT] pre-repurpose world bbox: "
                                f"{_flat_w:.2f}x{_flat_d:.2f}x{_flat_h:.2f}m",
                                flush=True,
                            )
                            _flat_current_extent = max(_flat_w, _flat_d, 0.001)
                        else:
                            _flat_w = _flat_d = _flat_h = 0.0
                            _flat_current_extent = max(_env_horiz_extent, 0.001)
                            print(
                                "[ENVIRONMENT] WARN: could not measure flat env — "
                                "using union bbox horiz extent",
                                flush=True,
                            )

                        _env_ground_scale = _env_ground_target / _flat_current_extent
                        _env_ground_scale = max(0.001, min(1000.0, _env_ground_scale))

                        # 2. Apply scale to all parentless roots
                        for _er in _env_parentless:
                            _er.scale = tuple(s * _env_ground_scale for s in _er.scale)
                        bpy.context.view_layer.update()

                        # 3. Bake the scale into mesh data via
                        # transform_apply so downstream sees correct dims
                        try:
                            bpy.ops.object.select_all(action='DESELECT')
                            _selected_count = 0
                            for _ebobj in _env_new_objects:
                                try:
                                    _ebobj.select_set(True)
                                    _selected_count += 1
                                except Exception:
                                    pass
                            if _env_parentless:
                                bpy.context.view_layer.objects.active = _env_parentless[0]
                            if _selected_count > 0:
                                bpy.ops.object.transform_apply(
                                    location=False, rotation=False, scale=True,
                                )
                                print(
                                    f"[ENVIRONMENT] transform_apply baked scale into "
                                    f"{_selected_count} object(s)",
                                    flush=True,
                                )
                        except Exception as _ta_err:
                            print(
                                f"[ENVIRONMENT] WARN: transform_apply failed "
                                f"({_ta_err}) — meshes may still render "
                                f"oversized/undersized",
                                flush=True,
                            )
                        bpy.context.view_layer.update()

                        # 4. Re-measure after bake, detect flat axis,
                        # rotate to lay the plane horizontal.
                        _flat_post_coords = []
                        for _em in _env_meshes:
                            try:
                                mw = _em.matrix_world
                                if _em.data and hasattr(_em.data, "vertices"):
                                    for _v in _em.data.vertices:
                                        _flat_post_coords.append(mw @ _v.co)
                            except Exception:
                                pass
                        if not _flat_post_coords:
                            for _em in _env_meshes:
                                try:
                                    mw = _em.matrix_world
                                    for _c in _em.bound_box:
                                        _flat_post_coords.append(mw @ _EnvVec(_c))
                                except Exception:
                                    pass

                        if _flat_post_coords:
                            _post_w = max(c.x for c in _flat_post_coords) - min(c.x for c in _flat_post_coords)
                            _post_d = max(c.y for c in _flat_post_coords) - min(c.y for c in _flat_post_coords)
                            _post_h = max(c.z for c in _flat_post_coords) - min(c.z for c in _flat_post_coords)
                            _post_dims = [_post_w, _post_d, _post_h]
                            _thin_axis = _post_dims.index(min(_post_dims))

                            import math as _math_rot
                            if _thin_axis == 1:  # Y thin → rotate around X
                                for _er in _env_parentless:
                                    _er.rotation_euler = (
                                        _er.rotation_euler[0] + _math_rot.pi / 2,
                                        _er.rotation_euler[1],
                                        _er.rotation_euler[2],
                                    )
                                bpy.context.view_layer.update()
                                print(
                                    "[ENVIRONMENT] rotated 90° around X — "
                                    "laying flat-map horizontal (was Y-thin)",
                                    flush=True,
                                )
                            elif _thin_axis == 0:  # X thin → rotate around Y
                                for _er in _env_parentless:
                                    _er.rotation_euler = (
                                        _er.rotation_euler[0],
                                        _er.rotation_euler[1] + _math_rot.pi / 2,
                                        _er.rotation_euler[2],
                                    )
                                bpy.context.view_layer.update()
                                print(
                                    "[ENVIRONMENT] rotated 90° around Y — "
                                    "laying flat-map horizontal (was X-thin)",
                                    flush=True,
                                )
                            # _thin_axis == 2 means Z is already the thin
                            # axis — plane is already horizontal; no rotation

                        # 5. Re-measure AGAIN post-rotation, snap bottom to z=0
                        _flat_final_coords = []
                        for _em in _env_meshes:
                            try:
                                mw = _em.matrix_world
                                if _em.data and hasattr(_em.data, "vertices"):
                                    for _v in _em.data.vertices:
                                        _flat_final_coords.append(mw @ _v.co)
                            except Exception:
                                pass
                        if not _flat_final_coords:
                            for _em in _env_meshes:
                                try:
                                    mw = _em.matrix_world
                                    for _c in _em.bound_box:
                                        _flat_final_coords.append(mw @ _EnvVec(_c))
                                except Exception:
                                    pass
                        if _flat_final_coords:
                            _flat_final_min_z = min(c.z for c in _flat_final_coords)
                            if abs(_flat_final_min_z) > 0.01:
                                for _er in _env_parentless:
                                    _er.location.z -= _flat_final_min_z
                                bpy.context.view_layer.update()
                            _flat_final_w = max(c.x for c in _flat_final_coords) - min(c.x for c in _flat_final_coords)
                            _flat_final_d = max(c.y for c in _flat_final_coords) - min(c.y for c in _flat_final_coords)
                            _flat_final_h = max(c.z for c in _flat_final_coords) - min(c.z for c in _flat_final_coords)
                            print(
                                f"[ENVIRONMENT] repurposed as ground: "
                                f"factor={_env_ground_scale:.3f}x "
                                f"target={_env_ground_target:.1f}m "
                                f"pre_extent={_flat_current_extent:.2f}m "
                                f"post_dims={_flat_final_w:.1f}x"
                                f"{_flat_final_d:.1f}x{_flat_final_h:.1f}m "
                                f"bottom snapped to z=0",
                                flush=True,
                            )
                        else:
                            print(
                                f"[ENVIRONMENT] repurposed as ground: scaled by "
                                f"{_env_ground_scale:.3f}x (post-measurement failed)",
                                flush=True,
                            )

                        # Mark for downstream: hero uses world z=0, not env surface
                        manifest["_env_used_as_ground"] = True
                        manifest["_env_is_flat"] = True
                        _env_ground_top_z = 0.0
                        manifest["_env_ground_top_z"] = 0.0
                        # Skip the rest of the 3D-backdrop scale block below
                        # but still mark forced env active for camera adjust
                        manifest["_has_forced_environment"] = True
                        # Jump out of 3D path: nothing else to do for a flat env
                        _env_parentless = []  # signal: don't run the 3D scale path

                    # V1.3 batch-2 fix: clamp env scale factor to a sane
                    # range.  Previously a 3.44m diorama env scaled 87x to
                    # 300m target would place heroes at z=297m, camera
                    # couldn't follow, the hero was invisible.  15x upscale
                    # / 20x downscale is the hard ceiling — heroes framed
                    # on absurdly wrong-size env assets degrade gracefully
                    # (env looks too small in frame) instead of catastrophically
                    # (hero lost in the sky).
                    _ENV_MAX_UPSCALE = 15.0
                    _ENV_MIN_DOWNSCALE = 0.05
                    _env_raw_scale = _env_target_size / _env_current
                    _env_scale_factor = max(
                        _ENV_MIN_DOWNSCALE,
                        min(_env_raw_scale, _ENV_MAX_UPSCALE),
                    )
                    if abs(_env_scale_factor - _env_raw_scale) > 1e-4:
                        _shape_cls = str(_forced_env_entry.get("shape_class") or "unknown")
                        print(
                            f"[ENVIRONMENT] scale clamped: raw={_env_raw_scale:.2f} "
                            f"-> {_env_scale_factor:.2f} "
                            f"(target={_env_target_size}m current={_env_current:.2f}m "
                            f"shape={_shape_cls!r})",
                            flush=True,
                        )

                    # Scale every parentless root so the whole group scales together
                    # (skipped when flat-map path cleared _env_parentless)
                    for _er in _env_parentless:
                        _er.scale = tuple(s * _env_scale_factor for s in _er.scale)
                    bpy.context.view_layer.update()

                    # ── Bottom-snap 3D env to z=0 ──────────────────────
                    # A Sketchfab terrain may have its origin at z=0 but
                    # geometry at z=56-92m (glacier example).  Snap the
                    # bottom of the combined mesh bbox to world z=0 so
                    # downstream placement, camera, and lighting all
                    # operate in the normal coordinate range (0-10m rel.
                    # to ground instead of 56-92m).
                    _env_snap_coords = []
                    if not manifest.get("_env_used_as_ground"):
                        for _em in _env_meshes:
                            try:
                                mw = _em.matrix_world
                                for _c in _em.bound_box:
                                    _env_snap_coords.append(mw @ _EnvVec(_c))
                            except Exception:
                                pass
                    if _env_snap_coords and _env_parentless:
                        _env_pre_min_z = min(c.z for c in _env_snap_coords)
                        _env_pre_max_z = max(c.z for c in _env_snap_coords)
                        print(
                            f"[ENVIRONMENT] post-scale bbox: "
                            f"min_z={_env_pre_min_z:.2f} max_z={_env_pre_max_z:.2f}",
                            flush=True,
                        )
                        _env_snap_dz = -_env_pre_min_z
                        if abs(_env_snap_dz) > 0.01:
                            for _er in _env_parentless:
                                _er.location.z += _env_snap_dz
                            bpy.context.view_layer.update()
                            print(
                                f"[ENVIRONMENT] bottom-snapped: translated env by "
                                f"dz={_env_snap_dz:.2f}m so bottom sits at z=0",
                                flush=True,
                            )

                    # Re-measure after scale + bottom-snap.
                    _env_new_coords = []
                    if not manifest.get("_env_used_as_ground"):
                        for _em in _env_meshes:
                            try:
                                mw = _em.matrix_world
                                for _c in _em.bound_box:
                                    _env_new_coords.append(mw @ _EnvVec(_c))
                            except Exception:
                                pass
                    if _env_new_coords:
                        _env_min_z_now = min(c.z for c in _env_new_coords)
                        _env_max_z_now = max(c.z for c in _env_new_coords)
                        # Ground top Z: after bottom-snap, min_z ≈ 0.
                        # Hero sits on world z=0 which is also the env
                        # floor.  Raycast-based per-XY surface sampling
                        # is a future improvement (a hero that lands in
                        # a valley will be at the valley's floor; on a
                        # peak, on the peak).
                        _env_ground_top_z = _env_min_z_now
                        manifest["_env_ground_top_z"] = float(_env_ground_top_z)
                        manifest["_has_forced_environment"] = True
                        print(
                            f"[ENVIRONMENT] 3D terrain detected — using as backdrop",
                            flush=True,
                        )
                        print(
                            f"[ENVIRONMENT] ground reference for hero placement: "
                            f"z={_env_ground_top_z:.3f}",
                            flush=True,
                        )
                        print(
                            f"[ENVIRONMENT] placed {_env_parentless[0].name!r} "
                            f"scale_factor={_env_scale_factor:.4f} "
                            f"(target={_env_target_size}m was {_env_current:.2f}m) "
                            f"ground_top_z={_env_ground_top_z:.3f} "
                            f"env_bounds_z=[{_env_min_z_now:.2f},{_env_max_z_now:.2f}]",
                            flush=True,
                        )
                    else:
                        print("[ENVIRONMENT] WARN: env has no mesh bbox after scale", flush=True)
                else:
                    print(
                        f"[ENVIRONMENT] WARN: no parentless roots or no mesh bbox — "
                        f"parentless={len(_env_parentless)} meshes={len(_env_meshes)}",
                        flush=True,
                    )

                # ── Hero placement: raycast env surface under hero XY ─────
                # Round 4.1: instead of snapping hero to env min_z (valley
                # floor even when hero sits over a ridge), we cast a ray
                # straight down from above the hero's XY centroid onto
                # is_environment meshes. The first hit is the actual
                # surface Z at that point.  Falls back to _env_ground_top_z
                # when the raycast misses (hero standing over a hole / off
                # the env's footprint).
                try:
                    _hero_meshes_place = [
                        o for o in bpy.data.objects
                        if o.type == "MESH"
                        and o.get("is_hero", False)
                        and not o.get("is_environment", False)
                    ]
                    if _hero_meshes_place:
                        _hero_coords = []
                        for _hm in _hero_meshes_place:
                            try:
                                mw = _hm.matrix_world
                                for _c in _hm.bound_box:
                                    _hero_coords.append(mw @ _EnvVec(_c))
                            except Exception:
                                pass
                        if _hero_coords:
                            _hero_min_z = min(c.z for c in _hero_coords)
                            _hero_cx = sum(c.x for c in _hero_coords) / len(_hero_coords)
                            _hero_cy = sum(c.y for c in _hero_coords) / len(_hero_coords)

                            # ══════════════════════════════════════════
                            # V1.3.5 Fix 3 — multi-hit ground raycast
                            # ══════════════════════════════════════════
                            # Old code: ray_cast returns FIRST hit per
                            # mesh, picks the max across meshes.  For
                            # complex terrain the first hit might be a
                            # cliff face / overhang far above the actual
                            # walkable surface, missing the dune top
                            # below it.  New: walk the ray repeatedly
                            # from each prior hit minus epsilon, collect
                            # ALL hits per mesh, then pick the highest
                            # hit globally that has an upward-facing
                            # normal (the actual top surface).
                            _ray_origin = _EnvVec((_hero_cx, _hero_cy, 1000.0))
                            _ray_dir = _EnvVec((0.0, 0.0, -1.0))
                            _env_surface_hits: list[float] = []
                            _env_meshes_for_ray = [
                                o for o in bpy.data.objects
                                if o.type == "MESH" and o.get("is_environment", False)
                            ]
                            _MAX_HITS_PER_MESH = 8
                            _RAY_EPSILON = 0.001
                            for _em_ray in _env_meshes_for_ray:
                                try:
                                    _mw_inv = _em_ray.matrix_world.inverted()
                                    _local_o = _mw_inv @ _ray_origin
                                    _local_d = (_mw_inv.to_3x3() @ _ray_dir).normalized()
                                    _cur_o = _local_o
                                    for _hit_i in range(_MAX_HITS_PER_MESH):
                                        _hit, _loc, _nrm, _idx = _em_ray.ray_cast(_cur_o, _local_d)
                                        if not _hit:
                                            break
                                        _world_hit = _em_ray.matrix_world @ _loc
                                        # Transform normal to world space; prefer
                                        # surfaces whose normal points up (z > 0).
                                        try:
                                            _world_nrm = (
                                                _em_ray.matrix_world.to_3x3() @ _nrm
                                            ).normalized()
                                            _norm_up = _world_nrm.z
                                        except Exception:
                                            _norm_up = 1.0  # accept on transform error
                                        # Only top-facing surfaces qualify as ground
                                        if _norm_up > 0.1:
                                            _env_surface_hits.append(float(_world_hit.z))
                                        # Step past this hit to find the next one.
                                        # Local-space step: move past _loc by
                                        # epsilon along ray direction.
                                        _cur_o = _loc + _local_d * _RAY_EPSILON
                                except Exception:
                                    pass
                            if _env_surface_hits:
                                _target_z = max(_env_surface_hits)
                                _place_method = "raycast_multihit"
                            else:
                                _target_z = _env_ground_top_z
                                _place_method = "fallback_min_z"

                            _hero_dz = _target_z - _hero_min_z
                            # Find hero root to translate (top-level parent)
                            _hero_roots_place = set()
                            for _hm in _hero_meshes_place:
                                _cur = _hm
                                while _cur.parent is not None:
                                    _cur = _cur.parent
                                _hero_roots_place.add(_cur)
                            for _hr in _hero_roots_place:
                                _hr.location.z += _hero_dz
                            bpy.context.view_layer.update()
                            manifest["_env_ground_top_z"] = float(_target_z)
                            print(
                                f"[HERO_PLACE] method={_place_method} "
                                f"hero XY=({_hero_cx:.2f},{_hero_cy:.2f}) "
                                f"hero bottom z was {_hero_min_z:.3f}, "
                                f"env surface z={_target_z:.3f}, "
                                f"moved by dz={_hero_dz:.3f} "
                                f"({len(_hero_roots_place)} root(s), "
                                f"{len(_env_surface_hits)} ray hits)",
                                flush=True,
                            )
                        else:
                            print(
                                "[HERO_PLACE] skipped — no hero bbox available",
                                flush=True,
                            )
                    else:
                        print(
                            "[HERO_PLACE] skipped — no is_hero meshes in scene "
                            "(template may import later or use placeholder)",
                            flush=True,
                        )
                except Exception as _place_err:
                    import traceback as _place_tb
                    print(f"[HERO_PLACE] failed (non-fatal): {_place_err}", flush=True)
                    print(_place_tb.format_exc(), flush=True)

                # Tell world_dev to skip synthetic scatter — the real
                # environment asset replaces it.
                manifest["_skip_synthetic_scatter"] = True
                # Mark env + hero placement authoritative so downstream
                # helpers (AERIAL_GUARD, VERIFY re-ground, FORCE_FIX hero
                # reposition) skip their corrective work.  Without this
                # gate, AERIAL_GUARD snaps the camera back to z≈1.77
                # thinking the high-Z was a top-down shot error; VERIFY
                # re-grounds the hero to z=0 undoing env placement.
                manifest["_env_placement_final"] = True
                print(
                    "[WORLD_DEV] synthetic scatter SKIPPED — forced environment asset in use",
                    flush=True,
                )

                # ── Round 4.2: template noise cleanup ──────────────────
                # Some templates create their own fake backdrop (curbs,
                # lane stripes, distant hills, atmospheric haze planes).
                # With a real environment asset those clash visually and
                # often punch through the terrain.  Strip them here —
                # only meshes matching known-noise name prefixes, and
                # never anything tagged is_hero / is_environment /
                # is_forced_hero (belt-and-suspenders guard).
                #
                # Exception: the car_hero / street templates rely on
                # curb + lanestripe geometry as the actual driving
                # surface.  Skip cleanup when template_name starts with
                # "car" or "street" so we don't break their scenes.
                try:
                    _tmpl_name = str(manifest.get("template_name") or "").lower()
                    _NOISE_PREFIXES = (
                        "background_building", "curb_l", "curb_r",
                        "distanthills_", "distanthill_",
                        "atmo_far", "atmo_near", "atmo_haze",
                        "streetground", "lanestripe", "lane_stripe",
                        "road_marking", "roadmarking",
                    )
                    _skip_cleanup = _tmpl_name.startswith(("car", "street"))
                    if _skip_cleanup:
                        print(
                            f"[NOISE_CLEAN] SKIPPED — template={_tmpl_name!r} "
                            f"relies on curb/lane/road geometry",
                            flush=True,
                        )
                    else:
                        _removed_names: list[str] = []
                        for _obj in list(bpy.data.objects):
                            if _obj.type != "MESH":
                                continue
                            if _obj.get("is_hero", False):
                                continue
                            if _obj.get("is_forced_hero", False):
                                continue
                            if _obj.get("is_environment", False):
                                continue
                            _nm = str(_obj.name or "").lower()
                            for _pfx in _NOISE_PREFIXES:
                                if _nm.startswith(_pfx):
                                    _removed_names.append(_obj.name)
                                    try:
                                        bpy.data.objects.remove(_obj, do_unlink=True)
                                    except Exception:
                                        pass
                                    break
                        if _removed_names:
                            print(
                                f"[NOISE_CLEAN] removed {len(_removed_names)} "
                                f"template-noise mesh(es) under forced env: "
                                f"{_removed_names[:8]}"
                                + ("..." if len(_removed_names) > 8 else ""),
                                flush=True,
                            )
                        else:
                            print("[NOISE_CLEAN] no template noise found", flush=True)
                except Exception as _nc_err:
                    print(f"[NOISE_CLEAN] failed (non-fatal): {_nc_err}", flush=True)

                # ── Env-aware camera adjust ────────────────────────────
                # With a real environment present, pull camera back and
                # widen the lens so both hero AND backdrop are visible.
                # Target: hero fills ~30% of frame (vs ~80% for solo
                # hero). This sets cam position + lens BEFORE CAMERA_FIX
                # runs; CAMERA_FIX will then see _camera_env_adjusted and
                # skip its own static-pose override.
                try:
                    _env_hero_meshes = [
                        o for o in bpy.data.objects
                        if o.type == "MESH"
                        and o.get("is_hero", False)
                        and not o.get("is_environment", False)
                    ]
                    if _env_hero_meshes:
                        _ec_coords = []
                        for _ehm in _env_hero_meshes:
                            try:
                                mw = _ehm.matrix_world
                                for _c in _ehm.bound_box:
                                    _ec_coords.append(mw @ _EnvVec(_c))
                            except Exception:
                                pass
                        if _ec_coords:
                            _ehc = _EnvVec((
                                (min(c.x for c in _ec_coords) + max(c.x for c in _ec_coords)) * 0.5,
                                (min(c.y for c in _ec_coords) + max(c.y for c in _ec_coords)) * 0.5,
                                (min(c.z for c in _ec_coords) + max(c.z for c in _ec_coords)) * 0.5,
                            ))
                            _ehw = max(c.x for c in _ec_coords) - min(c.x for c in _ec_coords)
                            _ehd = max(c.y for c in _ec_coords) - min(c.y for c in _ec_coords)
                            _ehh = max(c.z for c in _ec_coords) - min(c.z for c in _ec_coords)
                            _ehdiag = max(_ehw, _ehd, _ehh, 0.5)

                            _env_cam = bpy.context.scene.camera
                            if _env_cam is not None:
                                # V1.3.2 — defer to camera director. Old
                                # vector-preserving math + _pick_camera_distance_for_hero
                                # bucket lookup both replaced by director.
                                _cam_mn = (
                                    min(c.x for c in _ec_coords),
                                    min(c.y for c in _ec_coords),
                                    min(c.z for c in _ec_coords),
                                )
                                _cam_mx = (
                                    max(c.x for c in _ec_coords),
                                    max(c.y for c in _ec_coords),
                                    max(c.z for c in _ec_coords),
                                )
                                _profile = _director_profile_for_manifest(manifest)
                                _apply_director_to_camera(
                                    _env_cam,
                                    (_cam_mn, _cam_mx),
                                    _profile,
                                    manifest,
                                    "CAMERA_ENV_FORCED",
                                )
                                manifest["_camera_env_adjusted"] = True
                        else:
                            print(
                                "[CAMERA_ENV] skipped — no hero bbox available",
                                flush=True,
                            )
                    else:
                        print(
                            "[CAMERA_ENV] skipped — no is_hero meshes for camera framing",
                            flush=True,
                        )
                except Exception as _cam_env_err:
                    import traceback as _cam_env_tb
                    print(f"[CAMERA_ENV] failed (non-fatal): {_cam_env_err}", flush=True)
                    print(_cam_env_tb.format_exc(), flush=True)

                # ── V1.3 batch-2 Bug C: deterministic camera→hero tracking ──
                # The vector-math adjustment above can leave the camera at
                # a z that's too low for heroes lifted onto tall terrain
                # (e.g. horse on a 26m mountain ridge, camera at z=7).
                # For scenic_landscape renders we override with a direct,
                # deterministic placement: camera at hero.y − framing_dist,
                # z = hero.z + hero_size*0.6, aimed at hero.
                # Gated OFF for car_hero (Ferrari has choreographed camera
                # animation we must not stomp) and for any scene flagged
                # _camera_is_directed_animation.
                try:
                    _tn = str(manifest.get("template_name") or "").lower()
                    _tpl_recipe = str(manifest.get("_template_v2_recipe") or "").lower()
                    _is_scenic = (
                        _tn == "scenic_landscape"
                        or _tpl_recipe in {
                            "hero_mountain_establishing",
                            "cat_canyon_cinematic",
                            "hero_desert_epic",
                            "hero_forest_intimate",
                            "hero_castle_dramatic",
                            "animal_mountain_walk",
                            "animal_forest_intimate",
                        }
                    )
                    _is_directed = bool(manifest.get("_camera_is_directed_animation"))
                    if _is_scenic and not _is_directed and _env_hero_meshes and _ec_coords:
                        _cam = bpy.context.scene.camera
                        if _cam is not None:
                            # V1.3.2 — this pass also defers to the director.
                            # Previously used a distinct 4x multiplier + 50mm
                            # hardcoded; the director produces the same result
                            # as the CAMERA_ENV_FORCED call above, guaranteeing
                            # consistency.
                            _mn2 = (
                                min(c.x for c in _ec_coords),
                                min(c.y for c in _ec_coords),
                                min(c.z for c in _ec_coords),
                            )
                            _mx2 = (
                                max(c.x for c in _ec_coords),
                                max(c.y for c in _ec_coords),
                                max(c.z for c in _ec_coords),
                            )
                            _apply_director_to_camera(
                                _cam,
                                (_mn2, _mx2),
                                _director_profile_for_manifest(manifest),
                                manifest,
                                "CAMERA_ENV_TRACKED",
                            )
                            manifest["_camera_tracked_to_hero"] = True
                    elif _is_directed:
                        print(
                            "[CAMERA_ENV] tracking skipped — "
                            "_camera_is_directed_animation flag set",
                            flush=True,
                        )
                    elif not _is_scenic:
                        print(
                            f"[CAMERA_ENV] tracking skipped — template_name={_tn!r} "
                            f"recipe={_tpl_recipe!r} not a scenic_landscape variant",
                            flush=True,
                        )
                except Exception as _track_err:
                    import traceback as _track_tb
                    print(f"[CAMERA_ENV] tracking failed (non-fatal): {_track_err}", flush=True)
                    print(_track_tb.format_exc(), flush=True)
    except Exception as _env_outer_err:
        import traceback as _env_outer_tb
        print(f"[ENVIRONMENT] outer error (non-fatal): {_env_outer_err}", flush=True)
        print(_env_outer_tb.format_exc(), flush=True)
    log_stage("FORCED_ENVIRONMENT")

    # ── FIX 5: Default-primitive sweep ──────────────────────────────────
    # Even though clear_scene() runs before the template, some templates
    # add named primitives ("Cube", "Sphere", "Cylinder") as scratch
    # geometry and forget to rename or remove them. If those survive to
    # render, they appear as the mysterious white sphere-and-cylinder
    # on the ground plane. Sweep them here — only objects with exact
    # default names are removed, template-renamed geometry is kept.
    if _HAS_ASSET_IMPORT:
        _removed = clean_default_primitives(bpy)
        if _removed:
            print(f"DEBUG cleaned {_removed} default primitive(s) after build", flush=True)

    # ── ISSUE 5: Scene-basics guarantor ────────────────────────────────
    # Belt-and-braces safety net so every render has sky + ground +
    # grounded hero + camera + light. Templates should cover all of
    # this themselves; ensure_scene_basics only fills gaps so a broken
    # template can't produce a blank or floating render.
    if _HAS_ASSET_IMPORT:
        try:
            # Hero objects aren't tracked here — pass None and let
            # ensure_scene_basics skip the grounding step. Templates
            # that do track hero roots call this themselves.
            ensure_scene_basics(bpy, hero_objects=None)
        except Exception as e:
            print(f"DEBUG ensure_scene_basics failed (non-fatal): {e}", flush=True)
    log_stage("ENSURE_BASICS")

    # ── Round 9 Pillar 2: Cinematic environment gap-fillers ─────────────
    # build_environment_layers adds atmosphere, 3-point lighting, ground
    # material, and a contact shadow under the hero. It never clobbers
    # template-provided assets — each helper checks what's already there
    # and only fills gaps. Safe to run on every render.
    if _HAS_ENV_OPS:
        try:
            # Best-effort hero discovery for contact-shadow + key-light
            # aim. Anything that looks like a hero (not named Ground*/
            # Sky*/ContactShadow*/Camera*/Light*) and has mesh data.
            hero_candidates: list = []
            _skip_prefixes = (
                "ground", "sky", "backdrop", "contactshadow", "camera",
                "light", "cinematic", "hemi", "sun", "area", "point",
                "road", "street",
            )
            for obj in bpy.data.objects:
                if obj.type != "MESH":
                    continue
                lname = obj.name.lower()
                if any(lname.startswith(p) for p in _skip_prefixes):
                    continue
                hero_candidates.append(obj)
            build_environment_layers(
                bpy, scene, manifest, hero_objects=hero_candidates or None,
            )
        except Exception as e:
            print(f"DEBUG build_environment_layers failed (non-fatal): {e}", flush=True)
    log_stage("ENV_LAYERS")

    # ── ENVIRONMENT PRESET — data-driven environment enrichment ─────────
    # Matches the prompt against 20 cinematic environment presets and
    # applies ground color, lighting overrides, atmosphere, and optional
    # background geometry ON TOP of whatever the template already built.
    #
    # V1.3.6 Fix 4: when a forced_environment_id is set, the env asset
    # has already supplied environment styling — running the preset
    # match on top causes dual styling (e.g. desert preset color cast
    # over a placed mountain asset). Skip in that case.
    if manifest.get("forced_environment_id"):
        print(
            "[ENV_PRESET] SKIPPED — forced env active "
            f"(forced_environment_id={manifest.get('forced_environment_id')!r})",
            flush=True,
        )
    else:
        try:
            from app.scene.environment_builder import match_preset, apply_preset

            _prompt_text = str(manifest.get("core_objective_prompt") or "")
            _scene_params = manifest.get("scene_params") or {}
            if isinstance(_scene_params, str):
                _env_text = _scene_params
            else:
                _env_text = str(_scene_params.get("environment", ""))

            _preset_name, _preset = match_preset(_prompt_text, _env_text)
            if _preset:
                print(
                    f"[ENV_PRESET] matched: {_preset_name!r} for prompt: "
                    f"{_prompt_text[:60]!r}",
                    flush=True,
                )
                apply_preset(bpy, _preset, scene)

                # Store camera profile from preset for CAMERA_FIX to use
                _cam_profile = _preset.get("camera", {})
                if _cam_profile:
                    manifest["_env_camera_profile"] = _cam_profile
            else:
                print(
                    "[ENV_PRESET] no match for prompt — using base template",
                    flush=True,
                )
        except Exception as _ep_err:
            print(f"[ENV_PRESET] error (non-fatal): {_ep_err}", flush=True)
    log_stage("ENV_PRESET")

    # ── Round 12: MANDATORY environment safety net ──────────────────────
    # Runs AFTER build_environment_layers so it only fills genuine gaps.
    # Guarantees the render never ships as a flat gray void: if the
    # template + Round 9/10 helpers somehow left no sky / no ground / no
    # lights / no atmosphere, this adds them. Never removes anything.
    if _HAS_ENV_SAFETY:
        try:
            hero_for_safety: list = []
            _skip_prefixes_safety = (
                "ground", "sky", "backdrop", "contactshadow", "camera",
                "light", "cinematic", "hemi", "sun", "area", "point",
                "road", "street", "environment_ground", "atmosphere",
            )
            for obj in bpy.data.objects:
                if obj.type != "MESH":
                    continue
                lname = obj.name.lower()
                if any(lname.startswith(p) for p in _skip_prefixes_safety):
                    continue
                hero_for_safety.append(obj)
            _ensure_environment_safety_net(
                bpy, scene, manifest, hero_objects=hero_for_safety or None,
            )
        except Exception as e:
            print(f"DEBUG ensure_environment safety net failed (non-fatal): {e}", flush=True)
        try:
            _apply_directorial_controls(bpy, scene, manifest)
        except Exception as e:
            print(f"DEBUG apply_directorial_controls failed (non-fatal): {e}", flush=True)
    log_stage("ENSURE_ENV")

    # ══════════════════════════════════════════════════════════════════════
    # WORLD_DEVELOPMENT — the production designer pass
    # ══════════════════════════════════════════════════════════════════════
    # Runs AFTER the template + env are in place and BEFORE the optimizer.
    # Classifies the prompt to a biome, adds biome-appropriate scatter
    # props (rocks, bushes, torches, puddles, etc.), fog, silhouettes,
    # accent lights, and stores a color-grade dict for the compositor.
    # Every new object is tagged ``is_world_dev=True``.
    # Wrapped in try/except so world-dev can NEVER block a render.
    #
    # MULTI-ASSET: when a forced environment asset is active, skip the
    # synthetic scatter entirely — the real environment asset replaces
    # the procedural rocks/bushes/hills.
    if manifest.get("_skip_synthetic_scatter"):
        print(
            "[WORLD_DEV] pass SKIPPED — forced environment asset already placed",
            flush=True,
        )
    try:
        if manifest.get("_skip_synthetic_scatter"):
            raise RuntimeError("_skip_synthetic_scatter manifest flag set")
        from app.scene.world_development import classify_biome, develop_world
        # Compute hero bbox (reuse the collect helper above if it's defined)
        _wd_hero_bbox = None
        try:
            _wd_hero_meshes = [
                o for o in bpy.data.objects
                if o.type == "MESH" and o.get("is_hero", False)
            ]
            if _wd_hero_meshes:
                from mathutils import Vector as _WdVec
                _wd_coords = []
                for _o in _wd_hero_meshes:
                    try:
                        for _c in _o.bound_box:
                            _wd_coords.append(_o.matrix_world @ _WdVec(_c))
                    except Exception:
                        pass
                if _wd_coords:
                    _wd_hero_bbox = {
                        "min_x": min(c.x for c in _wd_coords),
                        "max_x": max(c.x for c in _wd_coords),
                        "min_y": min(c.y for c in _wd_coords),
                        "max_y": max(c.y for c in _wd_coords),
                        "min_z": min(c.z for c in _wd_coords),
                        "max_z": max(c.z for c in _wd_coords),
                    }
        except Exception:
            _wd_hero_bbox = None

        _wd_biome = classify_biome(manifest)
        _wd_report = develop_world(
            _wd_biome,
            scene_context={
                "bpy":          bpy,
                "manifest":     manifest,
                "hero_bbox":    _wd_hero_bbox,
                "camera":       bpy.context.scene.camera,
                "frame_range":  (bpy.context.scene.frame_start, bpy.context.scene.frame_end),
                "render_tier":  _resolve_tier_name(manifest),
            },
        )
        print(
            f"[WORLD_DEV] biome={_wd_report.biome!r} "
            f"confidence={_wd_report.confidence:.2f} "
            f"scatter_placed={_wd_report.scatter_total} "
            f"accents={_wd_report.accent_light_count} "
            f"silhouettes={_wd_report.silhouette_count} "
            f"atmosphere={_wd_report.atmosphere_kind!r} "
            f"grade_applied={_wd_report.grade_applied}",
            flush=True,
        )
    except Exception as _wd_err:
        _wd_err_msg = str(_wd_err)
        if "_skip_synthetic_scatter" in _wd_err_msg:
            # Expected skip signal — already printed above, suppress noise
            pass
        else:
            print(
                f"[WORLD_DEV] non-fatal error: {_wd_err} — "
                f"scene continues with base template",
                flush=True,
            )
    log_stage("WORLD_DEVELOPMENT")

    # ── Round 9 Pillar 3: Cinematic DOF — MOVED to after CAMERA_FIX ────
    # DOF is now set as the last step before compositor (after all camera
    # repositioning) so the focus target is correct.

    # ── Post-build optimization pipeline ────────────────────────────────
    # These run AFTER scene construction, BEFORE rendering.
    # Order matters: optimize scene first (remove waste), then lock render settings.
    resolved_tier = _resolve_tier_name(manifest)
    # Render budget treats unknown tier names as 'standard'; the legacy
    # quality_tier names (fast/standard/ultra) still drive it correctly.
    # For 'preview' and 'cinematic' we hand it the closest legacy bucket so
    # the budget heuristics don't try to override our explicit Eevee setup.
    if resolved_tier == "preview":
        quality_tier = "fast"
    elif resolved_tier == "cinematic":
        quality_tier = "ultra"
    else:
        quality_tier = resolved_tier
    scene_plan = manifest.get("_scene_plan")

    # 1. Scene Optimizer: remove tiny meshes, enforce light budget,
    #    control volumetrics, simplify materials
    if _HAS_OPTIMIZER:
        try:
            opt_stats = optimize_scene(bpy, scene, quality_tier, scene_plan)
        except Exception as e:
            print(f"DEBUG scene_optimizer failed (scene unchanged): {e}", flush=True)

    # 2. Render Budget: configure samples, bounces, device, resolution,
    #    install time guard. Skipped for the preview tier so the budget
    #    heuristics don't reach into Eevee state.
    if _HAS_BUDGET and resolved_tier != "preview":
        try:
            budget_info = apply_render_budget(bpy, scene, quality_tier, scene_plan)
        except Exception as e:
            print(f"DEBUG render_budget failed (using configure_scene defaults): {e}", flush=True)
    log_stage("OPTIMIZER_BUDGET")

    # ── Cinematic World Builder ────────────────────────────────────────
    # Runs AFTER the template built the scene but BEFORE rendering.
    # Adds atmosphere, time-of-day-aware HDRI, 3-point lighting,
    # environment details (roads/buildings/hills), and compositor polish.
    # Each helper inside world_builder is defensive: it checks for existing
    # assets and only fills gaps — it never clobbers template output.
    # Wrapped in try/except so it can NEVER break an existing render.
    try:
        from app.scene.world_builder import build_world
        hero_objects = [
            obj for obj in bpy.data.objects
            if obj.type in ('MESH', 'ARMATURE')
            and 'ground' not in obj.name.lower()
            and 'plane' not in obj.name.lower()
            and 'world_' not in obj.name.lower()
            and 'atmosphere' not in obj.name.lower()
        ]
        build_world(manifest, hero_objects)
    except Exception as e:
        print(f"[WORLD] World builder error (non-fatal): {e}", flush=True)
    log_stage("WORLD_BUILT")

    # ══════════════════════════════════════════════════════════════════════
    # COMPLEX ENVIRONMENT IMPORTER — if blender_runner fetched a stadium /
    # restaurant / kitchen / venue model, bring it in and anchor it around
    # the hero. Names every imported object with an "environment_" prefix
    # so the framing guarantor / lighting guarantor / world builders treat
    # it as set dressing, not hero geometry.
    # ══════════════════════════════════════════════════════════════════════
    def _env_find_rough_hero_center():
        """Quick hero center WITHOUT the environment we're about to import."""
        import mathutils  # type: ignore
        skip_terms = (
            "ground", "plane", "floor", "world_", "atmosphere", "sky",
            "environment", "backdrop", "road", "street", "contactshadow",
            "nuclear_",
        )
        coords = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            n = obj.name.lower()
            if any(t in n for t in skip_terms):
                continue
            try:
                for corner in obj.bound_box:
                    coords.append(obj.matrix_world @ mathutils.Vector(corner))
            except Exception:
                continue
        if not coords:
            return mathutils.Vector((0.0, 0.0, 0.0)), 2.0
        xs = [c.x for c in coords]; ys = [c.y for c in coords]; zs = [c.z for c in coords]
        center = mathutils.Vector((
            (min(xs) + max(xs)) / 2.0,
            (min(ys) + max(ys)) / 2.0,
            (min(zs) + max(zs)) / 2.0,
        ))
        size = mathutils.Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
        diag = max(0.5, (size.x ** 2 + size.y ** 2 + size.z ** 2) ** 0.5)
        return center, diag

    def _env_import_complex():
        """Import the environment model (if any), scale it, position it."""
        try:
            env_path = manifest.get("environment_asset_path")
            if not env_path:
                return
            if not _HAS_ASSET_IMPORT:
                print("[ENV_IMPORT] asset_import module unavailable — skipping", flush=True)
                return
            if not Path(str(env_path)).exists():
                print(f"[ENV_IMPORT] env file not on disk: {env_path}", flush=True)
                return

            # Record state BEFORE import so we know exactly what was added.
            before_names = {obj.name for obj in bpy.data.objects}
            print(f"[ENV_IMPORT] importing environment model: {env_path}", flush=True)
            try:
                imported = import_hero_asset(bpy, str(env_path))
            except Exception as e:
                print(f"[ENV_IMPORT] import_hero_asset raised: {e}", flush=True)
                imported = []
            if not imported:
                # Fallback: diff before/after
                imported = [
                    bpy.data.objects[n]
                    for n in (o.name for o in bpy.data.objects)
                    if n not in before_names
                ]
            if not imported:
                print("[ENV_IMPORT] no objects produced by import", flush=True)
                return

            # Rename so downstream helpers treat these as environment.
            for obj in imported:
                try:
                    if not obj.name.lower().startswith("environment_"):
                        obj.name = f"environment_{obj.name}"
                except Exception:
                    pass

            # Measure hero center + size to know where to anchor the
            # environment, then measure the environment's own bbox so we
            # can scale it sensibly (a 200m stadium around a 2m character
            # is perfect; a 0.5m stadium asset around a 2m character is not).
            import mathutils  # type: ignore
            hero_center, hero_diag = _env_find_rough_hero_center()

            env_meshes = [o for o in imported if o.type == 'MESH']
            if not env_meshes:
                # Armatures / empties only — skip positioning, just leave in place.
                return

            env_xs, env_ys, env_zs = [], [], []
            for o in env_meshes:
                try:
                    for c in o.bound_box:
                        w = o.matrix_world @ mathutils.Vector(c)
                        env_xs.append(w.x); env_ys.append(w.y); env_zs.append(w.z)
                except Exception:
                    continue
            if not env_xs:
                return
            env_min = mathutils.Vector((min(env_xs), min(env_ys), min(env_zs)))
            env_max = mathutils.Vector((max(env_xs), max(env_ys), max(env_zs)))
            env_center = (env_min + env_max) * 0.5
            env_size = env_max - env_min
            env_diag = max(0.1, (env_size.x ** 2 + env_size.y ** 2 + env_size.z ** 2) ** 0.5)

            # Per-venue scale: stadiums 25x, restaurants 8x, etc.
            try:
                from app.services.environment_fetcher import get_env_scale_multiplier
                mult = get_env_scale_multiplier(manifest)
            except Exception:
                mult = 10.0
            # Target: environment diagonal = mult × hero diagonal.
            target_env_diag = max(20.0, hero_diag * mult)
            scale_factor = target_env_diag / env_diag
            scale_factor = max(0.1, min(400.0, scale_factor))  # clamp sane range
            print(f"[ENV_IMPORT] using scale multiplier={mult}x hero_diag", flush=True)

            # Find top-level roots (no parent or parent not in imported set).
            imported_set = {o.name for o in imported}
            roots = [o for o in imported if not o.parent or o.parent.name not in imported_set]
            for root in roots:
                try:
                    root.scale = (
                        root.scale.x * scale_factor,
                        root.scale.y * scale_factor,
                        root.scale.z * scale_factor,
                    )
                except Exception:
                    pass

            # After scaling, recompute env_center and shift so its XY-center
            # sits under the hero and its bottom sits on z=0 (the ground).
            env_xs2, env_ys2, env_zs2 = [], [], []
            # Force a depsgraph update so matrices reflect the new scale.
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            for o in env_meshes:
                try:
                    for c in o.bound_box:
                        w = o.matrix_world @ mathutils.Vector(c)
                        env_xs2.append(w.x); env_ys2.append(w.y); env_zs2.append(w.z)
                except Exception:
                    continue
            if env_xs2:
                env_min2 = mathutils.Vector((min(env_xs2), min(env_ys2), min(env_zs2)))
                env_max2 = mathutils.Vector((max(env_xs2), max(env_ys2), max(env_zs2)))
                env_center2 = (env_min2 + env_max2) * 0.5
                # Shift so env XY-center aligns with hero XY, and env bottom = 0.
                dx = hero_center.x - env_center2.x
                dy = hero_center.y - env_center2.y
                dz = -env_min2.z
                for root in roots:
                    try:
                        root.location = (
                            root.location.x + dx,
                            root.location.y + dy,
                            root.location.z + dz,
                        )
                    except Exception:
                        pass

            print(
                f"[ENV_IMPORT] placed env scale={scale_factor:.2f} "
                f"(hero_diag={hero_diag:.2f} -> env_diag_target={target_env_diag:.2f})",
                flush=True,
            )
        except Exception as e:
            print(f"[ENV_IMPORT] complex env import crashed (non-fatal): {e}", flush=True)

    _env_import_complex()
    log_stage("ENV_IMPORT")

    # ══════════════════════════════════════════════════════════════════════
    # SCENE KEYWORD GUARANTOR — runs AFTER the complex env importer.
    # If the user prompt mentions outdoor elements (mountains / ocean /
    # trees / desert / snow) but no complex venue model was fetched,
    # synthesize stylized procedural stand-ins so the render reads as
    # the place the user asked for, not a gray infinite plane.
    # Safe no-op when a complex env model is present.
    # ══════════════════════════════════════════════════════════════════════
    if _HAS_KW_GUARANTOR:
        try:
            guarantee_scene_keywords(bpy, manifest)
        except Exception as _kw_e:
            print(f"[SCENE_KW] guarantor call failed (non-fatal): {_kw_e}", flush=True)
    log_stage("KW_GUARANTOR")

    # ══════════════════════════════════════════════════════════════════════
    # NUCLEAR SKY FIX — runs unconditionally on EVERY render.
    # Every other sky-building path (ensure_environment, world_builder,
    # the old "FORCED HDRI SKY GUARANTOR") has failed in practice because
    # its check passed but the resulting world didn't actually render as
    # a sky. This is the LAST thing that touches the world before the
    # frame loop. Keep it minimal, defensive, and loud in the log.
    # ══════════════════════════════════════════════════════════════════════
    # Round 4.3: per-env HDRI map.  When a forced env is active, bias
    # the HDRI pick toward filenames that semantically match the env's
    # subject / biome.  Falls through to time-of-day matching when no
    # env is present or no filename hits.
    _ENV_HDRI_MAP = {
        "canyon":     ["desert", "canyon", "red_rock", "arid", "sand"],
        "desert":     ["desert", "sand", "sahara", "dune", "arid"],
        "mountain":   ["mountain", "alpine", "ridge", "peak", "hill"],
        "arctic":     ["snow", "ice", "polar", "winter", "glacier", "arctic"],
        "glacier":    ["ice", "snow", "glacier", "polar", "arctic"],
        "iceland":    ["iceland", "volcanic", "arctic", "tundra"],
        "winter":     ["snow", "winter", "ice", "overcast"],
        "city":       ["city", "urban", "street", "rooftop", "downtown"],
        "rooftop":    ["city", "urban", "rooftop", "skyline"],
        "forest":     ["forest", "woods", "tree", "jungle"],
        "castle":     ["overcast", "stormy", "misty", "grassland", "dusk"],
        "ocean":      ["ocean", "sea", "beach", "coast", "tropical"],
        "italy":      ["tuscany", "italian", "golden", "warm", "sunset"],
        "european":   ["european", "overcast", "cloudy"],
        "thunderstorm":["storm", "cloudy", "overcast", "dark", "dramatic"],
        "landscape":  ["outdoor", "sky", "clear", "grassland"],
        "road":       ["road", "highway", "outdoor"],
    }

    def _pick_hdri_for_env(hdri_files, env_entry: dict):
        """Scan env entry's subject + subject_tags + biome_hints for a
        keyword present in _ENV_HDRI_MAP, then pick the first hdri_files
        entry whose stem contains one of the mapped tokens.  Returns
        None if no match."""
        if not hdri_files or not isinstance(env_entry, dict):
            return None
        signals: list[str] = []
        subj = str(env_entry.get("subject") or "").lower()
        if subj:
            signals.append(subj)
        for t in (env_entry.get("subject_tags") or []):
            signals.append(str(t).lower())
        for b in (env_entry.get("biome_hints") or []):
            signals.append(str(b).lower())
        tokens: list[str] = []
        seen = set()
        for sig in signals:
            for key, vals in _ENV_HDRI_MAP.items():
                if key in sig:
                    for v in vals:
                        if v not in seen:
                            seen.add(v)
                            tokens.append(v)
        for token in tokens:
            for f in hdri_files:
                if token in f.stem.lower():
                    print(
                        f"[SKY_FIX] env-aware HDRI pick: {f.name} "
                        f"(token={token!r}, env_subject={subj!r})",
                        flush=True,
                    )
                    return f
        return None

    def _sky_pick_hdri_for_time(hdri_files, time_of_day: str):
        """Pick the HDRI file whose name best matches the scene time-of-day.

        Round 4.3: if a forced environment is active, env-aware picks
        take priority over time-of-day picks — the backdrop's biome is
        a stronger visual signal than an abstract hour.
        """
        if not hdri_files:
            return None
        # Env-aware short-circuit
        try:
            _env_entry_hdri = manifest.get("forced_environment_entry") or {}
            if manifest.get("_has_forced_environment") and _env_entry_hdri:
                _env_pick = _pick_hdri_for_env(hdri_files, _env_entry_hdri)
                if _env_pick is not None:
                    return _env_pick
        except Exception as _env_hdri_err:
            print(f"[SKY_FIX] env HDRI pick failed (non-fatal): {_env_hdri_err}", flush=True)
        tod = (time_of_day or "").lower()
        # Ordered list of (token-group, score-bonus) per time-of-day. First match wins.
        match_groups = {
            "sunset":      ["sunset", "golden", "warm", "evening", "dusk"],
            "golden_hour": ["golden", "sunset", "warm", "evening"],
            "dusk":        ["dusk", "twilight", "blue_hour", "evening"],
            "night":       ["night", "dark", "star", "moon", "midnight"],
            "dawn":        ["dawn", "sunrise", "morning", "pink"],
            "morning":     ["morning", "sunrise", "dawn", "clear"],
            "midday":      ["noon", "clear", "sunny", "blue_sky", "midday"],
        }
        tokens = match_groups.get(tod, [])
        for token in tokens:
            for f in hdri_files:
                if token in f.stem.lower():
                    return f
        # Secondary: generic outdoor sky keywords.
        for token in ("blue", "sky", "clear", "sunny", "outdoor"):
            for f in hdri_files:
                if token in f.stem.lower():
                    return f
        # Fallback: largest file (usually highest quality).
        return hdri_files[0]

    def _sky_hdri_is_usable(img, hdri_path: str) -> bool:
        """
        Sample the HDRI to confirm it's not a flat / broken / gray file.
        An HDRI that passes file-existence checks but is 90% the same color
        produces a "gray soup" render. We reject such images and fall
        through to the procedural Nishita sky.

        Gate criteria (all must pass):
        - Dimensions > 0.
        - Mean brightness in a reasonable range (not pitch-black, not blown).
        - Chromaticity / brightness variance above a floor (proves detail).
        """
        try:
            w, h = img.size[0], img.size[1]
            if w <= 0 or h <= 0:
                print(f"[SKY_FIX] HDRI {hdri_path} has zero dimensions — rejecting", flush=True)
                return False
            ch = getattr(img, "channels", 4) or 4
            # Sample a coarse grid of pixels — never touch the full buffer
            # (can be 100M+ floats for an 8K HDRI).
            samples = 64
            xs = [int(w * (i + 0.5) / samples) for i in range(samples)]
            ys = [int(h * (i + 0.5) / samples) for i in range(samples)]
            pixels = img.pixels  # bpy_prop_array; indexable but slow
            rs, gs, bs, lums = [], [], [], []
            for y in ys[::4]:  # 16×16 = 256 samples, cheap
                for x in xs[::4]:
                    offs = (y * w + x) * ch
                    try:
                        r = float(pixels[offs])
                        g = float(pixels[offs + 1]) if ch > 1 else r
                        b = float(pixels[offs + 2]) if ch > 2 else r
                    except Exception:
                        continue
                    rs.append(r); gs.append(g); bs.append(b)
                    lums.append(0.2126 * r + 0.7152 * g + 0.0722 * b)
            if not lums:
                print(f"[SKY_FIX] HDRI {hdri_path} sampling returned nothing — rejecting", flush=True)
                return False
            n = len(lums)
            mean_l = sum(lums) / n
            min_l = min(lums); max_l = max(lums)
            # Chromaticity spread — how different are R/G/B per pixel on avg?
            chroma = sum(abs(rs[i] - gs[i]) + abs(gs[i] - bs[i]) + abs(rs[i] - bs[i]) for i in range(n)) / n
            print(
                f"[SKY_FIX] HDRI stats {Path(hdri_path).name}: "
                f"mean_L={mean_l:.3f} range=[{min_l:.3f},{max_l:.3f}] chroma={chroma:.3f}",
                flush=True,
            )
            # Reject pitch black
            if max_l < 0.02:
                print("[SKY_FIX]   → too dark, rejecting", flush=True)
                return False
            # Reject flat / gray: tiny luminance spread AND tiny chroma spread
            lum_range = max_l - min_l
            if lum_range < 0.05 and chroma < 0.02:
                print("[SKY_FIX]   → flat/gray, rejecting", flush=True)
                return False
            return True
        except Exception as e:
            # If sampling crashes, don't block the render — trust the file.
            print(f"[SKY_FIX] HDRI sampling skipped ({e}) — accepting", flush=True)
            return True

    def _sky_hdri_strength_for_time(tod: str) -> float:
        """Boost HDRI strength for night so the sky doesn't render as mud."""
        t = (tod or "").lower()
        if t == "night":
            return 2.0
        if t in ("dusk", "dawn"):
            return 1.4
        if t in ("sunset", "golden_hour"):
            return 1.15
        return 1.0

    def _sky_load_hdri(hdri_path: str) -> bool:
        """Wipe the world node graph and install an HDRI environment.

        Now gated by a pixel-sampling quality check — if the HDRI looks
        flat/gray/black, returns False so the caller falls back to the
        procedural Nishita sky (which is guaranteed vivid).
        """
        try:
            world = bpy.context.scene.world
            if not world:
                world = bpy.data.worlds.new("World")
                bpy.context.scene.world = world

            # Pre-load the image separately so we can sanity-check it BEFORE
            # installing into the world graph. Keeps the node tree clean if
            # we decide to reject.
            img = bpy.data.images.load(hdri_path, check_existing=True)
            if not _sky_hdri_is_usable(img, hdri_path):
                return False

            world.use_nodes = True
            tree = world.node_tree
            for n in list(tree.nodes):
                tree.nodes.remove(n)
            tex = tree.nodes.new('ShaderNodeTexEnvironment')
            bg = tree.nodes.new('ShaderNodeBackground')
            out = tree.nodes.new('ShaderNodeOutputWorld')
            tex.location = (-400, 0)
            bg.location = (-100, 0)
            out.location = (200, 0)
            tex.image = img
            tod_for_strength = ""
            try:
                tod_for_strength = str(manifest.get("_scene_plan", {}).get("time_of_day") or "")
            except Exception:
                pass
            strength = _sky_hdri_strength_for_time(tod_for_strength)
            # HDRI strength floor — ensures sky is always visible even when
            # the time-of-day lookup returns a low value or when the HDRI
            # itself is dim. A strength < 0.8 consistently produces gray skies.
            strength = max(strength, 0.8)
            bg.inputs['Strength'].default_value = strength
            tree.links.new(tex.outputs['Color'], bg.inputs['Color'])
            tree.links.new(bg.outputs['Background'], out.inputs['Surface'])
            print(
                f"[SKY_FIX] HDRI installed: {hdri_path} "
                f"(strength={strength:.2f})",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[SKY_FIX] HDRI load FAILED: {e}", flush=True)
            return False

    def _sky_create_procedural():
        """Install a Nishita procedural sky (vivid, NOT gray)."""
        try:
            world = bpy.context.scene.world
            if not world:
                world = bpy.data.worlds.new("World")
                bpy.context.scene.world = world
            world.use_nodes = True
            tree = world.node_tree
            for n in list(tree.nodes):
                tree.nodes.remove(n)
            try:
                sky = tree.nodes.new('ShaderNodeTexSky')
                sky.sky_type = 'NISHITA'
                # Scene-appropriate sun elevation / density.
                tod = ""
                try:
                    tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
                except Exception:
                    pass
                if tod in ("sunset", "golden_hour", "dawn"):
                    sky.sun_elevation = 0.25   # ~14°
                    sky.dust_density = 1.2
                elif tod == "night":
                    sky.sun_elevation = -0.1   # below horizon (star-ish)
                    sky.air_density = 0.5
                elif tod == "dusk":
                    sky.sun_elevation = 0.05
                    sky.dust_density = 1.5
                else:
                    sky.sun_elevation = 0.9     # ~52°
                    sky.dust_density = 0.5
                sky.sun_rotation = 0.0
                sky.altitude = 0
                sky.air_density = getattr(sky, "air_density", 1.0)
                sky.ozone_density = 1.0

                bg = tree.nodes.new('ShaderNodeBackground')
                bg.inputs['Strength'].default_value = 1.0
                out = tree.nodes.new('ShaderNodeOutputWorld')
                sky.location = (-400, 0)
                bg.location = (-100, 0)
                out.location = (200, 0)
                tree.links.new(sky.outputs['Color'], bg.inputs['Color'])
                tree.links.new(bg.outputs['Background'], out.inputs['Surface'])
                print(f"[SKY_FIX] Nishita procedural sky installed (tod={tod or 'default'})", flush=True)
                return
            except Exception as sky_err:
                print(f"[SKY_FIX] Nishita unavailable ({sky_err}) — falling back to flat blue", flush=True)
            # Oldest fallback — solid blue, still not gray.
            bg = tree.nodes.new('ShaderNodeBackground')
            bg.inputs['Color'].default_value = (0.3, 0.5, 0.8, 1.0)
            bg.inputs['Strength'].default_value = 2.0
            out = tree.nodes.new('ShaderNodeOutputWorld')
            tree.links.new(bg.outputs['Background'], out.inputs['Surface'])
            print("[SKY_FIX] flat blue sky installed", flush=True)
        except Exception as e:
            print(f"[SKY_FIX] procedural sky FAILED: {e}", flush=True)

    def _sky_force():
        """
        UNCONDITIONAL guarantee: this render will have a visible sky.
        Only skips if a TEX_ENVIRONMENT with a valid image is already wired
        and the image has non-zero dimensions (i.e. it actually loaded).
        """
        try:
            world = bpy.context.scene.world
            if world and world.use_nodes and world.node_tree:
                for node in world.node_tree.nodes:
                    if node.type == 'TEX_ENVIRONMENT' and node.image is not None:
                        try:
                            if node.image.size[0] > 0 and node.image.size[1] > 0:
                                print("[SKY_FIX] existing HDRI verified — skipping", flush=True)
                                return
                        except Exception:
                            pass  # size probe failed — treat as broken and replace

            hdri_dirs = [
                Path(r"C:/Users/bgrut/Desktop/FantasyAI/blender-studio-backend/assets/hdri"),
                Path(r"C:/Users/bgrut/Desktop/FantasyAI/blender-studio-backend/assets/hdris"),
            ]
            hdri_files: list[Path] = []
            for d in hdri_dirs:
                if d.exists():
                    hdri_files.extend(d.glob("*.hdr"))
                    hdri_files.extend(d.glob("*.exr"))
            # Largest file first — usually highest resolution.
            hdri_files = sorted(hdri_files, key=lambda f: f.stat().st_size, reverse=True)

            if hdri_files:
                tod = ""
                try:
                    tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "")
                except Exception:
                    pass
                # Try time-matched HDRI first, then any remaining files
                # in descending size order, until one passes the quality
                # gate. Gives us up to ~3 attempts before going procedural.
                preferred = _sky_pick_hdri_for_time(hdri_files, tod)
                ordered = []
                if preferred:
                    ordered.append(preferred)
                for f in hdri_files:
                    if f not in ordered:
                        ordered.append(f)
                for candidate in ordered[:4]:  # cap at 4 attempts to stay fast
                    if _sky_load_hdri(str(candidate)):
                        return
                    print(f"[SKY_FIX] rejecting {candidate.name}, trying next", flush=True)
                print("[SKY_FIX] all HDRIs failed quality gate — going procedural", flush=True)
            else:
                print("[SKY_FIX] no HDRI files on disk — going procedural", flush=True)

            _sky_create_procedural()
        except Exception as e:
            print(f"[SKY_FIX] nuclear sky fix itself crashed: {e}", flush=True)

    _sky_force()
    log_stage("SKY_FIX")

    # ══════════════════════════════════════════════════════════════════════
    # TIME-OF-DAY SANITY FORCE — the sky is in, now make sure the rest of
    # the scene AGREES with the time the user asked for.
    #
    # Promise: if the manifest says "day / midday / morning" we guarantee
    # a bright sun-lit render. If it says "night" we guarantee a dark
    # scene with moonlight (cool blue, low energy) AND dim the world
    # background so the sky doesn't blow out the night mood.
    #
    # This prevents:
    #  - "night at the beach" rendering like bright daytime because the
    #    HDRI is a blue-sky file and no one turned the world down.
    #  - "midday" rendering muddy because there's no key sun and the
    #    procedural sky was left at a weak default.
    #  - The hero booster's tod heuristic disagreeing with the sky.
    # ══════════════════════════════════════════════════════════════════════
    def _tod_resolve() -> str:
        """Return a normalized time-of-day: day / sunset / dusk / night / dawn."""
        raw = ""
        try:
            raw = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
        except Exception:
            pass
        if not raw:
            # Last-resort scan of the raw prompt.
            blob_parts = []
            for k in ("topic", "prompt", "user_prompt"):
                v = manifest.get(k)
                if v:
                    blob_parts.append(str(v).lower())
            blob = " ".join(blob_parts)
            for kw, tod in (
                ("night",     "night"),
                ("midnight",  "night"),
                ("moonlit",   "night"),
                ("evening",   "dusk"),
                ("dusk",      "dusk"),
                ("sunset",    "sunset"),
                ("golden hour", "sunset"),
                ("sunrise",   "dawn"),
                ("dawn",      "dawn"),
                ("morning",   "day"),
                ("midday",    "day"),
                ("noon",      "day"),
                ("afternoon", "day"),
                ("daytime",   "day"),
                (" day ",     "day"),
            ):
                if kw in blob:
                    return tod
            return "day"  # default assumption — most prompts are daytime
        if raw in ("midday", "noon", "morning", "afternoon", "day", "daytime"):
            return "day"
        if raw in ("sunset", "golden_hour", "golden hour"):
            return "sunset"
        if raw in ("dusk", "twilight", "blue_hour"):
            return "dusk"
        if raw in ("night", "midnight", "moonlit"):
            return "night"
        if raw in ("dawn", "sunrise"):
            return "dawn"
        return "day"

    def _tod_install_sun(tod: str):
        """Install / replace the NUCLEAR_TOD_SUN matching the time-of-day.

        Idempotent by name. Removes any stale copy first so re-renders
        don't stack suns.
        """
        import mathutils  # type: ignore
        # Kill any previous TOD sun to avoid stacking.
        old = bpy.data.objects.get("NUCLEAR_TOD_SUN")
        if old:
            try:
                bpy.data.objects.remove(old, do_unlink=True)
            except Exception:
                pass
        # Tuned (energy, color_rgb, euler_tilt_rad) per TOD.
        # Euler tilt is rotation around X so the sun comes from +Z tilted
        # toward -Y — gives a cinematic 3/4 key direction.
        # Softened ruleset after feedback: night was crushed to pitch-black.
        # World-class night cinema is moody-but-READABLE, not a black screen.
        # Moonlight now delivers enough key energy that environment silhouettes
        # (ocean, mountains, city) register even before rim / ambient fills.
        cfg = {
            "day":    (5.0,  (1.00, 0.97, 0.92), (-0.55, 0.0, 0.35)),  # sun high
            "sunset": (3.2,  (1.00, 0.62, 0.32), (-1.25, 0.0, 0.5)),   # near horizon, orange
            "dusk":   (1.4,  (0.65, 0.65, 0.90), (-1.45, 0.0, 0.8)),   # low, cool blue
            "night":  (0.95, (0.60, 0.75, 1.00), (-1.55, 0.0, 1.2)),   # moon proxy (brighter)
            "dawn":   (2.0,  (1.00, 0.75, 0.78), (-1.35, 0.0, -0.8)),  # low, soft pink
        }
        energy, color, euler = cfg.get(tod, cfg["day"])
        try:
            bpy.ops.object.light_add(type='SUN', location=(0, 0, 40))
            sun = bpy.context.object
            sun.name = "NUCLEAR_TOD_SUN"
            sun.data.energy = energy
            try:
                sun.data.color = color
                sun.data.angle = 0.01  # sharp sun shadow by default
                if tod == "night":
                    sun.data.angle = 0.05  # softer moonlight shadow
            except Exception:
                pass
            sun.rotation_euler = mathutils.Euler(euler, 'XYZ')
            print(
                f"[TOD_FIX] sun installed tod={tod} energy={energy} color={color}",
                flush=True,
            )
        except Exception as e:
            print(f"[TOD_FIX] sun install failed: {e}", flush=True)

    def _tod_world_strength_cap(tod: str):
        """Clamp world background strength so night doesn't over-expose."""
        try:
            world = bpy.context.scene.world
            if not world or not world.use_nodes or not world.node_tree:
                return
            # Desired caps: night = very dim sky light; dusk = dim; day = bright.
            # Softened caps — night at 0.30 killed ambient and made scenes
            # render as "hero dot on pure-black screen". Keep a floor so
            # ambient sky light still paints distant silhouettes.
            cap = {
                "day":    1.2,
                "sunset": 1.0,
                "dusk":   0.70,
                "night":  0.55,
                "dawn":   0.90,
            }.get(tod, 1.0)
            changed = 0
            for node in world.node_tree.nodes:
                if node.type == 'BACKGROUND':
                    try:
                        cur = float(node.inputs['Strength'].default_value)
                    except Exception:
                        continue
                    if cur > cap:
                        node.inputs['Strength'].default_value = cap
                        changed += 1
                    elif tod == "day" and cur < 0.8:
                        # Day scenes: make sure the world isn't whispering.
                        node.inputs['Strength'].default_value = 1.0
                        changed += 1
            if changed:
                print(f"[TOD_FIX] world bg strength adjusted (tod={tod}, cap={cap})", flush=True)
        except Exception as e:
            print(f"[TOD_FIX] world strength cap failed: {e}", flush=True)

    def _tod_exposure_adjust(tod: str):
        """Nudge view-transform exposure so night reads dark, day reads bright."""
        try:
            scene = bpy.context.scene
            vs = scene.view_settings
            # Exposure is in stops. Positive = brighter. These land on top
            # of any tier-level exposure_boost already applied.
            # Softened deltas — stacking -0.9 on top of cinematic's +0.15 tier
            # exposure landed net -0.75, which is black-level territory. These
            # values keep night visibly darker than day without going off a
            # cliff into unreadable.
            delta = {
                "day":     0.10,
                "sunset":  0.00,
                "dusk":   -0.20,
                "night":  -0.35,
                "dawn":   -0.10,
            }.get(tod, 0.0)
            try:
                vs.exposure = float(vs.exposure) + delta
            except Exception:
                vs.exposure = delta
            print(f"[TOD_FIX] exposure delta {delta:+.2f} (tod={tod})", flush=True)
        except Exception as e:
            print(f"[TOD_FIX] exposure adjust failed: {e}", flush=True)

    def _tod_install_ambient_fill(tod: str):
        """
        Always-on SCENE-WIDE ambient fill so environment silhouettes read
        even when the HDRI is dim/absent and the moonlight only covers the
        hero. Large AREA light placed high above origin, aimed straight
        down, broad falloff. Color/energy tuned per TOD.

        Without this, night renders look like a single spotlight on a hero
        floating in black void — which is exactly the failure mode the
        dolphin / Ferrari screenshots showed.
        """
        try:
            # Idempotent — replace on re-render.
            old = bpy.data.objects.get("NUCLEAR_AMBIENT_FILL")
            if old:
                try:
                    bpy.data.objects.remove(old, do_unlink=True)
                except Exception:
                    pass
            cfg = {
                "day":    (900,  (1.00, 0.98, 0.95)),   # soft sky fill
                "sunset": (700,  (1.00, 0.80, 0.55)),   # warm fill
                "dusk":   (650,  (0.75, 0.78, 1.00)),   # cool blue fill
                "night":  (550,  (0.60, 0.78, 1.00)),   # moon-blue fill
                "dawn":   (700,  (1.00, 0.88, 0.85)),   # soft pink fill
            }
            energy, color = cfg.get(tod, cfg["day"])
            bpy.ops.object.light_add(type='AREA', location=(0.0, 0.0, 35.0))
            fill = bpy.context.object
            fill.name = "NUCLEAR_AMBIENT_FILL"
            fill.data.energy = energy
            try:
                fill.data.size = 60.0       # enormous soft source
                fill.data.shape = 'DISK'
                fill.data.color = color
                # Spread everywhere, not a focused spot.
                if hasattr(fill.data, 'spread'):
                    fill.data.spread = 3.14159  # 180° in radians
            except Exception:
                pass
            # Point straight down.
            import mathutils  # type: ignore
            fill.rotation_euler = mathutils.Euler((0.0, 0.0, 0.0), 'XYZ')
            print(
                f"[TOD_FIX] ambient fill installed (tod={tod}, energy={energy})",
                flush=True,
            )
        except Exception as e:
            print(f"[TOD_FIX] ambient fill failed: {e}", flush=True)

    def _tod_force():
        """Guarantee the render visually matches the requested time-of-day."""
        try:
            tod = _tod_resolve()
            print(f"[TOD_FIX] resolved time_of_day={tod!r}", flush=True)
            _tod_install_sun(tod)
            _tod_world_strength_cap(tod)
            _tod_exposure_adjust(tod)
            _tod_install_ambient_fill(tod)
            # Stash resolved tod back onto the manifest so downstream
            # blocks (hero booster, night ambience) see a consistent value.
            try:
                plan = manifest.setdefault("_scene_plan", {})
                plan["time_of_day"] = tod
            except Exception:
                pass
        except Exception as e:
            print(f"[TOD_FIX] tod force crashed (non-fatal): {e}", flush=True)

    _tod_force()
    log_stage("TOD_FIX")

    # ── Cinematic 3-point lighting from scene_recipe ──────────────────
    if _HAS_CINEMATIC_LIGHTING:
        try:
            _cl_heroes = [
                obj for obj in bpy.data.objects
                if obj.type == "MESH"
                and not any(t in obj.name.lower() for t in (
                    "ground", "floor", "plane", "sky", "atmosphere",
                    "environment", "backdrop", "road", "street",
                ))
            ]
            apply_cinematic_lighting(bpy, scene, manifest, _cl_heroes or None)
        except Exception as _cl_err:
            print(f"[LIGHTING] cinematic lighting call failed: {_cl_err}", flush=True)
    log_stage("CINEMATIC_LIGHTING")

    # ══════════════════════════════════════════════════════════════════════
    # NUCLEAR LIGHTING GUARANTOR — runs after the sky is locked in.
    # HDRI light alone can't hit a dark hero (eagle in silhouette, black
    # Ferrari paint). This block aims a proper 3-point rig at the hero's
    # world-space center. It ONLY runs if the scene doesn't already have
    # at least two strong lights, so templates that carefully set their
    # own lighting are not disturbed.
    # ══════════════════════════════════════════════════════════════════════
    def _find_hero_center():
        """Bounding-box center of everything that looks like a hero mesh."""
        import mathutils  # type: ignore
        hero_terms = ("ground", "plane", "floor", "world_", "atmosphere", "sky", "environment")
        coords = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            name = obj.name.lower()
            if any(t in name for t in hero_terms):
                continue
            try:
                for corner in obj.bound_box:
                    coords.append(obj.matrix_world @ mathutils.Vector(corner))
            except Exception:
                continue
        if not coords:
            return mathutils.Vector((0.0, 0.0, 1.0))  # safe default
        xs = [c.x for c in coords]
        ys = [c.y for c in coords]
        zs = [c.z for c in coords]
        return mathutils.Vector((
            (min(xs) + max(xs)) / 2.0,
            (min(ys) + max(ys)) / 2.0,
            (min(zs) + max(zs)) / 2.0,
        ))

    def _aim_light_at(light_obj, target):
        """Rotate light so its -Z axis points at target."""
        import mathutils  # type: ignore
        direction = target - light_obj.location
        if direction.length < 0.001:
            return
        rot = direction.to_track_quat('-Z', 'Y').to_euler()
        light_obj.rotation_euler = rot

    def _install_hero_booster(hero_center):
        """
        Always-on key-light booster that guarantees the hero is not a
        silhouette regardless of what templates or HDRIs did. Placed a
        bit above and in front of hero, aimed straight at it. Only
        installed once per render (idempotent via name check).
        """
        try:
            if bpy.data.objects.get("NUCLEAR_HERO_BOOSTER"):
                return
            tod = ""
            try:
                tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
            except Exception:
                pass
            # Energy tuned by time-of-day. Night needs MORE local fill because
            # HDRI is dim and moonlight is weak.
            energy = 4800 if tod in ("night", "dusk") else 2800
            if tod in ("sunset", "golden_hour", "dawn"):
                color = (1.0, 0.85, 0.65)
            elif tod in ("night",):
                color = (0.85, 0.9, 1.0)
            else:
                color = (1.0, 0.97, 0.9)
            bpy.ops.object.light_add(
                type='AREA',
                location=(hero_center.x + 2.5, hero_center.y - 4.0, hero_center.z + 3.0),
            )
            booster = bpy.context.object
            booster.name = "NUCLEAR_HERO_BOOSTER"
            booster.data.energy = energy
            booster.data.size = 2.5
            try:
                booster.data.color = color
                booster.data.shape = 'DISK'
            except Exception:
                pass
            _aim_light_at(booster, hero_center)
            print(
                f"[LIGHT_FIX] hero booster installed (energy={energy}, tod={tod or 'day'})",
                flush=True,
            )
        except Exception as e:
            print(f"[LIGHT_FIX] hero booster failed: {e}", flush=True)

    def _install_hero_rim(hero_center):
        """
        Always-on RIM / back-light on the opposite side of the booster.
        Purpose: carve the hero's silhouette out of the background so at
        night it doesn't blur into the dark scene. This is what makes
        cinematic night shots (Blade Runner, Pixar) read — the subject
        always has a cool-colored edge light slicing around their shape.
        """
        try:
            if bpy.data.objects.get("NUCLEAR_HERO_RIM"):
                return
            tod = ""
            try:
                tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
            except Exception:
                pass
            # Rim is complementary: cool when the key is warm, warm when cool.
            if tod in ("night", "dusk"):
                color = (0.85, 0.75, 1.00)   # pale lavender rim
                energy = 3200
            elif tod in ("sunset", "dawn", "golden_hour"):
                color = (0.60, 0.75, 1.00)   # cool rim vs warm key
                energy = 2200
            else:
                color = (1.00, 0.95, 0.80)   # warm rim vs neutral daylight key
                energy = 1800
            # Behind the hero and slightly above, opposite the booster.
            bpy.ops.object.light_add(
                type='AREA',
                location=(hero_center.x - 3.5, hero_center.y + 5.0, hero_center.z + 4.5),
            )
            rim = bpy.context.object
            rim.name = "NUCLEAR_HERO_RIM"
            rim.data.energy = energy
            rim.data.size = 3.0
            try:
                rim.data.color = color
                rim.data.shape = 'DISK'
            except Exception:
                pass
            _aim_light_at(rim, hero_center)
            print(
                f"[LIGHT_FIX] hero rim installed (energy={energy}, tod={tod or 'day'})",
                flush=True,
            )
        except Exception as e:
            print(f"[LIGHT_FIX] hero rim failed: {e}", flush=True)

    def _lighting_force():
        try:
            scene = bpy.context.scene
            hero_center = _find_hero_center()

            # ── Step 1: re-aim every existing strong light at the hero ─────
            # Templates often place lights where the template expected the
            # hero to be. When the fetched hero lands somewhere else (or is
            # a different scale than planned), those lights miss. Always
            # re-point non-SUN strong lights so they actually hit the hero.
            reaimed = 0
            for obj in bpy.data.objects:
                if obj.type != 'LIGHT':
                    continue
                ldata = obj.data
                if ldata.type == 'SUN':
                    continue  # SUN is directional, aim already encoded in rotation
                if getattr(ldata, 'energy', 0) < 200:
                    continue
                try:
                    _aim_light_at(obj, hero_center)
                    reaimed += 1
                except Exception:
                    pass
            if reaimed:
                print(f"[LIGHT_FIX] re-aimed {reaimed} existing light(s) at hero", flush=True)

            # ── Step 2: count strong lights (after re-aim) ────────────────
            strong = 0
            for obj in bpy.data.objects:
                if obj.type != 'LIGHT':
                    continue
                ldata = obj.data
                if ldata.type == 'SUN':
                    strong += 1
                elif getattr(ldata, 'energy', 0) >= 200:
                    strong += 1

            # Even if the scene has lights, ALWAYS add a dedicated key
            # light aimed directly at the hero. HDRI-only illumination
            # routinely under-lights matte subjects (Ferrari paint, eagle
            # silhouette). The booster guarantees a bright hero read.
            _install_hero_booster(hero_center)
            # Always add a RIM on the opposite side so the hero silhouettes
            # out of the background — critical for night shots where the
            # environment is dim and the subject would otherwise blur into
            # the dark. Together booster+rim = always-on 2-point minimum.
            _install_hero_rim(hero_center)

            if strong >= 2:
                print(f"[LIGHT_FIX] scene already has {strong} strong lights — added booster only", flush=True)
                return

            # Pick key color temperature from scene_plan time_of_day.
            tod = ""
            try:
                tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
            except Exception:
                pass
            if tod in ("sunset", "golden_hour", "dawn"):
                key_color = (1.0, 0.82, 0.58)   # warm amber
                fill_color = (0.75, 0.82, 1.0)  # cool fill
            elif tod in ("night", "dusk"):
                key_color = (0.72, 0.82, 1.0)   # cool moonlight
                fill_color = (0.55, 0.65, 0.95)
            else:
                key_color = (1.0, 0.96, 0.88)   # near-daylight
                fill_color = (0.85, 0.9, 1.0)

            hero_center = _find_hero_center()
            print(f"[LIGHT_FIX] aiming 3-point rig at {tuple(round(c, 2) for c in hero_center)}", flush=True)

            # KEY (from front-right, 45° up). AREA for soft shadows.
            bpy.ops.object.light_add(type='AREA', location=(hero_center.x + 5, hero_center.y - 4, hero_center.z + 5))
            key = bpy.context.object
            key.name = "NUCLEAR_KEY"
            key.data.energy = 4000
            key.data.size = 3.0
            try:
                key.data.color = key_color
            except Exception:
                pass
            _aim_light_at(key, hero_center)

            # FILL (from front-left, lower, dimmer, wider). Cool color to balance key.
            bpy.ops.object.light_add(type='AREA', location=(hero_center.x - 5, hero_center.y - 3, hero_center.z + 2))
            fill = bpy.context.object
            fill.name = "NUCLEAR_FILL"
            fill.data.energy = 1200
            fill.data.size = 5.0
            try:
                fill.data.color = fill_color
            except Exception:
                pass
            _aim_light_at(fill, hero_center)

            # RIM (from behind, up high — separates hero from background).
            bpy.ops.object.light_add(type='SPOT', location=(hero_center.x, hero_center.y + 6, hero_center.z + 6))
            rim = bpy.context.object
            rim.name = "NUCLEAR_RIM"
            rim.data.energy = 2500
            try:
                rim.data.spot_size = 1.4  # ~80°
                rim.data.spot_blend = 0.4
                rim.data.color = (1.0, 1.0, 1.0)
            except Exception:
                pass
            _aim_light_at(rim, hero_center)

            print("[LIGHT_FIX] installed KEY+FILL+RIM — hero will no longer be in silhouette", flush=True)
        except Exception as e:
            print(f"[LIGHT_FIX] nuclear lighting crashed: {e}", flush=True)

    _lighting_force()

    # ── Forced-env light re-aim + hero boost ──────────────────────────
    # When a forced environment is present, the terrain/ground plane absorbs
    # a lot of ambient light and the hero can silhouette dark.  Re-aim all
    # non-hero lights at the hero's FINAL position (after env placement
    # may have shifted it) and give hero-specific lights a 1.5× energy
    # boost so the subject reads clearly against the backdrop.
    if manifest.get("_has_forced_environment"):
        try:
            from mathutils import Vector as _LFVec
            _env_hero_obj = None
            _env_hero_bbox_coords = []
            for _eho in bpy.data.objects:
                try:
                    if _eho.get("is_hero", False) and not _eho.get("is_environment", False):
                        if _eho.type == "MESH":
                            mw = _eho.matrix_world
                            for _c in _eho.bound_box:
                                _env_hero_bbox_coords.append(mw @ _LFVec(_c))
                            if _env_hero_obj is None:
                                _env_hero_obj = _eho
                except Exception:
                    pass
            if _env_hero_bbox_coords:
                _env_hero_center = _LFVec((
                    (min(c.x for c in _env_hero_bbox_coords) + max(c.x for c in _env_hero_bbox_coords)) * 0.5,
                    (min(c.y for c in _env_hero_bbox_coords) + max(c.y for c in _env_hero_bbox_coords)) * 0.5,
                    (min(c.z for c in _env_hero_bbox_coords) + max(c.z for c in _env_hero_bbox_coords)) * 0.5,
                ))
                _reaimed = 0
                _boosted = 0
                for _lt in bpy.data.objects:
                    if _lt.type != "LIGHT":
                        continue
                    _lname_lc = (_lt.name or "").lower()
                    try:
                        if "hero" in _lname_lc:
                            # Hero-specific light — boost energy
                            _lt.data.energy = float(_lt.data.energy) * 1.5
                            _boosted += 1
                        else:
                            # Non-hero light — re-aim at current hero center
                            _dir = _env_hero_center - _lt.location
                            if _dir.length > 0.001:
                                _lt.rotation_mode = "QUATERNION"
                                _lt.rotation_quaternion = _dir.to_track_quat("-Z", "Y")
                                _reaimed += 1
                    except Exception:
                        continue
                print(
                    f"[LIGHT_FIX] re-aimed {_reaimed} light(s) at hero center "
                    f"({_env_hero_center.x:.2f}, {_env_hero_center.y:.2f}, "
                    f"{_env_hero_center.z:.2f})",
                    flush=True,
                )
                if _boosted:
                    print(
                        f"[LIGHT_FIX] boosted {_boosted} hero light(s) 1.5× "
                        f"for forced env scene",
                        flush=True,
                    )
            else:
                print(
                    "[LIGHT_FIX] forced env present but no hero bbox — "
                    "skipping re-aim",
                    flush=True,
                )
        except Exception as _le_err:
            print(f"[LIGHT_FIX] forced-env re-aim failed (non-fatal): {_le_err}", flush=True)

    log_stage("LIGHTING_FIX")

    # ══════════════════════════════════════════════════════════════════════
    # NIGHT AMBIENCE LIGHTS — runs only when the scene is night/dusk so the
    # world doesn't look like it's lit solely by the moon. Adds a few
    # colored point lights (neon blue/magenta/amber) around the hero to
    # give practical source motivation — the Blade-Runner / Tokyo-alley
    # look that reads as "city night" instead of "moonlit field".
    # ══════════════════════════════════════════════════════════════════════
    def _night_ambience_force():
        try:
            tod = ""
            try:
                tod = str(manifest.get("_scene_plan", {}).get("time_of_day") or "").lower()
            except Exception:
                pass
            if tod not in ("night", "dusk"):
                return

            # Skip if someone already put colorful point lights around
            # the hero (template did its job).
            existing_points = sum(
                1 for obj in bpy.data.objects
                if obj.type == 'LIGHT' and getattr(obj.data, 'type', '') == 'POINT'
            )
            if existing_points >= 3:
                print(
                    f"[NIGHT_FIX] scene already has {existing_points} point lights — skipping",
                    flush=True,
                )
                return

            center = _find_hero_center()
            # Three practicals: magenta L, cyan R, amber back (like a sign behind hero).
            practicals = [
                {
                    "name": "NUCLEAR_NEON_MAGENTA",
                    "location": (center.x - 6, center.y - 2, center.z + 1.5),
                    "color": (1.0, 0.15, 0.8),
                    "energy": 900,
                },
                {
                    "name": "NUCLEAR_NEON_CYAN",
                    "location": (center.x + 6, center.y - 2, center.z + 1.5),
                    "color": (0.1, 0.7, 1.0),
                    "energy": 900,
                },
                {
                    "name": "NUCLEAR_NEON_AMBER",
                    "location": (center.x, center.y + 5, center.z + 2.8),
                    "color": (1.0, 0.55, 0.15),
                    "energy": 1400,
                },
            ]
            for p in practicals:
                try:
                    bpy.ops.object.light_add(type='POINT', location=p["location"])
                    lt = bpy.context.object
                    lt.name = p["name"]
                    lt.data.energy = p["energy"]
                    try:
                        lt.data.color = p["color"]
                        lt.data.shadow_soft_size = 0.8
                    except Exception:
                        pass
                except Exception as le:
                    print(f"[NIGHT_FIX] practical {p['name']} failed: {le}", flush=True)
            print("[NIGHT_FIX] added neon practicals (magenta/cyan/amber)", flush=True)
        except Exception as e:
            print(f"[NIGHT_FIX] night ambience crashed: {e}", flush=True)

    _night_ambience_force()
    log_stage("NIGHT_AMBIENCE")

    # ══════════════════════════════════════════════════════════════════════
    # NUCLEAR FRAMING GUARANTOR — the hero MUST be visible, well-scaled, and
    # not a tiny speck on an empty road. Templates set camera positions based
    # on assumptions about hero size that routinely break when the fetched
    # asset has a different scale than expected. This is the last line of
    # defense: measure the hero's world-space bbox, measure what fraction of
    # the frame it actually covers, and if < MIN_COVERAGE reposition the
    # camera at a proper 3/4 angle, distance derived from the lens FOV so
    # the hero fills ~42% of the frame with headroom above.
    # ══════════════════════════════════════════════════════════════════════
    # Aggressive fills — a world-class product frames the subject tight.
    # Previous values left the hero as a speck surrounded by scene. These
    # are tuned so the hero dominates the frame; the environment still
    # reads via the 3/4 angle + ambient fill + rim from earlier blocks.
    TARGET_FILL_FRAC  = 0.60   # day default — hero fills ~60% of frame diagonal
    HERO_MAX_DIAG_M   = 40.0   # meshes larger than this are env leaks, excluded
    def _framing_target_fill(manifest_ref) -> float:
        try:
            tod = str(manifest_ref.get("_scene_plan", {}).get("time_of_day") or "").lower()
        except Exception:
            tod = ""
        if tod in ("night", "dusk"):
            return 0.78   # night must be TIGHT — dim scene only reads close up
        if tod in ("sunset", "dawn", "golden_hour"):
            return 0.68
        return TARGET_FILL_FRAC

    def _mesh_diag(obj) -> float:
        """World-space bbox diagonal of a single mesh object (meters)."""
        import mathutils  # type: ignore
        try:
            corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
            xs = [v.x for v in corners]; ys = [v.y for v in corners]; zs = [v.z for v in corners]
            sx = max(xs) - min(xs); sy = max(ys) - min(ys); sz = max(zs) - min(zs)
            return (sx * sx + sy * sy + sz * sz) ** 0.5
        except Exception:
            return 0.0

    # ── Tag-based hero collection with size sanity ─────────────────────
    # Templates like scenic_landscape import their environment asset
    # (mountain, target_size=80m) via the same ``import_hero_asset_group``
    # path as dynamic heroes, so the mountain gets tagged ``is_hero=True``
    # alongside the real hero (pelican, 1.5m). Without per-object size
    # filtering, the combined bbox is dominated by the mountain and
    # FORCE_FIX scales everything down to invisibility.
    #
    # This helper returns only the tagged meshes whose individual world
    # dimensions are plausible for the manifest's ``hero_asset_type``.
    _HERO_SIZE_CAP_M = {
        "character":  5.0,
        "humanoid":   5.0,
        "robot":      6.0,
        "animal":    12.0,
        "vehicle":   20.0,
        "car":       20.0,
        "prop":       5.0,
        "product":    3.0,
        # Permissive for true environment-hero cases.
        "environment": 500.0,
        "building":    500.0,
        "landscape":   500.0,
    }

    def _collect_tagged_hero_meshes_filtered():
        """Return is_hero-tagged meshes, dropping env-scale outliers.
        Empty list when nothing is tagged (caller falls through to its
        own name-heuristic fallback).

        Two-stage filter:

          Stage A (per-mesh cap): drop tagged meshes whose own bbox is
              larger than the type cap. Catches a single 80 m mountain
              mesh tagged alongside a 1.5 m pelican.

          Stage B (per-cluster cap): group remaining meshes by their
              top-level parent root and drop any cluster whose *combined*
              world-space bbox exceeds the cap. Catches the scenic_landscape
              case where a mountain GLB is split into dozens of small leaf
              meshes (each <12 m, so stage A lets them through) that
              together span ~80 m. Without stage B, CAMERA_FIX computed a
              14 m combined bbox from mountain chunks + pelican and parked
              the camera 42 m away, rendering the pelican as a speck.

          Stage C (nearest-to-origin tiebreak): among clusters that pass
              both caps, prefer the one whose centroid is nearest the
              origin — templates place the hero near (0,0,0) while
              environment props (mountain at y≈18, ocean ring, etc.)
              are offset on the horizon.
        """
        from mathutils import Vector as _V

        tagged = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            try:
                # Skip World Development props — they're decoration, not hero
                if obj.get("is_world_dev", False):
                    continue
                if obj.get("is_hero", False):
                    tagged.append(obj)
            except Exception:
                continue
        if not tagged:
            return []

        hero_type = str(manifest.get("hero_asset_type", "") or "").lower()
        cap = _HERO_SIZE_CAP_M.get(hero_type, 20.0)

        # ── Stage A: per-mesh size cap ─────────────────────────────────
        kept_a, dropped_a = [], []
        for obj in tagged:
            try:
                md = max(obj.dimensions) if obj.dimensions else 0.0
            except Exception:
                md = 0.0
            if md <= cap:
                kept_a.append(obj)
            else:
                dropped_a.append((obj.name, md))
        if dropped_a:
            print(
                f"[HERO_TAG] stage A dropped {len(dropped_a)} oversized mesh(es) "
                f"(cap={cap:.1f}m for type={hero_type!r}): "
                f"{[(n, round(d, 1)) for n, d in dropped_a[:4]]}",
                flush=True,
            )
        if not kept_a:
            print(
                "[HERO_TAG] stage A emptied the set — keeping full tagged set",
                flush=True,
            )
            return tagged

        # ── Stage B: per-cluster size cap ──────────────────────────────
        # Group by top-level parent root so a mountain split across 30
        # leaf meshes is evaluated as a single cluster.
        def _root_of(o):
            cur = o
            while cur.parent is not None:
                cur = cur.parent
            return cur

        clusters: dict = {}
        for obj in kept_a:
            root = _root_of(obj)
            clusters.setdefault(root.name, []).append(obj)

        if len(clusters) <= 1:
            # Only one cluster — no cross-group leakage possible.
            return kept_a

        def _cluster_bbox_max(meshes):
            coords = []
            for o in meshes:
                for c in o.bound_box:
                    try:
                        coords.append(o.matrix_world @ _V(c))
                    except Exception:
                        pass
            if not coords:
                return 0.0, _V((0, 0, 0))
            xs = [c.x for c in coords]
            ys = [c.y for c in coords]
            zs = [c.z for c in coords]
            spread = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
            centroid = _V((
                (min(xs) + max(xs)) / 2,
                (min(ys) + max(ys)) / 2,
                (min(zs) + max(zs)) / 2,
            ))
            return spread, centroid

        cluster_stats = {
            root_name: _cluster_bbox_max(meshes)
            for root_name, meshes in clusters.items()
        }

        kept_b: list = []
        dropped_b: list = []
        for root_name, meshes in clusters.items():
            spread, _ = cluster_stats[root_name]
            if spread <= cap:
                kept_b.extend(meshes)
            else:
                dropped_b.append((root_name, spread, len(meshes)))

        if dropped_b:
            print(
                f"[HERO_TAG] stage B dropped {len(dropped_b)} oversized cluster(s) "
                f"(cap={cap:.1f}m): "
                f"{[(n, round(s, 1), f'{c} mesh') for n, s, c in dropped_b[:4]]}",
                flush=True,
            )

        if not kept_b:
            # Every cluster too big — keep the one nearest origin so the
            # scene has *something* framed rather than nothing.
            nearest = min(
                clusters.items(),
                key=lambda kv: cluster_stats[kv[0]][1].length,
            )
            print(
                f"[HERO_TAG] stage B emptied — falling back to nearest cluster "
                f"{nearest[0]!r} (spread={cluster_stats[nearest[0]][0]:.1f}m, "
                f"centroid_len={cluster_stats[nearest[0]][1].length:.1f}m)",
                flush=True,
            )
            return nearest[1]

        # ── Stage C: if multiple clusters survive, prefer the one
        # nearest origin (hero is placed at ~origin; env offset further).
        surviving_roots = [
            name for name, meshes in clusters.items() if meshes[0] in kept_b
        ]

        # ── Stage C.0 — forced_hero_id short-circuit ──────────────────
        # When the Asset Picker forced a specific library entry, the
        # glb_import stamps is_forced_hero=True on every imported mesh.
        # Find the cluster containing those meshes FIRST, skipping the
        # centroid heuristic entirely.  Prevents a prop that happens to
        # sit closer to origin from stealing framing from a lifted hero.
        _forced_id = str(manifest.get("forced_hero_id") or "").strip()

        # ── V1.3.4 Bug 1: pre-tag descendants of is_hero_root ──────────
        # When the manifest carries forced_hero_id but no mesh has
        # is_forced_hero=True yet (the .blend HERO_FALLBACK / multi-import
        # gap), walk every is_hero_root object's mesh descendants and
        # stamp the tag on those within 10m of origin (proximity filter
        # excludes env children that share a Sketchfab_model parent).
        # Runs ONCE before the existing tag-detection so the rest of the
        # cluster picker sees a populated tag set.
        if _forced_id:
            try:
                _existing_tagged = sum(
                    1 for _o in bpy.data.objects
                    if _o.type == "MESH" and _o.get("is_forced_hero", False)
                )
                if _existing_tagged == 0:
                    from mathutils import Vector as _FHTVec
                    _hero_roots = [
                        _o for _o in bpy.data.objects
                        if _o.get("is_hero_root", False)
                    ]
                    _stamped = 0
                    _stamp_proxim_skipped = 0
                    def _walk_descendants(parent):
                        for _ch in parent.children:
                            yield _ch
                            yield from _walk_descendants(_ch)
                    for _hroot in _hero_roots:
                        for _desc in _walk_descendants(_hroot):
                            if _desc.type != "MESH":
                                continue
                            try:
                                # World-space bbox center
                                _corners = [
                                    _desc.matrix_world @ _FHTVec(_c)
                                    for _c in _desc.bound_box
                                ]
                                if not _corners:
                                    continue
                                _ccx = sum(c.x for c in _corners) / len(_corners)
                                _ccy = sum(c.y for c in _corners) / len(_corners)
                                _ccz = sum(c.z for c in _corners) / len(_corners)
                                _d_origin = (_ccx*_ccx + _ccy*_ccy + _ccz*_ccz) ** 0.5
                                if _d_origin > 10.0:
                                    _stamp_proxim_skipped += 1
                                    continue
                                _desc["is_forced_hero"] = True
                                _stamped += 1
                            except Exception:
                                continue
                    if _stamped:
                        print(
                            f"[FORCED_HERO_TAG] applied is_forced_hero=True to "
                            f"{_stamped} descendant mesh(es) of "
                            f"forced_hero_id={_forced_id!r} "
                            f"(walked {len(_hero_roots)} is_hero_root parent(s); "
                            f"proximity-skipped {_stamp_proxim_skipped} env-placed "
                            f"mesh(es) > 10m from origin)",
                            flush=True,
                        )
                    elif _hero_roots:
                        print(
                            f"[FORCED_HERO_TAG] no descendants tagged — "
                            f"{len(_hero_roots)} is_hero_root parent(s) but "
                            f"all mesh descendants > 10m from origin "
                            f"(forced_hero_id={_forced_id!r}); falling back to "
                            f"existing HERO_TAG heuristics",
                            flush=True,
                        )
                    else:
                        print(
                            f"[FORCED_HERO_TAG] no is_hero_root parents found; "
                            f"forced_hero_id={_forced_id!r} cannot be propagated "
                            f"by descendant walk",
                            flush=True,
                        )
            except Exception as _fht_err:
                print(
                    f"[FORCED_HERO_TAG] pre-tag pass failed (non-fatal): "
                    f"{_fht_err}",
                    flush=True,
                )

        # ── V1.3.6 Fix 1: hide rig-control "orb" primitives ────────────
        # Some GLBs (e.g. horse.glb's Object_35) ship internal control
        # objects with is_hero=True but no is_forced_hero tag. They are
        # low-poly sphere-like meshes near the origin that render as
        # chrome orbs. After [FORCED_HERO_TAG] has stamped the real
        # hero descendants, sweep is_hero=True objects that did NOT
        # receive is_forced_hero=True and hide them from render when
        # they look like rig handles (low-poly + sphere-like dims).
        try:
            _cleanup_hidden = 0
            _cleanup_inspected = 0
            _name_hint_re = (
                "control", "rig", "handle", "ctrl", "helper", "empty"
            )
            for _co in list(bpy.data.objects):
                try:
                    if _co.type != "MESH":
                        continue
                    if not _co.get("is_hero", False):
                        continue
                    if _co.get("is_forced_hero", False):
                        continue
                    _cleanup_inspected += 1
                    _me = _co.data
                    _poly_count = len(_me.polygons) if _me else 0
                    _dx, _dy, _dz = _co.dimensions
                    _dmax = max(_dx, _dy, _dz) or 1e-9
                    _dmin = min(_dx, _dy, _dz)
                    _aspect = _dmax / max(_dmin, 1e-9)
                    _name_l = _co.name.lower()
                    _name_hint = any(h in _name_l for h in _name_hint_re)
                    # Heuristic: low-poly + sphere-like (max/min < 1.5)
                    # OR low-poly + name hint. Keep tight to avoid
                    # hiding real hero parts.
                    _is_low_poly = _poly_count > 0 and _poly_count < 200
                    _is_sphere_like = _aspect < 1.5
                    if _is_low_poly and (_is_sphere_like or _name_hint):
                        _co.hide_render = True
                        _co.hide_viewport = True
                        _cleanup_hidden += 1
                        print(
                            f"[CLEANUP] hiding untagged is_hero "
                            f"{_co.name!r} polys={_poly_count} "
                            f"dims=({_dx:.2f},{_dy:.2f},{_dz:.2f}) "
                            f"aspect={_aspect:.2f}",
                            flush=True,
                        )
                except Exception:
                    continue
            if _cleanup_inspected:
                print(
                    f"[CLEANUP] hid {_cleanup_hidden} untagged is_hero "
                    f"objects (inspected {_cleanup_inspected}; likely "
                    f"rig controls)",
                    flush=True,
                )
        except Exception as _clean_err:
            print(
                f"[CLEANUP] orb sweep failed (non-fatal): {_clean_err}",
                flush=True,
            )

        # ── V1.4.1.1: LOD twin cleanup ──────────────────────────────────
        # Some .blend files (notably bmw_01.blend) ship with two complete
        # copies of the hero geometry under sibling Sketchfab_model
        # parents. BLEND_DEDUP correctly merges the parent EMPTYs but its
        # transactional restore-matrix preserves world transforms of the
        # reparented sub-tree, leaving identical mesh twins at the
        # original authored scale alongside the LAYOUT-scaled keeper set.
        # The V1.3.6 orb cleanup gates on low-poly + sphere-like and
        # passes them through; result: dual-car render.
        #
        # Strategy: any is_hero=True && !is_forced_hero MESH that has an
        # exact twin (vert + face count + rounded world dims) among the
        # is_forced_hero set is a guaranteed LOD duplicate. hide_render
        # only — don't delete, so the data stays for debugging. Logs
        # [LOD_CLEANUP] detected N LOD variants, keeping highest-poly
        # cluster, hid M alternates.
        try:
            _lod_forced: dict = {}
            _lod_inspected = 0
            _lod_hidden = 0
            _lod_kept = 0
            for _fo in list(bpy.data.objects):
                try:
                    if _fo.type != "MESH":
                        continue
                    if not _fo.get("is_forced_hero", False):
                        continue
                    _md = _fo.data
                    if _md is None:
                        continue
                    _vc = len(_md.vertices)
                    _fc = len(_md.polygons)
                    _dx, _dy, _dz = _fo.dimensions
                    _key = (
                        _vc, _fc,
                        round(float(_dx), 2),
                        round(float(_dy), 2),
                        round(float(_dz), 2),
                    )
                    # Track every signature in the forced set so we can
                    # decide which to keep when the twin is also forced.
                    _lod_forced.setdefault(_key, []).append(_fo)
                except Exception:
                    continue
            for _co in list(bpy.data.objects):
                try:
                    if _co.type != "MESH":
                        continue
                    if not _co.get("is_hero", False):
                        continue
                    if _co.get("is_forced_hero", False):
                        continue
                    if _co.hide_render:
                        # Already hidden by orb sweep — skip.
                        continue
                    _md = _co.data
                    if _md is None:
                        continue
                    _vc = len(_md.vertices)
                    _fc = len(_md.polygons)
                    _dx, _dy, _dz = _co.dimensions
                    _key = (
                        _vc, _fc,
                        round(float(_dx), 2),
                        round(float(_dy), 2),
                        round(float(_dz), 2),
                    )
                    _lod_inspected += 1
                    if _key in _lod_forced:
                        # Exact twin of a forced-hero mesh → LOD duplicate.
                        _co.hide_render = True
                        _co.hide_viewport = True
                        _lod_hidden += 1
                        _twin = _lod_forced[_key][0]
                        print(
                            f"[LOD_CLEANUP] hiding LOD twin {_co.name!r} "
                            f"(verts={_vc} faces={_fc} "
                            f"dims=({_dx:.2f},{_dy:.2f},{_dz:.2f})) — "
                            f"twin of forced-hero {_twin.name!r}",
                            flush=True,
                        )
                    else:
                        _lod_kept += 1
                except Exception:
                    continue
            if _lod_inspected:
                # Count distinct LOD twin groups for the summary line.
                _lod_groups = sum(1 for v in _lod_forced.values() if v)
                print(
                    f"[LOD_CLEANUP] detected {_lod_groups} forced-hero "
                    f"signatures, inspected {_lod_inspected} untagged "
                    f"is_hero mesh(es); hid {_lod_hidden} LOD alternates, "
                    f"left {_lod_kept} non-twin mesh(es) alone",
                    flush=True,
                )
        except Exception as _lod_err:
            print(
                f"[LOD_CLEANUP] sweep failed (non-fatal): {_lod_err}",
                flush=True,
            )

        if _forced_id and len(surviving_roots) > 1:
            _forced_cluster_names: list = []
            for _root_name in surviving_roots:
                _cluster_meshes = clusters.get(_root_name) or []
                for _m in _cluster_meshes:
                    try:
                        if _m.get("is_forced_hero", False):
                            _forced_cluster_names.append(_root_name)
                            break
                    except Exception:
                        pass
            if _forced_cluster_names:
                # In rare cases multiple clusters share the tag (e.g.
                # dedup created a clone); pick the nearest-to-origin
                # among forced ones for consistency.
                if len(_forced_cluster_names) == 1:
                    _forced_winner = _forced_cluster_names[0]
                else:
                    _forced_winner = min(
                        _forced_cluster_names,
                        key=lambda n: cluster_stats[n][1].length,
                    )
                print(
                    f"[HERO_TAG] stage C: forced_hero_id={_forced_id!r} — "
                    f"picking cluster {_forced_winner!r} (contains is_forced_hero "
                    f"meshes). Dropped other clusters: "
                    f"{[n for n in surviving_roots if n != _forced_winner]}",
                    flush=True,
                )
                return clusters[_forced_winner]
            # No mesh tagged — warn loudly and fall through to
            # largest-root / centroid heuristic below.
            print(
                f"[HERO_TAG] WARN: forced_hero_id={_forced_id!r} set but no "
                f"cluster contains is_forced_hero meshes — falling back to "
                f"largest-root heuristic",
                flush=True,
            )

            # ── V1.3.1 Fix 3 — largest-root fallback for .blend vehicles ──
            # When a .blend import has 90+ body panels (BMW, Ferrari GT3),
            # the cluster-picker sees every panel as an independent root
            # because import_scene.blend doesn't always set parent
            # relationships on append.  The centroid heuristic then picks
            # a single 0.9m body panel closest to origin instead of the
            # whole vehicle.
            #
            # Remedy: group all surviving clusters by their topmost
            # parent.  The cluster whose parent-group has the largest
            # combined bbox wins — that's the whole vehicle.
            if _forced_id and len(surviving_roots) > 5:
                try:
                    import math as _rt_math
                    _by_parent: dict = {}
                    for _name in surviving_roots:
                        _ms = clusters.get(_name) or []
                        if not _ms:
                            continue
                        # Pick one representative; walk to topmost parent
                        _pivot = _ms[0]
                        _walker = _pivot
                        while _walker.parent is not None:
                            _walker = _walker.parent
                        _by_parent.setdefault(_walker.name, []).append((_name, _ms))

                    def _combined_diag(entries):
                        mn = [float("inf")] * 3
                        mx = [float("-inf")] * 3
                        any_mesh = False
                        for _cluster_name, _member_meshes in entries:
                            for _obj in _member_meshes:
                                if _obj.type != "MESH":
                                    continue
                                try:
                                    for _corner in _obj.bound_box:
                                        _world = _obj.matrix_world @ Vector(_corner)
                                        for _i in range(3):
                                            if _world[_i] < mn[_i]:
                                                mn[_i] = _world[_i]
                                            if _world[_i] > mx[_i]:
                                                mx[_i] = _world[_i]
                                    any_mesh = True
                                except Exception:
                                    pass
                        if not any_mesh:
                            return 0.0
                        return _rt_math.sqrt(sum((mx[_i] - mn[_i]) ** 2 for _i in range(3)))

                    if _by_parent:
                        _biggest_parent, _biggest_entries = max(
                            _by_parent.items(),
                            key=lambda kv: _combined_diag(kv[1]),
                        )
                        _root_diag = _combined_diag(_biggest_entries)
                        if _root_diag > 1.5:
                            # Collect every mesh across every cluster that
                            # shares this parent — that's our hero.
                            _merged_meshes: list = []
                            _member_cluster_names: list = []
                            for _cluster_name, _member_meshes in _biggest_entries:
                                _member_cluster_names.append(_cluster_name)
                                for _obj in _member_meshes:
                                    if _obj.type == "MESH":
                                        _merged_meshes.append(_obj)

                            # V1.3.2 Phase C — proximity filter.  The
                            # largest root can contain BOTH vehicle panels
                            # AND environment children (Sketchfab .blend
                            # packs do this).  Keep only meshes whose
                            # world-space bbox center is within 10m of
                            # origin — env children typically sit far away
                            # and get correctly excluded.
                            _proximity_kept: list = []
                            _proximity_dropped: list = []
                            for _obj in _merged_meshes:
                                try:
                                    _corners = [
                                        _obj.matrix_world @ Vector(_c)
                                        for _c in _obj.bound_box
                                    ]
                                    _ccx = sum(c.x for c in _corners) / len(_corners)
                                    _ccy = sum(c.y for c in _corners) / len(_corners)
                                    _ccz = sum(c.z for c in _corners) / len(_corners)
                                    _d = (_ccx * _ccx + _ccy * _ccy + _ccz * _ccz) ** 0.5
                                    if _d <= 10.0:
                                        _proximity_kept.append(_obj)
                                    else:
                                        _proximity_dropped.append((_obj.name, _d))
                                except Exception:
                                    _proximity_kept.append(_obj)

                            if _proximity_dropped:
                                print(
                                    f"[HERO_TAG] proximity-filter dropped "
                                    f"{len(_proximity_dropped)} env-placed "
                                    f"mesh(es) > 10m from origin: "
                                    f"{_proximity_dropped[:5]}",
                                    flush=True,
                                )

                            # Require the surviving set to be substantial;
                            # if the filter nuked everything we'd rather
                            # return the unfiltered merged set than crash.
                            if _proximity_kept:
                                _merged_meshes = _proximity_kept

                            print(
                                f"[HERO_TAG] fallback: picking root "
                                f"{_biggest_parent!r} with "
                                f"combined_diag={_root_diag:.2f}m "
                                f"({len(_merged_meshes)} meshes after "
                                f"proximity filter across "
                                f"{len(_biggest_entries)} clusters)",
                                flush=True,
                            )
                            return _merged_meshes
                        print(
                            f"[HERO_TAG] fallback: largest root diag "
                            f"{_root_diag:.2f}m < 1.5m — not a vehicle-sized "
                            f"group, falling through to centroid heuristic",
                            flush=True,
                        )
                except Exception as _root_err:
                    print(
                        f"[HERO_TAG] largest-root fallback error "
                        f"(non-fatal): {_root_err}",
                        flush=True,
                    )

        if len(surviving_roots) > 1:
            distances = {
                name: cluster_stats[name][1].length for name in surviving_roots
            }
            nearest_name = min(distances, key=distances.get)
            print(
                f"[HERO_TAG] stage C: {len(surviving_roots)} clusters survived; "
                f"picking {nearest_name!r} (centroid_len="
                f"{distances[nearest_name]:.1f}m). Dropped: "
                f"{[(n, round(distances[n], 1)) for n in surviving_roots if n != nearest_name]}",
                flush=True,
            )
            return clusters[nearest_name]

        return kept_b

    def _framing_collect_hero_meshes():
        """
        Return the meshes that actually represent the HERO — not the
        environment, not placeholder ground planes, not stadium bleachers.

        Strategy (in priority order):
          0. ``obj["is_hero"] == True`` tag wins above anything else. Set
             by import_glb_as_hero_group / import_hero_asset_group /
             import_hero_asset_path_fallback so we can cleanly separate
             hero geometry from environment meshes (mountain, ocean, etc.)
             that get imported via the same bpy.data.objects namespace.
          1. Name-based include — if any mesh has 'hero' or starts with
             'hero_proc_', use ONLY those. Strongest signal we have.
          2. Name-based exclude — drop anything matching env/ground/sky
             + common Sketchfab root-group junk (scenenode, rootnode, etc).
          3. Size sanity — drop any remaining mesh whose own bbox diagonal
             is > HERO_MAX_DIAG_M meters. A ferrari stand-in is ~4.5m; a
             horse ~2.5m; a stadium is ~200m. Anything huge is environment.
          4. If NOTHING survives, relax size rule and try again — some
             imported assets come in at 20-30m scale and we'd rather
             frame them than refuse to frame anything.
        """
        skip_terms = (
            "ground", "plane", "floor", "world_", "atmosphere", "sky",
            "environment", "backdrop", "road", "street", "sweep", "cove",
            "contactshadow", "nuclear_",
            # Scene keyword guarantor stand-ins — these are env, not hero.
            "mountain", "ocean", "dune", "tree_trunk", "tree_leaves",
            "snow_field",
            # Sketchfab root / Blender default names we don't want framing around.
            "scenenode", "rootnode", "sketchfab_model", "collection_",
        )

        # ── Step 0: is_hero tag wins, size-filtered ─────────────────────
        # Uses _collect_tagged_hero_meshes_filtered() so that a mountain
        # that was also tagged (scenic_landscape imports env via the same
        # hero-import path) doesn't dominate the hero bbox.
        tagged = _collect_tagged_hero_meshes_filtered()
        if tagged:
            print(
                f"[FRAME_FIX] found {len(tagged)} is_hero-tagged mesh(es) — "
                f"{[o.name for o in tagged[:6]]}",
                flush=True,
            )
            return tagged

        # ── Step 1: explicit hero names win ─────────────────────────────
        named_heroes = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            n = obj.name.lower()
            if "hero" in n and not any(t in n for t in ("nuclear_", "environment")):
                named_heroes.append(obj)
        if named_heroes:
            print(
                f"[FRAME_FIX] found {len(named_heroes)} explicit hero mesh(es) — "
                f"{[o.name for o in named_heroes[:6]]}",
                flush=True,
            )
            return named_heroes

        # ── Step 2+3: filter by name + size ─────────────────────────────
        survivors = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            n = obj.name.lower()
            if any(t in n for t in skip_terms):
                continue
            d = _mesh_diag(obj)
            if d > HERO_MAX_DIAG_M:
                print(
                    f"[FRAME_FIX] excluding '{obj.name}' (diag={d:.1f}m > "
                    f"{HERO_MAX_DIAG_M}m) — likely env leak",
                    flush=True,
                )
                continue
            survivors.append(obj)

        if survivors:
            return survivors

        # ── Step 4: size rule was too strict — relax it ──────────────────
        print("[FRAME_FIX] size filter killed everything — relaxing", flush=True)
        relaxed = []
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            n = obj.name.lower()
            if any(t in n for t in skip_terms):
                continue
            relaxed.append(obj)
        return relaxed

    def _framing_hero_bbox(meshes):
        """Return (min_vec, max_vec, center_vec, diagonal) in world space."""
        import mathutils  # type: ignore
        xs, ys, zs = [], [], []
        for obj in meshes:
            try:
                for corner in obj.bound_box:
                    w = obj.matrix_world @ mathutils.Vector(corner)
                    xs.append(w.x); ys.append(w.y); zs.append(w.z)
            except Exception:
                continue
        if not xs:
            return None
        mn = mathutils.Vector((min(xs), min(ys), min(zs)))
        mx = mathutils.Vector((max(xs), max(ys), max(zs)))
        center = (mn + mx) * 0.5
        size = mx - mn
        diag = max(0.01, (size.x ** 2 + size.y ** 2 + size.z ** 2) ** 0.5)
        return mn, mx, center, diag

    def _framing_project_coverage(cam, center, diag):
        """
        Approximate fraction of the frame diagonal the hero occupies.
        Fast heuristic: distance from camera to hero center vs FOV diagonal
        at that distance. coverage ≈ hero_diag / frame_diag_at_distance.
        """
        from math import tan
        try:
            cam_loc = cam.matrix_world.translation
            d = (center - cam_loc).length
            if d < 0.01:
                return 1.0
            # Camera angle is horizontal FOV; use it as an approximation.
            fov = max(0.1, float(cam.data.angle))
            frame_diag_at_d = 2.0 * d * tan(fov * 0.5) * 1.25  # 1.25 widens for diagonal
            return diag / max(0.001, frame_diag_at_d)
        except Exception:
            return 1.0  # assume ok if we can't measure

    def _count_keyframes(obj):
        """Count total keyframes across all fcurves (API-version agnostic)."""
        ad = getattr(obj, "animation_data", None)
        if not ad or not ad.action:
            return 0
        try:
            fcs = ad.action.fcurves
        except AttributeError:
            fcs = []
            if hasattr(ad.action, "layers") and ad.action.layers:
                _lyr = ad.action.layers[0]
                if hasattr(_lyr, "strips") and _lyr.strips:
                    _stp = _lyr.strips[0]
                    if hasattr(_stp, "channelbags") and _stp.channelbags:
                        fcs = _stp.channelbags[0].fcurves
        total = 0
        for fc in fcs:
            total += len(fc.keyframe_points)
        return total

    def _directed_behavior_active() -> tuple[bool, str]:
        """Is a directed shot behavior active?  Returns (is_active, behavior_key)."""
        _directed = {
            "driving", "racing", "flying", "walking", "galloping",
            "soaring", "climbing", "swimming", "running", "jumping",
        }
        # Behavior can come from several places depending on manifest shape
        _b = ""
        _dc = manifest.get("directorial_controls") or {}
        if isinstance(_dc, dict):
            _b = str(_dc.get("behavior") or _dc.get("motion_style") or "")
        if not _b:
            _director = manifest.get("director") or {}
            if isinstance(_director, dict):
                _b = str(_director.get("behavior") or "")
        if not _b:
            _sp = manifest.get("scene_plan") or {}
            if isinstance(_sp, dict):
                _style = str(_sp.get("animation_style") or "")
                # Map animation_style to behavior verbs
                if "vehicle_drive" in _style or "vehicle_drift" in _style:
                    _b = "driving"
                elif "character_walk" in _style:
                    _b = "walking"
                elif "character_dance" in _style:
                    _b = "dancing"
        _b = _b.lower().strip()
        return (_b in _directed, _b)

    def _scene_census(stage: str):
        """Log a detailed scene inventory for diagnostics.

        Emits a [SCENE_CENSUS @ stage] block covering hero/prop candidates,
        vehicle-like geometry, and the camera's animation state.  This is
        the log line that tells us whether dedup worked, whether the
        camera-subject lock held, and whether FRAME/CAMERA fix skipped
        or wiped animation.  Run immediately before FRAME_FIX and again
        immediately before RENDER_START.
        """
        try:
            _hero_list = []
            _prop_count = 0
            _vehicle_like = []
            _VEHICLE_HINTS = (
                "ferrari", "bmw", "sketchfab_model", "racecar",
                "vehicle", "car", "porsche", "lamborghini",
            )
            for _obj in bpy.data.objects:
                try:
                    _is_hero = bool(_obj.get("is_hero", False))
                    _is_prop = bool(_obj.get("is_prop", False))
                except Exception:
                    _is_hero = _is_prop = False
                if _is_prop:
                    _prop_count += 1
                if _is_hero:
                    try:
                        _loc = tuple(round(v, 2) for v in _obj.location)
                    except Exception:
                        _loc = (0.0, 0.0, 0.0)
                    _hero_list.append({
                        "name": _obj.name,
                        "type": _obj.type,
                        "location": _loc,
                        "keyframes": _count_keyframes(_obj),
                    })
                _nlower = (_obj.name or "").lower()
                if any(h in _nlower for h in _VEHICLE_HINTS):
                    try:
                        _loc = tuple(round(v, 2) for v in _obj.location)
                    except Exception:
                        _loc = (0.0, 0.0, 0.0)
                    _vehicle_like.append({
                        "name": _obj.name,
                        "type": _obj.type,
                        "location": _loc,
                        "keyframes": _count_keyframes(_obj),
                    })

            _cam = bpy.context.scene.camera
            _cam_info = None
            if _cam is not None:
                try:
                    _cloc = tuple(round(v, 2) for v in _cam.location)
                except Exception:
                    _cloc = (0.0, 0.0, 0.0)
                _track_to = None
                for _con in getattr(_cam, "constraints", []):
                    if _con.type == "TRACK_TO":
                        _track_to = getattr(_con.target, "name", "?") if _con.target else None
                        break
                _cam_info = {
                    "name": _cam.name,
                    "location": _cloc,
                    "keyframes": _count_keyframes(_cam),
                    "track_to_target": _track_to,
                }

            print(f"[SCENE_CENSUS @ {stage}]", flush=True)
            print(
                f"[SCENE_CENSUS]   hero_candidates: {len(_hero_list)} "
                f"{[(h['name'], h['keyframes']) for h in _hero_list[:6]]}",
                flush=True,
            )
            print(f"[SCENE_CENSUS]   prop_candidates: {_prop_count}", flush=True)
            print(
                f"[SCENE_CENSUS]   vehicle_like_objects: {len(_vehicle_like)} "
                f"{[(v['name'], v['keyframes']) for v in _vehicle_like[:6]]}",
                flush=True,
            )
            print(f"[SCENE_CENSUS]   camera: {_cam_info}", flush=True)
            print(
                f"[SCENE_CENSUS]   frame_range: "
                f"{bpy.context.scene.frame_start}..{bpy.context.scene.frame_end}",
                flush=True,
            )
        except Exception as _ce:
            print(f"[SCENE_CENSUS] error: {_ce}", flush=True)

    def _framing_reposition_camera(cam, center, diag):
        """Place camera at 3/4 angle, distance so hero fills TARGET_FILL_FRAC.

        Critical: nuke the camera's animation_data and any tracking
        constraints so the static placement we set here actually survives
        to render time. Templates that animated the camera via keyframes
        would otherwise override our reposition on playback.

        After placing the static framing we add a gentle orbit animation
        (12% arc over the shot) so the camera still has life.
        """
        from math import radians, sin, cos, tan
        import mathutils  # type: ignore

        # ── 1. GUARD: do not disturb directed shots ────────────────────────
        # If a directorial behavior (driving / walking / galloping / soaring /
        # climbing / swimming / flying / running / jumping / racing) is
        # active AND either the hero or camera has keyframes, FRAME_FIX
        # becomes a no-op.  This is the camera-subject lock rule: once a
        # shot is composed, we don't recompose it mid-pipeline.
        _directed_active, _beh = _directed_behavior_active()
        _cam_keyframes = _count_keyframes(cam)
        _hero_obj_for_guard = None
        for _o in bpy.data.objects:
            try:
                if _o.get("is_hero_root", False) or _o.get("is_hero", False):
                    _hero_obj_for_guard = _o
                    break
            except Exception:
                pass
        _hero_keyframes = _count_keyframes(_hero_obj_for_guard) if _hero_obj_for_guard else 0

        if _directed_active and (_hero_keyframes > 0 or _cam_keyframes > 0):
            print(
                f"[FRAME_FIX] SKIPPED — directed shot active "
                f"(behavior={_beh!r}, hero_anim={_hero_keyframes > 0}, "
                f"camera_anim={_cam_keyframes > 0})",
                flush=True,
            )
            # Lens is still safe to clamp; it never affects animation timing.
            try:
                cam.data.lens = max(24.0, min(85.0, float(cam.data.lens)))
            except Exception:
                cam.data.lens = 50.0
            return

        # Fallback legacy guard: even without a directed behavior, if the
        # camera has substantial keyframes (> 2) some motion profile ran
        # and we shouldn't overwrite it. Keeps the previous safety net.
        if _cam_keyframes > 2:
            print(
                f"[FRAME_FIX] preserving camera animation "
                f"({_cam_keyframes} keyframes detected — "
                f"non-directed motion profile); only lens may be adjusted",
                flush=True,
            )
            try:
                cam.data.lens = max(24.0, min(85.0, float(cam.data.lens)))
            except Exception:
                cam.data.lens = 50.0
            return

        # ── 1. Clear existing animation + constraints so reposition sticks ─
        try:
            if cam.animation_data:
                cam.animation_data_clear()
        except Exception as e:
            print(f"[FRAME_FIX] animation_data_clear failed: {e}", flush=True)
        # Target empty used by templates for TRACK_TO — remove constraints.
        for con in list(cam.constraints):
            try:
                cam.constraints.remove(con)
            except Exception:
                pass

        # ── 2. Lens/FOV: honor whatever template set unless absurd ─────────
        try:
            cam.data.lens = max(24.0, min(85.0, float(cam.data.lens)))
        except Exception:
            cam.data.lens = 50.0
        try:
            fov = max(0.3, float(cam.data.angle))
        except Exception:
            fov = radians(50.0)

        # ── 3. Distance so hero diagonal fills target (tod-aware) ─────────
        # Math: at distance d, frame's horizontal width ≈ 2 * d * tan(fov/2).
        # We want hero_diag to equal target_fill × frame_width, so:
        #     d = hero_diag / (target_fill × 2 × tan(fov/2))
        # Previous version multiplied frame_width by 1.25 "for diagonal" —
        # that silently pushed the camera 25% farther than intended and was
        # a big contributor to the "hero is a speck" failure mode.
        target_fill = _framing_target_fill(manifest)
        distance = diag / (target_fill * 2.0 * tan(fov * 0.5))
        # Safety: camera must be outside the bbox; use a modest margin.
        distance = max(distance, diag * 0.75)
        # HARD MAXIMUM — belt-and-suspenders against pathological hero sizes.
        # The math above can still push the camera far if diag is weird;
        # these caps enforce that no hero is ever more than 8/20/40m away
        # by absolute world units. Small subjects (cat, dolphin, product)
        # must be ~8m max, medium (car, horse, person) ~20m max, large
        # (whale, building, stadium) ~40m max. Beyond these, the subject
        # becomes unreadable on screen regardless of target_fill math.
        if diag < 3.0:
            hard_max = 8.0
        elif diag < 10.0:
            hard_max = 20.0
        else:
            hard_max = 40.0
        if distance > hard_max:
            print(
                f"[FRAME_FIX] distance {distance:.2f}m exceeds hard_max "
                f"{hard_max}m for diag={diag:.2f}m — clamping",
                flush=True,
            )
            distance = hard_max

        # ── 4. 3/4 angle position + aim ────────────────────────────────────
        angle = radians(22.5)
        cam_x = center.x + distance * sin(angle)
        cam_y = center.y - distance * cos(angle)
        # Slight eye-level rise for subject — 15% of the hero's own diagonal.
        # Previously used diag*0.18 which, combined with a too-far distance,
        # put the camera pointing DOWN at the subject from above.
        cam_z = center.z + diag * 0.15

        cam.location = (cam_x, cam_y, cam_z)
        direction = center - mathutils.Vector(cam.location)
        if direction.length > 0.001:
            rot = direction.to_track_quat('-Z', 'Y').to_euler()
            cam.rotation_euler = rot

        # ── 5. Gentle orbit so the shot has life (12° over duration) ──────
        try:
            frame_start = scene.frame_start
            frame_end = scene.frame_end
            if frame_end > frame_start + 2:
                # Keyframe current pose at frame_start
                cam.keyframe_insert(data_path="location", frame=frame_start)
                cam.keyframe_insert(data_path="rotation_euler", frame=frame_start)
                # Compute orbit-end position: same elevation, rotated +12°
                end_angle = angle + radians(12.0)
                cam.location = (
                    center.x + distance * sin(end_angle),
                    center.y - distance * cos(end_angle),
                    cam_z,
                )
                direction_end = center - mathutils.Vector(cam.location)
                if direction_end.length > 0.001:
                    cam.rotation_euler = direction_end.to_track_quat('-Z', 'Y').to_euler()
                cam.keyframe_insert(data_path="location", frame=frame_end)
                cam.keyframe_insert(data_path="rotation_euler", frame=frame_end)
                # Make the interpolation smooth (bezier default is fine).
        except Exception as e:
            print(f"[FRAME_FIX] orbit keyframing skipped: {e}", flush=True)

        print(
            f"[FRAME_FIX] repositioned camera | center=({center.x:.2f},"
            f"{center.y:.2f},{center.z:.2f}) diag={diag:.2f} dist={distance:.2f} "
            f"(animation cleared, orbit added)",
            flush=True,
        )

    def _framing_pick_nearest_origin(meshes):
        """Fallback: the mesh whose world-space center is closest to (0,0,0).

        Templates consistently anchor heroes at the origin. When all other
        filters fail to isolate the hero (e.g. unnamed Sketchfab root with
        30 child meshes all passing the name filter), the true hero is
        usually the mesh whose bbox center is nearest origin.
        """
        import mathutils  # type: ignore
        best = None
        best_d = float('inf')
        origin = mathutils.Vector((0.0, 0.0, 0.0))
        for obj in meshes:
            try:
                corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
                xs = [v.x for v in corners]; ys = [v.y for v in corners]; zs = [v.z for v in corners]
                cx = (min(xs) + max(xs)) * 0.5
                cy = (min(ys) + max(ys)) * 0.5
                cz = (min(zs) + max(zs)) * 0.5
                c = mathutils.Vector((cx, cy, cz))
                d = (c - origin).length
                if d < best_d:
                    best_d = d
                    best = obj
            except Exception:
                continue
        return best

    def _framing_force():
        """
        UNCONDITIONALLY reframe the camera around the hero.

        Previous version gated the reframe on a coverage check — but that
        check used the same bbox we'd be reframing to, making the logic
        circular. If the bbox was wrong (env leak, huge Sketchfab root),
        the coverage would also be wrong, and we'd leave a broken framing
        alone thinking it was fine.

        World-class rule: every single render gets a purposeful framing.
        Templates may have set something reasonable; we overwrite with
        something deterministic so behavior is predictable across all
        assets and scene types.
        """
        try:
            cam = scene.camera
            if not cam:
                print("[FRAME_FIX] no camera — skipping framing check", flush=True)
                return
            heroes = _framing_collect_hero_meshes()
            if not heroes:
                print("[FRAME_FIX] no hero meshes found — skipping", flush=True)
                return
            bbox = _framing_hero_bbox(heroes)
            if not bbox:
                print("[FRAME_FIX] hero bbox unavailable — skipping", flush=True)
                return
            _mn, _mx, center, diag = bbox
            # Diagnostic: print first few hero names + their individual diagonals
            # so broken framings can be traced from logs.
            diag_report = [(o.name, round(_mesh_diag(o), 2)) for o in heroes[:6]]
            print(
                f"[FRAME_FIX] hero bbox diag={diag:.2f}m center="
                f"({center.x:.1f},{center.y:.1f},{center.z:.1f}) "
                f"meshes={diag_report}",
                flush=True,
            )
            # Last-resort safety: if the bbox is still absurdly large (> 20m),
            # something env-like leaked past all filters. Fall back to framing
            # on the single mesh closest to origin — that's almost always the
            # hero, since templates anchor heroes at (0,0,0).
            if diag > 20.0:
                print(
                    f"[FRAME_FIX] bbox suspiciously large ({diag:.1f}m) — "
                    f"falling back to nearest-origin mesh",
                    flush=True,
                )
                fallback = _framing_pick_nearest_origin(heroes)
                if fallback is not None:
                    one = _framing_hero_bbox([fallback])
                    if one is not None:
                        _mn, _mx, center, diag = one
                        print(
                            f"[FRAME_FIX] fallback hero='{fallback.name}' "
                            f"diag={diag:.2f}m center=({center.x:.1f},"
                            f"{center.y:.1f},{center.z:.1f})",
                            flush=True,
                        )
            # ALWAYS reposition — deterministic, predictable, correct.
            _framing_reposition_camera(cam, center, diag)
        except Exception as e:
            print(f"[FRAME_FIX] framing guarantor crashed: {e}", flush=True)

    # ══════════════════════════════════════════════════════════════════════
    # HERO SCALE NORMALIZER — many Sketchfab assets import at extreme
    # scales (0.01 m robots, 200 m dragons). The framing guarantor would
    # then over-correct camera distance and the creature animation would
    # cycle through too-small-to-see loops. Clamp each hero group to a
    # sensible size before framing runs. Runs only when scale is clearly
    # pathological — well-placed assets are left alone.
    # ══════════════════════════════════════════════════════════════════════
    _HERO_TARGET_SIZES = {
        "character": 1.8,
        "humanoid":  1.8,
        "robot":     1.8,
        "animal":    1.2,
        "vehicle":   4.5,
        "car":       4.5,
        "product":   0.35,
        "prop":      0.6,
    }

    def _hero_scale_normalize():
        try:
            heroes = _framing_collect_hero_meshes()
            if not heroes:
                return
            bbox = _framing_hero_bbox(heroes)
            if not bbox:
                return
            _mn, _mx, _center, diag = bbox
            if diag <= 0.0:
                return

            asset_type = str(manifest.get("hero_asset_type", "") or "").lower()
            target = _HERO_TARGET_SIZES.get(asset_type, 1.8)

            # V1.4.1 floor decision: lower bound 0.35×target → 0.20×target.
            # Many legitimate assets — particularly vehicles in
            # character-scale environments — land in the 20–35% band and
            # were being force-rescaled up. The 20% floor lets them
            # render at their authored size. Outer floor 0.05m → 0.02m to
            # stay below the new HERO_VERIFY bbox_sane lower bound (0.2m)
            # so a 0.06m hero still gets force-scaled instead of slipping
            # past untouched. Upper bounds unchanged.
            # Only act on clearly-wrong scales. Leave anything reasonable alone.
            if diag < 0.02 or diag > 120.0:
                factor = target / diag
            elif diag < target * 0.20:
                factor = target / diag
            elif diag > target * 6.0:
                factor = target / diag
            else:
                print(
                    f"[HERO_SCALE] hero diag={diag:.2f}m ok for type={asset_type!r} "
                    f"target={target:.1f}m — leaving alone",
                    flush=True,
                )
                return

            factor = max(0.001, min(1000.0, factor))

            # Walk to the top-level parent of each hero mesh, then scale
            # unique roots. Scaling the mesh directly under an armature
                # parent breaks the rig; scaling the root preserves it.
            roots: list = []
            seen: set = set()
            for obj in heroes:
                root = obj
                while root.parent is not None and root.parent not in seen:
                    root = root.parent
                if root.name in seen:
                    continue
                seen.add(root.name)
                roots.append(root)

            print(
                f"[HERO_SCALE] diag={diag:.3f}m type={asset_type!r} target={target:.1f}m "
                f"factor={factor:.3f} across {len(roots)} root(s)",
                flush=True,
            )
            for root in roots:
                try:
                    root.scale = (
                        root.scale.x * factor,
                        root.scale.y * factor,
                        root.scale.z * factor,
                    )
                except Exception as se:
                    print(f"[HERO_SCALE] scale apply failed on {root.name}: {se}", flush=True)

            try:
                bpy.context.view_layer.update()
            except Exception:
                pass

            # Re-ground: after scaling, the hero's bottom may no longer be at z=0.
            try:
                bbox2 = _framing_hero_bbox(_framing_collect_hero_meshes())
                if bbox2:
                    _mn2, _mx2, _c2, _d2 = bbox2
                    dz = -_mn2.z
                    if abs(dz) > 0.01:
                        for root in roots:
                            try:
                                root.location = (
                                    root.location.x,
                                    root.location.y,
                                    root.location.z + dz,
                                )
                            except Exception:
                                pass
                        print(f"[HERO_SCALE] re-grounded by dz={dz:.3f}m", flush=True)
            except Exception as ge:
                print(f"[HERO_SCALE] re-ground skipped: {ge}", flush=True)
        except Exception as e:
            print(f"[HERO_SCALE] normalize crashed (non-fatal): {e}", flush=True)

    # ══════════════════════════════════════════════════════════════════════
    # POST-IMPORT HERO VERIFICATION — ground + scale + center + visibility.
    # Runs BEFORE the older _hero_scale_normalize so it catches cases the
    # looser thresholds there would miss (microscopic chef, floating car).
    # ══════════════════════════════════════════════════════════════════════
    def _verify_and_fix_hero():
        """
        Post-import verification pass:
        1. Confirm hero objects exist and have geometry
        2. Ground them to z=0 (fixes floating car)
        3. Scale to appropriate size (fixes microscopic chef)
        4. Center at origin if way off-screen
        5. Ensure visibility (not hidden)
        """
        try:
            import mathutils  # type: ignore
            heroes = _framing_collect_hero_meshes()
            if not heroes:
                print("[VERIFY] WARNING: No hero objects found after import!", flush=True)
                return

            # --- CHECK 1: Do objects have actual geometry? ---
            real_objects = []
            for obj in heroes:
                if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 3:
                    real_objects.append(obj)
                elif obj.type == 'ARMATURE':
                    real_objects.append(obj)
                elif obj.type == 'EMPTY' and obj.children:
                    real_objects.append(obj)
            if not real_objects:
                print("[VERIFY] WARNING: Hero objects have no usable geometry!", flush=True)
                return

            # --- CHECK 2: Get bounding box ---
            all_coords = []
            for obj in heroes:
                if obj.type == 'MESH' and hasattr(obj, 'bound_box'):
                    for corner in obj.bound_box:
                        try:
                            world_coord = obj.matrix_world @ mathutils.Vector(corner)
                            all_coords.append(world_coord)
                        except Exception:
                            pass
            if not all_coords:
                print("[VERIFY] Cannot compute bounding box — skipping", flush=True)
                return

            min_x = min(c.x for c in all_coords)
            max_x = max(c.x for c in all_coords)
            min_y = min(c.y for c in all_coords)
            max_y = max(c.y for c in all_coords)
            min_z = min(c.z for c in all_coords)
            max_z = max(c.z for c in all_coords)
            width = max_x - min_x
            depth = max_y - min_y
            height = max_z - min_z
            max_dim = max(width, depth, height, 0.001)
            center = mathutils.Vector(((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2))

            print(
                f"[VERIFY] Hero bounds: {width:.2f} x {depth:.2f} x {height:.2f} m",
                flush=True,
            )
            print(
                f"[VERIFY] Hero center: ({center.x:.2f}, {center.y:.2f}, {center.z:.2f})",
                flush=True,
            )
            print(f"[VERIFY] Hero bottom Z: {min_z:.3f}", flush=True)

            # Walk to top-level parent roots for all transforms.
            roots: list = []
            seen_roots: set = set()
            for obj in heroes:
                root = obj
                while root.parent is not None:
                    root = root.parent
                if root.name not in seen_roots:
                    seen_roots.add(root.name)
                    roots.append(root)

            # --- CHECK 3: GROUNDING — force bottom of hero to z=0 ---
            # Skip when forced environment placement set hero on the env
            # surface — that placement is authoritative.  Re-grounding to
            # z=0 here would undo the env-relative hero position.
            if manifest.get("_env_placement_final"):
                print(
                    f"[VERIFY] re-ground SKIPPED — forced env placement is "
                    f"authoritative (hero bottom z={min_z:.3f} intentional)",
                    flush=True,
                )
            elif abs(min_z) > 0.02:
                z_offset = -min_z
                for root in roots:
                    try:
                        root.location.z += z_offset
                    except Exception:
                        pass
                print(
                    f"[VERIFY] GROUNDED: moved hero by dz={z_offset:.3f}m "
                    f"(was floating at z={min_z:.3f})",
                    flush=True,
                )
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass

            # --- CHECK 3b: OCEAN OVERRIDE — lift hero above water surface ---
            # ocean_scene has its water surface at z ~ -0.1. After grounding
            # moved the hero bottom to z=0, the hero is AT the surface —
            # dolphins/whales should be ABOVE it. Re-measure the actual
            # post-grounding bottom z and lift if needed.
            _template_name = str(manifest.get("template_name") or "").lower()
            if _template_name == "ocean_scene":
                # Re-measure actual bottom after grounding
                _ocean_coords = []
                for _oobj in heroes:
                    if _oobj.type == 'MESH' and hasattr(_oobj, 'bound_box'):
                        for _oc in _oobj.bound_box:
                            try:
                                _ocean_coords.append(
                                    _oobj.matrix_world @ mathutils.Vector(_oc)
                                )
                            except Exception:
                                pass
                if _ocean_coords:
                    _ocean_bottom = min(c.z for c in _ocean_coords)
                    if _ocean_bottom < 1.0:
                        _ocean_lift = 1.5 - _ocean_bottom
                        _moved_roots: set = set()
                        for _oobj in heroes:
                            _oroot = _oobj
                            while _oroot.parent is not None:
                                _oroot = _oroot.parent
                            if _oroot.name not in _moved_roots:
                                _oroot.location.z += _ocean_lift
                                _moved_roots.add(_oroot.name)
                        print(
                            f"[VERIFY] OCEAN_LIFT: raised hero by "
                            f"{_ocean_lift:.2f}m (bottom was z="
                            f"{_ocean_bottom:.2f}, now z~1.5)",
                            flush=True,
                        )
                        try:
                            bpy.context.view_layer.update()
                        except Exception:
                            pass

            # --- CHECK 3c: ANTI-BURIAL — ensure hero center is above ground ---
            # Models in non-standing poses (lying horse, crouching cat) have
            # their lowest vertex at the belly/chest. Grounding to z=0 means
            # the legs/lower body goes BELOW the ground plane. This check
            # lifts the hero so at least 85% of its volume is above ground.
            if _template_name != "ocean_scene":
                try:
                    _ab_coords = []
                    for _abobj in heroes:
                        if _abobj.type == 'MESH' and hasattr(_abobj, 'bound_box'):
                            for _abc in _abobj.bound_box:
                                try:
                                    _ab_coords.append(
                                        _abobj.matrix_world @ mathutils.Vector(_abc)
                                    )
                                except Exception:
                                    pass
                    if _ab_coords:
                        _ab_min_z = min(c.z for c in _ab_coords)
                        _ab_max_z = max(c.z for c in _ab_coords)
                        _ab_center_z = (_ab_min_z + _ab_max_z) / 2.0
                        _ab_height = _ab_max_z - _ab_min_z
                        # If the hero's CENTER is below 15% of its height
                        # above ground, it's buried
                        _ab_min_visible = _ab_height * 0.15
                        if _ab_height > 0.01 and _ab_center_z < _ab_min_visible:
                            _ab_lift = _ab_min_visible - _ab_min_z
                            _ab_moved: set = set()
                            for _abobj in heroes:
                                _abroot = _abobj
                                while _abroot.parent is not None:
                                    _abroot = _abroot.parent
                                if _abroot.name not in _ab_moved:
                                    _abroot.location.z += _ab_lift
                                    _ab_moved.add(_abroot.name)
                            try:
                                bpy.context.view_layer.update()
                            except Exception:
                                pass
                            print(
                                f"[VERIFY] ANTI-BURIAL: lifted hero by "
                                f"{_ab_lift:.3f}m (center was at "
                                f"z={_ab_center_z:.3f}, now visible "
                                f"above ground)",
                                flush=True,
                            )
                except Exception as _ab_err:
                    print(
                        f"[VERIFY] anti-burial check failed (non-fatal): "
                        f"{_ab_err}",
                        flush=True,
                    )

            # --- CHECK 4: SCALE — force reasonable size ---
            asset_type = str(manifest.get("hero_asset_type", "") or "").lower()
            target_sizes = {
                "character": 1.8, "humanoid": 1.8, "robot": 1.8,
                "animal": 1.2, "vehicle": 4.5, "car": 4.5,
                "product": 0.4, "prop": 0.8,
                "environment": 10.0, "building": 15.0,
            }
            target = target_sizes.get(asset_type, 1.5)

            # Use HEIGHT for characters/animals, MAX DIM for vehicles/props
            if asset_type in ("character", "humanoid", "animal", "robot"):
                reference_dim = height
            else:
                reference_dim = max_dim

            needs_scale = False
            scale_factor = 1.0
            if reference_dim < 0.01:
                scale_factor = target / max(max_dim, 0.001)
                needs_scale = True
                print(f"[VERIFY] CRITICAL: Hero nearly invisible ({reference_dim:.4f}m)", flush=True)
            elif reference_dim < target * 0.2:
                scale_factor = target / reference_dim
                needs_scale = True
                print(
                    f"[VERIFY] Too small: {reference_dim:.3f}m (target: {target:.1f}m)",
                    flush=True,
                )
            elif reference_dim > target * 10:
                scale_factor = target / reference_dim
                needs_scale = True
                print(
                    f"[VERIFY] Too large: {reference_dim:.1f}m (target: {target:.1f}m)",
                    flush=True,
                )

            if needs_scale:
                scale_factor = max(0.001, min(5000.0, scale_factor))
                for root in roots:
                    try:
                        root.scale = (
                            root.scale.x * scale_factor,
                            root.scale.y * scale_factor,
                            root.scale.z * scale_factor,
                        )
                    except Exception:
                        pass
                print(
                    f"[VERIFY] SCALED: factor={scale_factor:.3f}, new size≈{target:.1f}m",
                    flush=True,
                )
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass

                # Re-ground after scaling
                all_coords2 = []
                for obj in heroes:
                    if obj.type == 'MESH' and hasattr(obj, 'bound_box'):
                        for corner in obj.bound_box:
                            try:
                                all_coords2.append(obj.matrix_world @ mathutils.Vector(corner))
                            except Exception:
                                pass
                if all_coords2:
                    new_min_z = min(c.z for c in all_coords2)
                    if abs(new_min_z) > 0.02:
                        for root in roots:
                            try:
                                root.location.z -= new_min_z
                            except Exception:
                                pass
                        print("[VERIFY] Re-grounded after scaling", flush=True)

            # --- CHECK 5: CENTER — if hero is way off-screen, move to origin ---
            if abs(center.x) > 50 or abs(center.y) > 50:
                offset_x = -center.x
                offset_y = -center.y
                for root in roots:
                    try:
                        root.location.x += offset_x
                        root.location.y += offset_y
                    except Exception:
                        pass
                print(
                    f"[VERIFY] CENTERED: moved hero by ({offset_x:.1f}, {offset_y:.1f})",
                    flush=True,
                )

            # --- CHECK 6: VISIBILITY — ensure objects are not hidden ---
            for obj in heroes:
                try:
                    obj.hide_viewport = False
                    obj.hide_render = False
                except Exception:
                    pass

            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
        except Exception as e:
            print(f"[VERIFY] verify_and_fix_hero crashed (non-fatal): {e}", flush=True)

    _verify_and_fix_hero()

    _hero_scale_normalize()

    # Diagnostic census before FRAME_FIX — captures hero/camera state
    # pre-repositioning so we can see what the framing stage inherited.
    _scene_census("pre_FRAME_FIX")

    _framing_force()

    # ══════════════════════════════════════════════════════════════════════
    # AERIAL-ANGLE GUARD — detect a camera that ended up looking nearly
    # straight down at the hero (birds-eye / top-down) and reset it to a
    # cinematic 3/4 angle. This is a safety net: templates or upstream
    # steps occasionally park the camera high above the subject with
    # minimal XY offset, which reads as a surveillance shot instead of a
    # commercial. We touch the camera ONLY when the downward-looking
    # condition is met so well-framed shots stay untouched.
    # ══════════════════════════════════════════════════════════════════════
    def _aerial_angle_guard():
        import math
        # Skip when forced environment placement is authoritative — the
        # high-Z camera set by _adjust_camera_for_environment is correct
        # (hero sits at z≈0 on bottom-snapped env, camera pulled back to
        # frame both), not a top-down error to correct.
        if manifest.get("_env_placement_final"):
            print(
                "[AERIAL_GUARD] SKIPPED — forced environment placement is final",
                flush=True,
            )
            return
        try:
            cam = scene.camera
            if cam is None:
                return
            heroes = _framing_collect_hero_meshes()
            if not heroes:
                return
            bbox = _framing_hero_bbox(heroes)
            if not bbox:
                return
            _mn, _mx, center, diag = bbox
            if diag > 20.0:
                fallback = _framing_pick_nearest_origin(heroes)
                if fallback is not None:
                    one = _framing_hero_bbox([fallback])
                    if one is not None:
                        _mn, _mx, center, diag = one

            import mathutils  # type: ignore
            cam_loc = cam.matrix_world.translation
            dx = cam_loc.x - center.x
            dy = cam_loc.y - center.y
            dz = cam_loc.z - center.z
            xy_dist = math.sqrt(dx * dx + dy * dy)

            # Aerial signature: camera far ABOVE hero (more than 2.5x the
            # hero diagonal in Z) AND horizontal offset tiny relative to
            # vertical offset (XY within 60% of Z rise). That's the shape
            # of a top-down shot.
            aerial_z_threshold = max(diag * 2.5, 6.0)
            is_aerial = (dz > aerial_z_threshold) and (xy_dist < dz * 0.6)
            if not is_aerial:
                return

            print(
                f"[AERIAL_GUARD] aerial camera detected "
                f"(dz={dz:.2f}m xy={xy_dist:.2f}m diag={diag:.2f}m) — "
                f"resetting to 3/4 cinematic angle",
                flush=True,
            )

            # Re-derive distance the same way _framing_reposition_camera does
            # so hero fill stays consistent with the rest of the pipeline.
            try:
                fov = max(0.3, float(cam.data.angle))
            except Exception:
                fov = math.radians(50.0)
            target_fill = _framing_target_fill(manifest)
            ideal_distance = diag / (target_fill * 2.0 * math.tan(fov * 0.5))
            ideal_distance = max(ideal_distance, diag * 0.75)
            if diag < 3.0:
                ideal_distance = min(ideal_distance, 8.0)
            elif diag < 10.0:
                ideal_distance = min(ideal_distance, 20.0)
            else:
                ideal_distance = min(ideal_distance, 40.0)

            angle_horizontal = math.radians(30.0)   # 30° around Z
            angle_vertical   = math.radians(20.0)   # 20° above horizon

            cam_x = center.x + ideal_distance * math.sin(angle_horizontal) * math.cos(angle_vertical)
            cam_y = center.y - ideal_distance * math.cos(angle_horizontal) * math.cos(angle_vertical)
            cam_z = center.z + ideal_distance * math.sin(angle_vertical)
            # Minimum 1 m above ground — a camera below floor level is always wrong.
            cam_z = max(cam_z, 1.0)

            # Strip any lingering animation/constraints so this placement sticks.
            try:
                if cam.animation_data:
                    cam.animation_data_clear()
            except Exception:
                pass
            for con in list(cam.constraints):
                try:
                    cam.constraints.remove(con)
                except Exception:
                    pass

            cam.location = (cam_x, cam_y, cam_z)
            direction = center - mathutils.Vector(cam.location)
            if direction.length > 0.001:
                cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

            print(
                f"[AERIAL_GUARD] reset camera to ({cam_x:.2f},{cam_y:.2f},{cam_z:.2f}) "
                f"aimed at ({center.x:.2f},{center.y:.2f},{center.z:.2f})",
                flush=True,
            )
        except Exception as e:
            print(f"[AERIAL_GUARD] crashed: {e}", flush=True)

    _aerial_angle_guard()

    # ══════════════════════════════════════════════════════════════════════
    # CAMERA MOTION TRACKING — if the hero is walking / running / driving
    # etc., make the camera follow its forward translation so the shot
    # doesn't leave the subject behind. Preserves the camera's existing
    # orbit keyframes by layering the follow offset on top of whatever
    # the framing step left. When the hero is static this is a no-op.
    # ══════════════════════════════════════════════════════════════════════
    _MOTION_TRACKING_ACTIONS = {
        "walking", "walk", "running", "run", "jogging", "jog", "sprint", "sprinting",
        "driving", "drive", "racing", "race",
        "galloping", "gallop", "swimming", "swim", "flying", "fly",
        "soaring", "soar",
    }

    def _camera_motion_tracking():
        try:
            cam = scene.camera
            if cam is None:
                return
            action_name = str(manifest.get("action", "") or "").lower().strip()
            if action_name not in _MOTION_TRACKING_ACTIONS:
                return

            # Identify a hero root to follow. Prefer armatures since
            # character procedural animation keyframes the armature root.
            heroes = _framing_collect_hero_meshes()
            if not heroes:
                return
            hero_roots: list = []
            seen: set = set()
            for obj in heroes:
                root = obj
                while root.parent is not None:
                    root = root.parent
                if root.name in seen:
                    continue
                seen.add(root.name)
                hero_roots.append(root)
            # Prefer armature roots if present.
            armatures = [r for r in hero_roots if r.type == 'ARMATURE']
            tracked_root = armatures[0] if armatures else (hero_roots[0] if hero_roots else None)
            if tracked_root is None:
                return

            # Measure tracked root's Y travel across the shot by sampling
            # its location fcurve. If there's no translation, skip.
            start_y = tracked_root.location.y
            end_y = start_y
            ad = getattr(tracked_root, "animation_data", None)
            if ad and ad.action:
                for fc in ad.action.fcurves:
                    if fc.data_path == "location" and fc.array_index == 1:
                        pts = fc.keyframe_points
                        if len(pts) >= 2:
                            start_y = pts[0].co[1]
                            end_y = pts[-1].co[1]
                            break

            travel_y = end_y - start_y
            if abs(travel_y) < 0.25:
                print(
                    f"[CAM_TRACK] action={action_name!r} but hero travel={travel_y:.2f}m "
                    f"— too small to track, skipping",
                    flush=True,
                )
                return

            frame_start = scene.frame_start
            frame_end = scene.frame_end
            if frame_end <= frame_start:
                return

            # Resolve the camera's current start-frame location (it may
            # already be keyframed by _framing_reposition_camera's orbit).
            # Add a Y-offset over time so the camera keeps pace with the hero.
            try:
                if cam.animation_data is None:
                    cam.animation_data_create()
            except Exception:
                pass

            # Evaluate existing location fcurves at frame_start / frame_end
            # so we layer on top of the orbit rather than overwriting it.
            def _eval_cam_loc(at_frame: int):
                try:
                    scene.frame_set(at_frame)
                    return (cam.location.x, cam.location.y, cam.location.z)
                except Exception:
                    return (cam.location.x, cam.location.y, cam.location.z)

            start_loc = _eval_cam_loc(frame_start)
            end_loc = _eval_cam_loc(frame_end)
            # Shift the end-frame camera Y by the hero's travel so the
            # horizontal distance to the hero stays constant.
            shifted_end = (end_loc[0], end_loc[1] + travel_y, end_loc[2])

            try:
                scene.frame_set(frame_start)
                cam.location = start_loc
                cam.keyframe_insert(data_path="location", frame=frame_start)
                scene.frame_set(frame_end)
                cam.location = shifted_end
                cam.keyframe_insert(data_path="location", frame=frame_end)
                scene.frame_set(frame_start)
            except Exception as e:
                print(f"[CAM_TRACK] keyframe follow failed: {e}", flush=True)
                return

            # Make the follow motion linear so it matches the hero's
            # constant-velocity glide instead of easing in and out.
            try:
                act = cam.animation_data.action
                if act:
                    for fc in act.fcurves:
                        if fc.data_path == "location" and fc.array_index == 1:
                            for kp in fc.keyframe_points:
                                kp.interpolation = 'LINEAR'
            except Exception:
                pass

            # Add a TRACK_TO constraint aimed at the hero so the camera
            # rotates naturally as the hero moves. Strip old TRACK_TOs
            # first so we don't stack them.
            try:
                for con in list(cam.constraints):
                    if con.type == 'TRACK_TO':
                        cam.constraints.remove(con)
                track = cam.constraints.new('TRACK_TO')
                track.target = tracked_root
                track.track_axis = 'TRACK_NEGATIVE_Z'
                track.up_axis = 'UP_Y'
            except Exception as e:
                print(f"[CAM_TRACK] track-to constraint failed: {e}", flush=True)

            print(
                f"[CAM_TRACK] tracking hero={tracked_root.name!r} "
                f"action={action_name!r} travel_y={travel_y:.2f}m",
                flush=True,
            )
        except Exception as e:
            print(f"[CAM_TRACK] crashed (non-fatal): {e}", flush=True)

    _camera_motion_tracking()

    # ══════════════════════════════════════════════════════════════════════
    # FINAL BRIGHTNESS GUARANTEE — no render ships as a black frame.
    # This is the LAST lighting-related step before the empty-scene guard.
    # After tod_force, lighting_force, night_ambience and booster+rim have
    # all run, we take one more pass: count total light energy, count
    # lights. If the scene is still under-lit (sum < 50W and no sun OR
    # zero lights), install an emergency SUN. If it's dim-but-not-zero,
    # multiplicatively boost up to 5x. Also clamps world background to
    # ≥ 1.0 if it's below 0.5 so ambient sky never vanishes.
    #
    # Conservative — tuned so it's effectively a no-op on normal scenes
    # and only kicks in when something upstream went catastrophically
    # wrong (template crashed before adding lights, HDRI was rejected
    # and procedural fallback failed, etc.).
    # ══════════════════════════════════════════════════════════════════════
    def _ensure_visible_lighting():
        try:
            total_energy = 0.0
            light_count = 0
            has_sun = False
            for obj in bpy.data.objects:
                if obj.type != 'LIGHT':
                    continue
                light_count += 1
                try:
                    total_energy += float(getattr(obj.data, 'energy', 0.0))
                except Exception:
                    pass
                if getattr(obj.data, 'type', '') == 'SUN':
                    has_sun = True
            print(
                f"[LIGHT_GUARANTEE] lights={light_count} total_energy={total_energy:.0f} "
                f"has_sun={has_sun}",
                flush=True,
            )

            # Catastrophic: zero lights or trivially dim. Install emergency sun.
            if light_count == 0 or total_energy < 50.0:
                print("[LIGHT_GUARANTEE] scene critically dark — installing emergency SUN", flush=True)
                try:
                    bpy.ops.object.light_add(type='SUN', location=(5.0, -5.0, 10.0))
                    sun = bpy.context.active_object
                    sun.name = "EMERGENCY_SUN"
                    sun.data.energy = 3.0
                    try:
                        sun.data.color = (1.0, 0.95, 0.9)
                    except Exception:
                        pass
                    # 3/4 angle so shadows read.
                    sun.rotation_euler = (0.8, 0.2, 0.5)
                except Exception as se:
                    print(f"[LIGHT_GUARANTEE] emergency sun failed: {se}", flush=True)
            # Mild dim: multiply all lights up, capped so we don't blow out a
            # careful template setup.
            elif total_energy < 100.0 and light_count > 0:
                boost = min(200.0 / max(total_energy, 1.0), 5.0)
                for obj in bpy.data.objects:
                    if obj.type == 'LIGHT':
                        try:
                            obj.data.energy *= boost
                        except Exception:
                            pass
                print(f"[LIGHT_GUARANTEE] boosted all lights by {boost:.2f}x", flush=True)

            # World background floor — if tod_force's cap set it below 0.5,
            # pull it back up so ambient sky paints the environment.
            try:
                world = bpy.context.scene.world
                if world and world.use_nodes and world.node_tree:
                    for node in world.node_tree.nodes:
                        if node.type == 'BACKGROUND':
                            try:
                                s = node.inputs['Strength']
                                if float(s.default_value) < 0.5:
                                    s.default_value = 1.0
                                    print("[LIGHT_GUARANTEE] world bg strength raised to 1.0", flush=True)
                            except Exception:
                                pass
            except Exception as we:
                print(f"[LIGHT_GUARANTEE] world strength check failed: {we}", flush=True)
        except Exception as e:
            print(f"[LIGHT_GUARANTEE] guarantee crashed (non-fatal): {e}", flush=True)

    _ensure_visible_lighting()

    # ══════════════════════════════════════════════════════════════════════
    # EMPTY-SCENE GUARD — total asset failure recovery.
    # If the hero couldn't be resolved, couldn't be fetched, couldn't be
    # imported, AND no complex environment came in, the render would be
    # a sky + ground plane with nothing in it. Detect that condition and
    # drop in a branded placeholder cube with the subject name extruded
    # as 3D text. Better UX than shipping an empty frame.
    # ══════════════════════════════════════════════════════════════════════
    def _scene_is_effectively_empty() -> bool:
        """
        A scene counts as "empty" from the HERO perspective if there is
        no mesh that could plausibly read as the subject. An imported
        stadium / restaurant / city block provides lots of meshes but
        ZERO hero — we still need to install a stand-in in that case.

        Rules (more lenient than before):
        - Any mesh already tagged ``hero_proc_*`` or ``placeholder_*`` counts
          as a hero → NOT empty.
        - Manifest has ``hero_asset_path`` pointing to a real file → NOT empty.
        - Otherwise we walk meshes, EXCLUDE environment/env/ground/sky/etc.,
          AND EXCLUDE meshes with ``environment_`` prefix (the complex env
          importer tags every imported env object that way). If nothing
          remains, we're empty.
        """
        # Shortcut A: hero already produced by us (earlier empty-guard call).
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            lname = obj.name.lower()
            if lname.startswith("hero_proc_") or lname.startswith("placeholder_"):
                print("[EMPTY_GUARD] hero stand-in already present", flush=True)
                return False

        # Shortcut B: manifest says a hero asset was successfully imported.
        hp = manifest.get("hero_asset_path")
        if hp and Path(str(hp)).exists():
            # Also require at least one non-env mesh to exist (sanity check).
            for obj in bpy.data.objects:
                if obj.type != 'MESH':
                    continue
                ln = obj.name.lower()
                if ln.startswith("environment_") or ln.startswith("hero_proc_"):
                    continue
                if any(t in ln for t in (
                    "ground", "plane", "floor", "world_", "atmosphere", "sky",
                    "backdrop", "road", "street", "sweep", "cove",
                    "contactshadow", "nuclear_",
                )):
                    continue
                # Found a plausible hero mesh.
                return False

        env_terms = (
            "ground", "plane", "floor", "world_", "atmosphere", "sky",
            "environment", "backdrop", "road", "street", "sweep", "cove",
            "contactshadow", "nuclear_",
        )
        nonenv_meshes = 0
        nonenv_polys = 0
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            n = obj.name.lower()
            if any(t in n for t in env_terms):
                continue
            if n.startswith("environment_"):
                continue
            nonenv_meshes += 1
            try:
                nonenv_polys += len(obj.data.polygons)
            except Exception:
                pass
        print(
            f"[EMPTY_GUARD] non-env/non-hero meshes={nonenv_meshes} polys={nonenv_polys}",
            flush=True,
        )
        # Fewer than 2 meshes OR very low poly count = effectively empty.
        # (Tightened from "< 4 meshes AND < 100 polys" — we were missing
        # cases where a single low-poly prop remained but wasn't the hero.)
        return nonenv_meshes < 2 or nonenv_polys < 80

    def _install_branded_placeholder():
        """
        Drop a procedural stand-in so the frame is never void.

        Attempts a stylized primitive character first (procedural_characters
        library), falls back to a branded pedestal+text cube if the primitive
        builder fails for any reason.
        """
        try:
            # Pick a subject name to display.
            subj = (
                (manifest.get("scene_recipe") or {}).get("summary", {}).get("subject")
                or (manifest.get("_scene_plan") or {}).get("focal_subject")
                or manifest.get("topic")
                or "Fantasy Studio"
            )
            subj = str(subj).strip()[:80] or "Fantasy Studio"

            # Try procedural character first — MUCH better than a cube.
            try:
                from app.scene.procedural_characters import (
                    build_procedural_hero,
                    boost_materials_for_low_light,
                )
                # Anchor around where the hero SHOULD have been (frame center).
                objs = build_procedural_hero(bpy, subj, center=(0.0, 0.0, 0.0))
                if objs:
                    print(
                        f"[EMPTY_GUARD] procedural hero installed for subject={subj!r} "
                        f"({len(objs)} objects)",
                        flush=True,
                    )
                    # At night / dusk, primitive characters disappear into a
                    # dim environment because Principled BSDF reflections
                    # need real HDRI bounce. Add subtle self-illumination
                    # so the hero actually reads.
                    try:
                        tod_now = str(
                            manifest.get("_scene_plan", {}).get("time_of_day") or ""
                        ).lower()
                    except Exception:
                        tod_now = ""
                    if tod_now in ("night", "dusk"):
                        try:
                            n = boost_materials_for_low_light(objs, intensity=0.28)
                            print(
                                f"[EMPTY_GUARD] boosted {n} materials for low-light tod={tod_now}",
                                flush=True,
                            )
                        except Exception as be:
                            print(f"[EMPTY_GUARD] low-light boost failed: {be}", flush=True)
                    try:
                        _framing_force()
                    except Exception:
                        pass
                    return
            except Exception as pe:
                print(f"[EMPTY_GUARD] procedural hero failed ({pe}) — using pedestal fallback", flush=True)

            # Fallback: branded pedestal cube with 3D text label.
            bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1.0))
            pedestal = bpy.context.object
            pedestal.name = "placeholder_pedestal"
            mat = bpy.data.materials.new("PlaceholderMat")
            mat.use_nodes = True
            try:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs["Base Color"].default_value = (0.07, 0.45, 0.95, 1.0)
                    bsdf.inputs["Metallic"].default_value = 0.2
                    bsdf.inputs["Roughness"].default_value = 0.35
            except Exception:
                pass
            if pedestal.data.materials:
                pedestal.data.materials[0] = mat
            else:
                pedestal.data.materials.append(mat)

            # 3D label above the pedestal.
            try:
                bpy.ops.object.text_add(location=(0, 0, 2.6))
                text = bpy.context.object
                text.name = "placeholder_label"
                text.data.body = subj
                text.data.align_x = 'CENTER'
                text.data.align_y = 'CENTER'
                text.data.extrude = 0.04
                text.rotation_euler = (1.5708, 0, 0)  # face camera on Y-axis
                # Match material.
                text_mat = bpy.data.materials.new("PlaceholderLabelMat")
                text_mat.use_nodes = True
                try:
                    bsdf = text_mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
                        bsdf.inputs["Roughness"].default_value = 0.25
                except Exception:
                    pass
                if text.data.materials:
                    text.data.materials[0] = text_mat
                else:
                    text.data.materials.append(text_mat)
            except Exception as te:
                print(f"[EMPTY_GUARD] text label failed: {te}", flush=True)

            print(
                f"[EMPTY_GUARD] installed branded placeholder for subject={subj!r}",
                flush=True,
            )
            # Re-run framing so the camera actually sees the placeholder.
            try:
                _framing_force()
            except Exception:
                pass
        except Exception as e:
            print(f"[EMPTY_GUARD] placeholder install failed: {e}", flush=True)

    if _scene_is_effectively_empty():
        print("[EMPTY_GUARD] scene is effectively empty — installing placeholder", flush=True)
        _install_branded_placeholder()

    # 3. Final safety check: verify scene is renderable
    mesh_count = sum(1 for obj in bpy.data.objects if obj.type == "MESH")
    light_count = sum(1 for obj in bpy.data.objects if obj.type == "LIGHT")
    has_camera = scene.camera is not None
    print(
        f"DEBUG pre-render check: camera={'YES' if has_camera else 'MISSING'} "
        f"meshes={mesh_count} lights={light_count}",
        flush=True,
    )
    if not has_camera:
        print("DEBUG CRITICAL: no camera -- building emergency fallback", flush=True)
        build_fallback_scene(bpy, scene)
    elif light_count == 0:
        print("DEBUG CRITICAL: no lights -- adding emergency light", flush=True)
        bpy.ops.object.light_add(type='AREA', location=(0, -6, 5))
        emergency_light = bpy.context.object
        emergency_light.data.energy = 5000

    # ══════════════════════════════════════════════════════════════════
    # BRUTE-FORCE PRE-RENDER GUARANTEES
    # ------------------------------------------------------------------
    # Everything above this point — templates, safety nets, world
    # builder, empty-scene guard — is allowed to be wrong. These final
    # three blocks are the last line of defence: they find whatever
    # hero meshes exist, rescale them to a visible size, ground them,
    # and point the camera at them. Each block is wrapped in try/except
    # so a failure here NEVER breaks a render — we'd rather ship a
    # slightly wonky frame than crash out.
    # ══════════════════════════════════════════════════════════════════

    # ── shared hero-mesh discovery (used by force-scale + force-camera)
    #
    # Primary signal: ``obj["is_hero"] == True`` — set by the GLB /
    # fallback importers. When present, we trust it unconditionally; this
    # prevents FORCE_FIX from lumping mountain terrain (245m) in with a
    # pelican (1.5m) and scaling the combined "hero" bbox down to 0.04m.
    #
    # Fallback signal: name-based heuristic. Needed for primitive
    # stand-ins that templates create when a real import fails — those
    # aren't tagged but should still be sized/centred/framed.
    hero_meshes: list = []
    try:
        from mathutils import Vector

        _ENVIRONMENT_NAMES = {
            'ground', 'plane', 'floor', 'world_', 'atmosphere', 'volume',
            'fog', 'building', 'backdrop', 'hill', 'distant',
            'road_marking', 'road', 'contact_shadow', 'pedestal',
            'mountain', 'terrain', 'water', 'stage', 'studio',
            'environment', 'background_building', 'sky', 'sun',
            'cyc', 'sweep', 'cove',
        }

        def _is_environment_object(name: str) -> bool:
            n = (name or "").lower()
            return any(env in n for env in _ENVIRONMENT_NAMES)

        # Primary: is_hero tag, size-filtered.
        # Uses the same helper as FRAME_FIX/HERO_SCALE/VERIFY so that an
        # 80m mountain that was tagged is_hero (scenic_landscape imports
        # environments via import_hero_asset_group) doesn't dominate the
        # hero bbox and scale the real hero to invisibility.
        _tagged_heroes = [
            o for o in _collect_tagged_hero_meshes_filtered()
            if o.data and len(o.data.vertices) >= 10
        ]

        if _tagged_heroes:
            hero_meshes = _tagged_heroes
            print(
                f"[FORCE_FIX] discovered {len(hero_meshes)} is_hero-tagged "
                f"mesh(es) after size filter; ignoring untagged env geometry",
                flush=True,
            )
        else:
            # Fallback: name-based heuristic for primitive stand-ins.
            # V1.3 batch-2 fix: when a hero import fails (e.g. zero-byte
            # .blend file was picked from the library), the previous
            # substring filter still let large env meshes through
            # (Hillock_, Plane_Material_, Sketchfab_model, WD_*) and
            # FORCE_FIX would then scale 288m terrain down to 1.8m,
            # producing tiny dark specks instead of a missing-hero
            # graceful degradation.  This filter uses exact prefix
            # matches + a 10m individual-dimension ceiling so only
            # plausibly hero-sized primitives qualify as fallbacks.
            _ENV_NAME_PREFIXES = (
                "Hillock_", "Ridge_", "environment_", "Sketchfab_model",
                "DistantHills_", "ScenicGround", "ScenicForegroundBlend",
                "Atmosphere_", "Atmo_", "WD_", "CarHeroGround",
                "CarHeroContactShadow", "ContactShadow", "CharContactShadow",
                "StreetGround", "GroundPlane", "Plane_Material",
                "Background_Building", "Curb_L", "Curb_R", "Road_Marking",
                "CarHeroRoad", "CarHeroTerrain", "Treeline_", "LaneStripe",
                "Distant_Hill", "Forest_Tree", "Tower", "Building_",
            )
            for _obj in bpy.data.objects:
                if _obj.type != 'MESH':
                    continue
                # Exact prefix match (stricter than the substring check)
                if any(_obj.name.startswith(p) for p in _ENV_NAME_PREFIXES):
                    continue
                # Legacy substring filter as belt-and-braces
                if _is_environment_object(_obj.name):
                    continue
                if not _obj.data or len(_obj.data.vertices) < 10:
                    continue
                # Size ceiling: no hero should be > 10m in any single
                # dimension. Caps out the "288m hillock scaled to 1.8m"
                # failure mode the spec calls out.
                try:
                    if max(_obj.dimensions) >= 10.0:
                        continue
                except Exception:
                    continue
                hero_meshes.append(_obj)
            if hero_meshes:
                print(
                    f"[FORCE_FIX] no is_hero-tagged meshes; name-heuristic "
                    f"with env-prefix + 10m ceiling filter found "
                    f"{len(hero_meshes)} candidate(s)",
                    flush=True,
                )
            else:
                print(
                    "[FORCE_FIX] no is_hero-tagged meshes found and no "
                    "plausible fallback (all candidates were env-prefixed "
                    "or >= 10m); skipping scale — render will show whatever "
                    "the scene has, not synthetic shrunk terrain",
                    flush=True,
                )
    except Exception as e:
        print(f"[FORCE_FIX] hero-discovery error (non-fatal): {e}", flush=True)
        hero_meshes = []

    # ── FORCE-SCALE FIX — make tiny / huge heroes visible ─────────────
    try:
        if hero_meshes:
            all_coords = []
            for _obj in hero_meshes:
                for _corner in _obj.bound_box:
                    try:
                        all_coords.append(_obj.matrix_world @ Vector(_corner))
                    except Exception:
                        pass

            if all_coords:
                _min_x = min(c.x for c in all_coords)
                _max_x = max(c.x for c in all_coords)
                _min_y = min(c.y for c in all_coords)
                _max_y = max(c.y for c in all_coords)
                _min_z = min(c.z for c in all_coords)
                _max_z = max(c.z for c in all_coords)

                _w = _max_x - _min_x
                _d = _max_y - _min_y
                _h = _max_z - _min_z
                _combined_max = max(_w, _d, _h, 0.001)

                _hero_type = str(manifest.get("hero_asset_type") or "character").lower()
                if _hero_type == "vehicle":
                    _target_size = 4.0
                elif _hero_type == "animal":
                    _target_size = 1.2
                elif _hero_type in ("character", "humanoid"):
                    _target_size = 1.8
                else:
                    _target_size = 1.5

                # ── Guard: trust the template if any INDIVIDUAL mesh is
                # already a reasonable size. Multi-part vehicles (the
                # Ferrari has 171 leaf meshes) have a combined world-space
                # bbox that can span hundreds of metres because the leaf
                # meshes are positioned relative to a parent that was
                # scaled separately — rescaling that combined bbox down
                # to target_size shrinks every part to ~2 cm, which is
                # why the Ferrari rendered as invisible confetti.
                # If the LARGEST INDIVIDUAL mesh dimension is already in
                # the plausible hero range, the template got it right
                # and we must not touch it.
                try:
                    _largest_individual = max(
                        (max(_o.dimensions) for _o in hero_meshes if _o.dimensions),
                        default=0.0,
                    )
                except Exception:
                    _largest_individual = 0.0

                print(
                    f"[FORCE_FIX] hero_meshes={len(hero_meshes)} "
                    f"combined={_combined_max:.3f}m "
                    f"largest_individual={_largest_individual:.3f}m "
                    f"type={_hero_type!r} target={_target_size}m",
                    flush=True,
                )

                _needs_scale = False
                # V1.4.1 floor decision: trust band lower bound 0.1m → 0.02m
                # and TINY trigger 0.1m → 0.02m, mirroring the broader
                # 20% floor. HERO_VERIFY now accepts heroes ≥ 0.2m, so
                # FORCE_FIX shouldn't second-guess between 0.05m and
                # 0.2m. Upper bound (50m) unchanged.
                # Only intervene when the hero is genuinely broken.
                # Thresholds: <0.02m is invisible; >50m is a scene-breaking
                # giant. Anything in between was sized by the template or
                # import pipeline and should be trusted.
                if 0.02 < _largest_individual < 50.0:
                    print(
                        f"[FORCE_FIX] Largest individual mesh is "
                        f"{_largest_individual:.2f}m -- within [0.02, 50]m, "
                        f"skipping scale (template handled it)",
                        flush=True,
                    )
                elif _combined_max < 0.02:
                    _needs_scale = True
                    print(
                        f"[FORCE_FIX] TINY hero ({_combined_max:.4f}m) "
                        f"-- forcing scale to {_target_size}m",
                        flush=True,
                    )
                elif _combined_max > 50.0:
                    _needs_scale = True
                    print(
                        f"[FORCE_FIX] HUGE hero ({_combined_max:.1f}m) "
                        f"-- scaling to {_target_size}m",
                        flush=True,
                    )

                if _needs_scale:
                    _scale_factor = _target_size / _combined_max
                    for _obj in hero_meshes:
                        _obj.scale *= _scale_factor
                    bpy.context.view_layer.update()
                    print(f"[FORCE_FIX] Applied scale factor: {_scale_factor:.4f}", flush=True)

                # GROUND + CENTER
                bpy.context.view_layer.update()
                _coords2 = []
                for _obj in hero_meshes:
                    for _corner in _obj.bound_box:
                        try:
                            _coords2.append(_obj.matrix_world @ Vector(_corner))
                        except Exception:
                            pass

                if _coords2:
                    _new_min_z = min(c.z for c in _coords2)
                    _new_cx = (min(c.x for c in _coords2) + max(c.x for c in _coords2)) / 2
                    _new_cy = (min(c.y for c in _coords2) + max(c.y for c in _coords2)) / 2

                    _ff_template = str(manifest.get("template_name") or "").lower()
                    if manifest.get("_env_placement_final"):
                        print(
                            f"[FORCE_FIX] grounding SKIPPED — forced env "
                            f"placement is authoritative "
                            f"(hero bottom z={_new_min_z:.3f} intentional)",
                            flush=True,
                        )
                    elif _ff_template == "ocean_scene":
                        print(
                            f"[FORCE_FIX] grounding SKIPPED for ocean_scene "
                            f"(VERIFY OCEAN_LIFT already positioned hero "
                            f"above water; min_z={_new_min_z:.2f})",
                            flush=True,
                        )
                    elif abs(_new_min_z) > 0.02:
                        _dz = -_new_min_z
                        for _obj in hero_meshes:
                            _obj.location.z += _dz
                        print(f"[FORCE_FIX] Grounded: moved z by {_dz:.3f}m", flush=True)

                    # DISABLED: Do not re-center the hero. The template
                    # placed it at a designed position relative to
                    # environment elements (road, lights, contact shadow,
                    # lane stripes). Moving only the hero meshes breaks
                    # the spatial relationship — e.g. the Ferrari ends up
                    # 27m from its own road while the camera chases it
                    # into empty space.
                    if abs(_new_cx) > 20 or abs(_new_cy) > 20:
                        print(
                            f"[FORCE_FIX] centering SKIPPED — template "
                            f"placement preserved (hero center at "
                            f"{_new_cx:.1f}, {_new_cy:.1f})",
                            flush=True,
                        )

                for _obj in hero_meshes:
                    _obj.hide_viewport = False
                    _obj.hide_render = False

                print(
                    f"[FORCE_FIX] complete. {len(hero_meshes)} meshes processed.",
                    flush=True,
                )
        else:
            print("[FORCE_FIX] WARNING: no hero mesh objects found in scene", flush=True)
    except Exception as e:
        print(f"[FORCE_FIX] Error (non-fatal): {e}", flush=True)
    log_stage("FORCE_FIX", f"hero_meshes={len(hero_meshes) if hero_meshes else 0}")

    # ── CONTACT SHADOW CATCHER ────────────────────────────────────────
    # Universal shadow catcher plane beneath the hero for grounding.
    # Added after FORCE_FIX so hero is at final scale and position.
    try:
        _has_contact = any(
            "contactshadow" in obj.name.lower() or "ContactShadow" in obj.name
            for obj in bpy.data.objects
        )
        if not _has_contact and hero_meshes:
            from mathutils import Vector as _CSVec
            _cs_coords = []
            for _obj in hero_meshes:
                if _obj.type != "MESH":
                    continue
                for _corner in _obj.bound_box:
                    try:
                        _cs_coords.append(_obj.matrix_world @ _CSVec(_corner))
                    except Exception:
                        continue
            if _cs_coords:
                _cs_xs = [c.x for c in _cs_coords]
                _cs_ys = [c.y for c in _cs_coords]
                _cs_zs = [c.z for c in _cs_coords]
                _cs_cx = (min(_cs_xs) + max(_cs_xs)) / 2
                _cs_cy = (min(_cs_ys) + max(_cs_ys)) / 2
                _cs_z = min(_cs_zs) + 0.005
                _cs_ext = max(max(_cs_xs) - min(_cs_xs), max(_cs_ys) - min(_cs_ys))
                _cs_radius = max(0.5, _cs_ext * 0.7)

                bpy.ops.mesh.primitive_circle_add(
                    vertices=48, radius=_cs_radius,
                    location=(_cs_cx, _cs_cy, _cs_z), fill_type="NGON",
                )
                _cs_disc = bpy.context.object
                _cs_disc.name = "ContactShadow_Universal"
                _cs_mat = bpy.data.materials.new("ContactShadowMat_Univ")
                _cs_mat.use_nodes = True
                _cs_bsdf = _cs_mat.node_tree.nodes.get("Principled BSDF")
                if _cs_bsdf:
                    _cs_bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                    try:
                        _cs_bsdf.inputs["Alpha"].default_value = 0.45
                    except KeyError:
                        pass
                    _cs_bsdf.inputs["Roughness"].default_value = 1.0
                try:
                    _cs_mat.blend_method = "BLEND"
                except Exception:
                    pass
                _cs_disc.data.materials.append(_cs_mat)
                print(
                    f"[CONTACT_SHADOW] universal shadow catcher at "
                    f"({_cs_cx:.2f}, {_cs_cy:.2f}, {_cs_z:.3f}) r={_cs_radius:.2f}",
                    flush=True,
                )
    except Exception as _cs_err:
        print(f"[CONTACT_SHADOW] failed (non-fatal): {_cs_err}", flush=True)
    log_stage("CONTACT_SHADOW")

    # ── FORCE CAMERA ON HERO ──────────────────────────────────────────
    # When env-aware camera adjust (Round 1 polish) already set distance
    # + lens for a forced environment, skip the solo-hero static pose.
    _skip_camera_fix = bool(manifest.get("_camera_env_adjusted"))
    if _skip_camera_fix:
        print(
            "[CAMERA_FIX] SKIPPED — environment-aware camera already applied",
            flush=True,
        )
    try:
        import math as _math
        from mathutils import Vector as _Vec

        _cam = bpy.context.scene.camera
        if (not _skip_camera_fix) and _cam and hero_meshes:
            # Evaluate hero bounds at frame 1 (start of animation).
            # directorial motions like character_walk keyframe the hero
            # 14 m along Y over the animation.  If we evaluate at the
            # current (possibly last) frame, the hero appears far from
            # its template-placed origin and the camera ends up inside
            # atmosphere volumes / behind environment geometry.
            _prev_frame = bpy.context.scene.frame_current
            bpy.context.scene.frame_set(bpy.context.scene.frame_start)
            bpy.context.view_layer.update()
            _coords3 = []
            for _obj in hero_meshes:
                if _obj.type != 'MESH':
                    continue
                for _corner in _obj.bound_box:
                    try:
                        _coords3.append(_obj.matrix_world @ _Vec(_corner))
                    except Exception:
                        pass

            if _coords3:
                # V1.3.2 — CAMERA_FIX math REPLACED by camera director.
                # The director is the single source of truth: hero bbox
                # + shot profile + aspect ratio → cam location + lens.
                # Directed-shot skip guards are preserved (directed shots
                # keep their choreographed animation).
                _fix_mn = (
                    min(c.x for c in _coords3),
                    min(c.y for c in _coords3),
                    min(c.z for c in _coords3),
                )
                _fix_mx = (
                    max(c.x for c in _coords3),
                    max(c.y for c in _coords3),
                    max(c.z for c in _coords3),
                )

                # ── GUARD: directed shots skip director placement ─────
                # directed behavior + any keyframes on hero or camera
                # means the shot is composed deliberately and must not
                # be recomposed here.
                _cam_keyframes = _count_keyframes(_cam)
                _hero_for_fix = None
                for _o2 in bpy.data.objects:
                    try:
                        if _o2.get("is_hero_root", False) or _o2.get("is_hero", False):
                            _hero_for_fix = _o2
                            break
                    except Exception:
                        pass
                _hero_fix_keyframes = _count_keyframes(_hero_for_fix) if _hero_for_fix else 0
                _directed_active_fix, _beh_fix = _directed_behavior_active()

                if _directed_active_fix and (_cam_keyframes > 0 or _hero_fix_keyframes > 0):
                    print(
                        f"[CAMERA_FIX] SKIPPED — directed shot active "
                        f"(behavior={_beh_fix!r}, hero_anim={_hero_fix_keyframes > 0}, "
                        f"camera_anim={_cam_keyframes > 0})",
                        flush=True,
                    )
                elif _cam_keyframes > 2:
                    # No directed behavior but camera has substantial
                    # keyframes — preserve them (legacy guard).
                    print(
                        f"[CAMERA_FIX] preserving camera animation "
                        f"({_cam_keyframes} keyframes — non-directed motion)",
                        flush=True,
                    )
                else:
                    # For small heroes, clear any template keyframes so
                    # they don't fight the director's placement.
                    _hero_max_dim = max(
                        _fix_mx[0] - _fix_mn[0],
                        _fix_mx[1] - _fix_mn[1],
                        _fix_mx[2] - _fix_mn[2],
                    )
                    if _hero_max_dim < 5.0:
                        try:
                            if _cam.animation_data:
                                _cam.animation_data_clear()
                            for _obj in bpy.data.objects:
                                if _obj.type == 'EMPTY' and 'target' in (_obj.name or '').lower():
                                    if _obj.animation_data:
                                        _obj.animation_data_clear()
                        except Exception as _anim_err:
                            print(
                                f"[CAMERA_FIX] animation clear failed "
                                f"(non-fatal): {_anim_err}",
                                flush=True,
                            )

                    # Defer to the director.
                    _apply_director_to_camera(
                        _cam,
                        (_fix_mn, _fix_mx),
                        _director_profile_for_manifest(manifest),
                        manifest,
                        "CAMERA_FIX",
                    )

            # Restore the scene frame so the render starts normally.
            bpy.context.scene.frame_set(_prev_frame)
    except Exception as e:
        print(f"[CAMERA_FIX] Error (non-fatal): {e}", flush=True)
    log_stage("CAMERA_FIX")

    # ══════════════════════════════════════════════════════════════════════
    # CAMERA_DIRECTOR_FINAL — V1.3.3 Fix A
    # ══════════════════════════════════════════════════════════════════════
    # Every earlier camera-touching stage is now ADVISORY.  This stage
    # is the authoritative final placement.  It samples the hero bbox
    # at frame_start (so camera matches what the render actually sees,
    # not where animations have moved the hero by frame_end), calls the
    # director, and applies the result.  If the bbox at frame_start
    # differs from any earlier-cached bbox the director was called with,
    # both bboxes are logged so we can spot animation-vs-static drift.
    try:
        _df_cam = bpy.context.scene.camera
        _df_hero_meshes = []
        for _o in bpy.data.objects:
            try:
                if _o.type == "MESH" and (
                    _o.get("is_hero", False) or _o.get("is_forced_hero", False)
                ):
                    _df_hero_meshes.append(_o)
            except Exception:
                pass

        if _df_cam is None or not _df_hero_meshes:
            print(
                f"[CAMERA_DIRECTOR_FINAL] SKIPPED — "
                f"cam={_df_cam is not None} hero_meshes={len(_df_hero_meshes)}",
                flush=True,
            )
        else:
            from mathutils import Vector as _DFVec
            # Sample bbox at frame_start (per V1.3.3 spec).
            _df_prev_frame = bpy.context.scene.frame_current
            _df_start = bpy.context.scene.frame_start
            try:
                bpy.context.scene.frame_set(_df_start)
                bpy.context.view_layer.update()
            except Exception:
                pass

            _df_coords = []
            for _hm in _df_hero_meshes:
                try:
                    mw = _hm.matrix_world
                    for _c in _hm.bound_box:
                        _df_coords.append(mw @ _DFVec(_c))
                except Exception:
                    pass
            if _df_coords:
                _df_mn = (
                    min(c.x for c in _df_coords),
                    min(c.y for c in _df_coords),
                    min(c.z for c in _df_coords),
                )
                _df_mx = (
                    max(c.x for c in _df_coords),
                    max(c.y for c in _df_coords),
                    max(c.z for c in _df_coords),
                )
                # If an earlier director call cached its bbox, compare.
                _earlier_bbox = manifest.get("_camera_director_bbox_at_call")
                if _earlier_bbox is not None:
                    try:
                        _e_mn, _e_mx = _earlier_bbox
                        # Difference threshold: 0.5m across any corner
                        _df_diff = max(
                            abs(_df_mn[i] - _e_mn[i]) for i in range(3)
                        ) + max(
                            abs(_df_mx[i] - _e_mx[i]) for i in range(3)
                        )
                        if _df_diff > 0.5:
                            print(
                                f"[CAMERA_DIRECTOR_FINAL] hero bbox drifted "
                                f"between earlier director call and frame_start: "
                                f"earlier=({_e_mn},{_e_mx}) "
                                f"frame_start=({_df_mn},{_df_mx}) "
                                f"max_corner_delta={_df_diff:.2f}m",
                                flush=True,
                            )
                    except Exception:
                        pass

                # Stash for any later inspection
                manifest["_camera_director_bbox_at_call"] = (_df_mn, _df_mx)

                # ── V1.3.4 Bug 2 — clear existing camera animation BEFORE
                # the director writes its static placement.  Without this,
                # earlier-stage tracking/orbit keyframes (set by
                # _tracking_camera, CAM_TRACK, FRAME_FIX orbit, AERIAL_GUARD)
                # win at render time because Blender evaluates fcurves
                # AFTER static .location assignments.  The director's
                # static pose then becomes invisible.
                _cleared_kf = 0
                try:
                    if _df_cam.animation_data and _df_cam.animation_data.action:
                        try:
                            for _fc in _df_cam.animation_data.action.fcurves:
                                _cleared_kf += len(_fc.keyframe_points)
                        except Exception:
                            pass
                        _df_cam.animation_data_clear()
                        print(
                            f"[CAMERA_DIRECTOR_FINAL] cleared {_cleared_kf} "
                            f"existing camera keyframes (animated tracking shot "
                            f"replaced with static director placement)",
                            flush=True,
                        )
                    # Also strip any tracking constraints that would fight
                    # the director's aim.
                    for _con in list(_df_cam.constraints):
                        try:
                            _df_cam.constraints.remove(_con)
                        except Exception:
                            pass
                except Exception as _clear_err:
                    print(
                        f"[CAMERA_DIRECTOR_FINAL] keyframe clear failed "
                        f"(non-fatal): {_clear_err}",
                        flush=True,
                    )

                _df_profile = _director_profile_for_manifest(manifest)
                _df_placement = _apply_director_to_camera(
                    _df_cam,
                    (_df_mn, _df_mx),
                    _df_profile,
                    manifest,
                    "CAMERA_DIRECTOR_FINAL",
                )

                # Stamp manifest with the authoritative location.  Used by
                # the writer guard below CAMERA_SAFETY to detect any
                # subsequent stage moving the camera unexpectedly.
                if _df_placement is not None:
                    manifest["_camera_director_final"] = True
                    manifest["_camera_director_final_location"] = tuple(
                        _df_placement.location
                    )
                    manifest["_camera_director_final_lens"] = float(
                        _df_placement.lens_mm
                    )

                    # ── V1.3.4 Bug 2 — re-bake tracking/orbit anchored
                    # to the director's static origin.  If the user asked
                    # for a tracking or orbiting shot via directorial_controls,
                    # we don't want to lose motion entirely — we want
                    # motion that respects the director's framing.
                    try:
                        _dc = manifest.get("directorial_controls") or {}
                        _cam_style = str(_dc.get("camera_style") or "").lower().strip()
                        _do_anim = _cam_style in ("tracking", "orbit")
                        if _do_anim:
                            import math as _df_math
                            from mathutils import Vector as _BakeVec
                            _origin = _BakeVec(_df_placement.location)
                            _scene = bpy.context.scene
                            _f_start = _scene.frame_start
                            _f_end   = _scene.frame_end
                            _hero_center = _BakeVec((
                                (_df_mn[0] + _df_mx[0]) * 0.5,
                                (_df_mn[1] + _df_mx[1]) * 0.5,
                                (_df_mn[2] + _df_mx[2]) * 0.5,
                            ))

                            # Frame_start: park at director's chosen pose.
                            _scene.frame_set(_f_start)
                            _df_cam.location = _origin
                            _df_cam.keyframe_insert(data_path="location", frame=_f_start)
                            _df_cam.keyframe_insert(data_path="rotation_euler", frame=_f_start)

                            if _cam_style == "tracking":
                                # 1.5m dolly-in along (origin -> hero_center)
                                _to_hero = _hero_center - _origin
                                if _to_hero.length > 0.001:
                                    _step = _to_hero.normalized() * 1.5
                                else:
                                    _step = _BakeVec((0.0, 0.0, 0.0))
                                _end_loc = _origin + _step
                                _scene.frame_set(_f_end)
                                _df_cam.location = _end_loc
                                _aim = _hero_center - _df_cam.location
                                if _aim.length > 0.001:
                                    _df_cam.rotation_euler = _aim.to_track_quat("-Z", "Y").to_euler()
                                _df_cam.keyframe_insert(data_path="location", frame=_f_end)
                                _df_cam.keyframe_insert(data_path="rotation_euler", frame=_f_end)
                                print(
                                    f"[CAMERA_DIRECTOR_FINAL] re-applied tracking "
                                    f"animation: type=tracking baked from director "
                                    f"origin ({_origin.x:.2f},{_origin.y:.2f},"
                                    f"{_origin.z:.2f}), end ({_end_loc.x:.2f},"
                                    f"{_end_loc.y:.2f},{_end_loc.z:.2f})",
                                    flush=True,
                                )
                            elif _cam_style == "orbit":
                                # 30deg arc around hero_center, preserving
                                # height + radius from the director's pose.
                                _r_xy_vec = _origin - _hero_center
                                _r_xy = _df_math.sqrt(_r_xy_vec.x**2 + _r_xy_vec.y**2)
                                if _r_xy < 0.01:
                                    _r_xy = 5.0
                                _start_a = _df_math.atan2(_r_xy_vec.y, _r_xy_vec.x)
                                _arc = _df_math.radians(30.0)
                                _end_a = _start_a + _arc
                                _end_loc = _BakeVec((
                                    _hero_center.x + _r_xy * _df_math.cos(_end_a),
                                    _hero_center.y + _r_xy * _df_math.sin(_end_a),
                                    _origin.z,
                                ))
                                _scene.frame_set(_f_end)
                                _df_cam.location = _end_loc
                                _aim = _hero_center - _df_cam.location
                                if _aim.length > 0.001:
                                    _df_cam.rotation_euler = _aim.to_track_quat("-Z", "Y").to_euler()
                                _df_cam.keyframe_insert(data_path="location", frame=_f_end)
                                _df_cam.keyframe_insert(data_path="rotation_euler", frame=_f_end)
                                print(
                                    f"[CAMERA_DIRECTOR_FINAL] re-applied tracking "
                                    f"animation: type=orbit baked from director "
                                    f"origin ({_origin.x:.2f},{_origin.y:.2f},"
                                    f"{_origin.z:.2f}), end ({_end_loc.x:.2f},"
                                    f"{_end_loc.y:.2f},{_end_loc.z:.2f})",
                                    flush=True,
                                )
                            # Restore frame
                            _scene.frame_set(_df_prev_frame)
                    except Exception as _bake_err:
                        import traceback as _bake_tb
                        print(
                            f"[CAMERA_DIRECTOR_FINAL] re-bake animation failed "
                            f"(non-fatal): {_bake_err}",
                            flush=True,
                        )
                        print(_bake_tb.format_exc(), flush=True)
            else:
                print(
                    "[CAMERA_DIRECTOR_FINAL] SKIPPED — no hero bbox available",
                    flush=True,
                )

            # Restore frame
            try:
                bpy.context.scene.frame_set(_df_prev_frame)
            except Exception:
                pass
    except Exception as _df_err:
        import traceback as _df_tb
        print(f"[CAMERA_DIRECTOR_FINAL] failed (non-fatal): {_df_err}", flush=True)
        print(_df_tb.format_exc(), flush=True)
    log_stage("CAMERA_DIRECTOR_FINAL")

    # ══════════════════════════════════════════════════════════════════════
    # CAMERA_SAFETY — last-line-of-defense against camera clipping into hero
    # ══════════════════════════════════════════════════════════════════════
    # Scan every frame of the camera's keyframed path. If the camera's
    # world-space location ends up inside the hero's (expanded) bounding
    # box at any frame, push it outward along the camera->hero vector
    # until it's on the bbox surface + padding. Overwrite that frame's
    # location keyframe with the corrected position.
    try:
        from mathutils import Vector as _SafeVec
        _safe_cam = bpy.context.scene.camera
        _safe_hero = None
        for _o3 in bpy.data.objects:
            try:
                if _o3.get("is_hero_root", False):
                    _safe_hero = _o3
                    break
            except Exception:
                pass
        if _safe_hero is None:
            for _o3 in bpy.data.objects:
                try:
                    if _o3.get("is_hero", False) and _o3.type == "MESH":
                        _safe_hero = _o3
                        break
                except Exception:
                    pass

        _scan_count = 0
        _fix_count = 0
        if _safe_cam is not None and _safe_hero is not None:
            _safe_ad = getattr(_safe_cam, "animation_data", None)
            _has_keys = False
            if _safe_ad and _safe_ad.action:
                try:
                    _has_keys = len(_safe_ad.action.fcurves) > 0
                except AttributeError:
                    # Blender 4.4+ layered actions
                    if hasattr(_safe_ad.action, "layers") and _safe_ad.action.layers:
                        _lyr = _safe_ad.action.layers[0]
                        if hasattr(_lyr, "strips") and _lyr.strips:
                            _stp = _lyr.strips[0]
                            if hasattr(_stp, "channelbags") and _stp.channelbags:
                                _has_keys = len(_stp.channelbags[0].fcurves) > 0

            if _has_keys:
                _padding = 0.5
                _fs = bpy.context.scene.frame_start
                _fe = bpy.context.scene.frame_end
                _prev = bpy.context.scene.frame_current

                for _fr in range(_fs, _fe + 1):
                    _scan_count += 1
                    try:
                        bpy.context.scene.frame_set(_fr)
                        bpy.context.view_layer.update()
                    except Exception:
                        continue

                    # Compute expanded hero bbox in world space
                    _corners = []
                    try:
                        for _c in _safe_hero.bound_box:
                            _corners.append(
                                _safe_hero.matrix_world @ _SafeVec(_c)
                            )
                    except Exception:
                        continue
                    if not _corners:
                        continue
                    _mn = _SafeVec((
                        min(c.x for c in _corners) - _padding,
                        min(c.y for c in _corners) - _padding,
                        min(c.z for c in _corners) - _padding,
                    ))
                    _mx = _SafeVec((
                        max(c.x for c in _corners) + _padding,
                        max(c.y for c in _corners) + _padding,
                        max(c.z for c in _corners) + _padding,
                    ))
                    _hc = (_mn + _mx) * 0.5

                    _cp = _safe_cam.matrix_world.translation
                    _inside = (
                        _mn.x <= _cp.x <= _mx.x
                        and _mn.y <= _cp.y <= _mx.y
                        and _mn.z <= _cp.z <= _mx.z
                    )
                    if not _inside:
                        continue

                    # Push camera out along (camera - hero_center) vector
                    _dir = _cp - _hc
                    if _dir.length < 0.001:
                        _dir = _SafeVec((0.0, -1.0, 0.0))
                    _dir.normalize()
                    # Project: find the bbox surface along this ray from hero_center.
                    # Use the largest axis extent as a safe push distance.
                    _ext = max(_mx.x - _mn.x, _mx.y - _mn.y, _mx.z - _mn.z) * 0.5 + _padding
                    _new_loc = _hc + _dir * _ext
                    _safe_cam.location = _new_loc
                    _safe_cam.keyframe_insert(data_path="location", frame=_fr)
                    _fix_count += 1

                try:
                    bpy.context.scene.frame_set(_prev)
                except Exception:
                    pass

        print(
            f"[CAMERA_SAFETY] scanned_frames={_scan_count} "
            f"corrected_frames={_fix_count} (padding=0.5)",
            flush=True,
        )
    except Exception as _cs_err:
        print(f"[CAMERA_SAFETY] error (non-fatal): {_cs_err}", flush=True)
    log_stage("CAMERA_SAFETY")

    # ══════════════════════════════════════════════════════════════════════
    # V1.3.3 Fix A — camera writer-attempt guard
    # ══════════════════════════════════════════════════════════════════════
    # CAMERA_SAFETY may legitimately re-keyframe the camera position
    # when it detected clipping into the hero bbox.  Anything else that
    # moves the camera between CAMERA_DIRECTOR_FINAL and RENDER_START is
    # a regression — log it loudly so it's caught in test runs.
    try:
        if manifest.get("_camera_director_final"):
            _cam_now = bpy.context.scene.camera
            _planned = manifest.get("_camera_director_final_location")
            if _cam_now is not None and _planned is not None:
                _delta = (
                    (_cam_now.location.x - _planned[0]) ** 2
                    + (_cam_now.location.y - _planned[1]) ** 2
                    + (_cam_now.location.z - _planned[2]) ** 2
                ) ** 0.5
                if _delta > 0.10:
                    # Most likely cause: CAMERA_SAFETY corrected a clip.
                    # Log it but DON'T treat it as an error — the safety
                    # adjustment is permitted.
                    print(
                        f"[CAMERA_WRITE_BLOCKED] post-director delta="
                        f"{_delta:.3f}m: planned={_planned} "
                        f"actual=({_cam_now.location.x:.2f},"
                        f"{_cam_now.location.y:.2f},"
                        f"{_cam_now.location.z:.2f}). "
                        f"Likely CAMERA_SAFETY clip-correction; permitted.",
                        flush=True,
                    )
                else:
                    print(
                        f"[CAMERA_WRITE_BLOCKED] no post-director writes "
                        f"detected (delta={_delta:.3f}m within 0.10m tolerance)",
                        flush=True,
                    )
    except Exception as _cwg_err:
        print(f"[CAMERA_WRITE_BLOCKED] guard error (non-fatal): {_cwg_err}", flush=True)
    log_stage("CAMERA_WRITE_GUARD")

    # ── FINAL DOF — set AFTER all camera repositioning ────────────────
    # This is the last step that touches the camera before render. Focus
    # target is resolved after FORCE_FIX and CAMERA_FIX so it's accurate.
    if _HAS_DOF and scene.camera is not None:
        _resolved_tier_for_dof = _resolve_tier_name(manifest)
        if _resolved_tier_for_dof != "preview":
            try:
                focus_target = None
                if hero_meshes:
                    focus_target = hero_meshes[0]
                else:
                    for obj in bpy.data.objects:
                        if obj.type != "MESH":
                            continue
                        lname = obj.name.lower()
                        if any(lname.startswith(p) for p in (
                            "ground", "sky", "backdrop", "contactshadow",
                            "road", "street",
                        )):
                            continue
                        focus_target = obj
                        break
                aperture = 2.2 if _resolved_tier_for_dof == "cinematic" else 3.5
                setup_cinematic_dof(
                    scene.camera, focus_target, aperture_fstop=aperture,
                )
            except Exception as e:
                print(f"DEBUG setup_cinematic_dof failed (non-fatal): {e}", flush=True)
    log_stage("DOF_FINAL")

    # ── PRE-RENDER DIAGNOSTIC — show everything in the scene ──────────
    try:
        print("=" * 70, flush=True)
        print("[PRE_RENDER] ========== SCENE DIAGNOSTIC ==========", flush=True)
        print(f"[PRE_RENDER] Total objects: {len(bpy.data.objects)}", flush=True)
        print(
            f"[PRE_RENDER] Frame range: {bpy.context.scene.frame_start} - "
            f"{bpy.context.scene.frame_end}",
            flush=True,
        )

        _cam = bpy.context.scene.camera
        if _cam:
            print(
                f"[PRE_RENDER] Camera: loc=({_cam.location.x:.2f}, "
                f"{_cam.location.y:.2f}, {_cam.location.z:.2f}) "
                f"lens={_cam.data.lens:.0f}mm",
                flush=True,
            )
        else:
            print("[PRE_RENDER] WARNING: No camera in scene!", flush=True)

        _world = bpy.context.scene.world
        if _world and _world.use_nodes:
            _has_hdri = any(
                n.type == 'TEX_ENVIRONMENT' for n in _world.node_tree.nodes
            )
            _has_sky = any(n.type == 'TEX_SKY' for n in _world.node_tree.nodes)
            print(
                f"[PRE_RENDER] Sky: HDRI={_has_hdri}, procedural={_has_sky}",
                flush=True,
            )
        else:
            print("[PRE_RENDER] WARNING: No world/sky configured!", flush=True)

        _lights = [o for o in bpy.data.objects if o.type == 'LIGHT']
        _total_energy = 0.0
        for _l in _lights:
            try:
                _total_energy += float(_l.data.energy)
            except Exception:
                pass
        print(
            f"[PRE_RENDER] Lights: {len(_lights)} total, "
            f"{_total_energy:.0f}W combined",
            flush=True,
        )

        print("[PRE_RENDER] --- MESH OBJECTS ---", flush=True)
        _mesh_count = 0
        for _obj in sorted(bpy.data.objects, key=lambda o: o.name):
            if _obj.type != 'MESH':
                continue
            _mesh_count += 1
            _dims = _obj.dimensions
            _loc = _obj.location
            _maxd = max(_dims.x, _dims.y, _dims.z)
            _verts = len(_obj.data.vertices) if _obj.data else 0
            _hidden = _obj.hide_render

            _flags = []
            if _maxd < 0.1 and _verts > 10:
                _flags.append("TINY!")
            if _maxd > 500:
                _flags.append("HUGE!")
            if _hidden:
                _flags.append("HIDDEN!")
            if abs(_loc.x) > 100 or abs(_loc.y) > 100:
                _flags.append("OFF-SCREEN!")
            _flag_str = f" *** {'  '.join(_flags)} ***" if _flags else ""

            print(
                f"[PRE_RENDER]   {_obj.name}: "
                f"dims=({_dims.x:.2f}, {_dims.y:.2f}, {_dims.z:.2f}) "
                f"loc=({_loc.x:.1f}, {_loc.y:.1f}, {_loc.z:.1f}) "
                f"verts={_verts} hidden={_hidden}{_flag_str}",
                flush=True,
            )

        print(f"[PRE_RENDER] Total meshes: {_mesh_count}", flush=True)

        for _arm in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
            print(
                f"[PRE_RENDER] Armature: {_arm.name} "
                f"bones={len(_arm.data.bones)} loc={tuple(_arm.location)}",
                flush=True,
            )

        print("[PRE_RENDER] ========== END DIAGNOSTIC ==========", flush=True)
        print("=" * 70, flush=True)
    except Exception as e:
        print(f"[PRE_RENDER] Error (non-fatal): {e}", flush=True)
    log_stage("PRE_RENDER_DIAG")

    # ── CINEMATIC POST-PROCESSING PIPELINE ────────────────────────────
    # Runs AFTER all scene construction, camera positioning, and
    # diagnostics — right before render. Rebuilds the compositor node
    # tree with mood-aware effects that match the tier.  Falls back to
    # the basic setup_compositor() that ran earlier if unavailable.
    if _HAS_CINEMATIC_COMPOSITOR:
        try:
            _scene_plan = manifest.get("_scene_plan") or {}
            _mood = infer_mood(_scene_plan)
            _tier = _resolve_tier_name(manifest)

            # Pick the first hero mesh as DoF focus target
            _hero_focus = hero_meshes[0] if hero_meshes else None

            build_cinematic_compositor(
                bpy.context.scene,
                tier=_tier,
                mood=_mood,
                hero_object=_hero_focus,
            )
            print(
                f"[RENDER] Cinematic compositor applied: "
                f"tier={_tier} mood={_mood} hero={'yes' if _hero_focus else 'no'}",
                flush=True,
            )
        except Exception as _comp_err:
            print(
                f"[RENDER] Cinematic compositor failed (non-fatal), "
                f"basic compositor remains: {_comp_err}",
                flush=True,
            )

    # World Development color grade — wires biome lift/gamma/gain + saturation
    # into the compositor AFTER the main cinematic compositor has set up its
    # nodes (we insert a ColorBalance + HueSat between RenderLayers and the
    # final Composite).  Preview tier skips.
    try:
        from app.scene.cinematic_compositor import apply_biome_grade
        apply_biome_grade(bpy, bpy.context.scene, tier=_resolve_tier_name(manifest))
    except Exception as _grade_err:
        print(f"[WORLD_DEV/GRADE] non-fatal error at compositor hook: {_grade_err}", flush=True)

    log_stage("COMPOSITOR")

    # Final census right before render so we can diff against pre_FRAME_FIX
    # and see exactly what FRAME_FIX/CAMERA_FIX/SAFETY did to the scene.
    _scene_census("pre_RENDER_START")

    # ══════════════════════════════════════════════════════════════════════
    # V1.3.3 Fix C — HERO_VERIFY gate (last chance to abort a bad render)
    # ══════════════════════════════════════════════════════════════════════
    # Five gates. If all pass, render. If only fill_ok fails, retry the
    # director once with the actual hero bbox, then re-check.  If any
    # other gate fails, write a debug snapshot to outputs/debug/ and
    # exit with non-zero code instead of producing a broken render.
    _hv_pass, _hv_reasons = _hero_verify_gate(manifest, retry_allowed=True)
    if not _hv_pass:
        _hero_verify_abort(manifest, _hv_reasons)
        # _hero_verify_abort calls sys.exit(2); execution should not reach here
        sys.exit(2)
    log_stage("HERO_VERIFY")

    log_stage("RENDER_START")
    bpy.ops.render.render(animation=True)
    log_stage("RENDER_COMPLETE")

    # ── Write attribution sidecar (credits.txt + credits_short.txt) ────
    # Attribution is a legal requirement for CC-BY licensed assets.
    # The user copies the sidecar into their YouTube/social-media
    # description when publishing the video.  Never rendered into MP4.
    try:
        from app.services.credits_writer import write_credits_sidecar
        _cred_report = write_credits_sidecar(manifest, output_dir)
        if _cred_report.get("n_missing", 0) > 0:
            print(
                f"[CREDITS] WARN: {_cred_report['n_missing']} asset(s) "
                f"missing attribution — see credits.txt for details",
                flush=True,
            )
    except Exception as _cred_err:
        import traceback as _cred_tb
        print(f"[CREDITS] sidecar write failed (non-fatal): {_cred_err}", flush=True)
        print(_cred_tb.format_exc(), flush=True)

    # ── Library auto-curation: promote successfully-rendered hero ──────
    # Every successful render that used an external (Objaverse/Sketchfab)
    # hero gets an entry in the rich library at app/data/library.json.
    # Idempotent by path — re-promotion just bumps use_count and flips
    # tested=True once use_count >= 2.  Non-fatal: failures log + continue.
    try:
        _hero_path_for_promo = str(manifest.get("hero_asset_path") or "").strip()
        _subject_for_promo = str(
            (manifest.get("scene_plan") or {}).get("focal_subject")
            or (manifest.get("scene_plan") or {}).get("subject")
            or manifest.get("topic", "")
        ).strip().lower()
        _source_for_promo = "unknown"
        if _hero_path_for_promo:
            _hp_lower = _hero_path_for_promo.lower().replace("\\", "/")
            if "objaverse" in _hp_lower:
                _source_for_promo = "objaverse"
            elif "sketchfab" in _hp_lower:
                _source_for_promo = "sketchfab"
            elif "cache" in _hp_lower or "assets/cache" in _hp_lower:
                _source_for_promo = "objaverse" if "objaverse" in _hp_lower else "cached"
            else:
                _source_for_promo = "local"
        if _hero_path_for_promo and _subject_for_promo and _source_for_promo != "local":
            from app.services.library_curator import promote_to_curated
            _hero_name_for_promo = ""
            for _o in bpy.data.objects:
                try:
                    if _o.get("is_hero_root", False) or _o.get("is_hero", False):
                        _hero_name_for_promo = _o.name
                        break
                except Exception:
                    pass
            # Prefer the rich fetch metadata stashed by asset_agent —
            # this is what populates visual_descriptors (orange/black/
            # realistic/etc) and subject_tags correctly.  Falls through
            # to the minimal shape if the stash is unavailable.
            _stashed_fm = manifest.get("hero_fetch_metadata") or {}
            _fetch_meta = {
                "source":      _source_for_promo,
                "name":        _stashed_fm.get("name") or _hero_name_for_promo,
                "description": _stashed_fm.get("description", ""),
                "tags":        _stashed_fm.get("tags", []),
                "uid":         _stashed_fm.get("uid") or manifest.get("hero_source_uid"),
                "type":        manifest.get("hero_asset_type"),
                "score":       _stashed_fm.get("score"),
                "url":         _stashed_fm.get("url"),
                "license":     _stashed_fm.get("license"),
            }
            # Also derive visual descriptors from the user prompt itself
            # ("orange cat" → ['orange']).  This works even when the
            # fetched asset's own metadata is sparse.
            try:
                from app.services.library_curator import extract_visual_hints
                _prompt_hints = extract_visual_hints(
                    str(manifest.get("topic", ""))
                    + " " + str(manifest.get("core_objective_prompt", ""))
                )
                if _prompt_hints:
                    # Merge prompt hints into tags so the library's own
                    # descriptor inference can pick them up
                    _fetch_meta["tags"] = list(set(
                        (_fetch_meta.get("tags") or []) + _prompt_hints
                    ))
                    _fetch_meta["description"] = (
                        (_fetch_meta.get("description", "") or "")
                        + " " + " ".join(_prompt_hints)
                    ).strip()
            except Exception:
                pass
            promote_to_curated(
                asset_path=_hero_path_for_promo,
                subject=_subject_for_promo,
                fetch_metadata=_fetch_meta,
                render_metadata={
                    "scale_class": manifest.get("hero_scale_class"),
                    "bounds_meters": None,
                },
            )
    except Exception as _prom_err:
        print(f"[LIBRARY] promote_to_curated failed (non-fatal): {_prom_err}", flush=True)

    # ── v1.4.3 polish — save composed scene as .blend ────────────────
    # Saves a copy of the just-rendered scene next to the MP4 so the user
    # can download it (Studio surfaces a "Download .blend" button) and
    # remix in Blender. pack_all() bundles textures so the .blend is
    # portable. copy=True writes a snapshot without marking the current
    # session as saved; compress=True trims file size noticeably.
    try:
        blend_path = output_path.with_suffix(".blend")
        try:
            bpy.ops.file.pack_all()
        except Exception as _pack_err:
            print(f"[PIPELINE] pack_all warning: {_pack_err}", flush=True)
        bpy.ops.wm.save_as_mainfile(
            filepath=str(blend_path),
            copy=True,
            compress=True,
        )
        print(f"[PIPELINE] composed scene saved to {blend_path}", flush=True)
    except Exception as _save_err:
        print(f"[PIPELINE] .blend save failed (non-fatal): {_save_err}", flush=True)

    # ── Write pipeline trace log ──────────────────────────────────────
    try:
        trace_path = output_dir / "pipeline_trace.log"
        with open(trace_path, "w", encoding="utf-8") as _lf:
            for entry in render_log:
                _lf.write(
                    f"+{entry['t']:7.3f}s  {entry['stage']}"
                    f"{'  ' + entry['details'] if entry['details'] else ''}\n"
                )
        print(f"[PIPELINE] trace written to {trace_path}", flush=True)
    except Exception as _log_err:
        print(f"[PIPELINE] trace write failed: {_log_err}", flush=True)


if __name__ == "__main__":
    main()
