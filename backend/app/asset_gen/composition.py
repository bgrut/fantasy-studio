"""COMPOSITION DECOMPOSITION (2026-08-25, critique-loop phase 3).

One coherent image becomes several game assets. Generating props one at a
time gives each its own lighting, palette and level of wear, and a scene
assembled from them reads as a collage; generating them TOGETHER in a single
SDXL sheet gives them one style by construction, and each instance is then
cut out and meshed individually through the existing TRELLIS path.

This is WorldClaw's regional-object stage, minus the parts a local pipeline
does not need. They segment with SAM3D because their compositions sit on
real terrain renders; OUR composition is authored by us, so it is a product
sheet on a plain seamless background and plain connected-component analysis
(scipy, already a dependency) separates the instances deterministically.
SAM2 is Apache-2.0 and is the upgrade path if compositions ever need to be
cluttered — checked 2026-08-25, and deliberately NOT a dependency today.

Instance identity comes from LAYOUT, not from a model: the prompt asks for a
2x2 grid in reading order and the components are assigned to the requested
item names row-major. That heuristic is checked by the caller (the overlay
image exists so a human or a harness can see the assignment); when SDXL
scrambles the order the set is still themed and still usable, just possibly
misnamed — and misnaming is visible, unlike a style clash.
"""

from __future__ import annotations

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SHEET_DIR = BACKEND_ROOT / "renders" / "_prop_sheets"


def _layout_depth(items: list[str], size: int = 1024):
    """Shape-hinted 2x2 depth template. Prompt-only multi-object layouts are
    exactly what SDXL is bad at — the first attempt returned a CATALOG
    COLLAGE: a dozen barrels in sub-panels, no crate, no sack. Depth
    conditioning is how this pipeline already locks biped poses, and the
    same mechanism locks a sheet into four separate objects at four known
    positions. Each blob's rough SHAPE hints its quadrant's object, which is
    what keeps four generic lumps from all becoming barrels."""
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    # a faint floor gradient, like the pose templates: depth models expect a
    # ground plane, and objects floating in void come back as stickers
    for y in range(size):
        v = int(18 + 30 * max(0, (y / size - 0.55)) / 0.45)
        d.line([(0, y), (size, y)], fill=v)
    centers = [(size // 4, size // 4), (3 * size // 4, size // 4),
               (size // 4, 3 * size // 4), (3 * size // 4, 3 * size // 4)]

    def blob(cx, cy, name):
        n = name.lower()
        w, h = int(size * 0.155), int(size * 0.17)
        if any(k in n for k in ("crate", "box", "chest")):
            d.rounded_rectangle([cx - w, cy - h, cx + w, cy + h],
                                radius=18, fill=235)
        elif any(k in n for k in ("cart", "wagon", "barrow")):
            d.rounded_rectangle([cx - int(w * 1.5), cy - int(h * 0.55),
                                 cx + int(w * 1.5), cy + int(h * 0.45)],
                                radius=22, fill=225)
            for wx in (-int(w * 0.85), int(w * 0.85)):
                d.ellipse([cx + wx - 52, cy + int(h * 0.1),
                           cx + wx + 52, cy + int(h * 0.1) + 104], fill=245)
        elif any(k in n for k in ("sack", "bag")):
            d.ellipse([cx - int(w * 0.95), cy - int(h * 0.5),
                       cx + int(w * 0.95), cy + h], fill=230)
            d.ellipse([cx - int(w * 0.35), cy - h,
                       cx + int(w * 0.35), cy - int(h * 0.3)], fill=215)
        else:                                     # barrel/keg/pot: capsule
            d.rounded_rectangle([cx - int(w * 0.8), cy - h,
                                 cx + int(w * 0.8), cy + h],
                                radius=int(w * 0.7), fill=235)

    for (cx, cy), name in zip(centers, items):
        blob(cx, cy, name)
    # VOLUME, not stickers (2026-08-25): flat-filled blobs at conditioning
    # 0.65 came back as flat painted SIGNBOARDS — the depth map said "this
    # region is a uniform plane" and SDXL obliged. A radial falloff inside
    # each blob says "this is a rounded solid", and the model shades real
    # 3/4 objects again without loosening the layout grip.
    import numpy as np
    a = np.asarray(img, dtype=np.float32)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    vol = np.zeros_like(a)
    for cx, cy in centers:
        r2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / float(size * 0.21) ** 2
        vol = np.maximum(vol, np.clip(1.0 - r2, 0.0, 1.0))
    lifted = np.where(a > 120, 150 + (a - 150) * 0.3 + vol * 85, a)
    img = Image.fromarray(np.clip(lifted, 0, 255).astype("uint8"))
    return img.filter(ImageFilter.GaussianBlur(7)).convert("RGB")


def generate_sheet(theme: str, items: list[str], out_png: str | Path,
                   seed: int = 7, steps: int = 30) -> Path:
    """One SDXL image containing every item at a known position: 2x2 grid,
    locked by a shape-hinted depth template, plain seamless background."""
    from app.asset_gen.reference import _load_t2i_controlnet_pipeline
    import torch

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    assert 2 <= len(items) <= 4, "a sheet is a 2x2 grid: 2-4 items"
    listing = ", ".join(
        f"{pos} a {name}" for pos, name in zip(
            ("top left", "top right", "bottom left", "bottom right"), items))
    # short on purpose: CLIP truncates at 77 tokens and the tail is silently
    # dropped, so every word has to earn its place near the front
    positive = (f"four separate {theme} objects: {listing}. plain light gray "
                "seamless studio background, soft even light, photorealistic, "
                "detailed")
    negative = ("collage, panels, grid lines, text, watermark, people, "
                "overlapping, cropped, frame, scenery")
    # determinism env, WITHOUT loading the base pipeline: instantiating both
    # SDXL pipelines put 15.5GB on a 16GB card and the sheet ran at thrash
    # speed — the exact failure class the ollama-eviction comment documents
    import os
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    pipe = _load_t2i_controlnet_pipeline()
    g = torch.Generator(device=pipe.device).manual_seed(seed)
    depth = _layout_depth(items)
    img = pipe(prompt=positive, negative_prompt=negative, image=depth,
               width=1024, height=1024, num_inference_steps=steps,
               guidance_scale=7.5, controlnet_conditioning_scale=0.55,
               generator=g).images[0]
    img.save(out_png)
    depth.save(Path(out_png).with_name("layout_depth.png"))
    return out_png


def segment_sheet(sheet_png: str | Path, out_dir: str | Path,
                  n_expected: int, overlay_png: str | Path | None = None
                  ) -> list[dict]:
    """Plain-background sheet -> per-instance crops, row-major order.

    Returns [{"crop": path, "bbox": (x0,y0,x1,y1), "area": px}] sorted into
    reading order. Writes an overlay image with numbered boxes so the
    assignment can be CHECKED BY EYE — the ordering is a heuristic, and a
    heuristic nobody can inspect is a bug that has not happened yet.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy import ndimage

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(sheet_png).convert("RGB")
    a = np.asarray(img, dtype=np.float32)
    H, W = a.shape[:2]

    # the background is whatever the BORDER is: median of a 12px ring. A
    # fixed "light gray" assumption would break the day SDXL warms the tone.
    ring = np.concatenate([
        a[:12].reshape(-1, 3), a[-12:].reshape(-1, 3),
        a[:, :12].reshape(-1, 3), a[:, -12:].reshape(-1, 3)])
    bg = np.median(ring, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    # threshold: above the border's own noise floor, with a hard minimum so a
    # soft vignette does not read as one giant object
    thr = max(30.0, float(np.percentile(np.sqrt(((ring - bg) ** 2).sum(axis=1)), 99)) * 1.6)
    mask = dist > thr
    # erode first to cut soft-shadow bridges between neighbours, then close
    # and fill so each object is one solid blob
    mask = ndimage.binary_erosion(mask, iterations=2)
    mask = ndimage.binary_closing(mask, iterations=6)
    mask = ndimage.binary_fill_holes(mask)
    lab, n = ndimage.label(mask)
    comps = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        area = h * w
        if area < 0.004 * H * W or area > 0.45 * H * W:
            continue
        comps.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop, area))
    # keep the n_expected largest, then sort into reading order: row bucket
    # first (top/bottom half by centre), then x
    comps = sorted(comps, key=lambda c: -c[4])[:n_expected]
    comps.sort(key=lambda c: (round(((c[1] + c[3]) / 2) / H), (c[0] + c[2]) / 2))

    results = []
    for i, (x0, y0, x1, y1, area) in enumerate(comps):
        pad = int(0.06 * max(x1 - x0, y1 - y0))
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1, cy1 = min(W, x1 + pad), min(H, y1 + pad)
        crop = img.crop((cx0, cy0, cx1, cy1))
        # square white canvas: the mesh path's own background removal re-keys
        # it, and TRELLIS wants the subject centred with margin
        side = int(max(crop.size) * 1.25)
        canvas = Image.new("RGB", (side, side), (245, 245, 245))
        canvas.paste(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
        # absolute: downstream passes run through the Blender bridge,
        # whose cwd is not ours — relative paths fail there silently
        cp = (out_dir / f"inst_{i}.png").resolve()
        canvas.resize((1024, 1024), Image.LANCZOS).save(cp)
        results.append({"crop": cp, "bbox": (cx0, cy0, cx1, cy1), "area": area})

    if overlay_png is not None:
        ov = img.copy()
        d = ImageDraw.Draw(ov)
        for i, r in enumerate(results):
            d.rectangle(r["bbox"], outline=(0, 255, 120), width=4)
            d.text((r["bbox"][0] + 6, r["bbox"][1] + 6), str(i),
                   fill=(0, 255, 120))
        ov.save(overlay_png)
    return results


def build_prop_set(theme: str, items: list[str], seed: int = 7,
                   target_tris: int = 16000, verbose: bool = True) -> list[dict]:
    """Sheet -> segments -> one GLB per item, registered in the library.

    Returns [{"kind", "glb", "crop"}]. Raises if the sheet segments into
    fewer instances than items — a wrong count means the assignment would be
    fiction, and a themed set with missing members is better regenerated
    with a new seed than shipped misnamed.
    """
    import hashlib

    from app.asset_gen.mesh import generate_mesh
    from app.asset_gen.reference import unload_reference_pipeline
    from app.game_export.bake import optimize_asset
    from app.game_export.generate import _register
    from app.game_export import library

    key = hashlib.md5((theme + ":" + ",".join(items)).encode()).hexdigest()[:10]
    work = SHEET_DIR / key
    work.mkdir(parents=True, exist_ok=True)
    sheet = work / "sheet.png"
    if not sheet.exists():
        if verbose:
            print(f"[propset] sheet: {theme} -> {sheet}")
        generate_sheet(theme, items, sheet, seed=seed)
        unload_reference_pipeline()          # SDXL out before TRELLIS loads
    segs = segment_sheet(sheet, work, n_expected=len(items),
                         overlay_png=work / "overlay.png")
    if len(segs) < len(items):
        raise RuntimeError(
            f"sheet segmented into {len(segs)} instances, need {len(items)} "
            f"— regenerate with another seed (overlay: {work / 'overlay.png'})")

    # the mesh engine needs the whole card: evict the chat LLM (same move as
    # ensure_asset — it thrashes TRELLIS from 5GB of resident weights)
    try:
        import requests as _rq
        for _m in _rq.get("http://localhost:11434/api/ps",
                          timeout=3).json().get("models", []):
            _rq.post("http://localhost:11434/api/generate",
                     json={"model": _m["name"], "keep_alive": 0}, timeout=5)
    except Exception:
        pass

    out = []
    for name, seg in zip(items, segs):
        kind = name.lower().strip().replace(" ", "_")
        final = BACKEND_ROOT / "assets" / "library" / f"{kind}.glb"
        raw = work / f"{kind}_raw.glb"
        if verbose:
            print(f"[propset] mesh: {kind} <- {seg['crop'].name}")
        try:
            generate_mesh(seg["crop"], output_path=raw, tier="standard")
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"[propset] {kind}: standard tier failed ({e}); triposr")
            generate_mesh(seg["crop"], output_path=raw, engine="triposr")
        optimize_asset(raw, final, target_tris=target_tris,
                       ref_png=seg["crop"], despeckle=False)
        rel = str(final.relative_to(BACKEND_ROOT)).replace("\\", "/")
        if library.resolve(kind):
            if verbose:
                print(f"[propset] '{kind}' already in library — leaving "
                      "the existing entry, set copy is at " + rel)
        else:
            _register(kind, rel)
            # the placement grammar reduces "place a wooden crate here" to its
            # LAST word, so the short name has to resolve too — but only when
            # it is free: a set must never shadow an existing library asset
            short = kind.rsplit("_", 1)[-1]
            if short != kind and not library.resolve(short):
                _register(short, rel)
        out.append({"kind": kind, "glb": str(final), "crop": str(seg["crop"])})
    (work / "set.json").write_text(json.dumps(
        {"theme": theme, "items": items, "assets": out}, indent=1),
        encoding="utf-8")
    return out
