"""
Draft Orchestrator.
Ties together: schema validation → icon resolution → rendering → persistence.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path  # noqa: F401 — used in _resolve_screenshot path source

from app.cache import GameAssetCache
from app.config import settings, tokens
from app.renderer.engine import render
from app.resolvers.combined import CombinedIconResolver
from app.resolvers.concept import ConceptIconResolver
from app.resolvers.iconify import IconifyResolver
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


def _fix_l_i_from_slug(game_name: str, slug: str) -> str:
    """
    Fix lowercase-l / uppercase-I confusion in game names using the URL slug.

    Copy-pasted text from some design tools replaces capital 'I' with lowercase
    'l' (e.g. "ldle" instead of "Idle"). The slug is always ASCII-lowercase so
    'idle' vs 'ldle' reveals the mismatch.
    """
    slug_words = slug.replace("-", " ").split()
    name_words = game_name.split()
    if len(slug_words) != len(name_words):
        return game_name
    corrected = []
    for nw, sw in zip(name_words, slug_words):
        # Compare case-insensitively treating l==i
        if nw.lower().replace("l", "i") == sw.replace("l", "i") and nw.lower() != sw:
            # Use slug as authoritative casing source (title-case each word)
            corrected.append(sw.capitalize())
        else:
            corrected.append(nw)
    return " ".join(corrected)


def _gplay_app(app_id: str) -> dict:
    """Synchronous Play Store metadata fetch — run in a thread pool."""
    from google_play_scraper import app as gplay_app  # type: ignore
    return gplay_app(app_id, lang="en", country="us")


class Orchestrator:
    def __init__(self, store: AssetStore, cache: GameAssetCache | None = None) -> None:
        self._store = store
        self._cache = cache
        _itunes = ItunesIconResolver(store, settings.itunes_rate_limit)
        _playstore = PlayStoreIconResolver(store)
        self._icon_resolver = CombinedIconResolver(_itunes, _playstore)
        self._upload = UploadIconResolver(store)
        self._iconify = IconifyResolver(store)
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

        # If screenshot was never fetched, try again now (cache or re-scrape)
        if not draft.screenshot_asset_key and draft.store_app_id and draft.store_type:
            logger.info("Screenshot missing for draft %s — retrying via cache/scrape", draft.id)
            key = await self._get_or_fetch_screenshot(
                app_id=draft.store_app_id,
                store_type=draft.store_type,
                game_name=draft.game_name,
                draft_id=draft.id,
                slug=draft.store_slug,
            )
            if key:
                draft.screenshot_asset_key = key

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
        store_url: str | None = None,
        store_type: str | None = None,
        game_name: str | None = None,
        game_publisher: str | None = None,
    ) -> DraftState:
        """
        Create a draft from a text-brief slide.

        If game_name is provided (new format), skip the Play Store metadata
        lookup and use the supplied name/publisher directly. Otherwise fall
        back to fetching from Google Play (legacy format).

        Supports both App Store and Play Store URLs for screenshot fetching.
        """
        import asyncio
        import functools

        publisher = game_publisher

        if game_name:
            # New format — name/publisher already parsed from text
            logger.info("Using explicit game name %r", game_name)
        else:
            # Legacy format — fetch metadata from Play Store
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

        # Extract slug from store URL for AppMagic fallback
        slug: str | None = None
        if store_url and store_type == "appstore":
            try:
                from app.utils.text_brief_parser import parse_store_url
                slug = parse_store_url(store_url).slug
            except Exception:
                pass

        # Fix l/I confusion: copy-paste from stylised sources often replaces
        # capital I with lowercase l (e.g. "ldle" instead of "Idle").
        # Correct this using the URL slug as ground truth.
        if game_name and slug:
            game_name = _fix_l_i_from_slug(game_name, slug)

        # Fetch screenshot — checks cache first, scrapes + caches on miss
        screenshot_key = await self._get_or_fetch_screenshot(
            app_id=app_id,
            store_type=store_type or "unknown",
            game_name=game_name,
            draft_id=draft_id,
            slug=slug,
        )

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
                # No publisher → try Iconify, fall back to concept placeholder
                icon_bytes = await self._iconify.resolve(name)
                if not icon_bytes:
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
            screenshot_asset_key=screenshot_key,
            inspirations=insps,
            store_app_id=app_id,
            store_type=store_type,
            store_slug=slug,
        )
        await self._render_and_save(draft)
        await self._persist_draft(draft)
        return draft

    async def _get_or_fetch_screenshot(
        self,
        app_id: str,
        store_type: str,
        game_name: str,
        draft_id: uuid.UUID,
        slug: str | None = None,
    ) -> str | None:
        """
        Return an AssetStore key for the game screenshot.

        Priority:
        1. Cache hit  → copy cached file into draft folder and return draft key
        2. Cache miss → scrape URL, download, save to game_cache AND draft folder
        """
        cache_screenshot_key = f"game_cache/{app_id}/screenshot.png"

        # ── 1. Cache hit ──────────────────────────────────────────────────────
        if self._cache:
            entry = await self._cache.get(app_id)
            if entry and entry.get("screenshot_key"):
                cached_key = entry["screenshot_key"]
                if await self._store.exists(cached_key):
                    # Copy into the draft's own key so URLs stay stable
                    draft_key = f"drafts/{draft_id}/screenshot.png"
                    data = await self._store.get(cached_key)
                    await self._store.put(draft_key, data)
                    logger.info("Cache hit for screenshot %r", app_id)
                    return draft_key

        # ── 2. Cache miss — scrape ────────────────────────────────────────────
        screenshot_url = await self._fetch_screenshot_url(app_id, store_type, slug=slug)

        if not screenshot_url:
            logger.warning("No screenshot URL found for %r", app_id)
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(screenshot_url)
                r.raise_for_status()
                img_bytes = r.content
        except Exception as exc:
            logger.warning("Screenshot download failed for %r: %s", app_id, exc)
            return None

        # Reject icon-sized images — screenshots must be at least 200px on the short side
        try:
            import io
            from PIL import Image as _Image
            _img = _Image.open(io.BytesIO(img_bytes))
            _w, _h = _img.size
            if min(_w, _h) < 200:
                logger.warning(
                    "Rejecting %r screenshot — too small (%dx%d), likely an icon",
                    app_id, _w, _h,
                )
                return None
        except Exception:
            pass  # if PIL can't read it, let it fail later at render time

        # Save to persistent game_cache
        await self._store.put(cache_screenshot_key, img_bytes)

        # Save to draft folder
        draft_key = f"drafts/{draft_id}/screenshot.png"
        await self._store.put(draft_key, img_bytes)

        # Update DB cache
        if self._cache:
            await self._cache.put(
                app_id=app_id,
                game_name=game_name,
                store_type=store_type,
                screenshot_key=cache_screenshot_key,
                source="scraped",
            )

        logger.info("Scraped and cached screenshot for %r", app_id)
        return draft_key

    async def save_manual_screenshot(
        self,
        app_id: str,
        game_name: str,
        store_type: str,
        img_bytes: bytes,
    ) -> str:
        """
        Persist a manually-uploaded screenshot to the game cache so future
        slides using the same app_id reuse this image without scraping.
        Returns the cache AssetStore key.
        """
        cache_key = f"game_cache/{app_id}/screenshot.png"
        await self._store.put(cache_key, img_bytes)
        if self._cache:
            await self._cache.put(
                app_id=app_id,
                game_name=game_name,
                store_type=store_type,
                screenshot_key=cache_key,
                source="manual",
            )
        logger.info("Manual screenshot saved to cache for %r (%r)", app_id, game_name)
        return cache_key

    async def _fetch_screenshot_url(self, app_id: str, store_type: str, slug: str | None = None) -> str | None:
        """
        Try to obtain a screenshot URL for the given app.
        - App Store: iTunes API → AppMagic (Playwright)
        - Play Store: google-play-scraper → HTML scrape
        Returns None on failure (non-fatal).
        """
        import asyncio
        import functools

        if store_type == "appstore":
            numeric_id = app_id.removeprefix("ios_")

            # 1. iTunes API
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        "https://itunes.apple.com/lookup",
                        params={"id": numeric_id, "country": "us"},
                    )
                    r.raise_for_status()
                    data = r.json()
                    results = data.get("results", [])
                    if results:
                        entry = results[0]
                        shots = (
                            entry.get("screenshotUrls")
                            or entry.get("ipadScreenshotUrls")
                            or []
                        )
                        if shots:
                            return shots[0]
                        logger.info("iTunes returned no screenshots for %r, trying AppMagic", app_id)
            except Exception as exc:
                logger.warning("iTunes screenshot lookup failed for %r: %s", app_id, exc)

            # 2. AppMagic scrape via Playwright
            url = await self._scrape_appmagic(numeric_id, slug=slug)
            if url:
                return url

            return None

        if store_type == "playstore":
            loop = asyncio.get_event_loop()
            try:
                app_info = await loop.run_in_executor(
                    None, functools.partial(_gplay_app, app_id)
                )
                screenshots = app_info.get("screenshots", [])
                if screenshots:
                    return screenshots[0]
                logger.info("No screenshots from scraper for %r, trying HTML fallback", app_id)
            except Exception as exc:
                logger.warning("Play Store scraper failed for %r: %s — trying HTML fallback", app_id, exc)

            # HTML fallback: fetch Play Store page and extract image URLs directly
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }) as client:
                    r = await client.get(
                        f"https://play.google.com/store/apps/details?id={app_id}",
                        params={"hl": "en"},
                    )
                    r.raise_for_status()
                    # Play Store embeds screenshot URLs as play-lh.googleusercontent.com with size suffix
                    matches = re.findall(
                        r'https://play-lh\.googleusercontent\.com/[A-Za-z0-9_\-]+=w\d+-h\d+',
                        r.text,
                    )
                    # Filter out small icons (icons are typically square, screenshots are landscape)
                    for url in matches:
                        m = re.search(r'=w(\d+)-h(\d+)', url)
                        if m:
                            w, h = int(m.group(1)), int(m.group(2))
                            if max(w, h) >= 400:
                                # Bump to higher resolution
                                hq_url = re.sub(r'=w\d+-h\d+', '=w1080-h1920', url)
                                logger.info("Play Store HTML screenshot for %r: %s", app_id, hq_url)
                                return hq_url
            except Exception as exc:
                logger.warning("Play Store HTML fallback failed for %r: %s", app_id, exc)
            return None

        return None

    async def _scrape_appmagic(self, numeric_id: str, slug: str | None = None) -> str | None:
        """
        Scrape a screenshot URL from AppMagic using Playwright (headless Chromium).
        AppMagic is a JS-rendered Angular SPA — plain HTTP returns no image data.

        Constructs the AppMagic URL from the iTunes numeric ID (and slug if available).
        Extracts images.appmagic.rocks proxy URLs, decodes the underlying mzstatic URL,
        and bumps the resolution to full-height.
        """
        import asyncio
        import functools
        from urllib.parse import urlparse, parse_qs

        # Build AppMagic URL — slug is optional, ID alone works via redirect
        if slug:
            appmagic_url = f"https://appmagic.rocks/ipad/{slug}/{numeric_id}"
        else:
            appmagic_url = f"https://appmagic.rocks/ipad/app/{numeric_id}"

        def _extract_screenshot_from_page(page) -> str | None:
            """Extract best mzstatic screenshot URL from a loaded AppMagic page."""
            imgs = page.query_selector_all('img[src*="images.appmagic.rocks"]')
            for img in imgs:
                src = img.get_attribute("src") or ""
                if "images.appmagic.rocks" not in src:
                    continue
                qs = parse_qs(urlparse(src).query)
                mzstatic = (qs.get("uri") or [""])[0]
                if not mzstatic or "mzstatic.com" not in mzstatic:
                    continue
                size_match = re.search(r'/0x(\d+)h', mzstatic)
                if size_match and int(size_match.group(1)) < 200:
                    continue
                return re.sub(r'/0x\d+h\.jpg$', '/0x1920h.jpg', mzstatic)
            return None

        def _playwright_scrape() -> str | None:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    # Try ipad then iphone platform paths
                    platforms = ["ipad", "iphone"]
                    if slug:
                        urls = [f"https://appmagic.rocks/{pl}/{slug}/{numeric_id}" for pl in platforms]
                    else:
                        urls = [f"https://appmagic.rocks/{pl}/app/{numeric_id}" for pl in platforms]

                    result = None
                    for url in urls:
                        try:
                            page = browser.new_page()
                            # Use 'load' + short networkidle wait — avoids infinite SPA hangs
                            page.goto(url, wait_until="load", timeout=45000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                pass  # networkidle optional
                            result = _extract_screenshot_from_page(page)
                            page.close()
                            if result:
                                break
                        except Exception as exc:
                            logger.debug("AppMagic %s failed for id=%r: %s", url, numeric_id, exc)
                            try:
                                page.close()
                            except Exception:
                                pass

                    browser.close()
                    return result
            except Exception as exc:
                logger.warning("AppMagic Playwright scrape failed for id=%r: %s", numeric_id, exc)
                return None

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _playwright_scrape)
        if result:
            logger.info("AppMagic screenshot for id=%r: %s", numeric_id, result)
        else:
            logger.info("AppMagic returned no screenshots for id=%r", numeric_id)
        return result

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
            icon_bytes = await self._iconify.resolve(icon_src.name)
            if not icon_bytes:
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
            "screenshot_transform": {
                "x": draft.ss_x,
                "y": draft.ss_y,
                "width": draft.ss_width,
            },
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
