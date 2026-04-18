"""POST /uploads — pre-upload images before creating a draft."""
from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("")
async def upload_file(request: Request, file: UploadFile = File(...)):
    store = request.app.state.store
    data = await file.read()
    # Sanitize filename
    safe_name = "".join(c for c in (file.filename or "upload.png") if c.isalnum() or c in "._-")
    key = f"uploads/{safe_name}"
    await store.put(key, data, file.content_type or "application/octet-stream")
    return {"upload_id": safe_name, "key": key, "size": len(data)}
