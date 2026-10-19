# 架構與效能設計

## 依賴方向

單向朝內：`ui/` → 領域模組 → 無依賴的葉節點。領域層不知道 Qt 或 VLC 的存在。

```text
src/cctv_wall/
  vendors.py      舊版各廠牌 RTSP 路徑樣板，只供載入舊設定時轉成網址（無依賴）
  layout.py       格子與分頁算術                              （無依賴）
  resources.py    CPU／記憶體取樣（ctypes 直呼 Windows API，無第三方依賴）
  models.py       Camera（name/url/user/password）/ Site / Workspace，建構即驗證，全部不可變；舊格式在此轉換
  i18n.py         zh_TW／en 翻譯目錄與 Translator（只依賴 models 的語言常數）
  urls.py         Camera → 可播放的網址（播放時才把帳密組進網址）、串流標記替換、日誌遮罩
  performance.py  唯一一組 libvlc 調校：INSTANCE_ARGS（Instance 參數）與 STREAM_OPTIONS（每路選項）
  player.py       Player 協定：VLC 實作 + 測試用假實作（唯一 import vlc 的檔案）
  repository.py   workspace.json 讀寫（唯一碰硬碟的檔案）
  event_log.py    輪替式診斷日誌（1 MB × 4），寫在設定檔旁邊
  vlc_runtime.py  打包後把 python-vlc 指向包內的 libvlc
  gst_sync.py     GStreamer 嚴格時間戳同步後端
  sync_probe.py   逐台攝影機探測 RTCP Sender Report 可用性
  ai_feed.py      AI 結果 TCP 來源：NDJSON 解析、攝影機對照／略過規則／代碼文字、顯示延遲、斷線重連（不碰 Qt）
  build.py        版本化單一 EXE 發行包建置（build cctv-wall）
  ui/theme.py         全站 Qt 視覺主題，明／暗兩套（不含任何行為）
  ui/flat_tree.py     兩層樹狀清單，在列內自繪縮排與展開箭頭（避開 Windows 11 樣式的選取破圖）；側欄與設定視窗共用
  ui/navigation.py    左側地點／攝影機樹狀導覽：只顯示、切換與排序，決策全部往上委派
  ui/view_mode.py     全螢幕／放大單格／填滿畫面等顯示狀態，不可變值，可脫離 Qt 測試
  ui/frameless.py     無邊框視窗的拖曳與縮放邊條
  ui/wall.py          Qt 影像牆：只維持可見格數的播放器與原生 VLC surface
  ui/editor.py        Qt 設定視窗：沒有草稿，每個動作驗證後立即存檔，關閉時影像牆重載一次
  ui/site_commands.py 地點層級指令（複製／改名／刪除）：回傳新的 Workspace 或 None
  ui/logs.py          事件紀錄檢視對話框（唯讀）
  ui/ai_panel.py      AI 結果側欄：把 socket 執行緒的事件轉回 GUI、延遲後分派到畫格
  ui/ai_feed_editor.py AI 辨識連線對話框：連線、攝影機對照、訊息格式（表單↔設定的轉換可單獨測試）
  ui/startup.py       啟動進度畫面
  ui/app.py           Qt 主視窗：組裝上述元件、持有 Workspace 並負責記憶
  __main__.py     進入點：唯一知道真實實作的地方（--check / --dry-run）
tests/
  test_domain.py       模型驗證、URL 組裝、帳密不外露、舊設定轉換、攝影機置換
  test_persistence.py  workspace.json 讀寫、打包後的設定檔路徑、啟動畫面容錯
  test_playback.py     格子分頁、libvlc 選項、打包後的 libvlc 定位
  test_resources.py    CPU 用量換算
  test_i18n.py         翻譯目錄守門：兩語言鍵對齊、無死鍵、佔位符一致
  test_reconnect.py    斷線重連的退避節奏（不需要 QApplication）
  test_sync.py         GStreamer 管線元件與凍結環境的 PATH 行為
  test_build.py        發行名稱清理與建置流程
  test_ai_feed.py      AI 結果解析、時間格式、延遲釋放、本機 loopback 連線與重連
cctv_wall.spec    PyInstaller 打包設定
```

換掉任何一層都只動一個檔案：

| 想改的事 | 要動的檔案 |
| --- | --- |
| 改存 SQLite 或雲端 | `repository.py` |
| 換播放後端（mpv、ffmpeg） | `player.py` |
| 調整 libvlc 解碼／快取參數 | `performance.py` |
| 加地點層級的操作 | `ui/site_commands.py` 加一個函式，並在 `app.SITE_COMMANDS` 加一列 |
| 加介面語言 | `models.SUPPORTED_LANGUAGES` 與 `i18n._MESSAGES` 各加一項（測試會強制鍵對齊） |
| 改 AI 結果的訊息格式 | `ai_feed.parse_line`（連線與顯示不用動） |
| 改視覺樣式 | `ui/theme.py`（明暗各一份明碼 CSS，刻意不抽模板以便一眼掃完） |

---

## 效能設計（低階電腦）

已不再有效能檔。每頁格數由操作員在頂部列設定（`Workspace.tiles_per_page`，
上限 `max_tiles`，預設 16、最多 64），libvlc 只有 `performance.py` 這一組調校。

省 CPU 的手段，依實際效果排序：

1. **只播當前地點的當前頁** —— 40 路的 workspace 也永遠只有一頁的解碼器在跑。
   切換地點或翻頁前會先 `release()` 所有播放器。
2. **網址指向子碼流（如 `/stream2`）** —— 從源頭少送像素，比任何本地優化都有效。
3. **`--avcodec-hw=any`** —— 把 H.264/H.265 解碼丟給 GPU。
4. **`:avcodec-skiploopfilter=nonref`** —— 只對非參考畫格關 deblocking，省下大量 CPU。
5. **`--no-audio`** —— 監視器不需要聲音，一律不解碼音訊。
6. **`--drop-late-frames`** —— 來不及就丟，不要讓延遲累積；快取 1000 ms。
7. **共用一個 libvlc Instance** —— 每個 Instance 都要掃一次外掛並佔記憶體。
8. **錯開建立連線** —— 每頁格數越少間隔越長（≤4 格 650 ms、≤9 格 350 ms、其餘 175 ms），嚴格同步模式不錯開。
9. **CPU 只每 2 秒取樣一次** —— 頂部列的資源顯示不跟著每次重繪取樣。

其他有感的細節：

- 預設打包成單一 EXE，啟動時以兩階段進度提示解壓與載入狀態。
- 不打包 `plugins.dat`，避免 libvlc 每次啟動都因快取失效而重掃並噴錯誤。

還想更省：攝影機網址改用子碼流、每頁格數調小。

> **libvlc 調校對嚴格同步無效**：嚴格同步走 GStreamer，`performance.py` 的選項
> 全是 libvlc 專屬。開啟嚴格同步後只剩「每頁格數」有作用。介面上目前看不出來。

---

## 已知的技術債

### `ui/app.py` 仍有 615 行

曾拆到 457 行（抽出 `ui/site_commands.py`、`ui/logs.py`），加入同步功能後又長回來；
顯示狀態已收進 `ui/view_mode.py`。`MainWindow` 現在同時負責：視窗外觀、地點切換、分頁、
工廠替換、同步開關、頂部列資源顯示、側欄寬度與顯示、快捷鍵、語言切換。

下一刀建議：把 `_toggle_strict_sync` / `_set_strict_sync` / `_refresh_sync_button`
抽成 `ui/sync_control.py`，比照 `site_commands.py` 的做法（回傳新狀態、由
`MainWindow` 套用與持久化），這樣才可測。

其餘分層仍乾淨。

### 註解繁體中文化只完成約 20%

已完成：`layout.py`、`vendors.py`、`vlc_runtime.py`、`models.py`
（其模組層 docstring 仍是英文）。`ui/wall.py`、`ui/editor.py` 只有較新的部分是中文。

作法建議：一次一個模組、改完就跑 `pytest`。守門測試是用正則讀原始碼，
**改註解不影響它們**，但絕對別動到 `t("…")`、`_element("…")`、
`REQUIRED_ELEMENTS` 裡的字面值。

### 重連的後續強化（目前版本已可用，以下屬加分）

- 重連過程沒有專屬提示文字，操作員只看到「未收到影像」。
- 沒有「連續失敗 N 次就標記為長期離線」的狀態，會一直每 30 秒重試下去。
- 重連成功後要等下一次稽核（最多 5 秒），頂部列的播放路數才更新。

### GUI 介面改善

- **字級**：`ui/theme.py` 硬寫 6 種尺寸共 28 處（9/10/11/16/17/20pt），沒有統一級距，
  也沒有讓使用者調整的方式。低階電腦常配小螢幕或高 DPI，建議抽成級距常數 +
  一個全域縮放設定（存進 `workspace.json`）。
- **配色**：明暗兩套各約 60 行明碼 CSS。尚無對比度檢查；
  `QLabel#tileNotice` 的橘字在淺色主題上偏淡。
