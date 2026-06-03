"""
Studio Orchestrator — local-LLM-driven scene composer.

Two execution modes:

    1. SLOT MODE (default, recommended) — `render_from_prompt_slots()`
       LLM extracts structured slots from English (one call); deterministic
       Python pipeline (`composer.py`) builds + renders the scene. Reliable,
       fast, works with smaller models. THIS IS THE SORA-STYLE ARCHITECTURE.

    2. FREEFORM MODE — `render_from_prompt_freeform()`
       LLM drives a ReAct loop, calling tools step-by-step. More flexible
       but much less reliable. Kept as a fallback for prompts that don't
       fit the slot schema, and as a research tool.

Top-level convenience: `render_from_prompt()` defaults to slot mode.
"""

from typing import Any, Dict, Optional

from .llm import OllamaClient
from .slots import extract_slots, SlotExtractionResult
from .composer import compose_scene, CompositionResult
from .loop import ToolLoop, run as _run_freeform, LoopResult

__all__ = [
    "OllamaClient",
    "extract_slots",
    "compose_scene",
    "render_from_prompt",
    "render_from_prompt_slots",
    "render_from_prompt_freeform",
    "SlotExtractionResult",
    "CompositionResult",
    "LoopResult",
    "ToolLoop",
]


# ───────────────────────────────────────────────────────────────────────
# Path allocation (shared by both modes — keeps outputs organized)
# ───────────────────────────────────────────────────────────────────────

def _allocate_paths(prompt: str) -> Dict[str, str]:
    from pathlib import Path
    import datetime

    backend_root = Path(__file__).resolve().parents[2]
    renders_dir = backend_root / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() else "_" for c in prompt.lower()[:40]).strip("_")

    return {
        "render_filepath":  (renders_dir / f"render_{ts}_{slug}.png").as_posix(),
        "animation_dir":    (renders_dir / f"anim_{ts}_{slug}").as_posix(),
        "video_filepath":   (renders_dir / f"video_{ts}_{slug}.mp4").as_posix(),
    }


# ───────────────────────────────────────────────────────────────────────
# Slot-based render (NEW DEFAULT)
# ───────────────────────────────────────────────────────────────────────

def render_from_prompt_slots(
    prompt: str,
    *,
    model: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Sora-style architecture: LLM extracts slots → deterministic pipeline composes.

    Returns a dict with:
        mode, success, render_path, video_path, is_animation,
        slots, slot_notes, steps_run, errors, duration_s
    """
    llm = OllamaClient(model=model) if model else OllamaClient()

    if verbose:
        print(f"\n[orchestrator] mode=slots, model={llm.model}")
        print(f"[orchestrator] prompt: {prompt!r}\n")

    # Step 1: extract slots
    slot_result = extract_slots(prompt, llm=llm, verbose=verbose)

    # Step 2: compose scene from slots
    paths = _allocate_paths(prompt)
    if verbose:
        print()
    comp_result = compose_scene(slot_result.slots, paths=paths, verbose=verbose)

    return {
        "mode": "slots",
        "prompt": prompt,
        "success": comp_result.success,
        "render_path": comp_result.render_path,
        "video_path": comp_result.video_path,
        "is_animation": comp_result.is_animation,
        "slots": slot_result.slots,
        "slot_notes": slot_result.notes,
        "slot_defaults_used": slot_result.used_defaults,
        "steps_run": comp_result.steps_run,
        "errors": comp_result.errors,
        "duration_s": comp_result.duration_s,
        "paths": paths,
    }


# ───────────────────────────────────────────────────────────────────────
# Freeform render (legacy ReAct loop — kept for advanced/edge cases)
# ───────────────────────────────────────────────────────────────────────

def render_from_prompt_freeform(
    prompt: str,
    *,
    model: Optional[str] = None,
    max_iterations: int = 30,
    verbose: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Original ReAct-loop architecture. LLM drives tool calls iteratively.

    Less reliable than slot mode but more flexible — falls back to this when
    the slot schema can't capture a prompt's structure (rare).
    """
    result = _run_freeform(
        prompt=prompt,
        model=model,
        max_iterations=max_iterations,
        verbose=verbose,
        dry_run=dry_run,
    )
    return {
        "mode": "freeform",
        "prompt": prompt,
        "success": result.success,
        "render_path": result.render_path,
        "video_path": result.video_path,
        "is_animation": result.is_animation,
        "iterations": result.iterations,
        "stopped_reason": result.stopped_reason,
        "tool_calls": len(result.steps),
        "final_message": result.final_message,
        "duration_s": result.duration_s,
    }


# ───────────────────────────────────────────────────────────────────────
# Top-level entry — defaults to slot mode
# ───────────────────────────────────────────────────────────────────────

def render_from_prompt(
    prompt: str,
    *,
    mode: str = "slots",
    model: Optional[str] = None,
    verbose: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """Convenience entry. Default mode=slots (recommended).

    Set mode="freeform" to use the legacy ReAct loop.
    """
    if mode == "slots":
        return render_from_prompt_slots(prompt, model=model, verbose=verbose)
    elif mode == "freeform":
        return render_from_prompt_freeform(prompt, model=model, verbose=verbose, **kwargs)
    else:
        raise ValueError(f"unknown mode: {mode!r}. expected 'slots' or 'freeform'.")
