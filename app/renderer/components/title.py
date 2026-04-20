"""
Title block component: game name (auto-sized, bold) + underline + publisher line.
"""
from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from app.renderer.text_fit import _load_font, fit_title, measure_text

# Characters that commonly appear in store names but have no glyph in most fonts
_SYMBOL_MAP = {
    "\u2122": "",   # ™
    "\u00ae": "",   # ®
    "\u00a9": "",   # ©
    "\u2019": "'",  # right single quote → apostrophe
    "\u2018": "'",  # left single quote
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2026": "...",# ellipsis
}


def _sanitize_text(text: str) -> str:
    """Replace known symbol characters and strip anything outside Latin-1."""
    for char, replacement in _SYMBOL_MAP.items():
        text = text.replace(char, replacement)
    # Drop any remaining non-Latin-1 characters that the font likely can't render
    return text.encode("latin-1", errors="ignore").decode("latin-1").strip()


def render(img: Image.Image, tokens: Any, ctx: dict) -> None:
    draw = ImageDraw.Draw(img)
    colors = tokens.get("colors")
    layout = tokens.get("layout", "title_block")
    fonts_cfg = tokens.get("fonts")

    left = layout["left_margin"]
    header_layout = tokens.get("layout", "header")
    header_bottom = header_layout["top_margin"] + header_layout["height"]
    top = header_bottom + layout["top_margin"]

    max_width = layout["title_max_width"]
    underline_thickness = layout["underline_thickness"]
    underline_margin = layout["underline_margin_top"]
    underline_width = layout.get("underline_width", max_width)
    publisher_margin = layout.get("publisher_margin_top", 12)

    game_name: str = _sanitize_text(ctx["game_name"])
    publisher: str = _sanitize_text(ctx.get("publisher", ""))

    # ── Title ────────────────────────────────────────────────────────────────
    title_cfg = fonts_cfg["title"]
    size_range = title_cfg["size_range"]
    title_font_path = tokens.font_path("title")
    lines, title_font = fit_title(
        game_name.upper(), title_font_path, tuple(size_range), max_width
    )

    # Measure line height
    sample_bbox = title_font.getbbox("A")
    line_h = sample_bbox[3] - sample_bbox[1]
    line_gap = int(line_h * 0.20)  # comfortable leading between title lines

    # Draw each title line
    y = top
    for line in lines:
        bbox = title_font.getbbox(line)
        draw.text((left - bbox[0], y - bbox[1]), line, font=title_font, fill=colors["text_primary"])
        y += line_h + line_gap

    title_bottom = y - line_gap

    # ── Publisher ────────────────────────────────────────────────────────────
    if publisher:
        subtitle_cfg = fonts_cfg["subtitle"]
        sub_size = subtitle_cfg["size"]
        sub_font_path = tokens.font_path("subtitle")
        sub_font = _load_font(sub_font_path, sub_size)
        pub_text = f"BY {publisher.upper()}"
        pub_bbox = sub_font.getbbox(pub_text)
        draw.text(
            (left - pub_bbox[0], title_bottom + publisher_margin - pub_bbox[1]),
            pub_text,
            font=sub_font,
            fill=colors["text_primary"],
        )
        pub_bottom = title_bottom + publisher_margin + (pub_bbox[3] - pub_bbox[1])
    else:
        pub_bottom = title_bottom

    # ── Underline ────────────────────────────────────────────────────────────
    underline_y = pub_bottom + underline_margin
    draw.rectangle(
        [left, underline_y, left + underline_width, underline_y + underline_thickness],
        fill=colors["underline"],
    )
