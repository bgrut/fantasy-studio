#!/usr/bin/env python3
"""
ingest_assets.py
================
Bulk-ingest pipeline for hand-sourced assets.

Workflow:
    1. Drop files into assets/inbox/{category}/.
       Categories: cats/, dogs/, horses/, animals/, vehicles/, hdris/, props/
       Or generic: characters/, environments/.
    2. Optional .json sidecar next to a .blend/.glb overrides auto-parsed metadata.
    3. Run: python scripts/ingest_assets.py --tier tested
    4. Files are copied to assets/cache/models/{category}/ (or assets/hdris/)
       and an entry is added to app/data/library.json.
    5. Processed source files are moved to assets/inbox/_processed/{timestamp}/.

Usage:
    python scripts/ingest_assets.py --tier tested
    python scripts/ingest_assets.py --tier unverified   # mark as review-pending
    python scripts/ingest_assets.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "assets" / "inbox"
PROCESSED_BASE = INBOX / "_processed"
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
MODELS_ROOT = ROOT / "assets" / "cache" / "models"
HDRI_ROOT = ROOT / "assets" / "hdris"

_BRAND_TOKENS = {
    "porsche", "ferrari", "bmw", "toyota", "ford", "chevrolet", "mercedes",
    "audi", "lamborghini", "bugatti", "mclaren", "aston", "nissan", "honda",
    "mazda", "subaru", "lotus", "tesla", "dodge", "chrysler", "kia", "hyundai",
    "volkswagen", "vw", "jaguar", "bentley", "rolls", "royce", "pagani",
    "koenigsegg",
}

# Compound brand tokens — recognised as a pair in filenames like
# aston_martin_db11 or rolls_royce_ghost.  The ingest collapses these
# back into a single brand value.
_COMPOUND_BRANDS = {
    ("aston", "martin"):  "aston_martin",
    ("rolls", "royce"):   "rolls_royce",
    ("alfa", "romeo"):    "alfa_romeo",
    ("land", "rover"):    "land_rover",
}
_MODEL_TOKENS = {
    "911", "718", "gt3", "gt", "rs", "m3", "m4", "m5", "camry", "corolla",
    "supra", "miata", "civic", "accord", "mustang", "corvette", "camaro",
    "challenger", "huracan", "aventador", "chiron", "veyron", "720s", "p1",
    "senna", "vantage", "cayman", "taycan", "panamera", "cayenne", "macan",
    "f40", "f50", "enzo", "488", "812",
}
_VARIANT_TOKENS = {"gt3", "rs", "turbo", "s", "gts", "r", "base"}

_COLOR_TOKENS = {
    "orange", "black", "white", "red", "blue", "green", "yellow", "brown",
    "grey", "gray", "silver", "golden", "tabby", "ginger", "calico",
    "striped", "spotted",
}
_BEHAVIOR_TOKENS = {
    "walking", "running", "sitting", "standing", "sleeping", "flying",
    "swimming", "jumping", "lying", "resting", "playing",
}
_STYLE_TOKENS = {
    "realistic", "cartoon", "stylized", "low_poly", "lowpoly", "anime",
    "photoreal", "detailed",
}

_FOLDER_CATEGORY_MAP = {
    "cats":         ("character", ["cat", "feline", "animal", "pet", "mammal"], "small", "cat"),
    "dogs":         ("character", ["dog", "canine", "animal", "pet", "mammal"], "small", "dog"),
    "horses":       ("character", ["horse", "equine", "animal", "mammal"], "medium", "horse"),
    "birds":        ("character", ["bird", "animal"], "small", "bird"),
    "animals":      ("character", ["animal"], "medium", None),
    "characters":   ("character", ["character"], "medium", None),
    "creatures":    ("character", ["creature", "animal"], "medium", None),
    "humans":       ("character", ["character", "human", "humanoid"], "medium", "human"),
    "robots":       ("character", ["robot", "character", "mechanical"], "medium", "robot"),
    "vehicles":     ("vehicle",   ["car", "vehicle"], "medium", None),
    "cars":         ("vehicle",   ["car", "vehicle"], "medium", None),
    "trucks":       ("vehicle",   ["truck", "vehicle"], "medium", "truck"),
    "motorcycles":  ("vehicle",   ["motorcycle", "vehicle"], "medium", "motorcycle"),
    "props":        ("prop",      ["prop"], "small", None),
    "products":     ("prop",      ["product", "prop"], "small", None),
    "environments": ("environment", ["environment"], "large", None),
    "buildings":    ("environment", ["building", "environment"], "large", "building"),
    "hdris":        ("hdri",      ["hdri"], "", "hdri"),
}

# Known subject nouns — winners over descriptors/behaviors/brands when
# present in the filename.  The world-dev biome system also consumes
# these as biome_hints (e.g. subject='canyon' → biome_hints=['canyon',
# 'desert', 'outdoor']).
_SUBJECT_NOUNS = {
    # animals — mammals
    "cat", "dog", "horse", "cow", "pig", "sheep", "goat", "rabbit", "fox",
    "wolf", "bear", "deer", "lion", "tiger", "cheetah", "leopard", "panther",
    "elephant", "rhino", "rhinoceros", "hippo", "hippopotamus", "giraffe",
    "zebra", "buffalo", "bison", "hyena", "otter", "beaver", "squirrel",
    "raccoon", "skunk", "kangaroo", "panda", "koala", "monkey", "gorilla",
    "chimpanzee", "chimp", "ape", "mouse", "rat", "hamster",
    "whale", "dolphin", "shark", "seal", "walrus",
    # animals — birds
    "eagle", "hawk", "falcon", "owl", "raven", "crow", "parrot", "flamingo",
    "penguin", "rooster", "chicken", "duck", "goose", "swan", "pigeon",
    "pelican", "peacock",
    # animals — reptiles/amphibians/fish
    "lizard", "snake", "turtle", "tortoise", "crocodile", "alligator",
    "dragon", "frog", "toad", "fish", "octopus",
    # characters
    "human", "man", "woman", "child", "knight", "warrior", "wizard",
    "robot", "soldier", "ninja", "samurai", "godzilla", "chef", "farmer",
    # vehicles — types
    "car", "truck", "motorcycle", "bike", "bicycle", "tank", "plane",
    "airplane", "helicopter", "boat", "ship", "train", "spaceship",
    "submarine",
    # environments — architectural
    "castle", "house", "building", "skyscraper", "bridge", "tower",
    "rooftop", "rooftops", "cityscape", "village", "ruins", "temple",
    "cathedral", "church", "fortress", "keep", "barn", "houses",
    # environments — landscape
    "landscape", "mountain", "canyon", "forest", "desert", "ocean",
    "lake", "river", "glacier", "iceland", "tundra", "jungle", "savanna",
    "meadow", "valley", "cliff", "beach", "volcano", "waterfall",
    "terrain", "skybox",
    # weather/atmosphere
    "thunderstorm", "storm", "blizzard", "fog", "aurora", "lightning",
    # plants / foliage
    "tree", "flower", "flowers", "bush", "bushes", "grass", "sunflower",
    "rose", "cactus",
    # props
    "chair", "table", "weapon", "sword", "shield", "lamp", "rock",
}

# Subject noun → biome hints for environment assets.  Feeds the world-dev
# classifier so a canyon_landscape.glb can be pulled when biome=desert.
_SUBJECT_BIOME_HINTS = {
    "canyon":     ["canyon", "desert", "mountain", "outdoor"],
    "landscape":  ["outdoor", "generic_outdoor"],
    "mountain":   ["mountain", "outdoor"],
    "forest":     ["forest", "outdoor"],
    "desert":     ["desert", "outdoor", "arid"],
    "ocean":      ["ocean", "water", "outdoor"],
    "glacier":    ["arctic", "snow", "ice"],
    "iceland":    ["arctic", "tundra", "volcanic"],
    "winter":     ["arctic", "snow", "winter"],
    "meadow":     ["meadow", "generic_outdoor", "summer"],
    "jungle":     ["forest", "jungle", "tropical"],
    "castle":     ["castle", "medieval", "fantasy"],
    "fortress":   ["castle", "medieval", "fantasy"],
    "temple":     ["temple", "fantasy", "ancient"],
    "house":      ["house", "residential", "rural"],
    "houses":     ["rural", "residential", "european"],
    "rooftop":    ["city", "urban"],
    "rooftops":   ["city", "urban", "european"],
    "cityscape":  ["city", "urban", "city_day", "city_night"],
    "skybox":     ["outdoor"],
    "sunflower":  ["meadow", "summer"],
    "flower":     ["meadow", "summer", "garden"],
    "flowers":    ["meadow", "summer", "garden"],
    "bush":       ["forest", "meadow"],
    "bushes":     ["forest", "meadow"],
    "tree":       ["forest"],
    "cactus":     ["desert"],
    "rose":       ["garden", "summer"],
}

# Keywords that signal use_as classification for environment assets.
_SKYBOX_TOKENS = {"skybox", "sky_box"}
_GROUND_TOKENS = {"terrain", "ground", "mossygrassy", "sand", "floor"}

_SUPPORTED_MODEL_EXTS = (".blend", ".glb", ".gltf", ".fbx", ".obj")
_SUPPORTED_HDRI_EXTS = (".exr", ".hdr")
_ARCHIVE_EXTS = (".zip",)


def _extract_archive_to_temp(archive_path: Path, tmp_root: Path) -> tuple | None:
    """Extract a zip into a tmp subdir and return
    (extracted_model_path, textures_dir_or_none, attribution_dict).

    Attribution is parsed from license.txt / README.md / any .txt
    inside the archive.  Returns None if no usable 3D model was found
    in the archive.
    """
    import zipfile
    tmp_root.mkdir(parents=True, exist_ok=True)
    target = tmp_root / archive_path.stem
    target.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            # Safety: skip any entries with .. or absolute paths
            for member in zf.namelist():
                if member.startswith("/") or ".." in member:
                    continue
                try:
                    zf.extract(member, target)
                except Exception:
                    pass
    except Exception as e:
        print(f"[INGEST] archive extract failed for {archive_path.name}: {e}", flush=True)
        return None

    # Find first model file
    model_path = None
    for ext in _SUPPORTED_MODEL_EXTS:
        hits = list(target.rglob(f"*{ext}"))
        if hits:
            # Prefer files in 'source/' or the archive root; deprioritise 'textures/'
            hits_ranked = sorted(hits, key=lambda p: (
                1 if "texture" in str(p).lower() else 0,
                len(p.parts),
                str(p),
            ))
            model_path = hits_ranked[0]
            break

    # Find textures dir (optional, adjacent to model)
    textures_dir = None
    if model_path:
        for candidate in (model_path.parent / "textures", model_path.parent / "Textures"):
            if candidate.exists() and candidate.is_dir():
                textures_dir = candidate
                break

    # Parse license / attribution
    attribution = _parse_archive_attribution(target)

    return model_path, textures_dir, attribution


_LICENSE_FILE_NAMES = (
    "license.txt", "LICENSE.txt", "LICENSE", "license",
    "readme.txt", "README.md", "readme.md", "README.txt",
    "credits.txt", "attribution.txt",
)

_LICENSE_PATTERNS = (
    (re.compile(r"\bCC0\b|\bpublic\s+domain\b", re.I),            "CC0"),
    (re.compile(r"\bCC[-\s]BY[-\s]SA(?:[-\s]?4\.0)?\b", re.I),    "CC-BY-SA-4.0"),
    (re.compile(r"\bCC[-\s]BY(?:[-\s]?4\.0)?\b", re.I),           "CC-BY-4.0"),
    (re.compile(r"\bCC[-\s]BY[-\s]NC(?:[-\s]?4\.0)?\b", re.I),    "CC-BY-NC-4.0"),
    (re.compile(r"\bMIT\s+License\b", re.I),                      "MIT"),
    (re.compile(r"\bApache\s*2", re.I),                            "Apache-2.0"),
)

_LICENSE_URLS = {
    "CC0":          "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0":    "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC-BY-NC-4.0": "https://creativecommons.org/licenses/by-nc/4.0/",
}


def _parse_archive_attribution(extracted_root: Path) -> dict:
    """Scan for license.txt / README / credits file; extract author/url/license.

    Handles typical Sketchfab download format:
        License:
            CC-BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
        Author:
            ArtistName (https://sketchfab.com/artist)
        Source:
            https://sketchfab.com/models/abc123...
    """
    attribution = {
        "author":      None,
        "source":      None,
        "source_url":  None,
        "license":     None,
        "license_url": None,
        "title":       None,
    }
    candidates: list = []
    for name in _LICENSE_FILE_NAMES:
        candidates.extend(extracted_root.rglob(name))
    if not candidates:
        return attribution

    for lic_path in candidates:
        try:
            text = lic_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # License
        if not attribution["license"]:
            for pat, label in _LICENSE_PATTERNS:
                if pat.search(text):
                    attribution["license"] = label
                    attribution["license_url"] = _LICENSE_URLS.get(label)
                    break

        # Author — "by X", "Author: X", "Author:\n    X"
        if not attribution["author"]:
            m = re.search(r"(?:Author|by)\s*:?\s*\n?\s*\"?([^\n\r()\"]{2,80})", text, re.I)
            if m:
                cand = m.group(1).strip(" \"'")
                if cand and not cand.lower().startswith(("http", "www", "license")):
                    attribution["author"] = cand[:80]

        # Source URL — sketchfab/polyhaven/cgtrader/turbosquid
        if not attribution["source_url"]:
            m = re.search(
                r"https?://(?:www\.)?"
                r"(sketchfab\.com|polyhaven\.com|cgtrader\.com|turbosquid\.com|"
                r"opengameart\.org|blendswap\.com|smithsonian\.si\.edu)[^\s\)]*",
                text, re.I,
            )
            if m:
                url = m.group(0).rstrip(".,)")
                attribution["source_url"] = url
                dom = m.group(1).lower().split(".")[0]
                attribution["source"] = dom

        # Title — first non-blank line of Title: block
        if not attribution["title"]:
            m = re.search(r"(?:Title|Name)\s*:?\s*\n?\s*([^\n\r]{2,120})", text, re.I)
            if m:
                t = m.group(1).strip(" \"'")
                if t and not t.lower().startswith("license"):
                    attribution["title"] = t[:120]

        if attribution["author"] and attribution["license"]:
            break  # enough info

    return attribution


def _load_library() -> dict:
    if not LIBRARY_PATH.exists():
        return {"version": 2, "schema": "unified_v2", "assets": []}
    try:
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "assets" not in data:
            return {"version": 2, "schema": "unified_v2", "assets": []}
        return data
    except Exception as e:
        print(f"[INGEST] warning: couldn't parse library.json ({e}) — starting fresh", flush=True)
        return {"version": 2, "schema": "unified_v2", "assets": []}


def _save_library(lib: dict) -> None:
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(json.dumps(lib, indent=2), encoding="utf-8")


def _tokenize_filename(stem: str) -> list:
    """Split filename stem into lowercase tokens (handles _, -, camelCase)."""
    # Insert underscore before capitals for camelCase
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", stem)
    s = s.lower().replace("-", "_")
    # Strip resolution suffixes / numeric trailers
    s = re.sub(r"_\d+k$", "", s)   # _4k, _2k
    tokens = [t for t in s.split("_") if t]
    # Drop pure numbers and very short filler
    tokens = [t for t in tokens if not (t.isdigit() and len(t) <= 2) and t not in ("v", "ver")]
    return tokens


def _parse_metadata_from_path(
    path: Path,
    category: str,
    category_tags: list,
    scale_class: str,
    folder_subject_hint: str | None = None,
) -> dict:
    """Return a library-entry dict populated from filename + folder heuristics.

    Subject-selection priority:
      1. A known species/object noun (_SUBJECT_NOUNS) in the filename
      2. Folder-supplied subject hint (e.g. ``cats/`` → 'cat')
      3. First non-noise token from the filename
    """
    stem = path.stem
    tokens = _tokenize_filename(stem)

    brand = next((t for t in tokens if t in _BRAND_TOKENS), None)
    model = next((t for t in tokens if t in _MODEL_TOKENS or (t.isdigit() and len(t) >= 3)), None)

    colors = [t for t in tokens if t in _COLOR_TOKENS]
    behaviors = [t for t in tokens if t in _BEHAVIOR_TOKENS]
    styles = [t for t in tokens if t in _STYLE_TOKENS]
    visual_descriptors = sorted(set(colors + styles))
    behavior_tags = behaviors

    # Compound brand collapse (aston_martin, rolls_royce, etc.)
    for (a, b), collapsed in _COMPOUND_BRANDS.items():
        if a in tokens and b in tokens:
            brand = collapsed
            break

    # 1. Known subject noun in filename wins
    subject = next((t for t in tokens if t in _SUBJECT_NOUNS), None)
    # For environments: if the filename has a specific landscape-type
    # noun (canyon, castle), prefer it over the generic "landscape" token.
    if category == "environment" and subject in ("landscape", "terrain", "scenery", None):
        _specific_env = next(
            (t for t in tokens if t in _SUBJECT_NOUNS
             and t not in ("landscape", "terrain", "scenery")),
            None,
        )
        if _specific_env:
            subject = _specific_env
    # 2. For branded vehicles (no generic subject noun), the subject is the brand
    if subject is None and brand:
        subject = brand
    # 3. Fall back to folder hint
    if subject is None and folder_subject_hint:
        subject = folder_subject_hint
    # 4. First non-noise token
    if subject is None:
        noise = set(
            _BRAND_TOKENS | _MODEL_TOKENS | _COLOR_TOKENS
            | _STYLE_TOKENS | _VARIANT_TOKENS | _BEHAVIOR_TOKENS
        )
        subject = next((t for t in tokens if t not in noise), None)
    if subject is None:
        subject = brand or stem

    subject_tags = sorted(set(category_tags + tokens + behavior_tags))
    subject_tags = [t for t in subject_tags if t and len(t) > 1 and t not in ("v",)]

    # Biome hints from subject noun (used by world-dev for environment assets)
    biome_hints = list(_SUBJECT_BIOME_HINTS.get(subject, []))
    # Also pull hints from any landscape-noun token
    for t in tokens:
        if t in _SUBJECT_BIOME_HINTS:
            for h in _SUBJECT_BIOME_HINTS[t]:
                if h not in biome_hints:
                    biome_hints.append(h)

    # use_as classification for environments
    use_as = None
    if category == "environment":
        token_set = set(tokens)
        if token_set & _SKYBOX_TOKENS:
            use_as = "skybox"
        elif token_set & _GROUND_TOKENS:
            use_as = "ground_replacement"
        else:
            use_as = "background_scenery"
    elif category == "prop":
        use_as = "scatter_element"

    return {
        "subject":            subject,
        "subject_tags":       subject_tags,
        "visual_descriptors": visual_descriptors,
        "category":           category,
        "scale_class":        scale_class,
        "brand":              brand,
        "model":              model,
        "biome_hints":        biome_hints,
        "use_as":             use_as,
    }


def _classify_file(path: Path, inbox_root: Path | None = None) -> tuple | None:
    """Return (category, base_tags, scale_class, subject_hint) from the folder.
    Returns None for unknown layouts."""
    try:
        rel = path.relative_to(inbox_root or INBOX)
    except ValueError:
        return None
    parts = [p.lower() for p in rel.parts[:-1]]  # folders only, not filename
    if not parts:
        return None
    folder = parts[0]
    if folder in _FOLDER_CATEGORY_MAP:
        return _FOLDER_CATEGORY_MAP[folder]
    return None


def _target_path(source: Path, category: str, keep_name: str) -> Path:
    """Where the ingested file should live after copy."""
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", keep_name)
    if category == "hdri":
        return HDRI_ROOT / safe
    if category == "vehicle":
        sub = "vehicles"
    elif category == "character":
        sub = "characters"
    elif category == "environment":
        sub = "environments"
    elif category == "prop":
        sub = "props"
    else:
        sub = category
    return MODELS_ROOT / sub / safe


def _entry_id(subject: str, brand: str | None, path: Path) -> str:
    parts = ["lib", subject or "asset"]
    if brand:
        parts.append(brand)
    parts.append(path.stem.lower())
    return "_".join(re.sub(r"[^a-zA-Z0-9]+", "_", p) for p in parts).strip("_")[:80]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["tested", "unverified"], default="unverified",
                        help="quality flag for ingested assets (default: unverified)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inbox", default=None, help="override inbox path")
    args = parser.parse_args()

    inbox = Path(args.inbox) if args.inbox else INBOX
    if not inbox.exists():
        print(f"[INGEST] inbox does not exist: {inbox}")
        return

    errors: list = []

    # Scan for files
    files = []
    for ext in _SUPPORTED_MODEL_EXTS + _SUPPORTED_HDRI_EXTS:
        files.extend(inbox.rglob(f"*{ext}"))
    archives = list(inbox.rglob("*.zip"))
    # Exclude already-processed
    files = [f for f in files if "_processed" not in [p.lower() for p in f.parts]]
    archives = [a for a in archives if "_processed" not in [p.lower() for p in a.parts]]

    # Extract archives → each yields a model file we add to the scan list
    tmp_extract = inbox / "_extract_tmp"
    archive_attributions: dict = {}  # dest_path -> attribution dict
    archive_sources: dict = {}       # dest_path -> original .zip path (for processed move)
    archive_texture_dirs: dict = {}  # dest_path -> extracted textures_dir
    if archives:
        print(f"[INGEST] scanning {len(archives)} archive(s) for zipped assets")
        for arc in archives:
            try:
                result = _extract_archive_to_temp(arc, tmp_extract)
                if result is None:
                    print(
                        f"[INGEST] extracted archive: {arc.name} -> "
                        f"no 3D model found inside, skipping",
                        flush=True,
                    )
                    continue
                extracted_model, textures_dir, attribution = result
                if extracted_model is None:
                    print(
                        f"[INGEST] extracted archive: {arc.name} -> "
                        f"no 3D model found inside, skipping",
                        flush=True,
                    )
                    continue
                files.append(extracted_model)
                archive_attributions[str(extracted_model)] = attribution
                archive_sources[str(extracted_model)] = arc
                if textures_dir:
                    archive_texture_dirs[str(extracted_model)] = textures_dir
                lic = attribution.get("license") or "license_unknown"
                auth = attribution.get("author") or "author_unknown"
                print(
                    f"[INGEST] extracted archive: {arc.name} -> "
                    f"found {extracted_model.name} "
                    f"({lic} by {auth!r})",
                    flush=True,
                )
            except Exception as e:
                import traceback
                print(f"[INGEST] archive extract error {arc.name}: {e}", flush=True)
                print(traceback.format_exc(), flush=True)

    if not files:
        print(f"[INGEST] no files found in {inbox} (extensions: "
              f"{_SUPPORTED_MODEL_EXTS + _SUPPORTED_HDRI_EXTS}, archives: {_ARCHIVE_EXTS})")
        return

    print(f"[INGEST] scanning {len(files)} files from {inbox}")

    library = _load_library()
    existing_paths = {
        str(a.get("path", "")).replace("\\", "/")
        for a in library.get("assets", [])
    }

    now = int(time.time())
    per_category: dict = {}
    skipped_duplicate = 0
    added_entries: list = []
    staged_copies: list = []   # (source, dest) pairs to perform at commit time

    for src in files:
        try:
            classification = _classify_file(src, inbox_root=inbox)
            if not classification:
                errors.append(f"couldn't classify (unknown folder): {src.relative_to(inbox)}")
                continue
            category, base_tags, scale, subject_hint = classification
            metadata = _parse_metadata_from_path(
                src, category, base_tags, scale,
                folder_subject_hint=subject_hint,
            )

            # Read optional .json sidecar
            sidecar = src.with_suffix(".json")
            if sidecar.exists():
                try:
                    override = json.loads(sidecar.read_text(encoding="utf-8"))
                    for k, v in override.items():
                        metadata[k] = v
                    print(f"[INGEST]   sidecar applied: {sidecar.name}")
                except Exception as e:
                    errors.append(f"sidecar parse failed for {sidecar.name}: {e}")

            dest = _target_path(src, category, src.name)
            # Dedup: if dest path already in library, skip
            dest_rel = str(dest.relative_to(ROOT)).replace("\\", "/")
            if dest_rel in existing_paths:
                skipped_duplicate += 1
                continue

            # Attribution: from archive extraction (if src was inside a zip)
            # or sidecar .json override, else needs_attribution=True.
            _attr_from_archive = archive_attributions.get(str(src), {})
            _attr = {
                "author":      _attr_from_archive.get("author"),
                "source":      _attr_from_archive.get("source") or "user_upload",
                "source_url":  _attr_from_archive.get("source_url"),
                "license":     _attr_from_archive.get("license"),
                "license_url": _attr_from_archive.get("license_url"),
                "title":       _attr_from_archive.get("title"),
            }
            if metadata.get("attribution"):
                # Sidecar override wins
                _attr.update({k: v for k, v in metadata["attribution"].items() if v})
            needs_attribution = not (_attr.get("author") and _attr.get("license"))

            # Format detection from file extension
            _fmt = src.suffix.lower().lstrip(".")

            entry = {
                "id":                 _entry_id(metadata.get("subject"), metadata.get("brand"), src),
                "path":               dest_rel,
                "subject":            metadata.get("subject"),
                "subject_tags":       metadata.get("subject_tags", []),
                "visual_descriptors": metadata.get("visual_descriptors", []),
                "category":           category,
                "scale_class":        metadata.get("scale_class", scale),
                "source":             "user_upload",
                "quality":            args.tier,
                "format":             _fmt,
                "use_count":          0,
                "last_used_at":       None,
                "added_at":           now,
                "brand":              metadata.get("brand"),
                "model":              metadata.get("model"),
                "biome_hints":        metadata.get("biome_hints", []),
                "use_as":             metadata.get("use_as"),
                "attribution":        _attr,
                "needs_attribution":  needs_attribution,
                "notes":              f"ingested from {src.relative_to(inbox)} at {now}",
            }
            if needs_attribution:
                print(
                    f"[INGEST] WARN: {src.name} has no attribution — "
                    f"add manually to library.json or set "
                    f"needs_attribution=false to suppress",
                    flush=True,
                )
            # V1.2: run healer on the staged destination so the library
            # entry lands with orientation_fix / shape_class / ground_offset
            # already populated.  Failures are flagged as notes; the entry
            # still registers (the one-off heal_library tool can sweep it).
            try:
                from app.services.asset_healer import heal_asset as _heal_asset
                if dest.exists() and dest.suffix.lower() in (".glb", ".gltf", ".blend", ".fbx", ".obj"):
                    _healed = _heal_asset(str(dest), proposed_category=category)
                    for _k, _v in (_healed or {}).items():
                        entry[_k] = _v
                    print(
                        f"[INGEST] heal {src.name}: "
                        f"shape={entry.get('shape_class')!r} "
                        f"orientation={entry.get('orientation_issue')!r} "
                        f"provisional_ready={entry.get('provisional_ready')}",
                        flush=True,
                    )
            except Exception as _he:
                print(f"[INGEST] heal failed for {src.name} (non-fatal): {_he}", flush=True)

            added_entries.append(entry)
            staged_copies.append((src, dest, sidecar if sidecar.exists() else None))
            existing_paths.add(dest_rel)
            per_category[category] = per_category.get(category, 0) + 1

            # Per-subject tally
            per_category.setdefault(f"_{category}_by_subject", {})
            subj_key = metadata.get("subject") or "?"
            per_category[f"_{category}_by_subject"][subj_key] = (
                per_category[f"_{category}_by_subject"].get(subj_key, 0) + 1
            )
        except Exception as e:
            errors.append(f"error on {src.name}: {e}")

    # ── Dry-run summary ──────────────────────────────────────────────
    if args.dry_run:
        print(f"[INGEST] DRY RUN — would add {len(added_entries)} entries")
        for c, n in per_category.items():
            if c.startswith("_"):
                continue
            print(f"[INGEST]   {c}: {n}")
            subdict = per_category.get(f"_{c}_by_subject", {})
            for s, cnt in sorted(subdict.items(), key=lambda kv: -kv[1])[:8]:
                print(f"[INGEST]     {s}x{cnt}")
        if skipped_duplicate:
            print(f"[INGEST]   skipped: {skipped_duplicate} (duplicate paths)")
        if errors:
            print(f"[INGEST]   errors: {len(errors)}")
            for e in errors[:10]:
                print(f"[INGEST]     {e}")
        return

    # ── Commit: copy files + append entries ──────────────────────────
    processed_dir = PROCESSED_BASE / time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    processed_dir.mkdir(parents=True, exist_ok=True)

    committed = 0
    for src, dest, sidecar in staged_copies:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

            # Copy textures/ dir if one came from a zip extraction
            _textures_dir = archive_texture_dirs.get(str(src))
            if _textures_dir and _textures_dir.exists():
                try:
                    tex_dest = dest.parent / "textures"
                    if not tex_dest.exists():
                        shutil.copytree(_textures_dir, tex_dest)
                        print(
                            f"[INGEST]   textures/ copied to {tex_dest.relative_to(ROOT)}",
                            flush=True,
                        )
                except Exception as e:
                    errors.append(f"textures copy failed for {src.name}: {e}")

            # Move source to processed (only if it's inside inbox)
            try:
                processed_target = processed_dir / src.relative_to(inbox)
                processed_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(processed_target))
            except ValueError:
                # src came from the _extract_tmp dir — don't try to move it
                # into processed/; it'll be cleaned with the tmp dir below
                pass
            # Move the original .zip to processed if this entry came from an archive
            _orig_zip = archive_sources.get(str(src))
            if _orig_zip and _orig_zip.exists():
                try:
                    zip_target = processed_dir / _orig_zip.relative_to(inbox)
                    zip_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(_orig_zip), str(zip_target))
                except Exception:
                    pass
            if sidecar and sidecar.exists():
                try:
                    sidecar_target = processed_dir / sidecar.relative_to(inbox)
                    shutil.move(str(sidecar), str(sidecar_target))
                except Exception:
                    pass
            committed += 1
        except Exception as e:
            errors.append(f"copy failed {src.name} -> {dest}: {e}")

    # Append only entries whose file copy succeeded
    committed_entries = added_entries[:committed]
    library.setdefault("assets", []).extend(committed_entries)
    before = len(library["assets"]) - len(committed_entries)
    _save_library(library)

    # ── Final summary ────────────────────────────────────────────────
    print(f"[INGEST] scanned {len(files)} files from {inbox}")
    for c in sorted(per_category.keys()):
        if c.startswith("_"):
            continue
        n = per_category[c]
        subdict = per_category.get(f"_{c}_by_subject", {})
        subj_summary = ", ".join(
            f"{s}x{n}" for s, n in sorted(subdict.items(), key=lambda kv: -kv[1])[:6]
        )
        print(f"[INGEST]   {c}: {n} added ({subj_summary})")
    if skipped_duplicate:
        print(f"[INGEST]   skipped: {skipped_duplicate} (duplicate paths)")
    if errors:
        print(f"[INGEST]   errors: {len(errors)}")
        for e in errors[:10]:
            print(f"[INGEST]     {e}")
    print(f"[INGEST] library.json entries: {before} -> {len(library['assets'])} (+{committed})")
    print(f"[INGEST] moved processed files to {processed_dir.relative_to(ROOT)}")

    # Clean up archive extraction tmp
    try:
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
