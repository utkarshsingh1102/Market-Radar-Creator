"""
Header component: NextBigGames pill (top-left) + LinkedIn profile row (top-right).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.renderer.text_fit import _load_font


def _rounded_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def render(img: Image.Image, tokens: Any, ctx: dict) -> None:
    draw = ImageDraw.Draw(img)
    colors = tokens.get("colors")
    layout = tokens.get("layout", "header")
    branding = tokens.get("branding")
    assets_root = Path(ctx.get("assets_root", "assets"))

    top = layout["top_margin"]
    pill_px = layout["pill_padding_x"]
    pill_py = layout["pill_padding_y"]
    pill_r = layout["pill_radius"]
    right_margin = layout["right_margin"]

    # ── Left: NextBigGames pill ──────────────────────────────────────────────
    pill_font_size = tokens.get("fonts", "pill", default={}).get("size", 30)
    pill_font_path = tokens.font_path("pill")
    pill_font = _load_font(pill_font_path, pill_font_size)

    logo_text = branding["logo_text"]
    bbox = pill_font.getbbox(logo_text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pill_w = text_w + pill_px * 2
    pill_h = text_h + pill_py * 2
    pill_x = layout.get("left_margin", right_margin)
    pill_y = top

    # Draw black rounded pill
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=pill_r,
        fill=colors["pill_background"],
    )
    # Draw white text centered in pill
    text_x = pill_x + pill_px - bbox[0]
    text_y = pill_y + pill_py - bbox[1]
    draw.text((text_x, text_y), logo_text, font=pill_font, fill=colors["text_inverted"])

    pill_center_y = pill_y + pill_h // 2

    # ── Right: LinkedIn icon + handle + avatar ───────────────────────────────
    profile = branding["profile"]
    handle = profile["handle"]
    avatar_size = profile.get("avatar_size", 56)
    li_size = profile.get("linkedin_icon_size", 32)

    profile_font_size = tokens.get("fonts", "profile", default={}).get("size", 28)
    profile_font_path = tokens.font_path("profile")
    profile_font = _load_font(profile_font_path, profile_font_size)

    handle_bbox = profile_font.getbbox(handle)
    handle_w = handle_bbox[2] - handle_bbox[0]
    handle_h = handle_bbox[3] - handle_bbox[1]

    gap = 12  # gap between elements

    # Total right group width: li_icon + gap + handle + gap + avatar
    group_w = li_size + gap + handle_w + gap + avatar_size
    group_x = tokens.canvas_width - right_margin - group_w
    group_center_y = pill_center_y

    # LinkedIn icon
    li_icon_path = assets_root / profile["linkedin_icon_path"].replace("assets/", "")
    li_y = group_center_y - li_size // 2
    if li_icon_path.exists():
        li_img = Image.open(li_icon_path).convert("RGBA").resize((li_size, li_size), Image.LANCZOS)
        img.paste(li_img, (group_x, int(li_y)), li_img)
    else:
        # Fallback: draw a blue "in" circle
        draw.ellipse(
            [group_x, int(li_y), group_x + li_size, int(li_y) + li_size],
            fill="#0A66C2",
        )
        in_font = _load_font(None, li_size - 8)
        draw.text((group_x + li_size // 2, int(li_y) + li_size // 2), "in",
                  font=in_font, fill="white", anchor="mm")

    # Handle text
    text_x = group_x + li_size + gap
    text_y = int(group_center_y - handle_h // 2 - handle_bbox[1])
    draw.text((text_x, text_y), handle, font=profile_font, fill=colors["text_primary"])

    # Avatar
    avatar_x = text_x + handle_w + gap
    avatar_y = int(group_center_y - avatar_size // 2)
    avatar_path = assets_root / profile["avatar_path"].replace("assets/", "")
    if avatar_path.exists():
        av_img = Image.open(avatar_path).convert("RGBA").resize(
            (avatar_size, avatar_size), Image.LANCZOS
        )
        # Circular mask
        circle_mask = Image.new("L", (avatar_size, avatar_size), 0)
        ImageDraw.Draw(circle_mask).ellipse([0, 0, avatar_size - 1, avatar_size - 1], fill=255)
        av_rgba = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
        av_rgba.paste(av_img, mask=circle_mask)
        img.paste(av_rgba, (avatar_x, avatar_y), av_rgba)
    else:
        # Fallback: grey circle
        draw.ellipse(
            [avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
            fill="#CCCCCC",
        )
