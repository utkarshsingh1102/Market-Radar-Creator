"""PATCH /drafts/{id}/fields, POST /drafts/{id}/images/{slot}"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from app.schemas import FieldPatch

router = APIRouter(prefix="/drafts", tags=["edits"])


@router.patch("/{draft_id}/fields")
async def patch_fields(draft_id: UUID, patch: FieldPatch, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if patch.game_name is not None:
        draft.game_name = patch.game_name
    if patch.publisher is not None:
        draft.publisher = patch.publisher
    if patch.inspirations is not None:
        for item in patch.inspirations:
            idx = item.get("index")
            if idx is not None and 0 <= idx < len(draft.inspirations):
                if "name" in item:
                    draft.inspirations[idx].name = item["name"]
                if "publisher" in item:
                    draft.inspirations[idx].publisher = item["publisher"]

    draft = await orchestrator.update_draft(draft)
    base = str(request.base_url).rstrip("/")
    return {
        "id": str(draft.id),
        "edit_count": draft.edit_count,
        "preview_url": f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}",
    }


@router.post("/{draft_id}/images/{slot}")
async def replace_image(
    draft_id: UUID,
    slot: str,
    request: Request,
    file: UploadFile = File(...),
):
    """
    slot: 'main_screenshot' or 'inspiration_0_icon', 'inspiration_1_icon', etc.
    """
    orchestrator = request.app.state.orchestrator
    store = request.app.state.store
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    data = await file.read()

    if slot == "main_screenshot":
        key = f"drafts/{draft_id}/screenshot.png"
        await store.put(key, data, file.content_type or "image/png")
        draft.screenshot_asset_key = key
    elif slot.startswith("inspiration_") and slot.endswith("_icon"):
        parts = slot.split("_")
        try:
            idx = int(parts[1])
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid slot: {slot}")
        if idx >= len(draft.inspirations):
            raise HTTPException(status_code=400, detail="Inspiration index out of range")
        key = f"drafts/{draft_id}/icon_{idx}.png"
        await store.put(key, data, file.content_type or "image/png")
        from app.schemas import IconStatus
        draft.inspirations[idx].icon_asset_key = key
        draft.inspirations[idx].icon_status = IconStatus.ok
    else:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")

    draft = await orchestrator.update_draft(draft)
    base = str(request.base_url).rstrip("/")
    return {
        "id": str(draft.id),
        "edit_count": draft.edit_count,
        "preview_url": f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}",
    }


@router.post("/{draft_id}/regenerate")
async def regenerate(draft_id: UUID, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft = await orchestrator.update_draft(draft)
    base = str(request.base_url).rstrip("/")
    return {
        "id": str(draft.id),
        "edit_count": draft.edit_count,
        "preview_url": f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}",
    }
