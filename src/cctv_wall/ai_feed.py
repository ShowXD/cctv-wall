"""AI 辨識結果的 TCP 來源：連到 AI 端，逐行讀取 JSON，交給畫面與影像對照。

刻意不碰 Qt：解析、時間對齊與重連都能在沒有 QApplication 的情況下測試。
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

DEFAULT_CAMERA_KEY = "camera"
DEFAULT_TIME_KEY = "ts"
# 與 low_end 效能檔的 network-caching 相同：影像大約晚這麼久才出現在畫面上。
# 實際延遲還包含攝影機編碼，所以這是現場校準用的旋鈕，而不是精確值。
DEFAULT_DELAY_MS = 1500
MAX_DELAY_MS = 30_000
# 異常的 AI 端若一直不送換行，不能讓它無限吃記憶體。
MAX_LINE_BYTES = 64 * 1024
CONNECT_TIMEOUT_SECONDS = 5
FIRST_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 30
# AI 時間與本機接收時間差超過這個值，多半是兩台機器的時鐘沒對時。
CLOCK_SKEW_WARNING_SECONDS = 2.0
# 數值大於這個值的 epoch 視為毫秒（1e11 秒已是西元 5138 年）。
_EPOCH_MILLISECONDS_THRESHOLD = 1e11

STATUS_CONNECTED = "connected"
STATUS_RECONNECTING = "reconnecting"


def _log() -> logging.Logger:
    # event_log 會匯入 Qt；子 logger 會往上傳到它設定好的 "cctv_wall" handler。
    return logging.getLogger("cctv_wall.ai_feed")


@dataclass(frozen=True, slots=True)
class AiFeedConfig:
    """一條 AI 結果連線。本程式是 client，主動連到 AI 端；一條連線可帶多台攝影機。"""

    host: str
    port: int
    camera_key: str = DEFAULT_CAMERA_KEY
    time_key: str = DEFAULT_TIME_KEY
    delay_ms: int = DEFAULT_DELAY_MS
    # AI 端識別值 → 攝影機顯示名稱。兩條連線常送同樣的 A001/A002，靠這張表分開；
    # 空表代表識別值本身就是顯示名稱。
    cameras: tuple[tuple[str, str], ...] = ()
    # (欄位, 值) 任一相符就略過。
    skip: tuple[tuple[str, str], ...] = ()
    # 這些欄位為空（null、""、[]、{}）就略過，例如每秒回報一次「目前沒有物件」的狀態。
    skip_empty: tuple[str, ...] = ()
    # 欄位 → (代碼, 顯示文字)。任何層級的同名欄位都會換掉，所以 payload 裡的 vdType 也適用；
    # 換專案時改設定就好，不必改程式。
    labels: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("ai_feed needs a host")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"ai_feed port must be 1-65535, got {self.port}")
        if not self.camera_key:
            raise ValueError("ai_feed needs a camera_key")
        if not 0 <= self.delay_ms <= MAX_DELAY_MS:
            raise ValueError(f"ai_feed delay_ms must be 0-{MAX_DELAY_MS}, got {self.delay_ms}")
        if any(not source or not name for source, name in self.cameras):
            raise ValueError("ai_feed cameras: ids and camera names must not be empty")

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def camera_names(self) -> tuple[str, ...]:
        return tuple(name for _source, name in self.cameras)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "AiFeedConfig":
        def text(key: str, default: str = "") -> str:
            value = raw.get(key)
            return default if value is None else str(value).strip()

        def number(key: str, default: int) -> int:
            value = text(key)
            if not value:
                return default
            try:
                return int(value)
            except ValueError as e:
                raise ValueError(f"ai_feed {key} must be a whole number, got {value!r}") from e

        def table(key: str) -> Mapping[str, Any]:
            value = raw.get(key) or {}
            if not isinstance(value, Mapping):
                raise ValueError(f"ai_feed {key} must be an object")
            return value

        skip = []
        for field_name, values in table("skip").items():
            for value in values if isinstance(values, list) else [values]:
                skip.append((str(field_name), _scalar(value)))
        skip_empty = raw.get("skip_empty") or []
        if not isinstance(skip_empty, list):
            raise ValueError("ai_feed skip_empty must be a list of field names")
        labels = []
        for field_name, codes in table("labels").items():
            if not isinstance(codes, Mapping):
                raise ValueError(f"ai_feed labels.{field_name} must be an object of code: text")
            labels.append((str(field_name),
                           tuple((_scalar(code), _text(label)) for code, label in codes.items())))
        return cls(host=text("host"), port=number("port", 0),
                   camera_key=text("camera_key", DEFAULT_CAMERA_KEY),
                   time_key=text("time_key", DEFAULT_TIME_KEY),
                   delay_ms=number("delay_ms", DEFAULT_DELAY_MS),
                   cameras=tuple((str(source).strip(), _text(name))
                                 for source, name in table("cameras").items()),
                   skip=tuple(skip),
                   skip_empty=tuple(str(field_name) for field_name in skip_empty),
                   labels=tuple(labels))

    def as_dict(self) -> dict[str, Any]:
        raw: dict[str, Any] = {"host": self.host, "port": self.port, "camera_key": self.camera_key,
                               "time_key": self.time_key, "delay_ms": self.delay_ms}
        if self.cameras:
            raw["cameras"] = dict(self.cameras)
        if self.skip:
            grouped: dict[str, list[str]] = {}
            for field_name, value in self.skip:
                grouped.setdefault(field_name, []).append(value)
            raw["skip"] = grouped
        if self.skip_empty:
            raw["skip_empty"] = list(self.skip_empty)
        if self.labels:
            raw["labels"] = {field_name: dict(codes) for field_name, codes in self.labels}
        return raw


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _scalar(value: Any) -> str:
    """比對與顯示用的文字：字串原樣，其餘用精簡 JSON，所以 2 與 "2" 視為相同。"""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class AiEvent:
    camera: str
    text: str
    received_at: float                 # 本機 epoch 秒
    event_time: float | None = None    # AI 端 epoch 秒；沒送或看不懂時為 None

    @property
    def clock_skew(self) -> float | None:
        """接收時間減 AI 時間；正值代表 AI 端時間較早。"""
        return None if self.event_time is None else self.received_at - self.event_time

    @property
    def has_clock_skew(self) -> bool:
        skew = self.clock_skew
        return skew is not None and abs(skew) > CLOCK_SKEW_WARNING_SECONDS


def parse_time(value: Any) -> float | None:
    """epoch 秒、epoch 毫秒或 ISO 8601；沒有時區的 ISO 時間視為本機時間。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            seconds = float(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value.strip()).timestamp()
            except ValueError:
                return None
    else:
        return None
    return seconds / 1000 if seconds > _EPOCH_MILLISECONDS_THRESHOLD else seconds


def _warn_once(config: AiFeedConfig, warned: set[str] | None, reason: str) -> None:
    # AI 端每秒送好幾行；同一種問題每行都記一次，會在幾分鐘內把輪替日誌洗掉。
    if warned is not None:
        if reason in warned:
            return
        warned.add(reason)
    _log().warning("ai_feed %s: ignored %s (repeats are not logged again)", config.address, reason)


def parse_line(line: str, config: AiFeedConfig, received_at: float,
               warned: set[str] | None = None) -> AiEvent | None:
    """一行 JSON 物件轉成事件；略過、壞掉或對不到攝影機的行回 None，不中斷整條連線。"""
    try:
        message = json.loads(line)
    except ValueError:
        _warn_once(config, warned, "a line that is not JSON")
        return None
    if not isinstance(message, dict):
        _warn_once(config, warned, "a line that is not a JSON object")
        return None
    if any(field_name in message and _scalar(message[field_name]) == value
           for field_name, value in config.skip):
        return None
    if any(field_name in message and message[field_name] in (None, "", [], {})
           for field_name in config.skip_empty):
        return None
    source = _scalar(message.get(config.camera_key, ""))
    if not source:
        _warn_once(config, warned, f"a line without {config.camera_key!r}")
        return None
    camera = dict(config.cameras).get(source) if config.cameras else source
    if camera is None:
        _warn_once(config, warned, f"{config.camera_key}={source!r}, which is not in its cameras table")
        return None
    event_time = parse_time(message.get(config.time_key)) if config.time_key else None
    rest = {k: v for k, v in message.items() if k not in (config.camera_key, config.time_key)}
    rest = _labelled(rest, {field_name: dict(codes) for field_name, codes in config.labels})
    text = "  ".join(f"{k}={_scalar(v)}" for k, v in rest.items())
    return AiEvent(camera, text, received_at, event_time)


def _labelled(value: Any, labels: dict[str, dict[str, str]]) -> Any:
    """把代碼換成文字，例如 vdType 2 → 汽車；沒有對照的代碼原樣保留，不會吃掉資訊。"""
    if isinstance(value, dict):
        return {k: labels[k].get(_scalar(v), v)
                if k in labels and not isinstance(v, (dict, list)) else _labelled(v, labels)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_labelled(item, labels) for item in value]
    return value


def release_due(pending: deque[AiEvent], now: float, delay_ms: int) -> list[AiEvent]:
    """取出已等滿延遲的事件，讓文字與晚到的畫面同時出現。pending 依接收時間排序。"""
    due = []
    while pending and pending[0].received_at + delay_ms / 1000 <= now:
        due.append(pending.popleft())
    return due


class AiFeedClient:
    """背景執行緒：連線、逐行讀取、斷線後以 1→2→4…30 秒退避重連。

    回呼在背景執行緒上被呼叫，呼叫端要自己轉回 GUI 執行緒。
    """

    def __init__(self, config: AiFeedConfig, on_event: Callable[[AiEvent], None],
                 on_status: Callable[[str], None],
                 connect: Callable[..., socket.socket] = socket.create_connection) -> None:
        self.config = config
        self._on_event = on_event
        self._on_status = on_status
        self._connect = connect
        self._stopping = threading.Event()
        self._warned: set[str] = set()
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, name="ai-feed", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        """關掉 socket 讓阻塞中的 readline 立刻返回；不等執行緒結束。"""
        self._stopping.set()
        with self._lock:
            sock, self._socket = self._socket, None
        if sock is not None:
            _close(sock)

    def _run(self) -> None:
        backoff = FIRST_BACKOFF_SECONDS
        while not self._stopping.is_set():
            self._on_status(STATUS_RECONNECTING)
            try:
                sock = self._connect((self.config.host, self.config.port), CONNECT_TIMEOUT_SECONDS)
            except OSError as error:
                _log().info("ai_feed %s: connect failed: %s", self.config.address, error)
            else:
                with self._lock:
                    if self._stopping.is_set():
                        _close(sock)
                        return
                    self._socket = sock
                _log().info("ai_feed %s: connected", self.config.address)
                self._on_status(STATUS_CONNECTED)
                backoff = FIRST_BACKOFF_SECONDS
                self._read(sock)
                with self._lock:
                    self._socket = None
                _close(sock)
                if not self._stopping.is_set():
                    _log().info("ai_feed %s: disconnected", self.config.address)
            if self._stopping.wait(backoff):
                return
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    def _read(self, sock: socket.socket) -> None:
        # stop() 會從別的執行緒關 socket 來中斷讀取，所以不設讀取逾時。
        sock.settimeout(None)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            with sock.makefile("rb") as stream:
                while not self._stopping.is_set():
                    raw = stream.readline(MAX_LINE_BYTES + 1)
                    if not raw:
                        return
                    if len(raw) > MAX_LINE_BYTES and not raw.endswith(b"\n"):
                        _log().warning("ai_feed %s: line over %d bytes, reconnecting",
                                       self.config.address, MAX_LINE_BYTES)
                        return
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        event = parse_line(line, self.config, time.time(), self._warned)
                        if event is not None:
                            self._on_event(event)
        except OSError as error:
            if not self._stopping.is_set():
                _log().info("ai_feed %s: read failed: %s", self.config.address, error)


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass  # 對方先斷線時 shutdown 本來就會失敗
    sock.close()
