"""POST /drafts, GET /drafts/{id}"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas import BriefIn, DraftResponse

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _draft_to_response(draft, request: Request) -> DraftResponse:
    base = str(request.base_url).rstrip("/")
    return DraftResponse(
        id=draft.id,
        edit_count=draft.edit_count,
        game_name=draft.game_name,
        publisher=draft.publisher,
        inspirations=draft.inspirations,
        preview_url=f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}" if draft.preview_asset_key else "",
        export_url=f"{base}/drafts/{draft.id}/export",
    )


@router.post("", status_code=201)
async def create_draft(brief: BriefIn, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.create_draft(brief)
    return _draft_to_response(draft, request)


@router.get("/{draft_id}")
async def get_draft(draft_id: UUID, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _draft_to_response(draft, request)
