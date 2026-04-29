from __future__ import annotations

"""
api/templates.py
================
HTTP endpoints for the template-pack marketplace.

    GET    /api/templates/packs                 list installed packs
    GET    /api/templates/packs/{pack_id}        single pack details
    POST   /api/templates/packs/validate         validate an uploaded pack
    POST   /api/templates/packs/install          validate + install
    DELETE /api/templates/packs/{pack_id}        uninstall

The validate / install endpoints accept a multipart upload (a .zip
template pack) so a frontend can drop one in directly. The install
endpoint optionally accepts ``force=true`` as a query param to allow
overwriting an existing pack with the same id.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..services.template_marketplace import (
    PACK_MANIFEST_SCHEMA,
    SUPPORTED_SPEC_VERSION,
    install_pack,
    list_packs,
    get_pack,
    uninstall_pack,
    validate_pack,
)


router = APIRouter(prefix="/api/templates", tags=["templates"])


# ═══════════════════════════════════════════════════════════════════════════
# Response models
# ═══════════════════════════════════════════════════════════════════════════

class PackRecord(BaseModel):
    pack_id: str
    name: str | None = None
    version: str | None = None
    author: str | None = None
    license: str | None = None
    scene_family: str | None = None
    template_name: str | None = None
    install_path: str | None = None
    installed_at: int | None = None
    manifest: dict[str, Any] | None = None


class PackListResponse(BaseModel):
    ok: bool
    spec_version: int
    packs: list[PackRecord]


class PackValidationResponse(BaseModel):
    ok: bool
    pack_id: str | None = None
    manifest: dict[str, Any] | None = None
    errors: list[str] = []
    warnings: list[str] = []


class PackInstallResponse(BaseModel):
    ok: bool
    pack_id: str | None = None
    record: PackRecord | None = None
    error: str | None = None
    warnings: list[str] = []


class SchemaResponse(BaseModel):
    ok: bool
    spec_version: int
    fields: list[dict[str, Any]]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

async def _stage_upload(file: UploadFile) -> Path:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="template pack must be a .zip file")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = Path(tmp.name)
    try:
        try:
            shutil.copyfileobj(file.file, tmp)
        finally:
            tmp.close()
            await file.close()
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"failed to stage upload: {e}")
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/schema", response_model=SchemaResponse)
def get_schema() -> SchemaResponse:
    """Expose the manifest schema so frontends/tools can build forms / linters."""
    fields = []
    for key, typ, required, allowed in PACK_MANIFEST_SCHEMA:
        if isinstance(typ, tuple):
            type_name = "|".join(t.__name__ for t in typ)
        else:
            type_name = typ.__name__
        fields.append({
            "key":      key,
            "type":     type_name,
            "required": required,
            "allowed":  allowed,
        })
    return SchemaResponse(
        ok=True,
        spec_version=SUPPORTED_SPEC_VERSION,
        fields=fields,
    )


@router.get("/packs", response_model=PackListResponse)
def list_installed_packs() -> PackListResponse:
    return PackListResponse(
        ok=True,
        spec_version=SUPPORTED_SPEC_VERSION,
        packs=[PackRecord(**p) for p in list_packs()],
    )


@router.get("/packs/{pack_id}", response_model=PackRecord)
def get_installed_pack(pack_id: str) -> PackRecord:
    record = get_pack(pack_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"pack {pack_id!r} not installed")
    return PackRecord(**record)


@router.post("/packs/validate", response_model=PackValidationResponse)
async def validate_pack_endpoint(
    file: UploadFile = File(...),
) -> PackValidationResponse:
    """Validate an uploaded .zip pack without installing it."""
    tmp_path = await _stage_upload(file)
    try:
        result = validate_pack(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
    return PackValidationResponse(
        ok=result.ok,
        pack_id=result.pack_id,
        manifest=result.manifest,
        errors=result.errors,
        warnings=result.warnings,
    )


@router.post("/packs/install", response_model=PackInstallResponse)
async def install_pack_endpoint(
    file: UploadFile = File(...),
    force: bool = Form(False),
) -> PackInstallResponse:
    """Validate + install an uploaded .zip pack."""
    tmp_path = await _stage_upload(file)
    try:
        result = install_pack(tmp_path, force=force)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    record = PackRecord(**result.record) if result.record else None
    return PackInstallResponse(
        ok=result.ok,
        pack_id=result.pack_id,
        record=record,
        error=result.error,
        warnings=result.warnings,
    )


@router.delete("/packs/{pack_id}", response_model=PackInstallResponse)
def uninstall_pack_endpoint(pack_id: str) -> PackInstallResponse:
    result = uninstall_pack(pack_id)
    record = PackRecord(**result.record) if result.record else None
    if not result.ok:
        return PackInstallResponse(
            ok=False,
            pack_id=pack_id,
            error=result.error,
        )
    return PackInstallResponse(
        ok=True,
        pack_id=pack_id,
        record=record,
    )
