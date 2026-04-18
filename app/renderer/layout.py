"""
Adaptive Layout Engine.
Computes all geometry for the left inspiration column based on N inspirations.
Pure math — no Pillow imports here so it can be unit-tested independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IconRow:
    index: int          # 0-based inspiration index
    y_center: float     # vertical center of this icon row
    icon_size: int      # square pixel size of the icon
    text_x: float       # x position where text starts
    text_y_center: float  # vertical center of text block


@dataclass
class PlusRow:
    y_center: float     # vertical center of the "+" glyph
    size: int           # font size for the "+"


@dataclass
class ColumnLayout:
    icon_rows: list[IconRow]
    plus_rows: list[PlusRow]
    icon_size: int
    row_height: float
    plus_row_height: float
    x_icon_center: float   # horizontal center of the icon column
    x_text_start: float    # x where inspiration text starts


def compute_layout(n: int, tokens: Any) -> ColumnLayout:
    """
    Given N inspirations and the design tokens, compute the full left-column layout.

    The column is a vertical flex-stack of:
        icon_row, plus_row, icon_row, plus_row, ..., icon_row
    where plus_rows are ~60% the height of icon_rows.
    """
    lc = tokens.get("layout", "left_column")

    x_start: int = lc["x_start"]
    x_end: int = lc["x_end"]
    y_start: int = lc["y_start"]
    y_end: int = lc["y_end"]
    icon_radius: int = lc["icon_radius"]
    plus_sizes: dict = lc["plus_size_by_count"]
    text_left_offset: int = tokens.get("layout", "left_column", default={}).get(
        "text_left_offset", 24
    )

    available_h = y_end - y_start
    # N icon rows + (N-1) plus rows at 60% weight
    total_units = n + 0.6 * (n - 1)
    row_height = available_h / total_units
    plus_row_height = row_height * 0.6
    icon_size = int(row_height * 0.80)

    # Keep icon size reasonable
    icon_size = min(icon_size, 160)
    icon_size = max(icon_size, 80)

    plus_size = int(plus_sizes.get(n, plus_sizes.get(str(n), 60)))
    x_icon_center = x_start + icon_size / 2

    icon_rows: list[IconRow] = []
    plus_rows: list[PlusRow] = []

    for i in range(n):
        # y center of this icon row
        y_center = y_start + row_height * i + plus_row_height * i + row_height / 2
        text_x = x_start + icon_size + text_left_offset
        icon_rows.append(
            IconRow(
                index=i,
                y_center=y_center,
                icon_size=icon_size,
                text_x=text_x,
                text_y_center=y_center,
            )
        )

        if i < n - 1:
            # y center of the plus between row i and i+1
            plus_y = y_start + row_height * (i + 1) + plus_row_height * i + plus_row_height / 2
            plus_rows.append(PlusRow(y_center=plus_y, size=plus_size))

    return ColumnLayout(
        icon_rows=icon_rows,
        plus_rows=plus_rows,
        icon_size=icon_size,
        row_height=row_height,
        plus_row_height=plus_row_height,
        x_icon_center=x_icon_center,
        x_text_start=x_start + icon_size + text_left_offset,
    )
