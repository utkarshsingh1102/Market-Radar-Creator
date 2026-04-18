"""Project CRUD API — /api/projects"""
from __future__ import annotations

import json
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.project import Project, ProjectSlide
from app.schemas import ProjectBriefIn

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Storage helpers ───────────────────────────────────────────────────────────

def _projects_dir(request: Request) -> Path:
    return Path(request.app.state.store.root) / "projects"


async def _load_project(projects_dir: Path, project_id: str) -> Project | None:
    p = projects_dir / f"{project_id}.json"
    if not p.exists():
        return None
    async with aiofiles.open(p) as f:
        return Project.model_validate_json(await f.read())


async def _save_project(projects_dir: Path, project: Project) -> None:
    projects_dir.mkdir(parents=True, exist_ok=True)
    p = projects_dir / f"{project.id}.json"
    async with aiofiles.open(p, "w") as f:
        await f.write(project.model_dump_json())


async def _delete_project_file(projects_dir: Path, project_id: str) -> None:
    p = projects_dir / f"{project_id}.json"
    if p.exists():
        p.unlink()


# ── Response helpers ──────────────────────────────────────────────────────────

def _project_to_dict(project: Project, base: str) -> dict:
    thumbnail_url = (
        f"{base}/storage/{project.thumbnail_key}" if project.thumbnail_key else None
    )
    slides = [
        {
            "draft_id": s.draft_id,
            "title": s.title,
            "preview_url": f"{base}/storage/{s.preview_key}" if s.preview_key else None,
        }
        for s in project.slides
    ]
    return {
        "id": project.id,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "source": project.source,
        "json_filename": project.json_filename,
        "slide_count": project.slide_count,
        "thumbnail_url": thumbnail_url,
        "slides": slides,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_projects(request: Request):
    projects_dir = _projects_dir(request)
    projects_dir.mkdir(parents=True, exist_ok=True)
    projects = []
    for f in sorted(projects_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            async with aiofiles.open(f) as fp:
                p = Project.model_validate_json(await fp.read())
            projects.append(_project_to_dict(p, str(request.base_url).rstrip("/")))
        except Exception:
            continue
    return projects


class CreateProjectBody(BaseModel):
    name: str
    source: str = "ui"


@router.post("", status_code=201)
async def create_project(body: CreateProjectBody, request: Request):
    projects_dir = _projects_dir(request)
    project = Project(name=body.name, source=body.source)
    await _save_project(projects_dir, project)
    return _project_to_dict(project, str(request.base_url).rstrip("/"))


@router.post("/from-json", status_code=201)
async def create_project_from_json(body: ProjectBriefIn, request: Request):
    """Create a project and all its slides from a multi-slide JSON brief."""
    orchestrator = request.app.state.orchestrator
    projects_dir = _projects_dir(request)
    base = str(request.base_url).rstrip("/")

    project = Project(name=body.project_name, source="json")

    for i, slide_brief in enumerate(body.slides):
        draft = await orchestrator.create_draft(slide_brief)
        project.slides.append(ProjectSlide(
            draft_id=str(draft.id),
            title=draft.game_name,
            preview_key=draft.preview_asset_key,
        ))

    await _save_project(projects_dir, project)
    return _project_to_dict(project, base)


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request):
    projects_dir = _projects_dir(request)
    project = await _load_project(projects_dir, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_dict(project, str(request.base_url).rstrip("/"))


class PatchProjectBody(BaseModel):
    name: str | None = None


@router.patch("/{project_id}")
async def update_project(project_id: str, body: PatchProjectBody, request: Request):
    projects_dir = _projects_dir(request)
    project = await _load_project(projects_dir, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.name is not None:
        project.name = body.name
    project.touch()
    await _save_project(projects_dir, project)
    return _project_to_dict(project, str(request.base_url).rstrip("/"))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request):
    projects_dir = _projects_dir(request)
    if not (projects_dir / f"{project_id}.json").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    await _delete_project_file(projects_dir, project_id)


@router.post("/{project_id}/slides", status_code=201)
async def add_slide(project_id: str, request: Request):
    """Add a new empty slide to an existing project."""
    projects_dir = _projects_dir(request)
    project = await _load_project(projects_dir, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.create_empty_draft(f"Slide {project.slide_count + 1}")

    slide = ProjectSlide(
        draft_id=str(draft.id),
        title=draft.game_name,
        preview_key=draft.preview_asset_key,
    )
    project.slides.append(slide)
    project.touch()
    await _save_project(projects_dir, project)

    base = str(request.base_url).rstrip("/")
    return {
        "draft_id": slide.draft_id,
        "title": slide.title,
        "preview_url": f"{base}/storage/{slide.preview_key}" if slide.preview_key else None,
        "project": _project_to_dict(project, base),
    }


@router.patch("/{project_id}/slides/{draft_id}")
async def update_slide_meta(project_id: str, draft_id: str, request: Request):
    """Sync slide title and preview_key from the latest draft state."""
    projects_dir = _projects_dir(request)
    project = await _load_project(projects_dir, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    orchestrator = request.app.state.orchestrator
    draft = await orchestrator.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    for slide in project.slides:
        if slide.draft_id == draft_id:
            slide.title = draft.game_name
            slide.preview_key = draft.preview_asset_key
            break

    project.touch()
    await _save_project(projects_dir, project)
    return {"ok": True}
