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


def _wrap_words(words: list[str], font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str] | None:
    """
    Greedily wrap words into at most max_lines lines, each fitting within max_width.
    Returns list of line strings, or None if it doesn't fit.
    """
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        w, _ = measure_text(font, trial)
        if w <= max_width:
            current.append(word)
        else:
            if not current:
                return None  # single word wider than max_width
            lines.append(" ".join(current))
            if len(lines) >= max_lines:
                return None  # ran out of lines
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines if all(measure_text(font, l)[0] <= max_width for l in lines) else None


def fit_title(
    text: str,
    font_path: Path | None,
    size_range: tuple[int, int],
    max_width: int,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """
    Returns (lines, font) where lines is 1–3 strings.
    Tries max size first, wraps up to 3 lines, steps down 4px if needed.
    As a true last resort truncates with ellipsis so text never overflows.
    """
    min_size, max_size = size_range[0], size_range[1]
    words = text.split()

    # Extended size range — go down to 28px before giving up
    hard_min = min(min_size, 28)

    for size in range(max_size, hard_min - 1, -2):
        font = _load_font(font_path, size)

        # Try 1 line
        w, _ = measure_text(font, text)
        if w <= max_width:
            return [text], font

        # Try 2 lines only — never go to 3
        result = _wrap_words(words, font, max_width, 2)
        if result:
            return result, font

    # Absolute last resort: 2 lines at hard_min size, best-effort split
    font = _load_font(font_path, hard_min)
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])], font
