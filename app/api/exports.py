"""GET /drafts/{id}/export"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter(prefix="/drafts", tags=["exports"])


@router.get("/{draft_id}/export")
async def export_draft(draft_id: UUID, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    png_bytes = await orchestrator.export_draft(draft)
    filename = (
        draft.meta.output_filename
        or f"market-radar-{draft.meta.series_number or 'X'}-{draft.game_name.lower().replace(' ', '-')}.png"
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
