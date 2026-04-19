"""
Draft Orchestrator.
Ties together: schema validation → icon resolution → rendering → persistence.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path  # noqa: F401 — used in _resolve_screenshot path source

from app.config import settings, tokens
from app.renderer.engine import render
from app.resolvers.combined import CombinedIconResolver
from app.resolvers.concept import ConceptIconResolver
from app.resolvers.itunes import ItunesIconResolver
from app.resolvers.playstore import PlayStoreIconResolver
from app.resolvers.upload import UploadIconResolver
from app.schemas import (
    BriefIn,
    DraftState,
    IconStatus,
    InspirationDraft,
    MetaIn,
)
from app.storage.base import AssetStore

logger = logging.getLogger(__name__)


def _gplay_app(app_id: str) -> dict:
    """Synchronous Play Store metadata fetch — run in a thread pool."""
    from google_play_scraper import app as gplay_app  # type: ignore
    return gplay_app(app_id, lang="en", country="us")


class Orchestrator:
    def __init__(self, store: AssetStore) -> None:
        self._store = store
        _itunes = ItunesIconResolver(store, settings.itunes_rate_limit)
        _playstore = PlayStoreIconResolver(store)
        self._icon_resolver = CombinedIconResolver(_itunes, _playstore)
        self._upload = UploadIconResolver(store)
        self._concept = ConceptIconResolver(store)

    # ── Draft lifecycle ───────────────────────────────────────────────────────

    async def create_draft(self, brief: BriefIn) -> DraftState:
        """Resolve icons, render preview, persist draft. Returns DraftState."""
        draft_id = uuid.uuid4()

        # Resolve main screenshot
        screenshot_key = await self._resolve_screenshot(brief, draft_id)

        # Resolve inspiration icons
        insps: list[InspirationDraft] = []
        for i, insp in enumerate(brief.inspirations):
            icon_bytes, icon_key, status = await self._resolve_icon(insp.icon, draft_id, i)
            insps.append(
                InspirationDraft(
                    name=insp.name,
                    publisher=insp.publisher,
                    icon_status=status,
                    icon_asset_key=icon_key,
                )
            )

        draft = DraftState(
            id=draft_id,
            game_name=brief.main_game.name,
            publisher=brief.main_game.publisher,
            screenshot_asset_key=screenshot_key,
            inspirations=insps,
            meta=brief.meta,
        )

        # Render and persist
        await self._render_and_save(draft)
        await self._persist_draft(draft)
        return draft

    async def update_draft(self, draft: DraftState) -> DraftState:
        """Re-render and re-persist an already-loaded draft."""
        draft.edit_count += 1
        draft.updated_at = datetime.utcnow()
        await self._render_and_save(draft)
        await self._persist_draft(draft)
        return draft

    async def load_draft(self, draft_id: str) -> DraftState | None:
        key = f"drafts/{draft_id}/state.json"
        if not await self._store.exists(key):
            return None
        data = await self._store.get(key)
        return DraftState.model_validate_json(data)

    async def export_draft(self, draft: DraftState) -> bytes:
        """Return final rendered PNG bytes."""
        if draft.preview_asset_key and await self._store.exists(draft.preview_asset_key):
            return await self._store.get(draft.preview_asset_key)
        # Re-render on demand
        return await self._do_render(draft)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def create_draft_from_text_slide(
        self,
        app_id: str,
        inspirations_data: list[dict],  # [{"name": str, "publisher": str|None}]
    ) -> DraftState:
        """
        Fetch the main game details from Google Play by app_id, resolve all
        inspiration icons (auto / concept), render and persist a new draft.
        """
        import asyncio
        import functools

        # Fetch main game metadata from Play Store
        loop = asyncio.get_event_loop()
        try:
            app_info = await loop.run_in_executor(
                None, functools.partial(_gplay_app, app_id)
            )
            game_name = app_info.get("title", app_id)
            publisher = app_info.get("developer", None)
        except Exception as exc:
            logger.warning("Play Store app lookup failed for %r: %s", app_id, exc)
            game_name = app_id
            publisher = None

        draft_id = uuid.uuid4()

        insps: list[InspirationDraft] = []
        for i, insp_data in enumerate(inspirations_data):
            name = insp_data["name"]
            pub = insp_data.get("publisher")

            if pub:
                # Named game with publisher — try app stores
                query = f"{name} {pub}"
                icon_bytes = await self._icon_resolver.resolve(query)
                if icon_bytes:
                    key = f"drafts/{draft_id}/icon_{i}.png"
                    await self._store.put(key, icon_bytes)
                    insps.append(InspirationDraft(
                        name=name, publisher=pub,
                        icon_status=IconStatus.ok, icon_asset_key=key,
                    ))
                else:
                    insps.append(InspirationDraft(
                        name=name, publisher=pub,
                        icon_status=IconStatus.needs_upload,
                    ))
            else:
                # No publisher → concept icon
                icon_bytes = await self._concept.resolve(name)
                key = f"drafts/{draft_id}/icon_{i}.png"
                await self._store.put(key, icon_bytes)
                insps.append(InspirationDraft(
                    name=name, publisher=None,
                    icon_status=IconStatus.ok, icon_asset_key=key,
                ))

        draft = DraftState(
            id=draft_id,
            game_name=game_name,
            publisher=publisher,
            screenshot_asset_key=None,
            inspirations=insps,
        )
        await self._render_and_save(draft)
        await self._persist_draft(draft)
        return draft

    async def create_empty_draft(self, game_name: str = "New Slide") -> DraftState:
        """Create a blank draft (no screenshot, placeholder inspirations)."""
        draft_id = uuid.uuid4()
        insps = [
            InspirationDraft(name="Inspiration 1", icon_status=IconStatus.needs_upload),
            InspirationDraft(name="Inspiration 2", icon_status=IconStatus.needs_upload),
        ]
        draft = DraftState(
            id=draft_id,
            game_name=game_name,
            publisher=None,
            screenshot_asset_key=None,
            inspirations=insps,
        )
        await self._render_and_save(draft)
        await self._persist_draft(draft)
        return draft

    async def _resolve_screenshot(self, brief: BriefIn, draft_id: uuid.UUID) -> str | None:
        src = brief.main_game.screenshot
        if src is None:
            return None
        if src.source == "upload":
            up_key = f"uploads/{src.upload_id}"
            if await self._store.exists(up_key):
                dest_key = f"drafts/{draft_id}/screenshot.png"
                data = await self._store.get(up_key)
                await self._store.put(dest_key, data)
                return dest_key
        elif src.source == "url":
            import httpx
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(src.url)
                    r.raise_for_status()
                    dest_key = f"drafts/{draft_id}/screenshot.png"
                    await self._store.put(dest_key, r.content)
                    return dest_key
            except Exception as e:
                logger.warning("Screenshot URL fetch failed: %s", e)
        elif src.source == "path":
            # Resolve relative to storage/uploads/ — safe, no path traversal
            safe_name = Path(src.path).name  # strip any directory components
            up_key = f"uploads/{safe_name}"
            if await self._store.exists(up_key):
                dest_key = f"drafts/{draft_id}/screenshot.png"
                data = await self._store.get(up_key)
                await self._store.put(dest_key, data)
                return dest_key
            else:
                logger.warning("Screenshot path not found in uploads: %s", src.path)
        return None

    async def _resolve_icon(self, icon_src, draft_id: uuid.UUID, idx: int):
        if icon_src.source == "auto":
            icon_bytes = await self._icon_resolver.resolve(icon_src.query)
            if icon_bytes:
                key = f"drafts/{draft_id}/icon_{idx}.png"
                await self._store.put(key, icon_bytes)
                return icon_bytes, key, IconStatus.ok
            return None, None, IconStatus.needs_upload
        elif icon_src.source == "upload":
            icon_bytes = await self._upload.resolve(icon_src.upload_id)
            if icon_bytes:
                key = f"drafts/{draft_id}/icon_{idx}.png"
                await self._store.put(key, icon_bytes)
                return icon_bytes, key, IconStatus.ok
            return None, None, IconStatus.needs_upload
        elif icon_src.source == "concept":
            icon_bytes = await self._concept.resolve(icon_src.name)
            key = f"drafts/{draft_id}/icon_{idx}.png"
            await self._store.put(key, icon_bytes)
            return icon_bytes, key, IconStatus.ok
        return None, None, IconStatus.needs_upload

    async def _do_render(self, draft: DraftState) -> bytes:
        # Build render context
        inspirations_ctx = []
        for insp in draft.inspirations:
            icon_bytes = None
            if insp.icon_asset_key and await self._store.exists(insp.icon_asset_key):
                icon_bytes = await self._store.get(insp.icon_asset_key)
            inspirations_ctx.append({
                "name": insp.name,
                "publisher": insp.publisher,
                "icon_bytes": icon_bytes,
            })

        screenshot_bytes = None
        if draft.screenshot_asset_key and await self._store.exists(draft.screenshot_asset_key):
            screenshot_bytes = await self._store.get(draft.screenshot_asset_key)

        ctx = {
            "game_name": draft.game_name,
            "publisher": draft.publisher or "",
            "inspirations": inspirations_ctx,
            "screenshot_bytes": screenshot_bytes,
            "assets_root": str(settings.assets_root),
        }
        return render(ctx, tokens)

    async def _render_and_save(self, draft: DraftState) -> None:
        png_bytes = await self._do_render(draft)
        key = f"drafts/{draft.id}/preview_v{draft.edit_count}.png"
        await self._store.put(key, png_bytes, "image/png")
        draft.preview_asset_key = key

    async def _persist_draft(self, draft: DraftState) -> None:
        key = f"drafts/{draft.id}/state.json"
        await self._store.put(key, draft.model_dump_json().encode())
