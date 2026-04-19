"""Export endpoints — single PNG and bulk PDF/ZIP."""
from __future__ import annotations

import io
import re
import zipfile
from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/drafts", tags=["exports"])


def _safe_name(text: str) -> str:
    return re.sub(r"[^\w\-]+", "-", text.lower()).strip("-") or "slide"


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


# ── Bulk export ───────────────────────────────────────────────────────────────

class BulkExportBody(BaseModel):
    format: str = "png"        # "png" or "pdf"
    draft_ids: List[str]


router_bulk = APIRouter(prefix="/api/projects", tags=["exports"])


@router_bulk.post("/{project_id}/export")
async def bulk_export(project_id: str, body: BulkExportBody, request: Request):
    if body.format not in ("png", "pdf"):
        raise HTTPException(status_code=422, detail="format must be 'png' or 'pdf'")
    if not body.draft_ids:
        raise HTTPException(status_code=422, detail="draft_ids must not be empty")

    orchestrator = request.app.state.orchestrator

    # Load drafts and render PNGs in order
    images: list[tuple[str, bytes]] = []   # (filename, png_bytes)
    for idx, draft_id in enumerate(body.draft_ids, start=1):
        draft = await orchestrator.load_draft(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
        png_bytes = await orchestrator.export_draft(draft)
        fname = f"slide-{idx:02d}-{_safe_name(draft.game_name or 'untitled')}"
        images.append((fname, png_bytes))

    # ── PDF ──────────────────────────────────────────────────────────────────
    if body.format == "pdf":
        from PIL import Image
        pil_images = []
        for _, png_bytes in images:
            pil_images.append(Image.open(io.BytesIO(png_bytes)).convert("RGB"))

        buf = io.BytesIO()
        if len(pil_images) == 1:
            pil_images[0].save(buf, format="PDF")
        else:
            pil_images[0].save(
                buf, format="PDF",
                save_all=True,
                append_images=pil_images[1:],
            )
        pdf_bytes = buf.getvalue()
        filename = f"market-radar-{project_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ── PNG — single file straight download ──────────────────────────────────
    if len(images) == 1:
        fname, png_bytes = images[0]
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{fname}.png"'},
        )

    # ── PNG — multiple files → ZIP ────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, png_bytes in images:
            zf.writestr(f"{fname}.png", png_bytes)
    zip_bytes = zip_buf.getvalue()
    filename = f"market-radar-{project_id[:8]}-slides.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
