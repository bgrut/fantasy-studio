from __future__ import annotations

"""
template_marketplace.py
=======================
Packaging, registry, and validation for distributable "template packs".

A template pack is a self-contained bundle a third party can ship to
extend the engine with new scene types without touching core code. Each
pack is either a directory or a .zip with this layout:

    my_pack/
        template_pack.json        # required manifest
        builder.py                # required Python module exposing build()
        previews/                 # optional preview thumbnails
            cover.jpg
        assets/                   # optional sample assets
            ...

template_pack.json schema (see PACK_MANIFEST_SCHEMA below):
    {
      "spec_version":   1,
      "name":           "Cyberpunk Streets",
      "pack_id":        "cyberpunk_streets",          # filesystem-safe
      "version":        "0.1.0",                      # semver
      "author":         "Studio Foo",
      "license":        "MIT",
      "description":    "Neon-soaked street scene pack",
      "scene_family":   "street_scene",
      "template_name":  "cyberpunk_streets",
      "builder_module": "builder.py",
      "entry_function": "build",
      "asset_requirements": [
        {"role": "hero_model",     "tags": ["car", "futuristic"], "optional": false},
        {"role": "environment",    "tags": ["neon", "city"],      "optional": false}
      ],
      "preview_image":  "previews/cover.jpg",
      "min_engine_version": "0.5.0"
    }

Responsibilities of this module
-------------------------------
- ``validate_pack(path)``  — load + schema-check the manifest, verify
  every referenced file exists, return a structured report.
- ``install_pack(path)``   — validate, copy into the local pack
  directory, register in the pack registry.
- ``uninstall_pack(id)``   — remove pack files + registry entry.
- ``list_packs()``         — return all registered packs.
- ``get_pack(pack_id)``    — fetch one pack record.

The marketplace deliberately does not import builder modules at install
time — that happens only when a render job actually requests the pack
template. This keeps install fast and prevents broken packs from
crashing the API server.
"""

import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Configuration / paths
# ═══════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[2]
PACKS_DIR = ROOT / "assets" / "template_packs"
REGISTRY_PATH = ROOT / "assets" / "manifests" / "template_pack_registry.json"
SUPPORTED_SPEC_VERSION = 1
ENGINE_VERSION = "0.5.0"

PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$")


# Schema declared as plain data so it can be served over the API. Each
# entry is (key, type, required, allowed_values_or_None).
PACK_MANIFEST_SCHEMA: list[tuple[str, type | tuple[type, ...], bool, Any]] = [
    ("spec_version",         int,        True,  [SUPPORTED_SPEC_VERSION]),
    ("name",                 str,        True,  None),
    ("pack_id",              str,        True,  None),
    ("version",              str,        True,  None),
    ("author",               str,        True,  None),
    ("license",              str,        True,  None),
    ("description",          str,        False, None),
    ("scene_family",         str,        True,  None),
    ("template_name",        str,        True,  None),
    ("builder_module",       str,        True,  None),
    ("entry_function",       str,        False, None),
    ("asset_requirements",   list,       False, None),
    ("preview_image",        str,        False, None),
    ("min_engine_version",   str,        False, None),
]


# ═══════════════════════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PackValidation:
    ok: bool
    pack_id: str | None = None
    manifest: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PackInstallResult:
    ok: bool
    pack_id: str | None = None
    record: dict[str, Any] | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Registry I/O
# ═══════════════════════════════════════════════════════════════════════════

def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"packs": []}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {"packs": []}


def _save_registry(registry: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def list_packs() -> list[dict[str, Any]]:
    """Return every installed pack record."""
    return list(_load_registry().get("packs") or [])


def get_pack(pack_id: str) -> dict[str, Any] | None:
    for pack in list_packs():
        if pack.get("pack_id") == pack_id:
            return pack
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════

def _semver_compare(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if equal, 1 if a > b. Pre-release tags compare lexically."""
    def parts(v: str) -> tuple:
        m = SEMVER_RE.match(v.strip())
        if not m:
            return (0, 0, 0, "")
        nums, _, suffix = v.partition("-")
        major, minor, patch = (int(x) for x in nums.split("."))
        return (major, minor, patch, suffix)

    pa, pb = parts(a), parts(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def _check_field(manifest: dict, key: str, expected_type, required: bool, allowed) -> str | None:
    if key not in manifest:
        if required:
            return f"missing required field: {key}"
        return None
    value = manifest[key]
    if not isinstance(value, expected_type):
        return f"field {key!r} has wrong type (expected {expected_type.__name__})"
    if allowed is not None and value not in allowed:
        return f"field {key!r} has unsupported value: {value!r}"
    return None


def _validate_manifest_dict(manifest: dict) -> list[str]:
    errors: list[str] = []
    for key, typ, required, allowed in PACK_MANIFEST_SCHEMA:
        err = _check_field(manifest, key, typ, required, allowed)
        if err:
            errors.append(err)

    if errors:
        return errors

    # Targeted format checks
    pack_id = manifest.get("pack_id", "")
    if not PACK_ID_RE.match(pack_id):
        errors.append(
            f"pack_id {pack_id!r} must be lowercase alnum/underscore, "
            f"starting with a letter, length 3-64"
        )

    version = manifest.get("version", "")
    if not SEMVER_RE.match(version):
        errors.append(f"version {version!r} is not valid semver (e.g. 1.2.3)")

    min_engine = manifest.get("min_engine_version")
    if min_engine and _semver_compare(min_engine, ENGINE_VERSION) > 0:
        errors.append(
            f"pack requires engine >= {min_engine}, current engine is {ENGINE_VERSION}"
        )

    asset_reqs = manifest.get("asset_requirements") or []
    for i, req in enumerate(asset_reqs):
        if not isinstance(req, dict):
            errors.append(f"asset_requirements[{i}] is not an object")
            continue
        if not req.get("role"):
            errors.append(f"asset_requirements[{i}] missing 'role'")
        tags = req.get("tags")
        if tags is not None and not isinstance(tags, list):
            errors.append(f"asset_requirements[{i}].tags must be a list")
    return errors


def _read_manifest(pack_root: Path) -> dict[str, Any]:
    manifest_path = pack_root / "template_pack.json"
    if not manifest_path.exists():
        raise FileNotFoundError("template_pack.json missing")
    return json.loads(manifest_path.read_text(encoding="utf-8-sig"))


def _check_referenced_files(pack_root: Path, manifest: dict) -> tuple[list[str], list[str]]:
    """Verify every file the manifest points at exists inside the pack."""
    errors: list[str] = []
    warnings: list[str] = []

    builder = manifest.get("builder_module")
    if builder:
        if not (pack_root / builder).exists():
            errors.append(f"builder_module not found: {builder}")

    preview = manifest.get("preview_image")
    if preview and not (pack_root / preview).exists():
        warnings.append(f"preview_image not found: {preview}")

    return errors, warnings


def validate_pack(path: Path) -> PackValidation:
    """
    Validate a pack at ``path`` (either a directory or a .zip).
    Always returns a PackValidation — never raises.
    """
    path = Path(path)
    if not path.exists():
        return PackValidation(ok=False, errors=[f"path does not exist: {path}"])

    pack_root: Path
    cleanup_dir: Path | None = None

    try:
        if path.is_file() and path.suffix.lower() == ".zip":
            tmp = Path(tempfile.mkdtemp(prefix="template_pack_"))
            cleanup_dir = tmp
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    zf.extractall(tmp)
            except (zipfile.BadZipFile, OSError) as e:
                return PackValidation(ok=False, errors=[f"invalid zip: {e}"])
            # If the zip contains a single top-level dir, descend into it
            entries = [p for p in tmp.iterdir()]
            if len(entries) == 1 and entries[0].is_dir():
                pack_root = entries[0]
            else:
                pack_root = tmp
        elif path.is_dir():
            pack_root = path
        else:
            return PackValidation(ok=False, errors=[f"unsupported pack source: {path}"])

        try:
            manifest = _read_manifest(pack_root)
        except FileNotFoundError as e:
            return PackValidation(ok=False, errors=[str(e)])
        except json.JSONDecodeError as e:
            return PackValidation(ok=False, errors=[f"template_pack.json invalid JSON: {e}"])
        except OSError as e:
            return PackValidation(ok=False, errors=[f"failed to read manifest: {e}"])

        errors = _validate_manifest_dict(manifest)
        file_errors, warnings = _check_referenced_files(pack_root, manifest)
        errors += file_errors

        return PackValidation(
            ok=not errors,
            pack_id=manifest.get("pack_id"),
            manifest=manifest,
            errors=errors,
            warnings=warnings,
        )
    finally:
        # The validate path doesn't keep the extracted dir around. The
        # install path will re-extract into the permanent location.
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# Install / uninstall
# ═══════════════════════════════════════════════════════════════════════════

def _materialize_pack(source: Path, target_dir: Path) -> Path:
    """
    Copy a pack source (dir or zip) into ``target_dir``. Returns the
    final pack root path.
    """
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source, "r") as zf:
            zf.extractall(target_dir)
        # If the archive used a single top-level folder, hoist it.
        entries = list(target_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            inner = entries[0]
            for child in inner.iterdir():
                shutil.move(str(child), str(target_dir / child.name))
            shutil.rmtree(inner, ignore_errors=True)
        return target_dir

    if source.is_dir():
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source, target_dir)
        return target_dir

    raise ValueError(f"unsupported pack source: {source}")


def install_pack(source: Path | str, *, force: bool = False) -> PackInstallResult:
    """
    Validate ``source`` and, on success, copy it into the local packs
    directory and register it. ``force=True`` allows overwriting an
    existing pack with the same ``pack_id``.
    """
    src = Path(source)
    validation = validate_pack(src)
    if not validation.ok:
        return PackInstallResult(
            ok=False,
            pack_id=validation.pack_id,
            error="; ".join(validation.errors) or "validation failed",
            warnings=validation.warnings,
        )

    manifest = validation.manifest or {}
    pack_id = manifest["pack_id"]

    existing = get_pack(pack_id)
    if existing and not force:
        return PackInstallResult(
            ok=False,
            pack_id=pack_id,
            error=f"pack {pack_id!r} is already installed (use force=True to overwrite)",
        )

    target_dir = PACKS_DIR / pack_id
    try:
        _materialize_pack(src, target_dir)
    except Exception as e:
        return PackInstallResult(
            ok=False,
            pack_id=pack_id,
            error=f"materialize failed: {type(e).__name__}: {e}",
        )

    record = {
        "pack_id":       pack_id,
        "name":          manifest.get("name"),
        "version":       manifest.get("version"),
        "author":        manifest.get("author"),
        "license":       manifest.get("license"),
        "scene_family":  manifest.get("scene_family"),
        "template_name": manifest.get("template_name"),
        "install_path":  str(target_dir.relative_to(ROOT).as_posix()),
        "installed_at":  int(time.time()),
        "manifest":      manifest,
    }

    registry = _load_registry()
    packs = registry.setdefault("packs", [])
    packs[:] = [p for p in packs if p.get("pack_id") != pack_id]
    packs.append(record)
    _save_registry(registry)

    print(
        f"[MARKETPLACE] installed pack {pack_id} v{manifest.get('version')} -> {target_dir}",
        flush=True,
    )
    return PackInstallResult(
        ok=True,
        pack_id=pack_id,
        record=record,
        warnings=validation.warnings,
    )


def uninstall_pack(pack_id: str) -> PackInstallResult:
    """Remove a pack from disk and registry. Idempotent."""
    record = get_pack(pack_id)
    if not record:
        return PackInstallResult(
            ok=False,
            pack_id=pack_id,
            error=f"pack {pack_id!r} is not installed",
        )

    install_path = ROOT / record.get("install_path", "")
    if install_path.exists() and install_path.is_dir():
        shutil.rmtree(install_path, ignore_errors=True)

    registry = _load_registry()
    packs = registry.setdefault("packs", [])
    registry["packs"] = [p for p in packs if p.get("pack_id") != pack_id]
    _save_registry(registry)

    print(f"[MARKETPLACE] uninstalled pack {pack_id}", flush=True)
    return PackInstallResult(ok=True, pack_id=pack_id, record=record)
