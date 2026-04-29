from __future__ import annotations

"""
registry.py
===========
Loads every layer + recipe JSON file under ``app/templates_v2/``,
validates each against its schema (if jsonschema is installed), and
exposes a typed lookup API.

The registry is the single source of truth at runtime.  All other V2
code (dispatcher, executor) queries it — never reads files directly.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ── jsonschema is optional.  If missing we still run and log a warning. ──
try:
    import jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except Exception:
    _HAS_JSONSCHEMA = False


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "templates_v2"
SCHEMAS_DIR = TEMPLATES_DIR / "_schemas"

LAYER_KINDS = ("base", "environment", "composition", "lighting",
               "animation", "ambient", "post")

# Directory name → layer kind. The spec uses plural directory names for
# multi-variant slots and singular for tier/post/ambient/base.
_DIR_TO_KIND: dict[str, str] = {
    "base":         "base",
    "environments": "environment",
    "compositions": "composition",
    "lighting":     "lighting",
    "animations":   "animation",
    "ambient":      "ambient",
    "post":         "post",
}
_KIND_TO_DIR: dict[str, str] = {v: k for k, v in _DIR_TO_KIND.items()}


@dataclass
class TemplateRegistry:
    """In-memory cache of all V2 layers + recipes."""
    layers: dict[str, dict[str, dict]] = field(default_factory=dict)
    # ^ {kind: {name: layer_dict}}
    recipes: dict[str, dict] = field(default_factory=dict)
    # ^ {name: recipe_dict}
    errors: list[str] = field(default_factory=list)

    # ── lookup helpers ─────────────────────────────────────────────────

    def get_layer(self, kind: str, name: str) -> dict | None:
        return self.layers.get(kind, {}).get(name)

    def get_recipe(self, name: str) -> dict | None:
        return self.recipes.get(name)

    def iter_recipes(self) -> Iterable[dict]:
        return self.recipes.values()

    def summary(self) -> str:
        parts = [f"{kind}={len(self.layers.get(kind, {}))}" for kind in LAYER_KINDS]
        return (
            f"TemplateRegistry(recipes={len(self.recipes)}, "
            + ", ".join(parts)
            + f", errors={len(self.errors)})"
        )


# ── schema helpers ─────────────────────────────────────────────────────

def _load_schema(name: str) -> dict | None:
    path = SCHEMAS_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[TEMPLATE_V2] schema parse failed for {name}: {e}", flush=True)
        return None


def _validate(doc: dict, schema: dict | None, file_path: Path) -> str | None:
    """Returns an error string if validation fails, else None."""
    if schema is None or not _HAS_JSONSCHEMA:
        return None
    try:
        jsonschema.validate(instance=doc, schema=schema)
        return None
    except jsonschema.ValidationError as ve:
        return f"{file_path}: {ve.message} at {'.'.join(str(p) for p in ve.absolute_path)}"
    except Exception as e:
        return f"{file_path}: schema error: {e}"


# ── loaders ────────────────────────────────────────────────────────────

def _load_layer_file(path: Path, schema: dict | None) -> tuple[str | None, dict | None, str | None]:
    """Return (kind, layer_dict, error). Either (kind, dict, None) or (None, None, err)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, None, f"{path}: JSON parse failed: {e}"

    # Cross-checks beyond schema: filename stem == name, kind matches dir.
    stem = path.stem
    if doc.get("name") != stem:
        return None, None, f"{path}: name={doc.get('name')!r} must equal filename stem {stem!r}"
    dir_name = path.parent.name
    expected_kind = _DIR_TO_KIND.get(dir_name)
    if expected_kind is None:
        return None, None, f"{path}: unknown layer directory {dir_name!r}"
    if doc.get("kind") != expected_kind:
        return None, None, (
            f"{path}: kind={doc.get('kind')!r} must equal {expected_kind!r} "
            f"(directory is {dir_name!r})"
        )
    err = _validate(doc, schema, path)
    if err:
        return None, None, err
    return expected_kind, doc, None


def _load_recipe_file(path: Path, schema: dict | None, registry: TemplateRegistry) -> tuple[dict | None, str | None]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"{path}: JSON parse failed: {e}"
    if doc.get("name") != path.stem:
        return None, f"{path}: name={doc.get('name')!r} must equal filename stem {path.stem!r}"
    err = _validate(doc, schema, path)
    if err:
        return None, err

    # Verify every referenced layer exists.
    layers = doc.get("layers") or {}
    missing: list[str] = []
    for slot, ref in layers.items():
        refs = ref if isinstance(ref, list) else [ref]
        for r in refs:
            if not isinstance(r, str):
                missing.append(f"{slot}:<non-string>")
                continue
            if registry.get_layer(slot, r) is None:
                missing.append(f"{slot}:{r}")
    if missing:
        return None, f"{path}: unresolved layer references: {missing}"

    return doc, None


def load_registry(templates_dir: Path | None = None) -> TemplateRegistry:
    """Scan templates_v2/, validate, return registry.

    Invalid files are skipped and their errors are collected on
    ``registry.errors`` — the registry itself always loads.  This lets
    the dispatcher keep working while an author iterates on one broken
    file.
    """
    root = Path(templates_dir) if templates_dir else TEMPLATES_DIR
    reg = TemplateRegistry()
    layer_schema = _load_schema("layer.schema.json")
    recipe_schema = _load_schema("recipe.schema.json")

    if not _HAS_JSONSCHEMA:
        reg.errors.append(
            "jsonschema not installed — files loaded without validation. "
            "Install with: pip install jsonschema"
        )

    # 1) layers first so recipe validation can check references
    for kind in LAYER_KINDS:
        kdir = root / _KIND_TO_DIR[kind]
        if not kdir.exists():
            continue
        for fp in sorted(kdir.glob("*.json")):
            kind_loaded, layer, err = _load_layer_file(fp, layer_schema)
            if err:
                reg.errors.append(err)
                continue
            reg.layers.setdefault(kind_loaded, {})[layer["name"]] = layer

    # 2) recipes
    rdir = root / "recipes"
    if rdir.exists():
        for fp in sorted(rdir.glob("*.json")):
            recipe, err = _load_recipe_file(fp, recipe_schema, reg)
            if err:
                reg.errors.append(err)
                continue
            reg.recipes[recipe["name"]] = recipe

    return reg
