"""Small, dependency-free UI translation catalog used by the Qt presentation layer."""
from __future__ import annotations

from dataclasses import dataclass

from cctv_wall.models import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

LANGUAGE_LABELS = {"zh_TW": "繁體中文", "en": "English"}

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "CCTV Wall", "toggle_sidebar": "Show or hide the site list (Ctrl+B)", "save_camera": "Save", "tiles_per_page": "Tiles per page — type a number, scroll, or use the arrow keys", "sites": "SITES",
        "manage": "Sites & cameras",         "sites_summary": "{first} … ({count} sites)", "ai_status_summary": "{connected} of {total} connections up", "no_site": "No site selected", "cameras": "{count} cameras configured", "camera": "{count} camera configured",
        "live": "●  {live}/{total} LIVE", "page": "Page {current} of {total}",
        "previous": "Previous page", "next": "Next page",         "reload_tip": "Reconnect visible cameras",         "no_cameras": "No cameras here yet", "add_camera_hint": "Open Settings to add a camera to this site.",
        "settings_title": "Settings — sites and cameras",                 "add_site": "Add site", "add_camera": "Add camera", "delete": "Delete", "site_list": "Sites", "camera_details": "Camera", "connection": "Connection",
                "cancel": "Cancel", "name": "Camera display name",         "port": "Port", "username": "Username", "password": "Password",         "direct_url": "RTSP URL",                 "delete_site_confirm": "Delete site {name!r} and its cameras?",
                        "reconnecting": "Reconnecting…", "retry_in": "Next attempt in {seconds}s", "retry_now": "Click to retry now",
                        "save_error": "Could not save settings", "connection_waiting": "Connecting — check the IP, port and network",
        "no_video": "No video received — check stream path or credentials", "vlc_error": "VLC could not play this stream", "not_playing": "Not playing",
        "language": "Language", "ai_tile_rows": "Under each tile", "ai_tile_key": "Group by", "ai_tile_none": "No grouping (latest result only)", "ai_tile_help": "Each ticked kind keeps its own line with its latest result; with none ticked only the latest result is kept. The choices come from the labels in the message format below.", "ai_tile_all_sites": "On OK, use the same for every site", "ai_filter": "Show only", "ai_filter_all": "Everything", "ai_filter_summary": "{field}: {values}", "ai_filter_title": "{camera} — show only", "ai_filter_help": "Results from this camera are shown, under the tile and in the side panel, only when the field has one of the ticked values (inside payload counts too). A result without the field is not shown.", "ai_connections_tip": "AI results — {connected}/{total} connections up", "url_credentials_hint": "You can paste a URL with the username and password in it; they move to the fields below.", "confirm": "OK", "apply": "Apply", "selection": "Selection", "selected_items": "{count} items selected. Del deletes them; Alt+↑/↓ moves sites, or cameras of one site.", "site_cameras": "{site} — {count} cameras (double-click one to edit it)", "editor_hint": "Right-click to add a site or a camera (Ctrl+N). Shift and Ctrl select several; Del deletes, Alt+↑/↓ moves, F2 renames. Nothing is saved until Apply or OK.", "save_changes": "Save changes", "save_changes_confirm": "Save these changes?\n\n{changes}", "unsaved_camera": "Changed, not saved yet", "changed_value": "{field} ({old} → {new})", "change_line": "• {camera}: {fields}", "list_separator": ", ", "appearance": "Appearance", "theme_system": "Follow system", "theme_dark": "Dark", "theme_light": "Light",         "maximize": "Fill app with video", "restore_window": "Restore normal interface", "stream_choice": "Stream {stream}",
        "logs": "Live log", "diagnostics": "Diagnostics", "close": "Close", "no_events": "No events in this session.",
        "sync_diagnostics": "Timestamp sync", "run_sync_probe": "Check current site", "sync_probe_running_button": "Checking…",
        "sync_probe_help": "Read-only check: briefly connects to each RTSP source and looks for RTCP Sender Reports. URLs and credentials are never displayed or stored in this window.",
        "sync_probe_running": "Checking {camera}…", "sync_probe_result_heading": "RTSP timestamp synchronisation capability",
        "sync_ready": "Ready for strict timestamp synchronisation", "sync_unavailable": "No usable RTCP Sender Report — strict synchronisation is unavailable",
        "sync_probe_error": "Could not check: {error}", "sender_reports": "{count} Sender Report(s)",
        "sync_probe_summary": "Eligible sources: {ready}/{total}. Strict sync only lines up sources that are eligible and NTP-synchronised.",
        "enable_strict_sync": "Enable strict sync", "disable_strict_sync": "Use normal playback", "sync_short": "Sync", "syncing": "Syncing — waiting for the shared playback time…",
        "usage": "CPU {cpu}  •  RAM {memory}", "usage_tip": "{players} players; the wall uses about {cores:.1f} of {total} CPU cores", "players_tip": "{players} players", "usage_unknown": "—",                 "copy_suffix": "copy",
        "rename": "Rename", "delete_site_action": "Delete site", "add_camera_action": "Add camera…", "play_together": "Play together ({count} cameras)", "edit_camera": "Edit camera…", "edit_camera_title": "Edit camera", "delete_selected": "Delete", "delete_site_item": "{name} (site, with its cameras)", "delete_selected_confirm": "Delete these {count} items? This is saved at once and cannot be undone.\n\n{items}", "delete_camera": "Delete camera", "delete_camera_confirm": "Delete camera {name!r}?",
        "import_cameras": "Import cameras…", "export_cameras": "Export cameras…", "export_all_cameras": "Export all cameras…", "import_title": "Import cameras", "import_help": "Choose what each column holds; columns left on Skip are ignored. A URL column wins; otherwise the IP, port and stream columns build the URL with the chosen brand. Rows without a site column go to the default site, and new sites are created as needed. Cameras already on a site with the same URL and username are skipped.", "import_skip": "Skip", "field_site": "Site", "field_name": "Name", "field_url": "RTSP URL", "field_host": "IP", "field_port": "Port", "field_stream": "Stream", "field_user": "Username", "field_password": "Password", "import_header_rows": "Header rows to skip", "import_vendor": "Brand (for IP columns)", "import_default_site": "Default site", "import_summary": "{count} cameras to import, {errors} rows with errors (hover for details)", "import_error_line": "Row {row}: {error}", "import_ok": "Import", "import_duplicates": "Imported {added} cameras; {skipped} were already there and were skipped.", "import_read_error": "Could not read the file: {error}", "export_title": "Export cameras", "export_credentials_confirm": "Include usernames and passwords in plain text?\n\nAnyone who gets the file can read them.", "export_all_file_name": "cameras", "export_write_error": "Could not write the file: {error}",
        "duplicate_site": "Duplicate site", "rename_site": "Rename site",         "site_exists": "A site named {name!r} already exists.", "new_site_name": "Site name",
        "ai_events": "AI results", "ai_short": "AI", "reset_layout_tip": "Restore the default layout: even tiles, both side panels at their usual width and shown, camera status off and back in the bottom-right corner", "corner_top_left": "Top left", "corner_top_right": "Top right", "corner_bottom_left": "Bottom left", "corner_bottom_right": "Bottom right", "stats_tip": "Show each camera's status on its picture: resolution, frames shown per second, dropped frames, bitrate and reconnects; the arrow picks the corner. Not shown while playing through GStreamer (strict sync, or AI matched to frame timestamps).", "tile_stats": "{size} · {fps} fps · dropped {lost} · {kbps} kbps · reconnects {reconnects}", "ai_all_cameras": "All cameras",
        "ai_connected": "Connected to {address}", "ai_reconnecting": "Connecting to {address}…",
        "ai_align_frame": "Match the frame timestamps", "ai_align_manual": "Manual display delay", "ai_delay_tip_frame": "Each result appears when the camera's picture reaches its AI time.", "ai_delay_tip_ai_time": "Each result appears {delay} ms after its AI time, with the matching video frame.", "ai_delay_tip_received": "Each result appears {delay} ms after it arrives, with the matching video frame.",
        "ai_event_tip": "AI time {ai_time}\nReceived {received}",
        "ai_clock_skew": "AI and this PC clocks differ by {seconds:.1f}s — check NTP time sync",
        "ai_feeds_action": "AI result connections…", "ai_feeds_button": "AI result connections", "ai_feeds_title": "AI result connections — {site}",
        "ai_feeds_help": "This site connects to every AI server listed here while it is on screen. Add a row per camera this AI server reports: the id it sends (e.g. A001) and the camera from the menu.",
        "ai_add_feed": "Add connection", "ai_remove_feed": "Remove connection", "ai_new_feed": "New connection",
        "ai_host": "AI server IP / host", "ai_delay": "Display delay",
        "ai_delay_help": "Matched to the frame timestamps: a result is held until that camera's picture reaches its AI time, so no delay needs tuning. The wall then plays through GStreamer, which reports when each frame was captured; a result that cannot be matched appears on arrival. Manual delay: a result appears this long after its AI time (or its arrival when it has no time or the clocks are more than 2 s apart); raise it if results come before the picture.", "ai_align": "Align to",
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
        "sites_summary": "{first} 等 {count} 個地點", "ai_status_summary": "已連線 {connected}/{total} 條", "no_site": "尚未選擇地點", "cameras": "已設定 {count} 支攝影機", "camera": "已設定 {count} 支攝影機",
        "live": "●  {live}/{total} 路播放中", "page": "第 {current} / {total} 頁", "previous": "上一頁", "next": "下一頁",
        "reload_tip": "重新連線目前可見的攝影機",
                "no_cameras": "這個地點尚未設定攝影機", "add_camera_hint": "請開啟設定，新增一支攝影機。",
        "settings_title": "設定 — 地點與攝影機",                 "add_site": "新增地點", "add_camera": "新增攝影機", "delete": "刪除", "site_list": "地點列表", "camera_details": "攝影機", "connection": "連線資訊",
                "cancel": "取消", "name": "攝影機顯示名稱", "port": "連接埠", "username": "帳號",
        "password": "密碼", "direct_url": "RTSP 網址",
                        
        "delete_site_confirm": "確定要刪除地點 {name!r} 及其攝影機嗎？",                 "reconnecting": "重新連線中…", "retry_in": "{seconds} 秒後重試", "retry_now": "點一下立即重試", "save_error": "無法儲存設定",
                        "connection_waiting": "正在連線 — 請檢查 IP、連接埠與網路",
        "no_video": "未收到影像 — 請檢查串流路徑或帳密", "vlc_error": "VLC 無法播放這個串流", "not_playing": "未播放",
        "language": "語言", "ai_tile_rows": "畫格下方顯示", "ai_tile_key": "分類欄位", "ai_tile_none": "不分類（只留最新一筆）", "ai_tile_help": "勾選的種類各留一行、顯示該種最新的結果；都不勾時只留最新一筆。選項來自下方訊息格式的 labels。", "ai_tile_all_sites": "按確定時套用至所有地點", "ai_filter": "只顯示", "ai_filter_all": "全部", "ai_filter_summary": "{field}：{values}", "ai_filter_title": "{camera} — 只顯示", "ai_filter_help": "這台攝影機的結果，欄位值是勾選的其中之一才顯示（payload 裡的也算），畫格下方與右側列表都套用；沒有這個欄位的結果不顯示。", "ai_connections_tip": "AI 辨識結果 — 已連線 {connected}/{total} 條", "url_credentials_hint": "可直接貼上含帳密的網址，帳號密碼會自動移到下方欄位。", "confirm": "確認", "apply": "套用", "selection": "已選取", "selected_items": "已選取 {count} 個項目。按 Del 刪除；Alt+↑／↓ 可移動地點，或同一地點內的攝影機。", "site_cameras": "{site} — {count} 台攝影機（雙擊一台可編輯）", "editor_hint": "右鍵可新增地點或攝影機（Ctrl+N）。Shift／Ctrl 可多選，Del 刪除，Alt+↑／↓ 移動，F2 改名。按套用或確認才會儲存。", "save_changes": "儲存變更", "save_changes_confirm": "要儲存以下變更嗎？\n\n{changes}", "unsaved_camera": "已修改，尚未儲存", "changed_value": "{field}（{old} → {new}）", "change_line": "• {camera}：{fields}", "list_separator": "、", "appearance": "外觀", "theme_system": "跟隨系統", "theme_dark": "深色", "theme_light": "淺色",         "maximize": "以影像填滿程式畫面", "restore_window": "還原一般介面", "stream_choice": "串流 {stream}",
        "logs": "即時紀錄", "diagnostics": "診斷資訊", "close": "關閉", "no_events": "本次執行尚無事件紀錄。",
        "sync_diagnostics": "時間戳同步", "run_sync_probe": "檢查目前地點", "sync_probe_running_button": "檢查中…",
        "sync_probe_help": "唯讀檢查：會短暫連線每支 RTSP 攝影機，確認是否收到 RTCP Sender Report。此視窗不會顯示或儲存網址與帳密。",
        "sync_probe_running": "正在檢查 {camera}…", "sync_probe_result_heading": "RTSP 時間戳同步能力",
        "sync_ready": "可納入嚴格時間戳同步", "sync_unavailable": "未收到可用的 RTCP Sender Report，無法嚴格同步",
        "sync_probe_error": "無法檢查：{error}", "sender_reports": "{count} 筆 Sender Report",
        "sync_probe_summary": "可用來源：{ready}/{total}。嚴格同步只能對齊可用且已完成 NTP 校時的來源。",
        "enable_strict_sync": "啟用嚴格時間戳同步", "disable_strict_sync": "改用一般播放", "sync_short": "同步", "syncing": "同步中 — 等待共同播放時間…",
        "usage": "CPU {cpu}  •  記憶體 {memory}", "usage_tip": "播放器 {players} 個；本程式約用 {cores:.1f} 顆核心（全機共 {total} 核）", "players_tip": "播放器 {players} 個", "usage_unknown": "—",                 "copy_suffix": "副本",
        "rename": "重新命名", "delete_site_action": "刪除地點", "add_camera_action": "新增攝影機…", "play_together": "同時播放（{count} 台）", "edit_camera": "編輯攝影機…", "edit_camera_title": "編輯攝影機", "delete_selected": "刪除", "delete_site_item": "{name}（地點，連同其攝影機）", "delete_selected_confirm": "要刪除以下 {count} 項嗎？會立即存檔，無法復原。\n\n{items}", "delete_camera": "刪除攝影機", "delete_camera_confirm": "要刪除攝影機 {name!r} 嗎？",
        "import_cameras": "匯入攝影機…", "export_cameras": "匯出攝影機…", "export_all_cameras": "匯出全部攝影機…", "import_title": "匯入攝影機", "import_help": "選擇每一欄是什麼資料，留在「略過」的欄不匯入。有網址欄時以網址為準，否則用 IP、Port、串流欄依所選廠牌組成網址。沒有地點欄時匯入到預設地點，不存在的地點會自動新增。同一地點已有相同網址與帳號的攝影機會略過。", "import_skip": "略過", "field_site": "地點", "field_name": "名稱", "field_url": "網址", "field_host": "IP", "field_port": "Port", "field_stream": "串流", "field_user": "帳號", "field_password": "密碼", "import_header_rows": "略過開頭幾列（標題）", "import_vendor": "廠牌（IP 欄用）", "import_default_site": "預設地點", "import_summary": "將匯入 {count} 台，{errors} 列有錯誤（滑鼠停留看原因）", "import_error_line": "第 {row} 列：{error}", "import_ok": "匯入", "import_duplicates": "已匯入 {added} 台；{skipped} 台已存在，已略過。", "import_read_error": "無法讀取檔案：{error}", "export_title": "匯出攝影機", "export_credentials_confirm": "要以明文包含帳號與密碼嗎？\n\n拿到檔案的人都看得到。", "export_all_file_name": "攝影機清單", "export_write_error": "無法寫入檔案：{error}",
        "duplicate_site": "複製地點", "rename_site": "重新命名地點",         "site_exists": "地點名稱 {name!r} 已存在。", "new_site_name": "地點名稱",
        "ai_events": "AI 辨識結果", "ai_short": "AI", "reset_layout_tip": "回復預設版面：影像平均分配、左右側欄回到預設寬度並顯示、攝影機狀態關閉並回到右下角", "corner_top_left": "左上角", "corner_top_right": "右上角", "corner_bottom_left": "左下角", "corner_bottom_right": "右下角", "stats_tip": "在每格影像上顯示攝影機狀態：解析度、每秒實際顯示幀數、丟幀數、位元率與重連次數；旁邊的箭頭選擇顯示在哪個角落。改用 GStreamer 播放時（嚴格同步、或 AI 與畫面時間戳一致）無法顯示。", "tile_stats": "{size} · {fps} fps · 丟幀 {lost} · {kbps} kbps · 重連 {reconnects}", "ai_all_cameras": "所有攝影機",
        "ai_connected": "已連線 {address}", "ai_reconnecting": "正在連線 {address}…",
        "ai_align_frame": "與畫面時間戳一致", "ai_align_manual": "手動調整顯示延遲", "ai_delay_tip_frame": "每筆結果在攝影機畫面播到其 AI 時間時顯示。", "ai_delay_tip_ai_time": "每筆結果在 AI 時間後 {delay} 毫秒顯示，以對上同一刻的畫面。", "ai_delay_tip_received": "每筆結果收到後延後 {delay} 毫秒顯示，以對上同一刻的畫面。",
        "ai_event_tip": "AI 時間 {ai_time}\n接收時間 {received}",
        "ai_clock_skew": "AI 端與本機時鐘相差 {seconds:.1f} 秒，請確認 NTP 校時",
        "ai_feeds_action": "AI 辨識連線…", "ai_feeds_button": "AI 辨識連線", "ai_feeds_title": "AI 辨識連線 — {site}",
        "ai_feeds_help": "畫面切到這個地點時，會連到下方列出的每一個 AI 端。這個 AI 端回報幾台攝影機就新增幾列：填它送來的識別值（例如 A001），再從選單選對應的攝影機。",
        "ai_add_feed": "新增連線", "ai_remove_feed": "刪除連線", "ai_new_feed": "新連線",
        "ai_host": "AI 端 IP / 主機", "ai_delay": "顯示延遲",
        "ai_delay_help": "與畫面時間戳一致：結果先暫存，等那台攝影機的畫面播到 AI 時間那一刻才顯示，不需要調延遲。此時畫面改用 GStreamer 播放，才讀得到每張畫面的拍攝時間；對不上時間的結果收到即顯示。手動調整顯示延遲：在 AI 時間後這麼久才顯示（沒有時間欄位或兩端時鐘相差超過 2 秒時改依收到時間），結果比畫面早出現就調大。", "ai_align": "對齊方式",
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
