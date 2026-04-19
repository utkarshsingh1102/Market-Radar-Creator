"""
Combined icon resolver: App Store (iTunes) → Play Store → None.
Tries the App Store first (no auth, high quality). Falls back to
Play Store if the App Store returns nothing.
"""
from __future__ import annotations

import logging

from app.resolvers.base import IconResolver
from app.resolvers.itunes import ItunesIconResolver
from app.resolvers.playstore import PlayStoreIconResolver

logger = logging.getLogger(__name__)


class CombinedIconResolver(IconResolver):
    def __init__(
        self,
        itunes: ItunesIconResolver,
        playstore: PlayStoreIconResolver,
    ) -> None:
        self._itunes = itunes
        self._playstore = playstore

    async def resolve(self, query: str) -> bytes | None:
        icon = await self._itunes.resolve(query)
        if icon:
            logger.debug("Icon resolved via App Store for %r", query)
            return icon

        logger.debug("App Store miss for %r, trying Play Store", query)
        icon = await self._playstore.resolve(query)
        if icon:
            logger.debug("Icon resolved via Play Store for %r", query)
        return icon
