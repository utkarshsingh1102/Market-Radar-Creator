"""
Google Play Store icon resolver.
Uses google-play-scraper to search for the app and fetch its icon.
Caches results via the AssetStore under cache/icons/gplay_{sha256}.png.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import logging

import httpx

from app.resolvers.base import IconResolver
from app.storage.base import AssetStore

logger = logging.getLogger(__name__)


class PlayStoreIconResolver(IconResolver):
    def __init__(self, store: AssetStore, timeout: float = 10.0) -> None:
        self._store = store
        self._timeout = timeout

    def _cache_key(self, query: str) -> str:
        digest = hashlib.sha256(query.lower().encode()).hexdigest()
        return f"cache/icons/gplay_{digest}.png"

    async def resolve(self, query: str) -> bytes | None:
        cache_key = self._cache_key(query)

        if await self._store.exists(cache_key):
            logger.debug("Play Store icon cache hit: %s", query)
            return await self._store.get(cache_key)

        # google-play-scraper is synchronous — run in a thread pool
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                functools.partial(
                    _gplay_search, query, n_hits=5, lang="en", country="us"
                ),
            )
        except Exception as exc:
            logger.warning("Play Store search failed for %r: %s", query, exc)
            return None

        if not results:
            logger.info("No Play Store results for %r", query)
            return None

        icon_url = results[0].get("icon")
        if not icon_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(icon_url)
                r.raise_for_status()
                icon_bytes = r.content
        except Exception as exc:
            logger.warning("Play Store icon download failed for %r: %s", icon_url, exc)
            return None

        await self._store.put(cache_key, icon_bytes, "image/png")
        logger.info(
            "Fetched and cached Play Store icon for %r (%d bytes)", query, len(icon_bytes)
        )
        return icon_bytes


def _gplay_search(query: str, **kwargs):
    """Thin wrapper so the import stays inside the thread-pool call."""
    from google_play_scraper import search  # type: ignore
    return search(query, **kwargs)
