"""
JSON brief validator.
Returns a structured list of issues (errors and warnings) with clear messages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Issue:
    level: Literal["error", "warning", "info"]
    slide: int | None          # 1-based slide index, None = project-level
    field: str                 # dot-path to the offending field
    message: str               # human-readable message shown to the user
    suggestion: str = ""       # optional fix hint


def validate_brief(data: Any) -> list[Issue]:
    """
    Validate a raw-parsed JSON brief (dict).
    Supports both single-slide format (BriefIn) and multi-slide format (ProjectBriefIn).
    Returns a list of Issue objects.  Empty list = fully valid.
    """
    issues: list[Issue] = []

    if not isinstance(data, dict):
        issues.append(Issue("error", None, "(root)", "JSON must be an object, not a list or primitive."))
        return issues

    # ── Detect format ─────────────────────────────────────────────────────────
    if "slides" in data:
        # Multi-slide project brief
        _validate_project(data, issues)
    elif "main_game" in data:
        # Single-slide brief
        _validate_slide(data, issues, slide_num=1, label="")
    else:
        issues.append(Issue(
            "error", None, "(root)",
            "Unrecognised JSON format. Expected either a single-slide brief with "
            "\"main_game\" and \"inspirations\", or a multi-slide brief with "
            "\"project_name\" and \"slides\".",
            suggestion="Download the sample JSON to see the correct structure.",
        ))

    return issues


# ── Project-level validation ──────────────────────────────────────────────────

def _validate_project(data: dict, issues: list[Issue]) -> None:
    # project_name
    if not data.get("project_name", "").strip():
        issues.append(Issue(
            "error", None, "project_name",
            "\"project_name\" is missing or empty.",
            suggestion="Add a project name, e.g. \"Market Radar #34\".",
        ))

    # slides array
    slides = data.get("slides")
    if not isinstance(slides, list) or len(slides) == 0:
        issues.append(Issue(
            "error", None, "slides",
            "\"slides\" must be a non-empty array.",
            suggestion="Add at least one slide object inside the \"slides\" array.",
        ))
        return

    if len(slides) > 10:
        issues.append(Issue(
            "warning", None, "slides",
            f"You have {len(slides)} slides — maximum supported is 10.",
        ))

    for i, slide in enumerate(slides):
        _validate_slide(slide, issues, slide_num=i + 1, label=f"Slide {i+1}: ")


# ── Per-slide validation ──────────────────────────────────────────────────────

def _validate_slide(data: Any, issues: list[Issue], slide_num: int, label: str) -> None:
    if not isinstance(data, dict):
        issues.append(Issue("error", slide_num, "(slide)", f"{label}Slide must be a JSON object."))
        return

    _validate_main_game(data.get("main_game"), issues, slide_num, label)
    _validate_inspirations(data.get("inspirations"), issues, slide_num, label)


def _validate_main_game(mg: Any, issues: list[Issue], slide_num: int, label: str) -> None:
    if mg is None:
        issues.append(Issue(
            "error", slide_num, "main_game",
            f"{label}\"main_game\" section is missing.",
            suggestion="Add a \"main_game\" object with at least a \"name\" field.",
        ))
        return

    if not isinstance(mg, dict):
        issues.append(Issue("error", slide_num, "main_game", f"{label}\"main_game\" must be a JSON object."))
        return

    # name
    if not mg.get("name", "").strip():
        issues.append(Issue(
            "error", slide_num, "main_game.name",
            f"{label}Game name is missing.",
            suggestion="Add \"name\": \"Your Game Title\" inside \"main_game\".",
        ))

    # publisher (warning, not required)
    if not mg.get("publisher", "").strip():
        issues.append(Issue(
            "warning", slide_num, "main_game.publisher",
            f"{label}Publisher name is missing — it will be left blank on the design.",
            suggestion="Add \"publisher\": \"Studio Name\" inside \"main_game\".",
        ))

    # screenshot (warning — optional but highly recommended)
    ss = mg.get("screenshot")
    if ss is None:
        issues.append(Issue(
            "warning", slide_num, "main_game.screenshot",
            f"{label}No screenshot provided — the phone mockup will be empty.",
            suggestion=(
                "Add a screenshot using one of:\n"
                "  • { \"source\": \"path\", \"path\": \"my_game.png\" }  "
                "    → drop the file in storage/uploads/\n"
                "  • { \"source\": \"upload\", \"upload_id\": \"<id>\" }  "
                "    → pre-upload via the UI\n"
                "  • { \"source\": \"url\", \"url\": \"https://...\" }"
            ),
        ))
    elif isinstance(ss, dict):
        src = ss.get("source")
        if src not in ("upload", "url", "path"):
            issues.append(Issue(
                "error", slide_num, "main_game.screenshot.source",
                f"{label}Screenshot \"source\" must be \"path\", \"upload\", or \"url\".",
            ))
        elif src == "upload" and not ss.get("upload_id", "").strip():
            issues.append(Issue(
                "error", slide_num, "main_game.screenshot.upload_id",
                f"{label}Screenshot source is \"upload\" but \"upload_id\" is empty.",
                suggestion="Upload the image first and paste the returned upload_id here.",
            ))
        elif src == "url" and not ss.get("url", "").strip():
            issues.append(Issue(
                "error", slide_num, "main_game.screenshot.url",
                f"{label}Screenshot source is \"url\" but \"url\" is empty.",
            ))
        elif src == "path" and not ss.get("path", "").strip():
            issues.append(Issue(
                "error", slide_num, "main_game.screenshot.path",
                f"{label}Screenshot source is \"path\" but \"path\" is empty.",
                suggestion="Set \"path\" to the filename you placed in storage/uploads/.",
            ))


def _validate_inspirations(insps: Any, issues: list[Issue], slide_num: int, label: str) -> None:
    if insps is None:
        issues.append(Issue(
            "error", slide_num, "inspirations",
            f"{label}\"inspirations\" section is missing.",
            suggestion="Add an \"inspirations\" array with 2–4 game objects.",
        ))
        return

    if not isinstance(insps, list):
        issues.append(Issue("error", slide_num, "inspirations", f"{label}\"inspirations\" must be an array."))
        return

    count = len(insps)
    if count < 2:
        issues.append(Issue(
            "error", slide_num, "inspirations",
            f"{label}Only {count} inspiration{'s' if count != 1 else ''} found — minimum is 2.",
            suggestion="Add at least 2 inspiration objects to the \"inspirations\" array.",
        ))
    elif count > 4:
        issues.append(Issue(
            "error", slide_num, "inspirations",
            f"{label}{count} inspirations found — maximum is 4.",
            suggestion="Remove inspirations until there are 4 or fewer.",
        ))

    for i, insp in enumerate(insps):
        _validate_single_inspiration(insp, issues, slide_num, label, insp_num=i + 1)


def _validate_single_inspiration(insp: Any, issues: list[Issue], slide_num: int, label: str, insp_num: int) -> None:
    prefix = f"{label}Inspiration {insp_num}: "

    if not isinstance(insp, dict):
        issues.append(Issue("error", slide_num, f"inspirations[{insp_num-1}]", f"{prefix}Must be a JSON object."))
        return

    if not insp.get("name", "").strip():
        issues.append(Issue(
            "error", slide_num, f"inspirations[{insp_num-1}].name",
            f"{prefix}Game name is missing.",
            suggestion=f"Add \"name\": \"Game Title\" to inspiration #{insp_num}.",
        ))

    if not insp.get("publisher", "").strip():
        issues.append(Issue(
            "warning", slide_num, f"inspirations[{insp_num-1}].publisher",
            f"{prefix}Publisher is missing — will be left blank.",
        ))

    icon = insp.get("icon")
    if icon is None:
        issues.append(Issue(
            "error", slide_num, f"inspirations[{insp_num-1}].icon",
            f"{prefix}\"icon\" is missing.",
            suggestion=(
                "Add an icon, e.g.:\n"
                "  { \"source\": \"auto\", \"query\": \"Game Name Publisher\" }"
            ),
        ))
    elif isinstance(icon, dict):
        src = icon.get("source")
        if src not in ("auto", "upload"):
            issues.append(Issue(
                "error", slide_num, f"inspirations[{insp_num-1}].icon.source",
                f"{prefix}Icon \"source\" must be \"auto\" or \"upload\".",
            ))
        elif src == "auto" and not icon.get("query", "").strip():
            issues.append(Issue(
                "warning", slide_num, f"inspirations[{insp_num-1}].icon.query",
                f"{prefix}Auto icon has no search query — iTunes lookup may fail.",
                suggestion=f"Add \"query\": \"{insp.get('name', 'Game')} {insp.get('publisher', '')}\".",
            ))
        elif src == "upload" and not icon.get("upload_id", "").strip():
            issues.append(Issue(
                "error", slide_num, f"inspirations[{insp_num-1}].icon.upload_id",
                f"{prefix}Icon source is \"upload\" but \"upload_id\" is empty.",
                suggestion="Upload the icon image first and paste the upload_id here.",
            ))
