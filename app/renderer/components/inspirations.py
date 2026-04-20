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


def _wrap_text(text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    """
    Greedily wrap text into at most max_lines lines, each fitting within max_width.
    Never truncates — last line gets as many words as possible.
    """
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        w, _ = measure_text(font, trial)
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
            if len(lines) >= max_lines - 1:
                # Last allowed line — pack all remaining words in
                remaining = " ".join(current + words[words.index(word) + 1:])
                lines.append(remaining)
                return lines
    if current:
        lines.append(" ".join(current))
    return lines or [text]

# Words that should stay lowercase in title case (unless first word)
_LOWERCASE_WORDS = {"a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "by", "for"}


def _title_case(text: str) -> str:
    """Capitalise first letter of each word, keeping small connector words lowercase."""
    if not text:
        return text
    words = text.split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or word.lower() not in _LOWERCASE_WORDS:
            result.append(word.capitalize())
        else:
            result.append(word.lower())
    return " ".join(result)


def _rounded_icon(icon_img: Image.Image, size: int, radius: int, border: int = 2, border_color: str = "#000000") -> Image.Image:
    """Resize icon to square and apply rounded corners with a border."""
    icon_resized = icon_img.convert("RGBA").resize((size, size), Image.LANCZOS)
    # Rounded mask for icon content
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(icon_resized, mask=mask)
    # Draw border on top
    if border > 0:
        bd = ImageDraw.Draw(result)
        bd.rounded_rectangle(
            [0, 0, size - 1, size - 1],
            radius=radius,
            outline=border_color,
            width=border,
        )
    return result


def _placeholder_icon(size: int, radius: int, color: str = "#CCCCCC", border: int = 2, border_color: str = "#000000") -> Image.Image:
    tile = Image.new("RGBA", (size, size), color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(tile, mask=mask)
    if border > 0:
        bd = ImageDraw.Draw(result)
        bd.rounded_rectangle(
            [0, 0, size - 1, size - 1],
            radius=radius,
            outline=border_color,
            width=border,
        )
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
        max_text_w = int(lc_cfg["x_end"]) - int(row.text_x)
        name_lines = _wrap_text(_title_case(insp.get("name", "")), name_font, max_text_w, max_lines=3)
        raw_pub = insp.get("publisher", "")
        pub_lines = _wrap_text(f"by {raw_pub}", pub_font, max_text_w, max_lines=2) if raw_pub else []

        # Measure line heights
        sample_name_bbox = name_font.getbbox("Ag")
        name_line_h = sample_name_bbox[3] - sample_name_bbox[1]
        name_line_gap = 2

        sample_pub_bbox = pub_font.getbbox("Ag")
        pub_line_h = sample_pub_bbox[3] - sample_pub_bbox[1]
        pub_line_gap = 2

        block_gap = 6  # gap between name block and publisher block

        total_name_h = len(name_lines) * name_line_h + max(0, len(name_lines) - 1) * name_line_gap
        total_pub_h = len(pub_lines) * pub_line_h + max(0, len(pub_lines) - 1) * pub_line_gap
        total_text_h = total_name_h + (block_gap + total_pub_h if pub_lines else 0)

        text_y_start = row.text_y_center - total_text_h / 2

        y = text_y_start
        for line in name_lines:
            bbox = name_font.getbbox(line)
            draw.text(
                (row.text_x - bbox[0], y - bbox[1]),
                line,
                font=name_font,
                fill=colors["text_primary"],
            )
            y += name_line_h + name_line_gap

        y += block_gap - name_line_gap  # replace last line_gap with block_gap
        for line in pub_lines:
            bbox = pub_font.getbbox(line)
            draw.text(
                (row.text_x - bbox[0], y - bbox[1]),
                line,
                font=pub_font,
                fill=colors["text_primary"],
            )
            y += pub_line_h + pub_line_gap

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
