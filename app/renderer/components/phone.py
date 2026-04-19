"""
Screenshot card component.
Renders the game screenshot as a rounded rectangle with a black stroke
on the right side of the canvas — no phone frame.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw


def render(img: Image.Image, tokens: Any, ctx: dict) -> None:
    pm = tokens.get("layout", "phone_mockup")

    # Token defaults — overridden per-draft via ctx["screenshot_transform"]
    x_start: int = pm["x_start"]
    y_start: int = pm["y_start"]
    card_w: int = pm["width"]
    corner_r: int = pm.get("screenshot_corner_radius", 40)
    stroke: int = pm.get("screenshot_stroke", 6)
    bottom_margin: int = pm.get("bottom_margin", 40)

    # Per-draft overrides passed in from the orchestrator
    xform: dict = ctx.get("screenshot_transform", {})
    if xform.get("x") is not None:
        x_start = xform["x"]
    if xform.get("y") is not None:
        y_start = xform["y"]
    if xform.get("width") is not None:
        card_w = xform["width"]

    card_h = tokens.canvas_height - y_start - bottom_margin

    screenshot_data: bytes | None = ctx.get("screenshot_bytes")

    # ── Build card image ─────────────────────────────────────────────────────
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))

    if screenshot_data:
        try:
            ss = Image.open(BytesIO(screenshot_data)).convert("RGBA")

            # Center-crop to fill the card exactly
            ss_ratio = ss.width / ss.height
            target_ratio = card_w / card_h
            if ss_ratio > target_ratio:
                new_h = ss.height
                new_w = int(new_h * target_ratio)
                left = (ss.width - new_w) // 2
                ss = ss.crop((left, 0, left + new_w, new_h))
            else:
                new_w = ss.width
                new_h = int(new_w / target_ratio)
                top = (ss.height - new_h) // 2
                ss = ss.crop((0, top, new_w, top + new_h))

            ss = ss.resize((card_w, card_h), Image.LANCZOS)

            # Apply rounded-corner mask to screenshot
            mask = Image.new("L", (card_w, card_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, card_w - 1, card_h - 1], radius=corner_r, fill=255
            )
            card.paste(ss, (0, 0))
            card.putalpha(mask)
        except Exception:
            pass  # leave card transparent if screenshot fails

    # ── Draw black stroke on top ─────────────────────────────────────────────
    if stroke > 0:
        bd = ImageDraw.Draw(card)
        bd.rounded_rectangle(
            [0, 0, card_w - 1, card_h - 1],
            radius=corner_r,
            outline="#000000",
            width=stroke,
        )

    # ── Paste card onto canvas ───────────────────────────────────────────────
    img.paste(card, (x_start, y_start), card)
