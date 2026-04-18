"""Abstract IconResolver interface."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IconResolver(ABC):
    @abstractmethod
    async def resolve(self, query: str) -> bytes | None:
        """
        Return raw PNG/JPEG bytes for the icon, or None if not found.
        Implementations should cache results.
        """
