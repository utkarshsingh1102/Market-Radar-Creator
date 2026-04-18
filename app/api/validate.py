"""POST /api/validate-brief — validate a raw JSON brief and return issues."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

from app.utils.validator import validate_brief

router = APIRouter(prefix="/api", tags=["validate"])


class ValidateRequest(BaseModel):
    brief: Any   # raw parsed JSON — we validate structure ourselves


@router.post("/validate-brief")
async def validate_brief_endpoint(body: ValidateRequest):
    issues = validate_brief(body.brief)
    errors   = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    infos    = [i for i in issues if i.level == "info"]

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": [
            {
                "level": i.level,
                "slide": i.slide,
                "field": i.field,
                "message": i.message,
                "suggestion": i.suggestion,
            }
            for i in issues
        ],
    }
