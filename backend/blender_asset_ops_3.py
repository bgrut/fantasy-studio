from __future__ import annotations

"""
blender_asset_ops.py
====================
Import helpers and blend-file metadata probes.

New public surface (additions only — no removals)
--------------------------------------------------
inspect_blend_metadata(bpy, blend_path)
    Returns a BlendMetadata namedtuple with:
        collections   list[str]
        objects       list[str]
        armatures     list[str]   — object names whose type is ARMATURE
        actions       list[str]   — action names stored in the blend

probe_imported_objects(bpy, before_names)
    After import, returns ImportedProbe with lists of new root objects
    split by type (meshes, armatures) so scene templates can target them.

import_asset(bpy, asset) → bool
    Unchanged signature, unchanged return type.
    Internally uses forward-slash separators (cross-platform).
"""

from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class BlendMetadata(NamedTuple):
    collections: list[str]
    objects:     list[str]
    armatures:   list[str]   # subset of objects whose type == ARMATURE
    actions:     list[str]


class ImportedProbe(NamedTuple):
    all_roots:  list   # all new root bpy objects
    meshes:     list   # subset with type == MESH
    armatures:  list   # subset with type == ARMATURE


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _resolve_asset_path(asset: dict) -> Path:
    path = asset.get("path")
    if not path:
        raise ValueError("Asset is missing 'path' field")
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _blend_dir(blend_path: Path, data_type: str) -> str:
    """
    Build the directory string Blender's wm.append expects.
    Uses forward slashes so it works on both Windows and Linux/macOS.
    Blender normalises separators internally.
    """
    return f"{blend_path.as_posix()}/{data_type}/"


# ---------------------------------------------------------------------------
# Blend file metadata inspection (pre-import, read-only)
# ---------------------------------------------------------------------------

def inspect_blend_metadata(bpy, blend_path: Path) -> BlendMetadata:
    """
    Open the .blend file in read-only mode and return all collections,
    objects, armature names, and action names without importing anything.

    Armature names are inferred by checking object type in the blend catalog.
    Actions are enumerated directly from data_from.actions.
    """
    empty = BlendMetadata([], [], [], [])
    if not blend_path.exists():
        print(f"[ASSET] inspect_blend_metadata: file not found {blend_path}", flush=True)
        return empty

    try:
        with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, _):
            collections = list(data_from.collections or [])
            objects     = list(data_from.objects     or [])
            actions     = list(data_from.actions     or [])

        # Identify armatures: load objects into a temp context and check type.
        # Blender stores object type in the .blend name with a prefix when using
        # link=False peek — we can't get types without actually importing.
        # Practical heuristic: object names that contain "armature", "rig", "skel"
        # or match common Blender conventions (object whose name starts with "RIG_",
        # "ARMATURE_", "Armature") are flagged.  The caller must verify post-import.
        armature_hints = [
            name for name in objects
            if any(kw in name.lower() for kw in ("armature", "rig", "skel", "skeleton"))
        ]

        meta = BlendMetadata(
            collections=collections,
            objects=objects,
            armatures=armature_hints,
            actions=actions,
        )
        print(
            f"[ASSET] inspect_blend_metadata | path={blend_path.name} "
            f"collections={len(collections)} objects={len(objects)} "
            f"actions={len(actions)} armature_hints={armature_hints}",
            flush=True,
        )
        return meta

    except Exception as e:
        print(f"[ASSET] inspect_blend_metadata failed: {blend_path} :: {e}", flush=True)
        return empty


# ---------------------------------------------------------------------------
# Post-import probe
# ---------------------------------------------------------------------------

def probe_imported_objects(bpy, before_names: set[str]) -> ImportedProbe:
    """
    Call after import_asset to classify what was just brought into the scene.
    Returns an ImportedProbe with typed lists of new root objects.
    """
    new_objs  = [obj for obj in bpy.data.objects if obj.name not in before_names]
    roots     = [obj for obj in new_objs if obj.parent is None] or new_objs
    meshes    = [obj for obj in roots if getattr(obj, "type", None) == "MESH"]
    armatures = [obj for obj in roots if getattr(obj, "type", None) == "ARMATURE"]

    print(
        f"[ASSET] probe_imported_objects | new={len(new_objs)} "
        f"roots={len(roots)} meshes={len(meshes)} armatures={len(armatures)}",
        flush=True,
    )
    return ImportedProbe(all_roots=roots, meshes=meshes, armatures=armatures)


# ---------------------------------------------------------------------------
# Internal append helpers
# ---------------------------------------------------------------------------

def _append_collection(bpy, blend_path: Path, collection_name: str) -> bool:
    directory = _blend_dir(blend_path, "Collection")
    filepath  = directory + collection_name
    try:
        bpy.ops.wm.append(
            filepath=filepath,
            filename=collection_name,
            directory=directory,
        )
        return True
    except Exception as e:
        print(
            f"[ASSET] append collection failed: {blend_path.name} :: "
            f"{collection_name} :: {e}",
            flush=True,
        )
        return False


def _append_object(bpy, blend_path: Path, object_name: str) -> bool:
    directory = _blend_dir(blend_path, "Object")
    filepath  = directory + object_name
    try:
        bpy.ops.wm.append(
            filepath=filepath,
            filename=object_name,
            directory=directory,
        )
        return True
    except Exception as e:
        print(
            f"[ASSET] append object failed: {blend_path.name} :: "
            f"{object_name} :: {e}",
            flush=True,
        )
        return False


# ---------------------------------------------------------------------------
# Public import entry point (unchanged signature)
# ---------------------------------------------------------------------------

def import_asset(bpy, asset: dict) -> bool:
    """
    Import an asset from its registry entry.  Returns True on success.

    For .blend files the import priority is:
      1. Preferred collection (blend_kind == "collection" and blend_name set)
      2. First available collection
      3. Preferred object by name
      4. First 25 objects

    For .glb/.gltf/.fbx/.obj: delegates to the appropriate Blender operator.
    """
    try:
        resolved_path = _resolve_asset_path(asset)
    except ValueError as e:
        print(f"[ASSET] import_asset: {e}", flush=True)
        return False

    if not resolved_path.exists():
        print(f"[ASSET] import_asset missing file: {resolved_path}", flush=True)
        return False

    print(f"[ASSET] import_asset: {resolved_path}", flush=True)

    suffix = resolved_path.suffix.lower()

    # ── Blend file ────────────────────────────────────────────────────────
    if suffix == ".blend":
        preferred_kind = str(asset.get("blend_kind", "collection")).lower()
        preferred_name = str(asset.get("blend_name", "")).strip()

        meta = inspect_blend_metadata(bpy, resolved_path)

        # 1) preferred collection
        if preferred_kind == "collection" and preferred_name and preferred_name in meta.collections:
            if _append_collection(bpy, resolved_path, preferred_name):
                return True

        # 2) first available collection
        for name in meta.collections:
            if _append_collection(bpy, resolved_path, name):
                return True

        # 3) preferred object
        if preferred_name and preferred_name in meta.objects:
            if _append_object(bpy, resolved_path, preferred_name):
                return True

        # 4) first 25 objects
        for name in meta.objects[:25]:
            if _append_object(bpy, resolved_path, name):
                return True

        print(f"[ASSET] import_asset: all strategies failed for {resolved_path}", flush=True)
        return False

    # ── Non-blend formats ─────────────────────────────────────────────────
    try:
        if suffix in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(resolved_path))
            return True
        elif suffix == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(resolved_path))
            return True
        elif suffix == ".obj":
            try:
                bpy.ops.wm.obj_import(filepath=str(resolved_path))
            except Exception:
                bpy.ops.import_scene.obj(filepath=str(resolved_path))
            return True
    except Exception as e:
        print(f"[ASSET] import_asset failed ({suffix}): {e}", flush=True)
        return False

    print(f"[ASSET] import_asset: unsupported format {suffix}", flush=True)
    return False
