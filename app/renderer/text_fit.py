"""
Title auto-sizing logic.
Tries max size, wraps to 2 lines, steps down 4px until it fits.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import ImageFont

if TYPE_CHECKING:
    pass


def _load_font(path: Path | None, size: int) -> ImageFont.FreeTypeFont:
    if path and path.exists():
        return ImageFont.truetype(str(path), size)
    # Fallback to Pillow's built-in default (limited but always available)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def measure_text(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_title(
    text: str,
    font_path: Path | None,
    size_range: tuple[int, int],
    max_width: int,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """
    Returns (lines, font) where lines is 1 or 2 strings.
    Tries max size first, wraps on ': ' or space, steps down 4px if needed.
    """
    min_size, max_size = size_range[0], size_range[1]

    for size in range(max_size, min_size - 1, -4):
        font = _load_font(font_path, size)

        # Try single line
        w, _ = measure_text(font, text)
        if w <= max_width:
            return [text], font

        # Try wrapping at ': '
        if ": " in text:
            parts = text.split(": ", 1)
            line1 = parts[0] + ":"
            line2 = parts[1]
            w1, _ = measure_text(font, line1)
            w2, _ = measure_text(font, line2)
            if w1 <= max_width and w2 <= max_width:
                return [line1, line2], font

        # Try wrapping at last space before midpoint
        words = text.split()
        if len(words) >= 2:
            best_split = None
            for i in range(1, len(words)):
                l1 = " ".join(words[:i])
                l2 = " ".join(words[i:])
                w1, _ = measure_text(font, l1)
                w2, _ = measure_text(font, l2)
                if w1 <= max_width and w2 <= max_width:
                    best_split = ([l1, l2], font)
            if best_split:
                return best_split

    # Last resort: use min size, force single line
    font = _load_font(font_path, min_size)
    return [text], font
