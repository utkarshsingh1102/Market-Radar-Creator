"""
Iconify icon resolver.

Searches the free Iconify API (api.iconify.design) for an icon matching the
game/concept name, downloads the SVG, and rasterises it to a 512×512 PNG
with a rounded coloured background — matching the style of the existing
ConceptIconResolver but with a real thematic icon instead of initials.

No API key required. Rate limit is generous for typical usage.
"""
from __future__ import annotations

import hashlib
import io
import logging

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.iconify.design/search"
_SVG_URL = "https://api.iconify.design/{prefix}/{name}.svg"
_SIZE = 512
_ICON_AREA = 320   # icon drawn inside a 320×320 box, centred on 512×512 canvas
_CORNER_RADIUS = 80

# Palette — same as ConceptIconResolver so colours stay consistent
_PALETTE = [
    (0x1A, 0x73, 0xE8),
    (0xE5, 0x39, 0x35),
    (0x2E, 0x7D, 0x32),
    (0x6A, 0x1B, 0x9A),
    (0xF5, 0x7C, 0x00),
    (0x00, 0x83, 0x8F),
    (0xC6, 0x28, 0x28),
    (0x1B, 0x5E, 0x20),
    (0x4A, 0x14, 0x8C),
    (0x0D, 0x47, 0xA1),
    (0x37, 0x47, 0x4F),
    (0xBF, 0x36, 0x0C),
]


def _pick_color(name: str) -> tuple[int, int, int]:
    digest = int(hashlib.md5(name.lower().encode()).hexdigest(), 16)
    return _PALETTE[digest % len(_PALETTE)]


def _rounded_rectangle(draw, xy, radius, fill):
    from PIL import ImageDraw  # noqa: F401
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + radius * 2, y0 + radius * 2], fill=fill)
    draw.ellipse([x1 - radius * 2, y0, x1, y0 + radius * 2], fill=fill)
    draw.ellipse([x0, y1 - radius * 2, x0 + radius * 2, y1], fill=fill)
    draw.ellipse([x1 - radius * 2, y1 - radius * 2, x1, y1], fill=fill)


def _svg_to_png_bytes(svg_bytes: bytes, size: int) -> bytes:
    import cairosvg
    return cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size)


def _compose_icon(name: str, svg_bytes: bytes) -> bytes:
    """Render SVG onto a coloured rounded-rect background → PNG bytes."""
    from PIL import Image

    bg_color = _pick_color(name)

    # Background canvas
    canvas = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    _rounded_rectangle(draw, [0, 0, _SIZE, _SIZE], _CORNER_RADIUS, bg_color)

    # Rasterise SVG with white fill rewrite so icon is always white on background
    white_svg = svg_bytes.replace(b'currentColor', b'white')
    icon_png = _svg_to_png_bytes(white_svg, _ICON_AREA)
    icon_img = Image.open(io.BytesIO(icon_png)).convert("RGBA")

    # Centre icon on canvas
    offset = (_SIZE - _ICON_AREA) // 2
    canvas.paste(icon_img, (offset, offset), icon_img)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


async def search_iconify(query: str) -> tuple[str, str] | None:
    """
    Search Iconify for icons matching *query*.
    Returns (prefix, icon_name) of the best match, or None.

    Tries progressively shorter queries so "Car theme" → "Car" still finds mdi:car.
    Prefers game-relevant icon sets: game-icons, mdi, fluent-emoji-flat.
    """
    preferred_sets = ["game-icons", "mdi", "fluent-emoji-flat", "noto", "twemoji"]

    # Build candidate queries: full phrase → each individual word (longest first)
    words = query.split()
    candidates = [query] + sorted(set(words), key=len, reverse=True)

    async with httpx.AsyncClient(timeout=10) as client:
        for candidate in candidates:
            if not candidate.strip():
                continue
            r = await client.get(_SEARCH_URL, params={"query": candidate, "limit": 20})
            if r.status_code != 200:
                continue
            icons: list[str] = r.json().get("icons", [])
            if not icons:
                continue

            # Prefer icons from game-relevant sets
            for pref in preferred_sets:
                for icon in icons:
                    if icon.startswith(pref + ":"):
                        prefix, name = icon.split(":", 1)
                        logger.debug("Iconify match for %r via %r: %s:%s", query, candidate, prefix, name)
                        return prefix, name

            # Accept first result from any set
            first = icons[0]
            prefix, name = first.split(":", 1)
            logger.debug("Iconify match for %r via %r: %s:%s", query, candidate, prefix, name)
            return prefix, name

    return None


async def fetch_iconify_svg(prefix: str, name: str) -> bytes | None:
    """Download the SVG bytes for a given icon."""
    url = _SVG_URL.format(prefix=prefix, name=name)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params={"color": "white", "height": str(_ICON_AREA)})
        if r.status_code != 200:
            return None
        return r.content


class IconifyResolver:
    """
    Resolves concept/mechanic names to icons via the Iconify API.
    Falls back gracefully — returns None so the caller can use ConceptIconResolver.
    """

    def __init__(self, store) -> None:
        self._store = store

    def _cache_key(self, name: str) -> str:
        digest = hashlib.sha256(name.lower().encode()).hexdigest()
        return f"cache/icons/iconify_{digest}.png"

    async def resolve(self, name: str) -> bytes | None:
        cache_key = self._cache_key(name)
        if await self._store.exists(cache_key):
            logger.debug("Iconify cache hit: %s", name)
            return await self._store.get(cache_key)

        try:
            result = await search_iconify(name)
            if not result:
                logger.info("Iconify: no icon found for %r", name)
                return None

            prefix, icon_name = result
            svg_bytes = await fetch_iconify_svg(prefix, icon_name)
            if not svg_bytes:
                logger.info("Iconify: SVG download failed for %r:%r", prefix, icon_name)
                return None

            import asyncio, functools
            loop = asyncio.get_event_loop()
            png_bytes = await loop.run_in_executor(
                None, functools.partial(_compose_icon, name, svg_bytes)
            )

            await self._store.put(cache_key, png_bytes, "image/png")
            logger.info("Iconify icon resolved for %r → %s:%s", name, prefix, icon_name)
            return png_bytes

        except Exception as exc:
            logger.warning("Iconify resolver failed for %r: %s", name, exc)
            return None
