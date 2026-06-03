# Fantasy Studio — MCP / Tool Layer

> Phase 1-4 of the orchestrator architecture. This package gives Studio's "brain" (a local LLM, eventually) the ability to compose Blender scenes through curated, schema-described tools — the same way Claude Code drives `blender-mcp` in those viral videos, but **fully local, no cloud, no API keys**.

---

## Why this exists

The existing Studio pipeline places pre-made library assets according to JSON template recipes. That's deterministic and reliable, but it can't **generate** scenes from natural language. To do that, Studio needs to:

1. Decompose an English prompt into atomic scene operations
2. Iterate against a verifier (HERO_VERIFY)
3. Self-correct when checks fail

This is exactly what Claude Code does when driving Blender via MCP. We're replicating the *pattern*, swapping the cloud LLM for a local one (Ollama: Llama 3.1 / Qwen 2.5 Coder / DeepSeek-Coder).

---

## Architecture

```
┌─────────────────────────────────────────────┐
│ User: "render a cyberpunk street with bike" │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│ Studio Orchestrator (Phase 5, future)       │
│   • Local LLM via Ollama                    │
│   • ReAct loop: think → tool → observe      │
│   • Falls back to templates when stuck      │
└────────────────┬────────────────────────────┘
                 ↓ in-process Python calls
┌─────────────────────────────────────────────┐
│ app/mcp/ — Tool Registry (THIS PACKAGE)     │
│                                             │
│ • scene_state  — read scene                 │
│ • assets       — find_assets, spawn_asset   │
│ • primitives   — create_primitive, transform│
│ • modifiers    — bevel, array, subdivision  │
│ • materials    — create_material, apply     │
│ • lighting     — add_light, 3-point preset  │
│ • camera       — create_camera, look_at     │
│ • animation    — set_keyframe, orbit_camera │
│ • render       — set_settings, render_frame │
│ • templates    — list/score/run recipes     │
│ • verify       — hero_verify 7-check gate   │
│ • execute      — escape hatch (raw Python)  │
└────────────────┬────────────────────────────┘
                 ↓ TCP socket (127.0.0.1:9876)
                 ↓ length-prefixed JSON
┌─────────────────────────────────────────────┐
│ blender_addons/fantasy_studio_bridge        │
│   • Long-lived addon inside Blender         │
│   • Socket server (worker threads)          │
│   • Main-thread dispatcher (bpy timer)      │
│   • Pure handler functions                  │
└────────────────┬────────────────────────────┘
                 ↓
              bpy + scene
```

---

## Setup

### 1. Install the Blender addon

```powershell
cd backend
.\scripts\install_bridge_addon.ps1
```

The script copies `blender_addons/fantasy_studio_bridge/` into Blender's user-scripts folder (`%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`).

### 2. Enable in Blender

1. Open Blender (any scene)
2. **Edit > Preferences > Add-ons**
3. Search **"Fantasy Studio Bridge"** → check the box
4. Bridge auto-starts on `127.0.0.1:9876`
5. Status visible in the N-panel: **View3D > N > Studio tab**

### 3. Smoke test

```powershell
python scripts\smoke_test_bridge.py
```

Should print PASS for every step and dump a test render under `scripts/smoke_test_output/`.

---

## Using the tool registry

```python
from app.mcp import bridge, registry

# Connection auto-opens on first call
result = registry.call("create_primitive", {
    "type": "cube",
    "name": "Hero",
    "location": [0, 0, 1],
    "size": 2.0,
})
print(result)  # {"name": "Hero", "type": "MESH", "dimensions": [...]}

# Run the verifier
report = registry.call("hero_verify")
print("passed:", report["passed"])
for name, check in report["checks"].items():
    print(f"  {name}: ok={check['ok']}")
```

### For the orchestrator (Phase 5)

```python
from app.mcp import registry

# Get OpenAI/Ollama function-calling specs for ALL tools
tool_specs = registry.as_openai_tools()

# Or filter by category — e.g. only geometry tools during a primitive-building step
geo_specs = registry.as_openai_tools(category="primitives") \
          + registry.as_openai_tools(category="modifiers")

# Pass tool_specs to Ollama's chat.completions, get back tool_calls,
# dispatch each via registry.call(name, args)
```

---

## Protocol spec (for debugging)

Both directions over TCP:

```
[4 bytes BE length] [UTF-8 JSON payload]
```

**Request:**
```json
{"id": "<uuid>", "op": "<op_name>", "params": {...}}
```

**Response (success):**
```json
{"id": "<uuid>", "ok": true, "result": <any-json>}
```

**Response (error):**
```json
{"id": "<uuid>", "ok": false, "error": "<msg>", "trace": "...", "code": "<optional>"}
```

**Special op:** `ping` — answered immediately on worker thread without main-thread dispatch (use for liveness checks).

---

## Tool inventory

| Category | Tools | Notes |
|---|---|---|
| `scene_state` | `get_scene_info`, `list_objects`, `get_object_info` | Read-only |
| `assets` | `find_assets`, `spawn_asset`, `reload_asset_registry` | In-process registry lookup; spawn calls bridge |
| `primitives` | `create_primitive`, `delete_object`, `transform_object` | Generative |
| `modifiers` | `add_modifier` | Bevel, subdivision, array, mirror, solidify, boolean, decimate, wireframe, smooth, displace, screw |
| `materials` | `create_material`, `apply_material`, `create_emissive_material`, `create_glass_material`, `create_metal_material` | Principled BSDF |
| `lighting` | `add_light`, `set_world_background`, `apply_three_point_lighting` | POINT/SUN/SPOT/AREA + preset |
| `camera` | `create_camera`, `look_at` | |
| `animation` | `set_keyframe`, `set_frame_range`, `animate_property`, `orbit_camera_around` | |
| `render` | `set_render_settings`, `render_frame` | |
| `templates` | `list_templates`, `score_templates`, `run_template` | Wraps existing `template_v2` (Fork A) |
| `verify` | `hero_verify` | 7-check gate, structured report |
| `escape_hatch` | `execute_python` | Raw bpy access — use sparingly |

Total: **24+ tools** as of v0.1.

---

## What's intentionally NOT in this phase

- **Orchestrator** (Phase 5) — the local LLM driver. Without it, you can call tools manually from Python or future-from Claude Desktop via the MCP side-door (Phase 6). The tools themselves work standalone.
- **MCP server side-door** (Phase 6) — exposes the same registry over the MCP protocol so power users can drive Studio from Claude Code/Cursor. The `as_mcp_tools()` registry export is the foundation.
- **HDRI loaders, particle systems, geometry nodes, constraints** — deferred until the orchestrator tells us they matter via empirical use (audit transcripts → see what it reaches for).
- **Unreal Engine bridge** — separate addon, same pattern, deferred to validate-the-Blender-loop first.

---

## File map

```
backend/
├── blender_addons/fantasy_studio_bridge/   # Runs INSIDE Blender
│   ├── __init__.py        — addon manifest + N-panel UI + auto-start
│   ├── bridge_server.py   — TCP socket server + main-thread dispatcher
│   └── handlers.py        — pure bpy handlers, one per op
│
├── app/mcp/                                 # Runs in orchestrator process
│   ├── __init__.py        — package init + auto-register tools
│   ├── blender_bridge.py  — socket client (Python → addon)
│   ├── registry.py        — Tool dataclass, register_fn(), call()
│   ├── README.md          — this file
│   └── tools/             — one module per category
│       ├── scene_state.py, assets.py, primitives.py, modifiers.py,
│       ├── materials.py, lighting.py, camera.py, animation.py,
│       └── render.py, templates.py, verify.py, execute.py
│
└── scripts/
    ├── install_bridge_addon.ps1   — copy addon into Blender's addons folder
    └── smoke_test_bridge.py       — end-to-end PASS/FAIL test runner
```

---

## Next phases

| Phase | Status | Description |
|---|---|---|
| 1. Tool wrappers | ✅ shipped | Wraps existing backend ops as tools |
| 2. Generative gap | ✅ shipped | create_primitive, modifiers, materials, animation |
| 3. Template tool | ✅ shipped | list/score/run_template — orchestrator can pick curated recipes |
| 4. Verifier loop | ✅ shipped | hero_verify exposed as tool — feedback loop primitive |
| 5. Orchestrator | ⏳ next | Local Ollama-driven ReAct loop |
| 6. MCP side-door | ⏳ optional | Expose registry as MCP for Claude Code / Cursor users |
| 7. Unreal bridge | ⏳ later | Same pattern, UE plugin |
