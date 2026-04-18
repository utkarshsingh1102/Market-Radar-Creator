"""
Phone mockup component.
Composites a screenshot inside an iPhone frame on the right side of the canvas.
If no frame asset is provided, draws a clean programmatic phone outline.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


def _draw_phone_frame(
    size: tuple[int, int],
    corner_radius: int,
    frame_color: str = "#1A1A1A",
    frame_width: int = 12,
    notch: bool = True,
) -> Image.Image:
    """
    Draw a programmatic iPhone-style frame when no frame asset is available.
    Returns an RGBA image of the given size.
    """
    w, h = size
    frame_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(frame_img)

    # Outer rounded rect (the phone body)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=corner_radius, fill=frame_color)

    # Inner screen area (white background cut-out)
    inset = frame_width
    screen_r = max(corner_radius - inset, 8)
    d.rounded_rectangle(
        [inset, inset, w - 1 - inset, h - 1 - inset],
        radius=screen_r,
        fill=(255, 255, 255, 255),
    )

    # Dynamic Island (notch) — centered top
    if notch:
        notch_w = int(w * 0.28)
        notch_h = int(h * 0.022)
        notch_x = (w - notch_w) // 2
        notch_y = inset + 6
        d.rounded_rectangle(
            [notch_x, notch_y, notch_x + notch_w, notch_y + notch_h],
            radius=notch_h // 2,
            fill=frame_color,
        )

    return frame_img


def render(img: Image.Image, tokens: Any, ctx: dict) -> None:
    pm = tokens.get("layout", "phone_mockup")
    assets_root = Path(ctx.get("assets_root", "assets"))

    x_start: int = pm["x_start"]
    y_start: int = pm["y_start"]
    phone_w: int = pm["width"]
    corner_r: int = pm.get("corner_radius", 48)
    screen_inset_top: int = pm.get("screen_inset_top", 80)
    screen_inset_bottom: int = pm.get("screen_inset_bottom", 40)
    screen_inset_sides: int = pm.get("screen_inset_sides", 20)

    # Phone height: fill remaining canvas height with small bottom margin
    phone_h = tokens.canvas_height - y_start - 40

    screenshot_data: bytes | None = ctx.get("screenshot_bytes")

    # ── Load or draw frame ───────────────────────────────────────────────────
    frame_asset_rel = pm.get("frame_asset", "")
    frame_path = assets_root / frame_asset_rel.replace("assets/", "") if frame_asset_rel else None

    if frame_path and frame_path.exists():
        frame_img = (
            Image.open(frame_path)
            .convert("RGBA")
            .resize((phone_w, phone_h), Image.LANCZOS)
        )
    else:
        frame_img = _draw_phone_frame((phone_w, phone_h), corner_r)

    # ── Screenshot inside frame ──────────────────────────────────────────────
    screen_x = screen_inset_sides
    screen_y = screen_inset_top
    screen_w = phone_w - screen_inset_sides * 2
    screen_h = phone_h - screen_inset_top - screen_inset_bottom

    if screenshot_data:
        try:
            ss = Image.open(BytesIO(screenshot_data)).convert("RGBA")
            # Crop to fill screen area (center crop)
            ss_ratio = ss.width / ss.height
            target_ratio = screen_w / screen_h
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
            ss = ss.resize((screen_w, screen_h), Image.LANCZOS)
            frame_img.paste(ss, (screen_x, screen_y))
        except Exception:
            pass  # leave screen empty if screenshot fails

    # ── Paste phone onto canvas ──────────────────────────────────────────────
    img.paste(frame_img, (x_start, y_start), frame_img)
