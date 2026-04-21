"""
DALL-E icon generator (last-resort fallback).

Uses the OpenAI Images API (DALL-E 3) to generate a 1024×1024 game-style icon
for a given concept/game name, then resizes to 512×512 PNG.

Requires OPENAI_API_KEY to be set (via env or .env file).
Returns None gracefully if the key is missing or the API call fails.
"""
from __future__ import annotations

import hashlib
import io
import logging

import httpx

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "A colorful, flat-design mobile game app icon for a game called '{name}'. "
    "512x512, bold graphic, no text, simple background, vibrant colors, "
    "professional game icon style."
)


async def _generate_dalle_icon(name: str, api_key: str) -> bytes | None:
    prompt = _PROMPT_TEMPLATE.format(name=name)
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "url",
                },
            )
            r.raise_for_status()
            image_url = r.json()["data"][0]["url"]

        async with httpx.AsyncClient(timeout=30) as client:
            img_r = await client.get(image_url)
            img_r.raise_for_status()
            return img_r.content

    except Exception as exc:
        logger.warning("DALL-E generation failed for %r: %s", name, exc)
        return None


def _resize_to_512(png_bytes: bytes) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    img = img.resize((512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class DalleIconResolver:
    """
    Generates a game icon via DALL-E 3.
    Returns None if api_key is absent or generation fails.
    """

    def __init__(self, store, api_key: str | None) -> None:
        self._store = store
        self._api_key = api_key or ""

    def _cache_key(self, name: str) -> str:
        digest = hashlib.sha256(name.lower().encode()).hexdigest()
        return f"cache/icons/dalle_{digest}.png"

    async def resolve(self, name: str) -> bytes | None:
        if not self._api_key:
            logger.debug("DalleIconResolver: no API key configured, skipping")
            return None

        cache_key = self._cache_key(name)
        if await self._store.exists(cache_key):
            logger.debug("DALL-E cache hit: %s", name)
            return await self._store.get(cache_key)

        logger.info("DALL-E: generating icon for %r", name)
        raw = await _generate_dalle_icon(name, self._api_key)
        if not raw:
            return None

        import asyncio, functools
        loop = asyncio.get_event_loop()
        png_bytes = await loop.run_in_executor(
            None, functools.partial(_resize_to_512, raw)
        )

        await self._store.put(cache_key, png_bytes, "image/png")
        logger.info("DALL-E: icon generated and cached for %r", name)
        return png_bytes
