"""Does the model look like what it says? A local judge for generated assets.

    python backend/tools/assetjudge.py            # scores every shaded render in shotgate/renders
    python backend/tools/assetjudge.py corvette   # one kind

Pixel statistics could not tell a mangled ferrari from a good corvette:
the ferrari's torn regions are dark in its own texture, the white cars'
shading holes counted as damage. The question is semantic, so a vision
model answers it. CLIP (openai/clip-vit-base-patch32, MIT, fetched once
into the same Hugging Face cache SDXL and TRELLIS live in, then local)
scores each shaded render from assetview.mjs against "a photo of a
{kind}" and "a broken 3D model, torn fragments, debris". The share of
belief on the kind is `looks_like`, written into library_render.json,
which assetmeta.py folds into each asset's verdict.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RENDERS = ROOT / "backend" / "tools" / "shotgate" / "renders"
RENDER_JSON = ROOT / "backend" / "assets" / "library_render.json"
MODEL = "openai/clip-vit-base-patch32"


def main() -> int:
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    only = set(sys.argv[1:])
    data = json.loads(RENDER_JSON.read_text(encoding="utf-8")) if RENDER_JSON.exists() else {}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained(MODEL).to(dev).eval()
    proc = CLIPProcessor.from_pretrained(MODEL)
    rows = []
    for file, rec in data.items():
        kind = rec.get("kind") or file.replace(".glb", "").replace("_", " ")
        if only and kind not in only:
            continue
        png = ROOT / rec.get("shaded_png", "")
        if not png.exists():
            continue
        noun = kind.replace("_", " ")
        pos = [f"a photo of a {noun}", f"a clean 3D render of a {noun}", f"a {noun}"]
        neg = ["a broken 3D model with torn fragments and holes", "a pile of shattered debris",
               "a corrupted mesh, glitch art", "an unrecognizable abstract shape"]
        with torch.no_grad():
            inputs = proc(text=pos + neg, images=Image.open(png).convert("RGB"), return_tensors="pt", padding=True).to(dev)
            out = model(**inputs)
            logits = out.logits_per_image[0].float().cpu()
            probs = torch.softmax(logits, dim=0)
            p_pos = float(probs[: len(pos)].sum())
            best = pos[int(torch.argmax(logits[: len(pos)]))]
        rec["looks_like"] = round(p_pos, 3)
        rec["looks_like_best"] = best
        rows.append((kind, p_pos, best))
        print(f"  {kind:22} looks like it: {p_pos:5.2f}   ({best})", flush=True)
    RENDER_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")
    rows.sort(key=lambda r: r[1])
    print(f"\n{len(rows)} judged; lowest: " + ", ".join(f"{k} {p:.2f}" for k, p, _ in rows[:8]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
