"""
Parses the slide text format into structured slide data.

Accepted input format (one blank line between slides):

    Coin Load Jam by Kevin Kuelbag
    https://apps.apple.com/us/app/coin-load-jam/id6758344115
    Park Match by Supersonic + Coins

    Pixel Flow by Loom Games
    https://play.google.com/store/apps/details?id=com.example.pixelflow
    Holes + Planet

Rules:
- Line 1: main game  "Name by Publisher"  (publisher optional)
- Line 2: App Store or Play Store URL (used to fetch screenshot)
- Line 3+: inspirations joined into one line, separated by ' + '
- Each inspiration: "Game Name by Publisher"  OR  just "Game Name" (concept)
- Also accepts the legacy numbered format:
    12) https://play.google.com/...
    Color block jam by rollic + Bus frenzy by crazylabs
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
    store_url: str
    store_type: str          # "appstore" | "playstore" | "unknown"
    app_id: str              # com.example.x  OR  ios_<numeric_id>
    game_name: str
    game_publisher: str | None
    inspirations: list[ParsedInspiration] = field(default_factory=list)

    # Keep backward-compat alias
    @property
    def play_store_url(self) -> str:
        return self.store_url


class TextBriefParseError(ValueError):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def parse_text_brief(text: str) -> list[ParsedSlide]:
    """
    Parse the pasted text into a list of ParsedSlide objects.
    Raises TextBriefParseError on fatal format issues.
    """
    slides: list[ParsedSlide] = []

    blocks = re.split(r"\n{2,}", text.strip())

    for block_idx, block in enumerate(blocks, start=1):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        # Detect format: if the first non-empty line looks like a URL or
        # starts with a slide number, treat as legacy format.
        if _is_url(lines[0]) or re.match(r"^\d+[).\s]", lines[0]):
            slide = _parse_legacy_block(lines, block_idx)
        else:
            slide = _parse_new_block(lines, block_idx)

        slides.append(slide)

    if not slides:
        raise TextBriefParseError("No valid slides found in the pasted text.")

    return slides


# ── New format: Name/URL/Inspirations ────────────────────────────────────────

def _parse_new_block(lines: list[str], block_idx: int) -> ParsedSlide:
    """
    Line 0: "Game Name by Publisher"
    Line 1: store URL
    Line 2+: inspirations (may span multiple lines joined with '+')
    """
    if len(lines) < 3:
        raise TextBriefParseError(
            f"Block {block_idx}: expected at least 3 lines "
            f"(game name · URL · inspirations), got {len(lines)}. "
            f"First line: {lines[0]!r}"
        )

    game_line = lines[0]
    url_line = lines[1]

    if not _is_url(url_line):
        raise TextBriefParseError(
            f"Block {block_idx}: expected a store URL on line 2, got: {url_line!r}"
        )

    # Join remaining lines as inspiration text (supports multi-line input)
    insp_text = " + ".join(lines[2:])

    game_name, game_publisher = _split_name_publisher(game_line)
    store_type, app_id = _classify_url(url_line, block_idx)
    inspirations = _parse_inspirations(insp_text, block_idx)

    return ParsedSlide(
        slide_number=None,
        store_url=url_line,
        store_type=store_type,
        app_id=app_id,
        game_name=game_name,
        game_publisher=game_publisher,
        inspirations=inspirations,
    )


# ── Legacy format: Number/URL/Inspirations ───────────────────────────────────

def _parse_legacy_block(lines: list[str], block_idx: int) -> ParsedSlide:
    if len(lines) < 2:
        raise TextBriefParseError(
            f"Block {block_idx}: expected 2+ lines (URL + inspirations), "
            f"got {len(lines)}."
        )

    url_line = lines[0]
    insp_text = " + ".join(lines[1:])

    # Extract optional leading "12)" or "12." prefix
    slide_number: int | None = None
    num_match = re.match(r"^(\d+)[).\s]+", url_line)
    if num_match:
        slide_number = int(num_match.group(1))
        url_line = url_line[num_match.end():].strip()

    store_type, app_id = _classify_url(url_line, block_idx)
    inspirations = _parse_inspirations(insp_text, block_idx)

    return ParsedSlide(
        slide_number=slide_number,
        store_url=url_line,
        store_type=store_type,
        app_id=app_id,
        game_name="",          # will be fetched from store
        game_publisher=None,
        inspirations=inspirations,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _split_name_publisher(line: str) -> tuple[str, str | None]:
    """Split 'Name by Publisher' → (name, publisher). Publisher may be None."""
    m = re.match(r"^(.+?)\s+by\s+(.+)$", line.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return line.strip(), None


def _classify_url(url: str, block_idx: int) -> tuple[str, str]:
    """Return (store_type, app_id). Raises TextBriefParseError if unrecognised."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # Apple App Store: https://apps.apple.com/us/app/name/id1234567890
    if "apple.com" in host:
        m = re.search(r"/id(\d+)", parsed.path)
        if m:
            return "appstore", f"ios_{m.group(1)}"
        raise TextBriefParseError(
            f"Block {block_idx}: could not extract iOS app id from: {url!r}"
        )

    # Google Play Store
    if "play.google.com" in host:
        qs = parse_qs(parsed.query)
        ids = qs.get("id", [])
        if ids:
            return "playstore", ids[0]
        m = re.search(r"[?&]id=([\w.]+)", url)
        if m:
            return "playstore", m.group(1)
        raise TextBriefParseError(
            f"Block {block_idx}: could not extract Play Store app id from: {url!r}"
        )

    raise TextBriefParseError(
        f"Block {block_idx}: unrecognised store URL: {url!r}. "
        "Expected apps.apple.com or play.google.com."
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
        m = re.match(r"^(.+?)\s+by\s+(.+)$", part, re.IGNORECASE)
        if m:
            result.append(ParsedInspiration(
                name=m.group(1).strip(),
                publisher=m.group(2).strip(),
            ))
        else:
            result.append(ParsedInspiration(name=part, publisher=None))

    return result
