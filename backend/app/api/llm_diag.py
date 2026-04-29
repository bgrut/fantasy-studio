from __future__ import annotations

"""
api/llm_diag.py
===============
Diagnostic endpoints for the local LLM integration.

    GET  /api/llm/status    connection state + call counters
    POST /api/llm/test      send a free-form prompt and return raw response
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.llm_service import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    LLM_ENABLED,
    get_stats,
    is_available,
    query_llm,
)


router = APIRouter(prefix="/api/llm", tags=["llm-diagnostics"])


@router.get("/status")
def llm_status():
    ollama_reachable = is_available()
    stats = get_stats()
    return {
        "ollama_reachable": ollama_reachable,
        "ollama_host": DEFAULT_HOST,
        "model_loaded": DEFAULT_MODEL if ollama_reachable else None,
        "llm_enabled": LLM_ENABLED,
        "last_call_timestamp": stats["last_call_timestamp"],
        "last_call_latency_ms": stats["last_call_latency_ms"],
        "total_calls": stats["total_calls"],
        "total_fallbacks": stats["total_fallbacks"],
        "last_fallback_reason": stats["last_fallback_reason"],
        "mode": stats["mode"],
    }


class TestPrompt(BaseModel):
    prompt: str
    temperature: float = 0.4
    max_tokens: int = 200


@router.post("/test")
def llm_test(payload: TestPrompt):
    if not is_available():
        return {
            "ok": False,
            "model": DEFAULT_MODEL,
            "response": None,
            "error": "Ollama is not reachable or LLM is disabled",
        }

    raw = query_llm(
        "You are a helpful creative assistant for a cinematic 3D engine.",
        payload.prompt,
        response_schema=None,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )

    return {
        "ok": raw is not None,
        "model": DEFAULT_MODEL,
        "response": raw,
        "error": None if raw else "LLM returned no response",
    }
