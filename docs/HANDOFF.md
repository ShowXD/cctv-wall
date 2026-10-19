# 交接概要（給後續 session 直接銜接）

> 這份文件記錄**程式碼看不出來的決策與陷阱**。
> 功能說明、操作方式、打包指令請看 [`../README.md`](../README.md) 與 `docs/` 底下的
> [USAGE](USAGE.md) / [BUILD](BUILD.md) / [ARCHITECTURE](ARCHITECTURE.md) /
> [TROUBLESHOOTING](TROUBLESHOOTING.md)。
> 最後更新：2026-10-19（介面改版與功能精簡）

---

## 一句話

多地點 Qt 影像牆：RTSP 監視器 / 本機影片，主打低階電腦，可打包成單一 exe。
兩套播放後端：VLC（一般）與 GStreamer（嚴格時間戳同步）。影像一律靜音。

## 環境與常用指令

```bash
uv sync                        # 開發環境
uv run --group dev pytest -q   # 190 passed（不需要 VLC、不連網）
uv run cctv-wall               # 啟動 GUI
uv run cctv-wall --check       # 環境診斷（含 strict sync 探測）
uv run cctv-wall --dry-run     # 用假後端建完整 GUI 後立刻結束
uv run build cctv-wall         # 打包（一律 onefile）
```

**注意**：`.venv` 曾出現沒有 pytest 的狀況，測試請用 `uv run --group dev pytest`。

## 目前狀態（皆為實測，非估計）

| 項目 | 值 |
| --- | --- |
| 測試 | **190 passed**（2026-10-19，`main`，`.venv/Scripts/python -m pytest -q`） |
| exe | **231,630,302 bytes（220.9 MiB）** |
| 最新建置 | `dist/releases/CCTVWall-0.2.0-20260806-171645/`，2026-08-06 17:19 |
| `--check` | 開發環境回報 `strict sync : available` |

**exe 比先前記錄的 186 MB 大了約 36 MB，這是刻意的**——見陷阱 3。

---

## 2026-10-19：介面改版與功能精簡（分支 `refactor/ui-redesign`）

**狀態：已實作、已驗證，依功能分批 commit 在 `refactor/ui-redesign`，已合併回 `main` 並 push，分支已刪除。**
下一步：使用者確認後合併回 `main`；之後可考慮讓工具列 `AI` 按鈕常駐（入口目前只在地點右鍵）。
navbar（選單列）已提出分流建議但使用者暫不實作。

第二輪微調（使用者試用後回饋，227 passed）：
- 方向鍵：清單上下鍵原本就會切換，但移回同地點的地點列時放大的攝影機不會還原；另外 `currentItemChanged`
  在「再點一次已選取的列」時不會觸發，所以「再點同一台還原」實際上點不動。改為選到目前地點就還原，
  並在 `_SiteTree.mouseReleaseEvent`（同一列按下又放開，避免拖曳誤觸）補報重複點擊。
- 每頁格數上限設定移除，固定 `TILES_LIMIT = 36`；舊檔 `max_tiles` 忽略。設定視窗只剩清單＋表單。
- 格數欄位：無上下箭頭、前綴 `▦`、固定寬 64px。CPU 只顯示全機佔比，核心數與播放器數放在滑鼠提示。
- 開啟時 16:9：第一次顯示後量測一格影像大小，用 `layout.fit_window_to_video` 反推視窗大小（只調高度；
  超出螢幕或低於最小高度 600 時固定高度改調寬度）。分隔欄改為只讓影像牆吸收寬度變化，否則加寬時
  多出的寬度會被側欄分走、比例對不上。實測 4／6／9 格開窗後每格 1.774–1.778。
- 另修：側欄清單下方多了一個 stretch，清單只用半個側欄高度，攝影機多時被截斷。

第三輪（232 passed）：
- 不必要的重新連線：`app.wall_needs_reload` 判斷畫面上的地點（攝影機、AI 連線、名稱、是否仍為使用中）
  有沒有變；關閉設定視窗、側欄地點指令都經 `_apply_workspace_change`，沒變只更新側欄。
- 單台重連：`WallView.replace_camera` 只 release／start 那一格（同 `_retry_camera` 作法），攝影機不在本頁
  時什麼都不做；嚴格同步（`factory.synchronized`）共用時鐘，回傳 False 讓呼叫端整頁重建。用於右鍵切串流
  與側欄「編輯攝影機…」。
- 側欄底部拆成「地點與攝影機」「AI 辨識連線…」兩顆（上下排，側欄最窄 160px 並排放不下）；AI 按鈕作用在目前地點
  （`_on_site_action` 收到空地點名稱即目前地點）。
- 單台攝影機：表單抽成 `ui/camera_form.CameraForm`（設定視窗與 `CameraDialog` 共用）；側欄右鍵地點
  「新增攝影機…」、攝影機「編輯攝影機…／刪除攝影機」走 `site_commands` 與 `app.CAMERA_COMMANDS`；
  移除兩處「觀看此地點」（點一下本來就會觀看／放大）。
- 截圖中某個欄位標籤看起來帶顏色，是 ClearType 子像素邊緣，實測所有標籤前景色都是同一色，不是 bug。

測試精簡：232 → 190，約 1.5 s → 0.8 s。刪掉重複、只測語言或測試替身本身、沒有新分支的
參數列；凡是唯一覆蓋某段程式的都保留。順帶修正 `TestRealSample` 一個測錯對象的測試（空 payload 先被
`skip_empty` 擋掉，從未走到對照表檢查）；AI 連線重連測試改把 `ai_feed.FIRST_BACKOFF_SECONDS` 調成 0.05 s，
不再真的等 1 秒。

使用者逐項檢視功能清單後的決定與實作：

- 側欄／設定樹破圖：Windows 11 原生樣式把選取色塊畫進縮排欄，QSS 管不到。改為 `ui/flat_tree.py`
  關掉縮排欄、在列內自畫縮排與箭頭（側欄與設定視窗共用）。換 Fusion 樣式或 `::branch` 規則都試過無效。
- 側欄可拉寬／隱藏並記住（`Workspace.sidebar_width`、`sidebar_visible`）；快捷鍵 Ctrl+B、PgUp/PgDn、
  Ctrl+PgUp/PgDn、F5。
- 點攝影機「一放大就全畫面、無法操作」：根因是聚焦模式設了 `filled`，連側欄工具列一起藏。聚焦已與
  `ViewMode` 脫鉤，只改影像牆。
- 頁首與狀態列合併為單一頂部列；CPU 只由 2 秒計時器取樣（先前每次刷新都取樣，數字會跳）。
- 移除聲音（VLC `--no-audio`）、三種效能檔（改為 `tiles_per_page` 數字欄位＋`max_tiles` 上限，舊值
  low_end/balanced/full → 4/9/16）、YouTube 與 yt-dlp（`resolvers.py` 整層移除）、畫質（`quality.py`）。
- 攝影機只剩 `name/url/user/password`；帳密不放網址、播放時才組入。舊的 host/vendor/stream 設定在載入時
  轉成網址（`vendors.py` 只為此保留）。未命名攝影機顯示網址時不帶帳密（先前側欄會直接顯示密碼）。
- 設定視窗不再有草稿：每個動作立即存檔，關閉時影像牆才重連一次。第 8（攝影機模型）與第 9（設定視窗）步
  合成一個 commit，因為舊表單無法搭配新模型運作。
- 另修：發行資料夾版本改讀 `pyproject.toml`（先前誤標 0.2.0）；DPAPI 解密失敗保留原密文（先前存檔會清空
  密碼）；啟動失敗在無主控台的 exe 改跳對話框並寫紀錄。
- 去重複：唯一地點名稱 → `Workspace.unique_site_name`；收合狀態 → `FlatTree.collapsed_top_level_texts`。
- 驗證：222 passed；以腳本實際開主視窗與設定視窗操作截圖確認（側欄選取、拉寬記憶、聚焦、頂部列、格數排版、
  設定視窗新增／改名／刪除／上限／錯誤提示）；以唯讀方式載入使用者現有 `workspace.json`（Demo 4 台）確認轉換正確。
- 已知：分支建立時使用者正在執行程式，`.venv` 的 `cctv-wall.exe` 被鎖住，`uv sync` 無法完成；
  測試改用 `.venv/Scripts/python -m pytest`。程式關閉後執行一次 `uv sync` 即可恢復（會移除 yt-dlp）。
- 未做：計畫中 B6–B8（嚴格同步說明與實際檢查不一致、嚴格同步的聆聽選單已隨聲音移除、AI 結果條不會自動清除）
  只有 B7 已因移除聲音而消失；D3（播放器釋放邏輯兩份）、D4（兩個建置指令進入點）未處理。

## 2026-10-19：AI 結果 TCP 對照

**狀態：已實作、已驗證，`feature/ai-feed` 已合併回 `main`（`4fbbe14`）並 push，分支已刪除。**
現場仍需以實際 AI 端校準各連線的 `delay_ms`，並確認第二條連線的攝影機識別值。

- 需求：部分專案的 AI 端以 TCP 回傳辨識結果（文字事件/數值），要和影像對照，且時間要對上。
- 實際專案：**2 條 TCP 連線，每條帶 2 台攝影機**，訊息如
  `{"eventType":4,"cameraName":"A001","created":"2026-10-19 12:10:49.750","payload":[...]}`；
  使用者確認 4 台在**同一個地點**（A 方案），該地點設 2 條連線。第二條連線的識別值未確認，
  可能也是 A001/A002，所以每條連線有自己的 `cameras` 對照表。
  `eventType`（0 未知／1 距離偵測／2 淨空區狀態／3 車流統計／4 路口停等偵測）與
  `vdType`（1 公車／2 汽車／3 機車／4 行人／5 卡車／6 大卡車／7 腳踏車）由使用者提供，以 `labels` 設定。
  `payload` 為空的狀態回報每台約每秒一筆，用 `skip_empty: ["payload"]` 略過（**不是**心跳，
  所以不按 eventType 整類濾掉）。
- 格式彈性：「每行一筆 JSON」的差異全部走設定（`camera_key`/`time_key`/`cameras`/`skip`/`skip_empty`/`labels`）；
  非 JSON 格式才需要換 `ai_feed.parse_line`，刻意等真的遇到再做。
- 設計：`Site.ai_feeds`（清單，選填）→ 每條各一個 `ai_feed.AiFeedClient` 背景執行緒讀 NDJSON →
  `ui/ai_panel.AiEventPanel` 以 Signal 轉回 GUI，事件在**每條連線各自的**佇列等滿該連線的 `delay_ms`
  （對齊 VLC 緩衝延遲）才同時顯示到側欄與畫格下方 `tileAi` 條。說明見 [USAGE](USAGE.md)〈AI 辨識結果對照〉。
- 決策：
  - 本程式是 client（使用者確認）；只支援每行一筆 JSON。
  - 用攝影機**名稱**對應（Camera 沒有 id），所以有 `ai_feeds` 的地點在 `Site.__post_init__` 強制名稱不重複，
    且同一台攝影機不可被兩條連線對到。對照表指到不存在的名稱**不**報錯，以免在設定視窗改名後無法存檔。
  - 同一種解析問題每條連線只記一次 log（`parse_line(..., warned)`），否則每秒的狀態回報會洗掉輪替日誌。
  - 文字放在影像外的條狀區，原因同 `tileAudio`：原生 VLC surface 會蓋住疊在上面的 Qt widget。
  - 聚焦單台攝影機時側欄**不隱藏**（`app._refresh_ai_panel`），全螢幕／填滿視窗才隱藏。
  - `ai_feed.py` 用 `logging.getLogger("cctv_wall.ai_feed")` 而非 `event_log.logger()`，避免領域層匯入 Qt。
  - 設定視窗與「複製地點」都會原樣保留 `ai_feeds`（`editor._SiteDraft.ai_feeds`、`site_commands.duplicate_site`）。
- 驗證：解析部分 229 passed（`tests/test_ai_feed.py` 含使用者提供的實際訊息、`labels` 巢狀替換、`skip_empty`、
  本機 loopback 收行、重連、`stop()` 中斷阻塞讀取）；使用者第二批 7 行訊息以完整 `labels` 設定解析，
  2 筆偵測顯示為「路口停等偵測／腳踏車」「距離偵測／機車」，5 筆空 `payload` 略過。
  另以兩個假 AI server（實際格式，皆送 A001/A002）＋`NullPlayerFactory` 實際開主視窗確認：
  兩條皆連線、空 `payload` 全數略過、8 筆偵測正確分到 4 台且代碼顯示為文字、各格下方顯示各自最新結果；
  更早一版也確認過壞行略過、時鐘偏差標 ⚠、點選後聚焦且側欄仍在。
  介面設定（238 passed，新增表單轉換測試）：實際操作對話框新增第二條連線，格式正確沿用、切換連線不遺失輸入、
  確定後產出兩條正確設定；左側欄右鍵路徑會存檔並讓側欄連線，設定視窗路徑在儲存後寫入。
- 介面設定：`ui/ai_feed_editor.AiFeedsDialog`，從左側欄地點右鍵（`site_commands.edit_site_ai_feeds`，
  立即存檔）或設定視窗地點右鍵（同樣立即存檔，見下方介面改版）開啟。IP／port／延遲／攝影機對照用表單；
  `camera_key`/`time_key`/`skip`/`skip_empty`/`labels` 屬於「換專案才改」的訊息格式，刻意用 JSON 文字框，
  新增連線時沿用所選連線的格式。表單→設定的驗證在 `config_from_form`／`feeds_from_forms`（有測試）。
- 刻意沒做：bbox 疊框（需透明頂層視窗）、本程式當 TCP server、非 JSON 格式、事件匯出。
- `uv.lock` 曾停在 0.2.0，導致每次第一次 `uv run` 都會自動改寫它；已由 `01d2cc3 chore: 更新 uv.lock 至 0.4.0`
  修正，合併後在 `main` 實測 `uv run` 不再變動 lock。之後升版號要同時跑 `uv lock` 並一起 commit。

## 這一輪（2026-08-06 下午）改了什麼

### 1. 斷線自動重連（已完成，新功能）

`src/cctv_wall/ui/wall.py`。原本攝影機掉線那一格會永遠凍住，只能手動按 `↻`；
現在稽核迴圈會自己重連。

- 重連時機：`audit_now()` 每 5 秒掃一次，狀態落在 `DEAD_STATES`
  （`ERROR` / `ENDED` / `IDLE`）或起始連線就失敗（`player is None`）時觸發。
- **`OPENING` 不算掉線**：低階電腦協商本來就慢，把它當故障會不斷打斷一個
  其實正在連線成功的來源。這是刻意的，別「順手補上」。
- 退避以「稽核次數」為單位，所以不需要額外計時器：1→2→4→6 次 ×5 秒
  ＝ 延遲 5→10→20→30 秒，上限 `MAX_RECONNECT_BACKOFF_TICKS`。
  影像恢復時 `_Tile.reset_backoff()` 歸零。
- 退避算術抽成模組函式 `_due_for_retry(tile)`，**刻意不碰 Qt**，
  這樣 `tests/test_reconnect.py`（6 tests）不需要 QApplication 就能守住節奏。
- 順手把釋放播放器的重複程式碼收斂成 `_release(tile)`，`stop()` 也改用它。

### 2. 地點／攝影機排序（已完成，新功能）

`src/cctv_wall/ui/editor.py`：設定視窗的樹狀清單右鍵新增「上移／下移」。
地點與攝影機共用同一段程式（`_selected_row()` 回傳「位置＋所屬清單」），
在邊界時該選項會 disable。

**沒有改任何模型**：`workspace.json` 的 `sites` / `cameras` 本來就是有序陣列，
順序即排列順序，存檔就生效。地點順序決定側欄排列，攝影機順序決定影像牆格子順序。

新增翻譯鍵 `move_up` / `move_down`（兩種語言都已加）。
注意寫法：因為 `tests/test_i18n.py` 是用正則掃 `t("字面值")`，
所以迴圈裡寫的是 `self._translator.t("move_up")` 而不是 `t(key)`，
否則會被判成死鍵。**日後新增用迴圈套用的翻譯時請比照辦理。**

側欄（`ui/navigation.py`）改用拖曳排序，設定視窗維持 `上移`／`下移` 選單。
兩者寫回同一份 `Workspace`；側欄只允許同層拖曳，跨地點搬移仍只在設定視窗做。

### 3. 註解繁體中文化（**只完成約 20%**）

實測目前覆蓋率：

| 類型 | 繁中 | 英文 |
| --- | --- | --- |
| `#` 註解 | 8 行 | **85 行** |
| docstring | 31 個 | **138 個** |

**已完成的檔案**：`layout.py`、`vendors.py`、`vlc_runtime.py`、
`models.py`（其模組層 docstring 仍是英文，漏掉了）。
`ui/wall.py`、`ui/editor.py` 只有這次新寫的部分是中文，舊程式仍是英文。

**完全沒動**：`__main__.py`、`build.py`、`event_log.py`、`gst_sync.py`、
`performance.py`、`player.py`、`repository.py`、`resolvers.py`、`resources.py`、
`sync_probe.py`、`urls.py`、`i18n.py`、`ui/app.py`、`ui/logs.py`、
`ui/navigation.py`、`ui/site_commands.py`、`ui/startup.py`、`ui/theme.py`。

作法建議：一次一個模組、改完就跑 `pytest`。守門測試是用正則讀原始碼，
**改註解不影響它們**，但絕對別動到 `t("…")`、`_element("…")`、
`REQUIRED_ELEMENTS` 裡的字面值。同時精簡：講「為什麼」的留下，講「做什麼」的直接刪。

---

## 陷阱：改動前必讀（每一條都是實際踩過的）

### 1. GStreamer 在凍結環境靠 `PATH`，不是 `add_dll_directory()`

`gst_sync._prepare_frozen_runtime()` 裡把 `runtime/bin` 前置到 `os.environ["PATH"]`
的那一行**不能刪**。typelib 宣告的 DLL 由 GLib 的 `g_module_open()` 載入，走 Win32
`LoadLibrary`，**不帶** `LOAD_LIBRARY_SEARCH_USER_DIRS`，因此完全看不到
`os.add_dll_directory()` 註冊的目錄。

刪掉的症狀非常誤導：`gi` 匯入成功，然後 `Gst` 變成空殼，最後以
`TypeError: must be an interface` 收場，同步按鈕彈警告後自己彈回，畫面繼續用 VLC 播
——「有影像但不同步」。`tests/test_sync.py` 有一項專門鎖住這個 `PATH` 行為。

### 2. `excludes` 不會移除「被掃描器收集的 binary」

`cctv_wall.spec` 的兩道去重（`_is_unreachable_gstreamer_copy()` 與
`SKIPPED_PLUGIN_PACKAGES`）詳見 README 的「exe 體積與 GStreamer 去重」。
拿掉它們，exe 會再胖 50 MB。**這兩道目前都還在，不要動。**

### 3. plugin wheel 的 `bin/` 現在會被打包（2026-08-06 17:12 的變更）

`gstreamer_payload()` 裡新增了一段：把每個 plugin wheel 的 `bin/`
（`gstlibav.dll` 需要的 `avcodec-61.dll`／`avutil` 等 FFmpeg DLL）
複製到 `gstreamer/runtime/bin`。

- **直接原因（實際遇到的）**：**部署目標是 Windows 10，該環境的影像轉譯
  無法正常運作**（走 `d3d11videosink` / `d3d11h264dec` 這條路失敗）。
  舊版沒複製這些支援 DLL，`avdec_h264` 從來就是壞的，等於在那台機器上
  完全沒有可用的解碼器。補上支援 DLL 後才有軟體解碼這條後路。
- **代價**：exe 從 186 MB 變成 220.9 MiB（約 +36 MB）。
- 這是刻意的取捨，而且**是為了讓程式在 Win10 目標機上跑得起來，不是為了保險**。
  **要瘦身時第一個會被盯上的就是這裡——砍掉等於讓 Win10 目標機再次沒有畫面。**
  除非確定所有目標機都是 Win11 且 `d3d11h264dec` 正常，否則不要動。

（舊版 HANDOFF 寫「avdec_h264 本來就是壞的、別花時間修」——**該敘述已作廢**。）

### 4. 打包後失敗一定先看 log 與 `--check`

exe 旁邊有 `cctv-wall.log`（與 `workspace.json` 同目錄）。曾有兩次失敗因為
「except 分支只彈對話框、不寫 log」而完全查不到線索。
**新增任何「彈對話框就 return」的分支時，一律同時寫一行 log。**

### 5. `--replace` 會撞檔案鎖

若剛執行過該版 exe（或 Explorer 開著那個資料夾），`shutil.rmtree()` 會失敗。
已包成人話訊息（`close any running CCTVWall.exe`），看到就照做。

### 6. 兩個守門測試會擋你

- `tests/test_i18n.py` 掃描 `src/` 所有 `t("…")` **字面值**並比對翻譯目錄：
  新增文字**兩種語言都要加**；刪功能忘了刪鍵會被列成死鍵；
  動態組出的鍵要加進 `DYNAMIC_KEYS` 白名單（寫法提醒見上面第 2 節）。
- `tests/test_sync.py` 比對 `REQUIRED_ELEMENTS` 與 `play()` 實際建構的元件，
  改管線要同步兩邊。

### 7. VLC 調校參數對嚴格同步無效

`performance.py` 的 `INSTANCE_ARGS`／`STREAM_OPTIONS` 是 libvlc 專屬選項，嚴格同步（GStreamer）用不到。
開啟嚴格同步後只剩「每頁格數」有作用，GPU 解碼／跳 loop filter 全部不生效。
介面上看不出來，也還沒在 UI 說明。

### 8. 重連的時間單位是「稽核次數」不是秒

改 `AUDIT_INTERVAL_MS` 會**同時**改變重連節奏（目前 5 秒 × 1/2/4/6）。
兩者綁在一起是刻意的（省掉一個計時器），但改之前要知道。

---

## 未完成的工作（依價值排序）

### A. 註解繁中化剩下約 80%

見上面第 3 節，含完整的已完成／未完成檔案清單。

### B. SOLID：`ui/app.py` 又長回 673 行

曾拆到 457 行（抽出 `ui/site_commands.py`、`ui/logs.py`），加入同步功能後又長回來。
`MainWindow` 現在同時負責：視窗外觀、沉浸模式狀態（6 個布林）、地點切換、分頁、
工廠替換、同步開關、資源狀態列、語言切換。

下一刀建議：把 `_toggle_strict_sync` / `_set_strict_sync` / `_refresh_sync_button`
抽成 `ui/sync_control.py`，比照 `site_commands.py` 的做法（回傳新狀態、由
`MainWindow` 套用與持久化），這樣才可測。

其餘分層仍乾淨：領域層（`models`/`urls`/`vendors`/`layout`）不依賴 Qt 或 VLC，
`repository.py` 是唯一碰硬碟的檔，`player.py` 是唯一 `import vlc` 的檔。

### C. GUI 介面改善

- **字級**：`ui/theme.py` 硬寫 6 種尺寸共 28 處（9/10/11/16/17/20pt），沒有統一級距，
  也沒有讓使用者調整的方式。低階電腦常配小螢幕或高 DPI，建議抽成級距常數 +
  一個全域縮放設定（存進 `workspace.json`）。
- **配色**：明暗兩套各約 60 行明碼 CSS（刻意不抽模板，方便一眼掃完）。
  尚無對比度檢查；`QLabel#tileNotice` 的橘字在淺色主題上偏淡。

### D. 重連的後續強化（目前版本已可用，以下屬加分）

- 重連過程沒有專屬提示文字，操作員只看到「未收到影像」。
- 沒有「連續失敗 N 次就標記為長期離線」的狀態，會一直每 30 秒重試下去。
- 重連成功後要等下一次稽核（最多 5 秒），狀態列的播放路數才更新。

### E. 其他可再瘦身（刻意沒動）

| 項目 | 未壓縮 | 顧慮 |
| --- | --- | --- |
| plugin `bin/` 支援 DLL | ~36 MB | **不能砍，見陷阱 3**：Win10 目標機的影像轉譯不正常，全靠這條軟體解碼後路 |
| `opengl32sw.dll` | 20 MB | Qt 軟體 OpenGL 後援。純 Widgets 理論上不需要，但本專案主打低階電腦，顯卡驅動不全時可能真的會退回它——要實機測 |
| `gstreamer_plugins_gpl_restricted` | 23 MB | 含 x264/x265（編碼器，播放用不到）。另有散布 GPL 的授權問題值得確認 |
| **只留 GStreamer、砍掉 VLC** | **136 MB** | 架構級重寫：`player.py` 整支、`performance.py` 的 libvlc 調校都要改。GStreamer 功能上是 VLC 的超集，但工程量與回歸風險都大 |

---

## README.md 的同步狀態

**已於 2026-08-06 17:40 校正完畢**，與程式碼一致。當時修掉的是：

- 三處「127 個測試」→ **154**
- 疑難排解「斷線後畫面凍住／目前沒有自動重連」→ 改為說明自動重連與 `↻` 的差別
- 「已經刻意不做的事」不再把斷線自動重連列為未做，並新增獨立的
  「斷線自動重連」章節（含 `OPENING` 不算掉線、退避 5→30 秒的說明）
- 體積「約 186 MB」→ **231,630,302 bytes（約 221 MiB）**，並註明舊組成表是
  加入 plugin `bin/` 之前的版本
- 設定視窗章節補上「上移／下移」排序

**日後改功能請順手掃一次 README**：這個專案已經發生過兩次「程式改了、README 留著
反向敘述」的情況（自動重連被同時寫在「已實作」與「刻意不做」兩處）。
最容易過期的四個地方是：測試數量、exe 體積、疑難排解表、「已經刻意不做的事」。

---

## 搬移專案後要確認的事

1. `uv sync` 重建環境（`.venv` 不要跟著搬）。
2. `uv run --group dev pytest -q` → 應為 **190 passed**。
   `tests/test_persistence.py` 有一項會檢查專案根目錄存在 `pyproject.toml`。
3. `uv run cctv-wall --check` → `libvlc` 要有版本號、`strict sync` 要 available。
   原機 VLC 在 `C:\Tools\VLC`；換機器要確認 `find_vlc_dir()` 找得到，或用 `--vlc-dir` 指定。
   **64-bit Python 必須配 64-bit VLC。**
4. 重新打包一次，看 stderr 的三行 `[cctv-wall]` 訊息（VLC 檔數、GStreamer 檔數、
   丟掉的重複檔數）。體積若明顯偏離 220 MiB，先查陷阱 2 與 3。
5. **實際部署目標是 Windows 10，該機影像轉譯不正常**（陷阱 3）。
   驗收一定要在那台 Win10 上跑打包後的 exe，開發機（Win11）跑得動不代表過關。
6. `workspace.json` 內含**明碼密碼**，別進版控、別放共用磁碟。見 [../SECURITY.md](../SECURITY.md)。
7. `dist/`、`build/`、`cctv-wall.log` 可以不搬（純產物與快取），`.gitignore` 已排除。
8. 專案已納入 git 版控（GitHub：`ShowXD/cctv-wall`），CI 與自動打包見
   [BUILD.md](BUILD.md)。這份文件保留下來的價值只剩「程式碼與 commit 訊息看不出來的
   決策與陷阱」。
