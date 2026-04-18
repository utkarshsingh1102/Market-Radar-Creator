"""Upload-based icon resolver — reads pre-uploaded files from the AssetStore."""
from __future__ import annotations

import logging

from app.resolvers.base import IconResolver
from app.storage.base import AssetStore

logger = logging.getLogger(__name__)


class UploadIconResolver(IconResolver):
    def __init__(self, store: AssetStore) -> None:
        self._store = store

    async def resolve(self, upload_id: str) -> bytes | None:
        key = f"uploads/{upload_id}"
        if await self._store.exists(key):
            return await self._store.get(key)
        logger.warning("Uploaded icon not found: %s", upload_id)
        return None
