"""
Ollama client — OpenAI-compatible function calling.

Ollama exposes /v1/chat/completions identical to OpenAI's API as of v0.4+.
Tool calling works the same way: pass `tools=[...]`, model returns
`message.tool_calls=[{id, type:"function", function:{name, arguments}}]`,
you execute each, append `{role:"tool", tool_call_id, content}` messages,
loop.

Env vars:
    OLLAMA_HOST   = http://127.0.0.1:11434  (default)
    OLLAMA_MODEL  = qwen2.5-coder:7b        (default, override per call)
"""

import json
import os
from typing import Any, Dict, List, Optional

try:
    import urllib.request
    import urllib.error
except ImportError:
    raise

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Phase 9: slot-extraction architecture — model only needs to output structured JSON,
# not orchestrate multi-step plans. gemma3:12b is solid at this, runs on consumer
# GPUs, and is already validated on the user's hardware (Aurora uses it too).
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:12b")
DEFAULT_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "300"))


class OllamaError(Exception):
    pass


class OllamaClient:
    """Thin wrapper over Ollama's OpenAI-compatible chat endpoint.

    Stateless — message history is owned by the caller (the ToolLoop).
    Auto-retries are deferred to the caller too; this just does the round trip.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ───────────────────────────────────────────────────────────────────
    # Health check
    # ───────────────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        """Quick check that Ollama is reachable. Doesn't verify the model exists."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return names of installed Ollama models."""
        req = urllib.request.Request(f"{self.host}/api/tags")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "<unnamed>") for m in data.get("models", [])]

    def has_model(self, name: Optional[str] = None) -> bool:
        target = name or self.model
        try:
            installed = self.list_models()
        except Exception:
            return False
        # Match exact or with/without :tag
        if target in installed:
            return True
        base = target.split(":")[0]
        return any(m.startswith(base + ":") or m == base for m in installed)

    # ───────────────────────────────────────────────────────────────────
    # Chat completion (OpenAI-compatible)
    # ───────────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion. Returns the OpenAI-shaped message dict from choices[0].

        On tool calls, message.tool_calls is a list of:
            {"id": str, "type": "function", "function": {"name": str, "arguments": json-str}}

        On plain text, message.content is the assistant response.
        """
        body: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise OllamaError(f"HTTP {e.code} from Ollama: {err_body}")
        except urllib.error.URLError as e:
            raise OllamaError(f"can't reach Ollama at {self.host}: {e}")

        choices = payload.get("choices", [])
        if not choices:
            raise OllamaError(f"Ollama returned no choices: {payload}")
        return choices[0].get("message", {})
