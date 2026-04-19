"""Jinja2-rendered HTML pages."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
static_dir = Path(__file__).parent / "static"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/projects/new", response_class=HTMLResponse)
async def new_project_page(request: Request):
    return templates.TemplateResponse("new_project.html", {"request": request})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_page(project_id: str, request: Request):
    orchestrator = request.app.state.orchestrator
    # Load project via the API router logic inline
    from app.models.project import Project
    from app.storage.local import LocalAssetStore
    from pathlib import Path as P
    import aiofiles

    store: LocalAssetStore = request.app.state.store
    projects_dir = P(store.root) / "projects"
    proj_file = projects_dir / f"{project_id}.json"
    if not proj_file.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    async with aiofiles.open(proj_file) as f:
        project = Project.model_validate_json(await f.read())

    base = str(request.base_url).rstrip("/")

    # Build slides with preview URLs and initial draft data
    slides = []
    for s in project.slides:
        slides.append({
            "draft_id": s.draft_id,
            "title": s.title,
            "preview_url": f"{base}/storage/{s.preview_key}" if s.preview_key else "",
        })

    # Load first slide's draft fields for initial render
    initial_draft = None
    initial_draft_data = None
    initial_preview_url = ""
    if project.slides:
        initial_draft = await orchestrator.load_draft(project.slides[0].draft_id)
        if initial_draft:
            initial_preview_url = (
                f"{base}/storage/{initial_draft.preview_asset_key}?v={initial_draft.edit_count}"
                if initial_draft.preview_asset_key else ""
            )
            initial_draft_data = {
                "id": str(initial_draft.id),
                "game_name": initial_draft.game_name,
                "publisher": initial_draft.publisher or "",
                "edit_count": initial_draft.edit_count,
                "inspirations": [
                    {
                        "name": insp.name,
                        "publisher": insp.publisher or "",
                        "icon_status": insp.icon_status.value,
                    }
                    for insp in initial_draft.inspirations
                ],
            }

    return templates.TemplateResponse("project.html", {
        "request": request,
        "project": project,
        "slides": slides,
        "initial_draft_data": initial_draft_data,
        "initial_preview_url": initial_preview_url,
    })


# Legacy edit-draft route (direct draft edit, no project context)
@router.get("/drafts/{draft_id}/edit", response_class=HTMLResponse)
async def edit_draft_page(draft_id: UUID, request: Request):
    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(str(draft_id))
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    base = str(request.base_url).rstrip("/")
    preview_url = (
        f"{base}/storage/{draft.preview_asset_key}?v={draft.edit_count}"
        if draft.preview_asset_key else ""
    )
    return templates.TemplateResponse(
        "edit_draft.html",
        {"request": request, "draft": draft, "preview_url": preview_url},
    )


@router.get("/sample-brief.json")
async def download_sample_brief():
    path = static_dir / "sample_brief.json"
    return FileResponse(
        path,
        media_type="application/json",
        filename="market_radar_sample_brief.json",
    )
