"""Small, dependency-free UI translation catalog used by the Qt presentation layer."""
from __future__ import annotations

from dataclasses import dataclass

from cctv_wall.models import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

LANGUAGE_LABELS = {"zh_TW": "繁體中文", "en": "English"}

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "CCTV Wall", "toggle_sidebar": "Show or hide the site list (Ctrl+B)", "save_camera": "Save", "tiles_per_page": "Tiles per page — type a number, scroll, or use the arrow keys", "sites": "SITES",
        "manage": "Sites & cameras",         "no_site": "No site selected", "cameras": "{count} cameras configured", "camera": "{count} camera configured",
        "live": "●  {live}/{total} LIVE", "page": "Page {current} of {total}",
        "previous": "Previous page", "next": "Next page",         "reload_tip": "Reconnect visible cameras",         "no_cameras": "No cameras here yet", "add_camera_hint": "Open Settings to add a camera to this site.",
        "settings_title": "Settings — sites and cameras",                 "add_site": "Add site", "add_camera": "Add camera", "delete": "Delete", "add": "Add", "site_list": "Sites", "camera_details": "Camera", "connection": "Connection",
                "cancel": "Cancel", "name": "Camera display name",         "port": "Port", "username": "Username", "password": "Password",         "direct_url": "RTSP URL",                 "delete_site": "Delete site", "delete_site_confirm": "Delete site {name!r} and its cameras?",
                        "reconnecting": "Reconnecting…", "retry_in": "Next attempt in {seconds}s", "retry_now": "Click to retry now",
                        "save_error": "Could not save settings", "connection_waiting": "Connecting — check the IP, port and network",
        "no_video": "No video received — check stream path or credentials", "vlc_error": "VLC could not play this stream", "not_playing": "Not playing",
        "language": "Language",         "maximize": "Fill app with video", "restore_window": "Restore normal interface", "stream_choice": "Stream {stream}",
        "logs": "Live log", "diagnostics": "Diagnostics", "close": "Close", "no_events": "No events in this session.",
        "sync_diagnostics": "Timestamp sync", "run_sync_probe": "Check current site", "sync_probe_running_button": "Checking…",
        "sync_probe_help": "Read-only check: briefly connects to each RTSP source and looks for RTCP Sender Reports. URLs and credentials are never displayed or stored in this window.",
        "sync_probe_running": "Checking {camera}…", "sync_probe_result_heading": "RTSP timestamp synchronisation capability",
        "sync_ready": "Ready for strict timestamp synchronisation", "sync_unavailable": "No usable RTCP Sender Report — strict synchronisation is unavailable",
        "sync_probe_error": "Could not check: {error}", "sender_reports": "{count} Sender Report(s)",
        "sync_probe_summary": "Eligible sources: {ready}/{total}. All sources must be eligible and NTP-synchronised before strict sync can be enabled.",
        "enable_strict_sync": "Enable strict sync", "disable_strict_sync": "Use normal playback", "sync_short": "Sync", "syncing": "Syncing — waiting for the shared playback time…",
        "usage": "CPU {cpu}  •  RAM {memory}", "usage_tip": "{players} players; the wall uses about {cores:.1f} of {total} CPU cores", "players_tip": "{players} players", "usage_unknown": "—",                 "copy_suffix": "copy",
        "rename": "Rename", "delete_site_action": "Delete site", "add_camera_action": "Add camera…", "edit_camera": "Edit camera…", "edit_camera_title": "Edit camera", "delete_camera": "Delete camera", "delete_camera_confirm": "Delete camera {name!r}?",
        "duplicate_site": "Duplicate site", "rename_site": "Rename site",         "site_exists": "A site named {name!r} already exists.", "new_site_name": "Site name",
        "ai_events": "AI results", "ai_short": "AI", "ai_all_cameras": "All cameras",
        "ai_connected": "Connected to {address}", "ai_reconnecting": "Connecting to {address}…",
        "ai_delay_tip": "Each result is held for {delay} ms so it appears with the matching video frame (delay_ms in workspace.json).",
        "ai_event_tip": "AI time {ai_time}\nReceived {received}",
        "ai_clock_skew": "AI and this PC clocks differ by {seconds:.1f}s — check NTP time sync",
        "ai_feeds_action": "AI result connections…", "ai_feeds_button": "AI result connections", "ai_feeds_title": "AI result connections — {site}",
        "ai_feeds_help": "This site connects to every AI server listed here while it is on screen. Add a row per camera this AI server reports: the id it sends (e.g. A001) and the camera from the menu.",
        "ai_add_feed": "Add connection", "ai_remove_feed": "Remove connection", "ai_new_feed": "New connection",
        "ai_host": "AI server IP / host", "ai_delay": "Display delay",
        "ai_delay_help": "Hold each result this long so it appears with the matching video frame. Raise it if results show up before the picture.",
        "ai_camera_map": "Camera mapping", "ai_source_id": "AI camera id", "ai_camera": "Camera",
        "ai_add_row": "Add mapping", "ai_remove_row": "Remove mapping",
        "ai_advanced": "Message format (advanced, JSON)",
        "ai_advanced_help": "camera_key, time_key, skip, skip_empty, labels — see USAGE.md. A new connection copies the selected one's format.",
        "ai_feeds_invalid": "Invalid AI connection", "ai_ok": "OK",
        "untitled_site": "New site",
        "move_up": "Move up", "move_down": "Move down",
    },
    "zh_TW": {
        "app_title": "CCTV 影像牆", "toggle_sidebar": "顯示或隱藏地點清單（Ctrl+B）", "save_camera": "儲存", "tiles_per_page": "每頁格數：可直接輸入、滾動滑鼠滾輪或按方向鍵", "sites": "監看地點", "manage": "地點與攝影機",
        "no_site": "尚未選擇地點", "cameras": "已設定 {count} 支攝影機", "camera": "已設定 {count} 支攝影機",
        "live": "●  {live}/{total} 路播放中", "page": "第 {current} / {total} 頁", "previous": "上一頁", "next": "下一頁",
        "reload_tip": "重新連線目前可見的攝影機",
                "no_cameras": "這個地點尚未設定攝影機", "add_camera_hint": "請開啟設定，新增一支攝影機。",
        "settings_title": "設定 — 地點與攝影機",                 "add_site": "新增地點", "add_camera": "新增攝影機", "delete": "刪除", "add": "新增", "site_list": "地點列表", "camera_details": "攝影機", "connection": "連線資訊",
                "cancel": "取消", "name": "攝影機顯示名稱", "port": "連接埠", "username": "帳號",
        "password": "密碼", "direct_url": "RTSP 網址",
                        "delete_site": "刪除地點",
        "delete_site_confirm": "確定要刪除地點 {name!r} 及其攝影機嗎？",                 "reconnecting": "重新連線中…", "retry_in": "{seconds} 秒後重試", "retry_now": "點一下立即重試", "save_error": "無法儲存設定",
                        "connection_waiting": "正在連線 — 請檢查 IP、連接埠與網路",
        "no_video": "未收到影像 — 請檢查串流路徑或帳密", "vlc_error": "VLC 無法播放這個串流", "not_playing": "未播放",
        "language": "語言",         "maximize": "以影像填滿程式畫面", "restore_window": "還原一般介面", "stream_choice": "串流 {stream}",
        "logs": "即時紀錄", "diagnostics": "診斷資訊", "close": "關閉", "no_events": "本次執行尚無事件紀錄。",
        "sync_diagnostics": "時間戳同步", "run_sync_probe": "檢查目前地點", "sync_probe_running_button": "檢查中…",
        "sync_probe_help": "唯讀檢查：會短暫連線每支 RTSP 攝影機，確認是否收到 RTCP Sender Report。此視窗不會顯示或儲存網址與帳密。",
        "sync_probe_running": "正在檢查 {camera}…", "sync_probe_result_heading": "RTSP 時間戳同步能力",
        "sync_ready": "可納入嚴格時間戳同步", "sync_unavailable": "未收到可用的 RTCP Sender Report，無法嚴格同步",
        "sync_probe_error": "無法檢查：{error}", "sender_reports": "{count} 筆 Sender Report",
        "sync_probe_summary": "可用來源：{ready}/{total}。要啟用嚴格同步，所有來源都必須可用且已完成 NTP 校時。",
        "enable_strict_sync": "啟用嚴格時間戳同步", "disable_strict_sync": "改用一般播放", "sync_short": "同步", "syncing": "同步中 — 等待共同播放時間…",
        "usage": "CPU {cpu}  •  記憶體 {memory}", "usage_tip": "播放器 {players} 個；本程式約用 {cores:.1f} 顆核心（全機共 {total} 核）", "players_tip": "播放器 {players} 個", "usage_unknown": "—",                 "copy_suffix": "副本",
        "rename": "重新命名", "delete_site_action": "刪除地點", "add_camera_action": "新增攝影機…", "edit_camera": "編輯攝影機…", "edit_camera_title": "編輯攝影機", "delete_camera": "刪除攝影機", "delete_camera_confirm": "要刪除攝影機 {name!r} 嗎？",
        "duplicate_site": "複製地點", "rename_site": "重新命名地點",         "site_exists": "地點名稱 {name!r} 已存在。", "new_site_name": "地點名稱",
        "ai_events": "AI 辨識結果", "ai_short": "AI", "ai_all_cameras": "所有攝影機",
        "ai_connected": "已連線 {address}", "ai_reconnecting": "正在連線 {address}…",
        "ai_delay_tip": "每筆結果延後 {delay} 毫秒顯示，以對上同一刻的畫面（workspace.json 的 delay_ms）。",
        "ai_event_tip": "AI 時間 {ai_time}\n接收時間 {received}",
        "ai_clock_skew": "AI 端與本機時鐘相差 {seconds:.1f} 秒，請確認 NTP 校時",
        "ai_feeds_action": "AI 辨識連線…", "ai_feeds_button": "AI 辨識連線", "ai_feeds_title": "AI 辨識連線 — {site}",
        "ai_feeds_help": "畫面切到這個地點時，會連到下方列出的每一個 AI 端。這個 AI 端回報幾台攝影機就新增幾列：填它送來的識別值（例如 A001），再從選單選對應的攝影機。",
        "ai_add_feed": "新增連線", "ai_remove_feed": "刪除連線", "ai_new_feed": "新連線",
        "ai_host": "AI 端 IP / 主機", "ai_delay": "顯示延遲",
        "ai_delay_help": "每筆結果延後這麼久才顯示，以對上同一刻的畫面。結果比畫面早出現就調大。",
        "ai_camera_map": "攝影機對照", "ai_source_id": "AI 端識別值", "ai_camera": "攝影機",
        "ai_add_row": "新增對照", "ai_remove_row": "刪除對照",
        "ai_advanced": "訊息格式（進階，JSON）",
        "ai_advanced_help": "camera_key、time_key、skip、skip_empty、labels，說明見 USAGE.md。新增連線時會沿用目前所選連線的格式。",
        "ai_feeds_invalid": "AI 連線設定有誤", "ai_ok": "確定",
        "untitled_site": "新地點",
        "move_up": "上移", "move_down": "下移",
    },
}


@dataclass(frozen=True, slots=True)
class Translator:
    language: str = DEFAULT_LANGUAGE

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            object.__setattr__(self, "language", DEFAULT_LANGUAGE)

    def t(self, key: str, **values: object) -> str:
        return _MESSAGES[self.language].get(key, key).format(**values)
