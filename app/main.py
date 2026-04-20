"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api import drafts, edits, exports, uploads, projects as projects_api, validate as validate_api
from app.cache import GameAssetCache
from app.orchestrator import Orchestrator
from app.storage.local import LocalAssetStore
from app.web import routes

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Radar Forge",
    description="Automated 1080×1080 Market Radar post generator for NextBigGames",
    version="0.1.0",
)

# ── State ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    store = LocalAssetStore(settings.storage_root)
    cache = GameAssetCache(settings.storage_root / "game_cache" / "assets.db")
    await cache.init()
    app.state.store = store
    app.state.cache = cache
    app.state.orchestrator = Orchestrator(store, cache)
    logger.info("Market Radar Forge started. Storage: %s", settings.storage_root)


# ── Static file serving (previews, uploads) ───────────────────────────────────
storage_root = settings.storage_root
storage_root.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

static_dir = Path(__file__).parent / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

assets_dir = Path(__file__).resolve().parent.parent / "assets"
assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(drafts.router)
app.include_router(edits.router)
app.include_router(exports.router)
app.include_router(exports.router_bulk)
app.include_router(uploads.router)
app.include_router(projects_api.router)
app.include_router(validate_api.router)
app.include_router(routes.router)
