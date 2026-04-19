"""
Parses the numbered slide text format into structured slide data.

Expected input format (one blank line between slides):

    12) https://play.google.com/store/apps/details?id=com.adengames.colorrushmania
    Color block jam by rollic + Bus frenzy by crazylabs

    13) https://play.google.com/store/apps/details?id=com.adengames.boxqueue
    Coffee mania by crazylabs + Packing

Rules:
- Line 1: optional slide number + Play Store URL
- Line 2: inspirations separated by ' + '
- Each inspiration: "Game Name by Publisher"  OR  just "Game Name" (concept)
- A concept has no publisher and isn't expected to be in any app store
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse


@dataclass
class ParsedInspiration:
    name: str
    publisher: str | None  # None → treat as concept


@dataclass
class ParsedSlide:
    slide_number: int | None
    play_store_url: str
    app_id: str                          # com.example.mygame
    inspirations: list[ParsedInspiration] = field(default_factory=list)


class TextBriefParseError(ValueError):
    pass


def parse_text_brief(text: str) -> list[ParsedSlide]:
    """
    Parse the pasted text into a list of ParsedSlide objects.
    Raises TextBriefParseError on fatal format issues.
    """
    slides: list[ParsedSlide] = []

    # Split into blocks separated by one or more blank lines
    blocks = re.split(r"\n{2,}", text.strip())

    for block_idx, block in enumerate(blocks, start=1):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            raise TextBriefParseError(
                f"Block {block_idx}: expected 2 lines (URL line + inspirations line), "
                f"got {len(lines)}."
            )

        url_line = lines[0]
        insp_line = lines[1]

        # Extract optional leading "12)" or "12." prefix
        slide_number: int | None = None
        num_match = re.match(r"^(\d+)[).\s]+", url_line)
        if num_match:
            slide_number = int(num_match.group(1))
            url_line = url_line[num_match.end():].strip()

        # Validate Play Store URL and extract app id
        app_id = _extract_app_id(url_line, block_idx)

        # Parse inspirations
        inspirations = _parse_inspirations(insp_line, block_idx)

        slides.append(ParsedSlide(
            slide_number=slide_number,
            play_store_url=url_line,
            app_id=app_id,
            inspirations=inspirations,
        ))

    if not slides:
        raise TextBriefParseError("No valid slides found in the pasted text.")

    return slides


def _extract_app_id(url: str, block_idx: int) -> str:
    """Extract app id from a Play Store URL."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        ids = qs.get("id", [])
        if ids:
            return ids[0]
    except Exception:
        pass

    # Fallback: regex match
    m = re.search(r"[?&]id=([\w.]+)", url)
    if m:
        return m.group(1)

    raise TextBriefParseError(
        f"Block {block_idx}: could not extract app id from URL: {url!r}"
    )


def _parse_inspirations(line: str, block_idx: int) -> list[ParsedInspiration]:
    """Split 'Game A by Pub + Game B by Pub + Concept' into ParsedInspiration list."""
    parts = [p.strip() for p in line.split("+") if p.strip()]
    if not parts:
        raise TextBriefParseError(
            f"Block {block_idx}: inspiration line is empty: {line!r}"
        )

    result: list[ParsedInspiration] = []
    for part in parts:
        # "Name by Publisher" — case-insensitive ' by ' separator
        m = re.match(r"^(.+?)\s+by\s+(.+)$", part, re.IGNORECASE)
        if m:
            result.append(ParsedInspiration(
                name=m.group(1).strip(),
                publisher=m.group(2).strip(),
            ))
        else:
            # No publisher → concept
            result.append(ParsedInspiration(name=part, publisher=None))

    return result
