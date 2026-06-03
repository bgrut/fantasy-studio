"""
Fantasy Studio — Phase 16 diffusion refinement layer.

Wraps SDXL img2img + ControlNet-depth so the orchestrator can take a
procedural Blender frame and turn it into something photoreal (or
stylized: cartoon, anime, painting, claymation).

Key design decisions:

1. **Lazy heavy imports.** torch + diffusers are 2-3s to import even on
   warm caches. We do it inside `refine_frame()` so the whole orchestrator
   stays cheap when refinement is disabled.

2. **One pipeline, reused.** SDXL takes ~30s to load. We cache the
   instance globally so 120-frame animations don't re-pay that.

3. **ControlNet-depth keeps silhouette.** Without depth conditioning,
   img2img drifts — a dog can become a cat. Depth-from-render locks
   the geometry while letting the surfaces be reimagined.

4. **Style is prompt-engineering, not different pipelines.** Photoreal,
   cartoon, anime, painting, claymation are all just different positive
   prompts on the same SDXL Base. Keeps the install lean.

5. **Category-aware proportion prompts.** The slot extractor already
   knows base_pattern (quadruped/biped/vehicle/celestial) and
   library_query ("dog"). We turn that into prompt text the LLM image
   model can use for proportions.

Public API:
    refine_frame(image_path, slots, style="photoreal", strength=0.55)
        → returns Path to refined PNG (next to original, .refined.png)

    refine_animation(frame_dir, slots, style, strength)
        → refines every frame, returns count

    is_available() → bool
        Quick check: torch + diffusers importable AND models downloaded?
"""

from .refiner import (
    refine_frame,
    refine_animation,
    is_available,
    STYLE_PRESETS,
)

__all__ = ["refine_frame", "refine_animation", "is_available", "STYLE_PRESETS"]
