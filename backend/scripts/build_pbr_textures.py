"""Hyper-real texture pack (Phase 77): SDXL -> seamless tileable PBR textures.

The 'cartooney' verdict is flat albedo everywhere. This generates REAL
photographic surface textures once on the GPU (~40 s each, cached forever):
grass, soil, forest floor, rock, castle stone, brick, bark, roof shingles,
snow, sand, asphalt. Each is made seamless (wrap-shift + feathered cross
blend) and gets a derived normal map (Sobel on luminance).

Output: assets/textures/<name>.jpg + <name>_n.jpg (1024px).
Runtime (photoreal style) maps material classes to these instead of the
procedural canvases. Fully local, MIT-safe — our own SDXL outputs.

Run: venv/Scripts/python.exe scripts/build_pbr_textures.py
"""
import sys
from pathlib import Path

import numpy as np

B = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(B))
OUT = B / "assets" / "textures"
OUT.mkdir(parents=True, exist_ok=True)

PACK = {
    "grass":    "top-down photograph of dense green lawn grass texture, "
                "overhead flat view, even daylight, high detail",
    "soil":     "top-down photograph of packed brown dirt ground with small "
                "pebbles, overhead flat view, even light",
    "forest":   "top-down photograph of forest floor, fallen leaves twigs "
                "moss, overhead flat view, even light",
    "rock":     "photograph of rough gray rock surface, cracks and grain, "
                "flat frontal view, even light",
    "stone":    "photograph of medieval castle stone block wall, weathered "
                "masonry courses, flat frontal view, even light",
    "brick":    "photograph of aged red brick wall with mortar joints, flat "
                "frontal view, even light",
    "bark":     "photograph of rough brown tree bark texture, vertical "
                "ridges, flat frontal view, even light",
    "roof":     "photograph of overlapping dark roof shingle rows, flat "
                "frontal view, even light",
    "snow":     "top-down photograph of fresh snow surface with subtle "
                "sparkle and drift ripples, overhead view, soft light",
    "sand":     "top-down photograph of desert sand with fine wind ripples, "
                "overhead flat view, warm even light",
    "asphalt":  "top-down photograph of worn asphalt road surface with fine "
                "cracks, overhead flat view, even light",
}
NEG = ("shadow of photographer, object, person, animal, watermark, text, "
       "logo, border, vignette, fisheye, tilt")


def make_seamless(img: np.ndarray, feather: int = 160) -> np.ndarray:
    """Wrap-shift by half then cross-blend the (now centered) seams."""
    h, w = img.shape[:2]
    sh = np.roll(np.roll(img, h // 2, axis=0), w // 2, axis=1).astype(np.float32)
    orig = img.astype(np.float32)
    # blend weight peaks at the shifted seams (image center lines)
    yy = np.abs(np.arange(h) - h / 2)[:, None]
    xx = np.abs(np.arange(w) - w / 2)[None, :]
    wy = np.clip(1 - yy / feather, 0, 1)
    wx = np.clip(1 - xx / feather, 0, 1)
    wgt = np.maximum(wy, wx)[..., None]            # near seam -> use original
    return np.clip(sh * (1 - wgt) + orig * wgt, 0, 255).astype(np.uint8)


def normal_map(img: np.ndarray, strength: float = 2.2) -> np.ndarray:
    lum = img.mean(axis=2).astype(np.float32) / 255.0
    gx = np.roll(lum, -1, axis=1) - np.roll(lum, 1, axis=1)
    gy = np.roll(lum, -1, axis=0) - np.roll(lum, 1, axis=0)
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(lum)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], axis=-1)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def main() -> None:
    import torch
    from PIL import Image
    from app.asset_gen.reference import _load_t2i_pipeline  # cached SDXL loader

    pipe = _load_t2i_pipeline()
    for name, prompt in PACK.items():
        jpg = OUT / f"{name}.jpg"
        if jpg.exists():
            print(f"[skip] {name} (exists)", flush=True)
            continue
        g = torch.Generator("cuda").manual_seed(hash(name) % (2**31))
        im = pipe(prompt=prompt, negative_prompt=NEG, width=1024, height=1024,
                  num_inference_steps=30, guidance_scale=6.5,
                  generator=g).images[0]
        arr = np.asarray(im.convert("RGB"))
        arr = make_seamless(arr)
        Image.fromarray(arr).save(jpg, quality=88)
        Image.fromarray(normal_map(arr)).save(OUT / f"{name}_n.jpg", quality=88)
        print(f"[made] {name}", flush=True)
    print("PBR PACK DONE", flush=True)


if __name__ == "__main__":
    main()
