"""Quick sweep: generate quadruped references at varying ControlNet pose-lock
scales + seeds so we can eyeball how many legs SDXL produces. The pose template
encodes near/far legs as offset columns; too strong a lock makes SDXL fill the
ambiguity with a 5th leg. Find the highest scale that still gives a clean 4.

Usage: python scripts/leg_sweep.py
Outputs: renders/_legsweep/dog_s{scale}_seed{seed}.png
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.asset_gen import reference as ref  # noqa: E402

SLOTS = {"subject": {"library_query": "dog", "color_name": "brown",
                     "base_pattern": "quadruped"},
         "scene": {"mood": "golden hour"}}

SCALES = [0.35, 0.22, 0.12, 0.0]
SEEDS = [42, 7]


def main():
    out = BACKEND_ROOT / "renders" / "_legsweep"
    out.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        ref.CONTROLNET_CONDITIONING_SCALE = scale
        for seed in SEEDS:
            p = out / f"dog_s{scale:.2f}_seed{seed}.png"
            print(f"=== scale={scale} seed={seed} -> {p.name}", flush=True)
            ref.generate_reference(SLOTS, output_path=p, style="photoreal", seed=seed)
    print("SWEEP DONE", flush=True)


if __name__ == "__main__":
    main()
