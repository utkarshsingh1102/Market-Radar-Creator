"""
Parses the slide text format into structured slide data.

Accepted input format — each slide is exactly 3 consecutive lines,
blank lines between slides are optional:

    Coin Load Jam by Kevin Kuelbag
    https://apps.apple.com/us/app/coin-load-jam/id6758344115
    Park Match by Supersonic + Coins
    Planets (game) by Oksana Voloshyna
    https://apps.apple.com/us/app/planets-game/id6761521229
    Pixel Flow by Loom Games + Holes + Planet

Rules:
- Line 1: main game  "Name by Publisher"  (publisher optional)
- Line 2: App Store or Play Store URL
- Line 3: inspirations separated by ' + '
- Each inspiration: "Game Name by Publisher"  OR  just "Game Name" (concept)

Also accepts the legacy numbered format (URL on line 1):
    12) https://play.google.com/...
    Color block jam by rollic + Bus frenzy
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

    # Backward-compat alias
    @property
    def play_store_url(self) -> str:
        return self.store_url


class TextBriefParseError(ValueError):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def parse_text_brief(text: str) -> list[ParsedSlide]:
    """
    Parse the pasted text into a list of ParsedSlide objects.

    Strategy:
    1. Strip blank lines so we get a flat list of non-empty lines.
    2. Walk the list and group into 3-line blocks by detecting the URL line
       (position 1 within each group). Each block is: name → URL → inspirations.
    3. If the first non-empty line looks like a URL or has a slide-number prefix,
       fall into legacy mode for that block.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise TextBriefParseError("No content found in the pasted text.")

    # Check if first line is legacy format (URL or numbered)
    if _is_url(lines[0]) or re.match(r"^\d+[).\s]", lines[0]):
        return _parse_legacy(lines)

    return _parse_new(lines)


# ── New format: triplets of (name, URL, inspirations) ────────────────────────

def _parse_new(lines: list[str]) -> list[ParsedSlide]:
    """
    Group consecutive lines into 3-line blocks: name → URL → inspirations.
    The URL is always line index 1 within a block; we use that as the anchor.
    """
    slides: list[ParsedSlide] = []
    i = 0
    block_idx = 0

    while i < len(lines):
        block_idx += 1

        # Find the URL line — it should be the next line after a non-URL line
        # Tolerate occasional blank remnants already stripped.
        name_line = lines[i]

        if _is_url(name_line):
            # Unexpected URL where we expected a name — skip
            i += 1
            continue

        # The URL must be the very next line
        if i + 1 >= len(lines):
            raise TextBriefParseError(
                f"Block {block_idx}: game line {name_line!r} has no following URL."
            )

        url_line = lines[i + 1]
        if not _is_url(url_line):
            raise TextBriefParseError(
                f"Block {block_idx}: expected a store URL after {name_line!r}, "
                f"got: {url_line!r}"
            )

        if i + 2 >= len(lines):
            raise TextBriefParseError(
                f"Block {block_idx}: no inspirations line after URL {url_line!r}."
            )

        insp_line = lines[i + 2]
        if _is_url(insp_line):
            raise TextBriefParseError(
                f"Block {block_idx}: expected inspirations after URL but got another URL: {insp_line!r}"
            )

        game_name, game_publisher = _split_name_publisher(name_line)
        store_type, app_id = _classify_url(url_line, block_idx)
        inspirations = _parse_inspirations(insp_line, block_idx)

        slides.append(ParsedSlide(
            slide_number=None,
            store_url=url_line,
            store_type=store_type,
            app_id=app_id,
            game_name=game_name,
            game_publisher=game_publisher,
            inspirations=inspirations,
        ))

        i += 3  # advance by exactly one 3-line block

    if not slides:
        raise TextBriefParseError("No valid slides found in the pasted text.")

    return slides


# ── Legacy format: URL first, then inspirations ───────────────────────────────

def _parse_legacy(lines: list[str]) -> list[ParsedSlide]:
    """Original format: optional number + URL on line 1, inspirations on line 2."""
    slides: list[ParsedSlide] = []
    i = 0
    block_idx = 0

    while i < len(lines):
        block_idx += 1
        url_line = lines[i]

        slide_number: int | None = None
        num_match = re.match(r"^(\d+)[).\s]+", url_line)
        if num_match:
            slide_number = int(num_match.group(1))
            url_line = url_line[num_match.end():].strip()

        if not _is_url(url_line):
            i += 1
            continue

        if i + 1 >= len(lines):
            raise TextBriefParseError(
                f"Block {block_idx}: URL {url_line!r} has no following inspirations line."
            )

        insp_line = lines[i + 1]
        store_type, app_id = _classify_url(url_line, block_idx)
        inspirations = _parse_inspirations(insp_line, block_idx)

        slides.append(ParsedSlide(
            slide_number=slide_number,
            store_url=url_line,
            store_type=store_type,
            app_id=app_id,
            game_name="",
            game_publisher=None,
            inspirations=inspirations,
        ))
        i += 2

    if not slides:
        raise TextBriefParseError("No valid slides found in the pasted text.")

    return slides


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _split_name_publisher(line: str) -> tuple[str, str | None]:
    m = re.match(r"^(.+?)\s+by\s+(.+)$", line.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return line.strip(), None


def _classify_url(url: str, block_idx: int) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "apple.com" in host:
        m = re.search(r"/id(\d+)", parsed.path)
        if m:
            return "appstore", f"ios_{m.group(1)}"
        raise TextBriefParseError(
            f"Block {block_idx}: could not extract iOS app id from: {url!r}"
        )

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
