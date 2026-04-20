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
class StoreUrlInfo:
    """
    Parsed and cross-derived store URL info for a single game.

    - For iOS games: numeric_id and slug are populated; appmagic_url is derivable.
    - For Android games: package_id is populated; appmagic_android_url is derivable.
    - Cross-platform (iOS ↔ Android) derivation is NOT possible from URLs alone
      since they use different IDs — that requires a name-based lookup.
    """
    store_type: str           # "appstore" | "playstore" | "appmagic_ios" | "appmagic_android"
    app_id: str               # canonical ID: "ios_<num>" or Play Store package name

    # iOS-specific
    numeric_id: str | None = None     # e.g. "6758454315"
    slug: str | None = None           # e.g. "last-hero-idle-zombie-survive"

    # Android-specific
    package_id: str | None = None     # e.g. "idle.merge.battle.upgrade"

    @property
    def appstore_url(self) -> str | None:
        if self.numeric_id and self.slug:
            return f"https://apps.apple.com/us/app/{self.slug}/id{self.numeric_id}"
        return None

    @property
    def playstore_url(self) -> str | None:
        if self.package_id:
            return f"https://play.google.com/store/apps/details?id={self.package_id}"
        return None

    @property
    def appmagic_url(self) -> str | None:
        """AppMagic URL — iOS variant."""
        if self.numeric_id and self.slug:
            return f"https://appmagic.rocks/ipad/{self.slug}/{self.numeric_id}"
        return None

    @property
    def appmagic_android_url(self) -> str | None:
        """AppMagic URL — Android variant."""
        if self.package_id:
            return f"https://appmagic.rocks/android/{self.package_id}"
        return None

    def all_urls(self) -> dict[str, str | None]:
        return {
            "appstore": self.appstore_url,
            "playstore": self.playstore_url,
            "appmagic_ios": self.appmagic_url,
            "appmagic_android": self.appmagic_android_url,
        }


def parse_store_url(url: str) -> StoreUrlInfo:
    """
    Parse any supported store URL and return a StoreUrlInfo with all
    derivable cross-platform links populated.

    Supported inputs:
      - https://apps.apple.com/us/app/<slug>/id<numeric_id>
      - https://play.google.com/store/apps/details?id=<package>
      - https://appmagic.rocks/ipad/<slug>/<numeric_id>
      - https://appmagic.rocks/android/<package>
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "apple.com" in host:
        m = re.search(r"/app/([^/]+)/id(\d+)", parsed.path)
        if not m:
            raise ValueError(f"Cannot parse App Store URL: {url!r}")
        slug, numeric_id = m.group(1), m.group(2)
        return StoreUrlInfo(
            store_type="appstore",
            app_id=f"ios_{numeric_id}",
            numeric_id=numeric_id,
            slug=slug,
        )

    if "play.google.com" in host:
        qs = parse_qs(parsed.query)
        pkg = (qs.get("id") or [""])[0]
        if not pkg:
            raise ValueError(f"Cannot parse Play Store URL: {url!r}")
        return StoreUrlInfo(
            store_type="playstore",
            app_id=pkg,
            package_id=pkg,
        )

    if "appmagic.rocks" in host:
        # /ipad/<slug>/<numeric_id>  OR  /android/<package>
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 1 and parts[0] == "android":
            pkg = "/".join(parts[1:]) if len(parts) > 1 else ""
            if not pkg:
                raise ValueError(f"Cannot parse AppMagic Android URL: {url!r}")
            return StoreUrlInfo(
                store_type="appmagic_android",
                app_id=pkg,
                package_id=pkg,
            )
        if len(parts) >= 3 and parts[0] in ("ipad", "iphone", "ios"):
            slug, numeric_id = parts[1], parts[2]
            return StoreUrlInfo(
                store_type="appmagic_ios",
                app_id=f"ios_{numeric_id}",
                numeric_id=numeric_id,
                slug=slug,
            )
        raise ValueError(f"Cannot parse AppMagic URL: {url!r}")

    raise ValueError(f"Unrecognised store URL: {url!r}")


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

_STORE_HOSTS = ("apple.com", "play.google.com", "appmagic.rocks")


def _is_url(s: str) -> bool:
    if not (s.startswith("http://") or s.startswith("https://")):
        return False
    host = urlparse(s).netloc.lower()
    return any(h in host for h in _STORE_HOSTS)


def _split_name_publisher(line: str) -> tuple[str, str | None]:
    m = re.match(r"^(.+?)\s+by\s+(.+)$", line.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return line.strip(), None


def _classify_url(url: str, block_idx: int) -> tuple[str, str]:
    try:
        info = parse_store_url(url)
        # Normalise AppMagic types to their canonical store type
        store_type = info.store_type
        if store_type == "appmagic_ios":
            store_type = "appstore"
        elif store_type == "appmagic_android":
            store_type = "playstore"
        return store_type, info.app_id
    except ValueError as exc:
        raise TextBriefParseError(f"Block {block_idx}: {exc}") from exc


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
