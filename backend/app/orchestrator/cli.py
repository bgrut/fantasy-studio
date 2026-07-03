"""
Orchestrator CLI.

Default mode: 'slots' (Sora-style — extract slots, deterministic compose).
Fallback mode: 'freeform' (legacy ReAct loop).

Usage:
    python -m app.orchestrator.cli "a red metallic cube"
    python -m app.orchestrator.cli --mode freeform "..."   # use legacy loop
    python -m app.orchestrator.cli --model llama3.1:8b "..."
"""

import argparse
import json
import sys
from pathlib import Path

from . import render_from_prompt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="studio-orchestrator",
        description="Render a Blender scene from an English prompt using a local LLM.",
    )
    parser.add_argument("prompt", help="English description of the scene to render")
    parser.add_argument(
        "--mode",
        choices=["slots", "freeform"],
        default="slots",
        help="slots = deterministic pipeline driven by slot extraction (default, reliable). "
             "freeform = legacy ReAct loop (experimental, variable quality).",
    )
    parser.add_argument("--model", default=None, help="Ollama model (default: gemma3:12b)")
    parser.add_argument("--max-iterations", type=int, default=30, help="(freeform mode only) safety cap")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-step output")
    parser.add_argument("--save-trace", type=str, default=None, help="Write JSON trace of the run")
    parser.add_argument("--quick", action="store_true",
                        help="Iteration mode: render a single still frame (no 120-frame animation). 5x faster.")
    parser.add_argument("--no-render", action="store_true",
                        help="Skip render entirely. Only produces reference image + GLB mesh + .blend file. "
                             "Fastest path to inspect orientation/mesh quality.")

    args = parser.parse_args(argv)
    verbose = not args.quiet
    import os
    if args.quick:
        os.environ["FANTASY_STUDIO_QUICK"] = "1"
    if args.no_render:
        os.environ["FANTASY_STUDIO_NO_RENDER"] = "1"

    print(f"┌─ Studio Orchestrator")
    print(f"│  prompt:  {args.prompt}")
    print(f"│  mode:    {args.mode}")
    print(f"│  model:   {args.model or 'default (gemma3:12b)'}")
    print(f"└─\n")

    try:
        if args.mode == "slots":
            result = render_from_prompt(
                prompt=args.prompt,
                mode="slots",
                model=args.model,
                verbose=verbose,
            )
        else:  # freeform
            result = render_from_prompt(
                prompt=args.prompt,
                mode="freeform",
                model=args.model,
                verbose=verbose,
                max_iterations=args.max_iterations,
            )
    except RuntimeError as e:
        print(f"\n✗ Preflight failed: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    print("\n" + "═" * 70)
    print(f"RESULT — mode={result.get('mode')}")
    print("═" * 70)
    print(f"  success:  {result.get('success')}")
    print(f"  duration: {result.get('duration_s', 0):.1f}s")

    if result.get("mode") == "slots":
        slots = result.get("slots") or {}
        subj = slots.get("subject", {})
        scene = slots.get("scene", {})
        motion = slots.get("motion", {})
        cam = slots.get("camera", {})
        out_s = slots.get("output", {})
        print(f"\nExtracted slots:")
        print(f"  subject:  {subj.get('shape')} ({subj.get('color_name')}, {subj.get('material')}, emissive={subj.get('emissive')})")
        print(f"  scene:    mood={scene.get('mood')}, ground={scene.get('ground')}")
        print(f"  motion:   {motion.get('type')} @ {motion.get('speed')}")
        print(f"  camera:   {cam.get('framing')} {cam.get('angle')}")
        print(f"  output:   {out_s.get('resolution')}, animation={out_s.get('is_animation')}, {out_s.get('duration_seconds')}s")
        if result.get("slot_notes"):
            print(f"  notes:    {result['slot_notes']}")
        steps_run = result.get("steps_run") or []
        errors = result.get("errors") or []
        print(f"\nComposer: {len(steps_run)} steps, {len(errors)} errors")
        if errors and verbose:
            for e in errors:
                print(f"  ✗ {e}")
    else:
        print(f"  iterations:   {result.get('iterations')}")
        print(f"  tool calls:   {result.get('tool_calls')}")
        print(f"  stopped:      {result.get('stopped_reason')}")

    if result.get("video_path"):
        print("\n" + "─" * 70)
        print(f"  🎬 VIDEO: {result['video_path']}")
        print("─" * 70)
    elif result.get("render_path"):
        print("\n" + "─" * 70)
        print(f"  🖼️  RENDER: {result['render_path']}")
        print("─" * 70)

    if args.save_trace:
        trace_path = Path(args.save_trace)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nTrace written to: {trace_path}")

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
