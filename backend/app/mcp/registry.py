"""
Tool Registry — single source of truth for what Studio's "brain" can do.

A Tool is a Python callable wrapped with:
    - name: stable identifier the orchestrator references
    - description: what it does, in plain English (LLM reads this)
    - input_schema: JSON Schema for params (LLM uses this to format calls)
    - handler: the Python function that does the work

Output formats:
    - registry.as_openai_tools()   → list of OpenAI/Ollama function-calling specs
    - registry.as_mcp_tools()      → list of MCP tool definitions (for Phase 6)
    - registry.call(name, params)  → invoke a tool by name, returns result

Design notes:
    - Tools live in app/mcp/tools/*.py — each file calls register() at import time
    - Most handlers just delegate to bridge.call(<op>, params) — i.e. they're
      thin wrappers around the addon's dispatcher. Some (templates, asset
      registry) do real work in this process before calling the bridge.
    - Categories tag tools for filtering (e.g. orchestrator can request only
      "geometry" tools when planning a scene primitive step).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# Common LLM-isms we silently normalize so a confused model doesn't deadlock the loop.
# When the LLM uses key_x, we treat it as the canonical key. Per-tool schemas take
# precedence — if a tool's schema explicitly has the LLM-ism (rare), don't rewrite.
_PARAM_ALIASES: Dict[str, str] = {
    "object_name":     "object",
    "obj_name":        "object",
    "obj":             "object",
    "material_name":   "material",
    "mat_name":        "material",
    "mat":             "material",
    "filename":        "filepath",
    "output_path":     "filepath",
    "output_file":     "filepath",
    "tool_name":       "name",
    "loc":             "location",
    "rotation":        "rotation_euler",  # most callers mean euler
    "kind_name":       "kind",
    "modifier_kind":   "kind",
    "modifier_type":   "kind",
    "object_to_modify": "object",
    "target_object":   "object",
    "color_rgb":       "color",
    "base_color":      "color",
    "strength_value":  "strength",
    "energy_value":    "energy",
    "frame_number":    "frame",
}


def _coerce_value(value: Any, expected_type: Optional[str]) -> Any:
    """Best-effort coerce a value to match its declared JSON schema type.

    The single most common LLM bug: emitting JSON arrays as STRINGS that contain
    array syntax — `"location": "[0,0,1]"` instead of `"location": [0,0,1]`.
    bpy then reads the string as a sequence of characters and fails.

    This function fixes that class of bug. It runs before tool dispatch.
    """
    if value is None:
        return value

    if expected_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            s = value.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            # Last-resort: comma-split a "1,2,3" style string
            if "," in s:
                parts = [p.strip() for p in s.strip("[]()").split(",") if p.strip()]
                # Try to coerce each part to a number if they all look numeric
                try:
                    return [float(p) if "." in p else int(p) for p in parts]
                except (ValueError, TypeError):
                    return parts
            return value

    if expected_type == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return value

    if expected_type in ("number", "integer"):
        if isinstance(value, (int, float)):
            return int(value) if expected_type == "integer" else value
        if isinstance(value, str):
            try:
                f = float(value)
                return int(f) if expected_type == "integer" else f
            except ValueError:
                pass
        return value

    if expected_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.lower().strip()
            if v in ("true", "1", "yes", "on"):
                return True
            if v in ("false", "0", "no", "off"):
                return False
        return value

    if expected_type == "string":
        if isinstance(value, str):
            return value
        # JSON-encode complex types to a string the handler can read
        try:
            return json.dumps(value) if not isinstance(value, (int, float, bool)) else str(value)
        except (TypeError, ValueError):
            return str(value)

    return value


def _normalize_params(schema: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Apply alias rename + type coercion to params. Defensive against LLM sloppiness."""
    if not isinstance(params, dict):
        return params
    schema_props = (schema or {}).get("properties", {}) or {}
    out: Dict[str, Any] = {}

    for k, v in params.items():
        # Step 1: resolve to canonical key via alias map
        if k in schema_props:
            target_key = k
        else:
            canonical = _PARAM_ALIASES.get(k)
            if canonical and canonical in schema_props:
                target_key = canonical
            else:
                # Unknown key — pass through (handler may accept extras or raise)
                out[k] = v
                continue

        # Step 2: coerce value to declared type
        prop_schema = schema_props.get(target_key, {})
        if isinstance(prop_schema, dict):
            # Handle 'oneOf' / 'anyOf' — pick the first declared type as the coercion target
            if "oneOf" in prop_schema or "anyOf" in prop_schema:
                variants = prop_schema.get("oneOf") or prop_schema.get("anyOf") or []
                expected_type = None
                for variant in variants:
                    if isinstance(variant, dict) and "type" in variant:
                        expected_type = variant["type"]
                        # Prefer 'object' or 'array' if value is a string that looks structural
                        if isinstance(v, str) and v.strip().startswith(("[", "{")) and expected_type in ("array", "object"):
                            break
            else:
                expected_type = prop_schema.get("type")
            if expected_type:
                v = _coerce_value(v, expected_type)

        # Don't clobber if a previous alias already mapped to this canonical
        if target_key not in out:
            out[target_key] = v

    return out


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]
    category: str = "general"
    side_effects: bool = True  # False for pure read tools (get_scene_info etc)

    def __call__(self, params: Optional[Dict[str, Any]] = None) -> Any:
        normalized = _normalize_params(self.input_schema, params or {})
        return self.handler(normalized)


_REGISTRY: Dict[str, Tool] = {}


# ───────────────────────────────────────────────────────────────────────
# Registration
# ───────────────────────────────────────────────────────────────────────

def register(tool: Tool) -> None:
    if tool.name in _REGISTRY:
        # Overwrite is allowed (dev iteration), but log it
        print(f"[mcp.registry] overwriting existing tool: {tool.name}")
    _REGISTRY[tool.name] = tool


def register_fn(
    name: str,
    description: str,
    input_schema: Dict[str, Any],
    category: str = "general",
    side_effects: bool = True,
) -> Callable[[Callable], Callable]:
    """Decorator form.

    @register_fn("create_primitive", "Spawn a primitive mesh.", {...})
    def my_handler(params): ...
    """
    def deco(fn: Callable[[Dict[str, Any]], Any]) -> Callable:
        register(Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=fn,
            category=category,
            side_effects=side_effects,
        ))
        return fn
    return deco


# ───────────────────────────────────────────────────────────────────────
# Lookup + invocation
# ───────────────────────────────────────────────────────────────────────

def get(name: str) -> Tool:
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool: {name}. available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def call(name: str, params: Optional[Dict[str, Any]] = None) -> Any:
    return get(name)(params)


def list_tools(category: Optional[str] = None) -> List[Tool]:
    if category:
        return [t for t in _REGISTRY.values() if t.category == category]
    return list(_REGISTRY.values())


def categories() -> List[str]:
    return sorted({t.category for t in _REGISTRY.values()})


# ───────────────────────────────────────────────────────────────────────
# Export formats — feed these to Ollama / MCP later
# ───────────────────────────────────────────────────────────────────────

def as_openai_tools(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """OpenAI / Ollama function-calling format. Drop into chat.completions params."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in list_tools(category=category)
    ]


def as_mcp_tools(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """MCP tool format. Used by the Phase 6 MCP side-door server."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.input_schema,
        }
        for t in list_tools(category=category)
    ]


def summary() -> Dict[str, Any]:
    """Quick human-readable overview — what tools exist, grouped by category."""
    by_cat: Dict[str, List[str]] = {}
    for t in _REGISTRY.values():
        by_cat.setdefault(t.category, []).append(t.name)
    return {
        "total": len(_REGISTRY),
        "categories": {k: sorted(v) for k, v in sorted(by_cat.items())},
    }
