#!/usr/bin/env python3
"""
curate_asset.py
===============
Round 11: one-shot curation driver. Takes a Sketchfab URL / UID (or a
local file path), downloads + probes + normalises the model in headless
Blender, writes the cleaned GLB into
``assets/curated/<category>/<slug>/scene.glb`` along with a
``metadata.json``, and appends the entry to
``assets/curated/catalog.json``.

Usage
-----
    # From a Sketchfab URL (requires SKETCHFAB_API_TOKEN in env)
    python tools/curate_asset.py \\
        --url "https://sketchfab.com/3d-models/golden-retriever-xxxxx" \\
        --category animal \\
        --subcategory dog \\
        --keywords "dog,puppy,retriever,golden,pet" \\
        --name "Golden Retriever" \\
        --animations "idle=Idle,walk=Walk,run=Run"

    # From a local file (already downloaded by hand)
    python tools/curate_asset.py \\
        --file path/to/model.glb \\
        --category animal \\
        --subcategory dog \\
        --keywords "dog,puppy"

    # Force re-probe of an already-curated asset
    python tools/curate_asset.py --re-curate <asset_id>

Requires
--------
    BLENDER_EXE              path to Blender executable (e.g.
                             "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe").
    SKETCHFAB_API_TOKEN     when --url is used.

The curation script never renders — it just downloads, inspects,
normalises, and catalogs. Use the regular ``/api/render-jobs`` pipeline
to verify the asset looks good in an actual scene.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# The curation CLI lives in tools/ which sits next to app/. Add the
# backend project root to sys.path so we can import the Sketchfab
# fetcher directly rather than reimplementing download logic.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.services.sketchfab_fetcher import (  # noqa: E402
    _download_url,
    _stream_to_file,
    _extract_archive,
    is_available as sketchfab_available,
    search_models,
    is_relevant_to_subject,
    _score_model,
)


_CURATED_ROOT = _PROJECT_ROOT / "assets" / "curated"
_CATALOG_PATH = _CURATED_ROOT / "catalog.json"


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Curate a 3D asset into the library")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Sketchfab model URL or UID")
    src.add_argument("--file", help="Local path to .glb / .gltf / .fbx")
    src.add_argument("--re-curate", help="Re-probe an existing catalog entry by id")
    src.add_argument("--search",
                     help="Search Sketchfab and auto-pick the best match for the given query")
    p.add_argument("--animated", action="store_true",
                   help="With --search: prefer animated/rigged models")
    p.add_argument("--max-candidates", type=int, default=12,
                   help="With --search: how many Sketchfab results to score before picking (default 12)")

    p.add_argument("--category", choices=[
        "animal", "vehicle", "character", "environment", "prop",
    ], help="Top-level category")
    p.add_argument("--subcategory", default="", help="Subcategory (e.g. dog)")
    p.add_argument("--keywords", default="", help="Comma-separated keywords")
    p.add_argument("--name", default="", help="Human-readable display name")
    p.add_argument("--animations", default="",
                   help="Comma-separated mapping of action→clip, e.g. 'idle=Idle,walk=Walk'")
    p.add_argument("--license", default="cc-by", help="License slug")
    p.add_argument("--author", default="", help="Original author credit")
    p.add_argument("--target-height", type=float, default=None,
                   help="Normalise bounding height (meters). Defaults to category-specific preset.")
    p.add_argument("--no-normalize", action="store_true",
                   help="Skip scale/origin normalisation")
    p.add_argument("--id", default="",
                   help="Override the generated asset id")

    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_SKETCHFAB_UID_RE = re.compile(r"([a-f0-9]{32})", re.IGNORECASE)


def _extract_uid(url_or_uid: str) -> str | None:
    if not url_or_uid:
        return None
    m = _SKETCHFAB_UID_RE.search(url_or_uid)
    return m.group(1).lower() if m else None


def _slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return s or "asset"


_DEFAULT_TARGET_HEIGHTS = {
    "animal":      1.0,
    "vehicle":     1.6,
    "character":   1.8,
    "prop":        0.6,
    "environment": None,  # don't rescale environments
}


def _resolve_target_height(category: str, override: float | None) -> float | None:
    if override is not None:
        return override
    return _DEFAULT_TARGET_HEIGHTS.get(category, 1.0)


def _blender_exe() -> str:
    # Priority: explicit env var, then a few common install paths.
    exe = os.environ.get("BLENDER_EXE", "").strip()
    if exe and Path(exe).exists():
        return exe
    candidates = [
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/usr/bin/blender",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise RuntimeError(
        "Blender executable not found. Set BLENDER_EXE env var or install "
        "Blender at one of the default paths."
    )


def _probe_script() -> Path:
    return Path(__file__).resolve().parent / "_blender_probe.py"


# ═══════════════════════════════════════════════════════════════════════════
# Sketchfab download
# ═══════════════════════════════════════════════════════════════════════════

def _download_from_sketchfab(url_or_uid: str, dest_dir: Path) -> Path | None:
    uid = _extract_uid(url_or_uid)
    if not uid:
        raise RuntimeError(
            f"Could not extract a 32-char UID from {url_or_uid!r}. "
            f"Paste the full Sketchfab model URL."
        )
    if not sketchfab_available():
        raise RuntimeError(
            "SKETCHFAB_API_TOKEN is not set — cannot download curated "
            "assets from Sketchfab. Download the model by hand and use "
            "--file instead."
        )

    print(f"[CURATE] fetching download URL for uid={uid} ...", flush=True)
    dl_info = _download_url(uid)
    if not dl_info:
        raise RuntimeError(f"Sketchfab /models/{uid}/download returned nothing")

    archive_url = (dl_info.get("gltf") or {}).get("url") or (dl_info.get("source") or {}).get("url")
    if not archive_url:
        raise RuntimeError("Sketchfab download response did not include a glTF URL")

    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / "archive.zip"
    print(f"[CURATE] downloading archive -> {archive_path}", flush=True)
    if not _stream_to_file(archive_url, archive_path):
        raise RuntimeError("Sketchfab archive download failed")

    extracted = _extract_archive(archive_path, dest_dir)
    if not extracted:
        raise RuntimeError("Extracted archive did not contain a usable 3D file")
    # Clean up the zip now we have the extracted contents.
    try:
        if archive_path.exists() and archive_path.resolve() != Path(extracted).resolve():
            archive_path.unlink()
    except OSError:
        pass
    return Path(extracted)


# ═══════════════════════════════════════════════════════════════════════════
# Sketchfab auto-search (powers --search and the auto-curation API)
# ═══════════════════════════════════════════════════════════════════════════

def _pick_best_from_search(
    query: str,
    *,
    animated: bool = False,
    max_candidates: int = 12,
) -> dict | None:
    """
    Run a Sketchfab search for ``query``, filter for relevance, and return
    the highest-scoring downloadable result (or None on miss).
    """
    if not sketchfab_available():
        raise RuntimeError(
            "SKETCHFAB_API_TOKEN is not set — cannot search Sketchfab."
        )
    print(f"[CURATE] searching Sketchfab for {query!r} (animated={animated}) ...",
          flush=True)
    results = search_models(
        query=query,
        limit=max_candidates,
        animated=True if animated else None,
    )

    if not results:
        print(f"[CURATE] Sketchfab returned 0 hits for {query!r}", flush=True)
        return None

    # Relevance gate first — drops Halloween costumes when query is "dog".
    relevant = [r for r in results if is_relevant_to_subject(r, query)]
    if not relevant:
        print(f"[CURATE] no relevant matches after subject gate "
              f"({len(results)} raw hits)", flush=True)
        return None

    scored = []
    for r in relevant:
        try:
            score = _score_model(query, r, want_animated=animated)
        except Exception:
            score = 0
        scored.append((score, r))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]
    print(
        f"[CURATE] best match: {best.get('name')!r} "
        f"uid={best.get('uid')} score={best_score} "
        f"(of {len(relevant)} relevant / {len(results)} total)",
        flush=True,
    )
    return best


def _resolve_search_uid(args: argparse.Namespace) -> tuple[str, str]:
    """
    For --search mode, returns (sketchfab_url, uid) of the chosen model
    so the rest of the pipeline can treat it as if --url was passed.
    """
    best = _pick_best_from_search(
        args.search,
        animated=bool(args.animated),
        max_candidates=int(args.max_candidates or 12),
    )
    if not best:
        raise RuntimeError(
            f"No suitable Sketchfab model found for {args.search!r}. "
            f"Try a different query or --animated=False."
        )
    uid = best.get("uid") or _extract_uid(best.get("viewerUrl") or "")
    if not uid:
        raise RuntimeError("Sketchfab result missing a UID")
    url = best.get("viewerUrl") or f"https://sketchfab.com/3d-models/{uid}"
    # If the user didn't supply --name, take it from the search hit.
    if not args.name and best.get("name"):
        args.name = str(best["name"])
    if not args.keywords and best.get("name"):
        # Seed keywords from query + model name words.
        seed = f"{args.search},{best['name']}"
        args.keywords = ",".join({w.strip().lower() for w in seed.replace(",", " ").split() if w.strip()})
    return url, uid


# ═══════════════════════════════════════════════════════════════════════════
# Catalog I/O
# ═══════════════════════════════════════════════════════════════════════════

def _load_catalog() -> dict:
    if not _CATALOG_PATH.exists():
        return {"version": 1, "assets": []}
    try:
        raw = _CATALOG_PATH.read_text(encoding="utf-8-sig")
        data = json.loads(raw) if raw.strip() else {"version": 1, "assets": []}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[CURATE] catalog load failed ({e}); starting fresh", flush=True)
        return {"version": 1, "assets": []}
    if not isinstance(data, dict):
        return {"version": 1, "assets": []}
    data.setdefault("version", 1)
    data.setdefault("assets", [])
    return data


def _save_catalog(catalog: dict) -> None:
    catalog["generated_at"] = datetime.utcnow().isoformat() + "Z"
    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CATALOG_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _upsert_asset(catalog: dict, entry: dict) -> None:
    assets = catalog.setdefault("assets", [])
    for i, existing in enumerate(assets):
        if isinstance(existing, dict) and existing.get("id") == entry.get("id"):
            assets[i] = entry
            return
    assets.append(entry)


# ═══════════════════════════════════════════════════════════════════════════
# Animation map parsing
# ═══════════════════════════════════════════════════════════════════════════

def _parse_animations(spec: str, report: dict) -> dict:
    """
    ``spec`` looks like "idle=Idle_01,walk=WalkForward,run=Run". Returns
    a dict of the same shape the curated metadata expects. Action names
    that don't appear in the probed action list emit a warning but are
    still recorded — the user may have a typo they want to keep.
    """
    out: dict = {}
    if not spec:
        return out
    known_actions: set[str] = set()
    for arm in report.get("armatures") or []:
        for name in arm.get("actions") or []:
            known_actions.add(name)

    for pair in spec.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        action_key, clip_name = [p.strip() for p in pair.split("=", 1)]
        if action_key and clip_name:
            out[action_key] = {"action_name": clip_name, "description": ""}
            if known_actions and clip_name not in known_actions:
                print(
                    f"[CURATE] WARNING: animation clip {clip_name!r} for "
                    f"action {action_key!r} not found in the armature. "
                    f"Known actions: {sorted(known_actions)[:8]}...",
                    flush=True,
                )
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════

def _run_probe(
    input_path: Path,
    report_path: Path,
    export_path: Path | None,
    target_height: float | None,
    normalize: bool,
) -> dict:
    cmd = [
        _blender_exe(),
        "-b",
        "--python",
        str(_probe_script()),
        "--",
        "--input", str(input_path),
        "--report", str(report_path),
    ]
    if export_path is not None:
        cmd += ["--export", str(export_path)]
    if target_height is not None:
        cmd += ["--target-height", str(target_height)]
    if not normalize:
        cmd += ["--no-normalize"]

    print(f"[CURATE] running Blender probe:\n  {' '.join(cmd)}", flush=True)
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        print("--- Blender stdout ---", flush=True)
        print(proc.stdout, flush=True)
        print("--- Blender stderr ---", flush=True)
        print(proc.stderr, flush=True)
        raise RuntimeError(f"Blender probe exited with code {proc.returncode}")

    if not report_path.exists():
        raise RuntimeError(f"Probe report missing: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8-sig"))


def _build_metadata(args: argparse.Namespace, report: dict, out_glb: Path,
                    source_url: str, source_uid: str | None) -> dict:
    keywords = [k.strip().lower() for k in (args.keywords or "").split(",") if k.strip()]
    if args.subcategory:
        keywords = list(dict.fromkeys([args.subcategory.lower(), *keywords]))

    animations = _parse_animations(args.animations, report)

    final_bbox = report.get("final_bbox") or report.get("raw_bbox") or {}
    # ``path`` is stored relative to project root so the catalog is
    # portable across machines.
    rel_path = out_glb.relative_to(_PROJECT_ROOT).as_posix()

    asset_id = args.id.strip() or _slugify(
        f"{args.category}_{args.subcategory or args.name or source_uid or out_glb.stem}"
    )

    metadata = {
        "id":            asset_id,
        "name":          args.name or asset_id.replace("_", " ").title(),
        "path":          rel_path,
        "category":      args.category,
        "subcategory":   args.subcategory or None,
        "keywords":      keywords,
        "has_armature":  bool(report.get("has_armature")),
        "animations":    animations,
        "scale_normalized": bool(report.get("normalize", {}).get("centered")) if not args.no_normalize else False,
        "forward_axis":  report.get("forward_axis", "Y"),
        "ground_contact_z": 0.0,
        "bounding_box": {
            "width":  final_bbox.get("width", 0.0),
            "depth":  final_bbox.get("depth", 0.0),
            "height": final_bbox.get("height", 0.0),
        },
        "recommended_camera_distance": _recommend_camera_distance(final_bbox),
        "recommended_lens_mm": _recommend_lens(args.category),
        "face_count":    report.get("face_count", 0),
        "material_count": report.get("material_count", 0),
        "texture_count": report.get("texture_count", 0),
        "source":        "sketchfab" if source_uid else "local",
        "source_url":    source_url,
        "source_uid":    source_uid,
        "license":       args.license,
        "author":        args.author,
        "tested":        True,
        "test_date":     datetime.utcnow().strftime("%Y-%m-%d"),
    }
    return metadata


def _recommend_camera_distance(bbox: dict) -> float:
    max_dim = max(
        float(bbox.get("width", 0.0)),
        float(bbox.get("depth", 0.0)),
        float(bbox.get("height", 0.0)),
        0.5,
    )
    return round(max_dim * 2.6, 2)


def _recommend_lens(category: str) -> int:
    return {
        "animal":      50,
        "character":   50,
        "vehicle":     35,
        "prop":        65,
        "environment": 28,
    }.get(category, 50)


def main() -> int:
    args = _parse_args()

    if args.re_curate:
        print("[CURATE] --re-curate is not yet implemented. Delete the "
              "catalog entry and re-run with --url or --file.", flush=True)
        return 2

    if not args.category:
        print("ERROR: --category is required (animal|vehicle|character|environment|prop)",
              flush=True)
        return 2

    # Prepare the target folder under assets/curated/<category>/<slug>/
    slug = _slugify(args.id or args.subcategory or args.name or "asset")
    target_dir = _CURATED_ROOT / args.category / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    source_url = ""
    source_uid = None
    if args.search:
        try:
            source_url, source_uid = _resolve_search_uid(args)
        except Exception as e:
            print(f"ERROR: Sketchfab search failed: {e}", flush=True)
            return 6
        # Re-derive slug now that we may have learned a name from the search hit.
        slug = _slugify(args.id or args.subcategory or args.name or "asset")
        target_dir = _CURATED_ROOT / args.category / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        staged = _download_from_sketchfab(source_url, target_dir / "_staging")
        input_path = Path(staged)
    elif args.url:
        source_url = args.url
        source_uid = _extract_uid(args.url)
        staged = _download_from_sketchfab(args.url, target_dir / "_staging")
        input_path = Path(staged)
    else:
        input_path = Path(args.file).resolve()
        if not input_path.exists():
            print(f"ERROR: local file not found: {input_path}", flush=True)
            return 3

    out_glb = target_dir / "scene.glb"
    report_path = target_dir / "_probe_report.json"
    target_height = _resolve_target_height(args.category, args.target_height)
    normalize = not args.no_normalize

    try:
        report = _run_probe(
            input_path=input_path,
            report_path=report_path,
            export_path=out_glb,
            target_height=target_height,
            normalize=normalize,
        )
    except Exception as e:
        print(f"ERROR: probe failed: {e}", flush=True)
        return 4

    if not report.get("ok"):
        print(f"ERROR: probe report says failure: {report.get('error')}", flush=True)
        return 5

    metadata = _build_metadata(
        args, report, out_glb, source_url=source_url, source_uid=source_uid,
    )
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Catalog update
    catalog = _load_catalog()
    _upsert_asset(catalog, metadata)
    _save_catalog(catalog)

    print("\n" + "=" * 72)
    print(f"[CURATE] asset curated: {metadata['id']}")
    print(f"  path:       {metadata['path']}")
    print(f"  armature:   {metadata['has_armature']} "
          f"(actions: {sum(len(a.get('actions') or []) for a in report.get('armatures', []))})")
    print(f"  bbox:       {metadata['bounding_box']}")
    print(f"  face_count: {metadata['face_count']}")
    print(f"  animations: {list(metadata['animations'].keys())}")
    print(f"  catalog:    {_CATALOG_PATH}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
