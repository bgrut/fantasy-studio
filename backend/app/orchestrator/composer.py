"""
Deterministic scene composer.

Takes slot dict (from slots.py) + output paths → composes the scene through
the existing MCP tools in a fixed, reliable order. NO LLM in this layer.

This is the Sora-style architecture: the LLM did the semantic extraction;
this module does the deterministic execution. Reliable, fast, predictable.

Composition order (single hero v1):
    1. reset_scene
    2. set_render_settings
    3. set_frame_range (if animation)
    4. create_primitive / spawn_asset for the hero
    5. tag the hero
    6. ground plane (if requested)
    7. create_material + apply_material
    8. apply_three_point_lighting (mood-driven)
    9. create_camera + look_at (framing/angle-driven)
    10. motion (if animation): orbit / rotate / translate / bounce / drift
    11. render_frame OR render_animation + encode_video
"""

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..mcp import registry, bridge
from .scene_inference import COLOR_MAP, MATERIAL_VIBES, LIGHTING_MOOD
from . import patterns as pattern_lib
from . import motion_rig
from . import procedural_vehicle


# ───────────────────────────────────────────────────────────────────────
# Phase 18 FINAL — per-pattern standing orientation, in BLENDER's frame.
#
# Calibrated once per pattern with scripts/orient_audit_blender.py, which
# renders all 24 axis-aligned orientations from a true side view using the real
# Blender renderer. You pick the cell where the subject stands; paste its Euler
# (degrees, Blender XYZ) here. Applied + baked + re-grounded after mesh import.
# None = not yet calibrated (mesh imports in raw orientation).
# ───────────────────────────────────────────────────────────────────────
_BLENDER_PATTERN_EULER = {
    # CALIBRATION MODE: None → mesh imports RAW (no rotation baked). Open the
    # composer-produced .blend, set the Hero's rotation mode to XYZ Euler,
    # rotate it standing with the gizmo, read the three Rotation values, and
    # paste them here as (rx, ry, rz). Because the mesh is raw (no hidden
    # offset) and we apply in the same Blender frame you measured in, the value
    # is guaranteed to reproduce your standing pose.
    # quadruped: orthographic audit cell #13 "y270" — true-ortho front view
    # shows a clean standing side profile (head up, four feet on the ground).
    # Ortho removes the perspective distortion that made earlier picks (#17
    # x90) look standing when they were actually lying flat.
    # TripoSR frame: cell #13 "y270" stands every pattern upright (ControlNet
    # pose-lock makes all subjects share one frame).
    "quadruped": (0.0, 270.0, 0.0),
    "biped":     (0.0, 270.0, 0.0),
    "vehicle":   (0.0, 270.0, 0.0),
    "tree":      (0.0, 270.0, 0.0),
    "celestial": None,   # spheres — orientation doesn't matter
}

# TripoSG outputs UPRIGHT by default (verified via audit_triposg2 — identity is
# already standing). We add a z90 spin for a flattering side-profile start.
# Engine-aware: applied only when the mesh came from TripoSG.
_TRIPOSG_PATTERN_EULER = {
    "quadruped": (0.0, 0.0, 90.0),
    "biped":     (0.0, 0.0, 90.0),
    "vehicle":   (0.0, 0.0, 90.0),
    "tree":      (0.0, 0.0, 90.0),
    "celestial": None,
}


# ───────────────────────────────────────────────────────────────────────
# Result type
# ───────────────────────────────────────────────────────────────────────

@dataclass
class CompositionResult:
    success: bool
    render_path: Optional[str] = None
    video_path: Optional[str] = None
    blend_path: Optional[str] = None  # Phase 17 — editable scene alongside output
    is_animation: bool = False
    steps_run: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_s: float = 0.0
    slots: Dict[str, Any] = field(default_factory=dict)


# ───────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────

def _resolve_color(color_name: str) -> List[float]:
    """color_name → RGB. Falls back to neutral gray if unknown."""
    return COLOR_MAP.get(color_name.lower(), [0.65, 0.65, 0.70])


def _material_params_from_slots(subj: Dict[str, Any], run_id: str, base_pattern: str = "primitive_geo") -> Dict[str, Any]:
    """Translate subject slots → PrincipledBSDF params for create_material.

    The material name includes a run-unique suffix so Blender NEVER silently
    falls back to a stale 'HeroMat' from a previous render.

    Special handling:
    - For bipeds with no color specified and "human/person" in name → skin tone
    - For celestial pattern → emission is controlled by the pattern preset, NOT the slot
      (the LLM extracts "emissive=True" for "moon" because moons emit light visually,
      but in 3D we want the moon to REFLECT light, not glow)
    """
    color_name = subj.get("color_name", "neutral")
    name_text = (subj.get("name") or "").lower() + " " + (subj.get("library_query") or "").lower()

    # Auto-skin for humans without explicit color
    if color_name in ("neutral", "") and base_pattern == "biped":
        if "human" in name_text or "person" in name_text or "kid" in name_text or "child" in name_text or "man" in name_text or "woman" in name_text:
            color_name = "skin"

    color_rgb = _resolve_color(color_name)
    material = subj.get("material", "matte")
    vibe = MATERIAL_VIBES.get(material, {"metallic": 0.0, "roughness": 0.55})

    params: Dict[str, Any] = {
        "name": f"HeroMat_{run_id}",
        "color": color_rgb + [1.0],
        "metallic": vibe.get("metallic", 0.0),
        "roughness": vibe.get("roughness", 0.55),
    }
    # Subsurface scattering for organic surfaces (skin, fur, wax, fabric).
    # Light penetrates the surface slightly → soft glow → looks alive vs plastic.
    if material in ("fuzzy", "fabric", "rubber") or color_name.startswith("skin"):
        params["subsurface"] = 0.25 if color_name.startswith("skin") else 0.15
        params["subsurface_color"] = color_rgb
        params["subsurface_radius"] = [1.0, 0.4, 0.3] if color_name.startswith("skin") else [0.5, 0.4, 0.4]

    # Vehicle bodies get anisotropic metal — directional highlights read as brushed/painted
    # car steel rather than flat plastic. Bumps metallic to ensure the BSDF actually
    # uses the anisotropy term.
    if base_pattern == "vehicle":
        params["metallic"] = max(params.get("metallic", 0.0), 0.85)
        params["roughness"] = max(0.20, min(params.get("roughness", 0.55), 0.45))
        params["anisotropic"] = 0.6
        params["anisotropic_rotation"] = 0.0  # 0 = horizontal highlights, classic car-panel look
        # Add a faint clearcoat for that just-waxed look
        params["clearcoat"] = 0.5
        params["clearcoat_roughness"] = 0.08

    # Emission ONLY when slot says emissive AND we're not on a pattern that owns its emission
    if subj.get("emissive") and base_pattern != "celestial":
        params["emission_color"] = color_rgb
        params["emission_strength"] = 15.0
    return params


def _lighting_params_from_mood(mood: str) -> Dict[str, Any]:
    """Mood → 3-point lighting parameters. Fallback matches 'neutral' studio."""
    return LIGHTING_MOOD.get(mood, {
        "color_temp": "neutral",
        "key_energy": 2500, "fill_energy": 900, "rim_energy": 1200,
    }).copy()


def _setup_mesh_relative_orbit(
    runner, hero_name: str, duration_frames: int, revolutions: float,
    lens: float = 50.0, verbose: bool = True,
) -> bool:
    """Set up a camera + orbit animation in the Hero's PCA frame.

    Why: TripoSR meshes arrive in arbitrary world orientations (sometimes flat,
    sometimes tilted). World-axis cameras then produce weird angles. Instead,
    we compute the mesh's three principal axes via PCA and:

      - longest axis  → "body length" (subject's longest dimension)
      - medium axis   → "up" (used as orbit axis, so the camera circles like
                              a turntable in the mesh's local frame)
      - shortest axis → "depth" (camera approaches from this direction so the
                                 longest axis appears horizontal in the frame)

    The camera always sees a flattering side-profile-ish shot regardless of
    which world axis the mesh's longest dim happens to point along.

    Returns True on success, False if PCA setup failed (caller falls back to
    world-axis camera).
    """
    # All math + Blender ops happen inside a single execute_python so we can
    # use numpy and don't have to round-trip vertex data through the bridge.
    code = f"""
import bpy, math, json
from mathutils import Vector, Matrix
import numpy as np

hero = bpy.data.objects.get('{hero_name}')
if hero is None or hero.type != 'MESH':
    __result__ = json.dumps({{'ok': False, 'why': 'hero_not_mesh'}})
else:
    # Vertices in WORLD space (include hero's location/rotation/scale).
    mw = hero.matrix_world
    verts = np.array([list(mw @ v.co) for v in hero.data.vertices], dtype=np.float64)
    if verts.shape[0] < 10:
        __result__ = json.dumps({{'ok': False, 'why': 'too_few_verts'}})
    else:
        # Center + PCA via covariance eigendecomposition.
        centroid = verts.mean(axis=0)
        centered = verts - centroid
        cov = np.cov(centered.T)
        evals, evecs = np.linalg.eigh(cov)
        # eigh returns ascending eigenvalues. Reorder to: PC1 (longest) first.
        order = np.argsort(evals)[::-1]
        evals = evals[order]
        evecs = evecs[:, order]
        # Extents along each PC.
        proj = centered @ evecs
        spans = proj.max(axis=0) - proj.min(axis=0)
        pc1 = evecs[:, 0]   # mesh's longest axis (body length, usually)

        # ─── Hybrid framing ────────────────────────────────────────────────
        # Lesson from previous PCA attempt: using a non-vertical PCA axis as
        # "up" puts the camera looking down at the mesh, which makes the
        # subject appear head-down even when geometry is correct.
        #
        # Better: ALWAYS use world +Z as camera up; ALWAYS orbit around world
        # Z. PCA only determines WHICH horizontal angle to view from — we
        # project PC1 (body length) onto the world XY plane and place the
        # camera PERPENDICULAR to that projection. That gives a clean
        # broadside view regardless of which world axis the body happens to
        # lie along.
        # ────────────────────────────────────────────────────────────────────
        # Project PC1 onto world XY plane (remove Z component, renormalize).
        pc1_xy = np.array([pc1[0], pc1[1], 0.0])
        norm = np.linalg.norm(pc1_xy)
        if norm < 1e-4:
            # PC1 is nearly vertical (mesh is tall/thin). Default to -Y view.
            length_xy = np.array([0.0, 1.0, 0.0])
        else:
            length_xy = pc1_xy / norm
        # Perpendicular to length_xy in the XY plane (rotate 90° around Z).
        broadside_xy = np.array([-length_xy[1], length_xy[0], 0.0])

        # Distance: enough to fit longest in-XY extent at ~55% of frame for a
        # 50mm lens. Use the larger of (PC1 span, world-bbox max dim) so we
        # don't crop tall meshes.
        bbox_max = float(max(spans[0], spans[1], spans[2]))
        base_dist = max(bbox_max * 1.7, 2.5)
        # 3/4 elevation: ~20° above horizontal.
        height_offset = bbox_max * 0.35

        # Camera offset from centroid (world space).
        cam_offset = broadside_xy * base_dist + np.array([0.0, 0.0, height_offset])
        cam_start = centroid + cam_offset

        # Create or reuse 'Cam'.
        cam = bpy.data.objects.get('Cam')
        if cam is None:
            cam_data = bpy.data.cameras.new('Cam')
            cam = bpy.data.objects.new('Cam', cam_data)
            bpy.context.scene.collection.objects.link(cam)
        cam.data.lens = {lens}
        cam.location = Vector(cam_start.tolist())

        # Aim at centroid using WORLD +Z as up (camera roll stays stable).
        # to_track_quat picks the rotation so -Z (camera forward) points along
        # look_dir, and Y (camera up) aligns with world +Z. This keeps the
        # horizon level no matter where the camera orbits to.
        look_dir = Vector(centroid.tolist()) - cam.location
        rot_quat = look_dir.to_track_quat('-Z', 'Y')
        cam.rotation_mode = 'QUATERNION'
        cam.rotation_quaternion = rot_quat
        bpy.context.scene.camera = cam

        # Animate: orbit around the WORLD Z axis through the centroid. We use
        # world Z (not a PCA axis) because mesh principal axes don't generally
        # align with vertical, and orbiting around non-vertical axes makes the
        # video appear to tumble. Rodrigues rotation around world +Z:
        total_angle = 2.0 * math.pi * {revolutions}
        n_keys = max(8, int({duration_frames} / 4))   # keyframe every ~4 frames
        k = np.array([0.0, 0.0, 1.0])
        v0 = cam_offset.copy()
        # Clear any existing animation data on cam
        cam.animation_data_clear()
        for i in range(n_keys + 1):
            frac = i / n_keys
            angle = total_angle * frac
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            v_rot = (
                v0 * cos_a
                + np.cross(k, v0) * sin_a
                + k * (k @ v0) * (1.0 - cos_a)
            )
            pos = centroid + v_rot
            frame = 1 + int(frac * ({duration_frames} - 1))
            cam.location = Vector(pos.tolist())
            # Re-aim
            look_dir = Vector(centroid.tolist()) - cam.location
            cam.rotation_quaternion = look_dir.to_track_quat('-Z', 'Y')
            cam.keyframe_insert(data_path='location', frame=frame)
            cam.keyframe_insert(data_path='rotation_quaternion', frame=frame)

        # Set interpolation to LINEAR so the orbit reads as smooth circular motion
        # (default BEZIER eases in/out and looks like a wobble).
        if cam.animation_data and cam.animation_data.action:
            for fc in cam.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'

        __result__ = json.dumps({{
            'ok': True,
            'centroid': centroid.tolist(),
            'pc1_span': float(spans[0]),
            'pc2_span': float(spans[1]),
            'pc3_span': float(spans[2]),
            'n_keyframes': n_keys + 1,
        }})
"""
    try:
        result = runner.run("mesh_relative_orbit", "execute_python", {"code": code}, critical=False)
    except Exception as e:
        if verbose:
            print(f"[composer] mesh_relative_orbit failed: {type(e).__name__}: {e}")
        return False

    payload = (result or {}).get("result") if isinstance(result, dict) else None
    try:
        import json as _json
        parsed = _json.loads(payload) if isinstance(payload, str) else {}
    except Exception:
        parsed = {}
    if not parsed.get("ok"):
        if verbose:
            print(f"[composer] mesh_relative_orbit no-op: {parsed.get('why', 'unknown')}")
        return False
    if verbose:
        print(f"[composer]   PC spans: PC1={parsed.get('pc1_span', 0):.2f} "
              f"PC2={parsed.get('pc2_span', 0):.2f} "
              f"PC3={parsed.get('pc3_span', 0):.2f}, "
              f"keyframes={parsed.get('n_keyframes', 0)}")
    return True


def _detect_subject_bbox(ref_png: str, verbose: bool = True):
    """Return the subject's content bbox in a reference image as normalized
    (x0, y0, x1, y1) with a top-left origin. SDXL backgrounds are a neutral gray
    gradient; the subject is warmer/saturated, so we segment by saturation (plus
    a dark-pixel catch) inside a frame-skipped region. Falls back to a sane inset.
    """
    x0, y0, x1, y1 = 0.08, 0.06, 0.92, 0.96
    try:
        from PIL import Image
        import numpy as _np
        im = _np.asarray(Image.open(ref_png).convert("RGB"), dtype=_np.float32)
        h, w = im.shape[:2]
        f = 0.05
        ry0, ry1 = int(h * f), int(h * (1 - f))
        rx0, rx1 = int(w * f), int(w * (1 - f))
        mx = im.max(axis=2); mn = im.min(axis=2)
        sat = (mx - mn) / (mx + 1e-3)
        mask = sat > 0.20
        lum = im.mean(axis=2)
        mask |= lum < 55.0
        keep = _np.zeros_like(mask)
        keep[ry0:ry1, rx0:rx1] = True
        mask &= keep
        cols = _np.where(mask.any(axis=0))[0]
        rows = _np.where(mask.any(axis=1))[0]
        if cols.size and rows.size:
            pad = 0.01
            x0 = max(0.0, cols.min() / w - pad); x1 = min(1.0, cols.max() / w + pad)
            y0 = max(0.0, rows.min() / h - pad); y1 = min(1.0, rows.max() / h + pad)
            if verbose:
                frac = float(mask.sum()) / float(mask.size)
                print(f"[composer] subject bbox x=[{x0:.2f},{x1:.2f}] "
                      f"y=[{y0:.2f},{y1:.2f}] of {w}x{h} (fg {frac*100:.0f}%)")
    except Exception as _e:
        if verbose:
            print(f"[composer] bbox detect fell back ({type(_e).__name__}: {_e})")
    return x0, y0, x1, y1


def _orient_hero_by_reference(runner, hero_name: str, ref_png: str, work_dir,
                              min_iou: float = 0.30, wheels_down: bool = False,
                              candidates=None, verbose: bool = True):
    """Reference-anchored orientation gate (Phase 20, scalable).

    The reference image is the source of truth for which way the subject faces /
    stands. We render the freshly-imported mesh at each of the 24 axis-aligned
    orientations, mask each silhouette, and pick the rotation whose silhouette
    (aspect-preserved, so upright vs sideways is distinguishable) best matches the
    reference subject's silhouette (IoU). This replaces the fragile per-pattern
    hardcoded Euler and works for ANY subject — the same loop fixes the cat,
    fox, robot, etc. After choosing, it azimuth-normalizes (long horizontal → Y,
    for the side texture projection) and grounds to z=0.

    Returns {"ok": bool, "euler": (x,y,z), "iou": float} — ok=False (low score or
    error) means the caller should fall back to the legacy per-pattern Euler.
    """
    check_png = str((Path(work_dir) / "orient_silhouette_check.png").as_posix())
    tmp_png = str((Path(work_dir) / "_orient_tmp.png").as_posix())
    code = _ORIENT_SILHOUETTE_CODE
    for k, v in (("__HERO__", hero_name), ("__REF__", str(Path(ref_png).as_posix())),
                 ("__TMP__", tmp_png), ("__CHECK__", check_png), ("__RES__", "160"),
                 ("__MINIOU__", str(min_iou)), ("__WHEELSDOWN__", "1" if wheels_down else "0"),
                 ("__CANDS__", repr([list(c) for c in candidates]) if candidates else "None")):
        code = code.replace(k, v)
    try:
        res = runner.run("orient_silhouette", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] orient(silhouette): euler={info.get('euler')} "
                      f"IoU={info.get('iou')} (chose best of {info.get('tried')} orientations)")
            return info
        if verbose:
            print(f"[composer] orient(silhouette): low/again "
                  f"({info.get('reason') if info else 'no result'}, iou={info.get('iou') if info else '?'}) "
                  f"→ falling back to per-pattern Euler")
        return {"ok": False}
    except Exception as e:
        if verbose:
            print(f"[composer] orient(silhouette): failed ({type(e).__name__}: {e}) → per-pattern Euler")
        return {"ok": False}


# Runs fully inside Blender: builds the reference silhouette, renders the mesh at
# the 24 axis-aligned orientations, scores each by IoU, applies the best, then
# azimuth-normalizes + grounds. numpy + bpy available in the bridge process.
_ORIENT_SILHOUETTE_CODE = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector, Matrix

HERO="__HERO__"; REF=r"__REF__"; TMP=r"__TMP__"; CHECK=r"__CHECK__"
RES=__RES__; MIN_IOU=__MINIOU__
o=bpy.data.objects.get(HERO)
out={"ok":False,"reason":""}
try:
    if o is None or o.type!="MESH":
        raise RuntimeError("no hero mesh")
    o.rotation_mode="XYZ"

    def canvas(mask):
        ys,xs=np.where(mask)
        if len(xs)<20: return None
        y0,y1,x0,x1=ys.min(),ys.max(),xs.min(),xs.max()
        crop=mask[y0:y1+1,x0:x1+1].astype(np.float32)
        ch,cw=crop.shape; s=(RES-2)/max(ch,cw,1)
        nh=max(1,int(round(ch*s))); nw=max(1,int(round(cw*s)))
        yi=np.clip((np.arange(nh)/s).astype(int),0,ch-1)
        xi=np.clip((np.arange(nw)/s).astype(int),0,cw-1)
        small=crop[yi][:,xi]>0.5
        cv=np.zeros((RES,RES),bool); oy=(RES-nh)//2; ox=(RES-nw)//2
        cv[oy:oy+nh,ox:ox+nw]=small
        return cv

    # ── reference subject silhouette (saturated OR dark, border trimmed) ──
    rimg=bpy.data.images.load(REF, check_existing=True)
    rw,rh=rimg.size
    rp=np.array(rimg.pixels[:],dtype=np.float32).reshape(rh,rw,4)[::-1,:,:3]
    mx=rp.max(2); mn=rp.min(2); sat=(mx-mn)/(mx+1e-6)
    rm=((sat>0.18)|(mx<0.32))
    by=int(rh*0.04); bx=int(rw*0.04)
    tmpm=np.zeros_like(rm); tmpm[by:rh-by,bx:rw-bx]=rm[by:rh-by,bx:rw-bx]; rm=tmpm
    refc=canvas(rm)
    if refc is None: raise RuntimeError("empty reference mask")

    # ── temp ortho cam (looks -Y) + sun; render with transparent film for alpha ──
    cam=bpy.data.cameras.new("OCam"); cam.type='ORTHO'
    co=bpy.data.objects.new("OCam",cam); bpy.context.scene.collection.objects.link(co)
    sun=bpy.data.lights.new("OSun",type='SUN'); sun.energy=3.0
    so=bpy.data.objects.new("OSun",sun); bpy.context.scene.collection.objects.link(so)
    so.rotation_euler=(math.radians(60),0,math.radians(30))
    sc=bpy.context.scene
    prev=(sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,
          sc.render.filepath,sc.render.film_transparent)
    sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=RES; sc.render.resolution_y=RES
    sc.render.film_transparent=True; sc.camera=co

    # Candidate orientations: explicit list, or all 24 axis-aligned (dedupe by basis)
    CANDS=__CANDS__
    if CANDS:
        cands=[tuple(c) for c in CANDS]
    else:
        seen={}
        for rx in (0,90,180,270):
            for ry in (0,90,180,270):
                for rz in (0,90,180,270):
                    M=(Matrix.Rotation(math.radians(rz),4,'Z')@Matrix.Rotation(math.radians(ry),4,'Y')@Matrix.Rotation(math.radians(rx),4,'X')).to_3x3()
                    key=tuple(int(round(M[i][j])) for i in range(3) for j in range(3))
                    if key not in seen: seen[key]=(rx,ry,rz)
        cands=list(seen.values())

    def render_mask(eu):
        o.rotation_euler=(math.radians(eu[0]),math.radians(eu[1]),math.radians(eu[2]))
        bpy.context.view_layer.update()
        ws=[o.matrix_world@Vector(c) for c in o.bound_box]
        xs=[p.x for p in ws]; ys=[p.y for p in ws]; zs=[p.z for p in ws]
        cxw=(min(xs)+max(xs))/2; cyw=(min(ys)+max(ys))/2; czw=(min(zs)+max(zs))/2
        span=max(max(xs)-min(xs),max(zs)-min(zs),1e-3)
        cam.ortho_scale=span*1.18
        co.location=Vector((cxw, cyw-span*4.0, czw))
        ld=Vector((cxw,cyw,czw))-co.location; co.rotation_euler=ld.to_track_quat('-Z','Y').to_euler()
        sc.render.filepath=TMP; bpy.ops.render.render(write_still=True)
        ri=bpy.data.images.load(TMP, check_existing=False)
        rw2,rh2=ri.size
        a=np.array(ri.pixels[:],dtype=np.float32).reshape(rh2,rw2,4)[::-1,:,3]
        bpy.data.images.remove(ri)
        return canvas(a>0.5)

    # Score = IoU + vertical centre-of-mass match. CoM is the up/down
    # discriminator IoU alone misses: an upright quadruped's mass sits in the
    # UPPER half (body above thin legs); flipped, it sits low — and the
    # reference shows the correct distribution.
    def cmy(mask):
        ys,_=np.where(mask)
        return float(ys.mean())/mask.shape[0] if len(ys) else 0.5
    ref_cmy=cmy(refc)
    best_eu=None; best_iou=-1.0; best_score=-9.0
    for eu in cands:
        cm=render_mask(eu)
        if cm is None: continue
        inter=int(np.logical_and(cm,refc).sum()); uni=int(np.logical_or(cm,refc).sum())
        iou=inter/max(uni,1)
        score=iou - 2.0*abs(cmy(cm)-ref_cmy)
        if score>best_score: best_score=score; best_iou=iou; best_eu=eu

    # restore render settings; drop temp cam/sun
    sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,sc.render.filepath,sc.render.film_transparent=prev
    bpy.data.objects.remove(co,do_unlink=True); bpy.data.cameras.remove(cam)
    bpy.data.objects.remove(so,do_unlink=True); bpy.data.lights.remove(sun)

    if best_eu is None or best_iou < MIN_IOU:
        out={"ok":False,"reason":"low_iou","iou":round(max(best_iou,0),3),"tried":len(cands)}
    else:
        # apply best, then azimuth-normalize (long horizontal -> Y) + ground
        o.rotation_euler=(math.radians(best_eu[0]),math.radians(best_eu[1]),math.radians(best_eu[2]))
        bpy.context.view_layer.update()
        zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location.z-=min(zs)
        bpy.context.view_layer.update()
        xs0=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys0=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
        if (max(xs0)-min(xs0)) > (max(ys0)-min(ys0)):
            o.rotation_euler.z+=math.radians(90.0); bpy.context.view_layer.update()
            zs2=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location.z-=min(zs2)
            bpy.context.view_layer.update()
        flipped=0
        if __WHEELSDOWN__:
            # Vehicles: side silhouette is up/down-ambiguous to IoU, so tiebreak by
            # geometry — the wheeled UNDERSIDE is wider (in X) than the roof. If the
            # narrow band is at the bottom, the car is inverted → flip 180 about Y.
            Wv=np.array([list(o.matrix_world@v.co) for v in o.data.vertices], dtype=np.float64)
            Zv=Wv[:,2]; Xv=Wv[:,0]; z0,z1=Zv.min(),Zv.max(); Hh=max(z1-z0,1e-6)
            def xw(sel):
                return float(Xv[sel].max()-Xv[sel].min()) if int(sel.sum())>6 else 0.0
            if xw(Zv>z1-0.15*Hh) > xw(Zv<z0+0.15*Hh):   # wide roof, narrow bottom => inverted
                o.rotation_euler.y+=math.radians(180.0); bpy.context.view_layer.update()
                zs3=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location.z-=min(zs3)
                bpy.context.view_layer.update(); flipped=1
        out={"ok":True,"euler":list(best_eu),"iou":round(best_iou,3),"tried":len(cands),
             "wheels_flip":flipped,"post_dims":[round(d,3) for d in o.dimensions]}
    __result__=json.dumps(out)
except Exception as e:
    __result__=json.dumps({"ok":False,"reason":"{}: {}".format(type(e).__name__,e)})
'''


def _apply_texture_color_fidelity(runner, hero_name: str, ref_png: str, work_dir,
                                  verbose: bool = True):
    """Texture-fidelity gate (Phase 20, gate #2): make the textured hero's colors
    match the reference image. Renders the textured hero, measures its subject
    saturation/value, compares to the reference subject, and inserts a
    Hue/Saturation/Value correction into the hero material(s). Focuses on
    SATURATION (the 'dull / colors-off' fix) — value is clamped tight because the
    measurement render's lighting differs from the final scene. Reference-anchored
    and universal: same correction for animals, characters, vehicles. Returns
    {"ok", "sat_gain", "val_gain"} (never raises)."""
    tmp_png = str((Path(work_dir) / "_texfid_tmp.png").as_posix())
    code = _TEXFIDELITY_CODE
    for k, v in (("__HERO__", hero_name), ("__REF__", str(Path(ref_png).as_posix())),
                 ("__TMP__", tmp_png), ("__RES__", "256")):
        code = code.replace(k, v)
    try:
        res = runner.run("tex_fidelity", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] texture-fidelity: sat×{info.get('sat_gain')} val×{info.get('val_gain')} "
                      f"(ref S/V={info.get('ref_sv')} → hero S/V={info.get('hero_sv')})")
            return info
        if verbose:
            print(f"[composer] texture-fidelity: skipped ({info.get('reason') if info else 'no result'})")
        return {"ok": False}
    except Exception as e:
        if verbose:
            print(f"[composer] texture-fidelity: failed ({type(e).__name__}: {e})")
        return {"ok": False}


# Runs in Blender: render textured hero → mean subject S/V vs reference subject →
# insert a Hue/Saturation/Value node before each material's Base Color.
_TEXFIDELITY_CODE = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO="__HERO__"; REF=r"__REF__"; TMP=r"__TMP__"; RES=__RES__
o=bpy.data.objects.get(HERO)
out={"ok":False,"reason":""}
try:
    if o is None or o.type!="MESH":
        raise RuntimeError("no hero mesh")

    def sv_of(rgb, mask):
        if int(mask.sum())<30: return None
        r=rgb[:,:,0][mask]; g=rgb[:,:,1][mask]; b=rgb[:,:,2][mask]
        mxx=np.maximum(np.maximum(r,g),b); mnn=np.minimum(np.minimum(r,g),b)
        S=((mxx-mnn)/np.maximum(mxx,1e-4))
        return float(S.mean()), float(mxx.mean())

    # ── render the textured hero (front-ish ortho, transparent film) ──
    cam=bpy.data.cameras.new("FCam"); cam.type='ORTHO'
    co=bpy.data.objects.new("FCam",cam); bpy.context.scene.collection.objects.link(co)
    sun=bpy.data.lights.new("FSun",type='SUN'); sun.energy=3.0
    so=bpy.data.objects.new("FSun",sun); bpy.context.scene.collection.objects.link(so)
    so.rotation_euler=(math.radians(55),0,math.radians(35))
    sc=bpy.context.scene
    prev=(sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,
          sc.render.filepath,sc.render.film_transparent,sc.view_settings.view_transform,sc.world)
    sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=RES; sc.render.resolution_y=RES
    sc.render.film_transparent=True
    try: sc.view_settings.view_transform='Standard'   # measure raw colors, not tone-mapped
    except Exception: pass
    # Flat, bright, EVEN lighting so measured S/V reflects the true albedo (not
    # shadow). Without this the hero renders near-black and the gain maxes out.
    fw=bpy.data.worlds.new("FidWorld"); fw.use_nodes=True
    _bg=fw.node_tree.nodes.get("Background")
    if _bg: _bg.inputs["Color"].default_value=(1,1,1,1); _bg.inputs["Strength"].default_value=1.3
    sc.world=fw
    sun.energy=2.2
    ws=[o.matrix_world@Vector(c) for c in o.bound_box]
    xs=[p.x for p in ws]; ys=[p.y for p in ws]; zs=[p.z for p in ws]
    cxw=(min(xs)+max(xs))/2; cyw=(min(ys)+max(ys))/2; czw=(min(zs)+max(zs))/2
    span=max(max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs),1e-3)
    cam.ortho_scale=span*1.25
    co.location=Vector((cxw+span*0.6, cyw-span*4.0, czw+span*0.2))
    ld=Vector((cxw,cyw,czw))-co.location; co.rotation_euler=ld.to_track_quat('-Z','Y').to_euler()
    sc.camera=co; sc.render.filepath=TMP; bpy.ops.render.render(write_still=True)
    ri=bpy.data.images.load(TMP, check_existing=False)
    rw,rh=ri.size; arr=np.array(ri.pixels[:],dtype=np.float32).reshape(rh,rw,4)[::-1]
    bpy.data.images.remove(ri)
    hero_mask=arr[:,:,3]>0.5
    hsv_hero=sv_of(arr[:,:,:3], hero_mask)

    # restore render settings + world; drop temp cam/sun/world
    sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,sc.render.filepath,sc.render.film_transparent,sc.view_settings.view_transform,sc.world=prev
    bpy.data.objects.remove(co,do_unlink=True); bpy.data.cameras.remove(cam)
    bpy.data.objects.remove(so,do_unlink=True); bpy.data.lights.remove(sun)
    try: bpy.data.worlds.remove(fw)
    except Exception: pass
    if hsv_hero is None: raise RuntimeError("empty hero mask")

    # ── reference subject S/V ──
    rimg=bpy.data.images.load(REF, check_existing=True)
    rW,rH=rimg.size; rp=np.array(rimg.pixels[:],dtype=np.float32).reshape(rH,rW,4)[::-1,:,:3]
    mx2=rp.max(2); mn2=rp.min(2); sat2=(mx2-mn2)/(mx2+1e-6)
    rmask=((sat2>0.18)|(mx2<0.32))
    by=int(rH*0.05); bx=int(rW*0.05); mm=np.zeros_like(rmask); mm[by:rH-by,bx:rW-bx]=rmask[by:rH-by,bx:rW-bx]; rmask=mm
    hsv_ref=sv_of(rp, rmask)
    if hsv_ref is None: raise RuntimeError("empty reference mask")

    rS,rV=hsv_ref; hS,hV=hsv_hero
    # Conservative caps: the measurement render under-reads saturation (projection
    # coverage shows grey fallback), so the raw ratio over-shoots. Cap the boost so
    # dull assets are enriched without over-cooking already-vivid ones.
    sat_gain=float(np.clip(rS/max(hS,1e-3), 0.85, 1.7))
    val_gain=float(np.clip(rV/max(hV,1e-3), 0.92, 1.15))

    # ── insert Hue/Saturation/Value correction before each Base Color ──
    applied=0
    for mat in list(o.data.materials):
        if not mat or not mat.use_nodes: continue
        nt=mat.node_tree
        bsdf=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'), None)
        if bsdf is None: continue
        bc=bsdf.inputs.get('Base Color')
        if bc is None: continue
        hsv=nt.nodes.new('ShaderNodeHueSaturation')
        hsv.inputs['Saturation'].default_value=sat_gain
        hsv.inputs['Value'].default_value=val_gain
        if bc.is_linked:
            src=bc.links[0].from_socket
            nt.links.new(src, hsv.inputs['Color'])
        else:
            hsv.inputs['Color'].default_value=tuple(bc.default_value)
        nt.links.new(hsv.outputs['Color'], bc)
        applied+=1

    out={"ok":applied>0,"sat_gain":round(sat_gain,3),"val_gain":round(val_gain,3),
         "ref_sv":[round(rS,3),round(rV,3)],"hero_sv":[round(hS,3),round(hV,3)],
         "materials":applied}
    if applied==0: out["reason"]="no principled material"
    __result__=json.dumps(out)
except Exception as e:
    __result__=json.dumps({"ok":False,"reason":"{}: {}".format(type(e).__name__,e)})
'''


def _apply_reference_texture(runner, hero_name: str, ref_png: str,
                             flip_u: bool = False, flip_v: bool = False,
                             verbose: bool = True) -> bool:
    """Phase 19 texturing (projection half): project the SDXL reference photo
    onto the TripoSG mesh as a texture, giving it real color + facial features
    (eyes/nose/fur come straight from the photo).

    Headless-safe: computes per-vertex UVs by orthographic projection along the
    mesh's WIDTH axis (X) — u = length (Y), v = height (Z) — since the reference
    is a side profile. Both flanks receive the (mirrored) photo, which reads
    correctly for roughly-symmetric subjects. The img2img pass (later) unifies
    the far side. No viewport needed, no fiddly angle-matching.

    Key trick: SDXL references put the subject in the center over a near-uniform
    background, so a raw [0,1] UV map would paint the body with background gray.
    We detect the subject's CONTENT bounding box in the photo (foreground pixels
    vs. the border background color) and map the mesh extent onto exactly that
    box, so the dog's silhouette lands on the dog's pixels.
    """
    ref_png_posix = str(Path(ref_png).as_posix())

    # Detect subject content bbox so the mesh maps onto the dog's pixels, not the
    # background margin (else the body samples gray).
    x0, y0, x1, y1 = _detect_subject_bbox(ref_png, verbose=verbose)

    # Blender image V is bottom-up; numpy rows are top-down → invert.
    # mesh v=0 (feet) → photo bottom (row y1) ; mesh v=1 (head) → photo top (row y0)
    tv_lo = 1.0 - y1   # texture V at mesh v=0
    tv_hi = 1.0 - y0   # texture V at mesh v=1

    code = (
        "import bpy\n"
        "import numpy as np\n"
        f"o = bpy.data.objects.get('{hero_name}')\n"
        "if o and o.type == 'MESH':\n"
        "    me = o.data\n"
        "    nv = len(me.vertices)\n"
        "    # VECTORIZED: pull all local coords at once, apply world matrix via numpy.\n"
        "    co_local = np.empty(nv * 3, dtype=np.float64)\n"
        "    me.vertices.foreach_get('co', co_local)\n"
        "    co_local = co_local.reshape(nv, 3)\n"
        "    mw = np.array(o.matrix_world)\n"
        "    co = co_local @ mw[:3, :3].T + mw[:3, 3]\n"
        "    # project along X (width): u from Y (length), v from Z (height)\n"
        "    u = co[:, 1]; v = co[:, 2]\n"
        "    u = (u - u.min()) / max(u.max() - u.min(), 1e-6)\n"
        "    v = (v - v.min()) / max(v.max() - v.min(), 1e-6)\n"
        f"    if {flip_u}: u = 1.0 - u\n"
        f"    if {flip_v}: v = 1.0 - v\n"
        "    # Map normalized mesh extent onto the subject's content box in the photo.\n"
        f"    u = {x0!r} + u * ({x1!r} - {x0!r})\n"
        f"    v = {tv_lo!r} + v * ({tv_hi!r} - {tv_lo!r})\n"
        "    uvl = me.uv_layers.get('RefProj') or me.uv_layers.new(name='RefProj')\n"
        "    me.uv_layers.active = uvl\n"
        "    # VECTORIZED loop UVs: gather per-loop vertex indices, build flat (u,v)\n"
        "    # interleaved array, write in one foreach_set call (microseconds vs minutes).\n"
        "    nl = len(me.loops)\n"
        "    lvi = np.empty(nl, dtype=np.int32)\n"
        "    me.loops.foreach_get('vertex_index', lvi)\n"
        "    uvflat = np.empty(nl * 2, dtype=np.float64)\n"
        "    uvflat[0::2] = u[lvi]\n"
        "    uvflat[1::2] = v[lvi]\n"
        "    uvl.data.foreach_set('uv', uvflat)\n"
        "    img = bpy.data.images.load(r'" + ref_png_posix + "', check_existing=True)\n"
        "    mat = bpy.data.materials.new('RefTex')\n"
        "    mat.use_nodes = True\n"
        "    nt = mat.node_tree\n"
        "    bsdf = nt.nodes.get('Principled BSDF')\n"
        "    bsdf.inputs['Roughness'].default_value = 0.6\n"
        "    tex = nt.nodes.new('ShaderNodeTexImage')\n"
        "    tex.image = img\n"
        "    tex.extension = 'EXTEND'\n"
        "    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])\n"
        "    o.data.materials.clear()\n"
        "    o.data.materials.append(mat)\n"
        "    __result__ = 'textured'\n"
        "else:\n"
        "    __result__ = 'no hero'\n"
    )
    try:
        runner.run("ref_texture", "execute_python", {"code": code}, critical=False)
        if verbose:
            print(f"[composer] ref_texture: projected reference photo onto hero "
                  f"(flip_u={flip_u} flip_v={flip_v})")
        return True
    except Exception as e:
        if verbose:
            print(f"[composer] ref_texture failed ({type(e).__name__}: {e})")
        return False


def _render_self_view(runner, hero_name: str, out_png: str, view: str,
                      verbose: bool = True):
    """Render the hero from a tight orthographic camera along one axis into
    out_png. Returns framing {hmin,hmax,vmin,vmax,haxis} where the image's
    horizontal world axis is haxis ('X' or 'Y') and vertical is always Z, so
    back-projection maps exactly. Self-renders align to the mesh silhouette, so
    projecting them back never bleeds onto background (unlike the raw photo).

    view='xpos': camera on +X looking -X  (covers the flanks; horizontal=Y)
    view='ypos': camera on +Y looking -Y  (covers +Y faces; horizontal=X)
    view='yneg': camera on -Y looking +Y  (covers -Y faces; horizontal=X)
    """
    # (camera-offset expr, in-plane horizontal extent expr, horizontal axis,
    #  hmin/hmax centre coord)
    cfg = {
        "xpos": ("Vector((cx+dist, cy, cz))", "max(ymax-ymin,1e-4)", "Y", "cy"),
        "ypos": ("Vector((cx, cy+dist, cz))", "max(xmax-xmin,1e-4)", "X", "cx"),
        "yneg": ("Vector((cx, cy-dist, cz))", "max(xmax-xmin,1e-4)", "X", "cx"),
    }
    cam_loc, hext_expr, haxis, hcen = cfg[view]
    code = f"""
import bpy, math, json
from mathutils import Vector
o = bpy.data.objects.get('{hero_name}')
for nm in ('SelfCam','SelfLight','SelfFill'):
    ob = bpy.data.objects.get(nm)
    if ob: bpy.data.objects.remove(ob, do_unlink=True)
xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]
ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
zz=[(o.matrix_world@Vector(c)).z for c in o.bound_box]
xmin,xmax=min(xs),max(xs); zmin,zmax=min(zz),max(zz); ymin,ymax=min(ys),max(ys)
xext=max(xmax-xmin,1e-4); yext=max(ymax-ymin,1e-4); zext=max(zmax-zmin,1e-4)
cx=(xmin+xmax)/2.0; cz=(zmin+zmax)/2.0; cy=(ymin+ymax)/2.0
m=1.06
hext={hext_expr}
half=max(hext,zext)/2.0*m   # SQUARE frame on the larger in-plane dimension
cd=bpy.data.cameras.new('SelfCam'); cd.type='ORTHO'
cd.sensor_fit='AUTO'; cd.ortho_scale=2.0*half
cam=bpy.data.objects.new('SelfCam',cd); bpy.context.scene.collection.objects.link(cam)
dist=max(xext,yext,zext)*3.0
cam.location={cam_loc}
look=Vector((cx,cy,cz))-cam.location
cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
world=bpy.context.scene.world or bpy.data.worlds.new('SelfWorld')
bpy.context.scene.world=world; world.use_nodes=True
bg=world.node_tree.nodes.get('Background')
if bg: bg.inputs[0].default_value=(0.5,0.5,0.5,1.0); bg.inputs[1].default_value=0.9
ll=bpy.data.lights.new('SelfLight',type='SUN'); ll.energy=3.0
lo=bpy.data.objects.new('SelfLight',ll); bpy.context.scene.collection.objects.link(lo)
lo.rotation_euler=(cam.location-Vector((cx,cy,cz))).to_track_quat('Z','Y').to_euler()
bpy.context.scene.camera=cam
sc=bpy.context.scene
sc.render.engine='BLENDER_EEVEE'
res=1024
sc.render.resolution_x=res; sc.render.resolution_y=res
sc.render.film_transparent=False
try: sc.view_settings.view_transform='Standard'
except Exception: pass
sc.render.filepath=r'{out_png}'
bpy.ops.render.render(write_still=True)
bpy.data.objects.remove(cam, do_unlink=True)
bpy.data.objects.remove(lo, do_unlink=True)
hc={hcen}
__result__=json.dumps({{'hmin':hc-half,'hmax':hc+half,'vmin':cz-half,'vmax':cz+half,'haxis':'{haxis}'}})
"""
    res = runner.run("self_view", "execute_python", {"code": code}, critical=False)
    framing = None
    try:
        import json as _json
        raw = res.get("result") if isinstance(res, dict) else None
        framing = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        framing = None
    if verbose:
        print(f"[composer] self_view[{view}] -> {Path(out_png).name} framing={framing}")
    return framing


def _apply_multiview_texture(runner, hero_name: str, side_ref_png: str,
                             slots: Dict[str, Any], work_dir, run_id,
                             style: str = "photoreal", verbose: bool = True) -> bool:
    """Phase 19 texturing (full hybrid): cover ALL sides of the gray TripoSG mesh.

    1. Side reference photo → flanks (X projection, content-bbox aligned).
    2. Render the mesh's +Y and -Y self-views, img2img-refine each (reuses the
       Phase 16 refiner) into a coherent dog from that angle — this fills the
       gray feet / smear with real fur that respects the silhouette + depth.
    3. Back-project all three onto the mesh and blend in the shader weighted by
       each surface's world normal, so every point samples its best-facing view.

    Falls back to side-only projection if the refiner is unavailable.
    """
    from pathlib import Path as _P
    side_ref_png = str(_P(side_ref_png).as_posix())
    work_dir = _P(work_dir)

    # FLAT-BROWN SEED: paint the mesh a uniform subject-average color before the
    # self-renders. img2img then KEEPS that base color (no white-marking invention
    # the way a gray/patchy seed caused) while still adding fur + facial detail
    # (eyes/nose/mouth) from the depth/silhouette. Faces come from img2img of the
    # front self-view, projected back onto the actual face (self-render = aligned).
    seed_rgb = [0.32, 0.20, 0.11]
    try:
        from PIL import Image as _PI
        import numpy as _np
        _im = _np.asarray(_PI.open(side_ref_png).convert("RGB"), dtype=_np.float32)
        _mx = _im.max(axis=2); _mn = _im.min(axis=2)
        _fg = ((_mx - _mn) / (_mx + 1e-3) > 0.20) | (_im.mean(axis=2) < 55.0)
        if _fg.any():
            _s = _im[_fg].mean(axis=0) / 255.0
            seed_rgb = [float(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92)
                        for c in _s]
    except Exception:
        pass
    runner.run("seed_flat", "execute_python", {"code": (
        "import bpy\n"
        f"o=bpy.data.objects.get('{hero_name}')\n"
        "if o and o.type=='MESH':\n"
        "    m=bpy.data.materials.new('SeedFlat'); m.use_nodes=True\n"
        "    b=m.node_tree.nodes.get('Principled BSDF')\n"
        f"    b.inputs['Base Color'].default_value=({seed_rgb[0]},{seed_rgb[1]},{seed_rgb[2]},1.0)\n"
        "    b.inputs['Roughness'].default_value=0.7\n"
        "    o.data.materials.clear(); o.data.materials.append(m)\n"
        "    __result__='seeded'\n"
        "else:\n    __result__='no hero'\n"
    )}, critical=False)

    # Refiner availability gate.
    try:
        from ..refinement import refiner as _refiner
        refiner_ok = _refiner.is_available()
    except Exception as e:
        refiner_ok = False
        if verbose:
            print(f"[composer] multiview: refiner import failed ({type(e).__name__}: {e})")
    if not refiner_ok:
        if verbose:
            print("[composer] multiview: refiner unavailable → side-only texture")
        return True

    # FREE THE REFERENCE SDXL PIPELINE BEFORE ANY EEVEE RENDER. A resident SDXL
    # pipeline (~8 GB) starves the bridge's EEVEE renderer → the self-views come
    # back BLACK → the ±Y texture fill is black (the two-tone/bare-rear bug). The
    # reference image is already generated by now, so this is safe + frees VRAM
    # for both the self-view renders AND the upcoming refiner load.
    try:
        from ..asset_gen.reference import unload_reference_pipeline
        unload_reference_pipeline()
        if verbose:
            print("[composer] multiview: reference VRAM released (pre-render)")
    except Exception:
        pass

    # ── 2a. Render BOTH self-views FIRST (bridge EEVEE) ──────────────────────
    # Order matters: every bridge render must finish before the first img2img
    # loads the refiner pipeline (same VRAM-starvation reason).
    renders = {}
    for view in ("xpos", "ypos", "yneg"):
        raw_png = work_dir / f"selfview_{view}_{run_id}.png"
        framing = _render_self_view(runner, hero_name, str(raw_png.as_posix()),
                                    view, verbose=verbose)
        if not (raw_png.exists() and framing is not None):
            if verbose:
                print(f"[composer] multiview: {view} render missing → skip")
            continue
        # Black-frame guard: never project a black render onto the mesh. If the
        # render came back dark (EEVEE GPU/VRAM hiccup), drop this view so the
        # blend falls back to the other views instead of painting it black.
        try:
            from PIL import Image as _PILImg
            import numpy as _np
            mean_lum = float(_np.asarray(_PILImg.open(raw_png).convert("L")).mean())
        except Exception:
            mean_lum = 255.0
        if mean_lum < 6.0:
            if verbose:
                print(f"[composer] multiview: {view} render is BLACK "
                      f"(lum={mean_lum:.1f}) → dropping view")
            continue
        renders[view] = {"raw": raw_png, "framing": framing}

    # ── 2b. img2img-refine each rendered view (host GPU) ─────────────────────
    # Prefer depth-locked SDXL ControlNet img2img (isolated venv_triposg subprocess)
    # — keeps detail aligned to geometry (de-clay, sharper fur/face). Fall back to
    # the main-venv plain img2img if the subprocess path is unavailable.
    use_cn = False
    try:
        use_cn = _refiner.is_controlnet_available()
    except Exception:
        use_cn = False
    if verbose:
        print(f"[composer] multiview: refiner = "
              f"{'controlnet-depth (venv_triposg)' if use_cn else 'plain img2img'}")
    views = {}
    out_map = {view: work_dir / f"selfview_{view}_{run_id}.refined.png"
               for view in renders}

    refined_ok = set()
    if use_cn:
        # Depth-locked ControlNet img2img, BATCHED in one subprocess (loads the
        # ~10 GB pipeline once). Higher strength for real fur/face detail; the
        # depth ControlNet at a moderate scale holds the geometry so the strength
        # can't drift the shape or add limbs (tuned: 0.72 / 0.45).
        jobs = [(str(renders[v]["raw"]), str(out_map[v])) for v in renders]
        try:
            _refiner.refine_frames_controlnet(jobs, slots, style=style,
                                              strength=0.72, steps=28, seed=42,
                                              controlnet_scale=0.45)
            refined_ok = {v for v in renders if out_map[v].exists()}
        except Exception as e:
            if verbose:
                print(f"[composer] multiview: controlnet batch failed "
                      f"({type(e).__name__}: {e}) → falling back to plain img2img")

    for view, info in renders.items():
        ref_out = out_map[view]
        try:
            if view not in refined_ok:  # plain fallback (or non-CN path)
                _refiner.refine_frame(str(info["raw"]), slots, style=style,
                                      strength=0.55, steps=22, seed=42,
                                      output_path=str(ref_out))
            views[view] = {"png": str(ref_out.as_posix()), **info["framing"]}
            if verbose:
                print(f"[composer] multiview: {view} refined → {ref_out.name}")
        except Exception as e:
            if verbose:
                print(f"[composer] multiview: {view} refine failed ({type(e).__name__}: {e})")

    # ── 2c. Free SDXL VRAM so the FINAL video render isn't black ─────────────
    try:
        _refiner.unload()
        if verbose:
            print("[composer] multiview: refiner VRAM released")
    except Exception:
        pass

    if not views:
        if verbose:
            print("[composer] multiview: no refined views → side-only texture")
        return True

    # ── 3. Build the blended material from the (up-to-3) self-renders ─────────
    ok = _build_multiview_material(runner, hero_name, side_ref_png, views,
                                   verbose=verbose)
    return ok


def _build_multiview_material(runner, hero_name, side_ref_png, views,
                              verbose=True) -> bool:
    """Assemble a material that samples the per-axis self-renders (xpos=flanks,
    ypos/yneg=front/back) via projective UV layers and blends them by world
    normal, with an average-color fallback so nothing is ever bare/gray.

    All inputs are SELF-RENDERS (rendered from the mesh, then img2img-colored),
    so each projects back onto its own silhouette exactly — no background bleed
    and no proportional drift (the old raw-photo side projection's failure mode).
    """
    import json as _json
    # Average subject color (from the reference photo) → fallback base so any
    # low-coverage spot reads dog-colored, never gray. sRGB→linear to match.
    avg = [0.35, 0.22, 0.12]
    try:
        from PIL import Image
        import numpy as _np
        im = _np.asarray(Image.open(side_ref_png).convert("RGB"), dtype=_np.float32)
        mx = im.max(axis=2); mn = im.min(axis=2)
        fg = ((mx - mn) / (mx + 1e-3) > 0.20) | (im.mean(axis=2) < 55.0)
        if fg.any():
            srgb = (im[fg].mean(axis=0) / 255.0)
            avg = [float(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92)
                   for c in srgb]
    except Exception:
        pass
    # Per-view config: (uv name, flip_u, depth axis, depth sign, vcolor channel).
    # The depth axis/sign give the view's camera direction for the occlusion test;
    # the channel packs that view's per-vertex weight into R/G/B of a color attr.
    spec = {
        "xpos": ("RefProjX",  False, "X",  1.0, 0),
        "ypos": ("RefProjYp", True,  "Y",  1.0, 1),
        "yneg": ("RefProjYn", False, "Y", -1.0, 2),
    }
    vlist = []
    for name, v in views.items():
        if name in spec and v:
            uvn, flip, dax, dsign, ch = spec[name]
            vlist.append({"uv": uvn, "flip": flip, "png": v["png"],
                          "hmin": v["hmin"], "hmax": v["hmax"],
                          "vmin": v["vmin"], "vmax": v["vmax"], "haxis": v["haxis"],
                          "dax": dax, "dsign": dsign, "ch": ch})
    payload = {"hero": hero_name, "avg": avg, "views": vlist}
    code = '''
import bpy, numpy as np, json
P = json.loads(%r)
o = bpy.data.objects.get(P["hero"])
if not (o and o.type == "MESH"):
    __result__ = "no hero"
else:
    me = o.data
    nv = len(me.vertices)
    M = np.array(o.matrix_world)
    co_local = np.empty(nv*3, dtype=np.float64); me.vertices.foreach_get("co", co_local)
    co = co_local.reshape(nv,3) @ M[:3,:3].T + M[:3,3]
    nrm = np.empty(nv*3, dtype=np.float64); me.vertices.foreach_get("normal", nrm)
    wn = nrm.reshape(nv,3) @ M[:3,:3].T
    wn /= (np.linalg.norm(wn, axis=1, keepdims=True) + 1e-9)
    X, Y, Z = co[:,0], co[:,1], co[:,2]
    nl = len(me.loops)
    lvi = np.empty(nl, dtype=np.int32); me.loops.foreach_get("vertex_index", lvi)
    def set_uv(name, u, v):
        uvl = me.uv_layers.get(name) or me.uv_layers.new(name=name)
        flat = np.empty(nl*2, dtype=np.float64)
        flat[0::2] = u[lvi]; flat[1::2] = v[lvi]
        uvl.data.foreach_set("uv", flat)
    RES = 256
    vcol = np.zeros((nv,3), dtype=np.float64)
    for vw in P["views"]:
        H = Y if vw["haxis"] == "Y" else X
        u = (H - vw["hmin"]) / max(vw["hmax"]-vw["hmin"], 1e-6)
        vv = (Z - vw["vmin"]) / max(vw["vmax"]-vw["vmin"], 1e-6)
        set_uv(vw["uv"], (1.0 - u) if vw["flip"] else u, vv)
        # OCCLUSION (z-buffer): a vertex only gets this view if it is the FRONTMOST
        # surface toward the view camera at its projected pixel. Kills the bleed of
        # face features onto the neck/chest hidden behind the head.
        D = (X if vw["dax"] == "X" else Y) * vw["dsign"]
        ncomp = (wn[:,0] if vw["dax"] == "X" else wn[:,1]) * vw["dsign"]
        ui = np.clip((u*RES).astype(np.int64), 0, RES-1)
        vi = np.clip((vv*RES).astype(np.int64), 0, RES-1)
        idx = vi*RES + ui
        maxd = np.full(RES*RES, -1e18); np.maximum.at(maxd, idx, D)
        span = float(D.max() - D.min()) + 1e-6
        vis = (D >= maxd[idx] - 0.04*span).astype(np.float64)
        vcol[:, vw["ch"]] = np.clip(ncomp, 0.0, None)**2 * vis
    ca = me.color_attributes.get("ProjW")
    if ca is None:
        ca = me.color_attributes.new(name="ProjW", type="FLOAT_COLOR", domain="POINT")
    rgba = np.zeros((nv,4), dtype=np.float64); rgba[:,:3] = vcol; rgba[:,3] = 1.0
    ca.data.foreach_set("color", rgba.ravel())

    mat = bpy.data.materials.new("RefTexMV"); mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.6
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "ProjW"
    try: attr.attribute_type = "GEOMETRY"
    except Exception: pass
    sepc = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(attr.outputs["Color"], sepc.inputs["Color"])
    chan = {0: "Red", 1: "Green", 2: "Blue"}
    def img_node(path, uvname):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(path, check_existing=True)
        t.extension = "EXTEND"
        uvm = nt.nodes.new("ShaderNodeUVMap"); uvm.uv_map = uvname
        nt.links.new(uvm.outputs["UV"], t.inputs["Vector"])
        return t
    contribs = []  # (color_socket, weight_socket)
    for vw in P["views"]:
        t = img_node(vw["png"], vw["uv"])
        contribs.append((t.outputs["Color"], sepc.outputs[chan[vw["ch"]]]))
    base_rgb = nt.nodes.new("ShaderNodeRGB")
    base_rgb.outputs[0].default_value = (P["avg"][0], P["avg"][1], P["avg"][2], 1.0)
    base_w = nt.nodes.new("ShaderNodeValue"); base_w.outputs[0].default_value = 0.10
    contribs.append((base_rgb.outputs["Color"], base_w.outputs["Value"]))
    def addv(a, b):
        n = nt.nodes.new("ShaderNodeMath"); n.operation = "ADD"
        nt.links.new(a, n.inputs[0]); nt.links.new(b, n.inputs[1]); return n.outputs["Value"]
    total = None
    for _, w in contribs:
        total = w if total is None else addv(total, w)
    teps = nt.nodes.new("ShaderNodeMath"); teps.operation = "ADD"; teps.inputs[1].default_value = 1e-4
    nt.links.new(total, teps.inputs[0])
    acc = None
    for c, w in contribs:
        sc = nt.nodes.new("ShaderNodeVectorMath"); sc.operation = "SCALE"
        nt.links.new(c, sc.inputs[0]); nt.links.new(w, sc.inputs["Scale"])
        if acc is None:
            acc = sc.outputs["Vector"]
        else:
            ad = nt.nodes.new("ShaderNodeVectorMath"); ad.operation = "ADD"
            nt.links.new(acc, ad.inputs[0]); nt.links.new(sc.outputs["Vector"], ad.inputs[1]); acc = ad.outputs["Vector"]
    invt = nt.nodes.new("ShaderNodeMath"); invt.operation = "DIVIDE"; invt.inputs[0].default_value = 1.0
    nt.links.new(teps.outputs["Value"], invt.inputs[1])
    fin = nt.nodes.new("ShaderNodeVectorMath"); fin.operation = "SCALE"
    nt.links.new(acc, fin.inputs[0]); nt.links.new(invt.outputs["Value"], fin.inputs["Scale"])
    nt.links.new(fin.outputs["Vector"], bsdf.inputs["Base Color"])
    o.data.materials.clear(); o.data.materials.append(mat)
    __result__ = "mv-occlusion:%%d" %% len(contribs)
''' % (_json.dumps(payload),)
    try:
        runner.run("multiview_mat", "execute_python", {"code": code}, critical=False)
        if verbose:
            print(f"[composer] multiview material: blended {len(vlist)} self-render "
                  f"projections ({', '.join(views.keys())}) by normal")
        return True
    except Exception as e:
        if verbose:
            print(f"[composer] multiview material failed ({type(e).__name__}: {e})")
        return False


def _build_realistic_environment(runner, setting: str, mood: str, hero_name: str,
                                 verbose: bool = True):
    """Phase 19.5: real-world backdrop for terrain settings (desert/mountain/snow)
    via SRTM/DEM elevation, with the hero placed ON the terrain. Returns the env
    type string on success, else None so the caller falls back to the procedural
    environment. Keeps the hero the subject — the existing camera frames it and
    the real terrain recedes behind. No world volumes (those black-render EEVEE).
    """
    # ── Phase 19.5 #104: HERO-IN-CITY — real OSM buildings around the hero ──
    if setting in ("street", "night_city"):
        from pathlib import Path as _P
        import math as _m
        try:
            from . import osm_city
        except Exception as e:
            if verbose:
                print(f"[composer] city_env: osm_city import failed ({e})")
            return None
        cache_osm = _P(__file__).resolve().parents[2] / "renders" / "_blosm_cache" / "osm" / "map.osm"
        try:
            if not cache_osm.exists():
                bb = osm_city.make_bbox(*osm_city.CITY_CENTERS["new_york"], radius_m=350)
                osm_city.fetch_osm(*bb, cache_osm)
            data = osm_city.parse_osm(cache_osm)
        except Exception as e:
            if verbose:
                print(f"[composer] city_env: OSM unavailable ({type(e).__name__}) → procedural")
            return None

        def _ctr(b):
            xs = [p[0] for p in b["footprint"]]; ys = [p[1] for p in b["footprint"]]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
        # Clear a ~18m plaza around the hero (origin) and trim the far fringe.
        data["buildings"] = [b for b in data.get("buildings", [])
                             if 18.0 < _m.hypot(*_ctr(b)) < 320.0]
        night = (setting == "night_city") or any(
            k in (mood or "").lower() for k in ("night", "moon", "dark"))
        ext = osm_city.build_city(runner, data, cache_osm.parent, night=night, verbose=verbose)
        if not ext:
            return None
        # Street ground + sky + sun (no world volumes — they black-render EEVEE).
        if night:
            c_sun_e, c_sun_col, c_elev, c_azim = 0.8, (0.55, 0.62, 0.95), 35, 200
            c_lo, c_hi = (0.07, 0.08, 0.14), (0.01, 0.01, 0.04)
        else:
            c_sun_e, c_sun_col, c_elev, c_azim = 3.8, (1.0, 0.85, 0.62), 55, 130
            c_lo, c_hi = (0.85, 0.72, 0.55), (0.35, 0.5, 0.75)
        city_code = (
            "import bpy, math\n"
            "bpy.ops.mesh.primitive_plane_add(size=900, location=(0,0,-0.02))\n"
            "gp=bpy.context.active_object; gm=bpy.data.materials.new('Asphalt'); gm.use_nodes=True\n"
            "gb=gm.node_tree.nodes.get('Principled BSDF')\n"
            "gb.inputs['Base Color'].default_value=(0.07,0.07,0.08,1); gb.inputs['Roughness'].default_value=0.9\n"
            "gp.data.materials.append(gm)\n"
            f"sun=bpy.data.lights.new('CitySun',type='SUN'); sun.energy={c_sun_e}; sun.color=({c_sun_col[0]},{c_sun_col[1]},{c_sun_col[2]}); sun.angle=math.radians(1.5)\n"
            "so=bpy.data.objects.new('CitySun',sun); bpy.context.scene.collection.objects.link(so)\n"
            f"so.rotation_euler=(math.radians({c_elev}),0,math.radians({c_azim}))\n"
            "w=bpy.context.scene.world or bpy.data.worlds.new('W'); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree\n"
            "for n in list(wn.nodes): wn.nodes.remove(n)\n"
            "out=wn.nodes.new('ShaderNodeOutputWorld'); bgn=wn.nodes.new('ShaderNodeBackground')\n"
            "grad=wn.nodes.new('ShaderNodeTexGradient'); ramp=wn.nodes.new('ShaderNodeValToRGB')\n"
            "mapp=wn.nodes.new('ShaderNodeMapping'); texco=wn.nodes.new('ShaderNodeTexCoord')\n"
            f"ramp.color_ramp.elements[0].position=0.38; ramp.color_ramp.elements[0].color=({c_lo[0]},{c_lo[1]},{c_lo[2]},1)\n"
            f"ramp.color_ramp.elements[1].position=0.62; ramp.color_ramp.elements[1].color=({c_hi[0]},{c_hi[1]},{c_hi[2]},1)\n"
            "mapp.inputs['Rotation'].default_value=(math.radians(90),0,0)\n"
            "wn.links.new(texco.outputs['Generated'],mapp.inputs['Vector']); wn.links.new(mapp.outputs['Vector'],grad.inputs['Vector'])\n"
            "wn.links.new(grad.outputs['Fac'],ramp.inputs['Fac']); wn.links.new(ramp.outputs['Color'],bgn.inputs['Color'])\n"
            "bgn.inputs['Strength'].default_value=0.7; wn.links.new(bgn.outputs['Background'],out.inputs['Surface'])\n"
            "__result__='city_dressed'\n"
        )
        runner.run("city_env", "execute_python", {"code": city_code}, critical=False)
        if verbose:
            print(f"[composer] city_env: hero-in-city ({'night' if night else 'day'}, "
                  f"{len(data['buildings'])} buildings, plaza cleared)")
        return "city"

    cfg = {
        "desert": ("namib_desert", "sand"),
        "mountain": ("mountains_alps", "rock"),
        "snow": ("mountains_alps", "snow"),
    }
    if setting not in cfg:
        return None
    preset, kind = cfg[setting]
    from pathlib import Path as _P
    try:
        from . import dem_terrain
    except Exception as e:
        if verbose:
            print(f"[composer] realistic_env: dem_terrain import failed ({e})")
        return None
    lat, lon = dem_terrain.TERRAIN_PRESETS[preset]
    cache = _P(__file__).resolve().parents[2] / "renders" / "_realistic_cache"
    ext = dem_terrain.build_terrain(runner, lat, lon, cache, z=12, crop=90,
                                    target_span_m=500.0, verbose=verbose)
    if not ext:
        return None

    # mood → sun + sky
    m = (mood or "").lower()
    if any(k in m for k in ("golden", "sunset", "sunrise", "dusk", "dawn")):
        sun_e, sun_col, elev, azim = 4.0, (1.0, 0.78, 0.5), 64, 118
        sky_lo, sky_hi = (0.97, 0.74, 0.45), (0.5, 0.62, 0.85)
    elif any(k in m for k in ("night", "moon", "dark")):
        sun_e, sun_col, elev, azim = 1.2, (0.6, 0.7, 1.0), 50, 200
        sky_lo, sky_hi = (0.10, 0.12, 0.2), (0.02, 0.03, 0.07)
    else:  # noon / daylight
        sun_e, sun_col, elev, azim = 4.5, (1.0, 0.96, 0.9), 80, 135
        sky_lo, sky_hi = (0.8, 0.85, 0.92), (0.4, 0.55, 0.85)
    mats = {
        "sand": ((0.6, 0.42, 0.25), (0.86, 0.71, 0.47), 0.96),
        "rock": ((0.28, 0.25, 0.22), (0.52, 0.46, 0.4), 0.95),
        "snow": ((0.7, 0.74, 0.82), (0.95, 0.96, 1.0), 0.45),
    }
    c0, c1, rough = mats[kind]

    code = (
        "import bpy, math\n"
        "from mathutils import Vector\n"
        "ob=bpy.data.objects.get('Terrain'); o=bpy.data.objects.get('" + str(hero_name) + "')\n"
        "if ob and o:\n"
        "    m=bpy.data.materials.new('Terrain'); m.use_nodes=True; nt=m.node_tree\n"
        "    bsdf=nt.nodes.get('Principled BSDF'); bsdf.inputs['Roughness'].default_value=" + repr(rough) + "\n"
        "    ns=nt.nodes.new('ShaderNodeTexNoise'); ns.inputs['Scale'].default_value=20.0\n"
        "    rp=nt.nodes.new('ShaderNodeValToRGB')\n"
        "    rp.color_ramp.elements[0].color=(" + f"{c0[0]},{c0[1]},{c0[2]},1)\n"
        "    rp.color_ramp.elements[1].color=(" + f"{c1[0]},{c1[1]},{c1[2]},1)\n"
        "    nt.links.new(ns.outputs['Fac'],rp.inputs['Fac']); nt.links.new(rp.outputs['Color'],bsdf.inputs['Base Color'])\n"
        "    ob.data.materials.clear(); ob.data.materials.append(m)\n"
        "    # sit the hero ON the terrain: move hero aside, raycast terrain at its XY\n"
        "    hx,hy=o.location.x,o.location.y; o.location.z+=1000.0; bpy.context.view_layer.update()\n"
        "    dg=bpy.context.view_layer.depsgraph\n"
        "    hit,loc,nrm,idx,obj,mw=bpy.context.scene.ray_cast(dg,Vector((hx,hy,400.0)),Vector((0,0,-1)))\n"
        "    tz=loc.z if hit else 0.0; o.location.z-=1000.0; bpy.context.view_layer.update()\n"
        "    zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location.z+=(tz-min(zs)+0.02); bpy.context.view_layer.update()\n"
        "    # sky gradient world\n"
        "    w=bpy.context.scene.world or bpy.data.worlds.new('W'); bpy.context.scene.world=w; w.use_nodes=True; wn=w.node_tree\n"
        "    for n in list(wn.nodes): wn.nodes.remove(n)\n"
        "    wo=wn.nodes.new('ShaderNodeOutputWorld'); wb=wn.nodes.new('ShaderNodeBackground')\n"
        "    gd=wn.nodes.new('ShaderNodeTexGradient'); rr=wn.nodes.new('ShaderNodeValToRGB')\n"
        "    mp=wn.nodes.new('ShaderNodeMapping'); tc=wn.nodes.new('ShaderNodeTexCoord')\n"
        "    rr.color_ramp.elements[0].position=0.45; rr.color_ramp.elements[0].color=(" + f"{sky_lo[0]},{sky_lo[1]},{sky_lo[2]},1)\n"
        "    rr.color_ramp.elements[1].position=0.62; rr.color_ramp.elements[1].color=(" + f"{sky_hi[0]},{sky_hi[1]},{sky_hi[2]},1)\n"
        "    mp.inputs['Rotation'].default_value=(math.radians(90),0,0)\n"
        "    wn.links.new(tc.outputs['Generated'],mp.inputs['Vector']); wn.links.new(mp.outputs['Vector'],gd.inputs['Vector'])\n"
        "    wn.links.new(gd.outputs['Fac'],rr.inputs['Fac']); wn.links.new(rr.outputs['Color'],wb.inputs['Color'])\n"
        "    wb.inputs['Strength'].default_value=1.0; wn.links.new(wb.outputs['Background'],wo.inputs['Surface'])\n"
        "    # key sun\n"
        "    for nm in ('EnvSun',):\n"
        "        eo=bpy.data.objects.get(nm)\n"
        "        if eo: bpy.data.objects.remove(eo,do_unlink=True)\n"
        "    sd=bpy.data.lights.new('EnvSun',type='SUN'); sd.energy=" + repr(sun_e) + "; sd.color=(" + f"{sun_col[0]},{sun_col[1]},{sun_col[2]}); sd.angle=math.radians(1.0)\n"
        "    sl=bpy.data.objects.new('EnvSun',sd); bpy.context.scene.collection.objects.link(sl)\n"
        "    sl.rotation_euler=(math.radians(" + f"{elev}),0,math.radians({azim}))\n"
        "    try: bpy.context.scene.eevee.use_gtao=True\n"
        "    except Exception: pass\n"
        "    __result__='realistic:" + setting + "'\n"
        "else:\n    __result__='no terrain/hero'\n"
    )
    try:
        runner.run("realistic_env", "execute_python", {"code": code}, critical=False)
        if verbose:
            print(f"[composer] realistic_env: {setting} → DEM '{preset}' ({kind}), "
                  f"hero placed on terrain")
        return "dem"
    except Exception as e:
        if verbose:
            print(f"[composer] realistic_env failed ({type(e).__name__}: {e})")
        return None


def _build_environment(runner, env_spec: Dict[str, Any], verbose: bool = True) -> bool:
    """Realize a resolved environment spec (see patterns.environment.resolve_environment)
    entirely via execute_python: gradient sky world, sun, textured procedural
    ground, volumetric fog, and color management. No addon changes required.
    """
    import json
    spec_json = json.dumps(env_spec)
    # NOTE: %r embeds the JSON safely as a Python string literal — avoids
    # f-string brace collisions with all the bpy node code below.
    code = '''
import bpy, json, math
from mathutils import Vector

S = json.loads(%r)
g = S["ground"]; sky = S["sky"]; sun = S["sun"]; fog = S["fog"]; post = S.get("post", {})

# ── 1. WORLD: vertical gradient sky (+ optional fog volume) ───────────────
world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
nt = world.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputWorld")
bg = nt.nodes.new("ShaderNodeBackground")
bg.inputs["Strength"].default_value = float(sky["strength"])
texco = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
mr = nt.nodes.new("ShaderNodeMapRange")
mr.inputs["From Min"].default_value = -0.3
mr.inputs["From Max"].default_value = 0.7
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position = 0.0
ramp.color_ramp.elements[0].color = (sky["horizon"][0], sky["horizon"][1], sky["horizon"][2], 1.0)
ramp.color_ramp.elements[1].position = 1.0
ramp.color_ramp.elements[1].color = (sky["zenith"][0], sky["zenith"][1], sky["zenith"][2], 1.0)
nt.links.new(texco.outputs["Generated"], sep.inputs["Vector"])
nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

# optional fog as a world volume (cinematic atmospheric depth)
if float(fog.get("density", 0.0)) > 0.0005:
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = float(fog["density"])
    fc = fog["color"]
    try:
        vol.inputs["Color"].default_value = (fc[0], fc[1], fc[2], 1.0)
    except Exception:
        pass
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    try:
        bpy.context.scene.eevee.use_volumetric_lights = True
    except Exception:
        pass

# ── 2. SUN light from elevation/azimuth ──────────────────────────────────
for o in [o for o in bpy.context.scene.objects if o.type == "LIGHT" and o.name.startswith("EnvSun")]:
    bpy.data.objects.remove(o, do_unlink=True)
sd = bpy.data.lights.new("EnvSun", type="SUN")
sd.energy = float(sun["energy"])
sc = sun["color"]; sd.color = (sc[0], sc[1], sc[2])
try:
    sd.angle = math.radians(2.0)   # soft-ish sun for nicer shadows
except Exception:
    pass
so = bpy.data.objects.new("EnvSun", sd)
bpy.context.scene.collection.objects.link(so)
elev = math.radians(float(sun["elevation"]))
azim = math.radians(float(sun["azimuth"]))
# point the sun: rotate so -Z aims along the chosen elevation/azimuth
so.rotation_euler = (math.radians(90.0) - elev, 0.0, azim)

# ── 3. GROUND: large plane + procedural material per kind ────────────────
kind = g["kind"]
if kind != "void":
    # remove old env ground
    old = bpy.data.objects.get("EnvGround")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "EnvGround"
    mat = bpy.data.materials.new("EnvGroundMat")
    mat.use_nodes = True
    mnt = mat.node_tree
    for n in list(mnt.nodes):
        mnt.nodes.remove(n)
    mout = mnt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = mnt.nodes.new("ShaderNodeBsdfPrincipled")
    col = g["color"]
    bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
    bsdf.inputs["Roughness"].default_value = float(g["roughness"])
    # surface relief via noise->bump for natural kinds
    if kind in ("grass", "sand", "concrete", "rock", "snow", "wood"):
        noise = mnt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = {"grass": 120.0, "sand": 60.0, "concrete": 30.0, "rock": 18.0, "snow": 40.0, "wood": 8.0}.get(kind, 30.0)
        noise.inputs["Detail"].default_value = 6.0
        bump = mnt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = {"grass": 0.5, "sand": 0.3, "concrete": 0.25, "rock": 0.7, "snow": 0.15, "wood": 0.2}.get(kind, 0.3)
        mnt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        mnt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        # two-tone color variation for organic kinds
        if kind in ("grass", "sand", "rock"):
            cramp = mnt.nodes.new("ShaderNodeValToRGB")
            darker = (col[0]*0.7, col[1]*0.7, col[2]*0.7, 1.0)
            cramp.color_ramp.elements[0].color = darker
            cramp.color_ramp.elements[1].color = (col[0], col[1], col[2], 1.0)
            cnoise = mnt.nodes.new("ShaderNodeTexNoise")
            cnoise.inputs["Scale"].default_value = 8.0
            mnt.links.new(cnoise.outputs["Fac"], cramp.inputs["Fac"])
            mnt.links.new(cramp.outputs["Color"], bsdf.inputs["Base Color"])
    if kind == "water":
        bsdf.inputs["Roughness"].default_value = 0.05
        try:
            bsdf.inputs["Transmission Weight"].default_value = 0.3
        except Exception:
            pass
        wave = mnt.nodes.new("ShaderNodeTexNoise")
        wave.inputs["Scale"].default_value = 6.0
        bump = mnt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        mnt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
        mnt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mnt.links.new(bsdf.outputs["BSDF"], mout.inputs["Surface"])
    ground.data.materials.clear()
    ground.data.materials.append(mat)

# ── 4. Color management (exposure + cinematic look) ──────────────────────
vs = bpy.context.scene.view_settings
try:
    vs.exposure = float(post.get("exposure", 0.0))
except Exception:
    pass
try:
    sat = float(post.get("saturation", 1.0))
    vs.look = "AgX - Punchy" if sat > 1.2 else "AgX - Base"
except Exception:
    try:
        vs.look = "Medium High Contrast"
    except Exception:
        pass

__result__ = {"setting": S.get("_setting"), "mood": S.get("_mood"), "ground_kind": kind, "fog": float(fog.get("density", 0.0))}
''' % spec_json
    try:
        runner.run("environment", "execute_python", {"code": code}, critical=False)
        if verbose:
            print(f"[composer] environment: setting={env_spec.get('_setting')} "
                  f"mood={env_spec.get('_mood')} style={env_spec.get('_style')} "
                  f"ground={env_spec['ground']['kind']} fog={env_spec['fog'].get('density')}")
        return True
    except Exception as e:
        if verbose:
            print(f"[composer] environment build failed ({type(e).__name__}: {e})")
        return False


def _camera_position_for_framing(framing: str, angle: str, hero_loc: List[float], hero_scale: float) -> Tuple[List[float], List[float]]:
    """Compute camera location based on slot framing + angle. Returns (cam_xyz, target_xyz).

    Distances tuned so a 2m subject occupies ~40-55% of frame diagonal (the
    sweet spot HERO_VERIFY wants: [35%, 70%]).
    """
    # Tighter — previous values were leaving subjects at 14-27% fill. Target 40-55%.
    distances = {"close": 3.2, "medium": 4.8, "wide": 7.5, "ultrawide": 12.0}
    d = distances.get(framing, 4.8) * max(0.5, hero_scale)

    hx, hy, hz = hero_loc

    if angle == "front":
        cam = [hx, hy - d, hz + 0.5]
    elif angle == "side":
        cam = [hx + d, hy, hz + 0.5]
    elif angle == "above":
        cam = [hx, hy - d * 0.3, hz + d * 0.9]
    elif angle == "below":
        cam = [hx, hy - d * 0.7, hz - d * 0.3]
    else:  # three-quarter (default)
        # Was hz + d*0.45 → camera way too high, looked DOWN at subject.
        # 0.15 keeps it closer to subject eye level for asset-gen meshes
        # without losing the "slightly above" cinematic feel.
        cam = [hx + d * 0.7, hy - d * 0.7, hz + d * 0.18]

    return cam, [hx, hy, hz]


def _frames_for_speed(speed: str, base: int = 120) -> int:
    """Speed → frame count for a 5s @ 24fps render. (We keep duration constant; speed affects motion rate.)"""
    return base  # duration is set by output.duration_seconds; speed affects keyframe values


def _revolutions_for_speed(speed: str) -> float:
    return {"slow": 1.0, "medium": 1.5, "fast": 2.5}.get(speed, 1.0)


def _rotation_radians_for_speed(speed: str) -> float:
    return {"slow": 2 * math.pi, "medium": 4 * math.pi, "fast": 6 * math.pi}.get(speed, 2 * math.pi)


def _ensure_bridge() -> None:
    """Make sure the Blender bridge is reachable. Raises if not."""
    if not bridge.is_connected():
        bridge.connect(timeout=3.0)
    if not bridge.ping(timeout=2.0):
        raise RuntimeError("Blender bridge not reachable")


# ───────────────────────────────────────────────────────────────────────
# Phase 17 — asset-driven pipeline (reference → mesh → import)
# ───────────────────────────────────────────────────────────────────────

# Which base_patterns benefit from the asset-driven flow vs procedural.
# Celestial is procedural-only (planets are spheres and metaball blob fits well).
# primitive_geo is always procedural (the user literally asked for a cube/sphere).
ASSET_GEN_PATTERNS = {"quadruped", "biped", "vehicle", "tree"}


def _should_use_asset_gen(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None,
                           verbose: bool = True) -> bool:
    """Decide whether to use Phase 17 asset-driven pipeline for this job.

    Returns False (→ procedural fallback) when:
    - base_pattern is celestial or primitive_geo (procedural is correct for those)
    - explicit subj.asset_gen=False (debug / direct procedural request)
    - SDXL text-to-image OR mesh generator deps unavailable

    Each gate prints a one-line explanation so the operator can see exactly
    which step bailed — critical for diagnosing install issues.
    """
    base_pattern = subj.get("base_pattern", "primitive_geo")
    if base_pattern not in ASSET_GEN_PATTERNS:
        if verbose:
            print(f"[composer] asset-gen skipped: base_pattern '{base_pattern}' not in {sorted(ASSET_GEN_PATTERNS)}")
        return False
    if subj.get("asset_gen") is False:
        if verbose:
            print("[composer] asset-gen skipped: explicit subj.asset_gen=False")
        return False
    try:
        from ..asset_gen import is_t2i_available, is_mesh_gen_available
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen skipped: cannot import asset_gen module ({type(e).__name__}: {e})")
        return False
    if not is_t2i_available():
        if verbose:
            print("[composer] asset-gen skipped: is_t2i_available()=False (SDXL weights or torch/diffusers unavailable)")
        return False
    tri = is_mesh_gen_available("triposr")
    ins = is_mesh_gen_available("instantmesh")
    if verbose:
        print(f"[composer] asset-gen mesh engines: triposr={tri}, instantmesh={ins}")
    if not (tri or ins):
        if verbose:
            print("[composer] asset-gen skipped: no mesh engine available")
        return False
    return True


def _run_asset_gen(slots: Dict[str, Any], scene: Dict[str, Any], subj: Dict[str, Any],
                   runner, paths: Dict[str, Any], run_id: str, verbose: bool = True) -> Optional[str]:
    """Generate reference image → mesh → import into Blender.

    Returns the imported hero object name on success, or None if anything
    failed (composer should fall back to procedural).
    """
    from ..asset_gen import generate_reference, generate_mesh
    tier, style = _resolve_tier_style(scene, subj, slots)

    # Paths — alongside render outputs
    work_dir = Path(paths.get("animation_dir") or Path(paths["render_filepath"]).parent)
    work_dir.mkdir(parents=True, exist_ok=True)
    ref_png = work_dir / f"reference_{run_id}.png"
    mesh_glb = work_dir / f"asset_{run_id}.glb"

    # 1. Reference image (SDXL text-to-image)
    try:
        if verbose:
            print(f"[composer] asset-gen: generating reference image (style={style})")
        t0 = time.time()
        generate_reference(slots, output_path=ref_png, style=style, seed=42)
        if verbose:
            print(f"[composer] asset-gen: reference done in {time.time() - t0:.1f}s → {ref_png.name}")
        # Free the SDXL reference pipeline VRAM BEFORE mesh generation — a resident
        # ~8GB pipeline starves the TripoSG subprocess and caused 600s timeouts
        # (the same starvation pattern as the multiview self-render fix).
        try:
            from ..asset_gen.reference import unload_reference_pipeline
            unload_reference_pipeline()
            import torch as _torch
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache(); _torch.cuda.synchronize()
            if verbose:
                print("[composer] asset-gen: reference VRAM released before mesh gen")
        except Exception as _ue:
            if verbose:
                print(f"[composer] asset-gen: VRAM release skipped ({type(_ue).__name__})")
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at reference step ({type(e).__name__}: {e})")
        return None

    # 2. Mesh generation. Default to TripoSR (proven asset quality; orientation
    # handled by our pose-aware silhouette + canonical-orient post-pass).
    # InstantMesh stays available as a fallback / explicit opt-in via
    # subj.mesh_engine="instantmesh".
    from ..asset_gen import is_mesh_gen_available
    _env_engine = os.environ.get("FS_MESH_ENGINE", "").strip()
    if subj.get("mesh_engine"):
        engine = subj["mesh_engine"]
    elif _env_engine and is_mesh_gen_available(_env_engine):
        engine = _env_engine     # explicit override (e.g. FS_MESH_ENGINE=triposg)
    elif is_mesh_gen_available("trellis2"):
        engine = "trellis2"  # DEFAULT since the 2026-06 A/B sweep (4/4 wins):
        #                      MIT, crisper geometry, natively textured output
    elif is_mesh_gen_available("triposg"):
        engine = "triposg"   # MIT, higher-fidelity, isolated venv
    elif is_mesh_gen_available("triposr"):
        engine = "triposr"
    else:
        engine = "instantmesh"
    try:
        if verbose:
            print(f"[composer] asset-gen: generating mesh via {engine}")
        t0 = time.time()
        generate_mesh(ref_png, output_path=mesh_glb, engine=engine, tier=tier,
                      base_pattern=subj.get("base_pattern"),
                      force_flip_vertical=bool(subj.get("force_flip_vertical", False)))
        os.environ["FS_LAST_MESH_ENGINE"] = engine  # read by the motion/wheels steps
        if verbose:
            print(f"[composer] asset-gen: mesh done in {time.time() - t0:.1f}s → {mesh_glb.name}")
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at mesh step ({type(e).__name__}: {e})")
        # Resilient fallback chain: retry the SAME engine once (transient HF/network
        # 404s happen), then descend by quality. InstantMesh is last (known flaky).
        _chain = [engine] + [x for x in ("trellis2", "triposg", "triposr", "instantmesh")
                             if x != engine and is_mesh_gen_available(x)]
        ok = False
        for _fb in _chain:
            try:
                if verbose:
                    print(f"[composer] asset-gen: retrying with {_fb}")
                generate_mesh(ref_png, output_path=mesh_glb, engine=_fb, tier=tier,
                              base_pattern=subj.get("base_pattern"))
                os.environ["FS_LAST_MESH_ENGINE"] = _fb
                ok = True
                break
            except Exception as e2:
                if verbose:
                    print(f"[composer] asset-gen: {_fb} failed ({type(e2).__name__}: {e2})")
        if not ok:
            return None

    # 3. Import mesh into Blender as hero.
    # Phase 19.7 — real-world scale per pattern (normalize the LONGEST axis to a
    # plausible real size) so trees tower, cars are car-sized, etc. The camera
    # frames off the actual bbox so larger heroes still fill frame correctly.
    _PATTERN_SIZE_M = {
        "quadruped": 1.1,   # dog/cat nose-to-tail ~1m
        "biped":     1.8,   # human/robot height
        "vehicle":   4.5,   # car length
        "tree":      6.0,   # a real tree towers
        "celestial": 2.0,   # arbitrary — it's a sphere
        "primitive_geo": 1.5,
    }
    _norm_size = _PATTERN_SIZE_M.get(subj.get("base_pattern"), 1.5)
    try:
        import_result = runner.run("asset_import", "import_mesh_file", {
            "filepath": str(mesh_glb),
            "name": "Hero",
            "normalize_size": _norm_size,
            "ground_to_z0": True,
            "join": True,
            # GLB is already canonically oriented at the trimesh level — no Blender rotation needed
            "orientation_fix": None,
        }, critical=False)
        if not isinstance(import_result, dict) or not import_result.get("ok"):
            return None
        hero_name = import_result.get("name", "Hero")

        # Phase 22 — TRELLIS.2 mesh hygiene: its remesh leaves hair-thin "string"
        # shards (faces with edges ~100x longer than real surface edges). Delete
        # faces containing any edge > 6% of the bbox span, then loose verts, then
        # re-ground (the strings extended below the wheels and skewed grounding).
        if engine == "trellis2":
            # The string shards are their own small connected components. Find
            # components with a numpy union-find over the edge list (NO bpy.ops
            # — separate(LOOSE) on 390k verts deadlocked the bridge), then bmesh-
            # delete verts of every island < max(2000, 0.5%) verts. Re-ground.
            _clean_code = (
                "import bpy, bmesh, json\n"
                "import numpy as np\n"
                "from mathutils import Vector\n"
                f"o=bpy.data.objects.get('{hero_name}')\n"
                "me=o.data; nv=len(me.vertices)\n"
                "ne=len(me.edges)\n"
                "ed=np.empty(ne*2, dtype=np.int64); me.edges.foreach_get('vertices', ed)\n"
                "ed=ed.reshape(-1,2)\n"
                "# glTF splits verts at UV seams -> edge connectivity alone sees 1000s of\n"
                "# fake islands. Virtually weld by QUANTIZED POSITION: verts at the same\n"
                "# 3D spot get unioned too (mesh/texture untouched).\n"
                "co=np.empty(nv*3, dtype=np.float64); me.vertices.foreach_get('co', co)\n"
                "co=co.reshape(-1,3)\n"
                "q=np.round(co/1e-5).astype(np.int64)  # exact-position welds only (coarser welded flakes INTO the body)\n"
                "_, inv=np.unique(q, axis=0, return_inverse=True)\n"
                "order=np.argsort(inv, kind='stable')\n"
                "welds=[]\n"
                "i=0\n"
                "while i < nv:\n"
                "    j=i\n"
                "    while j+1<nv and inv[order[j+1]]==inv[order[i]]: j+=1\n"
                "    if j>i:\n"
                "        for k in range(i+1, j+1): welds.append((order[i], order[k]))\n"
                "    i=j+1\n"
                "if welds: ed=np.vstack([ed, np.array(welds, dtype=np.int64)])\n"
                "parent=np.arange(nv, dtype=np.int64)\n"
                "def find(a):\n"
                "    root=a\n"
                "    while parent[root]!=root: root=parent[root]\n"
                "    while parent[a]!=root: parent[a],a=root,parent[a]\n"
                "    return root\n"
                "for a,b in ed:\n"
                "    ra,rb=find(a),find(b)\n"
                "    if ra!=rb: parent[rb]=ra\n"
                "roots=np.array([find(i) for i in range(nv)])\n"
                "uniq,counts=np.unique(roots, return_counts=True)\n"
                # Organic meshes (fur tufts ARE small islands/cards): debris-only
                # floor; aggressive floor mangles the coat. Hard-surface keeps the
                # full recipe (verified: ferrari needed it, retriever was harmed).
                f"floor={'300' if subj.get('base_pattern') in ('quadruped', 'biped') else 'max(2000, int(nv*0.005))'}\n"
                "small=set(uniq[counts<floor].tolist())\n"
                "# ROPE filter (safe for fur): strings are 1-D islands — one huge extent,\n"
                "# two tiny. Fur cards are FLAT (two big extents) and survive untouched.\n"
                "for _r in uniq[(counts>=floor)&(counts<12000)]:\n"
                "    _sel=roots==_r; _pc=co[_sel]\n"
                "    _ext=np.sort(_pc.max(0)-_pc.min(0))\n"
                "    if _ext[2] > 8.0*max(_ext[1],1e-9):\n"
                "        small.add(int(_r))\n"
                "if len(small)==len(uniq): small=set()\n"
                "kill=np.where(np.isin(roots, list(small)))[0] if small else np.array([],dtype=np.int64)\n"
                "# DENSITY PRUNE: strings connected to the body survive the island filter.\n"
                "# Body surface is dense; strings are sparse 1D chains -> bucket verts on a\n"
                "# 1.5%-span grid and kill verts in near-empty buckets (capped at 8% of verts).\n"
                "span=float(max(np.ptp(co[:,0]), np.ptp(co[:,1]), np.ptp(co[:,2]), 1e-6))\n"
                "cell=span*0.015\n"
                "qb=np.floor(co/cell).astype(np.int64)\n"
                "_, binv, bcounts=np.unique(qb, axis=0, return_inverse=True, return_counts=True)\n"
                "# valence guard: body verts have 5-6 linked faces; string-chain verts <=3.\n"
                "# Without it the prune punched holes in smooth low-tessellation panels.\n"
                "nl=len(me.loops); lv=np.empty(nl, dtype=np.int64); me.loops.foreach_get('vertex_index', lv)\n"
                "val=np.bincount(lv, minlength=nv)\n"
                # Density prune is hard-surface only: on organics it shreds fur cards.
                f"ORGANIC={1 if subj.get('base_pattern') in ('quadruped', 'biped') else 0}\n"
                "sparse=np.where((bcounts[binv]<=4) & (val<=3))[0] if not ORGANIC else np.array([],dtype=np.int64)\n"
                "if 0 < len(sparse) <= int(nv*0.08):\n"
                "    kill=np.unique(np.concatenate([kill, sparse]))\n"
                "# BARNACLE filter (#125): micro shard-clusters FUSED onto the surface\n"
                "# (bake dark from self-shadow). They survive every other filter. Detect:\n"
                "# vertex normals violently disagreeing with a COHERENT local consensus —\n"
                "# bucket-mean normal at 3% span; only judge where the neighborhood agrees\n"
                "# with itself (coh>0.6), which protects fur regions and sharp edges.\n"
                "vn=np.empty(nv*3, dtype=np.float64); me.vertices.foreach_get('normal', vn)\n"
                "vn=vn.reshape(-1,3)\n"
                "cell3=span*0.03\n"
                "qb3=np.floor(co/cell3).astype(np.int64)\n"
                "_, binv3, bcnt3=np.unique(qb3, axis=0, return_inverse=True, return_counts=True)\n"
                "acc=np.zeros((bcnt3.shape[0],3), dtype=np.float64)\n"
                "np.add.at(acc, binv3, vn)\n"
                "mean=acc[binv3]\n"
                "L=np.linalg.norm(mean, axis=1)\n"
                "coh=L/np.maximum(bcnt3[binv3],1)\n"
                "unit=mean/np.maximum(L,1e-9)[:,None]\n"
                "dot=(vn*unit).sum(1)\n"
                "barn=np.where((coh>0.6) & (dot<0.35) & (bcnt3[binv3]>=20))[0]\n"
                "n_barn=len(barn)\n"
                "if 0 < n_barn <= int(nv*0.05):\n"
                "    kill=np.unique(np.concatenate([kill, barn]))\n"
                "if len(kill):\n"
                "    bm=bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()\n"
                "    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill.tolist()], context='VERTS')\n"
                "    bm.to_mesh(me); bm.free(); me.update()\n"
                "bpy.context.view_layer.update()\n"
                "ws=[o.matrix_world@Vector(c) for c in o.bound_box]\n"
                "o.location.z += -min(p.z for p in ws)\n"
                "bpy.context.view_layer.update()\n"
                "# tear-off edges expose interior faces as dark patches -> cull them\n"
                "for _mt in me.materials:\n"
                "    if _mt: _mt.use_backface_culling=True\n"
                "__result__=json.dumps({'islands':int(len(uniq)),'dropped_verts':int(len(kill)),'verts':len(me.vertices)})\n"
            )
            _cl = runner.run("trellis2_clean", "execute_python", {"code": _clean_code}, critical=False)
            if verbose and isinstance(_cl, dict):
                print(f"[composer] trellis2 cleanup: {_cl.get('result')}")
            # ── QUALITY RE-ROLL GATE: flaky TRELLIS generations (torn flaps,
            # speckled texture) show up as MANY shard islands. Clean gens run
            # 38-65 islands / <2% dropped verts; flaky ones 100+ / 3%+.
            # Regenerate ONCE with a different seed — ~3 min, saves the render.
            try:
                _ci = json.loads(_cl.get("result")) if isinstance(_cl, dict) and isinstance(_cl.get("result"), str) else {}
            except Exception:
                _ci = {}
            _isl = int(_ci.get("islands", 0)); _drp = int(_ci.get("dropped_verts", 0))
            _tot = max(int(_ci.get("verts", 1)), 1)
            # Organics naturally carry many small fur-card islands — only truly
            # extreme counts indicate a flaky generation there.
            _organic = subj.get("base_pattern") in ("quadruped", "biped")
            _isl_lim, _shard_lim = (400, 0.10) if _organic else (100, 0.025)
            if _isl >= _isl_lim or _drp / _tot >= _shard_lim:
                if verbose:
                    print(f"[composer] quality gate: flaky gen (islands={_isl}, "
                          f"shard={_drp/_tot:.1%}) → re-rolling with new seed")
                try:
                    os.environ["FS_TRELLIS_SEED"] = "1337"
                    generate_mesh(ref_png, output_path=mesh_glb, engine="trellis2", tier=tier,
                                  base_pattern=subj.get("base_pattern"))
                    runner.run("reroll_clear", "execute_python", {"code": (
                        f"import bpy\no=bpy.data.objects.get('{hero_name}')\n"
                        "if o: bpy.data.objects.remove(o, do_unlink=True)\n__result__='cleared'")},
                        critical=False)
                    import_result = runner.run("asset_import", "import_mesh_file", {
                        "filepath": str(mesh_glb), "name": "Hero",
                        "normalize_size": _norm_size, "ground_to_z0": True,
                        "join": True, "orientation_fix": None}, critical=False)
                    hero_name = import_result.get("name", "Hero") if isinstance(import_result, dict) else "Hero"
                    _cl2 = runner.run("trellis2_clean", "execute_python", {"code": _clean_code}, critical=False)
                    if verbose and isinstance(_cl2, dict):
                        print(f"[composer] re-roll cleanup: {_cl2.get('result')}")
                except Exception as _re:
                    if verbose:
                        print(f"[composer] re-roll failed ({type(_re).__name__}: {_re}) — keeping first gen")
                finally:
                    os.environ.pop("FS_TRELLIS_SEED", None)

            # ── TEXTURE DESPECKLE: flaky gens bake floating micro-shards INTO the
            # albedo as isolated dark dots — geometry pruning can't touch paint.
            # Heal pixels far darker than a BRIGHT 8x8 neighborhood (panel lines /
            # windows are larger structures with dark neighborhoods → untouched).
            _despeckle = (
                "import bpy, json\n"
                "import numpy as np\n"
                f"o=bpy.data.objects.get('{hero_name}')\n"
                "healed=0; imgs=0\n"
                "seen=set()\n"
                "for mt in (o.data.materials if o else []):\n"
                "    if not (mt and mt.use_nodes): continue\n"
                "    for nd in mt.node_tree.nodes:\n"
                "        if nd.type!='TEX_IMAGE' or not nd.image or nd.image.name in seen: continue\n"
                "        img=nd.image; seen.add(img.name)\n"
                "        w,h=img.size\n"
                "        if w*h==0 or w<64 or h<64: continue\n"
                "        px=np.empty(w*h*4, dtype=np.float32)\n"
                "        img.pixels.foreach_get(px)\n"
                "        px=px.reshape(h,w,4)\n"
                "        lum=px[:,:,:3].mean(2)\n"
                "        H8,W8=(h//8)*8,(w//8)*8\n"
                "        blk=lum[:H8,:W8].reshape(H8//8,8,W8//8,8).mean((1,3))\n"
                "        nb=np.repeat(np.repeat(blk,8,0),8,1)\n"
                "        m=(lum[:H8,:W8] < 0.45*nb) & (nb > 0.18)\n"
                "        n=int(m.sum())\n"
                "        if n==0 or n > 0.10*H8*W8: continue   # nothing / too much (not speckle)\n"
                "        blkc=px[:H8,:W8,:3].reshape(H8//8,8,W8//8,8,3).mean((1,3))\n"
                "        nbc=np.repeat(np.repeat(blkc,8,axis=0),8,axis=1)\n"
                "        sub=px[:H8,:W8,:3]\n"
                "        sub[m]=nbc[m]\n"
                "        px[:H8,:W8,:3]=sub\n"
                "        img.pixels.foreach_set(px.ravel())\n"
                "        img.update()\n"
                "        healed+=n; imgs+=1\n"
                "__result__=json.dumps({'healed_px':healed,'images':imgs})\n"
            )
            _ds = runner.run("trellis2_despeckle", "execute_python", {"code": _despeckle}, critical=False)
            if verbose and isinstance(_ds, dict):
                print(f"[composer] despeckle: {_ds.get('result')}")

        # Phase 18 FINAL — deterministic Blender-frame orientation. Calibrated
        # ONCE per pattern via scripts/orient_audit_blender.py (renders all 24
        # orientations from a true side view in Blender; you pick the standing
        # cell). Because both the audit and this application run in Blender's
        # own coordinate frame, the picked rotation is guaranteed correct — no
        # trimesh/glTF/matplotlib convention mismatches.
        base_pattern = subj.get("base_pattern", "primitive_geo")
        # Phase 20 — reference-anchored orientation gate (scalable, per-asset).
        # Picks the rotation whose silhouette best matches the reference image, so
        # we don't depend on a per-pattern hardcoded Euler that breaks on subjects
        # TripoSG happens to emit at a different azimuth (cat/fox/etc). Falls back
        # to the per-pattern Euler below when it can't get a confident match.
        silo = None
        if engine == "trellis2":
            # TRELLIS.2 meshes are USUALLY canonical but the up/down varies run
            # to run (one e2e came out roof-down). Step 1: azimuth-normalize the
            # long horizontal to Y and BAKE it. Step 2: silhouette-IoU gate
            # restricted to the 4 flips that preserve that axis — picks the one
            # matching the reference. Robust to string remnants, cheap (4 renders).
            _t2o = (
                "import bpy, math, json\n"
                "from mathutils import Vector\n"
                f"o=bpy.data.objects.get('{hero_name}')\n"
                "o.rotation_mode='XYZ'; bpy.context.view_layer.update()\n"
                "xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]\n"
                "if (max(xs)-min(xs))>(max(ys)-min(ys)):\n"
                "    o.rotation_euler.z+=math.radians(90.0)\n"
                "    bpy.context.view_layer.objects.active=o; o.select_set(True)\n"
                "    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)\n"
                "bpy.context.view_layer.update()\n"
                "zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]\n"
                "o.location.z+=-min(zs); bpy.context.view_layer.update()\n"
                "__result__=json.dumps({'ok':True})\n"
            )
            runner.run("trellis2_azimuth", "execute_python", {"code": _t2o}, critical=False)
            if ref_png.exists():
                silo = _orient_hero_by_reference(
                    runner, hero_name, str(ref_png), work_dir, min_iou=0.0,
                    wheels_down=(base_pattern == "vehicle"),
                    candidates=[(0, 0, 0), (180, 0, 0), (0, 180, 0), (0, 0, 180)],
                    verbose=verbose)
            else:
                silo = {"ok": True}
            if base_pattern == "vehicle":
                # PAINT-SIDE-UP check: silhouettes can't tell a flipped car (and
                # shard remnants fool width heuristics), but TEXTURE can — the
                # roof is saturated paint, the underside is dark chassis. Render
                # ortho top + bottom, compare subject-pixel saturation, flip if
                # the painted side faces down.
                _ps = (
                    "import bpy, math, json\n"
                    "import numpy as np\n"
                    "from mathutils import Vector\n"
                    f"o=bpy.data.objects.get('{hero_name}')\n"
                    "sc=bpy.context.scene\n"
                    "cam=bpy.data.cameras.new('PSCam'); cam.type='ORTHO'\n"
                    "co=bpy.data.objects.new('PSCam',cam); sc.collection.objects.link(co)\n"
                    "sun=bpy.data.lights.new('PSSun',type='SUN'); sun.energy=3.0\n"
                    "so=bpy.data.objects.new('PSSun',sun); sc.collection.objects.link(so)\n"
                    "prev=(sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,sc.render.filepath,sc.render.film_transparent)\n"
                    "sc.render.engine='BLENDER_EEVEE'; sc.render.resolution_x=128; sc.render.resolution_y=128\n"
                    "sc.render.film_transparent=True; sc.camera=co\n"
                    "try: sc.render.image_settings.color_mode='RGBA'\n"
                    "except Exception: pass\n"
                    "ws=[o.matrix_world@Vector(c) for c in o.bound_box]\n"
                    "cx=(min(p.x for p in ws)+max(p.x for p in ws))/2; cy=(min(p.y for p in ws)+max(p.y for p in ws))/2\n"
                    "cz=(min(p.z for p in ws)+max(p.z for p in ws))/2\n"
                    "span=max(max(p.x for p in ws)-min(p.x for p in ws), max(p.y for p in ws)-min(p.y for p in ws))\n"
                    "cam.ortho_scale=span*1.15\n"
                    "def shoot(zoff, rx, path):\n"
                    "    co.location=Vector((cx,cy,cz+zoff)); co.rotation_euler=(rx,0,0)\n"
                    "    so.rotation_euler=(rx,0,0)\n"
                    "    sc.render.filepath=path; bpy.ops.render.render(write_still=True)\n"
                    "    im=bpy.data.images.load(path, check_existing=False)\n"
                    "    w,h=im.size; a=np.array(im.pixels[:],dtype=np.float32).reshape(h,w,4)\n"
                    "    bpy.data.images.remove(im)\n"
                    "    m=a[:,:,3]>0.5\n"
                    "    if m.sum()<20: m=a[:,:,:3].max(axis=2)>0.03   # alpha empty -> luminance mask\n"
                    "    if m.sum()<20: return 0.0\n"
                    "    rgb=a[m][:,:3]; mx=rgb.max(1); mn=rgb.min(1)\n"
                    "    return float(((mx-mn)/(mx+1e-4)).mean())\n"
                    f"tp=r'{str((Path(work_dir) / '_ps_top.png').as_posix())}'\n"
                    f"bp=r'{str((Path(work_dir) / '_ps_bot.png').as_posix())}'\n"
                    "sat_top=shoot(span*3.0, 0.0, tp)                      # camera above, looking down\n"
                    "sat_bot=shoot(-span*3.0, math.pi, bp)                 # camera below, looking up\n"
                    "flipped=0\n"
                    "if sat_bot > sat_top*1.15:\n"
                    "    o.rotation_euler.y+=math.pi; bpy.context.view_layer.update()\n"
                    "    zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]\n"
                    "    o.location.z+=-min(zs); bpy.context.view_layer.update(); flipped=1\n"
                    "sc.camera,sc.render.engine,sc.render.resolution_x,sc.render.resolution_y,sc.render.filepath,sc.render.film_transparent=prev\n"
                    "bpy.data.objects.remove(co,do_unlink=True); bpy.data.cameras.remove(cam)\n"
                    "bpy.data.objects.remove(so,do_unlink=True); bpy.data.lights.remove(sun)\n"
                    "__result__=json.dumps({'sat_top':round(sat_top,3),'sat_bot':round(sat_bot,3),'flipped':flipped})\n"
                )
                _pr = runner.run("paint_side_up", "execute_python", {"code": _ps}, critical=False)
                if verbose and isinstance(_pr, dict):
                    print(f"[composer] paint-side-up: {_pr.get('result')}")
        elif os.environ.get("FS_ORIENT_SILHOUETTE", "1") != "0" and ref_png.exists():
            silo = _orient_hero_by_reference(runner, hero_name, str(ref_png), work_dir,
                                             wheels_down=(base_pattern == "vehicle"), verbose=verbose)
        # Engine-aware orientation: TripoSG and TripoSR emit in different frames.
        _euler_map = _TRIPOSG_PATTERN_EULER if engine == "triposg" else _BLENDER_PATTERN_EULER
        euler = _euler_map.get(base_pattern)
        if (not silo or not silo.get("ok")) and euler is not None:
            rx, ry, rz = euler
            # DIAGNOSTIC + robust apply: print the import baseline (which the
            # glTF importer leaves as a quaternion +90X conversion), then bake
            # that baseline to zero so our measured Euler — which the user read
            # as an ABSOLUTE rotation in the .blend — reproduces their pose
            # exactly from the same zeroed baseline.
            # CRITICAL: do NOT transform_apply/bake. The mesh has a non-identity
            # scale from normalize_size, and transform_apply(rotation=True) on a
            # scaled object bakes the rotation incorrectly (the orient audit,
            # which leaves rotation as object rotation and never bakes, renders
            # the SAME mesh+rotation correctly standing). So we set rotation_euler
            # and leave it live — exactly matching the audit. Ground via the
            # rotation-aware world bbox.
            _check_png = str((Path(work_dir) / "orient_check.png").as_posix())
            rot_code = (
                "import bpy, math\n"
                "from mathutils import Vector\n"
                f"o = bpy.data.objects.get('{hero_name}')\n"
                "if o:\n"
                "    o.rotation_mode = 'XYZ'\n"
                f"    o.rotation_euler = (math.radians({rx}), math.radians({ry}), math.radians({rz}))\n"
                "    bpy.context.view_layer.update()\n"
                "    zs = [(o.matrix_world @ Vector(c)).z for c in o.bound_box]\n"
                "    o.location.z -= min(zs)\n"
                "    bpy.context.view_layer.update()\n"
                "    # AZIMUTH-NORMALIZE: make the LONG horizontal axis run along Y\n"
                "    # (flanks face ±X). The mesh engine's output azimuth varies per\n"
                "    # subject; this guarantees the side texture projection (which\n"
                "    # projects along X onto the flanks) is always axis-correct.\n"
                "    xs0=[(o.matrix_world@Vector(c)).x for c in o.bound_box]\n"
                "    ys0=[(o.matrix_world@Vector(c)).y for c in o.bound_box]\n"
                "    if (max(xs0)-min(xs0)) > (max(ys0)-min(ys0)):\n"
                "        o.rotation_euler.z += math.radians(90.0)\n"
                "        bpy.context.view_layer.update()\n"
                "        zs2=[(o.matrix_world@Vector(c)).z for c in o.bound_box]\n"
                "        o.location.z -= min(zs2)\n"
                "        bpy.context.view_layer.update()\n"
                "    post_dims = tuple(round(d,3) for d in o.dimensions)\n"
                "    center_z = sum(((o.matrix_world @ Vector(c)).z for c in o.bound_box)) / 8.0\n"
                "    # IMMEDIATE front-ortho proof render — before any other step runs\n"
                "    xs=[(o.matrix_world@Vector(c)).x for c in o.bound_box]\n"
                "    ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]\n"
                "    zz=[(o.matrix_world@Vector(c)).z for c in o.bound_box]\n"
                "    span=max(max(xs)-min(xs),max(ys)-min(ys),max(zz)-min(zz),1.0)\n"
                "    midz=(min(zz)+max(zz))/2.0\n"
                "    cd=bpy.data.cameras.new('ChkCam'); cd.type='ORTHO'; cd.ortho_scale=span*1.6\n"
                "    co=bpy.data.objects.new('ChkCam',cd); bpy.context.scene.collection.objects.link(co)\n"
                "    co.location=Vector((0.0,-span*4.0,midz)); ld=(Vector((0,0,midz))-co.location); co.rotation_euler=ld.to_track_quat('-Z','Y').to_euler()\n"
                "    ll=bpy.data.lights.new('ChkL',type='SUN'); ll.energy=3.5; lo=bpy.data.objects.new('ChkL',ll); bpy.context.scene.collection.objects.link(lo); lo.rotation_euler=(math.radians(55),0,math.radians(40))\n"
                "    pc=bpy.context.scene.camera; pe=bpy.context.scene.render.engine; px=bpy.context.scene.render.resolution_x; py=bpy.context.scene.render.resolution_y; pf=bpy.context.scene.render.filepath\n"
                "    bpy.context.scene.camera=co; bpy.context.scene.render.engine='BLENDER_EEVEE'; bpy.context.scene.render.resolution_x=500; bpy.context.scene.render.resolution_y=500\n"
                f"    bpy.context.scene.render.filepath=r'{_check_png}'\n"
                "    bpy.ops.render.render(write_still=True)\n"
                "    bpy.data.objects.remove(co,do_unlink=True); bpy.data.cameras.remove(cd); bpy.data.objects.remove(lo,do_unlink=True); bpy.data.lights.remove(ll)\n"
                "    bpy.context.scene.camera=pc; bpy.context.scene.render.engine=pe; bpy.context.scene.render.resolution_x=px; bpy.context.scene.render.resolution_y=py; bpy.context.scene.render.filepath=pf\n"
                "    __result__ = {'post_dims': post_dims, 'center_z': round(center_z,3), 'check_png': r'" + _check_png + "'}\n"
                "else:\n"
                "    __result__ = 'no hero'\n"
            )
            runner.run("orient_hero", "execute_python", {"code": rot_code}, critical=False)
            if verbose:
                print(f"[composer] orient_hero: pattern='{base_pattern}' "
                      f"Blender Euler=({rx}, {ry}, {rz}) applied + baked + grounded")
        elif silo and silo.get("ok"):
            pass  # oriented by the reference-silhouette gate already
        elif verbose:
            print(f"[composer] orient_hero: no calibration for pattern='{base_pattern}' "
                  f"— run scripts/orient_audit_blender.py to calibrate")

        # Phase 19 mesh-quality: smooth-shade + a Corrective Smooth modifier to
        # melt the remaining blobby TripoSR micro-noise while preserving the
        # silhouette. Big visual de-blob with near-zero render cost.
        # SKIP for TRELLIS.2: its meshes are already crisp, and Corrective Smooth
        # moves verts under the baked UVs -> blotchy smeared texture.
        smooth_code = "" if engine == "trellis2" else (
            "import bpy\n"
            f"o = bpy.data.objects.get('{hero_name}')\n"
            "if o and o.type == 'MESH':\n"
            "    for p in o.data.polygons:\n"
            "        p.use_smooth = True\n"
            "    m = o.modifiers.get('HeroSmooth') or o.modifiers.new('HeroSmooth', 'CORRECTIVE_SMOOTH')\n"
            "    m.iterations = 12\n"
            "    m.factor = 0.6\n"
            "    try:\n"
            "        m.use_only_smooth = True\n"
            "    except Exception:\n"
            "        pass\n"
            "    __result__ = 'smoothed'\n"
            "else:\n"
            "    __result__ = 'no hero'\n"
        )
        if smooth_code:
            runner.run("smooth_hero", "execute_python", {"code": smooth_code}, critical=False)
            if verbose:
                print(f"[composer] smooth_hero: corrective-smooth + shade-smooth applied")
        elif verbose:
            print(f"[composer] smooth_hero: skipped (trellis2 mesh is already crisp)")

        # Phase 19 texturing (projection half): paint the SDXL reference photo
        # onto the gray TripoSG geometry so it gets real color + facial features.
        # TripoSG meshes import as uniform gray [102,102,102]; this is what gives
        # the hero its actual appearance. The img2img polish pass refines the far
        # side later. flip_u/flip_v env hooks let us correct the facing in one shot.
        try:
            if engine == "trellis2":
                # TRELLIS.2 GLBs arrive ALREADY textured (PBR baked from the
                # reference) — projecting over them would smear the real texture.
                if verbose:
                    print("[composer] reftex skipped: trellis2 mesh is natively textured")
            elif os.environ.get("FS_REFTEX", "1") == "1" and ref_png.exists():
                if os.environ.get("FS_REFTEX_MULTIVIEW", "1") == "1":
                    # Full hybrid: side photo + img2img-refined ±Y views, blended.
                    _apply_multiview_texture(runner, hero_name, str(ref_png),
                                             slots, work_dir, run_id, style=style,
                                             verbose=verbose)
                else:
                    _flip_u = os.environ.get("FS_REFTEX_FLIP_U", "0") == "1"
                    _flip_v = os.environ.get("FS_REFTEX_FLIP_V", "0") == "1"
                    _apply_reference_texture(runner, hero_name, str(ref_png),
                                             flip_u=_flip_u, flip_v=_flip_v, verbose=verbose)
                # Texture-fidelity gate (#2): match the textured hero's colors to
                # the reference (saturation-led). Universal 'colors off' fix.
                if os.environ.get("FS_TEXFIDELITY", "1") != "0":
                    _apply_texture_color_fidelity(runner, hero_name, str(ref_png), work_dir, verbose=verbose)
        except Exception as _te:
            if verbose:
                print(f"[composer] ref_texture skipped ({type(_te).__name__}: {_te})")

        return hero_name
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at import step ({type(e).__name__}: {e})")
        return None


# ───────────────────────────────────────────────────────────────────────
# Phase 16 — diffusion refinement gate
# ───────────────────────────────────────────────────────────────────────

def _resolve_tier_style(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
    """Pull tier+style from whichever slot level the LLM populated.

    The slot extractor puts them under output.render_tier / output.style, but
    older paths also stashed them on subject. Check both, fall back to defaults.
    """
    out_slots = (slots or {}).get("output", {}) if slots else {}
    tier = (
        out_slots.get("render_tier")
        or scene.get("render_tier")
        or subj.get("requested_tier")
        or "fast"
    )
    style = (
        out_slots.get("style")
        or scene.get("style")
        or subj.get("requested_style")
        or "photoreal"
    )
    return str(tier).lower(), str(style).lower()


def _should_refine(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> bool:
    """Decide whether the per-frame img2img refiner should run.

    Phase 17 change: defaults to OFF. The asset-driven path produces real meshes
    that Blender renders correctly — per-frame img2img creates temporal artifacts
    (the spinning "blotchy brown marks" the user spotted in v1). We keep refinement
    available as an OPT-IN stylization pass for non-photoreal styles where the
    user explicitly wants diffusion polish.

    Opt-in via slot subj.use_refiner=True OR scene.use_refiner=True.

    Skips when:
    - Not explicitly opted in (default)
    - Style is 'raw'/'procedural' (debug)
    - Refinement module not installed
    - Render tier is 'preview'
    """
    tier, style = _resolve_tier_style(scene, subj, slots)
    if style in ("raw", "procedural", "none", "off"):
        return False
    if tier == "preview":
        return False
    # Opt-in gate — Phase 17 default off
    opt_in = bool(subj.get("use_refiner") or scene.get("use_refiner"))
    if not opt_in:
        return False
    try:
        from ..refinement import is_available
        return is_available()
    except Exception:
        return False


def _refine_params(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map render_tier → refinement quality settings."""
    tier, style = _resolve_tier_style(scene, subj, slots)
    tier_map = {
        "fast":      {"strength": 0.45, "steps": 18, "guidance_scale": 7.0},
        "standard":  {"strength": 0.55, "steps": 25, "guidance_scale": 7.5},
        "cinematic": {"strength": 0.65, "steps": 35, "guidance_scale": 8.0},
    }
    params = dict(tier_map.get(tier, tier_map["standard"]))
    params["style"] = style
    return params


def _maybe_refine_single(render_path: str, slots: Dict[str, Any], scene: Dict[str, Any],
                          subj: Dict[str, Any], runner, verbose: bool = True) -> None:
    if not _should_refine(scene, subj, slots):
        return
    try:
        from ..refinement import refine_frame
    except Exception as e:
        if verbose:
            print(f"[composer] refine skipped — module unavailable: {e}")
        return
    params = _refine_params(scene, subj, slots)
    if verbose:
        print(f"[composer] refining frame — style={params['style']}, "
              f"strength={params['strength']}, steps={params['steps']}")
    t0 = time.time()
    try:
        # Refine in-place so downstream paths keep working
        refine_frame(render_path, slots, output_path=render_path, **params)
        if verbose:
            print(f"[composer] refine done in {time.time() - t0:.1f}s")
    except Exception as e:
        # Non-fatal — fall back to the raw render
        if verbose:
            print(f"[composer] refine FAILED (non-fatal, using raw render): "
                  f"{type(e).__name__}: {e}")


def _maybe_refine_animation(anim_dir: str, slots: Dict[str, Any], scene: Dict[str, Any],
                             subj: Dict[str, Any], runner, verbose: bool = True) -> None:
    if not _should_refine(scene, subj):
        return
    try:
        from ..refinement import refine_animation
    except Exception as e:
        if verbose:
            print(f"[composer] refine skipped — module unavailable: {e}")
        return
    params = _refine_params(scene, subj)
    if verbose:
        print(f"[composer] refining animation frames — style={params['style']}, "
              f"strength={params['strength']}, steps={params['steps']}")
    t0 = time.time()
    try:
        n = refine_animation(anim_dir, slots, **params)
        if verbose:
            print(f"[composer] refined {n} frames in {time.time() - t0:.1f}s")
    except Exception as e:
        if verbose:
            print(f"[composer] refine FAILED (non-fatal, using raw frames): "
                  f"{type(e).__name__}: {e}")


def _build_accent_materials(runner, run_id: str, hero_mat_params: Dict[str, Any], subj: Dict[str, Any]) -> Dict[str, str]:
    """Create the small set of accent materials patterns reference via material_hint.

    Returns mapping {hint: material_name}. Created lazily so we don't pollute Blender
    with unused materials.
    """
    out: Dict[str, str] = {}

    def _make(hint: str, params: Dict[str, Any]) -> None:
        params = dict(params)
        params["name"] = f"{hint.title()}Mat_{run_id}"
        res = runner.run(f"accent_mat:{hint}", "create_material", params)
        out[hint] = (res or {}).get("name", params["name"]) if isinstance(res, dict) else params["name"]

    # Eyes — sclera (white), iris (colored), pupil (black). Layered spheres
    # produce a proper-reading eye instead of a single black bead.
    _make("eyes", {"color": [0.95, 0.93, 0.90, 1.0], "metallic": 0.0, "roughness": 0.20})
    # Iris — colored ring. Default warm brown; LLM can override via slot accent_color later.
    iris_color = subj.get("iris_color") or [0.30, 0.18, 0.10, 1.0]
    if len(iris_color) == 3:
        iris_color = list(iris_color) + [1.0]
    _make("iris", {"color": iris_color, "metallic": 0.0, "roughness": 0.30})
    # Pupil — pure black, slightly glossy for catchlight
    _make("pupil", {"color": [0.01, 0.01, 0.01, 1.0], "metallic": 0.0, "roughness": 0.05})
    # Lips — slightly redder than skin, soft sheen
    _make("lips", {"color": [0.65, 0.35, 0.32, 1.0], "metallic": 0.0, "roughness": 0.40,
                   "subsurface": 0.20, "subsurface_color": [0.65, 0.32, 0.30],
                   "subsurface_radius": [1.0, 0.4, 0.3]})
    # Nostril — dark recess
    _make("nostril", {"color": [0.10, 0.06, 0.06, 1.0], "metallic": 0.0, "roughness": 0.60})
    # Headlights — emissive white, used by vehicle
    _make("headlight", {
        "color": [0.95, 0.95, 0.85, 1.0],
        "metallic": 0.0, "roughness": 0.20,
        "emission_color": [1.0, 0.95, 0.85], "emission_strength": 12.0,
    })
    # Tire — dark matte rubber, used by vehicle wheels
    _make("tire", {"color": [0.08, 0.08, 0.08, 1.0], "metallic": 0.0, "roughness": 0.85})
    # Foliage — saturated green, used by tree canopy
    _make("foliage", {"color": [0.12, 0.40, 0.10, 1.0], "metallic": 0.0, "roughness": 0.85})
    # Wood — warm brown, used by tree trunk
    _make("wood", {"color": [0.30, 0.18, 0.08, 1.0], "metallic": 0.0, "roughness": 0.85})
    return out


# ───────────────────────────────────────────────────────────────────────
# Step runner — captures errors but keeps composing
# ───────────────────────────────────────────────────────────────────────

class _StepRunner:
    def __init__(self, result: CompositionResult, verbose: bool):
        self.result = result
        self.verbose = verbose

    def run(self, step_name: str, tool_name: str, params: Dict[str, Any], critical: bool = False) -> Any:
        """Run a tool call. Logs. If critical=True, propagates exceptions."""
        if self.verbose:
            preview = json.dumps(params, default=str)
            if len(preview) > 150:
                preview = preview[:147] + "..."
            print(f"[composer] {step_name}: {tool_name}({preview})")
        try:
            out = registry.call(tool_name, params)
            self.result.steps_run.append(step_name)
            if self.verbose and isinstance(out, dict):
                # Echo the result so we can debug name-collision issues like
                # Blender auto-renaming HeroMat → HeroMat.001
                rprev = json.dumps(out, default=str)
                if len(rprev) > 120:
                    rprev = rprev[:117] + "..."
                print(f"[composer]   → {rprev}")
            return out
        except Exception as e:
            err = f"{step_name} ({tool_name}) failed: {type(e).__name__}: {e}"
            self.result.errors.append(err)
            if self.verbose:
                print(f"[composer]   ✗ {err}")
            if critical:
                raise
            return None


# ───────────────────────────────────────────────────────────────────────
# Main composer
# ───────────────────────────────────────────────────────────────────────

_ACTOR_STAGE_CODE = r"""
import bpy, math, json
from mathutils import Vector
h=bpy.data.objects.get('__HERO__'); a=bpy.data.objects.get('__ACTOR__')
a.rotation_mode='XYZ'; bpy.context.view_layer.update()
if __FIGHT__:
    # FACE-OFF: the opponent is the SAME cached asset as the hero, so inherit the
    # hero's EXACT (silhouette-gate-solved) orientation. The fight gate then flips
    # exactly one of the two 180 deg (via FACE), guaranteeing they square up
    # antiparallel instead of the unrelated bbox-aspect guess used for companions.
    h.rotation_mode='XYZ'
    a.rotation_euler=h.rotation_euler.copy(); bpy.context.view_layer.update()
else:
    xs=[(a.matrix_world@Vector(c)).x for c in a.bound_box]; ys=[(a.matrix_world@Vector(c)).y for c in a.bound_box]
    if (max(xs)-min(xs))>(max(ys)-min(ys)):
        a.rotation_euler.z+=math.radians(90.0); bpy.context.view_layer.update()
hx=[(h.matrix_world@Vector(c)).x for c in h.bound_box]
ax=[(a.matrix_world@Vector(c)).x for c in a.bound_box]
gap=(max(hx)-min(hx))*0.5+(max(ax)-min(ax))*0.5+__PAD__
a.location.x=h.location.x+gap; a.location.y=h.location.y
bpy.context.view_layer.update()
zs=[(a.matrix_world@Vector(c)).z for c in a.bound_box]
a.location.z+=-min(zs); bpy.context.view_layer.update()
__result__=json.dumps({'gap':round(gap,2)})
"""


def _spawn_extra_actor(runner, slots, ex, idx, hero_name, total_frames, fps,
                       run_id, paths, action="walk", verbose=True):
    """Phase 23 T1: generate + place + animate a companion actor beside the hero.

    v1 scope (intentionally lean): reference->mesh (cached by identity so "two
    dogs" costs one generation), import as Actor<idx>, ground + offset to the
    hero's side, gait without camera tracking. Heavy gates (orientation IoU,
    shard cleanup) are skipped in v1 — logged as the known gap."""
    import copy
    import hashlib
    from pathlib import Path as _P
    from ..asset_gen import generate_reference, generate_mesh
    from ..asset_gen.reference import unload_reference_pipeline
    from . import motion_rig

    ident = (ex.get("identity_phrase") or "companion").strip()
    pattern = ex.get("base_pattern") or "biped"
    actor = f"Actor{idx}"
    cache_dir = _P(__file__).resolve().parents[2] / "renders" / "_actor_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(ident.encode("utf-8")).hexdigest()[:12]
    glb = cache_dir / f"{key}.glb"

    if not glb.exists():
        slots2 = copy.deepcopy(slots)
        slots2["subject"] = {
            "name": ident, "base_pattern": pattern, "shape": None,
            "library_query": None, "identity_phrase": ident, "pose": "standing",
            "color_name": "neutral", "material": "matte", "emissive": False,
            "scale": 1.0, "location": [0, 0, 0],
        }
        slots2.pop("extra_subjects", None)
        ref2 = cache_dir / f"{key}_ref.png"
        if verbose:
            print(f"[composer] extra actor: generating '{ident}' ({pattern})")
        generate_reference(slots2, output_path=ref2, style="photoreal", seed=42)
        try:
            unload_reference_pipeline()
            import torch as _t
            if _t.cuda.is_available():
                _t.cuda.empty_cache()
        except Exception:
            pass
        try:
            generate_mesh(ref2, output_path=glb, engine="trellis2", tier="fast",
                          base_pattern=pattern)
        except Exception as _ge:
            if verbose:
                print(f"[composer] extra actor: trellis2 failed ({type(_ge).__name__}) -> triposg")
            generate_mesh(ref2, output_path=glb, engine="triposg", tier="fast",
                          base_pattern=pattern)
    elif verbose:
        print(f"[composer] extra actor: cache hit for '{ident}'")

    size_m = {"quadruped": 1.0, "biped": 1.75, "vehicle": 4.4}.get(pattern, 1.5)
    imp = runner.run("actor_import", "import_mesh_file", {
        "filepath": str(glb), "name": actor, "normalize_size": size_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None,
    }, critical=False)
    if not isinstance(imp, dict) or not imp.get("ok"):
        raise RuntimeError("actor import failed")
    actor = imp.get("name", actor)

    # Face-off (fight) puts the opponent AHEAD along the duel axis at sword
    # distance; companions (walk) stand close beside the hero.
    _pad = "1.10" if action == "fight" else "0.35"
    stage = (_ACTOR_STAGE_CODE.replace("__HERO__", hero_name)
             .replace("__ACTOR__", actor).replace("__PAD__", _pad)
             .replace("__FIGHT__", "True" if action == "fight" else "False"))
    st = runner.run("actor_stage", "execute_python", {"code": stage}, critical=False)
    if verbose and isinstance(st, dict):
        print(f"[composer] extra actor staged: {st.get('result')}")

    if pattern in motion_rig.SKELETAL_PATTERNS:
        import math as _m
        ok = motion_rig.build_skeletal_gait(
            runner, actor, pattern, total_frames, fps, track_camera=False,
            action=action, phase=(_m.pi if action == "fight" else 0.0),
            face=-1.0, verbose=verbose)
        if verbose:
            print(f"[composer] extra actor gait: {'ok' if ok else 'skipped'} (action={action})")


# Phase 23 T3: MOUNT — stage a rideable prop (skateboard) under the hero, then
# translate hero+board together with a bob + carve sway; tracking camera. The
# hero keeps its standing pose (no gait) — riding, not walking.
_MOUNT_RIDE_CODE = r"""
import bpy, math, json
from mathutils import Vector
h=bpy.data.objects.get('__HERO__'); b=bpy.data.objects.get('__MOUNT__')
TOTAL=__TOTAL__; FPSV=__FPSV__
if h is None or b is None:
    __result__=json.dumps({'ok': False, 'reason': 'missing hero or mount'})
else:
    b.rotation_mode='XYZ'; bpy.context.view_layer.update()
    bx=[(b.matrix_world@Vector(c)).x for c in b.bound_box]; by=[(b.matrix_world@Vector(c)).y for c in b.bound_box]
    if (max(bx)-min(bx))>(max(by)-min(by)):
        b.rotation_euler.z+=math.radians(90.0); bpy.context.view_layer.update()
    hb=[h.matrix_world@Vector(c) for c in h.bound_box]
    hcx=sum(v.x for v in hb)/8.0; hcy=sum(v.y for v in hb)/8.0
    bb=[b.matrix_world@Vector(c) for c in b.bound_box]
    bcx=sum(v.x for v in bb)/8.0; bcy=sum(v.y for v in bb)/8.0
    b.location.x+=hcx-bcx; b.location.y+=hcy-bcy
    bpy.context.view_layer.update()
    bz=[(b.matrix_world@Vector(c)).z for c in b.bound_box]
    b.location.z+=-min(bz); bpy.context.view_layer.update()
    deck=max((b.matrix_world@Vector(c)).z for c in b.bound_box)
    hz=[v.z for v in hb]
    h.location.z+=deck-min(hz)
    bpy.context.view_layer.update()
    sc=bpy.context.scene; sc.frame_start=1; sc.frame_end=TOTAL
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type='LINEAR'
    except Exception: pass
    travel=2.0*TOTAL/float(FPSV)
    hbase=h.location.copy(); bbase=b.location.copy()
    cam=sc.camera
    span=max(max(hz)-min(hz), max(v.x for v in hb)-min(v.x for v in hb),
             max(v.y for v in hb)-min(v.y for v in hb), 0.6)
    midz=(min(hz)+max(hz))/2.0+(deck-min(hz))
    for f in range(1,TOTAL+1):
        frac=(f-1)/max(TOTAL-1,1); d=travel*frac
        bob=0.008*math.sin(2*math.pi*frac*7)
        for ob, base in ((h,hbase),(b,bbase)):
            ob.location=(base.x, base.y+d, base.z+bob)
            ob.keyframe_insert('location', frame=f)
        if cam is not None:
            cam.location=(hcx+span*2.0, hcy+d+span*2.4, midz+span*0.6)
            look=Vector((hcx, hcy+d, midz))-Vector(cam.location)
            cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
            cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)
    __result__=json.dumps({'ok': True, 'deck': round(deck,3), 'travel': round(travel,2)})
"""

# Real-world long-axis sizes for rideable props (meters).
_MOUNT_SIZE_M = {"skateboard": 0.82, "surfboard": 1.9, "snowboard": 1.5,
                 "sled": 1.2, "hoverboard": 0.7}


def _spawn_mount(runner, slots, mount, hero_name, total_frames, fps, verbose=True):
    """Generate + stage a rideable prop under the hero and bake the ride motion.
    Returns True if the ride animation was applied (composer then skips the
    hero gait — the board carries the rider)."""
    import copy
    import hashlib
    from pathlib import Path as _P
    from ..asset_gen import generate_reference, generate_mesh
    from ..asset_gen.reference import unload_reference_pipeline

    ident = (mount.get("identity_phrase") or "skateboard").strip()
    cache_dir = _P(__file__).resolve().parents[2] / "renders" / "_actor_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(ident.encode("utf-8")).hexdigest()[:12]
    glb = cache_dir / f"{key}.glb"

    if not glb.exists():
        slots2 = copy.deepcopy(slots)
        slots2["subject"] = {
            "name": ident, "base_pattern": "primitive_geo", "shape": None,
            "library_query": None, "identity_phrase": ident, "pose": None,
            "color_name": "neutral", "material": "matte", "emissive": False,
            "scale": 1.0, "location": [0, 0, 0],
        }
        slots2.pop("extra_subjects", None); slots2.pop("mount", None)
        ref2 = cache_dir / f"{key}_ref.png"
        if verbose:
            print(f"[composer] mount: generating '{ident}'")
        generate_reference(slots2, output_path=ref2, style="photoreal", seed=42)
        try:
            unload_reference_pipeline()
            import torch as _t
            if _t.cuda.is_available():
                _t.cuda.empty_cache()
        except Exception:
            pass
        try:
            generate_mesh(ref2, output_path=glb, engine="trellis2", tier="fast",
                          base_pattern="primitive_geo")
        except Exception as _ge:
            if verbose:
                print(f"[composer] mount: trellis2 failed ({type(_ge).__name__}) -> triposg")
            generate_mesh(ref2, output_path=glb, engine="triposg", tier="fast",
                          base_pattern="primitive_geo")
    elif verbose:
        print(f"[composer] mount: cache hit for '{ident}'")

    size_m = _MOUNT_SIZE_M.get(ident, 1.0)
    imp = runner.run("mount_import", "import_mesh_file", {
        "filepath": str(glb), "name": "Mount", "normalize_size": size_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None,
    }, critical=False)
    if not isinstance(imp, dict) or not imp.get("ok"):
        raise RuntimeError("mount import failed")
    mname = imp.get("name", "Mount")

    code = (_MOUNT_RIDE_CODE.replace("__HERO__", hero_name)
            .replace("__MOUNT__", mname)
            .replace("__TOTAL__", str(int(total_frames)))
            .replace("__FPSV__", str(int(fps))))
    res = runner.run("mount_ride", "execute_python", {"code": code}, critical=False)
    raw = res.get("result") if isinstance(res, dict) else None
    import json as _json
    info = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
    ok = bool(info and info.get("ok"))
    if verbose:
        print(f"[composer] mount ride: {'ok' if ok else 'failed'} ({info})")
    return ok


def compose_scene(
    slots: Dict[str, Any],
    paths: Dict[str, str],
    verbose: bool = True,
) -> CompositionResult:
    """Deterministically build + render a scene from slots.

    paths must include:
        - render_filepath (.png target for stills)
        - animation_dir   (directory for PNG sequence)
        - video_filepath  (.mp4 target for video)
    """
    result = CompositionResult(success=False, slots=slots)
    t0 = time.time()

    try:
        _ensure_bridge()
    except Exception as e:
        result.errors.append(f"bridge unreachable: {e}")
        result.duration_s = time.time() - t0
        return result

    runner = _StepRunner(result, verbose)

    # Lazy-import environment to avoid circular issues
    from .patterns import environment as env_module

    # Per-run unique ID — used to suffix material/object names so we can't
    # accidentally pick up stale data from previous runs.
    import datetime
    run_id = datetime.datetime.now().strftime("%H%M%S%f")[:10]

    subj = slots["subject"]
    scene = slots["scene"]
    motion = slots["motion"]
    cam_slots = slots["camera"]
    out_slots = slots["output"]

    # ── Iteration-speed flags (set by the CLI / API to fast-path through testing).
    import os
    quick_mode = os.environ.get("FANTASY_STUDIO_QUICK") == "1"
    no_render = os.environ.get("FANTASY_STUDIO_NO_RENDER") == "1"
    if quick_mode and verbose:
        print("[composer] QUICK mode: single still frame instead of 120-frame animation")
    if no_render and verbose:
        print("[composer] NO-RENDER mode: producing reference + mesh + .blend only, no MP4")

    # ── Product decision: every render is a 5-second video by default.
    # If the user's prompt had no motion words, we add a subtle camera drift
    # ("ambient orbit") so even static subjects feel cinematic. This is the
    # Sora pattern — never deliver a still when the user is expecting a clip.
    is_animation = True
    if motion.get("type") == "static":
        # Inject a gentle camera arc — slower than an "orbit" intent
        motion = {"type": "ambient_orbit", "speed": "slow"}
        if verbose:
            print(f"[composer] static prompt → defaulting to ambient camera drift (5s)")

    # Iteration mode overrides — single frame for --quick, no animation
    if quick_mode:
        is_animation = False

    result.is_animation = is_animation
    duration_s = int(out_slots.get("duration_seconds") or 5)
    if duration_s == 0:
        duration_s = 5  # always at least 5 seconds of video
    fps = 24
    total_frames = duration_s * fps if is_animation else 1

    # 1. Clean slate
    runner.run("reset", "reset_scene", {})

    # 2. Render settings (engine + resolution + fps + tier-driven samples)
    res_x, res_y = (1280, 720) if out_slots.get("resolution") == "720p" else (1920, 1080)
    tier = out_slots.get("render_tier", "fast")
    # Tier mapping: preview/fast = EEVEE (real-time), standard/cinematic = CYCLES (ray-traced)
    tier_config = {
        "preview":   {"engine": "BLENDER_EEVEE", "samples": 16},
        "fast":      {"engine": "BLENDER_EEVEE", "samples": 64},
        "standard":  {"engine": "CYCLES",        "samples": 64},
        "cinematic": {"engine": "CYCLES",        "samples": 256},
    }
    rconf = tier_config.get(tier, tier_config["fast"])
    runner.run("render_settings", "set_render_settings", {
        "engine": rconf["engine"],
        "resolution_x": res_x,
        "resolution_y": res_y,
        "samples": rconf["samples"],
        "fps": fps,
    })
    # Enable GPU compute for Cycles when available
    if rconf["engine"] == "CYCLES":
        runner.run("cycles_gpu", "execute_python", {"code": (
            "import bpy\n"
            "try:\n"
            "    bpy.context.scene.cycles.device = 'GPU'\n"
            "    prefs = bpy.context.preferences.addons.get('cycles')\n"
            "    if prefs:\n"
            "        prefs.preferences.compute_device_type = 'OPTIX' if 'OPTIX' in [d.type for d in prefs.preferences.devices] else 'CUDA'\n"
            "        for d in prefs.preferences.devices:\n"
            "            d.use = True\n"
            "except Exception: pass\n"
            "__result__ = 'gpu_attempted'"
        )})

    # 3. Frame range
    if is_animation:
        runner.run("frame_range", "set_frame_range", {"frame_start": 1, "frame_end": total_frames})

    # 4-7. PATTERN INSTANTIATION + materials
    # Pick the anatomical/structural pattern (or pass-through primitive).
    base_pattern = subj.get("base_pattern", "primitive_geo")
    if pattern_lib.get_pattern(base_pattern) is None:
        result.errors.append(f"pattern '{base_pattern}' not registered; falling back to primitive_geo")
        base_pattern = "primitive_geo"

    # ── Phase 17 GATE: try asset-driven pipeline FIRST for organic/vehicle subjects.
    # If reference→mesh→import succeeds we get a real mesh hero. If anything fails
    # we fall back to procedural pattern instantiation (the rest of the flow is unchanged).
    asset_gen_hero_name: Optional[str] = None
    # Phase 20 — PROCEDURAL hard-surface vehicle. Image-to-3D blobs cars and fuses
    # the wheels; for vehicles we build a crisp parametric car (body=Hero + 4
    # separate wheels) instead, so the geometry is sharp and the wheels can spin.
    # Treated like an asset-gen hero (skip metaball/fur/material). Gated by
    # FS_PROCEDURAL_VEHICLE; any failure falls through to the asset-gen path.
    # Phase 20 vehicle modes (FS_PROCEDURAL_VEHICLE): "0"=off (TripoSG only, no
    # wheels), "pure"=parametric box car, "1"(default)=HYBRID — keep TripoSG's
    # reference-matching body + texture, then attach crisp spinning wheels.
    used_proc_vehicle = False
    _veh_mode = os.environ.get("FS_PROCEDURAL_VEHICLE", "1")
    vehicle_hybrid = (base_pattern == "vehicle" and _veh_mode == "1")
    if base_pattern == "vehicle" and _veh_mode == "pure":
        _cname = subj.get("color_name", "") or ""
        _rgb = _resolve_color(_cname) if _cname not in ("", "neutral") else [0.55, 0.05, 0.06]
        _veh = procedural_vehicle.build_vehicle(runner, list(_rgb)[:3], verbose=verbose)
        if _veh.get("ok"):
            asset_gen_hero_name = _veh.get("hero", "Hero"); used_proc_vehicle = True
    use_asset_gen = (not used_proc_vehicle) and _should_use_asset_gen(scene, subj, slots)
    if use_asset_gen:
        if verbose:
            print(f"[composer] Phase 17 asset-driven path engaged for base_pattern='{base_pattern}'")
        asset_gen_hero_name = _run_asset_gen(slots, scene, subj, runner, paths, run_id, verbose=verbose)
        if asset_gen_hero_name is None and verbose:
            print(f"[composer] asset-gen unsuccessful → falling back to procedural")
    # Hybrid fallback: if the vehicle's TripoSG body failed, use the pure box car.
    if vehicle_hybrid and not asset_gen_hero_name:
        _cname = subj.get("color_name", "") or ""
        _rgb = _resolve_color(_cname) if _cname not in ("", "neutral") else [0.55, 0.05, 0.06]
        _veh = procedural_vehicle.build_vehicle(runner, list(_rgb)[:3], verbose=verbose)
        if _veh.get("ok"):
            asset_gen_hero_name = _veh.get("hero", "Hero"); used_proc_vehicle = True; vehicle_hybrid = False

    if asset_gen_hero_name:
        # Real mesh imported; skip procedural pattern parts entirely.
        parts = []
        if verbose:
            print(f"[composer] using imported mesh '{asset_gen_hero_name}' as hero — skipping pattern")
    else:
        parts = pattern_lib.instantiate(base_pattern, slots)
        if verbose:
            print(f"[composer] pattern '{base_pattern}' produced {len(parts)} part(s)")

    # Build the hero material (shared across non-detail parts).
    mat_params = _material_params_from_slots(subj, run_id=run_id, base_pattern=base_pattern)
    mat_result = runner.run("material", "create_material", mat_params)
    actual_mat_name = (mat_result or {}).get("name", mat_params["name"]) if isinstance(mat_result, dict) else mat_params["name"]
    if verbose and actual_mat_name != mat_params["name"]:
        print(f"[composer]   ⚠ material renamed: '{mat_params['name']}' → '{actual_mat_name}'")

    # Build accent materials for known hints (eyes, headlight, tire, foliage, wood)
    accent_mats: Dict[str, str] = _build_accent_materials(runner, run_id, mat_params, subj)

    # ── CELESTIAL OVERRIDE — when a part carries celestial params, build a richly-
    # textured material specifically for it (crater for moon, continent for earth, etc).
    celestial_parts: Dict[str, str] = {}
    for part in parts:
        if part.get("material_hint") == "celestial" and "_celestial_params" in part:
            cp = part["_celestial_params"]
            cel_mat_name = f"CelestialMat_{part['name']}_{run_id}"
            cel_params = {
                "name": cel_mat_name,
                "color": cp["color"],
                "metallic": cp.get("metallic", 0.0),
                "roughness": cp.get("roughness", 0.8),
                "texture_pattern": cp.get("texture_pattern"),
                "texture_scale": cp.get("texture_scale", 4.0),
                "texture_contrast": cp.get("texture_contrast", 0.6),
            }
            if cp.get("emissive"):
                cel_params["emission_color"] = cp["color"][:3]
                cel_params["emission_strength"] = cp.get("emission_strength", 15.0)
            cel_result = runner.run(f"cel_mat:{part['name']}", "create_material", cel_params)
            if isinstance(cel_result, dict) and cel_result.get("name"):
                celestial_parts[part["name"]] = cel_result["name"]

    # ── METABALL STRATEGY for organic creatures (quadruped, biped, except primitive_geo)
    # Instead of spawning each part as a separate primitive and trying to merge later,
    # build the ENTIRE creature as a single metaball family. Metaballs auto-blend into
    # one continuous surface — no gaps, no floating pieces. The right Blender tool
    # for organic character construction.
    METABALL_PATTERNS = {"quadruped", "biped"}
    use_metaball = base_pattern in METABALL_PATTERNS

    # Track which part is the hero — by convention the part with role="body"
    hero_name: Optional[str] = None
    placed_part_names: List[str] = []

    # Phase 17: if an imported mesh became the hero, register it now so the
    # rest of the flow (tag_hero, grounding, camera framing) treats it as primary.
    if asset_gen_hero_name:
        hero_name = asset_gen_hero_name
        placed_part_names.append(asset_gen_hero_name)

    # Phase 17: when asset-gen produced a real mesh hero, skip the entire
    # metaball / procedural-material / fur branch — that mesh already has
    # vertex colors baked from the SDXL reference and applying procedural
    # fur on a 76k-poly mesh kills the render.
    if asset_gen_hero_name and use_metaball:
        if verbose:
            print(f"[composer] asset-gen hero present — skipping metaball + procedural material + fur")
        use_metaball = False
        parts = []  # nothing more to spawn; HDRI/lights/camera/animation will run normally

    if use_metaball:
        # Build metaball element list from all hero-material parts
        meta_elements = []
        accent_parts = []
        for part in parts:
            if part.get("material_hint"):
                # Accent parts (eyes, etc) keep their own materials → spawn as primitives later
                accent_parts.append(part)
                continue
            scale = part.get("scale", [1, 1, 1])
            if isinstance(scale, (int, float)):
                scale = [float(scale)] * 3
            # Metaball size 1.0 ≈ a sphere of radius 1.0. The part's scale already
            # encodes the desired size. Multiply by 0.85 so blobs penetrate each
            # other (otherwise threshold would shrink them).
            ellipsoid_size = [float(s) * 0.85 for s in scale]
            meta_elements.append({
                "type": "ELLIPSOID",
                "location": part["location"],
                "rotation": part.get("rotation", [0, 0, 0]),
                "size_x": ellipsoid_size[0],
                "size_y": ellipsoid_size[1],
                "size_z": ellipsoid_size[2],
                "stiffness": 2.0,
            })

        # Create the unified blob (auto-converts to mesh)
        blob_result = runner.run("creature_blob", "create_metaball_blob", {
            "name": "Hero",
            "resolution": 0.06,
            "threshold": 0.6,
            "elements": meta_elements,
            "convert_to_mesh": True,
        })
        if isinstance(blob_result, dict) and blob_result.get("name"):
            hero_name = blob_result["name"]
            placed_part_names.append(hero_name)

        # Apply hero material to the blob
        if hero_name:
            runner.run("blob_material", "apply_material", {
                "object": hero_name, "material": actual_mat_name,
            })
            # Light subdivision + smooth shading for organic feel
            runner.run("blob_smooth", "execute_python", {
                "code": (
                    "import bpy\n"
                    f"o = bpy.data.objects.get('{hero_name}')\n"
                    "if o and o.data:\n"
                    "    sub = o.modifiers.new(name='BlobSmooth', type='SUBSURF')\n"
                    "    sub.levels = 1; sub.render_levels = 2\n"
                    "    for p in o.data.polygons: p.use_smooth = True\n"
                    "__result__ = 'smoothed'"
                )
            })

        # Spawn accent parts (eyes etc) as regular primitives with their own materials
        for part in accent_parts:
            spawn_result = runner.run(
                f"accent_part:{part['name']}",
                "create_primitive",
                {
                    "type": part["primitive"],
                    "name": part["name"],
                    "location": part["location"],
                    "rotation": part["rotation"],
                    "size": part["size"],
                },
            )
            actual_name = (spawn_result or {}).get("name", part["name"]) if isinstance(spawn_result, dict) else part["name"]
            placed_part_names.append(actual_name)
            if part["scale"] != [1, 1, 1]:
                runner.run(
                    f"accent_scale:{actual_name}",
                    "transform_object",
                    {"name": actual_name, "scale": part["scale"]},
                )
            hint = part.get("material_hint")
            mat_for_this = accent_mats.get(hint, actual_mat_name) if hint and hint != "celestial" else actual_mat_name
            runner.run(
                f"accent_mat:{actual_name}",
                "apply_material",
                {"object": actual_name, "material": mat_for_this},
            )
        # Skip the per-part loop below; metaball already handled all hero parts
        parts_to_spawn = []
    else:
        parts_to_spawn = parts

    for part in parts_to_spawn:
        # Spawn the primitive
        spawn_result = runner.run(
            f"part:{part['name']}",
            "create_primitive",
            {
                "type": part["primitive"],
                "name": part["name"],
                "location": part["location"],
                "rotation": part["rotation"],
                "size": part["size"],
            },
        )
        actual_name = (spawn_result or {}).get("name", part["name"]) if isinstance(spawn_result, dict) else part["name"]
        placed_part_names.append(actual_name)

        # Apply scale (transform_object handles tuple-or-scalar)
        if part["scale"] != [1, 1, 1]:
            runner.run(
                f"scale:{actual_name}",
                "transform_object",
                {"name": actual_name, "scale": part["scale"]},
            )

        # Apply optional modifiers (subdivision / bevel / etc.)
        for mod in part.get("modifiers", []):
            runner.run(
                f"mod:{actual_name}:{mod['kind']}",
                "add_modifier",
                {"object": actual_name, "kind": mod["kind"], "settings": mod.get("settings", {})},
            )

        # Pick material — celestial override > accent hint > hero
        if part["name"] in celestial_parts:
            mat_for_this = celestial_parts[part["name"]]
        else:
            hint = part.get("material_hint")
            mat_for_this = accent_mats.get(hint, actual_mat_name) if hint and hint != "celestial" else actual_mat_name
        runner.run(
            f"mat:{actual_name}",
            "apply_material",
            {"object": actual_name, "material": mat_for_this},
        )

        if part.get("role") == "body" and hero_name is None:
            hero_name = actual_name

    if hero_name is None and placed_part_names:
        hero_name = placed_part_names[0]

    # ── VEHICLE BODY MERGE: chassis + cabin via Boolean Union → one cohesive body.
    # Wheels and headlights stay separate (they need different materials anyway).
    if base_pattern == "vehicle":
        cabin_obj = next((n for n in placed_part_names if n.startswith("Cabin")), None)
        chassis_obj = next((n for n in placed_part_names if n.startswith("Chassis")), None)
        if cabin_obj and chassis_obj:
            runner.run("vehicle_body_merge", "boolean_union", {
                "target": chassis_obj,
                "operand": cabin_obj,
                "delete_operand": True,
            })

    # ── JOIN + VOXEL REMESH — only runs if we DIDN'T use metaball strategy.
    # Metaball patterns already produce a unified mesh, so skip this entirely.
    ORGANIC_PATTERNS = {"quadruped", "biped"}
    if base_pattern in ORGANIC_PATTERNS and hero_name and not use_metaball:
        # Find parts that use the HERO material (not eyes/accents)
        hero_part_names = [p["name"] for p in parts if not p.get("material_hint")]
        if len(hero_part_names) > 1:
            join_code = (
                "import bpy\n"
                "bpy.ops.object.select_all(action='DESELECT')\n"
                f"target = bpy.data.objects.get('{hero_name}')\n"
                f"names = {hero_part_names!r}\n"
                "joined = 0\n"
                "for n in names:\n"
                "    o = bpy.data.objects.get(n)\n"
                "    if o and o.type == 'MESH':\n"
                "        o.select_set(True)\n"
                "        joined += 1\n"
                "if target and joined > 1:\n"
                "    bpy.context.view_layer.objects.active = target\n"
                "    bpy.ops.object.join()\n"
                "    # Apply any pending modifiers on the joined mesh BEFORE remesh\n"
                "    for m in list(target.modifiers):\n"
                "        try:\n"
                "            bpy.ops.object.modifier_apply(modifier=m.name)\n"
                "        except Exception: pass\n"
                "    # VOXEL REMESH — this is the magic: wraps all input geometry in ONE\n"
                "    # continuous mesh. Body + head + ears + legs become one creature shape.\n"
                "    remesh = target.modifiers.new(name='OrganicMerge', type='REMESH')\n"
                "    remesh.mode = 'VOXEL'\n"
                "    remesh.voxel_size = 0.06\n"
                "    remesh.use_smooth_shade = True\n"
                "    try:\n"
                "        bpy.ops.object.modifier_apply(modifier=remesh.name)\n"
                "    except Exception as e:\n"
                "        print(f'[composer] remesh apply failed: {e}')\n"
                "    # Smooth the result with light subdivision\n"
                "    sub = target.modifiers.new(name='OrganicSmooth', type='SUBSURF')\n"
                "    sub.levels = 1; sub.render_levels = 2\n"
                "    for p in target.data.polygons: p.use_smooth = True\n"
                f"__result__ = f'remeshed {{joined}} parts into {hero_name}'\n"
            )
            runner.run("join_organic", "execute_python", {"code": join_code})

    # Tag hero for HERO_VERIFY
    if hero_name:
        runner.run("tag_hero", "execute_python", {
            "code": f"obj = bpy.data.objects.get('{hero_name}'); obj['is_forced_hero']=True; obj['hero']=True; __result__=obj.name",
        })

    # ── GROUND THE CHARACTER (Phase 15)
    # Procedural patterns place parts with feet/wheels at z<0 (e.g. legs at z=-0.1).
    # Result: the hero looks like it's floating above or sinking into the ground plane.
    # Fix: compute the lowest world-space Z across all placed parts and lift them so
    # the lowest point sits at z=0 (on the ground plane). Skip celestial — those float.
    GROUNDED_PATTERNS = {"quadruped", "biped", "vehicle"}
    # The procedural car is pre-grounded (wheels on z=0); re-grounding by the
    # BODY bbox alone would sink the wheels, so skip it for that path.
    if base_pattern in GROUNDED_PATTERNS and placed_part_names and not used_proc_vehicle:
        names_repr = repr(placed_part_names)
        ground_code = (
            "import bpy\n"
            "from mathutils import Vector\n"
            f"names = {names_repr}\n"
            "objs = [bpy.data.objects.get(n) for n in names]\n"
            "objs = [o for o in objs if o is not None and o.type in ('MESH', 'META')]\n"
            "# Force depsgraph update so bbox reflects latest modifiers/positions\n"
            "bpy.context.view_layer.update()\n"
            "min_z = float('inf')\n"
            "for o in objs:\n"
            "    for corner in o.bound_box:\n"
            "        wp = o.matrix_world @ Vector(corner)\n"
            "        if wp.z < min_z:\n"
            "            min_z = wp.z\n"
            "delta = -min_z if min_z != float('inf') else 0.0\n"
            "# Only lift if there's a real gap or sinkage (>1mm). Small tolerance avoids jitter.\n"
            "if abs(delta) > 0.001:\n"
            "    for o in objs:\n"
            "        o.location.z += delta\n"
            "    bpy.context.view_layer.update()\n"
            "__result__ = f'grounded delta={delta:.3f}'\n"
        )
        runner.run("ground_character", "execute_python", {"code": ground_code})

    # ── Phase 20 HYBRID vehicle: the TripoSG body is now grounded + textured;
    # detect its wheel positions and attach crisp spinning wheels (best of both —
    # reference-matching body + real wheels). Pure-procedural cars already have wheels.
    vehicle_wheels_attached = False
    _trellis_vehicle = (base_pattern == "vehicle" and
                        os.environ.get("FS_LAST_MESH_ENGINE") == "trellis2")
    if vehicle_hybrid and asset_gen_hero_name and not used_proc_vehicle and not _trellis_vehicle:
        # TripoSG bodies have blobby fused wheels -> cover with crisp ones.
        # TRELLIS.2 bodies have GOOD baked wheels -> keep them, rigid drive.
        _wr = procedural_vehicle.attach_wheels(runner, asset_gen_hero_name, verbose=verbose)
        vehicle_wheels_attached = bool(_wr.get("ok"))

    # ── FUR for quadrupeds (Phase 15). Real strand particles → reads as actual
    # fur instead of a smooth painted ball. Tier-scaled so previews stay fast.
    FURRY_SPECIES = {"cat", "dog", "fox", "rabbit", "sheep", "horse", "lion", "bear", "wolf"}
    species_hint = " ".join([
        str(subj.get("library_query") or ""),
        str(subj.get("name") or ""),
    ]).lower()
    # Phase 17: TripoSR/InstantMesh meshes already capture the surface in vertex
    # colors and silhouette. Adding fur particles on top kills perf (24k strands
    # × 76k polys) and re-introduces the "fluffy peanut" appearance we just removed.
    if base_pattern == "quadruped" and hero_name and not asset_gen_hero_name and any(sp in species_hint for sp in FURRY_SPECIES):
        tier = scene.get("render_tier") or subj.get("render_tier") or "fast"
        # Lower counts — 3k+ on a 2m hero became a hairball that occluded the shape.
        # These are TUNED for visible fur silhouette without losing the dog underneath.
        fur_count = {"preview": 400, "fast": 800, "standard": 2000, "cinematic": 5000}.get(tier, 800)
        # Shorter strands too — old 0.08m on a 1.5m subject was overpowering
        fur_length = 0.03 if "sheep" in species_hint else (0.06 if "lion" in species_hint or "bear" in species_hint else 0.04)
        try:
            runner.run("fur", "add_fur", {
                "object": hero_name,
                "count": fur_count,
                "length": fur_length,
                "children": 30 if tier in ("preview", "fast") else 80,
                "roughness": 0.85,
            })
        except Exception as e:
            # Non-fatal — fur is a polish step. Log via job_events if available.
            print(f"[composer] fur add failed (non-fatal): {e}")

    # ── Compute hero_loc + actual bbox-driven scale.
    # Metaball output and pattern-composed shapes have unpredictable bbox sizes
    # compared to slot.scale. Query the actual hero object's dimensions and
    # use that to scale camera distance correctly.
    hero_loc = list(subj.get("location", [0, 0, 1]))
    hero_scale = float(subj.get("scale", 1.0))
    if hero_name:
        try:
            info = registry.call("get_object_info", {"name": hero_name})
            if isinstance(info, dict) and info.get("location"):
                hero_loc = info["location"]
            if isinstance(info, dict) and info.get("dimensions"):
                # Use the longest axis of the actual bbox as our scale reference.
                # A 1.0 reference matches "a 2m cube at distance 4.8m" (medium framing).
                dims = info["dimensions"]
                longest_dim = max(dims)
                # Default reference is a 2m cube → hero_scale 1.0
                hero_scale = max(0.5, longest_dim / 2.0)
        except Exception:
            pass  # fall back to slot values

    # ── ENVIRONMENT ──────────────────────────────────────────────────────
    # Phase 19: setting-driven cinematic environment (place + mood + style →
    # gradient sky, sun, textured ground, fog, color grade). Falls back to the
    # legacy mood-only environment if no setting is present.
    setting = scene.get("setting")
    os.environ["FS_SCENE_SETTING"] = setting or ""   # read by motion_rig camera framing
    used_phase19_env = False
    realistic_env = None
    # Phase 19.5: real-world DEM terrain for desert/mountain/snow (hero placed ON
    # real elevation). Falls back to the procedural environment on any miss.
    if setting and os.environ.get("FS_REALISTIC_ENV", "1") == "1" and hero_name:
        try:
            realistic_env = _build_realistic_environment(
                runner, setting, scene.get("mood", "neutral"), hero_name, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"[composer] realistic_env errored ({type(e).__name__}: {e}) → procedural")
            realistic_env = None
    if realistic_env:
        used_phase19_env = True  # real terrain + hero-on-it + sky + sun all set
    elif setting:
        try:
            _, env_style = _resolve_tier_style(scene, subj, slots)
        except Exception:
            env_style = "photoreal"
        env_spec = env_module.resolve_environment(setting, scene.get("mood", "neutral"), env_style)
        used_phase19_env = _build_environment(runner, env_spec, verbose=verbose)

    if not used_phase19_env:
        # Legacy mood-only path (kept for safety / primitives).
        env = env_module.env_for_mood(scene.get("mood", "neutral"))
        from pathlib import Path as _Path
        backend_root = _Path(__file__).resolve().parents[2]
        hdri_dir = backend_root / "assets" / "hdri"
        hdri_path = env_module.hdri_for_mood(scene.get("mood", "neutral"), hdri_dir)
        if hdri_path is not None:
            hdri_strength = env.get("sky_strength", 1.0)
            if asset_gen_hero_name:
                hdri_strength = min(hdri_strength, 1.2)
            runner.run("world_hdri", "set_hdri_environment", {
                "hdri_path": str(hdri_path), "strength": hdri_strength,
            })
        else:
            runner.run("world_bg", "set_world_background", {
                "color": env["sky_color"], "strength": env["sky_strength"],
            })
        outdoor_moods = {"sunset", "sunrise", "golden hour", "dawn", "dusk", "noon", "daylight", "night", "moonlight", "bright"}
        needs_ground = scene.get("ground") or scene.get("mood") in outdoor_moods
        if needs_ground:
            ground_mat_name = f"GroundMat_{run_id}"
            runner.run("ground", "create_primitive", {
                "type": "plane", "name": "Ground", "location": [0, 0, 0], "size": 40.0,
            })
            runner.run("ground_material", "create_material", {
                "name": ground_mat_name, "color": env["ground_color"],
                "metallic": env["ground_metallic"], "roughness": env["ground_roughness"],
            })
            runner.run("ground_apply", "apply_material", {"object": "Ground", "material": ground_mat_name})

    # Shade-smooth all organic parts so subdivision actually softens the silhouette
    organic_names = [p["name"] for p in parts if p.get("primitive") in ("sphere", "icosphere") and p.get("role") in ("body", "head", "limb", "detail")]
    if organic_names:
        smooth_code = "; ".join([
            f"o = bpy.data.objects.get('{n}'); "
            f"[setattr(p, 'use_smooth', True) for p in o.data.polygons] if o and o.data else None"
            for n in organic_names
        ])
        runner.run("shade_smooth", "execute_python", {"code": smooth_code + "; __result__ = 'smoothed'"})

    # 8. Lighting. For asset-gen meshes, halve the energies (vertex colors
    # already encode the SDXL reference lighting). When the Phase 19 env is
    # active it provides the KEY sun, so the 3-point rig drops to a gentle fill
    # (×0.35) — just shape definition + soft shadow fill, not the main light.
    light_params = _lighting_params_from_mood(scene.get("mood", "neutral"))
    light_scale = 0.5 if asset_gen_hero_name else 1.0
    if used_phase19_env:
        light_scale *= 0.35
    runner.run("lighting", "apply_three_point_lighting", {
        "target": hero_loc,
        "color_temp": light_params.get("color_temp", "neutral"),
        "key_energy": light_params.get("key_energy", 1500) * light_scale,
        "fill_energy": light_params.get("fill_energy", 500) * light_scale,
        "rim_energy": light_params.get("rim_energy", 800) * light_scale,
    })

    # 9. Camera (framing + angle)
    #
    # Phase 18 final: for asset-gen heroes (TripoSR/InstantMesh meshes that may
    # arrive in arbitrary world orientation), use MESH-RELATIVE framing instead
    # of world-axis framing. PCA on the mesh finds its natural long/medium/short
    # axes; camera orbits perpendicular to the longest axis around the medium
    # axis. Net effect: the camera always shows a nice side profile no matter
    # which world axis the mesh happens to be oriented along.
    # DISABLED — the PCA mesh-relative orbit was the wrong approach and also
    # hit a Blender 5.1 API change (Action.fcurves removed). Replaced by the
    # deterministic orientation-audit workflow: render all 24 axis-aligned
    # orientations once, hardcode the correct per-pattern rotation in
    # mesh._PATTERN_ORIENTATION. Set _USE_PCA_ORBIT = True only to experiment.
    _USE_PCA_ORBIT = False
    used_mesh_relative_orbit = False
    if _USE_PCA_ORBIT and asset_gen_hero_name and is_animation:
        m_type = motion.get("type", "static")
        speed = motion.get("speed", "medium")
        # Only override for orbit-style motion (the default for static prompts).
        # Translate/bounce/rotate_self stay world-aligned since they move the hero.
        if m_type in ("ambient_orbit", "orbit", "static"):
            revs = 0.25 if m_type == "ambient_orbit" else _revolutions_for_speed(speed) if m_type == "orbit" else 0.25
            ok = _setup_mesh_relative_orbit(
                runner=runner,
                hero_name=asset_gen_hero_name,
                duration_frames=total_frames,
                revolutions=revs,
                lens=50.0,
                verbose=verbose,
            )
            if ok:
                used_mesh_relative_orbit = True
                if verbose:
                    print(f"[composer] camera: mesh-relative orbit (PCA-based) "
                          f"frames={total_frames} revolutions={revs:.2f}")

    if not used_mesh_relative_orbit:
        cam_xyz, look_target = _camera_position_for_framing(
            cam_slots.get("framing", "medium"),
            cam_slots.get("angle", "three-quarter"),
            hero_loc, hero_scale,
        )
        runner.run("camera", "create_camera", {"name": "Cam", "location": cam_xyz, "lens": 50.0, "set_active": True})
        runner.run("look_at", "look_at", {"object": "Cam", "target": look_target})

    # 10. Motion (always — every render is a video)
    #
    # Phase 20: real skeletal gait for legged heroes. Runs on the already-oriented
    # + textured hero (world-space rig, texture-safe). If a gait is applied we skip
    # the legacy object-translate locomotion AND idle breathing for this hero.
    # Gated by FS_SKELETAL_MOTION (default on); any failure falls back silently.
    # ── Phase 23 T1: EXTRA ACTORS — "a man walking his dog". Each companion gets
    # its own reference→mesh (cached by identity), import beside the hero, and a
    # gait WITHOUT camera tracking (the primary owns the camera). Fully gated:
    # any failure leaves the single-actor scene untouched.
    _extras = (slots.get("extra_subjects") or [])[:1]
    _spawned_extras = 0
    # Phase 23 T2: ACTION from the prompt — "two samurai warriors fighting"
    # switches bipeds from the walk gait to the combat cycle (stance + strikes
    # + lunges, opponents face-off and alternate attacks).
    _ptxt_a = (slots.get("_user_prompt") or "").lower()
    _action = "fight" if (base_pattern == "biped" and any(
        k in _ptxt_a for k in ("fighting", "fight", " duel", "dueling", "sparring", " spar", "battling", " battle"))) else "walk"
    if is_animation and hero_name and _extras and os.environ.get("FS_MULTI_ACTOR", "1") != "0":
        for _ai, _ex in enumerate(_extras, start=2):
            try:
                _spawn_extra_actor(runner, slots, _ex, _ai, hero_name,
                                   total_frames, fps, run_id, paths,
                                   action=_action, verbose=verbose)
                _spawned_extras += 1
            except Exception as _ee:
                if verbose:
                    print(f"[composer] extra actor {_ai} failed ({type(_ee).__name__}: {_ee}) — single-actor scene kept")


    skeletal_done = False
    # Phase 23 T3: MOUNT — "a cat riding a skateboard". The board is staged
    # under the hero and the pair ride together; the gait is skipped (the hero
    # keeps its standing pose). Failure-gated: any error falls through to the
    # normal gait path so the scene still works without the prop.
    _mount = slots.get("mount") if isinstance(slots.get("mount"), dict) else None
    if is_animation and hero_name and _mount and os.environ.get("FS_MOUNTS", "1") != "0":
        try:
            skeletal_done = _spawn_mount(runner, slots, _mount, hero_name,
                                         total_frames, fps, verbose=verbose)
        except Exception as _me:
            if verbose:
                print(f"[composer] mount failed ({type(_me).__name__}: {_me}) — falling back to gait")
    if skeletal_done:
        pass
    elif is_animation and hero_name and os.environ.get("FS_SKELETAL_MOTION", "1") != "0":
        if used_proc_vehicle or vehicle_wheels_attached or _trellis_vehicle:
            # Wheeled drive: body (+ wheels if any) translate, wheels spin,
            # driving camera. Mode from the user's wording (race / showcase are
            # the social-media staples); speed from the motion slot.
            _ptxt = (slots.get("_user_prompt") or "").lower()
            if any(k in _ptxt for k in ("showcase", "turntable", "show off", "showroom", "display")):
                _vmode = "showcase"
            elif any(k in _ptxt for k in ("racing", " race", "racetrack", "drag strip", "speeding")):
                _vmode = "race"
            else:
                _vmode = "drive"
            _vspeed = {"slow": 0.5, "medium": 1.0, "fast": 2.0}.get(motion.get("speed", "medium"), 1.0)
            skeletal_done = motion_rig.build_wheeled_drive(
                runner, hero_name, total_frames, fps,
                mode=_vmode, speed=_vspeed, verbose=verbose)
            # TRELLIS.2 PBR textures read near-black under the dim mood rig —
            # guarantee a real key light + ambient floor for these scenes.
            if os.environ.get("FS_LAST_MESH_ENGINE") == "trellis2":
                runner.run("trellis2_light", "execute_python", {"code": (
                    "import bpy, math\n"
                    "suns=[o for o in bpy.data.objects if o.type=='LIGHT' and o.data.type=='SUN']\n"
                    "if suns:\n"
                    "    for s in suns: s.data.energy=max(s.data.energy, 4.0)\n"
                    "else:\n"
                    "    sd=bpy.data.lights.new('T2Sun', type='SUN'); sd.energy=4.0\n"
                    "    so=bpy.data.objects.new('T2Sun', sd); bpy.context.scene.collection.objects.link(so)\n"
                    "    so.rotation_euler=(math.radians(55),0,math.radians(35))\n"
                    "w=bpy.context.scene.world\n"
                    "if w and w.use_nodes:\n"
                    "    bg=w.node_tree.nodes.get('Background')\n"
                    "    if bg: bg.inputs['Strength'].default_value=max(bg.inputs['Strength'].default_value, 0.6)\n"
                    "for s in suns:\n"
                    "    s.data.energy=max(s.data.energy, 5.0)\n"
                    "# Align the key sun with the camera so the camera views the LIT side\n"
                    "# (subjects were rendering shadow-side-to-camera = too dark).\n"
                    "cam=bpy.context.scene.camera\n"
                    "hero=bpy.data.objects.get('Hero')\n"
                    "if cam is not None and suns:\n"
                    "    hx,hy=(hero.location.x,hero.location.y) if hero else (0.0,0.0)\n"
                    "    theta=math.atan2(cam.location.y-hy, cam.location.x-hx)\n"
                    "    suns[0].rotation_euler=(math.radians(50),0.0,theta+math.pi/2)\n"
                    "try: bpy.context.scene.view_settings.exposure=1.2\n"
                    "except Exception: pass\n"
                    "__result__='lit'\n"
                )}, critical=False)
        elif base_pattern in motion_rig.SKELETAL_PATTERNS:
            skeletal_done = motion_rig.build_skeletal_gait(
                runner, hero_name, base_pattern, total_frames, fps,
                wide=(1.7 if _spawned_extras else None),
                action=_action, phase=0.0, face=1.0, verbose=verbose)

    if is_animation and not used_mesh_relative_orbit and not skeletal_done:
        m_type = motion.get("type", "static")
        speed = motion.get("speed", "medium")

        if m_type == "ambient_orbit":
            # Subtle camera arc for static prompts — quarter rotation over 5s
            radius = math.dist(cam_xyz, look_target)
            runner.run("ambient_orbit", "orbit_camera_around", {
                "camera": "Cam", "target": look_target,
                "radius": radius, "height": cam_xyz[2] - look_target[2],
                "duration_frames": total_frames,
                "revolutions": 0.25,   # quarter turn = cinematic dolly feel
            })
        elif m_type == "orbit":
            # camera circles the hero
            radius = math.dist(cam_xyz, look_target)
            runner.run("orbit", "orbit_camera_around", {
                "camera": "Cam", "target": look_target,
                "radius": radius, "height": cam_xyz[2] - look_target[2],
                "duration_frames": total_frames,
                "revolutions": _revolutions_for_speed(speed),
            })
        elif m_type == "rotate_self":
            # hero spins in place around Z
            rotation_amount = _rotation_radians_for_speed(speed)
            runner.run("rotate_self", "animate_property", {
                "object": hero_name, "data_path": "rotation_euler",
                "start_value": [0, 0, 0],
                "end_value": [0, 0, rotation_amount],
                "start_frame": 1, "end_frame": total_frames,
            })
        elif m_type == "translate":
            # hero moves across the scene (default: -X to +X)
            # For organic creatures, layer a walking bounce on top of the X motion
            distance = {"slow": 4, "medium": 8, "fast": 14}.get(speed, 8)
            organic = base_pattern in ORGANIC_PATTERNS
            bounce_h = 0.15 if organic else 0.0
            # 5 keyframes for walking gait — start, peak1, down (mid), peak2, end
            walk_path = [
                (1,                     [hero_loc[0] - distance / 2,        hero_loc[1], hero_loc[2]]),
                (int(total_frames*0.25), [hero_loc[0] - distance / 4,        hero_loc[1], hero_loc[2] + bounce_h]),
                (int(total_frames*0.50), [hero_loc[0],                       hero_loc[1], hero_loc[2]]),
                (int(total_frames*0.75), [hero_loc[0] + distance / 4,        hero_loc[1], hero_loc[2] + bounce_h]),
                (total_frames,           [hero_loc[0] + distance / 2,        hero_loc[1], hero_loc[2]]),
            ]
            for frame, loc in walk_path:
                runner.run(f"walk_kf_{frame}", "set_keyframe", {
                    "object": hero_name, "data_path": "location",
                    "value": loc, "frame": frame,
                })
        elif m_type == "bounce":
            # hero bounces up — chain 3 keyframes via two animate_property calls
            up = [hero_loc[0], hero_loc[1], hero_loc[2] + 2.0]
            mid_frame = total_frames // 2
            runner.run("bounce_up", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": hero_loc, "end_value": up,
                "start_frame": 1, "end_frame": mid_frame,
            })
            runner.run("bounce_down", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": up, "end_value": hero_loc,
                "start_frame": mid_frame, "end_frame": total_frames,
            })
        elif m_type == "drift":
            # gentle XY drift
            distance = 2.0
            end = [hero_loc[0] + distance, hero_loc[1] + distance * 0.5, hero_loc[2]]
            runner.run("drift", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": hero_loc, "end_value": end,
                "start_frame": 1, "end_frame": total_frames,
            })

    # ── 10b. IDLE LIFE — organic creatures breathe; celestial bodies rotate.
    # These layer ON TOP of the motion patterns so subjects feel alive whether
    # they're static or moving.
    if is_animation and hero_name:
        # Breathing for creatures during ambient_orbit (static prompt → camera-moves only).
        # Skipped when a skeletal gait is already driving the hero (Phase 20).
        if base_pattern in ORGANIC_PATTERNS and motion.get("type") == "ambient_orbit" and not skeletal_done:
            breath_code = (
                "import bpy\n"
                f"o = bpy.data.objects.get('{hero_name}')\n"
                "if o:\n"
                "    sx, sy, sz = o.scale.x, o.scale.y, o.scale.z\n"
                "    # 5 keyframes: rest → inhale → rest → inhale → rest\n"
                "    for f, mult in [(1, 1.00), (30, 1.03), (60, 1.00), (90, 1.03), (120, 1.00)]:\n"
                "        o.scale = (sx, sy * mult, sz * (1.0 + (mult-1) * 0.5))\n"
                "        o.keyframe_insert(data_path='scale', frame=f)\n"
                "__result__ = 'breathing'\n"
            )
            runner.run("idle_breathing", "execute_python", {"code": breath_code})

        # Celestial bodies rotate on Z axis — planets spin
        if base_pattern == "celestial":
            import math as _m
            # ~0.3 of a full rotation in 5s (slow majestic spin)
            rotation_z = _m.pi * 0.6
            runner.run("planet_spin_start", "set_keyframe", {
                "object": hero_name, "data_path": "rotation_euler",
                "value": [0, 0, 0], "frame": 1,
            })
            runner.run("planet_spin_end", "set_keyframe", {
                "object": hero_name, "data_path": "rotation_euler",
                "value": [0, 0, rotation_z], "frame": total_frames,
            })

        # Trees sway gently — subtle Y-axis tilt back and forth
        if base_pattern == "tree":
            sway_code = (
                "import bpy, math\n"
                f"o = bpy.data.objects.get('{hero_name}')\n"
                "if o:\n"
                "    for f, deg in [(1, 0), (30, 2), (60, 0), (90, -2), (120, 0)]:\n"
                "        o.rotation_euler = (0, math.radians(deg), 0)\n"
                "        o.keyframe_insert(data_path='rotation_euler', frame=f)\n"
                "__result__ = 'swaying'\n"
            )
            runner.run("tree_sway", "execute_python", {"code": sway_code})

    # 11. Verify (informational — we don't abort on failure)
    verify_result = runner.run("verify", "hero_verify", {})
    if verbose and isinstance(verify_result, dict):
        passed = verify_result.get("passed")
        print(f"[composer] hero_verify: {'PASS' if passed else 'FAIL (continuing anyway)'}")
        if not passed:
            for r in verify_result.get("abort_reasons", []):
                print(f"[composer]   • {r}")

    # 12. Render — skipped entirely in --no-render mode
    if no_render:
        if verbose:
            print("[composer] NO-RENDER: skipping render_animation + encode_video.")
        # Still produce a render_path/video_path placeholder so the .blend save uses a real basename.
        result.render_path = paths.get("render_filepath")
    elif is_animation:
        anim_dir = paths["animation_dir"]
        video_path = paths["video_filepath"]
        runner.run("render_animation", "render_animation", {
            "output_dir": anim_dir,
            "frame_start": 1, "frame_end": total_frames, "fps": fps,
        }, critical=True)

        # 12a. Phase 16 — diffusion refinement (optional, between render and encode)
        _maybe_refine_animation(anim_dir, slots, scene, subj, runner, verbose=verbose)

        runner.run("encode_video", "encode_video", {
            "frame_dir": anim_dir, "mp4_path": video_path, "fps": fps,
        }, critical=True)
        result.video_path = video_path
        result.render_path = str(Path(anim_dir) / "frame_0001.png")
    else:
        render_path = paths["render_filepath"]
        runner.run("render_frame", "render_frame", {"filepath": render_path}, critical=True)

        # 12a. Phase 16 — single-frame refinement
        _maybe_refine_single(render_path, slots, scene, subj, runner, verbose=verbose)

        result.render_path = render_path

    # Phase 17 deliverable: ship a .blend file alongside the MP4 so users
    # can open it in Blender and tweak. Saved BEFORE we declare success so
    # a failed save shows up in errors but doesn't kill the render.
    primary_artifact = result.video_path or result.render_path
    if primary_artifact:
        blend_path = str(Path(primary_artifact).with_suffix(".blend"))
        try:
            save_res = runner.run("save_blend", "save_blend_file", {
                "filepath": blend_path,
                "compress": True,
            }, critical=False)
            if isinstance(save_res, dict) and save_res.get("ok"):
                result.blend_path = blend_path
        except Exception as e:
            if verbose:
                print(f"[composer] save_blend skipped: {type(e).__name__}: {e}")

    result.success = result.render_path is not None and (
        not is_animation or result.video_path is not None
    )
    result.duration_s = time.time() - t0

    if verbose:
        artifact = result.video_path or result.render_path
        print(f"[composer] DONE in {result.duration_s:.1f}s — {len(result.steps_run)} steps, "
              f"{len(result.errors)} errors")
        print(f"[composer] artifact: {artifact}")
        if getattr(result, "blend_path", None):
            print(f"[composer] blend file: {result.blend_path}")

    return result
