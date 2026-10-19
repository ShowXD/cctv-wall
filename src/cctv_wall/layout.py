"""格子算術：幾列幾欄，以及一頁放得下哪幾支攝影機。

刻意不碰 Qt，所以排版規則不用開視窗就能測試。
分頁是為了效能：低階電腦只解碼目前這一頁的格子。
"""
from __future__ import annotations

import math

VIDEO_ASPECT = 16 / 9   # 一般監視攝影機的畫面比例


def grid_shape(tile_count: int) -> tuple[int, int]:
    """接近正方形的 (列數, 欄數)；欄數不會少於列數。"""
    if tile_count <= 0:
        return (0, 0)
    columns = math.ceil(math.sqrt(tile_count))
    return (math.ceil(tile_count / columns), columns)


def fit_window_to_video(window: tuple[int, int], surface: tuple[int, int], grid: tuple[int, int],
                        minimum: tuple[int, int], limit: tuple[int, int]) -> tuple[int, int]:
    """讓每格影像剛好 16:9 的視窗大小 (寬, 高)。

    用量測到的一格影像大小反推，而不是重算邊距與格距：版面細節改了也不會算錯。
    先保留寬度只調高度；高度超出螢幕或低於視窗最小高度時，把高度固定在那個界線，改調寬度。
    """
    (window_w, window_h), (surface_w, surface_h), (rows, columns) = window, surface, grid
    (minimum_w, minimum_h), (limit_w, limit_h) = minimum, limit
    if rows <= 0 or columns <= 0 or surface_w <= 0 or surface_h <= 0:
        return window
    height = window_h + rows * (surface_w / VIDEO_ASPECT - surface_h)
    if minimum_h <= height <= limit_h:
        return window_w, round(height)
    target_h = limit_h if height > limit_h else minimum_h
    surface_h_at_target = surface_h + (target_h - window_h) / rows
    width = window_w + columns * (surface_h_at_target * VIDEO_ASPECT - surface_w)
    return min(max(round(width), minimum_w), limit_w), target_h


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
