"""格子算術：幾列幾欄，以及一頁放得下哪幾支攝影機。

刻意不碰 Qt，所以排版規則不用開視窗就能測試。
分頁是為了效能：低階電腦只解碼目前這一頁的格子。
"""
from __future__ import annotations

import math


def grid_shape(tile_count: int) -> tuple[int, int]:
    """接近正方形的 (列數, 欄數)；欄數不會少於列數。"""
    if tile_count <= 0:
        return (0, 0)
    columns = math.ceil(math.sqrt(tile_count))
    return (math.ceil(tile_count / columns), columns)


def page_count(total: int, per_page: int) -> int:
    """需要幾頁；至少 1 頁，介面才有東西可顯示。"""
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    return max(1, math.ceil(total / per_page))


def clamp_page(page: int, total: int, per_page: int) -> int:
    """把頁碼夾在 0 到 page_count-1 之間。"""
    return max(0, min(page, page_count(total, per_page) - 1))


def page_slice(page: int, per_page: int) -> slice:
    """這一頁對應攝影機清單的哪一段。"""
    if page < 0:
        raise ValueError("page must not be negative")
    if per_page <= 0:
        raise ValueError("per_page must be positive")
    start = page * per_page
    return slice(start, start + per_page)
