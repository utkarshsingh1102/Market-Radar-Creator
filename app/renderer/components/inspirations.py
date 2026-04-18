"""
Inspirations left-column component.
Renders icon tiles + "+" separators + text labels using the adaptive layout engine.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from app.renderer.layout import compute_layout
from app.renderer.text_fit import _load_font, measure_text


def _rounded_icon(icon_img: Image.Image, size: int, radius: int) -> Image.Image:
    """Resize icon to square, apply white background tile, round corners."""
    # Create white tile
    tile = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    # Resize icon to fit inside tile with 6px padding
    pad = max(4, size // 16)
    inner_size = size - pad * 2
    icon_resized = icon_img.convert("RGBA").resize((inner_size, inner_size), Image.LANCZOS)
    tile.paste(icon_resized, (pad, pad), icon_resized)

    # Rounded mask
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(tile, mask=mask)
    return result


def _placeholder_icon(size: int, radius: int, color: str = "#E0E0E0") -> Image.Image:
    tile = Image.new("RGBA", (size, size), color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(tile, mask=mask)
    return result


def render(img: Image.Image, tokens: Any, ctx: dict) -> None:
    draw = ImageDraw.Draw(img)
    colors = tokens.get("colors")
    lc_cfg = tokens.get("layout", "left_column")
    fonts_cfg = tokens.get("fonts")

    inspirations: list[dict] = ctx["inspirations"]
    n = len(inspirations)
    icon_radius = lc_cfg["icon_radius"]

    layout = compute_layout(n, tokens)

    # Font sizes keyed by count
    name_sizes: dict = fonts_cfg["inspiration_name"]["size_by_count"]
    pub_sizes: dict = fonts_cfg["inspiration_publisher"]["size_by_count"]
    name_size = int(name_sizes.get(n, name_sizes.get(str(n), 38)))
    pub_size = int(pub_sizes.get(n, pub_sizes.get(str(n), 32)))

    name_font = _load_font(tokens.font_path("inspiration_name"), name_size)
    pub_font = _load_font(tokens.font_path("inspiration_publisher"), pub_size)
    plus_font = _load_font(tokens.font_path("inspiration_name"), layout.plus_rows[0].size if layout.plus_rows else 60)

    for row in layout.icon_rows:
        insp = inspirations[row.index]
        icon_data: bytes | None = insp.get("icon_bytes")

        # Draw icon
        icon_x = int(lc_cfg["x_start"])
        icon_y = int(row.y_center - row.icon_size / 2)

        if icon_data:
            try:
                icon_img = Image.open(BytesIO(icon_data))
                tile = _rounded_icon(icon_img, row.icon_size, icon_radius)
            except Exception:
                tile = _placeholder_icon(row.icon_size, icon_radius)
        else:
            tile = _placeholder_icon(row.icon_size, icon_radius)

        img.paste(tile, (icon_x, icon_y), tile)

        # Draw text to the right of icon
        name_text = insp.get("name", "")
        publisher_text = insp.get("publisher", "")

        name_bbox = name_font.getbbox(name_text) if name_text else (0, 0, 0, 0)
        pub_bbox = pub_font.getbbox(publisher_text) if publisher_text else (0, 0, 0, 0)

        name_h = name_bbox[3] - name_bbox[1]
        pub_h = pub_bbox[3] - pub_bbox[1]
        text_gap = 6

        if publisher_text:
            total_text_h = name_h + text_gap + pub_h
        else:
            total_text_h = name_h

        text_y_start = row.text_y_center - total_text_h / 2

        if name_text:
            draw.text(
                (row.text_x - name_bbox[0], text_y_start - name_bbox[1]),
                name_text,
                font=name_font,
                fill=colors["text_primary"],
            )
        if publisher_text:
            pub_y = text_y_start + name_h + text_gap
            draw.text(
                (row.text_x - pub_bbox[0], pub_y - pub_bbox[1]),
                publisher_text,
                font=pub_font,
                fill=colors["text_primary"],
            )

    # Draw "+" separators
    for pr in layout.plus_rows:
        plus_font_sized = _load_font(tokens.font_path("inspiration_name"), pr.size)
        plus_bbox = plus_font_sized.getbbox("+")
        plus_w = plus_bbox[2] - plus_bbox[0]
        plus_x = lc_cfg["x_start"] + layout.icon_size / 2 - plus_w / 2
        plus_y = pr.y_center - (plus_bbox[3] - plus_bbox[1]) / 2
        draw.text(
            (plus_x - plus_bbox[0], plus_y - plus_bbox[1]),
            "+",
            font=plus_font_sized,
            fill=colors["plus_color"],
        )
