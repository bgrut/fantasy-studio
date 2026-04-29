from __future__ import annotations

"""
llm_service.py
==============
Single interface for all LLM calls in the pipeline. Wraps a locally-running
Ollama instance (Gemma 3, Gemma 4, or any compatible model) and exposes a
small, opinionated API:

    query_llm(system_prompt, user_prompt, response_schema=None) -> dict | str
    parse_structured_response(raw, schema) -> dict
    enhance_prompt(raw_prompt) -> str

Design rules
------------
- LLM never touches the render pipeline directly. It only outputs structured
  JSON which downstream Python consumes.
- Every call has a hard timeout (default 12 s). On timeout / connection
  failure / invalid JSON, the function returns ``None`` so the caller can
  fall back to its existing hardcoded logic.
- The system prompt always ends with: "Respond ONLY with valid JSON matching
  the provided schema. No preamble, no markdown, no explanation."
- The model name is read from environment variable ``FANTASY_LLM_MODEL``
  (default: ``gemma3:12b``) and the host from ``FANTASY_LLM_HOST`` (default:
  ``http://localhost:11434``) so we can swap models without code changes.
- Every call is logged with timing so we can debug LLM latency in prod.

If the ``requests`` library or Ollama itself is unavailable, every public
function returns ``None`` and prints a one-line warning. Callers MUST be
defensive — they MUST always have a hardcoded fallback.
"""

import json
import os
import re
import time
from typing import Any

from .json_utils import safe_response_json

try:
    import requests  # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_MODEL = os.environ.get("FANTASY_LLM_MODEL", "gemma3:12b")
DEFAULT_HOST = os.environ.get("FANTASY_LLM_HOST", "http://localhost:11434")
DEFAULT_TIMEOUT = float(os.environ.get("FANTASY_LLM_TIMEOUT", "12"))
LLM_ENABLED = os.environ.get("FANTASY_LLM_ENABLED", "1") not in ("0", "false", "False", "")

_JSON_INSTRUCTION = (
    "Respond ONLY with valid JSON matching the provided schema. "
    "No preamble, no markdown, no explanation, no surrounding text."
)


# ═══════════════════════════════════════════════════════════════════════════
# Call tracking & file logging
# ═══════════════════════════════════════════════════════════════════════════

from pathlib import Path as _Path

_LOG_DIR = _Path(__file__).resolve().parents[2] / "logs"
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
_LOG_FILE = _LOG_DIR / "llm_calls.log"


class _CallStats:
    """Lightweight per-process call tracking for the diagnostic endpoint."""
    total_calls: int = 0
    total_fallbacks: int = 0
    last_call_ts: float = 0.0
    last_call_latency_ms: float = 0.0
    last_fallback_reason: str = ""

_stats = _CallStats()


def _log_to_file(line: str) -> None:
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_stats() -> dict:
    return {
        "total_calls": _stats.total_calls,
        "total_fallbacks": _stats.total_fallbacks,
        "last_call_timestamp": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(_stats.last_call_ts)
        ) if _stats.last_call_ts else None,
        "last_call_latency_ms": round(_stats.last_call_latency_ms, 1),
        "last_fallback_reason": _stats.last_fallback_reason or None,
        "mode": "llm" if is_available() else "fallback",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Status / availability
# ═══════════════════════════════════════════════════════════════════════════

_AVAILABILITY_CACHE: dict[str, Any] = {"checked": 0.0, "available": None}
_AVAILABILITY_TTL = 60.0  # re-check Ollama every 60s


def is_available() -> bool:
    """
    Check whether Ollama is reachable and the configured model is loaded.
    Result is cached for 60 seconds so we don't ping Ollama on every call.
    """
    if not LLM_ENABLED or not _HAS_REQUESTS:
        return False

    now = time.time()
    if (now - _AVAILABILITY_CACHE["checked"]) < _AVAILABILITY_TTL:
        cached = _AVAILABILITY_CACHE["available"]
        if cached is not None:
            return cached

    try:
        r = requests.get(f"{DEFAULT_HOST}/api/tags", timeout=2.0)
        ok = r.status_code == 200
        _AVAILABILITY_CACHE["checked"] = now
        _AVAILABILITY_CACHE["available"] = ok
        if ok:
            print(f"[LLM] Ollama reachable at {DEFAULT_HOST} (model={DEFAULT_MODEL})", flush=True)
        return ok
    except Exception as e:
        _AVAILABILITY_CACHE["checked"] = now
        _AVAILABILITY_CACHE["available"] = False
        print(f"[LLM] Ollama unavailable ({e}); pipeline will use fallbacks", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Core call
# ═══════════════════════════════════════════════════════════════════════════

def query_llm(
    system_prompt: str,
    user_prompt: str,
    response_schema: dict | None = None,
    *,
    model: str | None = None,
    timeout: float | None = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str | None:
    """
    Send a prompt to the local Ollama instance and return the raw text body.

    Parameters
    ----------
    system_prompt : str
        Role/system instruction. The standard JSON-only suffix is appended
        automatically when ``response_schema`` is provided.
    user_prompt : str
        Free-form user instruction. May include context.
    response_schema : dict, optional
        If supplied, the schema is included in the system prompt as a JSON
        block so the model knows what shape to produce.
    model : str, optional
        Override the configured default model.
    timeout : float, optional
        Per-call timeout in seconds. Defaults to ``DEFAULT_TIMEOUT``.
    temperature : float
        Lower values (0.1–0.3) yield more deterministic output, which is
        what we want for structured directorial decisions.
    max_tokens : int
        Upper bound on tokens generated. 800 is enough for the largest
        directorial manifest we expect.

    Returns
    -------
    str | None
        The raw response text, or ``None`` if the call failed.
    """
    if not _HAS_REQUESTS or not LLM_ENABLED:
        _stats.total_fallbacks += 1
        _stats.last_fallback_reason = "requests not installed" if not _HAS_REQUESTS else "LLM_ENABLED=0"
        _log_to_file(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] FALLBACK: {_stats.last_fallback_reason}")
        return None
    if not is_available():
        _stats.total_fallbacks += 1
        _stats.last_fallback_reason = "Ollama not reachable"
        _log_to_file(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] FALLBACK: Ollama not reachable")
        return None

    model = model or DEFAULT_MODEL
    timeout = timeout or DEFAULT_TIMEOUT

    # Build the system prompt
    full_system = system_prompt.strip()
    if response_schema is not None:
        schema_block = json.dumps(response_schema, indent=2)
        full_system += "\n\nResponse JSON schema:\n" + schema_block
    full_system += "\n\n" + _JSON_INSTRUCTION

    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": full_system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    started = time.time()
    _stats.total_calls += 1
    try:
        r = requests.post(
            f"{DEFAULT_HOST}/api/generate",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        # safe_response_json tolerates a leading UTF-8 BOM that strict
        # r.json() would otherwise reject.
        data = safe_response_json(r) or {}
        text = data.get("response", "").strip()
        elapsed = time.time() - started
        _stats.last_call_ts = time.time()
        _stats.last_call_latency_ms = elapsed * 1000
        log_line = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] OK | {model} | {elapsed:.2f}s | "
            f"{len(text)} chars | prompt={user_prompt[:80]!r} | resp={text[:120]!r}"
        )
        print(f"[LLM] {model} | {elapsed:.2f}s | {len(text)} chars | user_prompt[:60]={user_prompt[:60]!r}", flush=True)
        _log_to_file(log_line)
        return text
    except Exception as e:
        elapsed = time.time() - started
        _stats.total_fallbacks += 1
        _stats.last_fallback_reason = str(e)[:200]
        _stats.last_call_ts = time.time()
        _stats.last_call_latency_ms = elapsed * 1000
        log_line = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] FAIL | {model} | {elapsed:.2f}s | "
            f"error={e!r} | prompt={user_prompt[:80]!r}"
        )
        print(f"[LLM] call failed after {elapsed:.2f}s: {e}", flush=True)
        _log_to_file(log_line)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Structured response parsing
# ═══════════════════════════════════════════════════════════════════════════

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.MULTILINE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def parse_structured_response(raw: str | None, schema: dict | None = None) -> dict | None:
    """
    Extract a JSON object from a raw LLM response. Tolerates markdown
    fences, leading/trailing chatter, and minor formatting issues.

    Returns ``None`` if no valid JSON object can be found.

    Schema validation is intentionally lightweight: we only check that the
    top-level keys (if specified) are present. Strict validation is the
    caller's responsibility — typically by passing the parsed dict through
    a pydantic model that already exists in the pipeline.
    """
    if not raw:
        return None

    # 1. Try fenced code block first (LLMs often wrap JSON in ```json ... ```)
    m = _JSON_FENCE_RE.search(raw)
    candidate = m.group(1) if m else None

    # 2. Fall back to first {...} substring
    if candidate is None:
        m = _JSON_OBJECT_RE.search(raw)
        candidate = m.group(0) if m else None

    if candidate is None:
        print(f"[LLM] parse: no JSON object found in response", flush=True)
        return None

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        # Try a tolerant fix: trailing commas
        cleaned = re.sub(r",(\s*[\]}])", r"\1", candidate)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"[LLM] parse: invalid JSON ({e})", flush=True)
            return None

    if not isinstance(parsed, dict):
        print(f"[LLM] parse: top-level is not an object (got {type(parsed).__name__})", flush=True)
        return None

    # Optional shallow schema check: required top-level keys
    if schema and isinstance(schema, dict):
        required = list(schema.keys())
        missing = [k for k in required if k not in parsed]
        if missing:
            print(f"[LLM] parse: missing required keys {missing}", flush=True)
            # Don't return None — allow caller to use what we have

    return parsed


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: structured query that returns dict directly
# ═══════════════════════════════════════════════════════════════════════════

def structured_query(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    *,
    model: str | None = None,
    timeout: float | None = None,
) -> dict | None:
    """
    Convenience wrapper: query_llm() + parse_structured_response().
    Returns parsed dict or None on any failure.
    """
    raw = query_llm(
        system_prompt,
        user_prompt,
        response_schema=schema,
        model=model,
        timeout=timeout,
    )
    return parse_structured_response(raw, schema)


# ═══════════════════════════════════════════════════════════════════════════
# Optional prompt enhancement
# ═══════════════════════════════════════════════════════════════════════════

_PROMPT_ENHANCE_SYSTEM = (
    "You are a cinematic prompt enhancer for a 3D animation engine. "
    "Given a short user prompt, expand it into a richer one-sentence "
    "description that adds time of day, mood, lighting, and one specific "
    "cinematic detail. Do not change the subject. Keep it under 30 words. "
    "Respond with the enhanced sentence ONLY — no quotes, no preamble."
)


def enhance_prompt(raw_prompt: str) -> str:
    """
    Optionally enrich a sparse user prompt with cinematic detail.
    The enhanced prompt is internal — the user never sees it. Used to
    feed the scene planner with more context.

    On any failure (no Ollama, timeout, etc.) returns ``raw_prompt`` so
    the pipeline never breaks.
    """
    if not raw_prompt or not raw_prompt.strip():
        return raw_prompt
    if not LLM_ENABLED or not is_available():
        return raw_prompt

    raw = query_llm(
        _PROMPT_ENHANCE_SYSTEM,
        raw_prompt.strip(),
        response_schema=None,
        temperature=0.4,
        max_tokens=80,
    )
    if not raw:
        return raw_prompt

    # Take only the first line, strip quotes/markdown
    text = raw.strip().splitlines()[0].strip().strip('"').strip("'")
    if not text:
        return raw_prompt

    print(f"[LLM] prompt enhanced: {raw_prompt!r} -> {text!r}", flush=True)
    return text
