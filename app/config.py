"""
Loads design_tokens.yaml and environment settings.
All renderer code reads from here — zero hardcoded style values elsewhere.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings

ROOT = Path(__file__).resolve().parent.parent
TOKENS_PATH = ROOT / "config" / "design_tokens.yaml"


class Settings(BaseSettings):
    # --- environment ---
    app_env: str = "local"
    storage_backend: str = "local"
    storage_root: Path = ROOT / "storage"
    assets_root: Path = ROOT / "assets"

    # --- S3 (phase 8+) ---
    s3_bucket: str = ""
    s3_region: str = "us-east-1"

    # --- iTunes ---
    itunes_rate_limit: int = 20  # requests/minute

    # --- OpenAI (DALL-E fallback icon generation) ---
    openai_api_key: str = ""

    # --- Supabase theme catalogue ---
    supabase_theme_xlsx: Path = ROOT / "Supabase theme.xlsx"

    # --- database ---
    database_url: str = f"sqlite+aiosqlite:///{ROOT}/storage/drafts.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class DesignTokens:
    """Thin wrapper around the YAML design tokens dict."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, item: str) -> Any:
        try:
            return self._data[item]
        except KeyError:
            raise AttributeError(f"DesignTokens has no attribute '{item}'")

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    @property
    def canvas_width(self) -> int:
        return self._data["canvas"]["width"]

    @property
    def canvas_height(self) -> int:
        return self._data["canvas"]["height"]

    @property
    def canvas_background(self) -> str:
        return self._data["canvas"]["background"]

    def font_path(self, key: str) -> Path:
        """Return absolute path for a font key, or None if not set."""
        rel = self._data.get("fonts", {}).get(key, {}).get("path")
        if not rel:
            return None
        p = ROOT / rel
        return p if p.exists() else None

    def raw(self) -> dict[str, Any]:
        return self._data


def load_tokens(path: Path = TOKENS_PATH) -> DesignTokens:
    """Always reads fresh from disk so token edits take effect without restart."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return DesignTokens(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# settings is a true singleton; tokens are reloaded per render via load_tokens()
settings: Settings = get_settings()
tokens: DesignTokens = load_tokens()  # initial load for import compatibility
