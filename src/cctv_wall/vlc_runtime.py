"""把 python-vlc 指向打包在 exe 裡的 libvlc。

只有在「自帶 VLC 的 PyInstaller 包」中執行時才有意義。非打包環境下這裡什麼都不做，
python-vlc 會自己找到已安裝的 VLC。
必須在 `import vlc` **之前**呼叫，因為 python-vlc 是在匯入時才去找那個函式庫。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BUNDLE_SUBDIRECTORY = "vlc"
LIBRARY_NAME = "libvlc.dll" if sys.platform == "win32" else "libvlc.so"
PLUGINS_SUBDIRECTORY = "plugins"


def bundled_vlc_dir() -> Path | None:
    """打包進來的 VLC 目錄；非凍結環境或沒打包時回傳 None。"""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    candidate = Path(base) / BUNDLE_SUBDIRECTORY
    return candidate if (candidate / LIBRARY_NAME).exists() else None


def configure() -> Path | None:
    """讓打包的 libvlc 能被找到；回傳實際使用的目錄（沒有則 None）。"""
    directory = bundled_vlc_dir()
    if directory is None:
        return None
    # 前兩個給 python-vlc 讀；VLC_PLUGIN_PATH 則涵蓋 libvlc 自己的查找。
    os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(directory / LIBRARY_NAME))
    os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(directory / PLUGINS_SUBDIRECTORY))
    os.environ.setdefault("VLC_PLUGIN_PATH", str(directory / PLUGINS_SUBDIRECTORY))
    if hasattr(os, "add_dll_directory"):  # Windows：讓載入器找得到 libvlccore.dll
        os.add_dll_directory(str(directory))
    return directory
