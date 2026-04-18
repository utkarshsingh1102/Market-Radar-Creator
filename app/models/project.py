"""Project model — groups multiple draft slides into one named project."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectSlide(BaseModel):
    draft_id: str
    title: str = "New Slide"
    preview_key: Optional[str] = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = "ui"          # "json" | "ui"
    json_filename: Optional[str] = None
    slides: list[ProjectSlide] = []

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    @property
    def thumbnail_key(self) -> Optional[str]:
        for s in self.slides:
            if s.preview_key:
                return s.preview_key
        return None
