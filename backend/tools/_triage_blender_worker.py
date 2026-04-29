"""
tools/_triage_blender_worker.py
===============================
Blender-side worker for triage_previews.py.

Loops through an asset job list, loads each, applies healed orientation
fix + ground_offset_z, renders a 256×256 Eevee thumbnail, writes to
``assets/thumbnails/<asset_id>.png``.

Invoked as:
    blender -b --factory-startup --python _triage_blender_worker.py -- <job_file.json> <thumbs_dir>
"""
import json
import os
import sys
from pathlib import Path


def _wipe_scene():
    try:
        import bpy  # type: ignore
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except Exception:
        pass


def _import_asset(path: str) -> bool:
    import bpy  # type: ignore
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=path)
            else:
                bpy.ops.import_scene.obj(filepath=path)
        elif ext == ".blend":
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            for obj in dst.objects:
                if obj is not None:
                    bpy.context.scene.collection.objects.link(obj)
        else:
            return False
        return True
    except Exception as e:
        print(f"[TRIAGE] import failed for {path}: {e}", flush=True)
        return False


def _compute_world_bbox():
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    have = False
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mw = obj.matrix_world
        for v in obj.data.vertices:
            wc = mw @ v.co
            for i in range(3):
                if wc[i] < mn[i]:
                    mn[i] = wc[i]
                if wc[i] > mx[i]:
                    mx[i] = wc[i]
            have = True
    if not have:
        return None, None, None, None
    center = [(mn[i] + mx[i]) * 0.5 for i in range(3)]
    size = [mx[i] - mn[i] for i in range(3)]
    diag = max((size[0] ** 2 + size[1] ** 2 + size[2] ** 2) ** 0.5, 0.1)
    return Vector(mn), Vector(mx), Vector(center), diag


def _apply_heal(entry: dict):
    import bpy  # type: ignore
    rot = entry.get("orientation_fix_rotation_euler")
    gz = entry.get("ground_offset_z")
    roots = [
        o for o in bpy.context.scene.objects
        if o.parent is None and o.type in ("MESH", "EMPTY", "ARMATURE")
    ]
    for root in roots:
        if rot and isinstance(rot, (list, tuple)) and len(rot) >= 3:
            try:
                root.rotation_euler = (
                    root.rotation_euler.x + float(rot[0]),
                    root.rotation_euler.y + float(rot[1]),
                    root.rotation_euler.z + float(rot[2]),
                )
            except Exception:
                pass
        if gz is not None:
            try:
                gzf = float(gz)
                if abs(gzf) > 1e-4:
                    root.location.z -= gzf
            except Exception:
                pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _setup_render_once(scene):
    scene.render.resolution_x = 256
    scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    # Try Eevee Next (Blender 4.2+), fall back to legacy
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        try:
            scene.render.engine = "BLENDER_EEVEE"
        except Exception:
            pass
    # Low samples for speed
    try:
        scene.eevee.taa_render_samples = 8
    except Exception:
        pass


def _add_lights_and_camera(center, diag):
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
    # 3/4 angle camera
    cam_dist = max(diag * 1.5, 1.5)
    cam_loc = (
        center[0] + cam_dist * 0.7,
        center[1] - cam_dist,
        center[2] + cam_dist * 0.4,
    )
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.active_object
    cam.data.lens = 50
    bpy.context.scene.camera = cam
    direction = Vector(center) - cam.location
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = direction.to_track_quat("-Z", "Y")

    # Simple 3-point lighting
    bpy.ops.object.light_add(type="SUN", location=(5, -5, 10))
    try:
        bpy.context.active_object.data.energy = 3.0
    except Exception:
        pass
    bpy.ops.object.light_add(
        type="AREA",
        location=(center[0] - diag, center[1] - diag, center[2] + diag),
    )
    try:
        bpy.context.active_object.data.energy = 500
    except Exception:
        pass
    bpy.ops.object.light_add(
        type="AREA",
        location=(center[0] + diag, center[1] + diag, center[2] + diag * 0.5),
    )
    try:
        bpy.context.active_object.data.energy = 250
    except Exception:
        pass


def _setup_world():
    import bpy  # type: ignore
    world = bpy.data.worlds.new("TriageWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.15, 0.15, 0.18, 1.0)
        bg.inputs["Strength"].default_value = 1.0


def _render_one(entry: dict, thumbs_dir: Path) -> str:
    import bpy  # type: ignore
    eid = entry.get("id") or "unknown"
    path = entry.get("path") or ""
    if not path or not os.path.exists(path):
        return f"missing: {path}"

    _wipe_scene()
    if not _import_asset(path):
        return "import_failed"

    _apply_heal(entry)

    mn, mx, center, diag = _compute_world_bbox()
    if center is None:
        # No mesh to frame — still produce an empty thumbnail so user
        # sees the entry in the gallery.
        center = [0.0, 0.0, 0.0]
        diag = 2.0

    _setup_render_once(bpy.context.scene)
    _setup_world()
    _add_lights_and_camera(center, diag)

    out_path = thumbs_dir / f"{eid}.png"
    bpy.context.scene.render.filepath = str(out_path)
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        return f"render_failed: {e}"
    return "ok"


def main() -> None:
    try:
        sep = sys.argv.index("--")
    except ValueError:
        print("[TRIAGE] missing -- separator", flush=True)
        sys.exit(2)
    argv = sys.argv[sep + 1:]
    if len(argv) < 2:
        print("[TRIAGE] need <job_file> <thumbs_dir>", flush=True)
        sys.exit(2)

    job_file = argv[0]
    thumbs_dir = Path(argv[1])
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    entries = json.loads(Path(job_file).read_text(encoding="utf-8"))
    total = len(entries)
    print(f"[TRIAGE] worker starting: {total} entries", flush=True)
    ok = 0
    failed = 0
    for i, entry in enumerate(entries):
        eid = entry.get("id", f"idx_{i}")
        try:
            status = _render_one(entry, thumbs_dir)
        except Exception as e:
            status = f"crash: {e}"
        if status == "ok":
            ok += 1
        else:
            failed += 1
        print(f"[TRIAGE] {i+1}/{total} {eid} — {status}", flush=True)

    print(f"[TRIAGE] complete: ok={ok} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
