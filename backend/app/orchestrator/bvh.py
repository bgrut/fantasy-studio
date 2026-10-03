"""A BVH reader with forward kinematics, in numpy (2026-10-03).

The motion-matching database is built from source motion directly, outside
Blender: every joint's world rotation and position per frame, in metres, Y up.
Rotation transfer then needs nothing else from the source (BVH joints rest at
the identity, so a joint's world rotation IS its rotation away from rest).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Bvh:
    names: list[str] = field(default_factory=list)
    parents: list[int] = field(default_factory=list)
    offsets: np.ndarray | None = None          # (J, 3) rest offsets from the parent, file units
    ends: dict = field(default_factory=dict)   # joint index -> End Site offset
    channels: list[list[str]] = field(default_factory=list)
    frame_time: float = 1 / 120
    motion: np.ndarray | None = None           # (F, C) raw channel values

    def index(self, name: str) -> int:
        return self.names.index(name)


def read(path: str | Path) -> Bvh:
    b = Bvh()
    toks = Path(path).read_text(encoding="utf-8", errors="ignore").split()
    i = 0
    stack: list[int] = []
    offs: list[list[float]] = []
    last = -1
    while toks[i] != "MOTION":
        t = toks[i]
        if t in ("ROOT", "JOINT"):
            b.names.append(toks[i + 1]); b.parents.append(stack[-1] if stack else -1)
            b.channels.append([]); offs.append([0.0, 0.0, 0.0])
            last = len(b.names) - 1; i += 2; continue
        if t == "End":                          # End Site { OFFSET x y z }
            j = i
            while toks[j] != "OFFSET":
                j += 1
            b.ends[stack[-1]] = [float(v) for v in toks[j + 1:j + 4]]
            while toks[j] != "}":
                j += 1
            i = j + 1; continue
        if t == "{":
            stack.append(last); i += 1; continue
        if t == "}":
            stack.pop(); i += 1; continue
        if t == "OFFSET":
            offs[last] = [float(v) for v in toks[i + 1:i + 4]]; i += 4; continue
        if t == "CHANNELS":
            n = int(toks[i + 1]); b.channels[last] = toks[i + 2:i + 2 + n]; i += 2 + n; continue
        i += 1
    i += 1
    nf = int(toks[i + 1]); i += 2                  # Frames: N
    b.frame_time = float(toks[i + 2]); i += 3      # Frame Time: x
    nc = sum(len(c) for c in b.channels)
    vals = np.array(toks[i:i + nf * nc], dtype=np.float64)
    b.motion = vals.reshape(nf, nc)
    b.offsets = np.array(offs, dtype=np.float64)
    return b


def _axis_rot(axis: str, ang: np.ndarray) -> np.ndarray:
    c, s = np.cos(ang), np.sin(ang)
    o, z = np.ones_like(ang), np.zeros_like(ang)
    if axis == "X":
        m = [[o, z, z], [z, c, -s], [z, s, c]]
    elif axis == "Y":
        m = [[c, z, s], [z, o, z], [-s, z, c]]
    else:
        m = [[c, -s, z], [s, c, z], [z, z, o]]
    return np.stack([np.stack(r, -1) for r in m], -2)      # (F, 3, 3)


def fk(b: Bvh, scale: float = 1.0):
    """World rotations (F, J, 3, 3) and positions (F, J, 3), positions scaled."""
    F, J = b.motion.shape[0], len(b.names)
    R = np.zeros((F, J, 3, 3)); P = np.zeros((F, J, 3))
    col = 0
    for j in range(J):
        ch = b.channels[j]
        local = np.broadcast_to(np.eye(3), (F, 3, 3)).copy()
        pos = np.broadcast_to(b.offsets[j], (F, 3)).copy()
        for k, c in enumerate(ch):
            v = b.motion[:, col + k]
            if c.endswith("position"):
                pos[:, "XYZ".index(c[0])] = v if b.parents[j] < 0 else pos[:, "XYZ".index(c[0])] + v
            else:
                local = local @ _axis_rot(c[0], np.radians(v))
        col += len(ch)
        p = b.parents[j]
        if p < 0:
            R[:, j] = local; P[:, j] = pos * scale
        else:
            R[:, j] = R[:, p] @ local
            P[:, j] = P[:, p] + np.einsum("fij,fj->fi", R[:, p], pos * scale)
    return R, P


def leg_length(b: Bvh, hip: str, knee: str, ankle: str) -> float:
    """Thigh plus shin, in file units (the rest offsets of knee and ankle)."""
    return float(np.linalg.norm(b.offsets[b.index(knee)]) + np.linalg.norm(b.offsets[b.index(ankle)]))
