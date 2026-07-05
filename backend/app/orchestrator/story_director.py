"""Phase 38 — Story Director: one prompt → a multi-scene FILM plan.

The video sibling of the game extractor: Ollama turns a story prompt into a
3-act beat sheet (establish → develop → resolve), each beat a self-contained
scene prompt the slot pipeline can render. Continuity is free: the composer's
asset cache re-uses the same generated actor for the same subject phrase, so
the hero stays the same hero across scenes.

Deterministic fallback (no Ollama): a 3-beat template built from the prompt,
so Story mode never hard-fails.
"""
from __future__ import annotations

import json
import re


_PLAN_SYS = """You are a film director. Break the user's story idea into %d short scenes
(a beat sheet: establish, develop, resolve). Reply with ONLY a JSON object:
{"title": "<film title, max 6 words>",
 "scenes": [{"title": "<2-4 words>",
             "prompt": "<one self-contained sentence describing WHO does WHAT WHERE,
                         naming the SAME main subject with the SAME words in every scene,
                         plus time-of-day/mood>",
             "duration_s": <3-6>}]}
Rules: name the subject with a SHORT PLAIN phrase (2-3 words, e.g. "a horse",
"a samurai") — no adjectives on the subject itself — and use that IDENTICAL
phrase in every scene (continuity AND asset-cache reuse: decorated phrases
force a full regeneration per film); each prompt must stand alone (the
renderer sees one scene at a time); vary camera-worthy action and mood across
scenes; no dialogue, no text overlays."""


def _fallback_plan(prompt: str, n_scenes: int) -> dict:
    subject = prompt.strip().rstrip(".")
    beats = [
        ("Opening", f"{subject}, wide establishing view, golden morning light"),
        ("The journey", f"{subject}, moving through the scene, dynamic action, midday"),
        ("Arrival", f"{subject}, arriving at a scenic landmark, warm sunset glow"),
        ("Nightfall", f"{subject}, quiet closing moment under a night sky"),
        ("Epilogue", f"{subject}, final wide farewell view, soft dawn light"),
    ]
    return {
        "title": (subject[:40] or "Untitled").title(),
        "scenes": [{"title": t, "prompt": p, "duration_s": 4}
                   for t, p in beats[:max(2, min(n_scenes, len(beats)))]],
        "planner": "fallback",
    }


def plan_story(prompt: str, n_scenes: int = 3, model: str | None = None,
               verbose: bool = False) -> dict:
    """Beat sheet for `prompt`. Never raises; falls back to the template plan."""
    n_scenes = max(2, min(int(n_scenes or 3), 5))
    try:
        from .llm import OllamaClient
        client = OllamaClient()
        msg = client.chat(
            [{"role": "system", "content": _PLAN_SYS % n_scenes},
             {"role": "user", "content": prompt}],
            model=model, temperature=0.4)
        content = (msg or {}).get("content", "")
        m = re.search(r"\{.*\}", content, re.DOTALL)
        plan = json.loads(m.group(0)) if m else {}
        scenes = plan.get("scenes") or []
        clean = []
        for s in scenes[:n_scenes]:
            p = str(s.get("prompt", "")).strip()
            if len(p) < 8:
                continue
            clean.append({
                "title": str(s.get("title", f"Scene {len(clean) + 1}"))[:40],
                "prompt": p[:500],
                "duration_s": max(2, min(int(s.get("duration_s", 4) or 4), 8)),
            })
        if len(clean) >= 2:
            out = {"title": str(plan.get("title", "Untitled"))[:60],
                   "scenes": clean, "planner": "ollama"}
            if verbose:
                print(f"[story] planned {len(clean)} scenes: "
                      f"{[s['title'] for s in clean]}")
            return out
    except Exception as e:
        if verbose:
            print(f"[story] Ollama plan failed ({type(e).__name__}: {e}) — fallback")
    return _fallback_plan(prompt, n_scenes)
