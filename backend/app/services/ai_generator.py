"""
AI 3D-model generator — last-resort fallback when curated / Objaverse /
Sketchfab all fail to produce a usable hero asset.

Two backends:
  1. Meshy.ai v2 text-to-3D (preview mode) — needs MESHY_API_KEY env var.
  2. Hugging Face Space (stabilityai/stable-fast-3d) — needs gradio_client.

generate_ai_model(subject) tries Meshy first (higher quality), then HF.
Both backends cache outputs under assets/cache/models/ai_generated/ keyed
by sanitized prompt, so a repeat prompt reuses the prior file instantly.

Any failure — missing deps, missing key, network error, timeout — is
swallowed and None is returned so the caller can keep falling through.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

# Resolve project root from app/services/ai_generator.py -> up 3
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "assets" / "cache" / "models" / "ai_generated"

_MESHY_POLL_INTERVAL = 5
_MESHY_TIMEOUT_SEC = 120

# HuggingFace Space cascade — primary first, alternates if it's down or
# changes API. Each entry is (space_id, api_name) so we can override the
# endpoint per-space when one uses "/run" vs "/generate" vs default.
_HF_SPACE_ID = "stabilityai/stable-fast-3d"
_HF_SPACE_CASCADE: list[tuple[str, str]] = [
    ("stabilityai/stable-fast-3d", "/generate"),
    ("tencent/Hunyuan3D-2.0",      "/generate"),
    ("VAST-AI/TripoSR",            "/generate"),
    ("jiawei011/dreamgaussian",    "/generate"),
]

_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _cache_key(prompt: str) -> str:
    """Stable, filesystem-safe key derived from the prompt (trimmed to 60)."""
    key = _SANITIZE_RE.sub("_", (prompt or "").lower()).strip("_")
    return key[:60] or "unnamed"


def _cached_path(prompt: str, ext: str = "glb") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_cache_key(prompt)}.{ext}"


def _hf_extract_path(result) -> str | None:
    """Gradio predict returns a file path string, a dict, or a tuple of
    either — normalize to a single path string (or None)."""
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("path") or first.get("name")
    if isinstance(result, dict):
        return result.get("path") or result.get("name")
    return None


def _try_single_hf_space(space_id: str, api_name: str, prompt: str) -> Path | None:
    """Submit `prompt` to one HF Space and copy the result into the cache.
    Returns the cached path on success, or None on any failure (swallowed
    so the caller can try the next space in the cascade)."""
    try:
        from gradio_client import Client  # type: ignore
    except Exception as e:
        print(f"[AI-GEN/HF] gradio_client not installed: {e}", flush=True)
        return None

    cached = _cached_path(prompt, ext="glb")
    try:
        print(f"[AI-GEN/HF] submitting '{prompt}' to {space_id}{api_name}...", flush=True)
        client = Client(space_id)
        result = client.predict(prompt, api_name=api_name)
    except Exception as e:
        print(f"[AI-GEN/HF] {space_id} request failed: {e}", flush=True)
        return None

    candidate = _hf_extract_path(result)
    if not candidate:
        print(
            f"[AI-GEN/HF] {space_id} unexpected result shape: "
            f"{type(result).__name__}",
            flush=True,
        )
        return None

    src = Path(candidate)
    if not src.exists():
        print(f"[AI-GEN/HF] {space_id} returned non-existent path: {src}", flush=True)
        return None

    try:
        shutil.copy2(src, cached)
        print(
            f"[AI-GEN/HF] {space_id} -> cached as {cached.name} "
            f"({cached.stat().st_size} bytes)",
            flush=True,
        )
        return cached
    except Exception as e:
        print(f"[AI-GEN/HF] cache copy failed ({space_id}): {e}", flush=True)
        return None


def generate_via_huggingface(prompt: str) -> Path | None:
    """Text-to-3D via a HuggingFace Space using gradio_client. Tries each
    entry in _HF_SPACE_CASCADE in order; returns the first cached .glb, or
    None if every space fails."""
    if not prompt:
        return None

    cached = _cached_path(prompt, ext="glb")
    if cached.exists() and cached.stat().st_size > 0:
        return cached

    for space_id, api_name in _HF_SPACE_CASCADE:
        path = _try_single_hf_space(space_id, api_name, prompt)
        if path is not None:
            return path

    print(f"[AI-GEN/HF] all {len(_HF_SPACE_CASCADE)} spaces failed for '{prompt}'", flush=True)
    return None


def generate_via_meshy(prompt: str) -> Path | None:
    """Text-to-3D via Meshy.ai v2 (preview mode). Needs MESHY_API_KEY."""
    if not prompt:
        return None

    api_key = os.environ.get("MESHY_API_KEY")
    if not api_key:
        # Expected path when the user hasn't configured a key.
        return None

    cached = _cached_path(prompt, ext="glb")
    if cached.exists() and cached.stat().st_size > 0:
        return cached

    try:
        import requests  # type: ignore
    except Exception as e:
        print(f"[AI-GEN/MESHY] requests not available: {e}", flush=True)
        return None

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        print(f"[AI-GEN/MESHY] creating preview task for '{prompt}'...", flush=True)
        resp = requests.post(
            "https://api.meshy.ai/v2/text-to-3d",
            headers=headers,
            json={
                "mode": "preview",
                "prompt": prompt,
                "art_style": "realistic",
                "negative_prompt": "low quality, low poly",
            },
            timeout=30,
        )
        resp.raise_for_status()
        task_id = resp.json().get("result")
        if not task_id:
            print(f"[AI-GEN/MESHY] no task id returned: {resp.text[:200]}", flush=True)
            return None
    except Exception as e:
        print(f"[AI-GEN/MESHY] create task failed: {e}", flush=True)
        return None

    model_url: str | None = None
    elapsed = 0
    try:
        while elapsed < _MESHY_TIMEOUT_SEC:
            time.sleep(_MESHY_POLL_INTERVAL)
            elapsed += _MESHY_POLL_INTERVAL
            poll = requests.get(
                f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                headers=headers,
                timeout=30,
            )
            poll.raise_for_status()
            data = poll.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                urls = data.get("model_urls") or {}
                model_url = urls.get("glb") or urls.get("fbx")
                break
            if status in ("FAILED", "CANCELED", "EXPIRED"):
                print(f"[AI-GEN/MESHY] task {status}: {data.get('task_error')}", flush=True)
                return None
            print(f"[AI-GEN/MESHY] status={status} ({elapsed}s)", flush=True)
    except Exception as e:
        print(f"[AI-GEN/MESHY] poll failed: {e}", flush=True)
        return None

    if not model_url:
        print("[AI-GEN/MESHY] timed out waiting for SUCCEEDED", flush=True)
        return None

    try:
        dl = requests.get(model_url, timeout=120)
        dl.raise_for_status()
        cached.write_bytes(dl.content)
        print(f"[AI-GEN/MESHY] cached -> {cached.name} ({cached.stat().st_size} bytes)", flush=True)
        return cached
    except Exception as e:
        print(f"[AI-GEN/MESHY] download failed: {e}", flush=True)
        return None


def generate_ai_model(subject: str) -> dict | None:
    """Attempt Meshy first, then HuggingFace. Returns a fetcher-shaped dict
    on success, or None if both backends fail."""
    if not subject:
        return None

    path = generate_via_meshy(subject)
    source = "meshy"
    if path is None:
        path = generate_via_huggingface(subject)
        source = "huggingface"

    if path is None:
        return None

    return {
        "path": str(path),
        "name": subject,
        "source": source,
        "type": "glb",
        "generated": True,
    }
