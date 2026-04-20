"""
Game Asset Cache — SQLite-backed local cache for screenshots and icons.

Schema (table: game_assets):
  app_id       TEXT PRIMARY KEY   -- "ios_<num>" or Play Store package name
  game_name    TEXT
  store_type   TEXT               -- "appstore" | "playstore" | "manual"
  screenshot_key TEXT             -- AssetStore key, e.g. "game_cache/<app_id>/screenshot.png"
  icon_key     TEXT               -- AssetStore key for app icon
  fetched_at   TEXT               -- ISO-8601 timestamp
  source       TEXT               -- "scraped" | "manual"
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS game_assets (
    app_id         TEXT PRIMARY KEY,
    game_name      TEXT,
    store_type     TEXT,
    screenshot_key TEXT,
    icon_key       TEXT,
    fetched_at     TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'scraped'
);
CREATE INDEX IF NOT EXISTS idx_game_name ON game_assets (game_name COLLATE NOCASE);
"""


class GameAssetCache:
    """
    Thread-safe, async-friendly SQLite cache for game screenshots and icons.

    All blocking SQLite calls are run in an executor so they never block the
    event loop.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _open(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        conn.commit()
        return conn

    async def init(self) -> None:
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, self._open)
        logger.info("Game asset cache opened at %s", self._db_path)

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("GameAssetCache.init() has not been called")
        return self._conn

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, app_id: str) -> dict | None:
        """Return cached entry dict or None."""
        def _query():
            row = self._conn_or_raise().execute(
                "SELECT * FROM game_assets WHERE app_id = ?", (app_id,)
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def get_by_name(self, game_name: str) -> dict | None:
        """Look up by game name (case-insensitive). Returns first match."""
        def _query():
            row = self._conn_or_raise().execute(
                "SELECT * FROM game_assets WHERE game_name = ? COLLATE NOCASE LIMIT 1",
                (game_name,),
            ).fetchone()
            return dict(row) if row else None

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def list_all(self) -> list[dict]:
        """Return all cached entries sorted by game_name."""
        def _query():
            rows = self._conn_or_raise().execute(
                "SELECT * FROM game_assets ORDER BY game_name COLLATE NOCASE"
            ).fetchall()
            return [dict(r) for r in rows]

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    # ── Write ─────────────────────────────────────────────────────────────────

    async def put(
        self,
        app_id: str,
        game_name: str,
        store_type: str,
        screenshot_key: str | None = None,
        icon_key: str | None = None,
        source: str = "scraped",
    ) -> None:
        """Insert or update a cache entry."""
        now = datetime.now(timezone.utc).isoformat()

        def _write():
            conn = self._conn_or_raise()
            conn.execute(
                """
                INSERT INTO game_assets
                    (app_id, game_name, store_type, screenshot_key, icon_key, fetched_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    game_name      = excluded.game_name,
                    store_type     = excluded.store_type,
                    screenshot_key = COALESCE(excluded.screenshot_key, screenshot_key),
                    icon_key       = COALESCE(excluded.icon_key, icon_key),
                    fetched_at     = excluded.fetched_at,
                    source         = excluded.source
                """,
                (app_id, game_name, store_type, screenshot_key, icon_key, now, source),
            )
            conn.commit()

        await asyncio.get_event_loop().run_in_executor(None, _write)
        logger.debug("Cached %r → screenshot=%s icon=%s", app_id, screenshot_key, icon_key)

    async def set_screenshot(self, app_id: str, screenshot_key: str) -> None:
        """Update only the screenshot key for an existing entry."""
        def _write():
            conn = self._conn_or_raise()
            conn.execute(
                "UPDATE game_assets SET screenshot_key = ?, fetched_at = ? WHERE app_id = ?",
                (screenshot_key, datetime.now(timezone.utc).isoformat(), app_id),
            )
            conn.commit()

        await asyncio.get_event_loop().run_in_executor(None, _write)

    async def set_icon(self, app_id: str, icon_key: str) -> None:
        """Update only the icon key for an existing entry."""
        def _write():
            conn = self._conn_or_raise()
            conn.execute(
                "UPDATE game_assets SET icon_key = ?, fetched_at = ? WHERE app_id = ?",
                (icon_key, datetime.now(timezone.utc).isoformat(), app_id),
            )
            conn.commit()

        await asyncio.get_event_loop().run_in_executor(None, _write)

    async def delete(self, app_id: str) -> None:
        def _write():
            conn = self._conn_or_raise()
            conn.execute("DELETE FROM game_assets WHERE app_id = ?", (app_id,))
            conn.commit()

        await asyncio.get_event_loop().run_in_executor(None, _write)
