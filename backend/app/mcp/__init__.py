"""
Fantasy Studio MCP / Tool Layer
═══════════════════════════════

This package is the **abstraction layer between brains and Blender**.

Architecture:
    User prompt
        ↓
    Orchestrator (Phase 5, future) — local Ollama LLM doing ReAct loop
        ↓
    Tool Registry (this package) — Python functions with JSON-schema metadata
        ↓
    Blender Bridge (socket client) → Blender Addon (socket server) → bpy
        ↓
    Result returned up the chain

The SAME tool registry can later expose an MCP server (Phase 6) for power
users who want to drive Studio from Claude Code, Cursor, or any MCP client.
For the main product, the orchestrator drives it locally — no cloud.

Public API:
    from app.mcp import bridge, registry
    bridge.connect()
    result = registry.call("create_primitive", {"type": "cube", "location": [0,0,0]})
"""

from . import blender_bridge as bridge
from . import registry
from .tools import register_all_tools

# Auto-register all tools on import
register_all_tools()

__all__ = ["bridge", "registry"]
