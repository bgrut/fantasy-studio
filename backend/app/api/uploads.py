from __future__ import annotations

"""
api/uploads.py
==============
HTTP endpoint for ingesting user-uploaded assets. Wraps
``services.user_asset_ingestor.ingest_uploaded_file`` so the heavy
lifting (validate / normalize / probe / classify / register) lives in
the service layer and stays unit-testable independently of FastAPI.

Endpoints
---------
    POST /api/uploads/asset       multipart/form-data, single file
    GET  /api/uploads/limits       JSON describing accepted formats / max size
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..services.user_asset_ingestor import (
    ingest_uploaded_file,
    MAX_UPLOAD_BYTES,
    MODEL_EXTS,
    HDRI_EXTS,
    TEXTURE_EXTS,
)


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class UploadLimitsResponse(BaseModel):
    max_bytes: int
    model_extensions: list[str]
    hdri_extensions: list[str]
    texture_extensions: list[str]


class UploadAssetResponse(BaseModel):
    ok: bool
    asset_type: str
    record: dict | None = None
    warnings: list[str] = []
    error: str | None = None


@router.get("/limits", response_model=UploadLimitsResponse)
def get_limits() -> UploadLimitsResponse:
    """Tell the frontend what it's allowed to upload."""
    return UploadLimitsResponse(
        max_bytes=MAX_UPLOAD_BYTES,
        model_extensions=sorted(MODEL_EXTS),
        hdri_extensions=sorted(HDRI_EXTS),
        texture_extensions=sorted(TEXTURE_EXTS),
    )


@router.post("/asset", response_model=UploadAssetResponse)
async def upload_asset(file: UploadFile = File(...)) -> UploadAssetResponse:
    """
    Accept a single user-uploaded asset (model, HDRI, or texture),
    stage it to a temp file, and run it through the ingestor.

    The ingestor itself never raises — it returns an IngestResult that
    we forward to the client. The only HTTPException this endpoint
    raises is for missing/empty uploads, which is a client-side error.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="no file provided")

    # Stream the upload to a temp file so we never hold the whole
    # payload in memory. The ingestor will move it into its final
    # location during normalization.
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
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

    result = ingest_uploaded_file(tmp_path, file.filename)
    return UploadAssetResponse(
        ok=result.ok,
        asset_type=result.asset_type,
        record=result.record,
        warnings=result.warnings,
        error=result.error,
    )
