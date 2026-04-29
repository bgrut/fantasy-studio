from __future__ import annotations

"""
asset_post_filter.py
====================
Post-filters the manifest produced by ``enrich_manifest_with_assets``.

Why a separate module?
----------------------
The upstream files ``asset_agent.py``, ``asset_fetcher.py``,
``asset_resolver.py``, and ``sketchfab_fetcher.py`` are STABLE and cannot
be modified. But the real-world output of those modules occasionally
contradicts the user's prompt — e.g. a "cat dancing" request resolves to
``cat_sleeping.glb`` because the sleeping-cat asset scored highest on the
generic "cat" query. At render time that's a silent failure: the user
asked for motion and got a nap.

This module runs AFTER the asset pipeline and BEFORE the manifest leaves
for Blender. It does two things:

1. **Pose-conflict rejection** — if the resolved hero's filename / title
   contains pose keywords that contradict the requested ``action``
   (sleeping vs dancing, dead vs running, static vs flying), the hero
   is cleared so templates fall through to a standing / generic match
   or, ultimately, the branded placeholder. Better to have a neutral
   standing cat than a sleeping one while we asked for "dancing".

2. **Asset sanity warnings** — emits structured log lines the frontend
   can surface in the Scene Breakdown panel.

Intentionally conservative: we only reject when the conflict is obvious.
False positives here mean the user sees a placeholder instead of a
slightly-wrong asset, which is worse UX than a slightly-wrong asset.
"""

from pathlib import Path


# Action categories — the requested action falls into one of these
# "motion families". An asset whose name is tagged with a pose from a
# DIFFERENT family than the requested action is considered a conflict.
_ACTION_FAMILIES: dict[str, set[str]] = {
    "dynamic": {
        "dance", "dancing", "run", "running", "jog", "jogging", "sprint",
        "sprinting", "walk", "walking", "gallop", "galloping", "fly",
        "flying", "soar", "soaring", "jump", "jumping", "leap", "leaping",
        "swim", "swimming", "fight", "fighting", "punch", "punching",
        "kick", "kicking", "wave", "waving", "play", "playing",
        "attacking", "charging", "chasing",
    },
    "static": {
        "idle", "stand", "standing", "sit", "sitting", "pose", "posed",
        "rest", "resting", "looking", "look",
    },
    "lying": {
        "sleep", "sleeping", "asleep", "nap", "napping", "lying",
        "laying", "prone", "dead", "corpse", "ragdoll", "unconscious",
        "knocked_out", "fallen", "down",
    },
}

# Reverse lookup: pose keyword -> family name.
_POSE_TO_FAMILY: dict[str, str] = {}
for _family, _poses in _ACTION_FAMILIES.items():
    for _p in _poses:
        _POSE_TO_FAMILY[_p] = _family

# Conflicts: if requested action is in FAMILY_A but asset is tagged with
# a pose from FAMILY_B, that's a conflict worth rejecting.
_CONFLICT_PAIRS: set[tuple[str, str]] = {
    ("dynamic", "lying"),   # "dancing" hero that's actually sleeping
    ("static",  "lying"),   # "standing" hero that's actually lying down
    ("dynamic", "static"),  # "running" hero that's an idle pose — softer conflict
}


def _classify_action(action: str) -> str | None:
    """Return the family of a requested action, or None if unknown."""
    if not action:
        return None
    token = action.strip().lower()
    return _POSE_TO_FAMILY.get(token)


def _extract_pose_tokens(text: str) -> list[str]:
    """Pull any pose keywords out of an asset filename / title / tag string."""
    if not text:
        return []
    lower = text.lower()
    hits: list[str] = []
    for pose in _POSE_TO_FAMILY:
        # Word-boundary-ish: match as a whole word or after _/-/space.
        for sep in ("_", "-", " ", "."):
            if f"{sep}{pose}" in lower or lower.startswith(f"{pose}{sep}") or lower == pose:
                hits.append(pose)
                break
        else:
            # Also catch "<pose>" as pure substring when the asset name
            # is something like "sleepingcat.glb" with no separators.
            if pose in lower and len(pose) >= 5:
                hits.append(pose)
    return hits


def _describe_asset(manifest: dict) -> str:
    """Concatenate the fields we can use to detect pose keywords.

    Includes filename stem AND parent directory names because Sketchfab
    downloads are usually ``<cache_root>/<asset_slug>/scene.glb`` — all
    the pose metadata lives in the folder, not the file.
    """
    fragments: list[str] = []

    def _path_fragments(raw: str) -> list[str]:
        try:
            p = Path(str(raw))
        except Exception:
            return []
        out = [p.stem]
        # Walk up to 3 parent directories so we catch patterns like
        # "models/sketchfab/cat_sleeping_stretched/scene.glb".
        cur = p
        for _ in range(3):
            cur = cur.parent
            if cur.name:
                out.append(cur.name)
            else:
                break
        return out

    hero_path = manifest.get("hero_asset_path") or ""
    if hero_path:
        fragments.extend(_path_fragments(hero_path))
    for key in ("hero_asset_name", "hero_asset_title", "hero_asset_slug"):
        v = manifest.get(key)
        if v:
            fragments.append(str(v))
    # Pull resolved_assets hero entries too.
    ra = manifest.get("resolved_assets") or {}
    models = ra.get("models") or {}
    if isinstance(models, dict):
        hero_list = models.get("hero") or []
        for item in hero_list:
            if isinstance(item, dict):
                for k in ("name", "title", "slug"):
                    if item.get(k):
                        fragments.append(str(item[k]))
                if item.get("path"):
                    fragments.extend(_path_fragments(item["path"]))
    return " ".join(fragments)


def _clear_hero(manifest: dict, reason: str) -> None:
    """Blank out the hero so templates fall through to placeholder."""
    manifest["hero_asset_path"] = None
    manifest["hero_asset_type"] = None
    manifest["hero_has_armature"] = False
    manifest["hero_has_animations"] = False
    # Stash the reason so the recipe / credits panel can surface why.
    warnings = manifest.setdefault("_post_filter_warnings", [])
    warnings.append(reason)
    print(f"[POST_FILTER] hero cleared — {reason}", flush=True)


def apply_asset_post_filters(manifest: dict) -> dict:
    """
    Run all post-asset sanity filters on an enriched manifest and return
    it. Always returns the manifest (never raises) — the filters are
    advisory, not gatekeeping.

    Current filters:
    - Pose-conflict rejection (sleeping cat vs dancing request, etc.)
    - Subject-mismatch rejection (robot request resolved to cat, etc.)
    """
    try:
        _subject_match_filter(manifest)
    except Exception as e:
        # Never let the filter crash the render.
        print(f"[POST_FILTER] subject_match_filter error (ignored): {e}", flush=True)
    try:
        _pose_conflict_filter(manifest)
    except Exception as e:
        # Never let the filter crash the render.
        print(f"[POST_FILTER] pose_conflict_filter error (ignored): {e}", flush=True)
    return manifest


# ═════════════════════════════════════════════════════════════════════════
# Subject-match filter
# =========================================================================
# The upstream resolver is stable code and occasionally returns an asset
# that has NOTHING to do with the user's requested subject — most commonly
# because the asset cache already has a loose-match (e.g. a single cat
# blend from an earlier render) that scores higher than the proper
# Sketchfab query on a weak string-match heuristic. Result: user asks
# for "robot walking in a city", render shows a sleeping cat.
#
# This filter rejects resolved heroes whose name/tags/metadata contain
# NO word related to the requested subject. When it rejects, it also
# strips the hero slot clean so the next layer (empty-scene guard) can
# install a procedural stand-in — much better UX than showing the user
# a completely wrong subject.
# ═════════════════════════════════════════════════════════════════════════

# Subject synonyms — a requested word satisfies the match if it OR any of
# these synonyms appears in the asset metadata blob. Kept intentionally
# short; adding new entries is safe.
_SUBJECT_SYNONYMS: dict[str, list[str]] = {
    "robot":   ["robot", "mech", "droid", "android", "cyborg", "mechanical", "bot"],
    "dog":     ["dog", "canine", "puppy", "retriever", "shepherd", "poodle",
                "husky", "shiba", "labrador", "bulldog", "hound"],
    "cat":     ["cat", "kitten", "feline", "tabby", "kitty"],
    "car":     ["car", "vehicle", "automobile", "ferrari", "sedan", "coupe",
                "sports_car", "sportscar", "lamborghini", "porsche", "bmw",
                "mustang", "corvette", "roadster"],
    "horse":   ["horse", "stallion", "mare", "pony", "equine"],
    "eagle":   ["eagle", "hawk", "bird_of_prey", "raptor", "falcon"],
    "bird":    ["bird", "avian", "parrot", "owl", "sparrow", "crow"],
    "dolphin": ["dolphin", "porpoise", "cetacean"],
    "whale":   ["whale", "humpback", "orca", "cetacean"],
    "tiger":   ["tiger", "big_cat"],
    "lion":    ["lion", "big_cat"],
    "shark":   ["shark", "great_white", "hammerhead"],
    "fish":    ["fish", "tuna", "salmon", "bass"],
    "dragon":  ["dragon", "wyvern", "drake", "serpent"],
    "monkey":  ["monkey", "ape", "chimp", "gorilla", "primate"],
    "chef":    ["chef", "cook", "man", "woman", "person", "human", "humanoid"],
    "ninja":   ["ninja", "warrior", "fighter", "assassin", "human", "humanoid"],
    "human":   ["human", "person", "man", "woman", "character", "humanoid"],
    "plane":   ["plane", "airplane", "jet", "aircraft"],
    "motorcycle": ["motorcycle", "bike", "motorbike"],
    "cheetah": ["cheetah", "big_cat", "feline"],
    "wolf":    ["wolf", "canine", "husky"],
    "bear":    ["bear", "grizzly", "polar_bear"],
    "fox":     ["fox", "vulpine"],
}

# Words too generic to require a subject match on — skip them when scanning
# the user's prompt for subject tokens.
_SUBJECT_STOPWORDS: set[str] = {
    "a", "an", "the", "in", "on", "at", "of", "with", "and", "or", "to",
    "is", "are", "was", "were", "it", "its", "this", "that", "for", "by",
    "over", "under", "through", "across", "into", "onto", "scene", "video",
    "shot", "render", "frame", "small", "large", "big", "tiny", "some",
    "my", "our", "your",
}


def _is_subject_word(tok: str) -> bool:
    """A token counts as a 'subject word' if it's a canonical entry in
    ``_SUBJECT_SYNONYMS`` or a synonym of one — i.e. we recognise it as
    naming an animal / character / vehicle / object. This excludes
    environment/location words like 'stadium', 'neon', 'city' and action
    words like 'walking', 'dancing'."""
    if not tok:
        return False
    if tok in _SUBJECT_SYNONYMS:
        return True
    for group in _SUBJECT_SYNONYMS.values():
        if tok in group:
            return True
    return False


def _resolve_subject_tokens(manifest: dict) -> list[str]:
    """
    Pull the "what is the subject" tokens out of the manifest — the hero,
    NOT the environment or action. The filter must match 'monkey' against
    the hero blob, not 'baseball' or 'stadium' (those describe the scene
    around the hero, not the hero itself).

    Precedence:
      1. Explicit subject fields on the manifest / scene_plan / recipe.
         We take these tokens verbatim — the director is authoritative
         about what the hero is. If the director puts 'monkey dancing'
         there we check both words against the asset and that's fine.
      2. Fallback to scanning topic/prompt, BUT only keep tokens we
         recognise as subject words (canonical entries or synonyms in
         _SUBJECT_SYNONYMS). This drops 'baseball'/'stadium'/'neon'/
         'city' and similar environment nouns that caused valid heroes
         to be rejected by the post-filter.
    """
    tokens: list[str] = []

    # ── 1. Authoritative subject fields ────────────────────────────────
    for key in ("subject", "hero_subject"):
        v = manifest.get(key)
        if v:
            tokens.extend(str(v).lower().split())
    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    if isinstance(scene_plan, dict):
        for key in ("subject", "hero_subject", "character_species"):
            v = scene_plan.get(key)
            if v:
                tokens.extend(str(v).lower().split())
    recipe = manifest.get("scene_recipe") or {}
    hero = (recipe.get("hero") or {}) if isinstance(recipe, dict) else {}
    if isinstance(hero, dict):
        for key in ("subject", "species", "type"):
            v = hero.get(key)
            if v:
                tokens.extend(str(v).lower().split())

    # ── 2. Prompt/topic fallback — SUBJECT WORDS ONLY ──────────────────
    # The old fallback tokenized the full prompt, which meant the filter
    # would reject a perfectly good 'Simio Monkey' asset for 'monkey in
    # a baseball stadium' because 'baseball' and 'stadium' weren't in the
    # monkey's metadata. Now we only harvest words we recognise as
    # subjects, so environment nouns are ignored.
    if not tokens:
        for key in ("topic", "prompt", "user_prompt"):
            v = manifest.get(key)
            if not v:
                continue
            for raw in str(v).lower().split():
                tt = raw.strip(".,!?;:'\"()[]{}-_/")
                if _is_subject_word(tt):
                    tokens.append(tt)

    # De-dupe + strip stopwords + clean punctuation. On the authoritative
    # path we keep every token (monkey + dancing is fine). On the prompt
    # fallback path _is_subject_word already filtered noise.
    cleaned: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        tt = t.strip(".,!?;:'\"()[]{}-_/")
        if not tt or tt in _SUBJECT_STOPWORDS or len(tt) < 3:
            continue
        if tt in seen:
            continue
        seen.add(tt)
        cleaned.append(tt)
    return cleaned


def _subject_match_terms(tokens: list[str]) -> list[str]:
    """
    Expand subject tokens with their synonym lists. Returns the union of
    raw tokens + any synonym-group members for tokens we recognize.
    """
    terms: set[str] = set()
    for t in tokens:
        terms.add(t)
        syns = _SUBJECT_SYNONYMS.get(t)
        if syns:
            terms.update(syns)
        # Also check if the token IS a synonym of some canonical subject.
        for canonical, group in _SUBJECT_SYNONYMS.items():
            if t in group:
                terms.add(canonical)
                terms.update(group)
    return sorted(terms)


def _asset_text_blob(manifest: dict) -> str:
    """
    Concatenate every string we can reach that describes the resolved
    hero asset. Includes filename (stem + 3 parent dirs), explicit
    name/title/slug fields, species, tags, and keywords.
    """
    fragments: list[str] = []
    hero_path = manifest.get("hero_asset_path") or ""
    if hero_path:
        try:
            p = Path(str(hero_path))
            fragments.append(p.stem)
            cur = p
            for _ in range(3):
                cur = cur.parent
                if cur.name:
                    fragments.append(cur.name)
                else:
                    break
        except Exception:
            pass
    for key in (
        "hero_asset_name", "hero_asset_title", "hero_asset_slug",
        "hero_asset_species", "hero_subject", "hero_asset_id",
    ):
        v = manifest.get(key)
        if v:
            fragments.append(str(v))
    ra = manifest.get("resolved_assets") or {}
    models = ra.get("models") or {}
    if isinstance(models, dict):
        hero_list = models.get("hero") or []
        for item in hero_list:
            if not isinstance(item, dict):
                continue
            for k in ("name", "title", "slug", "species", "id", "query"):
                if item.get(k):
                    fragments.append(str(item[k]))
            if item.get("tags"):
                try:
                    fragments.extend(str(x) for x in item["tags"])
                except Exception:
                    pass
            if item.get("keywords"):
                try:
                    fragments.extend(str(x) for x in item["keywords"])
                except Exception:
                    pass
            if item.get("path"):
                try:
                    p = Path(str(item["path"]))
                    fragments.append(p.stem)
                    cur = p
                    for _ in range(3):
                        cur = cur.parent
                        if cur.name:
                            fragments.append(cur.name)
                        else:
                            break
                except Exception:
                    pass
    return " ".join(fragments).lower()


# Sources that run their own semantic validation before producing a
# record. When a hero came from one of these and has a positive score,
# the subject-match filter trusts it instead of re-checking with a
# less-informed keyword scan — Objaverse uses GPT-4 captions, the
# curated/registry layers are hand-validated, and the local registry
# is small enough to be ground truth.
_TRUSTED_HERO_SOURCES: set[str] = {
    "objaverse",
    "curated",
    "tested_curated",
    "local_registry",
    "registry",
    "local",
}


def _find_hero_source_record(manifest: dict) -> dict | None:
    """Locate the model dict in resolved_assets whose path matches the
    manifest's hero_asset_path. Scans every bucket (hero, characters,
    vehicles, environments, props, etc.), since Objaverse records are
    currently bucketed under 'characters' rather than 'hero' but still
    represent the scene's hero asset."""
    hero_path = manifest.get("hero_asset_path") or ""
    if not hero_path:
        return None
    ra = manifest.get("resolved_assets") or {}
    raw_models = ra.get("models")

    candidates: list[dict] = []
    if isinstance(raw_models, dict):
        for bucket_list in raw_models.values():
            if isinstance(bucket_list, list):
                candidates.extend(m for m in bucket_list if isinstance(m, dict))
    elif isinstance(raw_models, list):
        candidates.extend(m for m in raw_models if isinstance(m, dict))

    target = str(hero_path).replace("\\", "/").lower()
    for m in candidates:
        p = str(m.get("path") or m.get("local_path") or "").replace("\\", "/").lower()
        if p and p == target:
            return m
    return None


def _subject_match_filter(manifest: dict) -> None:
    """
    TEMPORARILY DISABLED — pass-through only.

    This filter was rejecting valid heroes because it cross-checked
    every prompt word (including environment nouns like "stadium",
    "city", "ocean") against the hero's metadata blob. Result: a
    correctly-resolved "Simio Monkey" asset would be cleared because
    "baseball" and "stadium" weren't in the monkey's metadata, every
    dynamic hero silently vanished, and every render came out empty.

    Until we ship a version that matches ONLY the subject tokens
    (not the full prompt), we log what WOULD have been checked and
    leave the hero in place. Force-scale + force-camera safety nets
    downstream will handle visibility.

    DO NOT restore the old rejection logic without first verifying
    against the test matrix: monkey-in-stadium, robot-in-city,
    dolphin-jumping, pelican-on-rock.
    """
    hero_path = manifest.get("hero_asset_path", "")
    if not hero_path:
        return  # nothing to log — no hero resolved upstream

    # Try to fish out a human-readable hero name for the log line so
    # operators can spot what was allowed through.
    hero_name = ""
    try:
        models = (manifest.get("resolved_assets") or {}).get("models") or {}
        target = str(hero_path).replace("\\", "/").lower()
        for bucket in models.values():
            if not isinstance(bucket, list):
                continue
            for record in bucket:
                if not isinstance(record, dict):
                    continue
                rp = str(record.get("path") or "").replace("\\", "/").lower()
                if rp and rp == target:
                    hero_name = str(record.get("name") or "")
                    break
            if hero_name:
                break
    except Exception:  # pragma: no cover - defensive
        pass

    print(
        f"[POST_FILTER] PASS-THROUGH: hero={hero_name!r} path={hero_path!r}",
        flush=True,
    )
    return


def _scan_motion_verbs_in_prompt(manifest: dict) -> str | None:
    """
    Last-resort action inference — scan the raw user prompt / topic for
    motion verbs. Catches "cat dancing on a rooftop" where the action
    field was parsed as "on a rooftop" and the real verb is hiding in the
    prompt body.
    """
    candidates = []
    for key in ("topic", "prompt", "user_prompt"):
        v = manifest.get(key)
        if v:
            candidates.append(str(v))
    # Also look inside animation_instructions[*].action if action itself was empty.
    ai = manifest.get("animation_instructions") or []
    for item in ai:
        if isinstance(item, dict):
            for k in ("action", "mode", "subject", "notes"):
                v = item.get(k)
                if v:
                    candidates.append(str(v))
    blob = " ".join(candidates).lower()
    if not blob.strip():
        return None
    # Look for any pose token as a whole word; prefer dynamic motions
    # over static ones so "dancing on a rooftop" scores dancing, not
    # "on"/"a".
    for family in ("dynamic", "lying", "static"):
        for pose in _ACTION_FAMILIES[family]:
            if len(pose) < 4:
                continue
            for sep in (" ", "_", "-", ",", ".", "!"):
                if f"{sep}{pose}" in blob or blob.startswith(f"{pose}{sep}"):
                    return pose
            # Substring fallback for glued phrases.
            if pose in blob:
                return pose
    return None


def _pose_conflict_filter(manifest: dict) -> None:
    """
    TEMPORARILY DISABLED — pass-through only.

    Part of the "strip back to fundamentals" pass: during the launch
    push we do NOT clear heroes for any reason. A slightly-wrong pose
    (sleeping cat for a dancing request) is still dramatically better
    than an empty frame while we verify the rest of the pipeline.

    Re-enable only after the force-scale / force-camera nets in
    render_from_manifest.py are proven and the subject_match filter
    is restored in a safe form.
    """
    return
