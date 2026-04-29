from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class BlendMetadata:
    collections: list[str]
    objects: list[str]
    armature_hints: list[str]
    actions: list[str]


@dataclass
class ImportedProbe:
    all_roots: list
    meshes: list
    armatures: list


def _resolve_asset_path(asset: dict) -> Path:
    path = asset.get("path")
    if not path:
        raise ValueError("Asset is missing path")
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _blend_dir(blend_path: Path, kind: str) -> str:
    return f"{blend_path.as_posix()}/{kind}/"


def inspect_blend_metadata(bpy, blend_path: Path) -> BlendMetadata:
    collections: list[str] = []
    objects: list[str] = []
    actions: list[str] = []
    try:
        with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
            collections = list(data_from.collections)
            objects = list(data_from.objects)
            actions = list(getattr(data_from, "actions", []))
    except Exception as e:
        print(f"DEBUG inspect_blend_metadata failed: {blend_path} :: {e}", flush=True)

    armature_hints = [name for name in objects if "armature" in name.lower() or "rig" in name.lower()]
    return BlendMetadata(
        collections=collections,
        objects=objects,
        armature_hints=armature_hints,
        actions=actions,
    )


def _mesh_descendants(root_objs) -> list:
    result = []
    seen = set()

    def walk(obj):
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        if getattr(obj, "type", None) == "MESH":
            result.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    for obj in root_objs:
        walk(obj)
    return result


def _armature_descendants(root_objs) -> list:
    result = []
    seen = set()

    def walk(obj):
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        if getattr(obj, "type", None) == "ARMATURE":
            result.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    for obj in root_objs:
        walk(obj)
    return result


def probe_imported_objects(bpy, before_names: set[str]) -> ImportedProbe:
    after_scene = [obj for obj in bpy.context.scene.objects if obj.name not in before_names]
    all_roots = [obj for obj in after_scene if obj.parent is None]
    meshes = _mesh_descendants(all_roots)
    armatures = _armature_descendants(all_roots)
    return ImportedProbe(all_roots=all_roots, meshes=meshes, armatures=armatures)


def _dedup_blend_roots(bpy, before_scene: set[str]) -> None:
    """Remove duplicate Sketchfab scene hierarchies from a .blend import.

    Many Sketchfab .blend exports contain TWO copies of the entire model
    under separate root empties with auto-suffixed names
    (``Sketchfab_model`` + ``Sketchfab_model_0``, ``root`` + ``root_1``,
    ``GLTF_SceneRootNode`` + ``GLTF_SceneRootNode_2``).  Importing such a
    file loads both copies and the renderer shows them overlaid — the
    "double car" / "ghost overlay" bug.

    The detection is NAME-PATTERN based (not parent-based), because
    ``bpy.data.libraries.load`` may not preserve parent relationships
    consistently across Blender versions.  We scan all newly-imported
    objects whose name matches one of the known twin patterns, group by
    pattern, and delete the losing hierarchies.
    """
    import re

    after_names = {obj.name for obj in bpy.data.objects}
    new_names = after_names - before_scene
    # Entry beacon so the trace always shows the dedup ran, even for
    # clean imports with no twins (those return early below).
    print(
        f"[BLEND_DEDUP] entry: {len(new_names)} new object(s) from .blend import",
        flush=True,
    )
    if not new_names:
        return

    new_objects = [bpy.data.objects[n] for n in new_names if n in bpy.data.objects]
    if len(new_objects) < 2:
        return

    # ── Twin name patterns (Sketchfab/glTF auto-suffixed duplicates) ──
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

    # Group every candidate by its matched pattern key
    groups: dict[str, list] = {}
    for obj in new_objects:
        key = _matches_pattern(obj)
        if key is not None:
            groups.setdefault(key, []).append(obj)

    # Only keep groups that have actual twins
    twin_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not twin_groups:
        return

    # Diagnostic: dump every twin-pattern hit for visibility
    print(
        f"[BLEND_DEDUP] scanning {len(new_objects)} imported objects, "
        f"found {len(twin_groups)} twin group(s)",
        flush=True,
    )
    for pat_key, members in twin_groups.items():
        print(
            f"[BLEND_DEDUP]   pattern={pat_key!r} -> "
            f"{[m.name for m in members]}",
            flush=True,
        )

    # ── Scoring helpers ───────────────────────────────────────────────
    def _descendant_count(obj) -> int:
        count = 0
        for child in obj.children:
            count += 1 + _descendant_count(child)
        return count

    def _has_animation(obj) -> bool:
        """Check for animation data WITH actual keyframes (empty Actions don't count)."""
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
        """Diagonal of the combined world-space bbox of this obj + all mesh descendants."""
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

    # ── Choose winner per twin group ──────────────────────────────────
    # V1.3.3 Fix B: track (loser_root, keeper_root) pairs so we can
    # REPARENT children before deleting losers, instead of recursively
    # deleting losing twins' children too (the BMW-invisible bug — a
    # 174-mesh BMW had its panels split across two twin roots; the old
    # code dropped one twin and recursively deleted ~half the panels).
    losers_with_keeper: list = []  # list of (loser_obj, keeper_obj)
    for pat_key, members in twin_groups.items():
        scored = []
        for m in members:
            scored.append({
                "obj":        m,
                "dc":         _descendant_count(m),
                "anim":       _has_animation(m),
                "bbox_diag":  _combined_mesh_bbox_diag(m),
            })
        # Primary: bbox_diag > 0.5m (real mesh content).
        # Tie-break: descendant count desc, then has_anim.
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
            f"[BLEND_DEDUP] pattern={pat_key!r}: keeping {winner_s['obj'].name!r} "
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
        return

    # ══════════════════════════════════════════════════════════════════
    # V1.3.5 Fix 1 — TRANSACTIONAL DEDUP
    # ══════════════════════════════════════════════════════════════════
    # The V1.3.3 reparenting wrote child.parent + matrix_parent_inverse
    # + matrix_world back-to-back per child.  On some Blender builds
    # (notably the .blend library-load path) the triple-write
    # invalidates the Object struct mid-loop, the next loop iteration
    # then crashes the builder with `StructRNA of type Object has been
    # removed`, and the entire car_hero template silently falls back
    # to a placeholder scene with no real BMW.
    #
    # New flow: GATHER → REPARENT → SETTLE → VALIDATE → DELETE.
    # On validation failure we ABORT dedup entirely and leave both
    # twin roots in place — the resulting scene has visual duplication
    # but renders correctly.  Better than a placeholder fallback.

    # Phase 1: GATHER — capture every loser's direct children + their
    # world matrices.  Names are captured too so later phases can
    # re-resolve via bpy.data.objects.get(name) if the proxy dies.
    plans = []  # list of dicts: {loser_name, keeper_name, children: [(name, matrix_world)]}
    for loser, keeper in losers_with_keeper:
        if loser is None or keeper is None:
            continue
        try:
            entries = []
            for child in list(loser.children):
                try:
                    entries.append((child.name, child.matrix_world.copy()))
                except Exception:
                    # Skip a child whose matrix is already broken
                    continue
            plans.append({
                "loser_name":   loser.name,
                "keeper_name":  keeper.name,
                "children":     entries,
            })
        except Exception as e:
            print(
                f"[BLEND_DEDUP] gather failed for loser={getattr(loser,'name','?')!r}: {e}",
                flush=True,
            )

    if not plans:
        return

    # Phase 2: REPARENT — change parent only, defer matrix restoration.
    # By the API contract Blender keeps the child object live as long as
    # we re-resolve via bpy.data.objects every step.
    total_reparented = 0
    for p in plans:
        keeper_obj = bpy.data.objects.get(p["keeper_name"])
        if keeper_obj is None:
            continue
        keeper_inv = None
        try:
            keeper_inv = keeper_obj.matrix_world.inverted()
        except Exception:
            keeper_inv = None
        for cname, mw in p["children"]:
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
                    f"[BLEND_DEDUP] reparent step (parent= ) failed for "
                    f"{cname!r}: {e}",
                    flush=True,
                )

    # Phase 2b: settle — view_layer.update so Blender refreshes
    # dependency graph before we touch matrix_world again.
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    # Phase 3: restore matrix_world per child so world position stays.
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

    # Phase 4: VALIDATE — every child must still resolve and have the
    # expected keeper as its parent.  If any are broken, ABORT delete.
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
            f"[BLEND_DEDUP] ABORT: child reference invalidated, "
            f"skipping dedup for this import. {len(invalid)} broken "
            f"reference(s); first few: {invalid[:5]}. "
            f"Twin roots will remain in scene (visually duplicated but "
            f"renderable). matrix_restore_failures={matrix_restore_failures}",
            flush=True,
        )
        # Don't delete losers; both twins stay
        return

    # Phase 5: DELETE — only now (after validation) remove loser roots.
    losers_deleted = 0
    for p in plans:
        loser_obj = bpy.data.objects.get(p["loser_name"])
        if loser_obj is None:
            continue
        try:
            bpy.data.objects.remove(loser_obj, do_unlink=True)
            losers_deleted += 1
        except Exception as e:
            print(f"[BLEND_DEDUP] delete loser root failed: {e}", flush=True)

    for p in plans:
        print(
            f"[BLEND_DEDUP] reparented {len(p['children'])} child(ren) from "
            f"{p['loser_name']!r} to {p['keeper_name']!r} before delete",
            flush=True,
        )

    print(
        f"[BLEND_DEDUP] reparent+delete complete: "
        f"reparented={total_reparented} loser_roots_deleted={losers_deleted} "
        f"twin_groups={len(plans)} matrix_restore_failures={matrix_restore_failures}",
        flush=True,
    )
    # Backwards-compat
    print(
        f"[BLEND_DEDUP] removed {losers_deleted} duplicate object(s) "
        f"({len(plans)} twin root(s))",
        flush=True,
    )

    doomed: set[str] = {p["loser_name"] for p in plans}

    # ── Tag surviving hero roots for downstream animation targeting ────
    # After dedup, any remaining parentless root that's tagged `is_hero`
    # (by the caller) OR has "sketchfab_model" / "root" / "gltf_scene" in
    # its base name is considered the hero root.  `_vehicle_drive` and
    # other directorial motion profiles prefer this tag over heuristics.
    _HERO_ROOT_HINTS = ("sketchfab_model", "root", "gltf_scenerootnode", "scene")
    for obj in bpy.data.objects:
        if obj.parent is not None or obj.name in doomed:
            continue
        _lname = obj.name.lower()
        _is_sketchfab_root = any(h in _lname for h in _HERO_ROOT_HINTS)
        if _is_sketchfab_root or obj.get("is_hero", False):
            try:
                obj["is_hero_root"] = True
            except Exception:
                pass


def _log_imported_objects(bpy, before_scene: set[str], label: str) -> None:
    """
    Walk bpy.data.objects, diff against before_scene, and loudly log what
    specifically appeared (type + verts/faces/bones). Matches the log
    format used by asset_import.import_hero_asset so templates and the
    asset-ops path produce consistent telemetry.
    """
    try:
        after_scene = {obj.name for obj in bpy.data.objects}
        new_names = after_scene - before_scene
        if not new_names:
            print(f"[IMPORT] {label}: no new objects appeared in bpy.data.objects", flush=True)
            return
        print(f"[IMPORT] {label}: successfully imported {len(new_names)} object(s):", flush=True)
        for name in sorted(new_names):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            extra = ""
            try:
                if obj.type == "MESH" and obj.data is not None:
                    extra = f" (verts={len(obj.data.vertices)}, faces={len(obj.data.polygons)})"
                elif obj.type == "ARMATURE" and obj.data is not None:
                    extra = f" (bones={len(obj.data.bones)})"
            except Exception:
                pass
            print(f"[IMPORT]   - {obj.name!r} type={obj.type}{extra}", flush=True)
    except Exception as e:
        print(f"[IMPORT] _log_imported_objects failed ({label}): {e}", flush=True)


def _append_collection_and_link(bpy, blend_path: Path, collection_name: str) -> bool:
    directory = _blend_dir(blend_path, "Collection")
    filepath = directory + collection_name
    try:
        before_collections = set(bpy.data.collections.keys())
        bpy.ops.wm.append(filepath=filepath, filename=collection_name, directory=directory)

        new_collections = [c for c in bpy.data.collections if c.name not in before_collections]
        for col in new_collections:
            if col.name not in bpy.context.scene.collection.children.keys():
                try:
                    bpy.context.scene.collection.children.link(col)
                    print(f"DEBUG linked appended collection into scene: {col.name}", flush=True)
                except Exception as e:
                    print(f"DEBUG linking collection failed: {col.name} :: {e}", flush=True)
        return True
    except Exception as e:
        print(f"DEBUG append collection failed: {blend_path} :: {collection_name} :: {e}", flush=True)
        return False


def _append_object(bpy, blend_path: Path, object_name: str) -> bool:
    directory = _blend_dir(blend_path, "Object")
    filepath = directory + object_name
    try:
        bpy.ops.wm.append(filepath=filepath, filename=object_name, directory=directory)
        return True
    except Exception as e:
        print(f"DEBUG append object failed: {blend_path} :: {object_name} :: {e}", flush=True)
        return False


def _load_all_objects_and_link(bpy, blend_path: Path) -> bool:
    """
    Robust path for .blend files that have no useful collections.
    Load all objects from the library and link them into the active scene.
    """
    try:
        with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
            data_to.objects = list(data_from.objects)

        loaded = [obj for obj in data_to.objects if obj is not None]
        if not loaded:
            print(f"DEBUG no objects loaded from blend: {blend_path}", flush=True)
            return False

        for obj in loaded:
            try:
                if obj.name not in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.link(obj)
            except Exception:
                try:
                    bpy.context.scene.collection.objects.link(obj)
                except Exception as e:
                    print(f"DEBUG object link failed: {obj.name} :: {e}", flush=True)

        bpy.context.view_layer.update()
        print(f"DEBUG linked all objects from blend: {blend_path} count={len(loaded)}", flush=True)
        return True
    except Exception as e:
        print(f"DEBUG load_all_objects failed: {blend_path} :: {e}", flush=True)
        return False


def _apply_import_rotation_override(bpy, asset: dict, before_scene: set) -> None:
    """V1.3.6 Fix 2: apply per-asset import_rotation_xyz override (degrees)
    on the parentless roots that appeared after import. Library-data driven
    corrective rotation for assets authored with non-standard axes.
    """
    try:
        rot = asset.get("import_rotation_xyz")
        if not (rot and isinstance(rot, (list, tuple)) and len(rot) >= 3):
            return
        import math as _m_iro
        rx = _m_iro.radians(float(rot[0]))
        ry = _m_iro.radians(float(rot[1]))
        rz = _m_iro.radians(float(rot[2]))
        new_roots = [
            o for o in bpy.data.objects
            if o.name not in before_scene and o.parent is None
        ]
        if not new_roots:
            return
        for hr in new_roots:
            try:
                hr.rotation_euler = (
                    hr.rotation_euler.x + rx,
                    hr.rotation_euler.y + ry,
                    hr.rotation_euler.z + rz,
                )
            except Exception:
                pass
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        print(
            f"[ASSET_ORIENT_OVERRIDE] applied rotation_xyz="
            f"({float(rot[0]):.1f},{float(rot[1]):.1f},{float(rot[2]):.1f}) "
            f"from library override (.blend path, {len(new_roots)} root(s))",
            flush=True,
        )
    except Exception as _e:
        print(f"[ASSET_ORIENT_OVERRIDE] skipped: {_e}", flush=True)


def import_asset(bpy, asset: dict) -> bool:
    resolved_path = _resolve_asset_path(asset)
    if not resolved_path.exists():
        print(f"[IMPORT] missing asset path: {resolved_path}", flush=True)
        return False

    # Pre-flight verification: catch ZIPs / HTML / empties before Blender
    # produces a noisier, less actionable error.
    try:
        from .asset_import import verify_asset_file
        ok, msg = verify_asset_file(str(resolved_path))
        print(f"[IMPORT] verification: {msg}", flush=True)
        if not ok:
            return False
    except ImportError:
        pass

    print(f"[IMPORT] resolved_path={resolved_path}", flush=True)
    suffix = resolved_path.suffix.lower()

    # Track objects so we can loudly report what actually got imported.
    before_scene = {obj.name for obj in bpy.data.objects}

    if suffix == ".blend":
        preferred_kind = str(asset.get("blend_kind", "collection")).lower()
        preferred_name = str(asset.get("blend_name", "")).strip()

        # Diagnostic: confirm the file is actually on disk and report its
        # header so zstd-compressed blends are obvious in the log.
        try:
            print(f"[IMPORT] .blend path: {resolved_path}", flush=True)
            print(f"[IMPORT] .blend file exists: {resolved_path.exists()}", flush=True)
            if resolved_path.exists():
                _blend_size = resolved_path.stat().st_size
                print(f"[IMPORT] .blend file size: {_blend_size}", flush=True)
                with open(resolved_path, "rb") as _fh:
                    _blend_head = _fh.read(8)
                if _blend_head[:7] == b"BLENDER":
                    _kind = "uncompressed"
                elif _blend_head[:2] == b"\x1f\x8b":
                    _kind = "gzip"
                elif _blend_head[:4] == b"\x28\xb5\x2f\xfd":
                    _kind = "zstd"
                else:
                    _kind = f"unknown ({_blend_head.hex()})"
                print(f"[IMPORT] .blend header kind: {_kind}", flush=True)
        except Exception as _e:
            print(f"[IMPORT] .blend diagnostic read failed: {_e}", flush=True)

        meta = inspect_blend_metadata(bpy, resolved_path)
        print(f"DEBUG blend catalog collections={meta.collections} objects_sample={meta.objects[:12]}", flush=True)

        before_names = {obj.name for obj in bpy.context.scene.objects}

        # 1) preferred collection
        if preferred_kind == "collection" and preferred_name and preferred_name in meta.collections:
            if _append_collection_and_link(bpy, resolved_path, preferred_name):
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots or probe.meshes:
                    _log_imported_objects(bpy, before_scene, f"blend preferred_collection={preferred_name!r}")
                    _dedup_blend_roots(bpy, before_scene)
                    _apply_import_rotation_override(bpy, asset, before_scene)
                    return True

        # 2) first collection
        for name in meta.collections:
            before_names = {obj.name for obj in bpy.context.scene.objects}
            if _append_collection_and_link(bpy, resolved_path, name):
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots or probe.meshes:
                    _log_imported_objects(bpy, before_scene, f"blend collection={name!r}")
                    _dedup_blend_roots(bpy, before_scene)
                    _apply_import_rotation_override(bpy, asset, before_scene)
                    return True

        # 3) preferred object
        if preferred_name and preferred_name in meta.objects:
            before_names = {obj.name for obj in bpy.context.scene.objects}
            if _append_object(bpy, resolved_path, preferred_name):
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots or probe.meshes:
                    _log_imported_objects(bpy, before_scene, f"blend preferred_object={preferred_name!r}")
                    _dedup_blend_roots(bpy, before_scene)
                    _apply_import_rotation_override(bpy, asset, before_scene)
                    return True

        # 4) If no collections exist, load all objects from the blend
        if not meta.collections and meta.objects:
            before_names = {obj.name for obj in bpy.context.scene.objects}
            if _load_all_objects_and_link(bpy, resolved_path):
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots or probe.meshes:
                    _log_imported_objects(bpy, before_scene, "blend load_all_objects")
                    _dedup_blend_roots(bpy, before_scene)
                    _apply_import_rotation_override(bpy, asset, before_scene)
                    return True

        # 5) last resort: try first few objects individually
        for name in meta.objects[:25]:
            before_names = {obj.name for obj in bpy.context.scene.objects}
            if _append_object(bpy, resolved_path, name):
                probe = probe_imported_objects(bpy, before_names)
                if probe.all_roots or probe.meshes:
                    _log_imported_objects(bpy, before_scene, f"blend object={name!r}")
                    _dedup_blend_roots(bpy, before_scene)
                    _apply_import_rotation_override(bpy, asset, before_scene)
                    return True

        # Nothing stuck — report what's actually in the scene so the log
        # shows whether Blender silently loaded objects we aren't seeing.
        _mesh_names = [o.name for o in bpy.data.objects if o.type == "MESH"]
        print(
            f"[IMPORT] Objects in scene after .blend import attempt: {_mesh_names}",
            flush=True,
        )
        print(f"DEBUG import_asset failed for blend: {resolved_path}", flush=True)
        return False

    try:
        if suffix in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(resolved_path))
            _log_imported_objects(bpy, before_scene, f"gltf {resolved_path.name}")
            return True
        elif suffix == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(resolved_path))
            _log_imported_objects(bpy, before_scene, f"fbx {resolved_path.name}")
            return True
        elif suffix == ".obj":
            try:
                bpy.ops.wm.obj_import(filepath=str(resolved_path))
            except Exception:
                bpy.ops.import_scene.obj(filepath=str(resolved_path))
            _log_imported_objects(bpy, before_scene, f"obj {resolved_path.name}")
            return True
    except Exception as e:
        print(f"[IMPORT] generic import failed: {resolved_path} :: {e}", flush=True)
        return False

    print(f"DEBUG unsupported asset format: {resolved_path}", flush=True)
    return False
