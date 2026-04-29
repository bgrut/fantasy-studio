"""
import_normalize.py
====================
Deterministic post-import normalization for .glb / .gltf / .fbx hero imports.

Called by the render pipeline AFTER the import completes, BEFORE the
existing [VERIFY] / [HERO_TAG] stages.  Fixes five failure modes seen
in V1 testing:

    1. Orientation — Y-up sources import sideways (eagle inverted,
       lizards on their side, cars lying down)
    2. Scale — .glb files import at wildly varying internal scales
       (Bugatti at 0.3m when expected 4-5m)
    3. Visibility — some exporters ship `hide_render=True` on meshes
       (three cat prompts, no cat visible)
    4. Materials — unlinked near-white Base Color renders as featureless
       blobs (Bugatti pure white)
    5. Vehicle lights — headlight/taillight materials without emission
       read as dead white plastic at night

Plus an asset override file (``app/data/asset_overrides.json``) as an
escape hatch for the 5-10 problem assets the heuristics break on.

Public API:
    normalize_imported_hero(bpy, imported_objects, asset_entry) -> dict
"""

from __future__ import annotations

import json
import math
import os
import traceback
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_OVERRIDES_PATH = _ROOT / "app" / "data" / "asset_overrides.json"


# Category → scale_class → target max-dimension in meters.  Used to
# normalize .glb imports that arrive at unit-scale or otherwise unusable
# proportions.  Keys that don't match fall through to 1.5m default.
_SCALE_TARGETS: dict = {
    # character sizes
    ("character", "tiny"):     0.15,   # mouse, insect
    ("character", "small"):    0.5,    # cat, rabbit, small dog
    ("character", "medium"):   1.7,    # human, large dog, deer
    ("character", "large"):    2.5,    # horse, bear, tiger
    ("character", "huge"):     4.0,    # elephant, large bear
    ("character", "massive"):  12.0,   # dragon, godzilla scale
    # animal sizes (treat same as character — sometimes mislabeled)
    ("animal", "tiny"):        0.15,
    ("animal", "small"):       0.5,
    ("animal", "medium"):      1.8,    # wolf, goat
    ("animal", "large"):       3.0,    # bear, horse, tiger
    ("animal", "huge"):        6.0,    # elephant, rhino, small whale
    ("animal", "massive"):     12.0,   # sperm whale, dinosaur
    # vehicles
    ("vehicle", "small"):      2.0,    # motorbike
    ("vehicle", "medium"):     4.5,    # sedan, sports car
    ("vehicle", "large"):      6.5,    # truck, SUV
    ("vehicle", "huge"):       12.0,   # bus, airplane
    # environments (landscapes stay huge)
    ("environment", "medium"): 30.0,
    ("environment", "large"):  80.0,
    ("environment", "huge"):   150.0,
    # props
    ("prop", "tiny"):          0.1,
    ("prop", "small"):         0.3,
    ("prop", "medium"):        0.8,
    ("prop", "large"):         2.0,
}

# Subject-noun → (category, scale_class) inference for when library
# metadata is missing or wrong ("character/medium" on a whale, etc).
_SUBJECT_SCALE_HINTS: dict = {
    # massive animals
    "whale":      ("animal", "massive"),
    "sperm_whale": ("animal", "massive"),
    "dinosaur":   ("animal", "massive"),
    "godzilla":   ("character", "massive"),
    "dragon":     ("animal", "massive"),
    # huge animals
    "elephant":   ("animal", "huge"),
    "rhino":      ("animal", "huge"),
    "rhinoceros": ("animal", "huge"),
    "hippo":      ("animal", "huge"),
    "hippopotamus": ("animal", "huge"),
    "giraffe":    ("animal", "huge"),
    # large animals
    "horse":      ("animal", "large"),
    "bear":       ("animal", "large"),
    "polar_bear": ("animal", "large"),
    "tiger":      ("animal", "large"),
    "lion":       ("animal", "large"),
    "cheetah":    ("animal", "large"),
    "leopard":    ("animal", "large"),
    "deer":       ("animal", "large"),
    "wolf":       ("animal", "medium"),
    "cow":        ("animal", "large"),
    "buffalo":    ("animal", "large"),
    "crocodile":  ("animal", "large"),
    # medium animals
    "dog":        ("animal", "small"),
    "pig":        ("animal", "medium"),
    "goat":       ("animal", "medium"),
    "sheep":      ("animal", "medium"),
    "hyena":      ("animal", "medium"),
    "eagle":      ("animal", "small"),
    "owl":        ("animal", "small"),
    "hawk":       ("animal", "small"),
    # small animals
    "cat":        ("animal", "small"),
    "rabbit":     ("animal", "small"),
    "fox":        ("animal", "small"),
    "rooster":    ("animal", "small"),
    "chicken":    ("animal", "small"),
    "lizard":     ("animal", "small"),
    "monkey":     ("animal", "medium"),
    # vehicles
    "car":        ("vehicle", "medium"),
    "bmw":        ("vehicle", "medium"),
    "ferrari":    ("vehicle", "medium"),
    "porsche":    ("vehicle", "medium"),
    "bugatti":    ("vehicle", "medium"),
    "mclaren":    ("vehicle", "medium"),
    "audi":       ("vehicle", "medium"),
    "toyota":     ("vehicle", "medium"),
    "ford":       ("vehicle", "medium"),
    "lamborghini": ("vehicle", "medium"),
    "aston":      ("vehicle", "medium"),
    "aston_martin": ("vehicle", "medium"),
    "truck":      ("vehicle", "large"),
    "motorcycle": ("vehicle", "small"),
    "airplane":   ("vehicle", "huge"),
    "helicopter": ("vehicle", "medium"),
    "boat":       ("vehicle", "large"),
    "ship":       ("vehicle", "huge"),
    "spaceship":  ("vehicle", "huge"),
}

_LIGHT_KEYWORDS = (
    "headlight", "taillight", "brake", "signal", "indicator", "led",
    "light_lens", "emissive", "glow", "lamp", "bulb",
)

_COLOR_KEYWORDS = {
    "red":    (0.70, 0.10, 0.10),
    "blue":   (0.10, 0.20, 0.70),
    "black":  (0.05, 0.05, 0.05),
    "white":  (0.90, 0.90, 0.90),
    "orange": (0.80, 0.40, 0.15),
    "tabby":  (0.75, 0.45, 0.20),
    "ginger": (0.80, 0.42, 0.18),
    "green":  (0.15, 0.50, 0.20),
    "yellow": (0.85, 0.75, 0.15),
    "silver": (0.80, 0.80, 0.82),
    "golden": (0.85, 0.68, 0.25),
    "grey":   (0.45, 0.45, 0.45),
    "gray":   (0.45, 0.45, 0.45),
    "brown":  (0.35, 0.22, 0.12),
}

_DEFAULT_TINT = (0.35, 0.35, 0.35)   # safer than white for untextured


# ═══════════════════════════════════════════════════════════════════════════
# Bbox helpers
# ═══════════════════════════════════════════════════════════════════════════

def _combined_world_bbox(meshes) -> dict | None:
    """World-space min/max across every mesh.  Returns None if empty."""
    try:
        from mathutils import Vector
    except ImportError:
        return None
    coords: list = []
    for m in meshes:
        try:
            mw = m.matrix_world
            for c in m.bound_box:
                coords.append(mw @ Vector(c))
        except Exception:
            continue
    if not coords:
        return None
    return {
        "min_x": min(c.x for c in coords), "max_x": max(c.x for c in coords),
        "min_y": min(c.y for c in coords), "max_y": max(c.y for c in coords),
        "min_z": min(c.z for c in coords), "max_z": max(c.z for c in coords),
    }


def _bbox_dims(bbox: dict) -> tuple:
    """Return (width_x, depth_y, height_z, max_dim)."""
    if not bbox:
        return 0.0, 0.0, 0.0, 0.0
    w = bbox["max_x"] - bbox["min_x"]
    d = bbox["max_y"] - bbox["min_y"]
    h = bbox["max_z"] - bbox["min_z"]
    return w, d, h, max(w, d, h, 0.001)


# ═══════════════════════════════════════════════════════════════════════════
# 1B. Orientation fix
# ═══════════════════════════════════════════════════════════════════════════

def _fix_orientation(bpy, meshes, asset_entry: dict) -> bool:
    """Rotate meshes if they came in sideways or lying flat."""
    bbox = _combined_world_bbox(meshes)
    if not bbox:
        return False
    w, d, h, _ = _bbox_dims(bbox)
    category = str(asset_entry.get("category") or "").lower()

    # Animals / characters should stand — height should dominate a min-side test
    if category in ("animal", "character", "creature"):
        if h < min(w, d) * 0.4:
            # Flat — rotate 90° around X to stand up
            for m in meshes:
                m.rotation_euler.x += math.radians(90)
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            print(
                f"[IMPORT_NORMALIZE] flat {category} detected "
                f"(w={w:.2f} d={d:.2f} h={h:.2f}) — rotated 90° X",
                flush=True,
            )
            return True

    # Vehicles should be longer in Y (forward axis).  If X is the long axis,
    # the model is parked perpendicular to forward — rotate 90° around Z.
    if category == "vehicle":
        if w > d * 1.5 and w > h:
            for m in meshes:
                m.rotation_euler.z += math.radians(90)
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            print(
                f"[IMPORT_NORMALIZE] sideways vehicle detected "
                f"(w={w:.2f} d={d:.2f} h={h:.2f}) — rotated 90° Z",
                flush=True,
            )
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
# 1C. Scale enforcement
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_category_and_scale(asset_entry: dict) -> tuple:
    """Determine (category, scale_class, source_note) from an asset_entry.

    Priority order:
      1. asset_entry['category'] + asset_entry['scale_class'] (library schema)
      2. asset_entry['type']     + asset_entry['scale_class'] (registry schema)
      3. subject-noun inference (whale → animal/massive) — used when the
         library entry has wrong/missing category/scale_class
      4. Default: character/medium

    Subject inference is applied ANY time the resolved scale_class is
    'medium' (the ingest default) AND the subject has a stronger hint —
    this fixes the whale=medium migration artifact without overriding
    cases where the user explicitly set a non-medium scale_class.
    """
    ae = asset_entry or {}
    # Layer 1: explicit category/type
    category = str(ae.get("category") or ae.get("type") or "").lower().strip()
    scale_class = str(ae.get("scale_class") or "").lower().strip()

    # Layer 2: subject-noun inference — only overrides when metadata is
    # weak (no category, or default medium).
    subject = str(ae.get("subject") or ae.get("name") or "").lower().strip()
    # Try multi-word keys first (sperm_whale, polar_bear, aston_martin)
    hint = None
    subject_compact = subject.replace(" ", "_").replace("-", "_")
    for key in _SUBJECT_SCALE_HINTS:
        if key in subject_compact:
            hint = _SUBJECT_SCALE_HINTS[key]
            break
    # Also check subject_tags for stronger signal
    if not hint:
        for tag in (ae.get("subject_tags") or []):
            tag_lc = str(tag).lower()
            if tag_lc in _SUBJECT_SCALE_HINTS:
                hint = _SUBJECT_SCALE_HINTS[tag_lc]
                break

    source_note = "metadata"
    if hint is not None:
        h_cat, h_scale = hint
        # Override category if missing OR if subject hint is "animal" and
        # library says "character" (migration artifact where every ingest
        # defaulted to character).
        if not category or (category == "character" and h_cat == "animal"):
            category = h_cat
            source_note = "subject-inferred"
        # Override scale_class if missing OR if library defaulted to medium
        # but the subject implies something larger/smaller.
        if not scale_class or scale_class == "medium":
            if h_scale != "medium":
                scale_class = h_scale
                source_note = "subject-inferred"

    # Layer 3: defaults
    if not category:
        category = "character"
    if not scale_class:
        scale_class = "medium"
    return category, scale_class, source_note


def retag_forced_hero_by_proximity(bpy, meshes, asset_entry: dict,
                                    origin_threshold_m: float = 10.0) -> int:
    """V1.3.2 Phase C — prune is_forced_hero from env-placed meshes.

    Some import paths (.blend library append with multi-root scenes,
    Sketchfab models where the top root contains both vehicle panels
    AND background props) stamp is_forced_hero=True on every imported
    object.  When the Hero Tagger later picks the forced-hero cluster,
    a background mesh near origin can win over a lifted vehicle panel.

    Remedy: walk the imported meshes, compute each mesh's world-space
    bbox center, and un-set is_forced_hero on any whose center sits
    more than ``origin_threshold_m`` metres from the world origin.
    Environment geometry typically lives far from (0,0,0); the hero
    is grounded there.

    Returns the count of meshes un-tagged (0 when no-op).
    """
    if not asset_entry or not meshes:
        return 0
    # Only runs when the asset was marked as a forced-hero selection.
    if not asset_entry.get("_is_forced_hero"):
        return 0
    untagged = 0
    try:
        from mathutils import Vector as _PVec
        for obj in meshes:
            if obj is None or getattr(obj, "type", None) != "MESH":
                continue
            if not obj.get("is_forced_hero", False):
                continue
            try:
                corners = [obj.matrix_world @ _PVec(tuple(c)) for c in obj.bound_box]
            except Exception:
                continue
            if not corners:
                continue
            cx = sum(c.x for c in corners) / len(corners)
            cy = sum(c.y for c in corners) / len(corners)
            cz = sum(c.z for c in corners) / len(corners)
            dist_from_origin = (cx * cx + cy * cy + cz * cz) ** 0.5
            if dist_from_origin > origin_threshold_m:
                obj["is_forced_hero"] = False
                untagged += 1
    except Exception as e:
        print(
            f"[IMPORT_NORMALIZE] retag_forced_hero_by_proximity error "
            f"(non-fatal): {e}",
            flush=True,
        )
    if untagged:
        print(
            f"[IMPORT_NORMALIZE] proximity retag: removed is_forced_hero "
            f"from {untagged} mesh(es) > {origin_threshold_m}m from origin "
            f"(asset_id={asset_entry.get('id')!r})",
            flush=True,
        )
    return untagged


_VEHICLE_SUBJECT_TOKENS = frozenset({
    "ferrari", "bmw", "lamborghini", "porsche", "bugatti", "aston",
    "audi", "mercedes", "toyota", "tesla", "mustang", "corvette",
    "camaro", "chevrolet", "ford", "car", "truck", "vehicle",
    "motorcycle", "bike", "scooter", "bus", "van",
})


def _looks_like_vehicle(asset_entry: dict, bbox_dims: tuple) -> tuple[bool, str]:
    """V1.3.1 Fix 2 — detect vehicles to skip character-size shrinking.

    Returns ``(is_vehicle, reason)`` where ``reason`` is a short tag used
    in the log. ``bbox_dims`` is ``(w, d, h)`` from the imported mesh's
    world-space combined bbox.

    Two signals, either is sufficient:
      1. Prompt/entry subject matches a known vehicle noun
      2. Dimensions are car-shaped: 3.5-8m on the long axis, ≤ 2.5m tall,
         long axis at least 1.5x the height (rules out tall narrow props)
    """
    # Signal 1: subject-level
    ae = asset_entry or {}
    subj = str(ae.get("subject") or ae.get("name") or "").lower().strip()
    category = str(ae.get("category") or ae.get("type") or "").lower().strip()
    if category == "vehicle":
        return True, "category=vehicle"
    subj_tokens = set(subj.replace("-", "_").split("_"))
    if subj_tokens & _VEHICLE_SUBJECT_TOKENS:
        return True, f"subject={subj!r}"
    for tag in (ae.get("subject_tags") or []):
        tl = str(tag).lower().strip()
        if tl in _VEHICLE_SUBJECT_TOKENS:
            return True, f"subject_tag={tl!r}"

    # Signal 2: dimension-based
    try:
        w, d, h = float(bbox_dims[0]), float(bbox_dims[1]), float(bbox_dims[2])
    except Exception:
        return False, ""
    longest = max(w, d)
    if (
        3.5 < longest < 8.0
        and h < 2.5
        and longest > h * 1.5
    ):
        return True, f"bbox_shape={w:.2f}x{d:.2f}x{h:.2f}m"

    return False, ""


def _enforce_scale(bpy, meshes, asset_entry: dict) -> float | None:
    """Scale mesh group to a category-appropriate target size."""
    category, scale_class, source_note = _resolve_category_and_scale(asset_entry)
    target = _SCALE_TARGETS.get((category, scale_class), 1.5)

    bbox = _combined_world_bbox(meshes)
    if not bbox:
        return None
    bw, bd, bh, current = _bbox_dims(bbox)
    if current < 0.01:
        print(
            f"[IMPORT_NORMALIZE] bbox too small ({current:.4f}m) — skipping scale",
            flush=True,
        )
        return None

    # V1.3.1 Fix 2 — skip shrink when the hero is clearly a vehicle.
    # Protects against wrong library metadata (BMW tagged character/medium
    # would otherwise shrink from 4.8m to 1.7m).  Runs BEFORE the factor
    # computation so we don't even compute a misleading scaling intent.
    is_vehicle, vehicle_reason = _looks_like_vehicle(asset_entry, (bw, bd, bh))
    if is_vehicle and abs((target / current) - 1.0) > 0.2:
        print(
            f"[IMPORT_NORMALIZE] SKIPPED — detected vehicle "
            f"(bbox={bw:.2f}x{bd:.2f}x{bh:.2f}m, reason={vehicle_reason}); "
            f"keeping imported size {current:.2f}m instead of shrinking "
            f"to target {target:.2f}m",
            flush=True,
        )
        return 1.0

    factor = target / current
    # Clamp: refuse to scale by absurd factors (corrupted source)
    factor = max(0.001, min(1000.0, factor))
    if abs(factor - 1.0) < 0.05:
        print(
            f"[IMPORT_NORMALIZE] scale OK (current={current:.2f}m target={target:.2f}m "
            f"factor≈1.0, category={category}/{scale_class} src={source_note}) — "
            f"skipping",
            flush=True,
        )
        return 1.0

    for m in meshes:
        m.scale = tuple(s * factor for s in m.scale)
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    print(
        f"[IMPORT_NORMALIZE] scaled by {factor:.3f}x to target {target:.2f}m "
        f"(was {current:.3f}m, category={category}/{scale_class} src={source_note})",
        flush=True,
    )
    return factor


# ═══════════════════════════════════════════════════════════════════════════
# 1D. Visibility restoration
# ═══════════════════════════════════════════════════════════════════════════

def _restore_visibility(bpy, meshes) -> int:
    """Unconditionally clear hide flags and ensure meshes are in active view layer."""
    restored = 0
    for m in meshes:
        try:
            hid = bool(m.hide_render) or bool(m.hide_viewport)
            try:
                hid = hid or m.hide_get()
            except Exception:
                pass
            if hid:
                m.hide_render = False
                m.hide_viewport = False
                try:
                    m.hide_set(False)
                except Exception:
                    pass
                restored += 1
        except Exception:
            continue

    if restored:
        print(
            f"[IMPORT_NORMALIZE] restored visibility on {restored} hidden mesh(es)",
            flush=True,
        )
    return restored


# ═══════════════════════════════════════════════════════════════════════════
# 1E. Material rescue
# ═══════════════════════════════════════════════════════════════════════════

def _find_principled_bsdf(mat):
    """Return the first Principled-BSDF node in a material's tree."""
    try:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                return n
    except Exception:
        pass
    return None


def _infer_color(mesh_name: str, asset_entry: dict) -> tuple:
    """Plausible color from mesh name hints or library visual_descriptors."""
    hints = (mesh_name or "").lower()
    hints += " " + " ".join(asset_entry.get("visual_descriptors") or [])
    hints += " " + " ".join(asset_entry.get("subject_tags") or [])
    for kw, rgb in _COLOR_KEYWORDS.items():
        if kw in hints:
            return rgb
    return _DEFAULT_TINT


def _rescue_materials(bpy, meshes, asset_entry: dict) -> int:
    """Patch unlinked near-white Base Colors; flag missing textures.
    Returns the number of materials rescued."""
    rescued = 0
    for m in meshes:
        for slot in getattr(m, "material_slots", []):
            mat = getattr(slot, "material", None)
            if not mat or not getattr(mat, "use_nodes", False):
                continue
            bsdf = _find_principled_bsdf(mat)
            if not bsdf:
                continue

            # Base Color rescue
            base = bsdf.inputs.get("Base Color")
            if base and not base.is_linked:
                col = base.default_value
                if col[0] > 0.9 and col[1] > 0.9 and col[2] > 0.9:
                    tint = _infer_color(m.name, asset_entry)
                    try:
                        base.default_value = (*tint, 1.0)
                        rescued += 1
                        print(
                            f"[IMPORT_NORMALIZE] material rescue: "
                            f"{mat.name!r} near-white → {tint}",
                            flush=True,
                        )
                    except Exception:
                        pass

            # Texture path validation (non-fatal warning)
            if base and base.is_linked:
                try:
                    tex_node = base.links[0].from_node
                    if tex_node.type == "TEX_IMAGE" and tex_node.image:
                        img_path = bpy.path.abspath(tex_node.image.filepath)
                        if img_path and not os.path.exists(img_path):
                            print(
                                f"[IMPORT_NORMALIZE] WARN: texture missing at "
                                f"{img_path!r} ({mat.name})",
                                flush=True,
                            )
                except Exception:
                    pass
    return rescued


# ═══════════════════════════════════════════════════════════════════════════
# 1F. Vehicle lights
# ═══════════════════════════════════════════════════════════════════════════

def _enable_vehicle_lights(bpy, meshes) -> int:
    """Give headlight/taillight materials emission so they glow."""
    lit = 0
    for m in meshes:
        for slot in getattr(m, "material_slots", []):
            mat = getattr(slot, "material", None)
            if not mat or not getattr(mat, "use_nodes", False):
                continue
            mat_name_lc = (mat.name or "").lower()
            if not any(kw in mat_name_lc for kw in _LIGHT_KEYWORDS):
                continue
            bsdf = _find_principled_bsdf(mat)
            if not bsdf:
                continue

            # Taillight keywords → red; else warm headlight
            if any(kw in mat_name_lc for kw in ("tail", "brake", "red")):
                em_col = (1.0, 0.12, 0.08, 1.0)
            else:
                em_col = (1.0, 0.90, 0.70, 1.0)

            try:
                em = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
                if em and not em.is_linked:
                    em.default_value = em_col
                strength = bsdf.inputs.get("Emission Strength")
                if strength:
                    strength.default_value = 3.0
                lit += 1
            except Exception:
                continue

    if lit:
        print(
            f"[IMPORT_NORMALIZE] enabled emission on {lit} vehicle light material(s)",
            flush=True,
        )
    return lit


# ═══════════════════════════════════════════════════════════════════════════
# Grounding
# ═══════════════════════════════════════════════════════════════════════════

def _ground_hero(bpy, meshes) -> float:
    """Translate the group so min Z sits at z=0 (skip for environments)."""
    bbox = _combined_world_bbox(meshes)
    if not bbox:
        return 0.0
    dz = -bbox["min_z"]
    if abs(dz) < 0.01:
        return 0.0
    for m in meshes:
        m.location.z += dz
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    print(
        f"[IMPORT_NORMALIZE] grounded hero by dz={dz:.3f} "
        f"(min_z was {bbox['min_z']:.3f})",
        flush=True,
    )
    return dz


# ═══════════════════════════════════════════════════════════════════════════
# 1G. Asset overrides
# ═══════════════════════════════════════════════════════════════════════════

def _load_overrides() -> dict:
    try:
        if _OVERRIDES_PATH.exists():
            return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[IMPORT_NORMALIZE] overrides load failed: {e}", flush=True)
    return {}


def _apply_asset_overrides(bpy, meshes, asset_id: str) -> dict:
    """Read app/data/asset_overrides.json and apply overrides for this asset.

    Priority:
      1. quality=rejected → caller should not even be here (handled by resolver),
         but if we see it, log loudly.
      2. rotation_euler → replaces runtime rotation
      3. scale_override → force to this max-dim (overrides heuristic)
      4. material_tint_hint → force all Principled BSDF Base Colors to this color
    """
    applied: dict = {}
    if not asset_id:
        return applied
    overrides = _load_overrides()
    override = overrides.get(asset_id)
    if not isinstance(override, dict):
        return applied

    print(f"[IMPORT_NORMALIZE] applying override for id={asset_id!r}", flush=True)

    if override.get("quality") == "rejected":
        print(
            f"[IMPORT_NORMALIZE] WARN: asset {asset_id!r} is marked rejected — "
            f"the resolver should have skipped it; rendering anyway",
            flush=True,
        )
        applied["rejected"] = True

    # Rotation override (replaces, not increments)
    rot = override.get("rotation_euler")
    if isinstance(rot, (list, tuple)) and len(rot) == 3:
        try:
            for m in meshes:
                m.rotation_euler = (
                    math.radians(float(rot[0])),
                    math.radians(float(rot[1])),
                    math.radians(float(rot[2])),
                )
            bpy.context.view_layer.update()
            applied["rotation"] = list(rot)
            print(
                f"[IMPORT_NORMALIZE]   rotation_euler override: {rot}",
                flush=True,
            )
        except Exception as e:
            print(f"[IMPORT_NORMALIZE]   rotation override failed: {e}", flush=True)

    # Scale override (replaces heuristic scale)
    scl = override.get("scale_override")
    if isinstance(scl, (int, float)) and scl > 0:
        bbox = _combined_world_bbox(meshes)
        if bbox:
            _, _, _, current = _bbox_dims(bbox)
            if current > 0.01:
                factor = float(scl) / current
                for m in meshes:
                    m.scale = tuple(s * factor for s in m.scale)
                bpy.context.view_layer.update()
                applied["scale_factor"] = factor
                print(
                    f"[IMPORT_NORMALIZE]   scale_override: scaled by {factor:.3f}x "
                    f"to force {scl}m",
                    flush=True,
                )

    # Material tint hint (force Base Color for all materials)
    tint_hint = override.get("material_tint_hint")
    if tint_hint and isinstance(tint_hint, str):
        rgb = _COLOR_KEYWORDS.get(tint_hint.lower(), _DEFAULT_TINT)
        count = 0
        for m in meshes:
            for slot in getattr(m, "material_slots", []):
                mat = getattr(slot, "material", None)
                if not mat or not getattr(mat, "use_nodes", False):
                    continue
                bsdf = _find_principled_bsdf(mat)
                if not bsdf:
                    continue
                base = bsdf.inputs.get("Base Color")
                if base and not base.is_linked:
                    try:
                        base.default_value = (*rgb, 1.0)
                        count += 1
                    except Exception:
                        pass
        if count:
            applied["material_tint"] = rgb
            print(
                f"[IMPORT_NORMALIZE]   material_tint_hint={tint_hint!r}: "
                f"tinted {count} Base Color input(s)",
                flush=True,
            )

    return applied


# ═══════════════════════════════════════════════════════════════════════════
# Public entry point
# ═══════════════════════════════════════════════════════════════════════════

def normalize_imported_hero(
    bpy,
    imported_objects: list,
    asset_entry: dict | None,
) -> dict:
    """Run the 5-step post-import normalization.  Never raises.

    Returns a report dict:
        {
          "orientation_fixed": bool,
          "scale_applied": float | None,
          "materials_rescued": int,
          "visibility_restored": int,
          "lights_enabled": int,
          "grounded_dz": float,
          "overrides_applied": dict,
          "hero_meshes": int,
        }
    """
    report = {
        "orientation_fixed":   False,
        "scale_applied":       None,
        "materials_rescued":   0,
        "visibility_restored": 0,
        "lights_enabled":      0,
        "grounded_dz":         0.0,
        "overrides_applied":   {},
        "hero_meshes":         0,
    }
    try:
        if not imported_objects:
            print("[IMPORT_NORMALIZE] no imported objects — skipping", flush=True)
            return report
        asset_entry = asset_entry or {}

        hero_meshes = [
            o for o in imported_objects
            if getattr(o, "type", None) == "MESH"
        ]
        report["hero_meshes"] = len(hero_meshes)
        if not hero_meshes:
            print("[IMPORT_NORMALIZE] no hero meshes found — skipping", flush=True)
            return report

        # Sequential normalize
        report["orientation_fixed"]   = _fix_orientation(bpy, hero_meshes, asset_entry)
        report["scale_applied"]       = _enforce_scale(bpy, hero_meshes, asset_entry)
        report["visibility_restored"] = _restore_visibility(bpy, hero_meshes)
        report["materials_rescued"]   = _rescue_materials(bpy, hero_meshes, asset_entry)
        if str(asset_entry.get("category") or "").lower() == "vehicle":
            report["lights_enabled"] = _enable_vehicle_lights(bpy, hero_meshes)
        if str(asset_entry.get("category") or "").lower() != "environment":
            report["grounded_dz"] = _ground_hero(bpy, hero_meshes)

        # V1.3.2 Phase C — proximity-based forced-hero retag.
        # Some import paths (.blend library append, multi-root Sketchfab
        # scenes) stamp is_forced_hero=True on every imported object —
        # including environment meshes that live far from origin.  The
        # Hero Tagger then picks the wrong cluster.  Walk the imported
        # meshes AFTER normalization and un-set is_forced_hero on any
        # whose world-space bbox center lies > 10m from origin.
        _retagged = retag_forced_hero_by_proximity(
            bpy, hero_meshes, asset_entry, origin_threshold_m=10.0,
        )
        if _retagged:
            report["proximity_retagged"] = _retagged

        # Overrides LAST — they win over heuristics
        report["overrides_applied"] = _apply_asset_overrides(
            bpy, hero_meshes, asset_entry.get("id", ""),
        )

        print(
            f"[IMPORT_NORMALIZE] asset={asset_entry.get('id')!r} "
            f"orient={report['orientation_fixed']} "
            f"scale={report['scale_applied']} "
            f"vis={report['visibility_restored']} "
            f"mats={report['materials_rescued']} "
            f"lights={report['lights_enabled']} "
            f"overrides={bool(report['overrides_applied'])}",
            flush=True,
        )
    except Exception as e:
        print(f"[IMPORT_NORMALIZE] failed (non-fatal): {e}", flush=True)
        print(traceback.format_exc(), flush=True)
    return report
