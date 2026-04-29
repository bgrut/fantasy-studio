from __future__ import annotations

"""
asset_import.py
===============
Bulletproof asset-import helpers used by the Blender render subprocess.

Responsibilities
----------------
- Verify that a downloaded asset file actually exists, is non-empty,
  and has the right magic bytes for its extension (so we catch ZIPs,
  HTML error pages, or truncated downloads *before* Blender's importer
  chokes on them).
- Resolve asset paths to absolute paths relative to the backend project
  root, so the render subprocess finds them regardless of CWD.
- Remove Blender's default startup primitives (Cube / Sphere / Cylinder
  / Cone / Suzanne / Torus / Plane) so they never end up as the hero.
- Import a 3D asset and *confirm* that new objects appeared in the
  scene, with loud logging of verts/faces/bones for each new object.

These helpers live in a standalone module so they can be imported both
by the render_from_manifest top level AND by individual templates
without any circular dependencies.
"""

from pathlib import Path


# Project root = .../blender-studio-backend  (two parents up from app/scene/)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════════════════
# Path resolution
# ═══════════════════════════════════════════════════════════════════════════

def resolve_asset_path(path_str: str | None) -> str | None:
    """
    Convert any relative asset path into an absolute path that Blender
    (which runs as a subprocess with an unknown CWD) can find.

    Checks, in order:
      1. The path is already absolute and exists.
      2. <project_root>/<path_str> exists.
      3. Path.cwd() / path_str exists.
    Returns the best-guess absolute path as a string, or None if the
    input was empty.
    """
    if not path_str:
        return None

    p = Path(path_str)
    if p.is_absolute() and p.exists():
        return str(p)

    candidate = (_PROJECT_ROOT / path_str).resolve()
    if candidate.exists():
        return str(candidate)

    cwd_candidate = (Path.cwd() / path_str).resolve()
    if cwd_candidate.exists():
        return str(cwd_candidate)

    print(
        f"[PATH] WARNING: could not resolve asset path: {path_str!r}\n"
        f"[PATH]   tried absolute: {p}\n"
        f"[PATH]   tried project:  {candidate}\n"
        f"[PATH]   tried cwd:      {cwd_candidate}",
        flush=True,
    )
    # Return the best-guess absolute path so the caller's error log
    # points somewhere useful instead of the raw relative string.
    return str(candidate)


# ═══════════════════════════════════════════════════════════════════════════
# File verification
# ═══════════════════════════════════════════════════════════════════════════

def verify_asset_file(asset_path: str | None) -> tuple[bool, str]:
    """
    Verify a downloaded asset file is present, non-empty, and appears to
    be a real 3D asset rather than a ZIP archive, HTML error page, or
    truncated download.

    Returns (is_valid, message). The message is suitable for logging.
    """
    if not asset_path:
        return False, "asset_path is None/empty"

    p = Path(asset_path)
    if not p.is_absolute():
        p = (_PROJECT_ROOT / asset_path).resolve()

    if not p.exists():
        return False, f"file not found: {p}"

    size = p.stat().st_size
    if size == 0:
        return False, f"file is empty (0 bytes): {p}"
    if size < 500:
        return False, f"file suspiciously small ({size} bytes): {p}"

    try:
        with open(p, "rb") as f:
            header = f.read(16)
    except OSError as e:
        return False, f"cannot read header from {p}: {e}"

    ext = p.suffix.lower()
    if ext == ".glb":
        if header[:4] != b"glTF":
            if header[:2] == b"PK":
                return False, f"file is a ZIP archive, not a GLB — needs extraction: {p}"
            if header[:1] == b"<":
                return False, f"file is HTML (probably an error page), not a GLB: {p}"
            return False, f"file does not have GLB magic bytes: {p}"
    elif ext == ".blend":
        # Blender 3.0+ saves with zstd compression by default, and older
        # versions used gzip. Both produce valid .blend files that
        # bpy.data.libraries.load() decompresses transparently — but the
        # file no longer starts with the literal "BLENDER" magic bytes.
        # Accept all three variants instead of rejecting perfectly-good
        # compressed blends as "invalid". This matters because every
        # asset in our local registry is zstd-compressed.
        _BLEND_MAGIC_UNCOMPRESSED = b"BLENDER"
        _BLEND_MAGIC_GZIP         = b"\x1f\x8b"
        _BLEND_MAGIC_ZSTD         = b"\x28\xb5\x2f\xfd"
        if header[:7] == _BLEND_MAGIC_UNCOMPRESSED:
            pass  # uncompressed
        elif header[:2] == _BLEND_MAGIC_GZIP:
            return True, f"valid gzip-compressed .blend ({size:,} bytes): {p}"
        elif header[:4] == _BLEND_MAGIC_ZSTD:
            return True, f"valid zstd-compressed .blend ({size:,} bytes): {p}"
        else:
            return False, (
                f"file is not a Blender file (no BLENDER / gzip / zstd "
                f"magic bytes, got {header[:8].hex()}): {p}"
            )
    elif ext == ".fbx":
        # Binary FBX starts with "Kaydara FBX Binary"; ASCII FBX starts with
        # "; FBX". Accept either.
        if (not header.startswith(b"Kaydara FBX Binary")
                and not header.lstrip().startswith(b"; FBX")):
            # Don't fail here — some exporters produce non-standard FBX
            # headers that Blender still reads fine. Just warn.
            return True, f"valid-ish ({size:,} bytes, unusual FBX header): {p}"

    return True, f"valid ({size:,} bytes): {p}"


# ═══════════════════════════════════════════════════════════════════════════
# Default-primitive cleanup
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_PRIMITIVE_NAMES = {
    "Cube", "Sphere", "Cylinder", "Suzanne", "Torus", "Cone", "Plane",
    "Ico Sphere", "Icosphere", "Circle", "Monkey", "Grid",
}

# Name prefixes Blender uses for numbered duplicates (e.g. "Cube.001").
_DEFAULT_PRIMITIVE_PREFIXES = tuple(
    f"{n}." for n in _DEFAULT_PRIMITIVE_NAMES
)

# Substrings we consider "template-created" and NEVER remove — templates
# rely on ground/floor/sky/backdrop geometry, and the hero mesh might
# literally be called "scene" by the glTF exporter.
_PROTECTED_NAME_SUBSTRINGS = (
    "ground", "floor", "sky", "backdrop", "terrain",
    "ocean", "water", "sea", "road", "street", "highway",
    "wall", "stage", "pedestal", "platform", "podium",
    "hero", "subject", "body", "rig", "armature",
    "placeholder",              # HeroPlaceholder from build_fallback_scene
    "scene", "mesh",            # glTF exports often include these
    "dog", "cat", "car", "ferrari", "whale", "mountain",  # known template defaults
)


def _is_protected_name(name: str) -> bool:
    n = name.lower()
    return any(sub in n for sub in _PROTECTED_NAME_SUBSTRINGS)


def clean_default_primitives(bpy) -> int:
    """
    Remove Blender's default startup primitives — including numbered
    duplicates like ``Cube.001`` — and unmaterialised scratch meshes a
    template may have left behind.

    Round 8 strengthens this to also catch:
      * Numbered-duplicate defaults (``Sphere.002``) left over when a
        template spawned and failed to rename them.
      * Small untextured meshes (no materials, < 1000 verts) whose name
        doesn't contain any protected template substring.

    Returns the number of objects removed. Protected names (``Ground``,
    ``OceanFloor``, ``SkyDome``, hero/armature/mesh) are always kept.
    """
    removed: list[str] = []

    for obj in list(bpy.data.objects):
        name = obj.name

        # Always protect known template/hero geometry regardless of shape.
        if _is_protected_name(name):
            continue

        # 1) Exact default-primitive name, or "Cube.001" style duplicate.
        if name in _DEFAULT_PRIMITIVE_NAMES or name.startswith(_DEFAULT_PRIMITIVE_PREFIXES):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
                removed.append(name)
                continue
            except Exception as e:
                print(f"[SCENE_CLEAN] failed to remove {name}: {e}", flush=True)
                continue

        # 2) Untextured, low-poly mesh with no protected name — almost
        #    certainly a template's scratch primitive that survived.
        try:
            if obj.type == "MESH" and obj.data is not None:
                mat_count = len(getattr(obj.data, "materials", []) or [])
                vert_count = len(getattr(obj.data, "vertices", []) or [])
                if mat_count == 0 and 0 < vert_count < 1000:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    removed.append(f"{name} (no-material, {vert_count} verts)")
        except Exception as e:
            print(f"[SCENE_CLEAN] inspect failed for {name}: {e}", flush=True)

    if removed:
        print(
            f"[SCENE_CLEAN] removed {len(removed)} default/scratch object(s): {removed}",
            flush=True,
        )
    return len(removed)


# ═══════════════════════════════════════════════════════════════════════════
# Scene-basics guarantor
# ═══════════════════════════════════════════════════════════════════════════

def _scene_has_ground(bpy) -> bool:
    """Heuristic: any large flat-ish mesh whose name looks ground-like."""
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        lname = obj.name.lower()
        looks_groundy = any(
            kw in lname for kw in ("ground", "floor", "plane", "terrain", "road", "stage")
        )
        if not looks_groundy:
            continue
        try:
            # Any axis > 5 units is "large enough to be a ground"
            if max(obj.scale.x, obj.scale.y) > 5.0:
                return True
            # Or the bounding box is wide — imported meshes sometimes have
            # scale == 1 but the mesh data itself is huge.
            if obj.data and len(obj.data.vertices) > 0:
                xs = [v.co.x for v in obj.data.vertices]
                ys = [v.co.y for v in obj.data.vertices]
                if (max(xs) - min(xs)) > 5.0 or (max(ys) - min(ys)) > 5.0:
                    return True
        except Exception:
            continue
    return False


def ensure_scene_basics(bpy, hero_objects=None) -> dict:
    """
    Guarantee every scene we render has: a sky world, a ground plane,
    a grounded hero (lowest point ~ z=0), a camera, and at least one
    light. Call this AFTER the template build, BEFORE render.

    This is a belt-and-braces safety net. Templates normally handle all
    of these themselves; ensure_scene_basics only ADDS what's missing so
    a broken template can never produce a blank/floating render.

    Returns a dict summarising what was added, for logging.
    """
    from mathutils import Vector

    added = {
        "sky": False, "ground": False, "camera": False,
        "light": False, "hero_grounded": False,
    }
    scene = bpy.context.scene

    # 1) SKY / world background --------------------------------------------
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
        added["sky"] = True
    if not world.use_nodes:
        world.use_nodes = True
        added["sky"] = True
    try:
        bg = world.node_tree.nodes.get("Background")
        if bg is not None:
            current = tuple(bg.inputs[0].default_value)
            if current == (0.0, 0.0, 0.0, 1.0):  # default pitch-black
                bg.inputs[0].default_value = (0.5, 0.6, 0.8, 1.0)  # sky blue
                added["sky"] = True
    except Exception as e:
        print(f"[SCENE_BASICS] world adjust skipped: {e}", flush=True)

    # 2) GROUND -------------------------------------------------------------
    if not _scene_has_ground(bpy):
        try:
            bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
            ground = bpy.context.active_object
            ground.name = "GroundPlane"
            mat = bpy.data.materials.new("GroundMaterial")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf is not None:
                bsdf.inputs["Base Color"].default_value = (0.3, 0.32, 0.28, 1.0)
                try:
                    bsdf.inputs["Roughness"].default_value = 0.85
                except Exception:
                    pass
            ground.data.materials.append(mat)
            added["ground"] = True
        except Exception as e:
            print(f"[SCENE_BASICS] ground create failed: {e}", flush=True)

    # 3) HERO GROUNDED ------------------------------------------------------
    if hero_objects:
        try:
            min_z = float("inf")
            for obj in hero_objects:
                if obj.type == "MESH" and obj.data is not None:
                    for v in obj.bound_box:
                        world_z = (obj.matrix_world @ Vector(v)).z
                        if world_z < min_z:
                            min_z = world_z
            if min_z != float("inf") and abs(min_z) > 0.01:
                # Move only top-level roots so child transforms don't double-apply.
                roots = {obj for obj in hero_objects if obj.parent not in hero_objects}
                offset = -min_z
                for obj in roots:
                    obj.location.z += offset
                added["hero_grounded"] = True
                print(
                    f"[SCENE_BASICS] grounded hero: shifted "
                    f"{len(roots)} root(s) by {offset:+.3f}",
                    flush=True,
                )
        except Exception as e:
            print(f"[SCENE_BASICS] hero-ground adjust failed: {e}", flush=True)

    # 4) CAMERA -------------------------------------------------------------
    if scene.camera is None:
        try:
            bpy.ops.object.camera_add(location=(10, -10, 5), rotation=(1.1, 0.0, 0.8))
            cam = bpy.context.active_object
            cam.name = "AutoCamera"
            cam.data.lens = 50
            scene.camera = cam
            added["camera"] = True
        except Exception as e:
            print(f"[SCENE_BASICS] camera create failed: {e}", flush=True)

    # 5) LIGHT --------------------------------------------------------------
    has_light = any(obj.type == "LIGHT" for obj in bpy.data.objects)
    if not has_light:
        try:
            bpy.ops.object.light_add(type="SUN", location=(5, 5, 10))
            sun = bpy.context.active_object
            sun.name = "AutoSun"
            sun.data.energy = 3.0
            added["light"] = True
        except Exception as e:
            print(f"[SCENE_BASICS] light create failed: {e}", flush=True)

    if any(added.values()):
        print(f"[SCENE_BASICS] filled gaps: {added}", flush=True)
    else:
        print("[SCENE_BASICS] scene already complete", flush=True)
    return added


# ═══════════════════════════════════════════════════════════════════════════
# Import with before/after tracking
# ═══════════════════════════════════════════════════════════════════════════

def import_hero_asset(bpy, asset_path: str) -> list:
    """
    Import a 3D asset into the current Blender scene and return the list
    of NEWLY appeared objects (so callers can animate / frame exactly
    what was imported, not whatever else happens to live in the scene).

    Returns an empty list on any failure — caller should fall back.
    """
    if not asset_path:
        print("[IMPORT] no asset_path provided", flush=True)
        return []

    p = Path(asset_path)
    if not p.is_absolute():
        resolved = resolve_asset_path(asset_path)
        if resolved:
            p = Path(resolved)

    ok, msg = verify_asset_file(str(p))
    print(f"[IMPORT] asset verification: {msg}", flush=True)
    if not ok:
        print(f"[IMPORT] SKIPPING import — file invalid.", flush=True)
        return []

    ext = p.suffix.lower()
    print(f"[IMPORT] attempting import: {p} (format={ext})", flush=True)

    before = {obj.name for obj in bpy.data.objects}

    try:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=str(p))
        elif ext == ".blend":
            with bpy.data.libraries.load(str(p), link=False) as (data_from, data_to):
                data_to.objects = list(data_from.objects)
            for obj in data_to.objects:
                if obj is not None:
                    try:
                        bpy.context.collection.objects.link(obj)
                    except Exception:
                        try:
                            bpy.context.scene.collection.objects.link(obj)
                        except Exception as le:
                            print(f"[IMPORT] link failed for {obj.name}: {le}", flush=True)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(p))
        elif ext == ".obj":
            try:
                bpy.ops.wm.obj_import(filepath=str(p))
            except AttributeError:
                bpy.ops.import_scene.obj(filepath=str(p))
        elif ext == ".zip":
            print(
                f"[IMPORT] ERROR: received a .zip file! "
                f"The extraction step failed upstream: {p}",
                flush=True,
            )
            return []
        else:
            print(f"[IMPORT] ERROR: unsupported format {ext!r}: {p}", flush=True)
            return []
    except Exception as e:
        print(f"[IMPORT] ERROR during import: {type(e).__name__}: {e}", flush=True)
        return []

    after = {obj.name for obj in bpy.data.objects}
    new_names = after - before

    if not new_names:
        print(
            f"[IMPORT] WARNING: import completed but NO new objects appeared. "
            f"before={len(before)} after={len(after)}",
            flush=True,
        )
        for col in bpy.data.collections:
            print(f"[IMPORT]   collection {col.name!r}: {len(col.objects)} objects", flush=True)
        return []

    new_objects = [bpy.data.objects[name] for name in new_names if name in bpy.data.objects]

    print(f"[IMPORT] successfully imported {len(new_objects)} objects:", flush=True)
    for obj in new_objects:
        extra = ""
        if obj.type == "MESH" and obj.data is not None:
            extra = f" (verts={len(obj.data.vertices)}, faces={len(obj.data.polygons)})"
        elif obj.type == "ARMATURE" and obj.data is not None:
            extra = f" (bones={len(obj.data.bones)})"
        print(f"[IMPORT]   - {obj.name!r} type={obj.type}{extra}", flush=True)

    return new_objects
