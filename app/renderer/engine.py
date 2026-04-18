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

from app.config import tokens as default_tokens
from app.renderer.components import header, inspirations, phone, title


def render(ctx: dict, tokens: Any = None, output_path: Path | None = None) -> bytes:
    """
    Render a 1080×1080 PNG from ctx.
    Returns raw PNG bytes. Optionally writes to output_path.
    """
    if tokens is None:
        tokens = default_tokens

    # Ensure assets_root is set
    if "assets_root" not in ctx:
        ctx = {**ctx, "assets_root": str(Path(__file__).resolve().parent.parent.parent / "assets")}

    # ── Create canvas ────────────────────────────────────────────────────────
    w = tokens.canvas_width
    h = tokens.canvas_height
    bg = tokens.canvas_background

    img = Image.new("RGB", (w, h), bg)

    # ── Render components ────────────────────────────────────────────────────
    header.render(img, tokens, ctx)
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
