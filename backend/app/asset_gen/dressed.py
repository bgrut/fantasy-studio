"""Is the person in a reference image dressed? (2026-10-03)

SDXL ignored "a man wearing a casual t-shirt and jeans, fully clothed" and a
negative prompt against undress often enough that the library shipped five
people in briefs or bare-chested (man, thug, waterbender, explorer, courier)
and a ranger in swimwear. A reference is now looked at before it becomes a
mesh: the figure is found against the studio backdrop, the centre of its chest
and belly is sampled, and if most of it is skin the person is undressed and the
reference is made again with another seed.

Skin is tested in YCrCb, the usual colour space for it: Cr 133-180, Cb 77-135,
with enough brightness to exclude shadow. Only the central band of the torso is
sampled, so outstretched arms and hands never count.
"""
from __future__ import annotations

from pathlib import Path


def torso_skin_fraction(png: str | Path) -> float | None:
    """Share of skin-toned pixels in the centre of the chest and belly, or None
    when no figure could be found."""
    try:
        import numpy as np
        from PIL import Image
        im = np.asarray(Image.open(png).convert("RGB").resize((256, 256)), dtype=np.float32)
        h, w, _ = im.shape
        # the backdrop: the median of the border, and anything far from it is figure
        border = np.concatenate([im[0], im[-1], im[:, 0], im[:, -1]])
        bg = np.median(border, axis=0)
        fg = np.abs(im - bg).sum(axis=2) > 60
        ys, xs = np.where(fg)
        if len(ys) < 400:
            return None
        y0, y1 = np.percentile(ys, 1), np.percentile(ys, 99)
        H = y1 - y0
        # the torso's centre line: the figure's median column in the chest band
        band = fg[int(y0 + 0.22 * H):int(y0 + 0.45 * H)]
        cols = np.where(band.any(axis=0))[0]
        if len(cols) == 0:
            return None
        cx = int(np.median(np.where(band)[1]))
        half = max(3, int(0.06 * H))            # a chest is about an eighth of the height across
        reg = im[int(y0 + 0.22 * H):int(y0 + 0.45 * H), max(0, cx - half):min(w, cx + half)]
        regfg = fg[int(y0 + 0.22 * H):int(y0 + 0.45 * H), max(0, cx - half):min(w, cx + half)]
        R, G, B = reg[..., 0], reg[..., 1], reg[..., 2]
        Y = 0.299 * R + 0.587 * G + 0.114 * B
        Cr = (R - Y) * 0.713 + 128
        Cb = (B - Y) * 0.564 + 128
        skin = (Cr > 133) & (Cr < 180) & (Cb > 77) & (Cb < 135) & (Y > 60)
        n = regfg.sum()
        if n < 30:
            return None
        return float((skin & regfg).sum() / n)
    except Exception:
        return None


def undressed_belief(png: str | Path) -> float | None:
    """CLIP's belief that the person is undressed (bare chest, underwear,
    swimwear) rather than clothed. Colour alone cannot tell a bare chest from
    a khaki shirt (both read as skin tone), so the reference judge's own model
    (openai/clip-vit-base-patch32, MIT) is asked instead."""
    try:
        import torch
        from PIL import Image
        from . import reference as _r
        _r._blotchiness_model_ready()
        model, proc = _r._CLIP_JUDGE
        dev = next(model.parameters()).device
        pos = ["a shirtless person", "a person with a bare chest", "a person in underwear",
               "a person in swim briefs", "a nude person"]
        neg = ["a person wearing a shirt", "a person wearing a jacket", "a person in a uniform",
               "a person wearing a long-sleeved top", "a person in armor", "a person in a dress",
               "a person in a full-body suit"]
        img = Image.open(png).convert("RGB")
        with torch.no_grad():
            inputs = proc(text=pos + neg, images=img, return_tensors="pt", padding=True).to(dev)
            probs = torch.softmax(model(**inputs).logits_per_image[0].float(), dim=0)
        return float(probs[:len(pos)].sum())
    except Exception:
        return None


def is_undressed(png: str | Path, threshold: float = 0.25) -> bool:
    # measured 2026-10-03: clothed 0.009-0.056 (khaki shirt, cycling kit,
    # ranger), bare chests 0.48-0.79; 0.5 let a shirtless 0.48 through
    b = undressed_belief(png)
    return b is not None and b > threshold
