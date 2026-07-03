"""Generate clean 4-legged dog candidates with PLAIN SDXL (no pose-lock), to
become the source for a new quadruped depth template. Plain SDXL has no corrupt
control signal, so it reliably draws 4-legged dogs. The user picks the cleanest
standing LEFT-FACING side profile; we then derive its depth map into the template.

Outputs: renders/_candidates/cand_{seed}.png
"""
import sys
from pathlib import Path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.asset_gen import reference as ref  # noqa: E402

SLOTS = {"subject": {"library_query": "dog", "color_name": "brown",
                     "base_pattern": "quadruped"},
         "scene": {"mood": "studio"}}
SEEDS = [42, 101, 202, 303, 404, 505]


def main():
    import torch
    out = BACKEND_ROOT / "renders" / "_candidates"
    out.mkdir(parents=True, exist_ok=True)
    positive, negative = ref._build_reference_prompt(SLOTS, "photoreal")
    # Reinforce a clean standing side profile w/ exactly four legs.
    positive = ("full body side profile photograph of a dog standing on all "
                "four legs, facing left, complete body in frame, " + positive)
    pipe = ref._load_t2i_pipeline()  # PLAIN SDXL — no ControlNet, no template
    device = "cuda" if torch.cuda.is_available() else "cpu"
    for s in SEEDS:
        gen = torch.Generator(device=device).manual_seed(s)
        img = pipe(prompt=positive, negative_prompt=negative,
                   width=1024, height=1024, guidance_scale=7.5,
                   num_inference_steps=30, generator=gen).images[0]
        p = out / f"cand_{s}.png"
        img.save(p)
        print(f"saved {p.name}", flush=True)
    print("CANDIDATES DONE", flush=True)


if __name__ == "__main__":
    main()
