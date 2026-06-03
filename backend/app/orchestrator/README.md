# Studio Orchestrator (Phase 5)

The "brain" that drives Studio's tool layer using a **local** LLM via Ollama. This is what makes Studio function as a standalone product — no Claude subscription, no cloud, no API keys. Same behavior pattern as Claude Code, different model.

---

## Setup

### 1. Install Ollama

Download from https://ollama.com/download. Run `ollama serve` (auto-starts on boot on Windows).

### 2. Pull a model

The orchestrator needs a model that supports **function calling**. Tested/recommended:

```powershell
# Best small option — coder-tuned, strong tool use (~4.7GB)
ollama pull qwen2.5-coder:7b

# Balanced — general-purpose with good tool calling (~4.7GB)
ollama pull llama3.1:8b

# Bigger / better reasoning if you have ≥24GB VRAM
ollama pull qwen2.5-coder:14b
ollama pull llama3.1:70b   # heavy, needs serious GPU
```

Default model is `qwen2.5-coder:7b`. Override with `--model` flag or `OLLAMA_MODEL` env var.

### 3. Start the Blender bridge

Either:
- **Interactive:** open Blender, enable the addon (status in N-panel > Studio).
- **Headless:** `.\scripts\start_headless_bridge.ps1` (no Blender UI appears).

### 4. Run a prompt

```powershell
cd backend
python scripts\render_from_prompt.py "a red metallic cube on a checkered floor at sunset"
```

---

## What happens

```
Your prompt
    ↓
[orchestrator]  → builds: [system_prompt, user_prompt]
    ↓
[Ollama LLM]    ← gets: messages + 31 tool specs
    ↓ returns: assistant_message with tool_calls
[orchestrator]  → executes each tool_call via registry.call
    ↓
[bridge]        → JSON over socket → Blender addon → bpy
    ↓ returns: tool results
[orchestrator]  → appends results as "tool" messages, loops
    ↓
[Ollama LLM]    ← next turn: sees results, decides next ops
    ↓
... repeat until LLM stops calling tools (scene done + rendered)
    ↓
final summary printed
```

---

## CLI flags

```
python scripts\render_from_prompt.py PROMPT [options]

Options:
  --model MODEL              Ollama model (default: qwen2.5-coder:7b)
  --max-iterations N         Safety cap on loop iterations (default: 30)
  --dry-run                  Print what tools WOULD be called, no Blender ops
  --quiet                    Suppress per-step output
  --save-trace PATH          Write full step-by-step JSON trace to PATH
```

---

## Tips

- **Start specific.** "A red cube" is better than "something cool". Give the LLM concrete subjects, lighting hints, and a vibe.
- **Iterate prompts, not code.** If output is off, refine the English. Most fixes are prompt-level.
- **Use `--dry-run` first** when testing new prompts. You'll see the plan without burning compute.
- **`--save-trace`** is your debugging gold — full JSON log of every tool call, args, result, errors.
- **Restart the bridge after Blender crashes.** The orchestrator surfaces "bridge unreachable" errors clearly.

---

## What this is NOT (yet)

- **Multi-turn dialogue.** The orchestrator runs once per prompt. No "make it bluer" follow-ups. Could be added with a conversation-state layer.
- **GPU-aware model selection.** Right now it's your job to pick a model that fits your VRAM. Could auto-detect later.
- **Pre-render preview.** It runs the full scene compose + render. A "plan only" surface would help iteration. (`--dry-run` is close but doesn't talk to Blender at all.)
- **MCP side-door.** Phase 6 — exposes the same tools to Claude Code / Cursor over MCP for power users.

---

## File map

```
app/orchestrator/
├── __init__.py     — package entry, re-exports run()
├── llm.py          — OllamaClient (HTTP wrapper, function-calling)
├── prompts.py      — versioned system prompt
├── loop.py         — ToolLoop class, the ReAct loop
├── cli.py          — argparse CLI
└── README.md       — this file

scripts/
└── render_from_prompt.py  — top-level entry: `python scripts/render_from_prompt.py "..."`
```
