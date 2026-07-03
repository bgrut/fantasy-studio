"""
ReAct-style tool loop — drives the LLM to compose a scene step-by-step.

Loop:
    1. messages = [system, user]
    2. Send messages + tool specs to LLM
    3. Read assistant message
       - If it has tool_calls → execute each, append results as "tool" role, repeat
       - If just content → loop ends (LLM is done)
    4. Bail at MAX_ITERATIONS to prevent runaways

This is the exact pattern Claude Code uses internally. The only difference
is the LLM is local (Ollama) instead of cloud (Claude).
"""

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .. import mcp
from ..mcp import registry, bridge
from .llm import OllamaClient, OllamaError
from .prompts import build_system_prompt, has_motion, build_user_message
from .scene_inference import run_pre_render_guard


# ───────────────────────────────────────────────────────────────────────
# Content-as-tool-calls parser
#
# Some local models (notably qwen2.5-coder via Ollama) emit tool calls as
# JSON in the assistant message's `content` field instead of in the
# `tool_calls` array. This parser rescues those — extracts the calls so
# the loop can still execute them.
# ───────────────────────────────────────────────────────────────────────

_VALID_TOOL_NAMES_CACHE: Optional[set] = None


def _all_tool_names() -> set:
    global _VALID_TOOL_NAMES_CACHE
    if _VALID_TOOL_NAMES_CACHE is None:
        _VALID_TOOL_NAMES_CACHE = {t.name for t in registry.list_tools()}
    return _VALID_TOOL_NAMES_CACHE


def _strip_code_fence(text: str) -> str:
    """Strip leading/trailing ``` fences (with or without lang tag)."""
    t = text.strip()
    if t.startswith("```"):
        # remove first line (the fence) and trailing fence if present
        lines = t.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _extract_json_objects(text: str) -> List[Any]:
    """Find JSON objects/arrays in arbitrary text using PROPER bracket balancing.

    Uses json.JSONDecoder().raw_decode() to consume the next valid JSON chunk
    starting at each `{` or `[`. Handles arbitrary nesting (the regex approach
    only handled one level deep, which is why nested arguments like
    `{"location":[0,0,0]}` were losing their args).
    """
    candidates: List[Any] = []

    # Try whole-string first (most common case: clean JSON object/array)
    try:
        candidates.append(json.loads(text))
        return candidates
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{" or c == "[":
            try:
                obj, end_offset = decoder.raw_decode(text[i:])
                candidates.append(obj)
                i += end_offset
                continue
            except json.JSONDecodeError:
                pass
        i += 1
    return candidates


def _parse_python_call_syntax(text: str, valid_names: set) -> List[Dict[str, Any]]:
    """Rescue tool calls emitted as Python function call syntax.

    Catches patterns like:
        list_templates()
        create_primitive(type="cube", size=2)
        set_render_settings(engine='BLENDER_EEVEE', resolution_x=1280)

    Returns OpenAI-shaped tool_call dicts. Best-effort — only handles flat kwargs
    with literal values (numbers, strings, simple lists). Complex nested args
    fall back to the JSON parser.
    """
    out: List[Dict[str, Any]] = []
    # Match name(...) where the body is balanced parens
    for m in re.finditer(r"\b([a-z_][a-z_0-9]*)\s*\(", text):
        name = m.group(1)
        if name not in valid_names:
            continue
        # Find balanced closing paren
        depth = 0
        start = m.end() - 1  # position of '('
        end = None
        in_str = None
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if c == in_str and text[i-1] != "\\":
                    in_str = None
            elif c in ('"', "'"):
                in_str = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        body = text[start+1:end].strip()
        args: Dict[str, Any] = {}
        if body:
            # Best-effort kwarg parser. Won't handle every case but covers the common ones.
            # Try parsing as JSON object first: {"k":1,"v":2}
            try:
                # Replace Python literals with JSON-equivalents
                py_body = body
                py_body = re.sub(r"\bTrue\b", "true", py_body)
                py_body = re.sub(r"\bFalse\b", "false", py_body)
                py_body = re.sub(r"\bNone\b", "null", py_body)
                # If it starts with { just try JSON
                if py_body.lstrip().startswith("{"):
                    args = json.loads(py_body)
                else:
                    # Split on commas at top level, parse each key=value
                    parts = _split_top_level(py_body)
                    for part in parts:
                        if "=" not in part:
                            continue
                        k, v = part.split("=", 1)
                        k = k.strip()
                        v = v.strip()
                        # Replace Python quotes with JSON quotes for literal parse
                        if v.startswith("'") and v.endswith("'"):
                            v = '"' + v[1:-1].replace('"', '\\"') + '"'
                        try:
                            args[k] = json.loads(v)
                        except json.JSONDecodeError:
                            args[k] = v.strip("'\"")
            except Exception:
                args = {}

        try:
            args_str = json.dumps(args)
        except (TypeError, ValueError):
            args_str = "{}"
        out.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        })
    return out


def _split_top_level(body: str) -> List[str]:
    """Split body by commas at depth 0 (ignoring commas inside brackets/quotes)."""
    parts: List[str] = []
    depth = 0
    in_str = None
    start = 0
    for i, c in enumerate(body):
        if in_str:
            if c == in_str and body[i-1] != "\\":
                in_str = None
        elif c in ('"', "'"):
            in_str = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    return parts


def parse_content_as_tool_calls(content: str) -> List[Dict[str, Any]]:
    """When the LLM emits tool calls in `content` instead of `tool_calls`, extract them.

    Returns OpenAI-shaped tool_call dicts:
        [{"id": str, "type": "function", "function": {"name": str, "arguments": json-str}}]
    """
    if not content or not content.strip():
        return []

    text = _strip_code_fence(content)
    valid_names = _all_tool_names()

    # First try Python-call-syntax rescue (covers `list_templates()` style)
    py_rescued = _parse_python_call_syntax(text, valid_names)
    if py_rescued:
        return py_rescued

    found: List[Dict[str, Any]] = []

    def maybe_add(obj: Dict[str, Any]):
        """Try to extract a {name, arguments} from an object and append."""
        if not isinstance(obj, dict):
            return
        name = (
            obj.get("name")
            or obj.get("tool")
            or obj.get("tool_call")
            or obj.get("function")
        )
        args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or obj.get("params")
        # 'function' key might itself be a dict {"name":..,"arguments":..} (OpenAI shape)
        if isinstance(name, dict):
            inner = name
            name = inner.get("name")
            args = args or inner.get("arguments") or inner.get("args")
        if not isinstance(name, str):
            return
        if args is None:
            args = {}
        # Only accept if name maps to a real tool — silences hallucinations
        if name not in valid_names:
            return
        if isinstance(args, str):
            # Already JSON string — keep as-is
            args_str = args
        else:
            try:
                args_str = json.dumps(args)
            except (TypeError, ValueError):
                args_str = "{}"
        found.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        })

    for parsed in _extract_json_objects(text):
        # Shape 1: list of {name,arguments} items
        if isinstance(parsed, list):
            for item in parsed:
                maybe_add(item)
        elif isinstance(parsed, dict):
            # Shape 2: {"tool_calls": [...]}
            if isinstance(parsed.get("tool_calls"), list):
                for tc in parsed["tool_calls"]:
                    if isinstance(tc, dict):
                        # OpenAI shape: {"function": {"name":..,"arguments":..}}
                        inner = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                        maybe_add(inner)
            # Shape 3: {"function_call": {...}}
            elif isinstance(parsed.get("function_call"), dict):
                maybe_add(parsed["function_call"])
            # Shape 4: direct {name, arguments}
            else:
                maybe_add(parsed)

    return found


# ───────────────────────────────────────────────────────────────────────
# Result types
# ───────────────────────────────────────────────────────────────────────

@dataclass
class StepLog:
    iteration: int
    tool_name: str
    tool_args: dict
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "iter": self.iteration,
            "tool": self.tool_name,
            "args": self.tool_args,
            "result": self.result if self.error is None else None,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class LoopResult:
    prompt: str
    final_message: str
    steps: List[StepLog] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = ""
    success: bool = True
    duration_s: float = 0.0
    render_path: Optional[str] = None  # PNG (still) or first frame of animation
    video_path: Optional[str] = None   # MP4 if animation mode succeeded
    is_animation: bool = False

    def summary(self) -> str:
        lines = [
            f"prompt: {self.prompt!r}",
            f"iterations: {self.iterations} ({self.stopped_reason})",
            f"tool calls: {len(self.steps)}",
            f"duration: {self.duration_s:.1f}s",
            f"success: {self.success}",
        ]
        if self.render_path:
            lines.append(f"render: {self.render_path}")
        lines += [
            "",
            "final message from LLM:",
            f"  {self.final_message}",
        ]
        return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────
# Tool loop
# ───────────────────────────────────────────────────────────────────────

class ToolLoop:
    def __init__(
        self,
        llm: Optional[OllamaClient] = None,
        max_iterations: int = 30,
        verbose: bool = True,
        dry_run: bool = False,
        on_step: Optional[Callable[[StepLog], None]] = None,
    ):
        self.llm = llm or OllamaClient()
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.dry_run = dry_run
        self.on_step = on_step

    # ───────────────────────────────────────────────────────────────────

    def run(self, prompt: str, context: Optional[dict] = None) -> LoopResult:
        # Pre-flight: tools registered, LLM reachable, bridge reachable (unless dry-run)
        self._preflight()

        # Snapshot tools as OpenAI function specs
        tool_specs = registry.as_openai_tools()
        if self.verbose:
            print(f"[loop] {len(tool_specs)} tools available")

        # ── CRITICAL: reset Blender's scene before the LLM starts.
        if not self.dry_run:
            try:
                reset_result = registry.call("reset_scene")
                if self.verbose:
                    print(f"[loop] scene reset: {reset_result}")
            except Exception as e:
                if self.verbose:
                    print(f"[loop] WARNING scene reset failed: {e}")

        # ── Detect animation intent from the prompt.
        motion = has_motion(prompt)
        if motion and self.verbose:
            print(f"[loop] motion detected → animation mode (5s @ 24fps = 120 frames)")

        # ── Pre-allocate paths for this run. Force these into render calls so
        # the LLM cannot use stale paths.
        from pathlib import Path
        import datetime
        renders_dir = Path(__file__).resolve().parents[2] / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        prompt_slug = "".join(c if c.isalnum() else "_" for c in prompt.lower()[:40]).strip("_")

        suggested_render_path = (renders_dir / f"render_{ts}_{prompt_slug}.png").as_posix()
        suggested_animation_dir = (renders_dir / f"anim_{ts}_{prompt_slug}").as_posix()
        suggested_video_path = (renders_dir / f"video_{ts}_{prompt_slug}.mp4").as_posix()

        ctx = dict(context or {})
        ctx.setdefault("render_filepath", suggested_render_path)
        if motion:
            ctx["mode"] = "animation"
            ctx["frame_count"] = 120
            ctx["fps"] = 24
            ctx["animation_dir"] = suggested_animation_dir
            ctx["video_filepath"] = suggested_video_path

        system_prompt = build_system_prompt(motion=motion)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": build_user_message(prompt, ctx)},
        ]
        self._suggested_render_path = suggested_render_path
        self._suggested_animation_dir = suggested_animation_dir
        self._suggested_video_path = suggested_video_path
        self._is_animation_mode = motion
        self._explanation_strikes = 0
        self._prompt_text = prompt       # for the pre-render guard's color/mood inference
        self._guard_fired = False         # only fires once per run

        # Helper used in multiple places below. Define it early so any code
        # path that references it (early break, fallback render, etc.) works.
        def _step_truly_succeeded(s) -> bool:
            if s.error:
                return False
            # Some tools (e.g. run_template) return {"error": "..."} dicts
            # instead of raising. Treat those as failures too.
            if isinstance(s.result, dict) and s.result.get("error"):
                return False
            return True
        self._step_truly_succeeded = _step_truly_succeeded

        result = LoopResult(prompt=prompt, final_message="", success=True)
        t0 = time.time()

        for iteration in range(1, self.max_iterations + 1):
            result.iterations = iteration
            if self.verbose:
                print(f"\n[loop iter {iteration}] → LLM")

            try:
                msg = self.llm.chat(messages=messages, tools=tool_specs)
            except OllamaError as e:
                result.success = False
                result.stopped_reason = f"LLM error: {e}"
                result.final_message = f"[orchestrator error] {e}"
                break

            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            # ── Rescue path: some models (qwen2.5-coder) emit tool calls as
            # JSON in the content instead of in tool_calls. Extract them.
            if not tool_calls and content.strip():
                rescued = parse_content_as_tool_calls(content)
                if rescued:
                    if self.verbose:
                        print(f"[loop iter {iteration}] rescued {len(rescued)} tool call(s) from content")
                    tool_calls = rescued
                    # Wipe content since it was actually tool calls in disguise
                    content = ""

            # Echo the LLM message (without tool args spam)
            if self.verbose and content.strip():
                print(f"[loop iter {iteration}] LLM: {content.strip()[:200]}")

            # Append assistant message verbatim — required for tool_call_id correlation
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            # If no tool calls (and nothing rescued), either:
            #   (a) the LLM is genuinely done (already rendered, summarizing)
            #   (b) the LLM dropped into "explanation mode" — wrote markdown/Python/JSON-shaped text
            #       describing what it WOULD do, but didn't actually call tools.
            #   (c) the LLM hallucinated a tool name (rescue parser filtered it out).
            # Treat (b) and (c) as strikes; only (a) is real done.
            if not tool_calls:
                rendered_yet = any(
                    s.tool_name in ("render_frame", "render_animation", "encode_video")
                    and not s.error for s in result.steps
                )
                # In animation mode, "done" requires encode_video too
                if rendered_yet and self._is_animation_mode:
                    video_made = any(
                        s.tool_name == "encode_video" and not s.error
                        for s in result.steps
                    )
                    if not video_made:
                        rendered_yet = False

                if rendered_yet:
                    result.final_message = content or "(no message)"
                    result.stopped_reason = "LLM finished (render complete)"
                    break

                # RELIABILITY FIX #2: count ANY non-tool-call response as a strike.
                # Previously we only flagged markdown shapes; now also catches
                # hallucinated tool names that the rescue parser silently dropped.
                if self._explanation_strikes < 2:
                    self._explanation_strikes += 1
                    if self.verbose:
                        print(f"[loop iter {iteration}] LLM produced no tool calls — sending corrective ({self._explanation_strikes}/2 strikes)")

                    # RELIABILITY FIX #1: if it looks like a hallucinated tool name,
                    # tell the LLM exactly which tool names DO exist.
                    hint_payload = ""
                    if content.strip().startswith("{") and '"name"' in content:
                        valid = sorted({t.name for t in registry.list_tools()})
                        hint_payload = (
                            f"\n\nNOTE: you tried to call a tool that doesn't exist. "
                            f"The valid tool names are: {', '.join(valid)}. "
                            f"Pick one of these and retry."
                        )

                    messages.append({
                        "role": "user",
                        "content": (
                            "STOP. You produced text, not a tool call. "
                            "Your VERY NEXT response MUST be one or more actual tool calls. "
                            "No markdown. No Python code. No JSON-shaped text in your message body. "
                            "Use the structured tool_calls field." + hint_payload
                        ),
                    })
                    continue  # retry the same iteration

                # Out of strikes — LLM genuinely can't proceed
                result.final_message = content or "(no message)"
                result.stopped_reason = "LLM stopped without rendering (out of explanation-mode strikes)"
                break

            # Execute each tool call, append result as "tool" role message
            for tc in tool_calls:
                step = self._execute_tool_call(tc, iteration)
                result.steps.append(step)
                if self.on_step:
                    try:
                        self.on_step(step)
                    except Exception:
                        pass

                # Tool result becomes a tool-role message for the LLM
                tool_msg_content = self._format_tool_result(step)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": step.tool_name,
                    "content": tool_msg_content,
                })
        else:
            # Loop hit max iterations
            result.success = False
            result.stopped_reason = f"max_iterations ({self.max_iterations}) hit"
            result.final_message = "(orchestrator: hit max iterations without LLM signaling done)"

        result.is_animation = self._is_animation_mode

        # Detect render and video outputs
        for s in result.steps:
            if not self._step_truly_succeeded(s):
                continue
            if s.tool_name == "render_frame" and isinstance(s.result, dict):
                result.render_path = result.render_path or s.result.get("filepath")
            elif s.tool_name == "render_animation" and isinstance(s.result, dict):
                # Use first frame as a preview path
                result.render_path = result.render_path or s.result.get("first_frame_path")
            elif s.tool_name == "encode_video" and isinstance(s.result, dict):
                result.video_path = s.result.get("mp4_path")

        # Count scene-modifying tool calls (excludes reads + the auto-reset)
        scene_mod_tools = {
            "create_primitive", "spawn_asset", "add_modifier", "create_material",
            "apply_material", "add_light", "create_camera", "look_at",
            "transform_object", "set_keyframe", "animate_property",
            "orbit_camera_around", "set_frame_range",
            "apply_three_point_lighting", "set_world_background",
            "create_emissive_material", "create_glass_material", "create_metal_material",
            "run_template", "execute_python",
        }
        successful_scene_mods = sum(
            1 for s in result.steps
            if s.tool_name in scene_mod_tools and self._step_truly_succeeded(s)
        )

        # Loud failure: if the LLM never actually modified the scene, the render
        # would just be an empty default scene. Don't pretend that succeeded.
        if successful_scene_mods == 0 and not self.dry_run:
            result.success = False
            result.stopped_reason = (
                f"LLM failed to execute prompt — 0 scene-modifying tools called. "
                f"{result.stopped_reason or 'no clear stop reason'}"
            )
            # Skip fallback render — there's nothing meaningful to render
            result.duration_s = time.time() - t0
            return result

        # Safety net: if loop ended without a successful render BUT the scene was
        # modified, force one. Better than no output for a populated scene.
        if not result.render_path and not self.dry_run and successful_scene_mods > 0:
            if self.verbose:
                print(f"\n[loop] LLM stopped without rendering (but made {successful_scene_mods} scene mods) — forcing fallback render")
            fallback_path = self._fallback_render()
            if fallback_path:
                result.render_path = fallback_path
                result.stopped_reason += " + fallback render"

        result.duration_s = time.time() - t0
        return result

    def _fallback_render(self) -> Optional[str]:
        """If the LLM didn't render, force one with sane defaults. Returns the path or None."""
        out_path = getattr(self, "_suggested_render_path", None)
        if out_path is None:
            from pathlib import Path
            import datetime
            renders_dir = Path(__file__).resolve().parents[2] / "renders"
            renders_dir.mkdir(parents=True, exist_ok=True)
            out_path = (renders_dir / f"fallback_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png").as_posix()

        try:
            # If no camera exists, the render will fail. Best-effort.
            scene_info = registry.call("get_scene_info")
            if not scene_info.get("active_camera"):
                # Try to add one at a sensible default
                registry.call("create_camera", {"name": "FallbackCam", "location": [6, -6, 4]})
                registry.call("look_at", {"object": "FallbackCam", "target": [0, 0, 0]})

            registry.call("set_render_settings", {
                "engine": "BLENDER_EEVEE",
                "resolution_x": 1280,
                "resolution_y": 720,
            })
            registry.call("render_frame", {"filepath": out_path})
            return out_path
        except Exception as e:
            if self.verbose:
                print(f"[loop] fallback render also failed: {e}")
            return None

    # ───────────────────────────────────────────────────────────────────
    # Internals
    # ───────────────────────────────────────────────────────────────────

    def _preflight(self) -> None:
        # Make sure tools are registered (idempotent — auto-runs on app.mcp import too)
        mcp.tools.register_all_tools()

        if not self.llm.is_alive():
            raise RuntimeError(
                f"Ollama not reachable at {self.llm.host}. "
                f"Is `ollama serve` running? Install: https://ollama.com/download"
            )
        if not self.llm.has_model():
            installed = []
            try:
                installed = self.llm.list_models()
            except Exception:
                pass
            raise RuntimeError(
                f"Ollama model '{self.llm.model}' not installed. "
                f"Pull it with: `ollama pull {self.llm.model}`. "
                f"Currently installed: {installed}"
            )

        if not self.dry_run:
            try:
                bridge.connect(timeout=2.0)
                if not bridge.ping(timeout=2.0):
                    raise RuntimeError("ping failed")
            except Exception as e:
                raise RuntimeError(
                    f"Blender bridge not reachable: {e}. "
                    f"Open Blender with addon enabled, OR run "
                    f"`scripts\\start_headless_bridge.ps1`."
                )

    def _execute_tool_call(self, tool_call: dict, iteration: int) -> StepLog:
        fn = tool_call.get("function", {})
        name = fn.get("name", "<unknown>")
        raw_args = fn.get("arguments", "{}")

        # Ollama returns arguments as a JSON string per the OpenAI spec
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError as e:
            return StepLog(
                iteration=iteration, tool_name=name, tool_args={},
                error=f"could not parse args (not JSON): {e}. raw={raw_args!r}",
            )

        # ── Llama 3.1 sometimes wraps its real args inside the dict:
        #    {"tool_call": "render_frame", "args": {"filepath": "..."}}
        # Detect this pattern and unwrap so the inner dict is what reaches the tool.
        if isinstance(args, dict) and isinstance(args.get("args"), dict) and (
            "tool_call" in args or "name" in args or "tool" in args
        ):
            args = args["args"]
        # Same pattern under different key names
        elif isinstance(args, dict) and isinstance(args.get("parameters"), dict) and (
            "tool_call" in args or "name" in args or "tool" in args
        ):
            args = args["parameters"]

        if self.verbose:
            args_preview = json.dumps(args, default=str)
            if len(args_preview) > 200:
                args_preview = args_preview[:197] + "..."
            print(f"[loop iter {iteration}] tool → {name}({args_preview})")

        step = StepLog(iteration=iteration, tool_name=name, tool_args=args)
        t0 = time.time()

        # ── FORCE filepath / output_dir / mp4_path on render-side tools.
        if name == "render_frame" and hasattr(self, "_suggested_render_path"):
            args["filepath"] = self._suggested_render_path
        elif name == "render_animation" and hasattr(self, "_suggested_animation_dir"):
            args["output_dir"] = self._suggested_animation_dir
        elif name == "encode_video" and hasattr(self, "_suggested_video_path"):
            args["frame_dir"] = self._suggested_animation_dir
            args["mp4_path"] = self._suggested_video_path

        # ── PRE-RENDER QUALITY FLOOR — fires BEFORE render_frame / render_animation.
        # Inspects the scene and injects missing lighting/material/camera using
        # defaults derived from the original prompt. Replicates the deterministic
        # guarantees of the legacy template_v2 / cinematic_lighting pipeline.
        if name in ("render_frame", "render_animation") and not self.dry_run:
            if not getattr(self, "_guard_fired", False):
                try:
                    guard_report = run_pre_render_guard(self._prompt_text, verbose=self.verbose)
                    self._guard_fired = True
                    self._guard_report = guard_report
                except Exception as e:
                    if self.verbose:
                        print(f"[loop iter {iteration}] pre-render guard failed: {e}")

        if self.dry_run:
            step.result = {"dry_run": True, "would_call": name, "args": args}
            step.duration_ms = (time.time() - t0) * 1000
            return step

        try:
            step.result = registry.call(name, args)
        except KeyError as e:
            step.error = f"unknown tool: {e}"
        except Exception as e:
            step.error = f"{type(e).__name__}: {e}"

        step.duration_ms = (time.time() - t0) * 1000

        if self.verbose:
            if step.error:
                print(f"[loop iter {iteration}] ✗ {step.error}")
            else:
                preview = json.dumps(step.result, default=str)
                if len(preview) > 200:
                    preview = preview[:197] + "..."
                print(f"[loop iter {iteration}] ✓ {preview}  ({step.duration_ms:.0f}ms)")

        return step

    def _format_tool_result(self, step: StepLog) -> str:
        """Format a tool result as a string the LLM will read on the next turn."""
        if step.error:
            return json.dumps({"ok": False, "error": step.error})
        try:
            return json.dumps({"ok": True, "result": step.result}, default=str)
        except (TypeError, ValueError):
            return json.dumps({"ok": True, "result": repr(step.result)})


# ───────────────────────────────────────────────────────────────────────
# Public convenience entry
# ───────────────────────────────────────────────────────────────────────

def run(
    prompt: str,
    *,
    model: Optional[str] = None,
    max_iterations: int = 30,
    verbose: bool = True,
    dry_run: bool = False,
    context: Optional[dict] = None,
) -> LoopResult:
    """One-shot: render a scene from an English prompt.

    Example:
        from app.orchestrator import render_from_prompt
        result = render_from_prompt("a red metallic cube on a checkered floor at sunset")
        print(result.summary())
    """
    llm = OllamaClient(model=model) if model else OllamaClient()
    loop = ToolLoop(llm=llm, max_iterations=max_iterations, verbose=verbose, dry_run=dry_run)
    return loop.run(prompt, context=context)
