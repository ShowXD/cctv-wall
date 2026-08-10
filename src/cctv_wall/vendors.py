"""各廠牌攝影機的 RTSP 路徑樣板。

以資料實現開放／封閉原則：支援新品牌只要在 VENDOR_TEMPLATES 加一列，
永遠不必動網址組裝器或 GUI。

樣板變數：
    {stream}    使用者選的串流編號，從 1 起算（1、2、3）
    {stream0}   從 0 起算，給子碼流從零編號的廠牌用
    {main_sub}  串流 1 代入 "main"，其餘代入 "sub"
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

GENERIC_VENDOR = "generic"
CUSTOM_VENDOR = "custom"

# ponytail: 實機會因固件版本而異——這張表就是校正旋鈕。
VENDOR_TEMPLATES: Mapping[str, str] = MappingProxyType({
    GENERIC_VENDOR: "stream{stream}",
    "hikvision": "Streaming/Channels/10{stream}",
    "dahua": "cam/realmonitor?channel=1&subtype={stream0}",
    "reolink": "h264Preview_01_{main_sub}",
    "tapo": "stream{stream}",
    CUSTOM_VENDOR: "",  # 由攝影機自己提供 path_template
})

VENDORS: tuple[str, ...] = tuple(VENDOR_TEMPLATES)


def is_known(vendor: str) -> bool:
    return vendor in VENDOR_TEMPLATES


def template_for(vendor: str, path_template: str = "") -> str:
    """要套用的樣板：廠牌內建的，或 custom 時攝影機自帶的。"""
    if not is_known(vendor):
        raise ValueError(f"unknown vendor {vendor!r}; expected one of {', '.join(VENDORS)}")
    if vendor == CUSTOM_VENDOR:
        if not path_template.strip():
            raise ValueError("vendor 'custom' requires a path_template")
        return path_template.strip()
    return VENDOR_TEMPLATES[vendor]


def render_path(template: str, stream: int) -> str:
    """填入樣板變數，並去掉開頭的斜線。"""
    try:
        path = template.format(stream=stream, stream0=stream - 1,
                               main_sub="main" if stream == 1 else "sub")
    except (KeyError, IndexError) as e:
        raise ValueError(f"path template {template!r} uses an unknown variable: {e}") from e
    return path.lstrip("/")
