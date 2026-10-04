"""Build the motion-matching database (2026-10-03).

Motion matching (Clavet and Zadziuk, GDC 2016; Holden's MIT reference
implementation, orangeduck/Motion-Matching) plays real captured motion: ten
times a second the runtime asks "which frame in all of this data has feet like
mine now and is about to go where the player is steering", and jumps there with
an inertialized blend. Starts, stops, turns and changes of pace then come from
an actor doing them, not from one looping cycle bent to fit.

This script turns curated BVH takes into one shared database every character
uses; the runtime (runtime/proc/mm.js) retargets it onto each rig by rotation
transfer, the same transform as the bake (retarget_rot.py).

Per frame, at 30 fps, in the character's own frame (the "root": the hips on
the ground, facing where the pelvis faces; +Z forward, +X the body's left,
+Y up, metres, legs scaled to 0.87 m):
  rot   21 bone world rotations, re-expressed against one canonical rest pose
        (W' = W . Q, Q turning the canonical rest direction onto the
        source's), so takes from different skeletons share one rest pose
  hips  the hips' position over the root
  feat  27 matching features: both ankles' positions and velocities, the
        hips' velocity, and the root's position and facing 1/3, 2/3 and 1 s
        ahead (Holden's set)
Every take is also mirrored (left and right swapped), which doubles the data
and balances turns.

Sources: CMU Graphics Lab (free in commercial products, credited in every
export) and 100STYLE (CC BY 4.0, credited). Output: assets/mocap/mm/
mm_db.bin (+ mm_db.json header).

    python tools/mmdb.py            # build
    python tools/mmdb.py --list     # takes and durations only
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.orchestrator import bvh  # noqa: E402

CMU = ROOT / "assets" / "mocap" / "_cmu_src"
CMU_LOCAL = ROOT / "assets" / "mocap" / "cmu"
STYLE = ROOT / "assets" / "mocap" / "_100style_src" / "100STYLE" / "Neutral"
OUT = ROOT / "assets" / "mocap" / "mm"
FPS = 30
LEG = 0.87

# stored bones; each rig's forearm twist bone reads its forearm's track
BONES = ["hips", "spine", "chest", "neck", "head",
         "clav_L", "uparm_L", "lowarm_L", "hand_L",
         "clav_R", "uparm_R", "lowarm_R", "hand_R",
         "upleg_L", "lowleg_L", "foot_L", "upleg_R", "lowleg_R", "foot_R"]
MIRROR = {b: (b[:-2] + ("_R" if b.endswith("_L") else "_L")) if b[-2:] in ("_L", "_R") else b for b in BONES}

# target bone -> (source joint, the joint its segment points at; None = end site)
MAP_CMU = {
    "hips": ("Hips", "Spine"), "spine": ("Spine", "Spine1"), "chest": ("Spine1", "Neck1"),
    "neck": ("Neck", "Head"), "head": ("Head", None),
    "clav_L": ("LeftShoulder", "LeftArm"), "uparm_L": ("LeftArm", "LeftForeArm"),
    "lowarm_L": ("LeftForeArm", "LeftHand"), "lowarm_tw_L": ("LeftForeArm", "LeftHand"),
    "hand_L": ("LeftHand", "LeftHandIndex1"),
    "clav_R": ("RightShoulder", "RightArm"), "uparm_R": ("RightArm", "RightForeArm"),
    "lowarm_R": ("RightForeArm", "RightHand"), "lowarm_tw_R": ("RightForeArm", "RightHand"),
    "hand_R": ("RightHand", "RightHandIndex1"),
    "upleg_L": ("LeftUpLeg", "LeftLeg"), "lowleg_L": ("LeftLeg", "LeftFoot"), "foot_L": ("LeftFoot", "LeftToeBase"),
    "upleg_R": ("RightUpLeg", "RightLeg"), "lowleg_R": ("RightLeg", "RightFoot"), "foot_R": ("RightFoot", "RightToeBase"),
}
MAP_STYLE = {
    "hips": ("Hips", "Chest"), "spine": ("Chest2", "Chest3"), "chest": ("Chest4", "Neck"),
    "neck": ("Neck", "Head"), "head": ("Head", None),
    "clav_L": ("LeftCollar", "LeftShoulder"), "uparm_L": ("LeftShoulder", "LeftElbow"),
    "lowarm_L": ("LeftElbow", "LeftWrist"), "lowarm_tw_L": ("LeftElbow", "LeftWrist"),
    "hand_L": ("LeftWrist", None),
    "clav_R": ("RightCollar", "RightShoulder"), "uparm_R": ("RightShoulder", "RightElbow"),
    "lowarm_R": ("RightElbow", "RightWrist"), "lowarm_tw_R": ("RightElbow", "RightWrist"),
    "hand_R": ("RightWrist", None),
    "upleg_L": ("LeftHip", "LeftKnee"), "lowleg_L": ("LeftKnee", "LeftAnkle"), "foot_L": ("LeftAnkle", "LeftToe"),
    "upleg_R": ("RightHip", "RightKnee"), "lowleg_R": ("RightKnee", "RightAnkle"), "foot_R": ("RightAnkle", "RightToe"),
}

# the canonical rest pose every take is expressed against: a T-pose facing +Z,
# the body's left on +X, feet pointing forward and down
_F = np.array([0.0, -0.45, 0.89]); _F /= np.linalg.norm(_F)
DC = {"hips": (0, 1, 0), "spine": (0, 1, 0), "chest": (0, 1, 0), "neck": (0, 1, 0), "head": (0, 1, 0),
      "clav_L": (1, 0, 0), "uparm_L": (1, 0, 0), "lowarm_L": (1, 0, 0), "lowarm_tw_L": (1, 0, 0), "hand_L": (1, 0, 0),
      "clav_R": (-1, 0, 0), "uparm_R": (-1, 0, 0), "lowarm_R": (-1, 0, 0), "lowarm_tw_R": (-1, 0, 0), "hand_R": (-1, 0, 0),
      "upleg_L": (0, -1, 0), "lowleg_L": (0, -1, 0), "foot_L": tuple(_F),
      "upleg_R": (0, -1, 0), "lowleg_R": (0, -1, 0), "foot_R": tuple(_F)}

# THE TAKES: (file, start s, end s or None, label). Long repetitive takes are
# capped; the budget is a database a web game can load in a second or two.
TAKES = [
    # standing and stepping off (100STYLE neutral, CC BY 4.0)
    ("style:Neutral_ID", 0.0, 22.0, "idle, step in and out"),
    ("style:Neutral_FW", 8.0, 28.0, "walk, curves and turns"),
    ("style:Neutral_FR", 8.0, 26.0, "jog, curves"),
    ("style:Neutral_BW", 8.0, 20.0, "walk backward"),
    ("style:Neutral_SW", 8.0, 20.0, "sidestep"),
    ("style:Neutral_TR1", 10.0, 30.0, "gait transitions"),
    # straight runs and jogs (CMU)
    *[(f"cmu:09_{i:02d}", 0, None, "run") for i in range(1, 12)],
    ("cmu:09_12", 0, 8, "walk forward, backward, sideways"),
    *[(f"cmu:16_{i}", 0, None, "run/jog") for i in (35, 36, 45, 46, 55, 56)],
    *[(f"cmu:35_{i}", 0, None, "run/jog") for i in range(17, 27)],
    *[(f"cmu:127_{i:02d}", 0, None, "run") for i in (3, 6, 7, 8)],
    *[(f"cmu:141_{i:02d}", 0, None, "sprint") for i in (1, 2, 3)],
    ("cmu:143_01", 0, None, "sprint"),
    # running turns
    *[(f"cmu:16_{i}", 0, None, "run turn/veer") for i in (37, 39, 41, 43, 48, 49, 51, 53)],
    *[(f"cmu:127_{i:02d}", 0, None, "run turn/veer/sidestep") for i in range(9, 17)],
    ("cmu:128_02", 0, None, "run left"), ("cmu:128_03", 0, None, "run right"),
    ("cmu:143_04", 0, None, "run figure 8"),
    ("cmu:139_12", 0, None, "run in circles"),
    # starts and stops
    ("cmu:16_08", 0, None, "run, sudden stop"), ("cmu:16_57", 0, None, "run, sudden stop"),
    *[(f"cmu:104_{i:02d}", 0, None, "start/stop jog and run") for i in (6, 8, 9, 10, 53, 54, 56, 57)],
    ("cmu:127_04", 0, None, "walk to run"), ("cmu:127_05", 0, None, "run to quick stop"),
    *[(f"cmu:128_{i:02d}", 0, None, "run stop run") for i in (5, 6, 7, 8)],
    ("cmu:143_02", 0, None, "run to stop"), ("cmu:143_03", 0, None, "start to run"),
    # (CMU 133's "walk stop walk" left out: a stooped walk, 12 degrees over
    # its own standing posture, played as a hero's stroll)
    ("cmu:131_01", 0, None, "start walk stop"),
    *[(f"cmu:134_{i}", 0, None, "start, stop and go") for i in (10, 11, 12, 13)],
    ("cmu:16_33", 0, None, "slow walk, stop"),
    # walking turns, turning on the spot
    *[(f"cmu:16_{i}", 0, None, "walk turn/veer") for i in (11, 13, 17, 19, 23, 25, 27, 29)],
    ("cmu:69_06", 0, 10, "walk and turn"), ("cmu:69_12", 0, 10, "walk and turn both ways"),
    ("cmu:69_13", 0, 9, "walk, turn in place"), ("cmu:69_16", 0, 10, "turn in place"),
    ("cmu:69_18", 0, 10, "turn in place, other way"),
    *[(f"cmu:69_{i}", 0, None, "walk 90 turn") for i in (20, 24, 28, 31)],
    ("cmu:36_02", 0, 12, "walk, turn around, walk back"),
    *[(f"cmu:83_{i}", 0, None, "walk 90 turn") for i in (36, 37)],
    # backpedal and sidestep
    ("cmu:69_34", 0, 9, "walk backwards and turn"), ("cmu:69_42", 0, 9, "walk sideways and turn"),
    ("cmu:69_50", 0, None, "walk sideways and backwards"),
    ("cmu:136_25", 0, 10, "walk backwards"), ("cmu:143_39", 0, None, "walk backwards"),
    ("cmu:41_02", 0, 10, "walk forward, backward, sideways"),
    # plain walks (already local)
    *[(f"local:{n}", 0, None, "walk") for n in ("02_01", "02_02", "07_01", "08_01", "35_01")],
]


def _src(tag: str) -> tuple[Path, dict]:
    kind, name = tag.split(":")
    if kind == "style":
        return STYLE / f"{name}.bvh", MAP_STYLE
    if kind == "local":
        return CMU_LOCAL / f"{name}.bvh", MAP_CMU
    return CMU / f"{name}.bvh", MAP_CMU


def _arc(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Minimal rotation matrix taking unit a onto unit b."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b))
    if c < -0.999999:                      # opposite: any perpendicular axis
        ax = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1 / (1 + c))


def _roty(a):
    c, s = np.cos(a), np.sin(a)
    o, z = np.ones_like(a), np.zeros_like(a)
    return np.stack([np.stack([c, z, s], -1), np.stack([z, o, z], -1), np.stack([-s, z, c], -1)], -2)


def _quat(m: np.ndarray) -> np.ndarray:
    """(..., 3, 3) -> (..., 4) as x, y, z, w with w >= 0."""
    m = np.asarray(m)
    tr = m[..., 0, 0] + m[..., 1, 1] + m[..., 2, 2]
    q = np.zeros(m.shape[:-2] + (4,))
    w = np.sqrt(np.maximum(0, 1 + tr)) / 2
    x = np.sqrt(np.maximum(0, 1 + m[..., 0, 0] - m[..., 1, 1] - m[..., 2, 2])) / 2
    y = np.sqrt(np.maximum(0, 1 - m[..., 0, 0] + m[..., 1, 1] - m[..., 2, 2])) / 2
    z = np.sqrt(np.maximum(0, 1 - m[..., 0, 0] - m[..., 1, 1] + m[..., 2, 2])) / 2
    x = np.copysign(x, m[..., 2, 1] - m[..., 1, 2])
    y = np.copysign(y, m[..., 0, 2] - m[..., 2, 0])
    z = np.copysign(z, m[..., 1, 0] - m[..., 0, 1])
    q[..., 0], q[..., 1], q[..., 2], q[..., 3] = x, y, z, w
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def _smooth(x: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing along axis 0 (edges held)."""
    if sigma <= 0:
        return x
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    pad = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)], 0)
    out = np.zeros_like(x, dtype=np.float64)
    for i, kv in enumerate(k):
        out += kv * pad[i:i + len(x)]
    return out


def load_take(tag: str, t0: float, t1: float | None):
    """One take as raw arrays at 30 fps in a frame where the rest pose faces +Z."""
    path, M = _src(tag)
    b = bvh.read(path)
    legs = (M["upleg_L"][0], M["lowleg_L"][0], M["foot_L"][0])
    scale = LEG / bvh.leg_length(b, *legs)
    R, P = bvh.fk(b, scale)
    src_fps = 1.0 / b.frame_time
    # rest positions (all rotations identity)
    J = len(b.names)
    rest = np.zeros((J, 3))
    for j in range(J):
        p = b.parents[j]
        rest[j] = (rest[p] if p >= 0 else 0) + b.offsets[j] * scale
    li, ri = b.index(M["upleg_L"][0]), b.index(M["upleg_R"][0])
    left = rest[li] - rest[ri]; left[1] = 0
    fwd = np.cross(left, [0, 1, 0])
    yaw0 = math.atan2(fwd[0], fwd[2])
    Ry = _roty(np.array(-yaw0))
    # trim: the first frames of a CMU take are a T-pose; then the window
    skip = 3 if tag.startswith(("cmu", "local")) else 0
    a = max(skip, int(t0 * src_fps)); e = len(R) if t1 is None else min(len(R), int(t1 * src_fps))
    e = max(a + 2, e - int(0.05 * src_fps))
    idx = np.arange(a, e, src_fps / FPS).astype(int)
    R, P = R[idx], P[idx]
    W, ds = {}, {}
    for t in BONES:
        j, c = M[t]
        ji = b.index(j)
        W[t] = Ry @ R[:, ji] @ Ry.T
        if c is not None and c in b.names:
            d = rest[b.index(c)] - rest[ji]
        elif ji in b.ends:
            d = np.array(b.ends[ji]) * scale
        else:
            d = np.array(DC[t], dtype=float)
        ds[t] = Ry @ d / np.linalg.norm(d)
    pos = {k: P[:, b.index(M[k][0])] @ Ry.T for k in ("hips", "foot_L", "foot_R")}
    return W, ds, pos


def mirror(W, ds, pos):
    Mx = np.diag([-1.0, 1.0, 1.0])
    W2 = {t: Mx @ W[MIRROR[t]] @ Mx for t in BONES}
    ds2 = {t: Mx @ ds[MIRROR[t]] for t in BONES}
    pos2 = {"hips": pos["hips"] @ Mx, "foot_L": pos["foot_R"] @ Mx, "foot_R": pos["foot_L"] @ Mx}
    return W2, ds2, pos2


def process(W, ds, pos):
    """Root frame, canonical rotations, features for one (possibly mirrored) take."""
    F = len(pos["hips"])
    # floor: the planted ankle sits at its own height over the ground
    low = np.minimum(pos["foot_L"][:, 1], pos["foot_R"][:, 1])
    floor = np.percentile(low, 3) - 0.08
    hips = pos["hips"].copy()
    # the root: hips over the ground, facing the pelvis's forward, smoothed
    rp = hips.copy(); rp[:, 1] = 0
    rp = _smooth(rp, 2.0)
    f = W["hips"] @ np.array([0, 0, 1.0])
    f[:, 1] = 0
    f = _smooth(f, 3.0)
    yaw = np.arctan2(f[:, 0], f[:, 2])
    Rinv = _roty(-yaw)                                   # world -> root frame
    rot = np.zeros((F, len(BONES), 4))
    for k, t in enumerate(BONES):
        Q = _arc(np.array(DC[t], float), ds[t])
        rot[:, k] = _quat(Rinv @ W[t] @ Q)
    def rel(p):
        d = p - rp; d = np.einsum("fij,fj->fi", Rinv, d); d[:, 1] = p[:, 1] - floor
        return d
    hip_rel = rel(hips)
    fl, fr = rel(pos["foot_L"]), rel(pos["foot_R"])
    def vel(p):
        v = np.gradient(p, axis=0) * FPS
        return np.einsum("fij,fj->fi", Rinv, v)
    vfl, vfr, vh = vel(pos["foot_L"]), vel(pos["foot_R"]), vel(hips)
    traj_p, traj_d = [], []
    # PAST THE END OF A TAKE THE BODY CARRIES ON (2026-10-03): CMU's runs are
    # one or two seconds long, and a future clamped at the last frame read as
    # a stop, so a sprint's own frames were never a match for running on. The
    # root is extrapolated at its last velocity and heading instead.
    v_end = (rp[-1] - rp[-min(6, F - 1) - 1]) / max(1, min(6, F - 1))
    for k in (10, 20, 30):
        idx = np.arange(F) + k
        j = np.minimum(idx, F - 1)
        over = (idx - j)[:, None]
        fut = rp[j] + v_end[None, :] * over
        dp = np.einsum("fij,fj->fi", Rinv, fut - rp)
        dd = np.einsum("fij,fj->fi", Rinv, np.stack([np.sin(yaw[j]), np.zeros(F), np.cos(yaw[j])], -1))
        traj_p.append(dp[:, [0, 2]]); traj_d.append(dd[:, [0, 2]])
    feat = np.concatenate([fl, fr, vfl, vfr, vh] + traj_p + traj_d, axis=1)   # 3+3+3+3+3+6+6 = 27
    # contacts: an ankle low and slow is planted
    con = np.stack([(fl[:, 1] < 0.08 + 0.05) & (np.linalg.norm(vfl, axis=1) < 0.6),
                    (fr[:, 1] < 0.08 + 0.05) & (np.linalg.norm(vfr, axis=1) < 0.6)], 1)
    speed = np.linalg.norm(np.gradient(rp, axis=0) * FPS, axis=1)
    return rot, hip_rel, feat.astype(np.float32), con, speed


def _qmul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], -1)


# THE TORSO STANDS AS THE ACTOR STOOD (2026-10-03). A capture skeleton's rest
# is a T-pose, not a stance: CMU's upper spine rests about ten degrees behind
# a natural standing back (a plain walk read 9-17 degrees of chest pitch, a jog
# 18-26), its collarbones 16-38 degrees up (an 18 degree shrug), 100STYLE's
# neck bent back (a relaxed head read 25-38 degrees down). Copied as
# directions onto a rig that rests in a natural stance, every hero hunched.
# The torso bones are re-referenced to each dataset's own average STANDING
# pose, so standing still puts our torso at its rest and only the lean and
# bend away from standing transfer. Limbs keep direction matching (a T-pose
# arm onto an A-pose arm needs it).
TORSO = ["hips", "spine", "chest", "neck", "head", "clav_L", "clav_R"]


def build(list_only: bool = False):
    rots, hipss, feats, cons, ranges, info = [], [], [], [], [], []
    dsets, stands = [], []
    start = 0
    for tag, t0, t1, label in TAKES:
        path, _ = _src(tag)
        if not path.exists():
            print(f"  missing {tag}"); continue
        W, ds, pos = load_take(tag, t0, t1)
        n = len(pos["hips"])
        if list_only:
            print(f"  {tag:18s} {n / FPS:5.1f}s  {label}"); start += 2 * n; continue
        for mir in (False, True):
            Wm, dsm, posm = mirror(W, ds, pos) if mir else (W, ds, pos)
            rot, hip, feat, con, sp = process(Wm, dsm, posm)
            rots.append(rot); hipss.append(hip); feats.append(feat); cons.append(con)
            dsets.append("style" if tag.startswith("style") else "cmu:" + tag.split(":")[1].split("_")[0].lstrip("0"))
            stands.append((sp < 0.15) & con[:, 0] & con[:, 1])
            ranges.append([start, start + n]); start += n
            info.append({"take": tag + (" (mirrored)" if mir else ""), "label": label, "frames": n,
                         "speed_p50": round(float(np.median(sp)), 2), "speed_max": round(float(sp.max()), 2)})
    if list_only:
        print(f"total {start} frames with mirrors = {start / FPS / 60:.1f} min"); return
    rot = np.concatenate(rots); hip = np.concatenate(hipss); feat = np.concatenate(feats); con = np.concatenate(cons)
    F = len(rot)
    # sign continuity within each range (q and -q are one rotation)
    for a, e in ranges:
        for i in range(a + 1, e):
            flip = (rot[i] * rot[i - 1]).sum(-1) < 0
            rot[i, flip] *= -1
    # each actor stands their own way (CMU subject 133 stoops; 127 leans), so
    # the reference is per actor where they stood still long enough (30
    # frames), else the average of their dataset
    def _mean_q(idx, b):
        qs = rot[idx, b].copy()
        qs[(qs * qs[0]).sum(-1) < 0] *= -1
        S = qs.mean(0)
        return S / np.linalg.norm(S)
    standing_ref = {}
    stand_idx = {}
    for r, (a, e) in enumerate(ranges):
        stand_idx.setdefault(dsets[r], []).append(np.arange(a, e)[stands[r]])
    stand_idx = {k: np.concatenate(v) for k, v in stand_idx.items()}
    pool = {"style": stand_idx.get("style", np.array([], int)),
            "cmu": np.concatenate([v for k, v in stand_idx.items() if k.startswith("cmu")])}
    refs = {}
    for dname in sorted(set(dsets)):
        own = stand_idx.get(dname, np.array([], int))
        use = own if len(own) >= 30 else pool["style" if dname == "style" else "cmu"]
        standing_ref[dname] = "own %d" % len(own) if len(own) >= 30 else "dataset"
        refs[dname] = {t: _mean_q(use, BONES.index(t)) for t in TORSO}
    for r, (a, e) in enumerate(ranges):
        for t in TORSO:
            b = BONES.index(t)
            Sinv = refs[dsets[r]][t] * np.array([-1, -1, -1, 1.0])
            rot[a:e, b] = _qmul(rot[a:e, b], Sinv[None, :])
    for a, e in ranges:                       # continuity again after the re-reference
        for i in range(a + 1, e):
            flip = (rot[i] * rot[i - 1]).sum(-1) < 0
            rot[i, flip] *= -1
    print("standing reference frames:", standing_ref)
    # feature normalisation: per group, one scale (Holden), then a weight
    # weights: Holden's, with the path a little heavier and the feet's speed a
    # little lighter, so a stroll is matched to walks, not to the start of a jog
    groups = [(0, 3, 0.75), (3, 6, 0.75), (6, 9, 0.75), (9, 12, 0.75), (12, 15, 1.0), (15, 21, 1.25), (21, 27, 1.5)]
    mean = feat.mean(0)
    std = np.zeros(27, np.float32); weight = np.zeros(27, np.float32)
    for a, e, w in groups:
        std[a:e] = feat[:, a:e].std(0).mean() + 1e-6; weight[a:e] = w
    OUT.mkdir(parents=True, exist_ok=True)
    rot_i16 = np.round(rot.reshape(F, -1) * 32767).astype(np.int16)
    hip_i16 = np.round(np.clip(hip, -3.2, 3.2) * 10000).astype(np.int16)
    feat_n = ((feat - mean) / std).astype(np.float32)
    con_u8 = (con[:, 0].astype(np.uint8) | (con[:, 1].astype(np.uint8) << 1))
    # THE LEAN OF EACH FRAME (2026-10-03): the features say where the feet
    # and the path go, nothing about posture, so a jog-off after a stop could
    # play an athlete's explosive restart, 22 degrees over. Each frame's trunk
    # lean (spine and chest up-axes, pitched forward in the root's frame) is
    # stored, and the runtime only takes frames whose lean the speed asked for
    # can carry (mm.js leanBudget).
    def _up(q):
        u = q[..., :3]; w = q[..., 3:]
        v = np.array([0.0, 1.0, 0.0])
        t = 2 * np.cross(u, v)
        return v + w * t + np.cross(u, t)
    tv = 0.4 * _up(rot[:, BONES.index("spine")]) + 0.6 * _up(rot[:, BONES.index("chest")])
    lean = np.degrees(np.arctan2(tv[:, 2], tv[:, 1]))
    lean_i8 = np.clip(np.round(lean), -100, 100).astype(np.int8)
    blob = (rot_i16.tobytes() + hip_i16.tobytes() + feat_n.astype(np.float16).tobytes() + con_u8.tobytes()
            + lean_i8.tobytes())
    (OUT / "mm_db.bin").write_bytes(blob)
    head = {"version": 1, "fps": FPS, "frames": F, "bones": BONES, "leg": LEG,
            "rest_dirs": {t: list(map(float, DC[t])) for t in BONES},
            "layout": {"rot_i16": [0, F * len(BONES) * 4], "hips_i16": F * len(BONES) * 4 * 2,
                       "feat_f16": F * len(BONES) * 4 * 2 + F * 3 * 2,
                       "contact_u8": F * len(BONES) * 4 * 2 + F * 3 * 2 + F * 27 * 2,
                       "lean_i8": F * len(BONES) * 4 * 2 + F * 3 * 2 + F * 27 * 2 + F},
            "feature": {"mean": mean.round(5).tolist(), "std": std.round(5).tolist(), "weight": weight.tolist(),
                        "names": "footL xyz, footR xyz, footL vel, footR vel, hips vel, traj pos 10/20/30 xz, traj dir 10/20/30 xz"},
            "ranges": ranges, "takes": info,
            "credit": ["The motion data used in this product was obtained from mocap.cs.cmu.edu.",
                       "100STYLE dataset (Mason, Starke, Komura), CC BY 4.0"]}
    (OUT / "mm_db.json").write_text(json.dumps(head), encoding="utf-8")
    print(f"mm_db: {F} frames ({F / FPS / 60:.1f} min with mirrors), {len(ranges)} ranges, "
          f"{len(blob) / 1e6:.2f} MB")


if __name__ == "__main__":
    build(list_only="--list" in sys.argv)
