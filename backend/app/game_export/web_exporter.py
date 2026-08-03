"""three.js web-game emitter: GameSpec + asset files → self-contained dist/.

Deterministic assembly only — templates are hand-written under runtime/, the
spec is injected as JSON, asset files are copied in and paths rewritten to
dist-relative. No network at build OR run time (vendored three.js + Rapier).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .spec import GameSpec

BACKEND_ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(__file__).resolve().parent / "runtime"


def _splat_points(path: Path, max_pts: int = 120_000):
    """Sample gaussian centers from a .ply (3DGS) or .splat file as an [N,3]
    float array. Returns None for formats we can't parse (.ksplat)."""
    import numpy as np
    ext = path.suffix.lower()
    if ext == ".splat":
        # antimatter15 format: 32-byte stride, first 12 bytes = float32 xyz
        raw = np.fromfile(path, dtype=np.uint8).reshape(-1, 32)
        pts = raw[:, :12].copy().view(np.float32).reshape(-1, 3)
    elif ext == ".ply":
        with open(path, "rb") as f:
            header = b""
            while not header.endswith(b"end_header\n"):
                line = f.readline()
                if not line:
                    return None
                header += line
            txt = header.decode("ascii", errors="ignore")
            if "binary_little_endian" not in txt:
                return None
            import re as _re
            m = _re.search(r"element vertex (\d+)", txt)
            props = [ln.split()[-1] for ln in txt.splitlines()
                     if ln.startswith("property float")]
            if not m or "x" not in props:
                return None
            n = int(m.group(1))
            data = np.fromfile(f, dtype=np.float32, count=n * len(props))
        data = data.reshape(-1, len(props))
        ix = [props.index(a) for a in ("x", "y", "z")]
        pts = data[:, ix]
    else:
        return None
    if len(pts) > max_pts:
        pts = pts[:: max(1, len(pts) // max_pts)]
    return pts


def _splat_fit(path: Path) -> dict | None:
    """Rotation/scale/position that turns a raw splat into a walkable
    diorama: source-aware up-axis fix (sidecar <file>.meta.json written by
    imagine/train), robust 2-98 percentile bounds (ignores floater outliers),
    object-scale splats blown up to ~40m, bottom seated at ground level."""
    import json
    import math

    import numpy as np
    pts = _splat_points(path)
    if pts is None or len(pts) < 100:
        return None

    # up-axis is solved from GEOMETRY, not provenance (the provenance guess
    # put a shrine upside-down overhead): among the 4 X-axis orientations,
    # the correct one has its gaussian mass sitting LOW — floors, ground
    # planes and structure bases are the densest regions of any scene. Same
    # insight as the vehicle wheels-down solver.
    s2 = math.sqrt(0.5)
    cands = [
        (np.stack([pts[:, 0], pts[:, 1], pts[:, 2]], axis=1),
         [0.0, 0.0, 0.0, 1.0]),                       # identity
        (np.stack([pts[:, 0], pts[:, 2], -pts[:, 1]], axis=1),
         [-s2, 0.0, 0.0, s2]),                        # rotX -90 (z-up src)
        (np.stack([pts[:, 0], -pts[:, 2], pts[:, 1]], axis=1),
         [s2, 0.0, 0.0, s2]),                         # rotX +90
        (np.stack([pts[:, 0], -pts[:, 1], -pts[:, 2]], axis=1),
         [1.0, 0.0, 0.0, 0.0]),                       # rotX 180 (y-down src)
    ]
    best = None
    for cpts, quat in cands:
        p2 = np.percentile(cpts[:, 1], 2)
        p98 = np.percentile(cpts[:, 1], 98)
        if p98 - p2 <= 1e-6:
            continue
        cz_norm = float((cpts[:, 1].mean() - p2) / (p98 - p2))
        if best is None or cz_norm < best[0]:
            best = (cz_norm, cpts, quat)
    if best is None:
        return None
    _, pts, rot = best

    lo = np.percentile(pts, 2, axis=0)
    hi = np.percentile(pts, 98, axis=0)
    ext = float(max(hi - lo))
    if ext <= 1e-6:
        return None
    # object-scale gaussians (TRELLIS ~1 unit) become a large set piece
    # (~55m). Verified limit: stretching a ~100k-gaussian object to full
    # world size (110m+) turns to blur up close — splats can't add detail
    # under magnification. True world-scale splats come from the Tier 2
    # video-training route. Capture-scale scenes (>15m) are left 1:1.
    scale = round(min(55.0 / ext, 90.0), 3) if ext < 15.0 else 1.0
    cx = float((lo[0] + hi[0]) / 2) * scale
    cz = float((lo[2] + hi[2]) / 2) * scale
    py = -float(lo[1]) * scale - 0.4    # seat the 2%-bottom just below ground
    return {"rotation": rot, "scale": scale,
            "position": [round(-cx, 3), round(py, 3), round(-cz, 3)]}


def export_web_game(spec: GameSpec, out_dir: str | Path, verbose: bool = True) -> Path:
    """Emit the playable game into `out_dir` (created/overwritten). Returns the
    dist path. Raises on missing player asset — a game without a player is a
    build error, not a warning."""
    out = Path(out_dir)
    dist = out / "dist"
    assets = dist / "assets"
    if assets.exists():          # purge stale assets from prior exports
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)

    # ── PBR texture pack (Phase 77): SDXL-generated seamless surfaces ───────
    tex_src = RUNTIME.parent.parent.parent / "assets" / "textures"
    if tex_src.is_dir():
        tex_dst = dist / "textures"
        if tex_dst.exists():
            shutil.rmtree(tex_dst)
        shutil.copytree(tex_src, tex_dst)

    # ── interior furniture props (Phase 95): rooms load props/<name>.glb ────
    lvl_d = (spec.world.level or {}) if getattr(spec.world, "level", None) else {}
    interior = lvl_d.get("interior")
    needed = set()
    if interior:
        needed |= {f[0] for f in interior.get("furniture", [])}
    if lvl_d.get("pois"):
        # POI clusters (moon plan 2.1) draw from a fixed prop set
        needed |= {"crate", "log", "stump", "barrel"}
    if lvl_d.get("enterable"):
        needed |= {f[0] for f in lvl_d["enterable"]["plan"].get("furniture", [])}
    if needed:
        props_src = RUNTIME.parent.parent.parent / "assets" / "props"
        props_dst = dist / "props"
        props_dst.mkdir(parents=True, exist_ok=True)
        for name in needed:
            src = props_src / f"{name}.glb"
            if src.exists():
                shutil.copy2(src, props_dst / src.name)

    # ── PEDESTRIANS (r4, 2026-07-30): city levels bundle the lightweight
    # walker (7.8MB bake of man_anim: decimated + 512px JPEG textures) so
    # the runtime can clone ambient sidewalk walkers. Baked once by
    # scripts/_bake_walker.py; silently skipped when absent.
    try:
        _lv = getattr(spec.world, "level", None) or {}
        if isinstance(_lv, dict) and _lv.get("osm"):
            _wsrc = BACKEND_ROOT / "assets" / "library" / "walker.glb"
            if _wsrc.exists():
                shutil.copy2(_wsrc, dist / "assets" / "walker.glb")
    except Exception:  # noqa: BLE001
        pass

    # ── OWNERSHIP MANIFEST (best-in-class plan, 2026-07-28): every export
    # carries receipts — the full license chain proving the game is the
    # user's to sell. This is a product feature: no competitor can print it.
    (dist / "LICENSES.md").write_text(
        f"""# {spec.title or 'Your Game'} — License Manifest

This game was generated with Fantasy Studio. **Everything in this folder is
yours** — the runtime is open source and every bundled asset is either
generated locally on your machine or dedicated to the public domain.

| Component | License |
|---|---|
| Game code & runtime (three.js) | MIT |
| Physics (Rapier) | Apache-2.0 |
| Gaussian-splat renderer (when present) | MIT |
| N8AO ambient occlusion | CC0 |
| HDRI environment (Poly Haven, when present) | CC0 — public domain |
| PBR textures | Generated locally (Stable Diffusion XL, user output) |
| Characters & 3D assets | Generated locally (SDXL + Microsoft TRELLIS, MIT) |
| Character motion | CMU Motion Capture Database (free for commercial products) |
| City street layouts (when present) | OpenStreetMap contributors, ODbL (data attribution: openstreetmap.org/copyright) |

No cloud services were used to build this game. No third party holds rights
over its content. You may sell it, publish it, or modify it freely.
""", encoding="utf-8")

    # ── HDRI IBL (Arc B slice, 2026-07-28): bundle the CC0 Poly Haven HDRI
    # matching the sky mood — real captured light for every PBR material.
    # Flat/stylized looks skip it (their pipeline strips photo response).
    if getattr(spec.world, "hdri", None) is None and spec.style in ("default", "horror"):
        _mood = {"day": "day", "sunset": "sunset", "dusk": "sunset",
                 "night": "night", "overcast": "overcast"}.get(spec.world.sky)
        if _mood:
            _h = BACKEND_ROOT / "assets" / "hdri" / f"{_mood}.hdr"
            if _h.exists():
                (dist / "hdri").mkdir(parents=True, exist_ok=True)
                shutil.copy2(_h, dist / "hdri" / _h.name)
                spec.world.hdri = f"hdri/{_h.name}"

    # ── Gaussian-splat world (Phase 136, additive): bundle the file the
    # spec points at; the runtime lazy-loads the renderer only when present
    if getattr(spec.world, "splat", None):
        sp_src = Path(spec.world.splat)
        if not sp_src.is_absolute():
            sp_src = BACKEND_ROOT / spec.world.splat
        if sp_src.exists():
            (dist / "splats").mkdir(parents=True, exist_ok=True)
            shutil.copy2(sp_src, dist / "splats" / sp_src.name)
            # PHASE 137.2: auto-fit — raw splats land tiny/sideways (TRELLIS
            # is object-scale + z-up). Compute rotation/scale/lift from the
            # actual point cloud so every splat becomes a walkable diorama.
            try:
                spec.world.splat_fit = _splat_fit(sp_src)
            except Exception as e:  # noqa: BLE001 — fit is best-effort
                if verbose:
                    print(f"[export] splat fit skipped: {e}")
            spec.world.splat = f"splats/{sp_src.name}"
        else:
            spec.world.splat = None            # missing file: normal world

    # ── vendored runtime libs ────────────────────────────────────────────────
    vend_src = RUNTIME / "vendor"
    vend_dst = dist / "vendor"
    if vend_dst.exists():
        shutil.rmtree(vend_dst)
    shutil.copytree(vend_src, vend_dst)

    # ── copy assets, rewrite spec paths to dist-relative ────────────────────
    rt = spec.runtime_json()

    def bring(src_path: str, tag: str) -> str:
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"{tag} asset missing: {src}")
        dst = assets / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        return f"./assets/{src.name}"

    if not spec.player.asset:
        raise ValueError("GameSpec.player.asset is required for export")
    rt["player"]["asset"] = bring(spec.player.asset, "player")
    for i, sct in enumerate(spec.world.scatter):
        rt["world"]["scatter"][i]["asset"] = bring(sct.asset, f"scatter[{i}]")
    for i, ent in enumerate(spec.entities):
        rt["entities"][i]["asset"] = bring(ent.asset, f"entity[{i}]")
    for i, ob in enumerate(spec.objectives):
        if getattr(ob, "asset", None):       # collect steps with a generated mesh
            rt["objectives"][i]["asset"] = bring(ob.asset, f"objective[{i}]")
    for i, it in enumerate(spec.world.placed_items):
        if it.asset:                         # procedural props ship no file
            rt["world"]["placed_items"][i]["asset"] = bring(it.asset, f"placed[{i}]")

    # ── render templates ─────────────────────────────────────────────────────
    html = (RUNTIME / "index.html.tpl").read_text(encoding="utf-8")
    (dist / "index.html").write_text(
        html.replace("__TITLE__", spec.title), encoding="utf-8")

    js = (RUNTIME / "main.js.tpl").read_text(encoding="utf-8")
    (dist / "game.js").write_text(
        js.replace("__GAME_SPEC__", json.dumps(rt)), encoding="utf-8")
    # machine-readable copy of the injected spec — read by verify_game + debugging
    (dist / "spec.json").write_text(json.dumps(rt, indent=2), encoding="utf-8")

    if verbose:
        n = sum(1 for _ in dist.rglob("*") if _.is_file())
        mb = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file()) / 1e6
        print(f"[game] exported '{spec.title}' -> {dist} ({n} files, {mb:.1f} MB)")
    return dist
