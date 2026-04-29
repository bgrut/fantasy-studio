"""
Credits / attribution generator for CC-licensed assets.

Reads a finished manifest (after the asset pipeline has populated
`resolved_assets`) and returns a structured credits payload:

    {
        "required": bool,           # True if any non-CC0 asset was used
        "text":     str,            # Copy-paste-ready attribution text
        "items":    list[dict],     # Per-asset structured entries
    }

Pure data — no Blender, no filesystem side effects. Safe to call from
the API layer after a render job completes.
"""
from __future__ import annotations

from typing import Any, Iterable


# Licenses that require no attribution.
_NO_ATTRIBUTION_LICENSES = {"", "cc0", "public domain", "public-domain", "cc-0"}


def _iter_assets(manifest: dict) -> Iterable[dict]:
    """Yield every asset dict from resolved_assets.models / hdris / sounds."""
    resolved = manifest.get("resolved_assets") or {}

    models = resolved.get("models")
    if isinstance(models, dict):
        for bucket in models.values():
            if isinstance(bucket, list):
                for asset in bucket:
                    if isinstance(asset, dict):
                        yield asset
    elif isinstance(models, list):
        for asset in models:
            if isinstance(asset, dict):
                yield asset

    for key in ("hdris", "sounds", "textures"):
        bucket = resolved.get(key)
        if isinstance(bucket, list):
            for asset in bucket:
                if isinstance(asset, dict):
                    yield asset


def _needs_attribution(license_value: Any) -> bool:
    if not license_value:
        return False
    return str(license_value).strip().lower() not in _NO_ATTRIBUTION_LICENSES


def generate_credits(manifest: dict) -> dict:
    """
    Build an attribution credits payload from `manifest`.

    Deduplicates by (name, author, source) so the same asset reused in
    several buckets appears only once in the credits text.
    """
    seen: set[tuple[str, str, str]] = set()
    items: list[dict] = []

    for asset in _iter_assets(manifest or {}):
        license_value = asset.get("license") or asset.get("license_id") or ""
        if not _needs_attribution(license_value):
            continue

        name = str(asset.get("name") or asset.get("title") or "Unknown").strip()
        author = str(
            asset.get("author")
            or asset.get("attribution")
            or asset.get("user", {}).get("displayName", "") if isinstance(asset.get("user"), dict) else asset.get("author") or "Unknown"
        ).strip() or "Unknown"
        source = str(
            asset.get("source_url")
            or asset.get("viewer_url")
            or asset.get("url")
            or ""
        ).strip()
        license_text = str(license_value).strip()

        key = (name.lower(), author.lower(), source.lower())
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "name":    name,
            "author":  author,
            "source":  source,
            "license": license_text,
        })

    if not items:
        return {
            "required": False,
            "text":     "No attribution required — all assets are CC0.",
            "items":    [],
        }

    lines = ["Assets used in this render:"]
    for c in items:
        lines.append(f'- "{c["name"]}" by {c["author"]} ({c["license"]})')
        if c["source"]:
            lines.append(f"  Source: {c['source']}")

    return {
        "required": True,
        "text":     "\n".join(lines),
        "items":    items,
    }
