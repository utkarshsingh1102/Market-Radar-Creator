"""
Concept icon generator.

For inspiration entries that are mechanic/theme names (e.g. "Packing", "Merge",
"Idle") rather than real app store games, this resolver generates a clean
512×512 icon using Pillow: a solid background with the concept's initials or
short label centred in bold text.

The background colour is deterministically derived from the concept name so
the same name always produces the same colour.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Palette of pleasant dark/saturated colours used for backgrounds.
# Chosen to contrast well with white text.
_PALETTE = [
    (0x1A, 0x73, 0xE8),  # Google Blue
    (0xE5, 0x39, 0x35),  # Red
    (0x2E, 0x7D, 0x32),  # Green
    (0x6A, 0x1B, 0x9A),  # Purple
    (0xF5, 0x7C, 0x00),  # Orange
    (0x00, 0x83, 0x8F),  # Teal
    (0xC6, 0x28, 0x28),  # Dark red
    (0x1B, 0x5E, 0x20),  # Dark green
    (0x4A, 0x14, 0x8C),  # Deep purple
    (0x0D, 0x47, 0xA1),  # Dark blue
    (0x37, 0x47, 0x4F),  # Blue-grey
    (0xBF, 0x36, 0x0C),  # Deep orange
]

_SIZE = 512
_CORNER_RADIUS = 80


def _pick_color(name: str) -> Tuple[int, int, int]:
    digest = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
    return _PALETTE[digest % len(_PALETTE)]


def _abbrev(name: str) -> str:
    """
    Return a short label for the icon:
    - 1 word  → first 3 chars uppercased
    - 2 words → initials (e.g. "Box Queue" → "BQ")
    - 3+ words → first 3 initials
    """
    words = [w for w in name.split() if w]
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0].upper() for w in words[:3])


def _rounded_rectangle(draw, xy, radius, fill):
    """Draw a rounded rectangle using Pillow ImageDraw."""
    from PIL import ImageDraw  # local import to keep top-level import-free
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + radius * 2, y0 + radius * 2], fill=fill)
    draw.ellipse([x1 - radius * 2, y0, x1, y0 + radius * 2], fill=fill)
    draw.ellipse([x0, y1 - radius * 2, x0 + radius * 2, y1], fill=fill)
    draw.ellipse([x1 - radius * 2, y1 - radius * 2, x1, y1], fill=fill)


def generate_concept_icon(name: str) -> bytes:
    """
    Return PNG bytes for a concept placeholder icon.
    512×512, rounded corners, solid colour, white abbreviation text.
    """
    from PIL import Image, ImageDraw, ImageFont

    bg_color = _pick_color(name)
    label = _abbrev(name)

    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background
    _rounded_rectangle(draw, [0, 0, _SIZE, _SIZE], _CORNER_RADIUS, bg_color)

    # Try to load a system font; fall back to Pillow default
    font = None
    font_size = 180 if len(label) <= 2 else 140
    for font_path in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except (IOError, OSError):
            continue

    if font is None:
        font = ImageFont.load_default()

    # Centre the text
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (_SIZE - tw) // 2 - bbox[0]
    ty = (_SIZE - th) // 2 - bbox[1]
    draw.text((tx, ty), label, font=font, fill=(255, 255, 255, 230))

    # Add subtle concept label at the bottom
    small_font_size = 48
    small_font = None
    for font_path in [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            small_font = ImageFont.truetype(font_path, small_font_size)
            break
        except (IOError, OSError):
            continue
    if small_font is None:
        small_font = ImageFont.load_default()

    # Truncate long names for bottom label
    bottom_label = name if len(name) <= 12 else name[:11] + "…"
    sbbox = draw.textbbox((0, 0), bottom_label, font=small_font)
    sw = sbbox[2] - sbbox[0]
    draw.text(
        ((_SIZE - sw) // 2, _SIZE - 80),
        bottom_label,
        font=small_font,
        fill=(255, 255, 255, 160),
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class ConceptIconResolver:
    """Generates placeholder icons for concept/mechanic inspiration names."""

    def __init__(self, store) -> None:
        self._store = store

    def _cache_key(self, name: str) -> str:
        digest = hashlib.sha256(name.lower().encode()).hexdigest()
        return f"cache/icons/concept_{digest}.png"

    async def resolve(self, name: str) -> bytes:
        cache_key = self._cache_key(name)
        if await self._store.exists(cache_key):
            logger.debug("Concept icon cache hit: %s", name)
            return await self._store.get(cache_key)

        import asyncio, functools
        loop = asyncio.get_event_loop()
        icon_bytes = await loop.run_in_executor(
            None, functools.partial(generate_concept_icon, name)
        )

        await self._store.put(cache_key, icon_bytes, "image/png")
        logger.info("Generated concept icon for %r (%d bytes)", name, len(icon_bytes))
        return icon_bytes
