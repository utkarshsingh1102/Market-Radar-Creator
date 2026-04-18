"""Jinja2-rendered HTML pages."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pathlib import Path

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("new_draft.html", {"request": request})


@router.get("/drafts/{draft_id}/edit", response_class=HTMLResponse)
async def edit_draft_page(draft_id: UUID, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    base = str(request.base_url).rstrip("/")
    preview_url = (
        f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}"
        if draft.preview_asset_key
        else ""
    )

    return templates.TemplateResponse(
        "edit_draft.html",
        {"request": request, "draft": draft, "preview_url": preview_url},
    )
