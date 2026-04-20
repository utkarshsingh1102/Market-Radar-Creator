"""
Pydantic v2 input/output schemas for the Market Radar Forge.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


# ── Icon source ───────────────────────────────────────────────────────────────

class IconSourceAuto(BaseModel):
    source: Literal["auto"]
    query: str = Field(..., min_length=1, description="iTunes search query")


class IconSourceUpload(BaseModel):
    source: Literal["upload"]
    upload_id: str = Field(..., min_length=1)


class IconSourceConcept(BaseModel):
    """Mechanic / theme name with no associated app store entry.
    A placeholder icon will be generated from the name."""
    source: Literal["concept"]
    name: str = Field(..., min_length=1)


IconSource = Annotated[
    IconSourceAuto | IconSourceUpload | IconSourceConcept,
    Field(discriminator="source"),
]


# ── Screenshot source ─────────────────────────────────────────────────────────

class ScreenshotSourceUpload(BaseModel):
    source: Literal["upload"]
    upload_id: str = Field(..., min_length=1)


class ScreenshotSourceUrl(BaseModel):
    source: Literal["url"]
    url: str = Field(..., min_length=1)


class ScreenshotSourcePath(BaseModel):
    source: Literal["path"]
    path: str = Field(..., min_length=1, description=(
        "Filename (or relative path) inside storage/uploads/. "
        "Drop your image there and reference it here, e.g. 'my_game.png'."
    ))


ScreenshotSource = Annotated[
    ScreenshotSourceUpload | ScreenshotSourceUrl | ScreenshotSourcePath,
    Field(discriminator="source"),
]


# ── Inspiration ───────────────────────────────────────────────────────────────

class InspirationIn(BaseModel):
    name: str = Field(..., min_length=1)
    publisher: str | None = None
    icon: IconSource


# ── Main game ─────────────────────────────────────────────────────────────────

class MainGameIn(BaseModel):
    name: str = Field(..., min_length=1)
    publisher: str | None = None
    screenshot: ScreenshotSource | None = None   # optional — can be added later in editor


# ── Meta ─────────────────────────────────────────────────────────────────────

class MetaIn(BaseModel):
    series_number: int | None = None
    output_filename: str | None = None


# ── Top-level brief ───────────────────────────────────────────────────────────

class BriefIn(BaseModel):
    main_game: MainGameIn
    inspirations: Annotated[
        list[InspirationIn],
        Field(min_length=2, max_length=4, description="2–4 inspiration games"),
    ]
    meta: MetaIn = Field(default_factory=MetaIn)


# ── Draft (persisted state) ───────────────────────────────────────────────────

class IconStatus(str, Enum):
    ok = "ok"
    needs_upload = "needs_upload"
    fetching = "fetching"
    error = "error"


class InspirationDraft(BaseModel):
    name: str
    publisher: str | None = None
    icon_status: IconStatus = IconStatus.needs_upload
    icon_asset_key: str | None = None   # key in AssetStore


class DraftState(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    edit_count: int = 0

    game_name: str
    publisher: str | None = None
    screenshot_asset_key: str | None = None

    inspirations: list[InspirationDraft]
    meta: MetaIn = Field(default_factory=MetaIn)

    preview_asset_key: str | None = None

    # Per-draft screenshot position/size overrides (None = use design_tokens defaults)
    ss_x: int | None = None
    ss_y: int | None = None
    ss_width: int | None = None

    # Store metadata — used to re-fetch screenshot if it failed on first attempt
    store_app_id: str | None = None
    store_type: str | None = None   # "appstore" | "playstore"
    store_slug: str | None = None   # App Store URL slug e.g. "skate-boy" (for AppMagic fallback)


# ── Edit payloads ─────────────────────────────────────────────────────────────

class FieldPatch(BaseModel):
    game_name: str | None = None
    publisher: str | None = None
    inspirations: list[dict] | None = None   # partial inspiration updates keyed by index
    ss_x: int | None = None
    ss_y: int | None = None
    ss_width: int | None = None


# ── API responses ─────────────────────────────────────────────────────────────

class DraftResponse(BaseModel):
    id: UUID
    edit_count: int
    game_name: str
    publisher: str | None
    inspirations: list[InspirationDraft]
    preview_url: str
    export_url: str


# ── Multi-slide project brief (for JSON upload) ───────────────────────────────

class ProjectBriefIn(BaseModel):
    """Top-level JSON schema for creating a full project with multiple slides."""
    project_name: str = Field(..., min_length=1)
    slides: list[BriefIn] = Field(..., min_length=1, max_length=10)
