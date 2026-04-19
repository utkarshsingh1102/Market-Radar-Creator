"""
Main render() function.
Composes all four components onto a 1080×1080 canvas.

ctx shape:
    game_name: str
    publisher: str
    inspirations: list[dict]   # {name, publisher, icon_bytes}
    screenshot_bytes: bytes | None
    assets_root: str | Path
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import load_tokens
from app.renderer.components import header, inspirations, phone, title


def render(ctx: dict, tokens: Any = None, output_path: Path | None = None) -> bytes:
    """
    Render a 1080×1080 PNG from ctx.
    Returns raw PNG bytes. Optionally writes to output_path.
    """
    # Always reload tokens from disk so YAML edits take effect without restart
    tokens = load_tokens()

    # Ensure assets_root is set
    if "assets_root" not in ctx:
        ctx = {**ctx, "assets_root": str(Path(__file__).resolve().parent.parent.parent / "assets")}

    # ── Create canvas ────────────────────────────────────────────────────────
    w = tokens.canvas_width
    h = tokens.canvas_height
    bg = tokens.canvas_background

    # Try to load background image asset, fall back to solid colour
    bg_path = Path(ctx["assets_root"]) / "background" / "market_radar_bg.png"
    if bg_path.exists():
        img = Image.open(bg_path).convert("RGB").resize((w, h), Image.LANCZOS)
    else:
        img = Image.new("RGB", (w, h), bg)

    # ── Render components ────────────────────────────────────────────────────
    # Header (NextBigGames pill + LinkedIn + avatar) is already baked into
    # the background PNG — skip rendering it again.
    title.render(img, tokens, ctx)
    inspirations.render(img, tokens, ctx)
    phone.render(img, tokens, ctx)

    # ── Encode ───────────────────────────────────────────────────────────────
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=False)
    png_bytes = buf.getvalue()

    if output_path:
        Path(output_path).write_bytes(png_bytes)

    return png_bytes
