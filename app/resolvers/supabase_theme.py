"""
Supabase theme image resolver.

Loads the theme catalogue from 'Supabase theme.xlsx' at ROOT, matches a game /
concept name to the closest theme by keyword overlap, then downloads the AVIF
image from Supabase and returns it as a 512×512 PNG suitable for use as an
inspiration icon.

Theme catalogue structure (Supabase theme.xlsx):
  ID | Theme                   | Emoji (Supabase public URL to .avif)
  1  | Aeroplane               | https://...ThemeImages/Aeroplane.avif
  …

Matching strategy (highest score wins, ties go to longer theme name):
  For each theme, count how many words from the query appear in the theme label
  (case-insensitive, also checks if the theme word appears in the query).
  A score ≥ 1 is required.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_SIZE = 512
_CORNER_RADIUS = 80


def _load_themes(xlsx_path: Path) -> list[tuple[str, str]]:
    """Return list of (theme_name, url) from the xlsx file."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(xlsx_path)
        ws = wb.active
        themes = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            theme_name = row[1]
            url = row[2]
            if theme_name and url:
                themes.append((str(theme_name), str(url)))
        return themes
    except Exception as exc:
        logger.warning("SupabaseThemeResolver: could not load %s — %s", xlsx_path, exc)
        return []


def _score(query: str, theme: str) -> int:
    """Score how well a query matches a theme label (higher = better)."""
    q_words = set(re.split(r"[\s:/\-_,]+", query.lower()))
    t_words = set(re.split(r"[\s:/\-_,]+", theme.lower()))
    # Count query words that appear in theme words and vice versa
    overlap = len(q_words & t_words)
    # Also reward partial containment (e.g. "Coins" matches "Coin")
    partial = sum(
        1 for qw in q_words for tw in t_words
        if len(qw) >= 3 and len(tw) >= 3 and (qw in tw or tw in qw)
    )
    return overlap + partial


def _best_theme(query: str, themes: list[tuple[str, str]]) -> tuple[str, str] | None:
    if not themes:
        return None
    scored = [(t, u, _score(query, t)) for t, u in themes]
    best = max(scored, key=lambda x: (x[2], len(x[0])))
    if best[2] < 1:
        return None
    return best[0], best[1]


def _avif_to_png(avif_bytes: bytes) -> bytes:
    """Convert AVIF bytes → 512×512 PNG bytes using Pillow."""
    from PIL import Image
    img = Image.open(io.BytesIO(avif_bytes)).convert("RGBA")
    img = img.resize((_SIZE, _SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class SupabaseThemeResolver:
    """
    Matches a name to the closest Supabase theme image and returns it as PNG.
    Returns None if no theme matches or the download fails.
    """

    def __init__(self, store, xlsx_path: Path) -> None:
        self._store = store
        self._themes: list[tuple[str, str]] = _load_themes(xlsx_path)
        logger.info("SupabaseThemeResolver: loaded %d themes", len(self._themes))

    def _cache_key(self, name: str) -> str:
        digest = hashlib.sha256(name.lower().encode()).hexdigest()
        return f"cache/icons/supabase_theme_{digest}.png"

    async def resolve(self, name: str) -> bytes | None:
        cache_key = self._cache_key(name)
        if await self._store.exists(cache_key):
            logger.debug("SupabaseTheme cache hit: %s", name)
            return await self._store.get(cache_key)

        match = _best_theme(name, self._themes)
        if not match:
            logger.info("SupabaseTheme: no theme match for %r", name)
            return None

        theme_name, url = match
        logger.info("SupabaseTheme: %r → theme %r (%s)", name, theme_name, url)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url)
                r.raise_for_status()
                avif_bytes = r.content

            import asyncio, functools
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                None, functools.partial(_avif_to_png, avif_bytes)
            )

            await self._store.put(cache_key, png_bytes, "image/png")
            return png_bytes

        except Exception as exc:
            logger.warning("SupabaseTheme: download/convert failed for %r: %s", url, exc)
            return None
