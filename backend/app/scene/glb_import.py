"""
glb_import.py
=============
Single entry point for importing multi-object GLB/GLTF hero assets as a
coherent group.

Objaverse (and many Sketchfab) downloads are not single meshes — they are
hierarchies of 10-30 objects (empties for scene structure, multiple mesh
parts for body / clothing / accessories, sometimes an armature). The
existing per-object scaling paths in the pipeline pick one "hero" mesh,
size that one to target, and leave the other 15 objects at their original
(often 10+ meter) scale. The camera then sees either nothing or a
massively-oversized jacket where the character should be.

``import_glb_as_hero_group`` fixes this by:

1. Importing the GLB and collecting every new object it produced.
2. Computing a COMBINED world-space bounding box over every mesh.
3. Finding (or creating) a single root empty that owns the whole tree.
4. Scaling that root so the combined max-dimension hits ``target_size``.
5. Grounding + centring the root so the group sits on z=0 at the origin.
6. Unhiding every new object in viewport + render.

Returns the full list of newly-imported objects so the caller can wire
them into animation, camera framing, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


# Default target sizes per asset type. The caller normally passes an
# explicit ``target_size``; the dict is here so templates that forward
# ``asset_type`` without caring about the number get something sensible.
_TARGET_SIZE_BY_TYPE: dict[str, float] = {
    "character": 1.8,
    "humanoid":  1.8,
    "animal":    1.5,
    "vehicle":   4.5,
    "car":       4.5,
    "prop":      0.8,
    "product":   0.4,
}

_PREFERRED_ROOT_NAMES = (
    "root",
    "gltf_scenerootnode",
    "sketchfab_model",
    "scene",
)


def validate_hero_mesh(bpy, meshes) -> tuple[bool, str]:
    """Validate imported meshes are a usable 3D hero, not a flat card or
    placeholder stub.

    Returns ``(ok, reason)`` — ``ok=False`` means the caller should discard
    this import and try the next candidate.

    Checks:
    1. **Vertex count** — fewer than 100 verts across all meshes is almost
       certainly a placeholder cube / default primitive, not a real model.
    2. **Flatness** — if the thinnest axis is < 8% of the longest AND the
       total vertex count is under 5 000, the model is a flat image card
       (common Objaverse failure: a photo textured onto a single quad).
       High-poly models (>5 000 verts) that happen to be flat are likely
       intentional (a rug, a leaf, a sign) and pass.
    """
    if not meshes:
        return False, "no meshes"

    total_verts = 0
    for obj in meshes:
        md = getattr(obj, "data", None)
        if md is not None and hasattr(md, "vertices"):
            total_verts += len(md.vertices)

    if total_verts < 100:
        return False, f"placeholder ({total_verts} verts)"

    # World-space bbox for flatness check
    bbox = _combined_world_bbox(meshes)
    if bbox is not None:
        dims = sorted([
            bbox["max_x"] - bbox["min_x"],
            bbox["max_y"] - bbox["min_y"],
            bbox["max_z"] - bbox["min_z"],
        ])
        thinnest = dims[0]
        longest = dims[-1]
        if longest > 0.001 and thinnest / longest < 0.08 and total_verts < 5000:
            return False, (
                f"flat card (ratio={thinnest/longest:.3f}, "
                f"verts={total_verts}, thin={thinnest:.3f}, long={longest:.3f})"
            )

    return True, "ok"


def _tag_as_hero(objects: Iterable) -> None:
    """Mark objects with ``obj["is_hero"] = True`` so downstream FORCE_FIX /
    HERO_SCALE / FRAME_FIX / CAMERA_FIX can filter hero meshes from
    environment geometry without name-heuristic guessing. Silent on failure:
    some Blender object types (cameras, lights in rare builds) reject
    id-properties and we don't want the whole import to unwind over it."""
    count = 0
    for obj in objects:
        try:
            obj["is_hero"] = True
            count += 1
        except Exception:
            pass
    if count:
        print(f"[HERO_TAG] tagged {count} object(s) as is_hero=True", flush=True)


def _combined_world_bbox(mesh_objects: Iterable):
    """World-space min/max corners across every mesh. Returns None if no
    mesh has a usable ``bound_box`` (e.g. procedural-only imports)."""
    from mathutils import Vector  # Blender-only import

    coords = []
    for obj in mesh_objects:
        bb = getattr(obj, "bound_box", None)
        if not bb:
            continue
        mw = obj.matrix_world
        for corner in bb:
            coords.append(mw @ Vector(corner))
    if not coords:
        return None
    return {
        "min_x": min(c.x for c in coords),
        "max_x": max(c.x for c in coords),
        "min_y": min(c.y for c in coords),
        "max_y": max(c.y for c in coords),
        "min_z": min(c.z for c in coords),
        "max_z": max(c.z for c in coords),
    }


def _dedup_sketchfab_roots(bpy, new_objects: list) -> list:
    """Remove duplicate Sketchfab root hierarchies from a GLB/GLTF import.

    Many Sketchfab exports ship TWO copies of the scene under root empties
    with auto-suffixed names (``Sketchfab_model`` + ``Sketchfab_model_0``,
    ``root`` + ``root_1``, ``GLTF_SceneRootNode`` + ``GLTF_SceneRootNode_2``).
    Importing such a file renders both copies overlaid — the "double car"
    bug.

    Returns the filtered ``new_objects`` list with duplicate hierarchies
    removed from both the list and ``bpy.data.objects``.
    """
    import re

    if len(new_objects) < 2:
        return new_objects

    # ── Name-pattern based twin detection (robust to parent changes) ──
    _TWIN_PATTERNS = [
        re.compile(r"^Sketchfab_model(\.\d+|_\d+)?$", re.IGNORECASE),
        re.compile(r"^root(\.\d+|_\d+)?$", re.IGNORECASE),
        re.compile(r"^GLTF_SceneRootNode(\.\d+|_\d+)?$", re.IGNORECASE),
        re.compile(r"^scene(\.\d+|_\d+)?$", re.IGNORECASE),
    ]

    def _matches_pattern(obj):
        for pat in _TWIN_PATTERNS:
            if pat.match(obj.name):
                return pat.pattern
        return None

    groups: dict[str, list] = {}
    for obj in new_objects:
        key = _matches_pattern(obj)
        if key is not None:
            groups.setdefault(key, []).append(obj)

    def _descendant_count(obj) -> int:
        """Count all descendants (direct + indirect children)."""
        count = 0
        for child in obj.children:
            count += 1 + _descendant_count(child)
        return count

    def _has_animation(obj) -> bool:
        """Check if obj or any descendant has animation data WITH KEYFRAMES."""
        ad = getattr(obj, "animation_data", None)
        if ad and ad.action:
            try:
                _fcs = ad.action.fcurves
            except AttributeError:
                _fcs = []
                if hasattr(ad.action, "layers") and ad.action.layers:
                    _lyr = ad.action.layers[0]
                    if hasattr(_lyr, "strips") and _lyr.strips:
                        _stp = _lyr.strips[0]
                        if hasattr(_stp, "channelbags") and _stp.channelbags:
                            _fcs = _stp.channelbags[0].fcurves
            for _fc in _fcs:
                if len(_fc.keyframe_points) > 0:
                    return True
        for child in obj.children:
            if _has_animation(child):
                return True
        return False

    def _combined_mesh_bbox_diag(obj) -> float:
        """Diagonal of the combined world-space bbox of obj + all mesh descendants."""
        from mathutils import Vector
        coords: list = []

        def _walk(o):
            if o.type == "MESH":
                try:
                    bb = o.bound_box
                    mw = o.matrix_world
                    for c in bb:
                        coords.append(mw @ Vector(c))
                except Exception:
                    pass
            for ch in o.children:
                _walk(ch)

        _walk(obj)
        if not coords:
            return 0.0
        dx = max(c.x for c in coords) - min(c.x for c in coords)
        dy = max(c.y for c in coords) - min(c.y for c in coords)
        dz = max(c.z for c in coords) - min(c.z for c in coords)
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    # Only keep groups that have actual twins
    twin_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not twin_groups:
        return new_objects

    print(
        f"[GLB_DEDUP] scanning {len(new_objects)} imported objects, "
        f"found {len(twin_groups)} twin group(s)",
        flush=True,
    )

    # V1.3.3 Fix B: track (loser, keeper) pairs so we REPARENT children
    # before deleting the loser root.  Old code deleted the loser AND
    # all its descendants recursively — but in Sketchfab .blend exports
    # the children were unique vehicle panels split across twin roots,
    # not duplicates.  Recursive delete was the BMW-invisible bug.
    losers_with_keeper: list = []
    for pat_key, members in twin_groups.items():
        scored = []
        for m in members:
            scored.append({
                "obj":       m,
                "dc":        _descendant_count(m),
                "anim":      _has_animation(m),
                "bbox_diag": _combined_mesh_bbox_diag(m),
            })
        def _rank(s):
            return (
                1 if s["bbox_diag"] > 0.5 else 0,
                s["dc"],
                1 if s["anim"] else 0,
                -len(s["obj"].name),
            )
        scored.sort(key=_rank, reverse=True)
        winner_s = scored[0]
        loser_ss = scored[1:]
        if not loser_ss:
            continue
        for ls in loser_ss:
            losers_with_keeper.append((ls["obj"], winner_s["obj"]))
        _reason = (
            "most_descendants_with_mesh" if winner_s["bbox_diag"] > 0.5
            else "most_descendants" if winner_s["dc"] > 0
            else "cleaner_name"
        )
        print(
            f"[GLB_DEDUP] pattern={pat_key!r}: keeping {winner_s['obj'].name!r} "
            f"(descendants={winner_s['dc']}, has_anim={winner_s['anim']}, "
            f"bbox_diag={winner_s['bbox_diag']:.2f}m), "
            f"removing {[s['obj'].name for s in loser_ss]}",
            flush=True,
        )
        print(
            f"[DEDUP_HERO] pattern={pat_key!r} kept={winner_s['obj'].name!r} "
            f"(descendants={winner_s['dc']}, has_anim={winner_s['anim']}, "
            f"bbox_diag={winner_s['bbox_diag']:.2f}m) | "
            f"removed={[s['obj'].name for s in loser_ss]} "
            f"(reason={_reason})",
            flush=True,
        )

    if not losers_with_keeper:
        return new_objects

    # ══════════════════════════════════════════════════════════════════
    # V1.3.5 Fix 1 — TRANSACTIONAL DEDUP (mirrors blender_asset_ops.py)
    # ══════════════════════════════════════════════════════════════════
    # Phase 1: GATHER plans (loser, keeper, children + matrices).
    # Phase 2: reparent (parent reassignment only, defer matrix_world).
    # Phase 2b: view_layer.update.
    # Phase 3: restore matrix_world per child.
    # Phase 4: VALIDATE — every child resolves + parent is keeper.
    # Phase 5 (only on validation pass): DELETE losers.
    # On validation failure: ABORT, leave twins, return new_objects
    # unchanged.

    plans = []
    for loser, keeper in losers_with_keeper:
        if loser is None or keeper is None:
            continue
        try:
            entries = []
            for child in list(loser.children):
                try:
                    entries.append((child.name, child.matrix_world.copy()))
                except Exception:
                    continue
            plans.append({
                "loser_name":  loser.name,
                "keeper_name": keeper.name,
                "children":    entries,
            })
        except Exception as e:
            print(f"[GLB_DEDUP] gather failed: {e}", flush=True)

    if not plans:
        return new_objects

    total_reparented = 0
    for p in plans:
        keeper_obj = bpy.data.objects.get(p["keeper_name"])
        if keeper_obj is None:
            continue
        try:
            keeper_inv = keeper_obj.matrix_world.inverted()
        except Exception:
            keeper_inv = None
        for cname, _mw in p["children"]:
            child_obj = bpy.data.objects.get(cname)
            if child_obj is None:
                continue
            try:
                child_obj.parent = keeper_obj
                if keeper_inv is not None:
                    child_obj.matrix_parent_inverse = keeper_inv
                total_reparented += 1
            except Exception as e:
                print(
                    f"[GLB_DEDUP] reparent step (parent=) failed for "
                    f"{cname!r}: {e}",
                    flush=True,
                )

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    matrix_restore_failures = 0
    for p in plans:
        for cname, mw in p["children"]:
            child_obj = bpy.data.objects.get(cname)
            if child_obj is None:
                matrix_restore_failures += 1
                continue
            try:
                child_obj.matrix_world = mw
            except Exception:
                matrix_restore_failures += 1

    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    # VALIDATE
    invalid = []
    for p in plans:
        keeper_obj = bpy.data.objects.get(p["keeper_name"])
        if keeper_obj is None:
            invalid.append(("keeper_missing", p["keeper_name"]))
            continue
        for cname, _mw in p["children"]:
            child_obj = bpy.data.objects.get(cname)
            if child_obj is None:
                invalid.append(("child_missing", cname))
                continue
            if child_obj.parent is not keeper_obj:
                invalid.append(("wrong_parent", cname))

    if invalid:
        print(
            f"[GLB_DEDUP] ABORT: child reference invalidated, "
            f"skipping dedup for this import. {len(invalid)} broken "
            f"reference(s); first few: {invalid[:5]}. "
            f"Twin roots will remain in scene (visually duplicated but "
            f"renderable). matrix_restore_failures={matrix_restore_failures}",
            flush=True,
        )
        return new_objects

    losers_deleted = 0
    for p in plans:
        loser_obj = bpy.data.objects.get(p["loser_name"])
        if loser_obj is None:
            continue
        try:
            bpy.data.objects.remove(loser_obj, do_unlink=True)
            losers_deleted += 1
        except Exception as e:
            print(f"[GLB_DEDUP] delete loser root failed: {e}", flush=True)

    for p in plans:
        print(
            f"[GLB_DEDUP] reparented {len(p['children'])} child(ren) from "
            f"{p['loser_name']!r} to {p['keeper_name']!r} before delete",
            flush=True,
        )

    print(
        f"[GLB_DEDUP] reparent+delete complete: "
        f"reparented={total_reparented} loser_roots_deleted={losers_deleted} "
        f"twin_groups={len(plans)} matrix_restore_failures={matrix_restore_failures}",
        flush=True,
    )
    print(
        f"[GLB_DEDUP] removed {losers_deleted} duplicate object(s) "
        f"({len(plans)} duplicate root(s))",
        flush=True,
    )
    doomed_names = {p["loser_name"] for p in plans}
    return [o for o in new_objects if o.name not in doomed_names]


def _pick_root(new_objects: list):
    """Prefer top-level empties with recognisable names (root,
    GLTF_SceneRootNode, Sketchfab_model). Fall back to the first
    parentless object. Returns None if the caller should create a new
    root empty and reparent."""
    parentless = [o for o in new_objects if o.parent is None]
    if not parentless:
        return None
    for candidate in parentless:
        if (candidate.name or "").lower() in _PREFERRED_ROOT_NAMES:
            return candidate
    # Single unambiguous parentless object → that's our root.
    if len(parentless) == 1:
        return parentless[0]
    # Multiple parentless objects — prefer an empty over a mesh (meshes
    # carry geometry we don't want to move without their siblings).
    for candidate in parentless:
        if getattr(candidate, "type", None) == "EMPTY":
            return candidate
    return parentless[0]


def import_glb_as_hero_group(
    bpy,
    filepath: str | Path,
    target_size: float | None = None,
    asset_type: str = "character",
    ground: bool = True,
    center_xy: bool = True,
    tag_as_hero: bool = True,
) -> list:
    """Import a GLB/GLTF file and scale + position every new object as a
    single hero group.

    Parameters
    ----------
    bpy : module
        The ``bpy`` module, passed in so the caller controls the Blender
        import and this file stays import-safe outside Blender.
    filepath : str or Path
        Path to the .glb or .gltf file.
    target_size : float, optional
        Desired largest world-axis dimension of the combined group. If
        None, derived from ``asset_type``.
    asset_type : str
        Used only to pick a default ``target_size``.
    ground : bool
        Shift the group up so its lowest point sits on z=0.
    center_xy : bool
        Shift the group so the bounding-box centre lands at (0, 0).

    Returns
    -------
    list
        Every newly-imported Blender object (meshes, empties, armatures,
        and the synthesised root if we had to create one). Empty list on
        import failure.
    """
    if target_size is None:
        target_size = _TARGET_SIZE_BY_TYPE.get(
            (asset_type or "").lower(), 1.5
        )

    filepath = str(filepath)
    print(f"[GLB_IMPORT] Loading: {filepath}", flush=True)

    before = {obj.name for obj in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=filepath)
    except Exception as e:
        print(f"[GLB_IMPORT] import_scene.gltf ERROR: {e}", flush=True)
        return []

    after = {obj.name for obj in bpy.data.objects}
    new_names = after - before
    new_objects = [bpy.data.objects[n] for n in new_names if n in bpy.data.objects]

    if not new_objects:
        print("[GLB_IMPORT] No new objects created — empty GLB?", flush=True)
        return []

    # ── 0. Dedup Sketchfab duplicate root hierarchies ─────────────────
    new_objects = _dedup_sketchfab_roots(bpy, new_objects)

    meshes    = [o for o in new_objects if getattr(o, "type", None) == "MESH"]
    empties   = [o for o in new_objects if getattr(o, "type", None) == "EMPTY"]
    armatures = [o for o in new_objects if getattr(o, "type", None) == "ARMATURE"]
    print(
        f"[GLB_IMPORT] Created: {len(meshes)} meshes, "
        f"{len(empties)} empties, {len(armatures)} armatures "
        f"(total {len(new_objects)})",
        flush=True,
    )

    if not meshes:
        print("[GLB_IMPORT] WARNING: no mesh in GLB — returning raw objects", flush=True)
        for obj in new_objects:
            obj.hide_viewport = False
            obj.hide_render = False
        if tag_as_hero:
            _tag_as_hero(new_objects)
        return new_objects

    # ── 1. Initial combined bbox ───────────────────────────────────────
    bbox = _combined_world_bbox(meshes)
    if bbox is None:
        print("[GLB_IMPORT] could not compute bbox — returning unscaled", flush=True)
        if tag_as_hero:
            _tag_as_hero(new_objects)
        return new_objects

    width  = bbox["max_x"] - bbox["min_x"]
    depth  = bbox["max_y"] - bbox["min_y"]
    height = bbox["max_z"] - bbox["min_z"]
    combined_max = max(width, depth, height, 0.001)
    print(
        f"[GLB_IMPORT] Combined bounds: "
        f"{width:.2f} x {depth:.2f} x {height:.2f} m "
        f"(min_z={bbox['min_z']:.2f}, max_dim={combined_max:.2f})",
        flush=True,
    )

    # ── 2. Find / make a single root to transform ─────────────────────
    root = _pick_root(new_objects)
    if root is None:
        # Nothing parentless — synthesise a root empty and re-parent.
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
        root = bpy.context.active_object
        root.name = "Hero_Root"
        for obj in new_objects:
            if obj is root:
                continue
            if obj.parent is None:
                obj.parent = root
        new_objects.append(root)
    else:
        # There might still be OTHER parentless peers (rare — some GLBs
        # produce sibling roots). Re-parent them onto the chosen root so
        # the group scales as one.
        for obj in list(new_objects):
            if obj is root:
                continue
            if obj.parent is None:
                obj.parent = root
    print(f"[GLB_IMPORT] Using root: {root.name}", flush=True)

    # Tag the chosen root so directorial motion can target it directly
    # without guessing. Downstream `_vehicle_drive` prefers this tag over
    # `find_animation_root` heuristics. Only tag as hero root for hero
    # imports — prop/building imports must not hijack hero animation.
    if tag_as_hero:
        try:
            root["is_hero_root"] = True
            print(f"[GLB_IMPORT] tagged is_hero_root on {root.name}", flush=True)
        except Exception:
            pass

    # ── 3. Scale root so combined max_dim becomes target_size ─────────
    scale_factor = float(target_size) / combined_max
    root.scale = (scale_factor, scale_factor, scale_factor)
    bpy.context.view_layer.update()
    print(
        f"[GLB_IMPORT] Applied scale: {scale_factor:.4f} "
        f"({combined_max:.2f}m -> {target_size:.2f}m)",
        flush=True,
    )

    # ══════════════════════════════════════════════════════════════════
    # V1.3.5 Fix 2 — vehicle-aware orientation gate
    # ══════════════════════════════════════════════════════════════════
    # Old heuristic (h < 0.30 * max(w,d)) flipped any low-and-wide
    # subject upside down — including BMWs whose healer metadata had
    # category=character/medium so the vehicle skip didn't catch them.
    #
    # New rule: rotate ONLY when Z is the longest axis of the bbox
    # (model genuinely lying on its side).  When Z is the shortest axis
    # (cars, low animals) we never rotate.  When Y or X is the longest
    # we never rotate (correct orientation).  We also still skip when
    # the asset_type is explicitly vehicle, as belt-and-suspenders.
    _asset_type_lc = (asset_type or "").lower()
    _VEHICLE_TYPES = ("vehicle", "car", "truck", "motorcycle", "bike", "van")
    _is_vehicle_hero = any(v in _asset_type_lc for v in _VEHICLE_TYPES)
    try:
        import math as _m
        bbox_pre = _combined_world_bbox(meshes)
        if bbox_pre is not None:
            _w = bbox_pre["max_x"] - bbox_pre["min_x"]
            _d = bbox_pre["max_y"] - bbox_pre["min_y"]
            _h = bbox_pre["max_z"] - bbox_pre["min_z"]
            _axes = {"X": _w, "Y": _d, "Z": _h}
            _axis_max = max(_axes, key=_axes.get)
            _max_val = _axes[_axis_max]

            if _is_vehicle_hero and _axis_max != "Z":
                # Vehicle, longest axis horizontal — correct orientation,
                # no rotation needed.  (The old explicit "vehicle skip"
                # log retained here for log compatibility.)
                print(
                    f"[GLB_ORIENT] vehicle orientation check: "
                    f"bbox=WxDxH=({_w:.2f}x{_d:.2f}x{_h:.2f}) "
                    f"-> axis_max={_axis_max} -> upright, no rotation needed",
                    flush=True,
                )
            elif _axis_max == "Z" and _max_val > 0.01:
                # Z is the longest axis — model is most likely lying on
                # its side (standing tall against gravity is rare for
                # ground-based subjects we render).
                if _d >= _w:
                    root.rotation_euler.x += _m.radians(-90)
                    print(
                        f"[GLB_ORIENT] Sideways model detected "
                        f"(w={_w:.2f} d={_d:.2f} h={_h:.2f}, axis_max=Z); "
                        f"rotating -90° around X to stand up",
                        flush=True,
                    )
                else:
                    root.rotation_euler.y += _m.radians(90)
                    print(
                        f"[GLB_ORIENT] Sideways model detected "
                        f"(w={_w:.2f} d={_d:.2f} h={_h:.2f}, axis_max=Z); "
                        f"rotating 90° around Y to stand up",
                        flush=True,
                    )
                bpy.context.view_layer.update()
            else:
                # Z is not the longest axis — model is upright (or
                # horizontal-flat like a vehicle).  Don't rotate.
                print(
                    f"[GLB_ORIENT] orientation check: "
                    f"bbox=WxDxH=({_w:.2f}x{_d:.2f}x{_h:.2f}) "
                    f"-> axis_max={_axis_max} -> upright, no rotation needed",
                    flush=True,
                )
    except Exception as _orient_err:
        print(f"[GLB_ORIENT] orientation check skipped: {_orient_err}", flush=True)

    # ── 4. Re-measure, then ground + centre ────────────────────────────
    if ground or center_xy:
        bbox2 = _combined_world_bbox(meshes)
        if bbox2 is not None:
            dx = -(bbox2["min_x"] + bbox2["max_x"]) / 2.0 if center_xy else 0.0
            dy = -(bbox2["min_y"] + bbox2["max_y"]) / 2.0 if center_xy else 0.0
            dz = -bbox2["min_z"] if ground else 0.0
            # Apply relative to the root's existing location (usually 0,0,0).
            root.location.x += dx
            root.location.y += dy
            root.location.z += dz
            bpy.context.view_layer.update()
            print(
                f"[GLB_IMPORT] Grounded root: dz={dz:.3f}  "
                f"centred: dx={dx:.3f}, dy={dy:.3f}",
                flush=True,
            )

    # ── 4b. Anti-burial check — lift if >30% of mesh is below ground ──
    # Some GLB models have their origin in the center of the mesh rather
    # than at the feet. After grounding (min_z → 0), the mesh is correct.
    # But if the mesh's local origin was below the visual center, the
    # bottom half may still be buried. Check and lift if needed.
    if ground:
        try:
            bbox3 = _combined_world_bbox(meshes)
            if bbox3 is not None:
                _total_h = bbox3["max_z"] - bbox3["min_z"]
                _below = abs(min(0.0, bbox3["min_z"]))
                if _total_h > 0.01 and _below > 0.30 * _total_h:
                    # Lift so only ~5% stays below ground (for contact)
                    _lift = _below - 0.05 * _total_h
                    if _lift > 0.001:
                        root.location.z += _lift
                        bpy.context.view_layer.update()
                        print(
                            f"[GLB_IMPORT] Anti-burial lift: +{_lift:.3f}m "
                            f"(was {_below/_total_h*100:.0f}% buried)",
                            flush=True,
                        )
        except Exception as _bury_err:
            print(f"[GLB_IMPORT] Anti-burial check skipped: {_bury_err}", flush=True)

    # ── 5. Visibility ──────────────────────────────────────────────────
    for obj in new_objects:
        obj.hide_viewport = False
        obj.hide_render = False

    # ── 5b. Validation — reject flat cards and placeholder stubs ──────
    valid, reason = validate_hero_mesh(bpy, meshes)
    if not valid:
        print(
            f"[GLB_IMPORT] REJECTED: {reason} — cleaning up {len(new_objects)} objects",
            flush=True,
        )
        for obj in new_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        return None

    # ── 5c. Log dimensions to asset library for curation ────────────────
    try:
        from app.services.asset_logger import log_asset
        import os as _os
        _log_bbox = _combined_world_bbox(meshes)
        _log_dims = None
        _log_verts = sum(
            len(getattr(o, "data", None).vertices)
            for o in meshes
            if getattr(o, "data", None) is not None
            and hasattr(o.data, "vertices")
        )
        if _log_bbox:
            _log_dims = [
                round(_log_bbox["max_x"] - _log_bbox["min_x"], 3),
                round(_log_bbox["max_y"] - _log_bbox["min_y"], 3),
                round(_log_bbox["max_z"] - _log_bbox["min_z"], 3),
            ]
        log_asset(
            subject=asset_type,
            source="import",
            uid=_os.path.basename(filepath),
            name=root.name if root else "unknown",
            file_path=filepath,
            dims=_log_dims,
            verts=_log_verts,
        )
    except Exception:
        pass  # logger not available in Blender subprocess — non-fatal

    # ── 6. Tag as hero so downstream sizing/framing can filter ─────────
    # Callers importing props / buildings / environment assets pass
    # tag_as_hero=False to keep the is_hero namespace clean — otherwise
    # a neon sign or skyscraper gets treated as the focal subject, and
    # the actual hero import is skipped by the HERO_FALLBACK guard.
    if tag_as_hero:
        _tag_as_hero(new_objects)
    else:
        # Mark as prop so downstream filters can still distinguish these
        # from truly-untagged scene geometry.
        for _obj in new_objects:
            try:
                _obj["is_prop"] = True
            except Exception:
                pass
        print(
            f"[GLB_IMPORT] tagged {len(new_objects)} object(s) as is_prop=True "
            f"(non-hero import)",
            flush=True,
        )

    print(
        f"[GLB_IMPORT] Done. {len(new_objects)} objects ready "
        f"({'hero' if tag_as_hero else 'prop'} group).",
        flush=True,
    )
    return new_objects


# ---------------------------------------------------------------------------
# Drop-in wrapper for templates
# ---------------------------------------------------------------------------
#
# Templates currently call ``layout_ops.import_and_place_asset_group``
# which imports via ``import_asset`` and then normalises each root
# independently. That path works for single-object assets but picks the
# wrong "hero" mesh in multi-object GLBs (e.g. the Anamorphic Pelican
# record that ships 16 mesh parts for body + clothing + accessories).
#
# ``import_hero_asset_group`` is a drop-in replacement: same signature,
# same return shape, but when the underlying file is a GLB/GLTF it
# routes through ``import_glb_as_hero_group`` so the whole tree is
# sized + grounded as a unit. For non-GLB assets it falls through to
# the original code path so behaviour is unchanged.


def _glb_path(asset) -> str | None:
    """Return the asset's filesystem path if it's a .glb/.gltf, else None."""
    if not isinstance(asset, dict):
        return None
    raw = asset.get("path") or asset.get("filepath") or asset.get("file")
    if not raw:
        return None
    p = str(raw).lower()
    if p.endswith(".glb") or p.endswith(".gltf"):
        return str(raw)
    return None


def import_hero_asset_group(
    bpy,
    import_asset_func,
    asset,
    target_center: tuple = (0.0, 0.0, 0.0),
    target_size: float = 2.0,
    ground_z: float = 0.0,
    axis_mode: str = "max",
    tag_as_hero: bool = True,
) -> tuple[bool, list]:
    """Drop-in replacement for ``layout_ops.import_and_place_asset_group``
    that is aware of multi-object GLB/GLTF hero assets.

    For .glb/.gltf files: uses ``import_glb_as_hero_group`` to size the
    combined bbox of every mesh to ``target_size`` as a single group,
    then translates the root so the base sits at ``ground_z`` and the
    centre lands at ``target_center`` XY.

    For anything else: delegates to the original
    ``import_and_place_asset_group`` so legacy behaviour is preserved.

    Returns ``(ok, meshes)`` to match the original contract.
    """
    glb_path = _glb_path(asset)

    if glb_path is None:
        # Non-GLB path — keep the legacy behaviour byte-for-byte, but tag
        # the returned meshes so FORCE_FIX/FRAME_FIX/HERO_SCALE can still
        # distinguish them from environment geometry.
        from .layout_ops import import_and_place_asset_group
        ok, meshes = import_and_place_asset_group(
            bpy,
            import_asset_func,
            asset,
            target_center=target_center,
            target_size=target_size,
            ground_z=ground_z,
            axis_mode=axis_mode,
        )
        if ok and meshes:
            if tag_as_hero:
                _tag_as_hero(meshes)
            else:
                for _m in meshes:
                    try:
                        _m["is_prop"] = True
                    except Exception:
                        pass
        return ok, meshes

    # Resolve semantic asset type so _TARGET_SIZE_BY_TYPE and the caller
    # stay in sync when callers forward an explicit target_size.
    asset_type = str(
        asset.get("type")
        or asset.get("asset_type")
        or asset.get("category")
        or "character"
    ).lower()

    print(
        f"[GLB_IMPORT] hero-aware path: {asset.get('name') or asset.get('uid') or '?'} "
        f"({asset_type}) -> target_size={target_size:.2f}, "
        f"target_center={target_center}, ground_z={ground_z}",
        flush=True,
    )

    new_objects = import_glb_as_hero_group(
        bpy,
        glb_path,
        target_size=float(target_size),
        asset_type=asset_type,
        ground=True,
        center_xy=True,
        tag_as_hero=tag_as_hero,
    )
    if not new_objects:
        return False, []

    # ── Forced-hero tagging (Asset Picker UI) ─────────────────────────
    # When the library injector marked this asset dict as _is_forced_hero,
    # stamp is_forced_hero=True on every imported object.  The Hero
    # Tagger's stage-C centroid heuristic checks this tag BEFORE running
    # the closest-to-origin fallback, so a whale lifted by OCEAN_LIFT
    # won't lose to a prop that happens to sit closer to (0,0,0).
    if tag_as_hero and asset.get("_is_forced_hero"):
        _tagged_count = 0
        for _obj in new_objects:
            try:
                _obj["is_forced_hero"] = True
                _tagged_count += 1
            except Exception:
                pass
        if _tagged_count:
            try:
                # Find the root for logging clarity
                _root_names = [o.name for o in new_objects if o.parent is None]
                _root_name = _root_names[0] if _root_names else "(no parentless)"
            except Exception:
                _root_name = "?"
            print(
                f"[GLB_IMPORT] tagged is_forced_hero=True on {_tagged_count} "
                f"object(s) rooted at {_root_name!r} "
                f"(forced_hero_id match: {asset.get('id')!r})",
                flush=True,
            )

    # ── V1 POLISH: import normalization pass ──────────────────────────
    # Runs BEFORE framing / post-translate so orientation fixes, scale
    # overrides, visibility, materials, and lights are all set before
    # downstream stages measure bboxes.  Non-fatal: failures log and
    # the render continues with the pre-normalize state.
    if tag_as_hero:
        try:
            from .import_normalize import normalize_imported_hero
            normalize_imported_hero(bpy, new_objects, asset)
        except Exception as _norm_err:
            print(f"[IMPORT_NORMALIZE] skipped: {_norm_err}", flush=True)

    # ── V1.2 HEAL APPLY: rotation + ground_offset from library entry ──
    # The asset dict carries the library entry (same dict merged into
    # resolved_assets), so any healer-generated orientation fix can be
    # replayed here.  Non-destructive to the source file.
    if tag_as_hero and asset.get("healer_version"):
        try:
            _h_roots = [o for o in new_objects if o.parent is None]
            _rot_fix = asset.get("orientation_fix_rotation_euler")
            _ground_z = asset.get("ground_offset_z")
            if _h_roots and (_rot_fix or _ground_z):
                for _hr in _h_roots:
                    if _rot_fix and isinstance(_rot_fix, (list, tuple)) and len(_rot_fix) >= 3:
                        try:
                            _hr.rotation_euler = (
                                _hr.rotation_euler.x + float(_rot_fix[0]),
                                _hr.rotation_euler.y + float(_rot_fix[1]),
                                _hr.rotation_euler.z + float(_rot_fix[2]),
                            )
                        except Exception:
                            pass
                    if _ground_z is not None:
                        try:
                            _gz = float(_ground_z)
                            if abs(_gz) > 1e-4:
                                _hr.location.z -= _gz
                        except Exception:
                            pass
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass
                print(
                    f"[HEAL_APPLY] hero rotation={_rot_fix} ground_z={_ground_z} "
                    f"(issue={asset.get('orientation_issue')!r})",
                    flush=True,
                )
        except Exception as _heal_err:
            print(f"[HEAL_APPLY] hero heal skipped: {_heal_err}", flush=True)

    # ── V1.3.6 Fix 2: per-asset import_rotation_xyz override ──────────
    # Library entries can carry an "import_rotation_xyz": [x, y, z]
    # (degrees) field to apply a final corrective rotation right after
    # GLB import — used for assets whose source orientation can't be
    # auto-detected (e.g. BMW models authored with non-standard axes).
    if tag_as_hero:
        try:
            _rot_override = asset.get("import_rotation_xyz")
            if _rot_override and isinstance(_rot_override, (list, tuple)) \
                    and len(_rot_override) >= 3:
                import math as _math_iro
                _h_roots_iro = [o for o in new_objects if o.parent is None]
                if _h_roots_iro:
                    _rx = _math_iro.radians(float(_rot_override[0]))
                    _ry = _math_iro.radians(float(_rot_override[1]))
                    _rz = _math_iro.radians(float(_rot_override[2]))
                    for _hr_iro in _h_roots_iro:
                        try:
                            _hr_iro.rotation_euler = (
                                _hr_iro.rotation_euler.x + _rx,
                                _hr_iro.rotation_euler.y + _ry,
                                _hr_iro.rotation_euler.z + _rz,
                            )
                        except Exception:
                            pass
                    try:
                        bpy.context.view_layer.update()
                    except Exception:
                        pass
                    print(
                        f"[ASSET_ORIENT_OVERRIDE] applied rotation_xyz="
                        f"({float(_rot_override[0]):.1f},"
                        f"{float(_rot_override[1]):.1f},"
                        f"{float(_rot_override[2]):.1f}) "
                        f"from library override",
                        flush=True,
                    )
        except Exception as _iro_err:
            print(
                f"[ASSET_ORIENT_OVERRIDE] skipped: {_iro_err}",
                flush=True,
            )

    # import_glb_as_hero_group leaves the root at (0, 0, 0) with its
    # base on z=0. Shift to the caller's requested placement.
    parentless = [o for o in new_objects if o.parent is None]
    root = parentless[0] if parentless else new_objects[0]
    try:
        root.location.x += float(target_center[0])
        root.location.y += float(target_center[1])
        root.location.z += float(ground_z)
        bpy.context.view_layer.update()
    except Exception as e:  # pragma: no cover - defensive
        print(f"[GLB_IMPORT] post-translate failed: {e}", flush=True)

    meshes = [o for o in new_objects if getattr(o, "type", None) == "MESH"]
    return True, meshes


# ---------------------------------------------------------------------------
# Fallback: import manifest['hero_asset_path'] if the template missed it
# ---------------------------------------------------------------------------
#
# Several templates only read a narrow slice of ``resolved_assets`` — e.g.
# ``scenic_landscape`` imports ``environments[]`` only. When a prompt like
# "pelican on a rock" routes to scenic_landscape, the pelican lands in the
# ``characters`` / ``animals`` bucket of ``resolved_assets`` and is never
# imported; the render is just the mountain.
#
# ``import_hero_asset_path_fallback`` is a safety net: if ``hero_asset_path``
# is set, the file exists, and the template didn't already import it, pull
# it into the scene. Downstream FORCE_FIX handles sizing / grounding.

def import_hero_asset_path_fallback(
    bpy,
    manifest: dict,
    target_center: tuple = (0.0, 0.0, 0.0),
    target_size: float | None = None,
    ground_z: float = 0.0,
    already_imported_paths=None,
) -> list:
    """Import ``manifest['hero_asset_path']`` if it wasn't picked up by the
    template's own resolve-import pass.

    Parameters
    ----------
    already_imported_paths : iterable of str | None
        Paths the template already imported. If the hero path matches any
        of these (case-insensitive, slash-normalised), we skip to avoid
        double-importing the same asset.

    Returns
    -------
    list
        Newly-imported MESH objects. Empty list when the hero was already
        in the scene, the file doesn't exist, or the import failed.
    """
    import os

    hero_path = str(manifest.get("hero_asset_path") or "").strip()
    if not hero_path:
        return []

    # ── AGGRESSIVE DEDUP (must run FIRST, before any path comparison) ──
    # If ANY object in the scene is already tagged is_hero=True, the
    # template has already imported the hero. Every template calls
    # import_hero_asset_group() which tags with is_hero BEFORE this
    # fallback runs. So if is_hero exists, a second import would create
    # a duplicate (Ferrari double wheels, doubled lizard, cat overlay).
    # This single check is bulletproof regardless of path normalisation
    # differences, relative-vs-absolute paths, or bucket mismatches.
    try:
        existing_hero_meshes = [
            obj for obj in bpy.data.objects
            if obj.type == 'MESH' and obj.get("is_hero", False)
        ]
        if existing_hero_meshes:
            print(
                f"[HERO_FALLBACK] hero already imported by template "
                f"({len(existing_hero_meshes)} hero meshes exist), "
                f"skipping duplicate: {hero_path}",
                flush=True,
            )
            return []
    except Exception:
        pass  # bpy not available (unit test) — skip this check

    if not os.path.exists(hero_path):
        print(
            f"[HERO_FALLBACK] hero_asset_path not on disk: {hero_path}",
            flush=True,
        )
        return []

    # Path-based dedup as a secondary safety net.
    nhp = os.path.normcase(os.path.normpath(hero_path))
    if already_imported_paths:
        already_norm = {
            os.path.normcase(os.path.normpath(str(p)))
            for p in already_imported_paths
            if p
        }
        if nhp in already_norm:
            print(
                f"[HERO_FALLBACK] hero path already imported by template, "
                f"skipping duplicate: {hero_path}",
                flush=True,
            )
            return []

    hero_type = str(manifest.get("hero_asset_type") or "").lower()
    if target_size is None:
        target_size = _TARGET_SIZE_BY_TYPE.get(hero_type, 1.5)

    print(
        f"[HERO_FALLBACK] importing dynamic hero: {hero_path} "
        f"type={hero_type!r} target_size={target_size} center={target_center}",
        flush=True,
    )

    _ext = hero_path.lower().rsplit(".", 1)[-1] if "." in hero_path else ""
    try:
        if _ext in ("glb", "gltf"):
            # Try primary path, then iterate hero_candidates on validation
            # failure (import_glb_as_hero_group returns None for flat
            # cards / placeholder stubs).
            _paths_to_try = [hero_path] + list(manifest.get("hero_candidates") or [])
            new_objs = None
            for _try_path in _paths_to_try:
                if not _try_path or not os.path.exists(str(_try_path)):
                    continue
                new_objs = import_glb_as_hero_group(
                    bpy, str(_try_path),
                    target_size=float(target_size),
                    asset_type=hero_type or "character",
                    ground=True,
                    center_xy=True,
                )
                if new_objs:
                    if _try_path != hero_path:
                        print(
                            f"[HERO_FALLBACK] primary rejected, using candidate: {_try_path}",
                            flush=True,
                        )
                    break
                print(
                    f"[HERO_FALLBACK] candidate rejected by validation: {_try_path}",
                    flush=True,
                )

            if not new_objs:
                return []
            # Translate the root to the caller's target_center + ground_z.
            parentless = [o for o in new_objs if o.parent is None]
            if parentless:
                root = parentless[0]
                try:
                    root.location.x += float(target_center[0])
                    root.location.y += float(target_center[1])
                    root.location.z += float(ground_z)
                    bpy.context.view_layer.update()
                except Exception as e:  # pragma: no cover
                    print(f"[HERO_FALLBACK] post-translate failed: {e}", flush=True)
            return [o for o in new_objs if getattr(o, "type", None) == "MESH"]

        # Non-GLB raw import — FORCE_FIX downstream will size + ground.
        before = {o.name for o in bpy.data.objects}
        if _ext == "fbx":
            bpy.ops.import_scene.fbx(filepath=hero_path)
        elif _ext == "obj":
            try:
                bpy.ops.wm.obj_import(filepath=hero_path)  # Blender 4+
            except AttributeError:
                bpy.ops.import_scene.obj(filepath=hero_path)  # 3.x
        elif _ext == "blend":
            with bpy.data.libraries.load(hero_path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            for obj in dst.objects:
                if obj is not None:
                    bpy.context.collection.objects.link(obj)
            # Dedup Sketchfab duplicates from the .blend
            _after_blend = {o.name for o in bpy.data.objects}
            _blend_new = [
                bpy.data.objects[n] for n in (_after_blend - before)
                if n in bpy.data.objects
            ]
            _dedup_sketchfab_roots(bpy, _blend_new)
        else:
            print(
                f"[HERO_FALLBACK] unsupported extension, skipping: {hero_path}",
                flush=True,
            )
            return []
        after = {o.name for o in bpy.data.objects}
        new_names = after - before
        new_meshes = [
            bpy.data.objects[n] for n in new_names
            if n in bpy.data.objects
            and getattr(bpy.data.objects[n], "type", None) == "MESH"
        ]
        # Also tag non-mesh siblings (empties, armatures) so any downstream
        # tag-based lookup sees the full hero group.
        new_siblings = [
            bpy.data.objects[n] for n in new_names
            if n in bpy.data.objects
        ]
        _tag_as_hero(new_siblings)
        print(
            f"[HERO_FALLBACK] imported {len(new_meshes)} new mesh(es) from {hero_path}",
            flush=True,
        )
        return new_meshes
    except Exception as e:
        print(f"[HERO_FALLBACK] import failed: {e}", flush=True)
        return []
