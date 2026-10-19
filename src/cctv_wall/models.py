"""Immutable domain model: Camera -> Site -> Workspace.

A site is a physical place (office, factory, home) holding several cameras;
a workspace is every site plus what the app should remember between runs.

Invalid values are rejected in __post_init__, so every other module can trust
whatever it is handed and skip defensive re-checks. Updates return new objects
(`with_*` / dataclasses.replace) — nothing here is ever mutated in place.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from cctv_wall import quality as quality_module
from cctv_wall.ai_feed import AiFeedConfig
from cctv_wall import vendors

MIN_STREAM = 1
MAX_STREAM = 4
DEFAULT_PORT = 554
MIN_PORT = 1
MAX_PORT = 65535
NAME_LIMIT = 48
SCHEMA_VERSION = 1
DEFAULT_TILES_PER_PAGE = 4
DEFAULT_MAX_TILES = 16
TILES_LIMIT = 64
# Older files stored a named performance profile instead of a tile count.
LEGACY_PROFILE_TILES = {"low_end": 4, "balanced": 9, "full": 16}
DEFAULT_GEOMETRY = "1280x800"
DEFAULT_SIDEBAR_WIDTH = 260
MIN_SIDEBAR_WIDTH = 160
MAX_SIDEBAR_WIDTH = 800
DEFAULT_LANGUAGE = "zh_TW"
SUPPORTED_LANGUAGES = frozenset({"zh_TW", "en"})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: int, field: str) -> int:
    """空白代表「用預設值」；非數字是錯誤，不會默默退回預設值。"""
    text = _text(value)
    if not text:
        return default
    try:
        return int(text)
    except ValueError as e:
        raise ValueError(f"{field} must be a whole number, got {text!r}") from e


def _bounded(value: Any, default: int, low: int, high: int) -> int:
    """版面偏好用：壞值退回預設，超出範圍就夾住，不讓整個設定檔因此載入失敗。"""
    try:
        number = int(_text(value) or default)
    except ValueError:
        number = default
    return min(max(number, low), high)


def _sidebar_width(value: Any) -> int:
    return _bounded(value, DEFAULT_SIDEBAR_WIDTH, MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH)


def _flag(value: Any) -> bool:
    """優先吃 JSON 布林值；也接受常見的舊字串，但不會把 'false' 當成真。"""
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Camera:
    """一個影像來源：RTSP 攝影機、本機檔案，或網路／YouTube 連結。"""

    name: str = ""
    url: str = ""            # 檔案與 YouTube 用；有值時蓋掉 RTSP 欄位
    host: str = ""
    port: int = DEFAULT_PORT
    user: str = ""
    password: str = ""
    vendor: str = vendors.GENERIC_VENDOR
    path_template: str = ""
    stream: int = MIN_STREAM
    quality: str = quality_module.DEFAULT_QUALITY

    def __post_init__(self) -> None:
        if not self.url and not self.host:
            raise ValueError("camera needs either a direct url or a host address")
        if not MIN_PORT <= self.port <= MAX_PORT:
            raise ValueError(f"port must be {MIN_PORT}-{MAX_PORT}, got {self.port}")
        if not MIN_STREAM <= self.stream <= MAX_STREAM:
            raise ValueError(f"stream must be {MIN_STREAM}-{MAX_STREAM}, got {self.stream}")
        if not vendors.is_known(self.vendor):
            raise ValueError(f"unknown vendor {self.vendor!r}")
        if not quality_module.is_known(self.quality):
            raise ValueError(f"unknown quality {self.quality!r}")
        if not self.url and self.vendor == vendors.CUSTOM_VENDOR and not self.path_template:
            raise ValueError("vendor 'custom' requires a path_template")

    @property
    def label(self) -> str:
        """清單上要顯示的名稱；未命名時用網址，但絕不帶出帳密。刻意不依賴 urls.py，避免匯入循環。"""
        if self.name:
            return self.name
        if not self.url:
            return f"{self.host}:{self.port}"
        parts = urlsplit(self.url)
        if "@" not in parts.netloc:
            return self.url
        return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "Camera":
        """從弱型別輸入建立：JSON 值或 GUI 輸入的字串。"""
        return cls(
            name=_text(raw.get("name"))[:NAME_LIMIT],
            url=_text(raw.get("url")),
            host=_text(raw.get("host")),
            port=_number(raw.get("port"), DEFAULT_PORT, "port"),
            user=_text(raw.get("user")),
            password=_text(raw.get("password")),
            vendor=_text(raw.get("vendor")) or vendors.GENERIC_VENDOR,
            path_template=_text(raw.get("path_template")),
            stream=_number(raw.get("stream"), MIN_STREAM, "stream"),
            quality=_text(raw.get("quality")) or quality_module.DEFAULT_QUALITY,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "url": self.url, "host": self.host, "port": self.port,
            "user": self.user, "password": self.password, "vendor": self.vendor,
            "path_template": self.path_template, "stream": self.stream,
            "quality": self.quality,
        }


@dataclass(frozen=True, slots=True)
class Site:
    """一個有攝影機的場所。影像牆一次只顯示一個地點。"""

    name: str
    cameras: tuple[Camera, ...] = ()
    ai_feeds: tuple[AiFeedConfig, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("site needs a name")
        if self.ai_feeds:
            # AI 結果是用攝影機名稱對應到畫格，同名就分不出是哪一台。
            names = [c.name for c in self.cameras if c.name]
            duplicate = next((n for n in names if names.count(n) > 1), None)
            if duplicate:
                raise ValueError(f"site {self.name!r} has ai_feeds, so camera names must be "
                                 f"unique; {duplicate!r} is used twice")
            # 不檢查對照表裡的名稱是否存在：在設定視窗改名或刪掉攝影機後仍要能存檔，
            # 對不到的結果照樣列在側欄，看得出來。
            mapped = [name for feed in self.ai_feeds for name in feed.camera_names]
            duplicate = next((n for n in mapped if mapped.count(n) > 1), None)
            if duplicate:
                raise ValueError(f"site {self.name!r}: camera {duplicate!r} is mapped more than "
                                 f"once in ai_feeds")

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "Site":
        cameras = raw.get("cameras") or ()
        if not isinstance(cameras, (list, tuple)):
            raise ValueError("'cameras' must be a list")
        built = []
        for index, camera in enumerate(cameras):
            if not isinstance(camera, Mapping):
                raise ValueError(f"camera[{index}]: must be an object")
            try:
                built.append(Camera.from_raw(camera))
            except ValueError as e:
                raise ValueError(f"camera[{index}]: {e}") from e
        feeds = raw.get("ai_feeds") or ()
        if not isinstance(feeds, (list, tuple)):
            raise ValueError("'ai_feeds' must be a list")
        built_feeds = []
        for index, feed in enumerate(feeds):
            if not isinstance(feed, Mapping):
                raise ValueError(f"ai_feeds[{index}]: must be an object")
            try:
                built_feeds.append(AiFeedConfig.from_raw(feed))
            except ValueError as e:
                raise ValueError(f"ai_feeds[{index}]: {e}") from e
        return cls(name=_text(raw.get("name"))[:NAME_LIMIT], cameras=tuple(built),
                   ai_feeds=tuple(built_feeds))

    def as_dict(self) -> dict[str, Any]:
        raw: dict[str, Any] = {"name": self.name, "cameras": [c.as_dict() for c in self.cameras]}
        if self.ai_feeds:
            raw["ai_feeds"] = [feed.as_dict() for feed in self.ai_feeds]
        return raw

    def with_cameras(self, cameras: Iterable[Camera]) -> "Site":
        return replace(self, cameras=tuple(cameras))


@dataclass(frozen=True, slots=True)
class Workspace:
    """所有地點，加上程式跨次啟動要記住的偏好設定。"""

    sites: tuple[Site, ...] = ()
    last_site: str = ""
    tiles_per_page: int = DEFAULT_TILES_PER_PAGE
    max_tiles: int = DEFAULT_MAX_TILES
    geometry: str = DEFAULT_GEOMETRY
    language: str = DEFAULT_LANGUAGE
    strict_sync: bool = False
    sidebar_width: int = DEFAULT_SIDEBAR_WIDTH
    sidebar_visible: bool = True

    def site(self, name: str) -> Site | None:
        return next((s for s in self.sites if s.name == name), None)

    @property
    def active_site(self) -> Site | None:
        """上次記住的地點；找不到就退回第一個。"""
        return self.site(self.last_site) or (self.sites[0] if self.sites else None)

    @property
    def site_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.sites)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "Workspace":
        sites = raw.get("sites") or ()
        if not isinstance(sites, (list, tuple)):
            raise ValueError("'sites' must be a list")
        built = []
        for index, site in enumerate(sites):
            if not isinstance(site, Mapping):
                raise ValueError(f"sites[{index}]: must be an object")
            try:
                built.append(Site.from_raw(site))
            except ValueError as e:
                raise ValueError(f"sites[{index}]: {e}") from e
        names = [s.name for s in built]
        duplicate = next((n for n in names if names.count(n) > 1), None)
        if duplicate:
            raise ValueError(f"duplicate site name {duplicate!r}")
        language = _text(raw.get("language")) or DEFAULT_LANGUAGE
        max_tiles = _bounded(raw.get("max_tiles"), DEFAULT_MAX_TILES, 1, TILES_LIMIT)
        return cls(
            sites=tuple(built),
            last_site=_text(raw.get("last_site")),
            tiles_per_page=_bounded(raw.get("tiles_per_page", LEGACY_PROFILE_TILES.get(
                _text(raw.get("performance")), DEFAULT_TILES_PER_PAGE)),
                DEFAULT_TILES_PER_PAGE, 1, max_tiles),
            max_tiles=max_tiles,
            geometry=_text(raw.get("geometry")) or DEFAULT_GEOMETRY,
            language=language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE,
            strict_sync=_flag(raw.get("strict_sync", False)),
            sidebar_width=_sidebar_width(raw.get("sidebar_width")),
            sidebar_visible=_flag(raw.get("sidebar_visible", True)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "last_site": self.last_site,
            "tiles_per_page": self.tiles_per_page,
            "max_tiles": self.max_tiles,
            "geometry": self.geometry,
            "language": self.language,
            "strict_sync": self.strict_sync,
            "sidebar_width": self.sidebar_width,
            "sidebar_visible": self.sidebar_visible,
            "sites": [s.as_dict() for s in self.sites],
        }

    def with_sites(self, sites: Iterable[Site]) -> "Workspace":
        return replace(self, sites=tuple(sites))

    def with_camera_replaced(self, old: Camera, new: Camera) -> "Workspace":
        """替換第一個與 `old` 相等的攝影機；沒有匹配時回傳自己。

        Camera 是以值比較，所以別處長得一模一樣的副本不會被動到：
        呼叫端改的是某一格，不是所有剛好長一樣的攝影機。
        """
        for site_index, site in enumerate(self.sites):
            for index, camera in enumerate(site.cameras):
                if camera == old:
                    cameras = (*site.cameras[:index], new, *site.cameras[index + 1:])
                    return self.with_sites((*self.sites[:site_index],
                                            site.with_cameras(cameras),
                                            *self.sites[site_index + 1:]))
        return self

    def with_last_site(self, name: str) -> "Workspace":
        return replace(self, last_site=name)

    def with_tiles_per_page(self, tiles: int) -> "Workspace":
        return replace(self, tiles_per_page=_bounded(tiles, self.tiles_per_page, 1, self.max_tiles))

    def with_max_tiles(self, max_tiles: int) -> "Workspace":
        """Lowering the cap also lowers the current page size so it never exceeds it."""
        limit = _bounded(max_tiles, self.max_tiles, 1, TILES_LIMIT)
        return replace(self, max_tiles=limit, tiles_per_page=min(self.tiles_per_page, limit))

    def with_geometry(self, geometry: str) -> "Workspace":
        return replace(self, geometry=geometry)

    def with_language(self, language: str) -> "Workspace":
        """設定支援的介面語言；設定檔壞掉時安全退回繁體中文。"""
        return replace(self, language=language if language in SUPPORTED_LANGUAGES
                       else DEFAULT_LANGUAGE)

    def with_sidebar(self, width: int, visible: bool) -> "Workspace":
        return replace(self, sidebar_width=_sidebar_width(width), sidebar_visible=visible)

    def with_strict_sync(self, enabled: bool) -> "Workspace":
        """記住 RTSP 影像牆是否要使用支援 NTP 時間戳的播放後端。"""
        return replace(self, strict_sync=enabled)
