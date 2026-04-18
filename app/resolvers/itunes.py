"""
iTunes Search API icon resolver.
Queries https://itunes.apple.com/search for the app icon (artworkUrl512).
Caches results via the AssetStore under cache/icons/{sha256}.png.
"""
from __future__ import annotations

import hashlib
import logging
import time

import httpx

from app.resolvers.base import IconResolver
from app.storage.base import AssetStore

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
_last_request_times: list[float] = []


async def _rate_limit(requests_per_minute: int) -> None:
    """Sliding window rate limiter."""
    now = time.monotonic()
    # Remove timestamps older than 60 seconds
    global _last_request_times
    _last_request_times = [t for t in _last_request_times if now - t < 60]
    if len(_last_request_times) >= requests_per_minute:
        import asyncio
        sleep_for = 60 - (now - _last_request_times[0]) + 0.1
        if sleep_for > 0:
            logger.debug("iTunes rate limit: sleeping %.1fs", sleep_for)
            await asyncio.sleep(sleep_for)
    _last_request_times.append(time.monotonic())


class ItunesIconResolver(IconResolver):
    def __init__(
        self,
        store: AssetStore,
        requests_per_minute: int = 20,
        timeout: float = 10.0,
    ) -> None:
        self._store = store
        self._rpm = requests_per_minute
        self._timeout = timeout

    def _cache_key(self, query: str) -> str:
        digest = hashlib.sha256(query.lower().encode()).hexdigest()
        return f"cache/icons/{digest}.png"

    async def resolve(self, query: str) -> bytes | None:
        cache_key = self._cache_key(query)

        # Cache hit
        if await self._store.exists(cache_key):
            logger.debug("Icon cache hit: %s", query)
            return await self._store.get(cache_key)

        # Fetch from iTunes
        await _rate_limit(self._rpm)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    ITUNES_SEARCH_URL,
                    params={"term": query, "entity": "software", "limit": 5},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("iTunes search failed for %r: %s", query, exc)
            return None

        results = data.get("results", [])
        if not results:
            logger.info("No iTunes results for %r", query)
            return None

        # Download top result's artwork
        artwork_url = results[0].get("artworkUrl512") or results[0].get("artworkUrl100")
        if not artwork_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                img_resp = await client.get(artwork_url)
                img_resp.raise_for_status()
                icon_bytes = img_resp.content
        except Exception as exc:
            logger.warning("Artwork download failed for %r: %s", artwork_url, exc)
            return None

        # Cache it
        await self._store.put(cache_key, icon_bytes, "image/png")
        logger.info("Fetched and cached icon for %r (%d bytes)", query, len(icon_bytes))
        return icon_bytes
