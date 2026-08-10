"""畫質預設值（1080p／720p／360p…）與其像素高度。

單一職責：命名一種畫面尺寸並說出它多高。這裡不認識攝影機、VLC 或檔案，
所以讀起來和測起來都便宜。
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

AUTO = "auto"

# 刻意設為唯讀：呼叫端只從這裡挑選，不在執行期擴充。
QUALITY_HEIGHTS: Mapping[str, int | None] = MappingProxyType({
    AUTO: None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
})

QUALITIES: tuple[str, ...] = tuple(QUALITY_HEIGHTS)
DEFAULT_QUALITY = AUTO


def is_known(quality: str) -> bool:
    return quality in QUALITY_HEIGHTS


def height_for(quality: str) -> int | None:
    """預設值的像素高度；None 代表交給來源自己決定。"""
    if not is_known(quality):
        raise ValueError(f"unknown quality {quality!r}; expected one of {', '.join(QUALITIES)}")
    return QUALITY_HEIGHTS[quality]
