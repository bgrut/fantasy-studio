"""Depth-locked SDXL ControlNet img2img refiner — runs in venv_triposg.

The main venv pins diffusers 0.20.2 (no SDXL ControlNet Img2Img class), so plain
img2img there gives a clay-like look and lets features drift. venv_triposg has
diffusers 0.38 with StableDiffusionXLControlNetImg2ImgPipeline, so we run the
refiner here as an isolated subprocess (TripoSG pattern) — the main venv's t2i
reference + plain refiner pipelines stay untouched.

Depth from each input render (MiDaS) constrains generation to the geometry, so
fur + facial features stay aligned + sharp instead of being repainted freely.

Batched: one invocation refines ALL views (loads the ~10 GB pipeline once).

Usage:
    python scripts/refine_subprocess.py --manifest jobs.json
    manifest = {"prompt","negative","strength","steps","guidance","seed",
                "controlnet_scale","jobs":[{"image","output"}, ...]}
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    with open(args.manifest, "r", encoding="utf-8") as f:
        M = json.load(f)
    jobs = M["jobs"]
    prompt = M.get("prompt", "")
    negative = M.get("negative", "")
    strength = float(M.get("strength", 0.72))
    steps = int(M.get("steps", 28))
    guidance = float(M.get("guidance", 7.0))
    seed = int(M.get("seed", 42))
    cn_scale = float(M.get("controlnet_scale", 0.45))

    from PIL import Image
    import torch
    from diffusers import (
        StableDiffusionXLControlNetImg2ImgPipeline, ControlNetModel, AutoencoderKL)
    from controlnet_aux import MidasDetector

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    midas = MidasDetector.from_pretrained("lllyasviel/Annotators")
    try:
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype)
    except Exception:
        vae = None
    controlnet = ControlNetModel.from_pretrained(
        "diffusers/controlnet-depth-sdxl-1.0", torch_dtype=dtype)
    pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        controlnet=controlnet, vae=vae, torch_dtype=dtype,
        variant="fp16" if device == "cuda" else None, use_safetensors=True)
    pipe = pipe.to(device)
    try:
        pipe.vae.enable_tiling()
    except Exception:
        pass

    for job in jobs:
        src = Image.open(job["image"]).convert("RGB")
        w, h = src.size
        w8, h8 = (w // 8) * 8, (h // 8) * 8
        if (w, h) != (w8, h8):
            src = src.resize((w8, h8), Image.LANCZOS)
        depth = midas(src).resize((w8, h8), Image.LANCZOS).convert("RGB")
        gen = torch.Generator(device=device).manual_seed(seed)
        out_img = pipe(
            prompt=prompt, negative_prompt=negative,
            image=src, control_image=depth,
            strength=strength, guidance_scale=guidance,
            num_inference_steps=steps, controlnet_conditioning_scale=cn_scale,
            generator=gen,
        ).images[0]
        if out_img.size != (w, h):
            out_img = out_img.resize((w, h), Image.LANCZOS)
        out_img.save(job["output"])
        print(f"REFINE_OK {job['output']}", flush=True)
    print("BATCH_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
