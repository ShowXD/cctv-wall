# 交接概要（給後續 session 直接銜接）

> 這份文件記錄**程式碼看不出來的決策與陷阱**。
> 功能說明、操作方式、打包指令請看 [`../README.md`](../README.md) 與 `docs/` 底下的
> [USAGE](USAGE.md) / [BUILD](BUILD.md) / [ARCHITECTURE](ARCHITECTURE.md) /
> [TROUBLESHOOTING](TROUBLESHOOTING.md)。
> 最後更新：2026-10-30（匯入匯出 #2 與 RTSP 畫面緩衝修正已合併 main 並推送）

---

## 一句話

多地點 Qt 影像牆：RTSP 監視器 / 本機影片，主打低階電腦，可打包成單一 exe。
兩套播放後端：VLC（一般）與 GStreamer（嚴格時間戳同步）。影像一律靜音。

## 環境與常用指令

```bash
uv sync                        # 開發環境
uv run --group dev pytest -q   # 251 passed（不需要 VLC、不連網）
uv run cctv-wall               # 啟動 GUI
uv run cctv-wall --check       # 環境診斷（含 strict sync 探測）
uv run cctv-wall --dry-run     # 用假後端建完整 GUI 後立刻結束
uv run build cctv-wall         # 打包（一律 onefile）
```

**注意**：`.venv` 曾出現沒有 pytest 的狀況，測試請用 `uv run --group dev pytest`。

## 目前狀態（皆為實測，非估計）

| 項目 | 值 |
| --- | --- |
| 測試 | **251 passed**（2026-10-30，`main`，`uv run --group dev pytest -q`） |
| exe | **231,630,302 bytes（220.9 MiB）** |
| 最新建置 | `dist/releases/CCTVWall-0.2.0-20260806-171645/`，2026-08-06 17:19 |
| `--check` | 開發環境回報 `strict sync : available` |

**exe 比先前記錄的 186 MB 大了約 36 MB，這是刻意的**——見陷阱 3。

---

## 2026-10-30：攝影機狀態的位元率永遠是 0 kbps（分支 `fix/tile-bitrate`，從 `main` 開）

**狀態：已修正、已驗證，尚未 commit。**
- 原因：`VlcPlayer.stats()` 只看 `MediaStats.input_bitrate`。VLC 3 的 live555（RTSP）自己收網路資料、不經過 stream 層，
  `input_bitrate`／`read_bytes` 永遠是 0；`demux_bitrate`／`demux_read_bytes` 由 es_out 統計，所有來源都有。
- 修正：`player.input_kbps(counters)`，input 為 0 時改用 demux（單位同為 bytes/ms）；本機檔案行為不變。
- 檢查：pytest 253 passed（新增 `TestBitrate` 2 項）、`--dry-run` 0；以 `--vout=dummy` 播一台現場 1080p 攝影機，
  修正前 input 0、修正後 530～558 kbps（與 demux_read_bytes 兩次取樣相減一致）。
- 同次確認：9 路 1080p 主碼流記憶體約 1947 MB（每路約 195 MB）屬正常，不需修改；多格時改用子碼流最有效。

---

## 2026-10-28：RTSP 大畫面被截斷（分支 `fix/rtsp-frame-buffer`，已合併 main）

**狀態：已修正、已測試，2026-10-30 已合併 main 並推送、分支已刪除；尚未用現場攝影機確認。**
- 現場 log：`MultiFramedRTPSource::doGetNextFrame1(): The total received frame size exceeds the client's buffer size (250000).
  N bytes of trailing data will be dropped!`。VLC 的 live555 每張畫面預設只留 250 000 bytes，高解析度主碼流的關鍵影格
  超過就丟掉後段，畫面下半部花掉到下一張關鍵影格。
- 修正：`performance.media_options_for` 對 RTSP 加 `:rtsp-frame-buffer-size=2000000`（`RTSP_FRAME_BUFFER_BYTES`）。
  已確認本機 libvlc 3.0.24（`C:\Tools\VLC`）的 live555 外掛有此選項。GStreamer 後端不受影響。
- 檢查：分支上 pytest 239 passed（新增一項選項測試）、`--dry-run` 0；合併後的結果見開頭表格。
- 下一步：使用者重新啟動後看 log 是否還有這行、畫面下半部是否正常。

---

## 2026-10-22：攝影機清單 Excel／CSV 匯入與匯出（分支 `feature/camera-import-export`，已合併 main）

**狀態：已實作、已測試，2026-10-30 已合併 main 並推送、分支已刪除；尚未重新打包驗證 exe 內的 openpyxl。** Issue：#2（2026-10-30 已關閉；打包與現場實測兩項未勾）。
- 需求：現場拿到的連線資訊是 Excel／CSV、欄位每份不同；要能指認每欄是什麼後一次匯入，也要能匯出。
- 使用者決定：Excel 用 **openpyxl**（新增相依 `openpyxl>=3.1.5`，帶入 `et-xmlfile`；只支援 `.xlsx`）；
  可指認地點欄（不存在就新增地點）；支援只有 IP／Port 的資料（選廠牌樣板組網址）；匯出前詢問是否含帳密（預設否）。
- `camera_table.py`（領域層）：`read_rows`（CSV 先 `utf-8-sig` 再 `cp950`；xlsx 的 554.0 轉回 554）、
  `guess_mapping`（標題關鍵字，比對順序避免 username 被當名稱）、`cameras_from_rows`（交給 `Camera.from_raw`，
  錯誤列回報試算表列號後繼續）、`merge_into`（同地點相同網址＋帳號略過）、`table_rows`／`write_rows`。
- `ui/table_import.py`：每欄上方下拉選欄位（同一欄位只能指給一欄）、標題列數、廠牌（只在有 IP 欄且無網址欄時啟用）、
  預設地點、即時摘要與錯誤 tooltip。指令掛在 `app.SITE_COMMANDS`（`import_cameras`／`export_cameras`／`export_all_cameras`）；
  側欄地點右鍵與清單空白處右鍵（原本空白處沒有選單）。signal 皆接 bound method。
- 檢查：pytest 248 passed（新增 `tests/test_camera_table.py` 10 項；`test_i18n` 的 INDIRECT_KEYS 納入匯入欄位標籤）、
  `--dry-run` 0；offscreen 腳本操作對話框：猜欄位、改指認時另一欄自動清空、IP＋hikvision 組網址、錯誤列號正確、新地點建立。
  尚未在實際視窗點選檔案對話框、尚未打包。
- 使用者實測後要求可選工作表（原本只讀作用中的那張）：`camera_table.sheet_names`／`read_rows(path, sheet)`，
  對話框上方「工作表」下拉（CSV 不顯示），換工作表重建預覽、重新猜欄位與標題列數；損毀或假 `.xlsx` 改回報讀檔錯誤
  （openpyxl 拋的 `InvalidFileException`／`BadZipFile` 原本不在攔截範圍，指令會直接中斷）。
  檢查：pytest 250 passed；offscreen 腳本確認切到第二張工作表後匯入 2 台、CSV 不顯示工作表選單。
- 下一步：以 main-build 或重新打包的 exe 實測匯入一份現場 xlsx 與匯出（確認 openpyxl 已收進 exe）。

---

## 2026-10-22：發布 v0.5.0（`main`）

- `pyproject.toml` 版本 0.4.0 → 0.5.0（`uv lock` 只更新專案版本與 exclude-newer 時間戳，相依未變），BUILD.md 範例同步。
  0.4.0（2026-08-25）之後累積的新功能都在這版：設定視窗改版、跨地點多選與同時播放、攝影機狀態、AI 依畫面時間戳對齊、
  版面記憶、可拖曳間隔、共用發布流程。使用者已在現場確認。
- 帶註解 tag `v0.5.0`（沿用 v0.2.0～v0.4.0 格式）→ 共用 workflow 檢查版本、打包、建立正式 Release（`CCTVWall.exe`）。
  這是共用流程第一次發正式版，Actions 結果待確認。
- 檢查：pytest 238 passed、`--dry-run` 0。

---

## 2026-10-22：準備公開 repo：README 改寫與截圖（`main`）

- 使用者要把 repo 設為 public。公開前檢查：`workspace.json` 從未進版控；gitleaks 掃 75 個 commit 無洩漏；
  歷史中的帳密都是範例字串、沒有公網 IP。公開後會看到 commit 作者 email 與本文件（已告知使用者）。
- README 改為常見開源格式：徽章（latest release 不含預先發布版）、截圖、功能分組、下載（正式版與 `main-build`）、
  快速開始、從原始碼建置、文件、貢獻、授權。截圖在 `docs/images/`：`wall.png`（554×311，偏小，建議重新擷取原尺寸覆蓋）、
  `tile-ai-results.png`、`ai-feed-settings.png`、`settings-sites.png`；已檢查無可辨識車牌、人臉或帳密，只有內網 IP。
- CONTRIBUTING 的測試數更新為 238。

---

## 2026-10-22：CI（Linux）測試全過後 Bus error 結束（`main`）

**狀態：已修正、已在 WSL Ubuntu 重現並驗證；已 commit 並推送 main，CI 結果待確認。**
- 症狀：CI 的 `python -m pytest` 236 passed 後印出 `QObject: shared QObject was deleted directly`，接著 Bus error，exit 135。
  Windows 本機不會發生。自 `TestCodePicker` 加入後就存在，推送 main 才觸發 CI 顯現。
- 原因（WSL 最小重現）：signal 接到**持有 self 的 lambda**時，lambda 與 widget 形成循環參考，widget 在 Python 這邊被釋放後
  拖到 QApplication 之後才真正銷毀，Linux 上就崩潰；接 bound method 則不會（PySide 對 bound method 的接收者另有處理）。
  先前一度改用 `activated` 看似修好，只是 GC 順序剛好，單獨跑該測試仍會崩。
- 修正：測試會建立的長駐 widget 改接 bound method——`_CodePicker._key`（`_key_chosen`）、`FlatTree` 展開／收合重繪
  （`_repaint_arrows`）、`SiteNavigation` 的 AI 按鈕與 Alt+↑↓。下拉選單同時改用 `activated`（`_CodePicker._key`、
  對齊方式、AI 側欄篩選、語言），只回應手動選擇，程式內的變更本來就自行呼叫處理函式。
  未改：暫時性選單項目的 lambda，以及測試未建立的 `wall.py`／`editor.py`（exe 只在 Windows 執行，未見問題）。
  之後在 widget 上接 signal，請用 bound method，不要用持有 self 的 lambda。
- 檢查：Windows `pytest` 238 passed（新增手動選擇分類欄位的測試）、ruff 無問題、`--dry-run` 0；
  WSL Ubuntu（Python 3.13、offscreen）：全套、各測試檔、`test_widgets.py` 每個測試各跑 3 次，共 66 次全部 exit 0。
- 重現方式：WSL 中複製 `src`、`tests`、`pyproject.toml` 到暫存目錄，`uv venv -p 3.13` 並安裝 `pyside6-essentials python-vlc pytest`，
  `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_widgets.py::TestCodePicker` 看結束碼。

---

## 2026-10-22：打包發布改用 dev-workflows 共用 workflow，main 更新也進 Release（已合併 main 並推送）

**狀態：三個 repo 已合併 main 並推送（dev-workflows `d9813fb`、traffic-packet `da1d790`，cctv-wall 本次）；Actions 實際執行結果待確認。**
- 使用者在 Release 頁面找不到 main 的建置，並要求與 traffic-packet 同一套固定方法，選擇「main 更新也進 Release」
  與「放進 dev-workflows 共用」。
- `ShowXD/dev-workflows` 新增 `python-windows-release.yml`（`workflow_call`）：
  push main → 刪除並重建預先發布版 `main-build`（tag 指向該 commit，`--latest=false`，永遠只有一份）；
  push `v*` tag → 檢查與 `pyproject.toml` 版本一致 → `gh release create --latest`；手動觸發只有 artifact。
  每次都上傳 artifact（`<app>-<version>-<分支>-<sha7>`，14 天）。Release 資產用 exe 原名，
  `releases/latest/download/<exe>` 連結因此不變（traffic-packet README 依賴這點）。
  專案只提供 `app-name`、`exe-name`、`build`，選用 `prepare`、`sync`、`verify`（`$env:ASSET`）、`release-notes`。
- cctv-wall `release.yml` 改成呼叫它：`prepare` 裝 VLC、`build` 檢查 `VLC bundling: DISABLED`、`verify` 跑 `--check`。
  Release 檔名由 `CCTVWall-vX.Y.Z.exe` 改為 `CCTVWall.exe`。原本 softprops/action-gh-release 改由 runner 上的 `gh`。
- traffic-packet `release.yml` 同樣改呼叫共用 workflow，README〈發布〉同步更新。
- 合併順序：dev-workflows 必須先合併並推上 main（兩個專案引用 `@main`），再推兩個專案，否則 Actions 找不到 workflow。
- 檢查：PyYAML 解析三個檔案、`actionlint` 三個檔案無警告。尚未在 GitHub 實際跑過。

---

## 2026-10-22：main 每次更新自動打包 exe 到 Actions artifact（`main`，已由上一節取代）

**狀態：已 commit 並推送；推送即觸發第一次建置，結果尚待確認。**
- 沿用 `.github/workflows/release.yml`（原本只有 tag 與手動觸發）：`on.push` 加上 `branches: [main]`（使用者的流程是在本機分支開發、合併後推送 main，
  只打包 main 可避免日後推送功能分支時每個半成品都跑一次；其他分支用手動觸發）。
  分支 push 只上傳 artifact（`CCTVWall-<version>-<分支>-<sha7>`，分支名稱非 `[A-Za-z0-9._-]` 換成 `-`），
  建立 Release 的步驟仍只在 tag 執行。新增 `concurrency`：同一 ref 的新 push 取消舊建置，tag 不取消。
- main 每次更新都會跑一次 Windows 打包（含 `choco install vlc`），會用掉 Actions 分鐘數。
- 檢查：PyYAML 解析 workflow 成功；PowerShell 模擬命名：分支 `fix/editor-add-button` → `CCTVWall-0.4.0-fix-editor-add-button-ac14c9c`，
  tag `v0.4.0` → `CCTVWall-v0.4.0`。

---

## 2026-10-22：版面記憶與一鍵回復、攝影機狀態可選角落（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已驗證，已合併 main 並推送。**
- 使用者要狀態文字預設右下角、可選位置或拖曳吸附。拖曳做不到：文字是 libvlc marquee 畫在原生影像視窗裡，
  Qt 收不到那塊的滑鼠事件，也無法在原生視窗上疊 Qt 元件。改成四角擇一（`Player.show_overlay(text, corner)`，
  VLC marquee Position 5/6/9/10），工具列長條圖按鈕改 `MenuButtonPopup`，箭頭選角落（objectName `compactMenuAction`）。
- `Workspace` 新增（設定檔皆可省略，舊檔照讀）：`ai_panel_width`／`ai_panel_visible`、`stats_visible`／`stats_corner`、
  `tile_layouts`（`{"3x3": {"rows": [...], "columns": [...]}}`，壞的項目略過）。`with_default_layout()` 回復這些與側欄，
  視窗大小位置不動。工具列新增四格圖示 → `MainWindow._reset_layout`（不重新連線）。
- 影像格比例：放開拖曳即存（`WallView.on_layout_changed`）；`_GridSplitter` 記住比例並在 resize 時重新套用
  （QSplitter 原本依 stretch 分配增減的空間，重開時視窗尚未到最終大小就套用會走樣，實測 0.17 變 0.23）。
  有存比例的形狀，開啟時不做「調成 16:9」（`video_surface_size` 回 None），否則依第一格大小算出的視窗會縮小。
- AI 側欄寬度在關閉時存（與側欄相同時機），顯示與否在切換時存。
- 檢查：pytest 237 passed（新增 `TestLayoutPreference` 3 項）、ruff 無問題、`--dry-run` 0；smoke（`MainWindow` dry-run）：
  拖曳後關閉重開（同視窗大小）列高／欄寬、側欄 340、狀態開啟與左上角全部一致；較小視窗重開時只受最小尺寸影響；
  回復預設後平均分配、側欄 260、狀態關閉右下角、`tile_layouts` 清空；有 AI 連線時 AI 側欄寬度與隱藏狀態會記住。
  工具列截圖確認長條圖按鈕與箭頭不擠。
- 2026-10-22 使用者以重新打包的 exe 現場確認：狀態顯示在所選角落、版面重開後一致。

---

## 2026-10-22：主畫面清單 Alt+↑↓ 整段移動、Del 刪除；修正拖曳排序蓋掉較新的設定（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已驗證，已合併 main 並推送。**
- `SiteNavigation`：`Alt+Up/Down` 移動選取的攝影機（同一地點才動）或目前的地點，移動後重新選取；`Del` 把
  (地點, 攝影機) 交給視窗 `_delete_from_list` → `site_commands.delete_items`：一次確認列出全部項目（最多 15 筆＋…），
  確認後經 `_apply_site_command` 存檔（主畫面立即存檔、沒有取消，所以這個確認不能省）。
- 修正（既有 bug）：清單排序原本把清單自己那份 workspace 整份交回視窗，而清單的那份不會隨「目前地點」「每頁格數」
  「側欄寬度」「右鍵切換串流」等更新，拖曳後這些會被舊值蓋掉（實測：換到 S3 再移動地點，畫面跳回 S1）。
  現在清單只送順序 `Order`（地點名＋攝影機原索引），視窗用 `navigation.apply_order` 套到自己的 workspace；
  順序和現況對不上時不做任何事。`_on_sites_reordered` 也改走 `_apply_site_command`，只有畫面上的地點變了才重載影像。
- 檢查：pytest 234 passed（新增移動、刪除、`apply_order` 共 5 項）、ruff 無問題、`--dry-run` 0；smoke（`MainWindow`
  dry-run）：Alt+↑ 兩台整段上移且影像順序跟著變、頂端再按不動、換到 S3 再移動地點畫面仍是 S3、Del 確認後刪除並存檔。

---

## 2026-10-22：AI 只連畫面上攝影機的連線、每格顏色不重複（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已驗證，已合併 main 並推送。**
- `MainWindow._ai_sites`：被看的地點只保留對照表含「本頁畫面上攝影機」的連線（放大單台時只算那一台）；
  沒有對照表的連線一律保留。`_cameras_on_page` 以放大前的頁碼計算。放大／還原時也呼叫 `_watch_ai`
  （AI 側欄只增減有變的連線）。嚴格同步／時間戳後端的判斷仍看整個地點（`_watched_sites`），放大時不會換播放後端。
- 顏色：`AiEventPanel.watch(sites, shown)`，本頁的格子依序先分配顏色；本頁超過 8 格改用黃金比例分散色相
  （`_camera_colour`），36 格內不重複。原本是依地點全部攝影機的索引取 8 色循環，9 格必定重複。
- 檢查：pytest 229 passed（新增顏色測試）、ruff 無問題；smoke（9 地點各 2 台、每台一條連線）：整個 S1 → 2 條、
  跨 9 地點各選 1 台 → 9 條且 9 色不同、放大一台 → 1 條、還原 → 9 條。

---

## 2026-10-22：影像間隔可拖曳、AI 連線狀態與頂部地點可收合（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已用腳本與截圖驗證，已合併 main 並推送。**
- `WallView` 的 `QGridLayout` 改成垂直 `QSplitter`（列）內含每列一個水平 `QSplitter`（`objectName=wallGrid`）。
  拖某列的欄邊界由 `_align_columns` 套到其他列；最後一列不足欄數時補空白 `QWidget` 讓欄對齊。
  `setOpaqueResize(False)`：放開才調整，拖曳中不會每一步都重設所有原生影像視窗的大小（遠端桌面／低階電腦）。
  先把整個 splitter 掛上視窗才呼叫 `surface.winId()`，避免原生視窗重新掛載而換掉 handle。放大單格改成隱藏其他列與格。
  尺寸不記住，換頁回到平均。間隔固定 6px（填滿畫面時原本是 2px，現在一樣 6px）。
- 畫格下方 AI 結果條沒有改成自動換行：換行會隨每筆結果改變高度、連帶重設原生影像視窗大小；改用拖曳放大格子，tooltip 仍有全文。
- AI 側欄連線狀態超過 `STATUS_LINES_SHOWN`（3）條時收合成「已連線 x/y 條 ▾」，點擊展開／收合。
- 頂部列 `ControlBar.show_status` 改收地點名稱 tuple：兩個以上收合成「1N1 等 n 個地點 ▾」，點擊展開，tooltip 為完整清單。
- 檢查：pytest 228 passed、ruff 無問題；smoke（`MainWindow` dry-run、5 地點 10 條連線）：拖第一列欄邊界後兩列欄寬一致
  （870／470），標題與連線狀態收合／展開正確，截圖確認。

---

## 2026-10-22：主畫面地點清單的 Ctrl／Shift 多選＋右鍵同時播放（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已測試，已合併 main 並推送。**
- 原本 Ctrl 與 Shift 都只是「點攝影機加選／取消」，點地點列沒有作用。改成和設定視窗一致：
  `Ctrl`＋點攝影機逐一切換、`Ctrl`＋點地點列切換該地點全部攝影機；`Shift`＋點選取錨點（上一次點的列）到這一列
  之間的攝影機，範圍兩端或收合的地點列帶入全部攝影機，中間展開的地點只算範圍內的攝影機列。
  點選只改選取，不再立刻換畫面：在選取的攝影機上右鍵選「同時播放（N 台）」（`play_together`）才呼叫
  `on_cameras_picked`；右鍵點在多選範圍內時不會改掉選取，也不會出現單台的編輯／刪除。
  （`ui/navigation.py` 的 `_pick`／`_pick_range`／`_selected_cameras`、`_show_context_menu`）
- 檢查：pytest 228 passed（新增 `TestSitePicking` 3 項）、ruff 無問題。測試裡換掉 `QMenu.exec` 要用 Python 子類別，
  `mock.patch.object(QMenu, "exec")` 不生效，選單會真的開啟而卡住。

---

## 2026-10-22：AI 結果與畫面時間戳一致（GStreamer 各自播放）／手動延遲（分支 `fix/editor-add-button`，已合併 main）

**狀態：已實作、已用 Demo 攝影機驗證播放與時間戳讀取；未接實際 AI 驗證，已合併 main 並推送。**
- 使用者回報「依 AI 時間」沒有真的對齊：原本只是 AI 時間＋固定 `delay_ms` 對本機時鐘，完全沒看攝影機畫面。
  使用者要兩種：①畫面與 AI 時間一致（每台攝影機各自等到畫面播到 AI 時間）②手動延遲，不強制任何模式。
- VLC（libvlc 3）不提供畫面的拍攝時間，只有相對播放時間；GStreamer 每張畫面帶 RTCP/NTP 時間：
  `rtspsrc add-reference-timestamp-meta=true`，從 sink 的 `last-sample` 讀 `timestamp/x-ntp` meta。
  `Player.frame_lag()`＝本機現在減去畫面上那一格的拍攝時間（攝影機時鐘）；少數畫面沒有 meta 沿用上一次的值；
  VLC 回 None，`NullPlayer` 回 `self.lag`。
- `align="frame"`（`ai_feed.ALIGN_FRAME`）：`due_at`＝`event_time + frame_lag`；沒有 frame_lag／AI 時間、或要等超過
  `MAX_DELAY_MS` 時收到即顯示。`ai_time`／`received` 行為不變。`release_due` 帶每台攝影機的查詢函式，
  `AiEventPanel(frame_lag=…)` → `WallView.frame_lag(camera)`。
- 播放後端改由 `MainWindow._use_backend(strict, timestamps)` 決定：嚴格同步 → GStreamer 同步；畫面上的地點有
  `frame` 連線 → `GStreamerSyncPlayerFactory(synchronized=False)`（latency 1000、無 ntp-sync／ts-offset、各格獨立重連）；
  其餘 → VLC。`_show_current_page` 每次確認，種類相同不動作；GStreamer 載入失敗只警告一次（`_timestamps_unavailable`）。
  嚴格同步開關不受影響。`_factory_builder` 的 build 多一個 `timestamps` 參數。
- 對話框對齊方式只剩兩項：與畫面時間戳一致（延遲欄與 −／＋ 停用）、手動調整顯示延遲；舊的 `received`
  顯示為手動且存回 `received`（不讓現場已校準的延遲位移），從 frame 改成手動存為 `ai_time`。
  主題原本沒有 disabled 樣式（停用的欄位看起來和可編輯一樣），兩套主題補上按鈕／輸入框的 disabled 灰階。
- 實驗（Demo 兩台）：不同步、latency 1000 的管線仍有 meta；兩格 frame_lag 穩定（約 3.6 s 與 1.3 s，差異來自
  兩台攝影機時鐘本身不同，sync_probe 的 SR 也顯示其中一台慢數秒）。第一個 SR 前的 meta 是依本機時間推估。
- 限制：需要 AI 時間與攝影機時鐘一致（AI 時間就是畫面拍攝時間，或同一台 NTP）；`created` 是拍攝時間還是
  AI 產生時間仍待使用者確認，若是後者結果會晚約 AI 處理時間，目前沒有往前微調。GStreamer 模式沒有狀態數字。
- 檢查：pytest 225 passed（新增 frame 對齊 3 項、管線模式 2 項）、ruff 無問題、`--dry-run` 0；
  smoke（`MainWindow`＋真的 builder＋Demo）：frame 連線 → GStreamer 非同步、兩格 frame_lag 有值；
  嚴格同步開／關正常切換；改回手動連線 → VLC；對話框 frame 時延遲停用、舊 `received` 保留。
- **已知問題（使用者決定暫緩）**：現場回報 AI 結果常比畫面早出現、間隔可達約 3 秒（攝影機已確認有校時）。
  原因未查；可能是 exe 不是這個版本、連線選的是手動延遲、`created` 格式（無時區時當本機時間，差超過 30 秒就收到即顯示）
  或 `created` 早於畫面拍攝時間。繼續查需要一行 AI 原始訊息的 `created` 值與當時的對齊方式；
  建議先在側欄每筆提示加上「依畫面時間戳／收到即顯示（原因）」以便現場判斷。
- 下一步：使用者打包 exe，接實際 AI，比對畫面 OSD 時間與結果條。

---

## 2026-10-22：設定視窗改為確認／套用／取消、多選與快捷鍵（分支 `fix/editor-add-button`）

**狀態：已實作、已驗證，已合併 main 並推送。**
- 起因：現場回報「新增」會清掉剛輸入的網址（選地點時表單本來就是空白新攝影機，「新增」只做清空），使用者進一步要求整個視窗改成確認／套用／取消。
- 新模型：`WorkspaceEditor` 持有工作副本 `_workspace` 與已套用的 `_applied`；新增、刪除、改名、排序、攝影機欄位、AI 連線都只改工作副本，`on_change` 只在套用／確認時呼叫。取消（含 Esc、×）直接捨棄，不再詢問。攝影機欄位的變更仍在套用前列出確認。
- 點地點時右邊改為該地點攝影機的唯讀表（密碼遮罩），雙擊跳到該台；點攝影機才是欄位表單；多選時顯示選取數與操作說明。
- 清單 ExtendedSelection：Shift 範圍、Ctrl 加選、Ctrl+A 全選；`Del` 刪除所選（地點與攝影機可混合）、`Alt+↑/↓` 整段移動（全為地點，或同一地點內的攝影機）、`F2` 改名、`Ctrl+N` 用 `camera_form.edit_camera` 小視窗新增攝影機。拿掉「新增」「刪除」按鈕，清單下方有一行操作提示。
- i18n：新增 `confirm`、`apply`、`selection`、`selected_items`、`site_cameras`、`editor_hint`；移除不再使用的 `add`、`delete_site`、`unsaved_changes`。
- 檢查：`uv run --group dev pytest -q` → 220 passed；腳本驗證地點表、Shift 範圍與 Ctrl 加選、Alt+↓ 整段移動、Del、Ctrl+N、套用後仍開著且只回傳一次、取消不回傳、確認後依新順序回傳並關閉。

---

## 2026-10-21：移除 exe 啟動圖（分支 `fix/remove-splash`）

**狀態：已合併 main 並推送；使用者 2026-10-22 以重新打包的 exe 現場確認。**
- 使用者在 Win10 打包實測：PyInstaller `Splash` 反而更慢出現，還先閃一個白色空框。原因是它必須先解壓並啟動 Tcl/Tk 才能畫圖，單一 exe 的主要等待（解壓約 211 MB）它並沒有縮短。
- 使用者選擇移除啟動圖、維持單一 exe：spec 拿掉 `Splash`，刪除 `assets/startup_splash.png` 與 `__main__._close_bootloader_splash`，註解與 BUILD／ARCHITECTURE／README 說明改回「解壓完才有進度小畫面」，並記錄不要再加回來。
- 若之後要更快啟動，可改發佈資料夾版（不必每次解壓），需改 `build.py`。
- 檢查：`uv run --group dev pytest -q` → 220 passed；`--dry-run` 正常；尚未重新打包。

---

## 2026-10-21：對話框截斷、攝影機狀態浮在影像上、跨地點選取、exe 啟動圖（已移除，見上一節）

**狀態：已合併 main 並推送；使用者 2026-10-22 以重新打包的 exe 確認不再有啟動圖與白框。**
- AI 辨識連線對話框：
  - 「畫格下方顯示」橫排的種類被截成「公車 …」。原因是自繪勾選框沒算進項目寬度，現在逐項設定 `sizeHint`。
  - 攝影機對照的下拉選單改顯示 `short_camera_name`（未命名的顯示 IP），完整標籤放在 itemData 與 tooltip；「只顯示」欄依內容寬度。
- 動畫：做過對話框淡入淡出、主視窗開關淡入淡出、側欄滑動，使用者看過後認為效果不明顯、沒必要，已全部移除（`ui/motion.py` 已刪）。
- 攝影機狀態（頂部列長條圖按鈕，不存檔）：
  - `Player.stats()` 讀 libvlc 的 `MediaStats`，`Player.show_overlay()` 用 libvlc 的 marquee 把文字畫在影像裡。原生影像視窗會蓋住 Qt 元件，浮在上面只能這樣做。
  - `WallView` 只在開啟時每秒更新一次：解析度、每秒顯示幀數（兩次取樣相減）、累計丟幀、位元率、重連次數（`_Tile.reconnects`）。
  - `performance.INSTANCE_ARGS` 拿掉 `--no-stats`，否則沒有統計可讀。
  - GStreamer 嚴格同步回傳 None，不顯示。
  - 已用真的 libvlc 播放本機圖片驗證：文字（含中文）畫在影像左上角，fps 與畫面一致。
- 跨地點選取（使用者選「連上所有被選地點的 AI」）：
  - 側欄 Ctrl＋點選不再限同一地點，`on_cameras_picked` 改傳 `(site, index)` 清單；只選同一個其他地點時仍會切到該地點。
  - `MainWindow._picked_cameras` 存 `(site, Camera)`；`_watched_sites` 是影像牆涉及的地點，頂部列標題列出這些地點。
  - `AiEventPanel.watch(sites)` 只增減有變的連線，已連上的不重連；事件以「地點＋標籤」對到 `Camera`，`WallView.show_ai_event` 改用 `Camera` 比對。兩個地點都有叫 Gate 的攝影機也不會送錯格。
  - 多地點時側欄每筆前面標地點；工作區有變動時清掉選取（側欄樹重建後選取本來就不在了）。
- exe 啟動：spec 加入 PyInstaller `Splash`（`assets/startup_splash.png`，由 `assets/splash.png` 縮成 480×270 並加上標題），`__main__` 在進度小畫面出現後呼叫 `pyi_splash.close()`。
- 待使用者實測：
  - 打包後雙擊是否立即出現啟動圖；
  - 現場 RTSP 下狀態數字是否合理（例如 fps 與攝影機設定相近）。
- 檢查：
  - `uv run --group dev pytest -q` → 220 passed（新增 `tests/test_widgets.py`、狀態文字兩項）；
  - `--dry-run` 正常；
  - 腳本以 9N7 的格式截圖：7 種全部完整、攝影機欄顯示 IP；
  - 跨地點腳本：兩個地點各一條 AI 連線，加選第二個地點時第一條沒有重連，結果各自進到自己地點的 Gate 格，按 Esc 回到原地點、只剩一條連線。
  - 尚未實際打包。

---

## 2026-10-21：全專案翻修（分支 `refactor/cleanup`）

**狀態：已合併 main（結構、效能、註解與文件三個 commit），已推送。** 目標：減輕低階電腦（常經遠端桌面觀看）的負擔、職責分明、註解只說明為什麼。
行為不變；子碼流維持手動（使用者決定），文件原本就建議多格時把網址指向 `/stream2`。
- 效能：
  - 畫格下方 AI 結果條同色連續亮著時不再重設樣式表、寬度不隨文字撐開畫格；
  - AI 側欄釋放計時器閒置即停、每批只捲一次、顏色查表；
  - `ai_feed._lookup_tables` 依連線快取對照表；
  - 250 ms 播放確認最多 30 秒且路數有變才更新頂部列；
  - 錯誤狀態條相同就不重套樣式；
  - 事件紀錄視窗逐行附加；
  - 頂部列看不到或最小化時不取樣 CPU。
- 結構：
  - 頂部列抽成 `ui/control_bar.py`（`app.py` 799 → 約 620 行）；`theme.painted_icon` 共用。
  - `event_log` 不再依賴 Qt：以 `add_listener` 訂閱，`ui/logs.py` 用 signal 轉回 GUI 執行緒。
  - `Player.play(url, window_id)`：VLC 參數由 `VlcPlayer` 自己套用；`PlayerFactory.synchronized` 進協定，取代 `getattr`。
  - `Workspace.with_site` / `without_site` / 名稱不重複檢查移進 `__post_init__`，`site_commands` 與設定視窗共用。
  - `_FilterButton` 取代在按鈕上掛屬性；`split_credentials` 公開。
  - `AiEvent.camera` → `camera_label`；`on_solo` → `on_focus`；單一呼叫端的 Optional 回呼改必填。
  - 刪除 `urls.display_url`。
- 註解與文件：
  - 修正過時說法（「唯一…」、已移除的效能檔、設定視窗草稿、`release_due` 的隊首取捨）；
  - 每個檔案的註解統一一種語言；
  - ARCHITECTURE 模組表與效能章節更新；
  - `sync_probe_summary` 改為不暗示會強制檢查。
- 注意：`ai_feed` 不能匯入 `event_log`（`event_log → repository → models → ai_feed` 循環），所以保留子 logger。
- 檢查：
  - `uv run --group dev pytest -q` → 217 passed（新增：Workspace 改名／刪除／重名、查表快取、結果條不重設樣式）；
  - `--dry-run` 正常；
  - 在乾淨直譯器確認 `ai_feed`、`gst_sync`、`event_log`、`player` 不載入 PySide6；
  - 腳本送 600 筆 AI 結果：側欄維持 500 筆並停在最底、閒置後計時器停止，頂部列按鈕、填滿、語言切換正常。

---

## 2026-10-21：指定攝影機篩選、畫格下方設定套用至所有地點、exe 嚴格同步缺模組（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin；exe 由使用者自行重新打包。**
- exe 開嚴格同步跳出 `No module named 'pkgutil'`：`gi` 以 data 複製（spec `excludes` 排除它的分析），
  它 import 的標準庫靠別人順帶收進來；移除 yt-dlp 後 `pkgutil`、`optparse`、`asyncio` 都不在 PYZ
  （`build/releases/CCTVWall-0.4.0-20261021-121044/cctv_wall/PYZ-00.toc` 確認）。`cctv_wall.spec` 的
  `hiddenimports` 補上這三個（經使用者同意）。尚未重新打包驗證。
- 「分類欄位」原本只看訊息最外層，選 `payload` 裡的 `vdType` 時畫格下方永遠不出現；改為任何層級都找
  （`ai_feed._field_values`），payload 有多筆時勾選的種類優先。
- 每條連線新增 `camera_filters`（`{"A001": {"vdType": ["2","5"]}}`）：該攝影機只留欄位值相符的結果，
  畫格下方與側欄都套用，沒有該欄位的結果也不顯示（使用者選「兩個條件都要符合」「連側欄也過濾」）。
  對話框「攝影機對照」多一欄「只顯示」，按鈕開小視窗選欄位與值。
- 「畫格下方顯示」多一個勾選「按確定時套用至所有地點」：分類欄位與勾選複製到所有地點的所有連線
  （`Workspace.with_ai_tile_rows`，由 `site_commands.edit_site_ai_feeds` 套用；設定視窗也改走它）。
- 檢查：`uv run --group dev pytest -q` → 212 passed（新增 8 項）；`--dry-run` 正常；腳本驅動對話框截圖、
  確認兩個地點都套用、篩選只存在 A001。
- 對話框版面重排：左側連線清單縮為約 170px；「連線資訊」與「攝影機對照」並排，「畫格下方顯示」佔整列寬
  （勾選項橫排換行、「套用至所有地點」移到分類欄位同一行）。顯示延遲的上下鈕原本是樣式表蓋不到的原生凸起按鈕
  （QSS 樣式化後 Qt 不畫箭頭），改為隱藏並在旁放扁平 `−`／`＋`（每次 100 ms）；`QCheckBox` 勾選框沿用清單的方框樣式。
  深色／淺色截圖確認。

---

## 2026-10-21：AI 結果依 AI 時間對齊（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin。** 現場回報 AI 結果與畫面時間不同步。
- 原本一律「收到時間＋delay_ms」，AI 端處理時間的抖動直接變成誤差。新增每條連線的 `align`：
  `ai_time`＝`event_time`＋delay（`ai_feed.due_at`），沒有時間或時鐘差 >2 s（`has_clock_skew`）時退回收到時間；
  `received`＝舊行為。設定檔沒有 `align` 時為 `received`（現場已校準的延遲不會變）；對話框新增連線預設
  `ai_time`。`release_due` 改收整個 config。對話框「連線資訊」多一列「對齊方式」。
- 待確認：使用者尚未回覆 `created` 是畫面拍攝時間還是 AI 產生結果的時間（影響可對齊的精度，不影響做法）。
  未做：側欄的延遲快速調整、嚴格同步模式下的自動對齊（方案 B）。
- 順帶：清單勾選框統一為方框（已勾填滿主題色），先前補清單樣式後已勾項目的外框消失。
- 檢查：`uv run --group dev pytest -q` → 204 passed（新增 3 項對齊測試）；對話框截圖確認選項與勾選框。

---

## 2026-10-21：外觀一致、統一捲軸、側欄多選攝影機（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin。**
- 現場透過遠端桌面觀看時，深色主題下清單、表格、文字框與表單標籤仍是淺色：Qt 改用舊的 windowsvista
  樣式，調色盤固定是淺色，而樣式表沒涵蓋這些元件。以 `QApplication.setStyle("windowsvista")` 重現。修正：
  `theme.application_palette` 依主題設定整個調色盤（`__main__._apply_system_theme` 與樣式表一起套用），
  樣式表補上 QListWidget／QTableWidget／QPlainTextEdit／QHeaderView。
- 所有捲軸統一為細圓角、無箭頭（兩套主題各一組顏色）。
- 側欄 Ctrl／Shift＋點攝影機：`_SiteTree` 改為 ExtendedSelection 但自己處理挑選（一般點擊仍單選），只限同一地點；
  `MainWindow._picked_cameras` 非空時影像牆只顯示它們（`_displayed_cameras`）。兩台以上才成立，剩一台改為放大、
  零台回到全部；Esc、地點列、一般點擊、換地點、重新載入都會清除，並把側欄選取改回地點列（`clear_picks`）。
  多選時不允許拖曳排序。不存檔。
- 檢查：`uv run --group dev pytest -q` → 201 passed；腳本：windowsvista 樣式下深色對話框與側欄截圖；
  以真實滑鼠事件 Ctrl＋點 .1/.4 只剩兩格、加入／移除 .2、Esc 與地點列還原、還原後重新挑選，並截圖淺色側欄。

---

## 2026-10-21：AI 結果側欄可讀性（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin。** 使用者在現場（1N1，兩條連線 192.168.101.5/.6:1001）實際收到資料後回饋。
- 由舊到新往下排（`addItem`、超過 500 筆從頂端刪）；只有原本停在最底才自動捲到底，捲動延到下一個
  事件迴圈（換行後的列高要等下一次排版）。
- 每筆兩行：`攝影機 · 時間` / 內容。未命名攝影機只顯示主機（`short_camera_name`）；內容在逗號後插入
  零寬空格（`wrappable`）才能依寬度換行（緊湊 JSON 沒有空白可斷）。列表開 word wrap、關水平捲軸。
- 每台攝影機一個顏色（`CAMERA_COLOURS`，依站內順序），側欄圓點與畫格結果條左緣同色，篩選選單也有圓點。
- 連線狀態：側欄頂端每條連線前加綠／黃點（拿掉整段變黃的舊規則）；工具列按鈕改為 `● AI`，
  `feed` 屬性 connected／partial／down 決定圓點顏色，提示顯示已連線條數。
- 畫格下方依種類分行：`AiFeedConfig.tile_key`／`tile_values`（存在 `ai_feeds[]`），`AiEvent.group` 是 tile_key 欄位
  換成文字前的值，`tile_row()` 決定第幾行（None＝這種不上畫格，只進側欄）。畫格的結果改為 `_AiLine` 一行一個、
  各自閃燈。對話框新增「畫格下方顯示」（與攝影機對照並排），分類欄位選項來自訊息格式 JSON 的 `labels`
  （`label_fields`；JSON 打到一半無效時保留原選項），勾選順序＝`labels` 的順序。都不勾＝舊行為。
- 畫格結果條每收到一筆就以攝影機顏色亮起 1 秒（`AI_FLASH_MS`，計時器每筆重新計時）。使用者以遠端桌面觀看，
  所以是直接切換顏色、不做淡出（遠端桌面會丟掉淡出的中間影格，也較耗頻寬）。
- 檢查：`uv run --group dev pytest -q` → 201 passed（新增 `short_camera_name`、`wrappable`、分行 5 項測試）；腳本用本機
  假 AI 端送真實格式資料，確認順序、換行、顏色對應、自動捲到底、狀態圓點，並截圖。
  注意：腳本中以 `QTest.qWait` 等待時背景 socket 執行緒拿不到 GIL、看似連不上；改用 `processEvents`＋`sleep`。

---

## 2026-10-20：設定視窗暫存攝影機修改、淺色模式修正（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin。**
- 設定視窗：攝影機欄位的修改改為草稿（`WorkspaceEditor._drafts`，以原攝影機物件的 id 為鍵，移動攝影機時跟著走；
  刪除或被 inline 改名取代時捨棄）。切換選取時 `_stash_form` 暫存，清單以斜體標示；`儲存` 先以
  `changed_fields`（`ui/camera_form.py`）列出變更（名稱顯示新舊值，網址與帳密只列欄位名）再一次 commit；
  關閉時有草稿就問 儲存／捨棄／取消（`reject`）。地點與結構性操作仍立即存檔。
- 網址欄貼上 `rtsp://帳號:密碼@IP:Port/...`，離開欄位或按 Enter 時立刻把帳密移到帳號／密碼欄（貼上的帳密取代
  欄位舊值；存檔時 `Camera.from_raw`「欄位優先」的規則不變），網址欄下方加提示文字。不新增 IP／Port 欄位：
  各廠牌路徑格式不同，拆欄位等於回到已被使用者移除的「主機＋廠牌樣板」。
- 在攝影機欄位按 ↑／↓ 換上一台／下一台攝影機（`_step_camera`，跳過地點列、只走展開的列），游標留在同一欄；
  `QShortcut` 的 context 是表單（WidgetWithChildrenShortcut），左右鍵仍在欄位內移動。
- 修正既有問題：攝影機列任何資料變動（例如字型）都會發出 itemChanged 而被當成 inline 改名，未命名攝影機會被
  寫入網址當名稱。改為名稱等於顯示文字時不處理，標記草稿時也暫停訊號。
- 淺色模式：設定視窗清單選取列的文字原本沿用調色盤的白色反白文字，樣式表補上文字顏色。
- `qt.qpa.window: ... Unable to set light window border.`：切換外觀時 Qt 要 DWM 替每個原生視窗換邊框色，
  libvlc 需要的子視窗一律被拒（一格一行，實測一次 26 行），頂層標題列實際有變色。`__main__` 以
  `QLoggingCategory.setFilterRules("qt.qpa.window.warning=false")` 關掉這個類別的警告。
- 填滿按鈕改為自繪「四角向外」圖示（`_painted_icon`，與外觀按鈕共用灰色），Qt 內建標題列圖示是白色，
  淺色模式看不到。
- 檢查：`uv run --group dev pytest -q` → 194 passed（新增 `changed_fields` 測試）；`--dry-run` 正常；腳本驗證
  切換不遺失、斜體標示、確認文字、一次寫入、關閉時取消／捨棄、淺色無邊框警告，並截圖。

---

## 2026-10-20：外觀主題切換（分支 `feature/menu-bar`）

**狀態：已合併 main（`b7c1ca9`）並推上 origin。**
- 曾做出完整選單列（`QMenuBar`：檢視／設定／工具／說明），使用者看過後認為畫面會變矮，決定**不要選單列**，
  已整個移除、頂部列維持原樣。之後若重提，不要再用會吃掉一列高度的選單列。
- 保留外觀主題：頂部列語言下拉旁的 `◐` 按鈕（自繪半實心圓圖示，`◐` 字元在 Segoe UI 太小），點開選
  跟隨系統／深色／淺色。`Workspace.theme`（system／dark／light，未知值退回 system），
  `ui/theme.apply_theme` 用 `QStyleHints.setColorScheme()`，Windows 標題列一起變色；既有
  `colorSchemeChanged` 換樣式表，不重建、不重連。啟動時 `__main__` 在讀完設定後套用一次。
- 選單以主視窗為 parent（與右鍵選單同理，避免 native child 當 transient parent 的 Qt 警告）。
- 檢查：`uv run --group dev pytest -q` → 193 passed（新增 theme 存讀測試）；`uv run cctv-wall --dry-run`
  正常結束；腳本切換深淺色確認存檔、配色改變、播放器物件不變、切英文後選單文字與勾選正確、無 Qt 警告，
  並截圖深淺兩種外觀。

---

## 2026-10-20：設定視窗沒有地點時無法操作（分支 `fix/editor-add-site`）

**狀態：已實作、已驗證，已 commit 並合併回 `main`（未 push）。**
「新增地點」原本只在設定視窗樹狀圖的右鍵選單；沒有任何地點時右側表單全部停用，看起來什麼都不能點
（使用者打包後以空設定開啟時發現）。依使用者要求重排版面：拿掉 QSplitter，視窗邊緣與兩欄之間統一 16 px（`MARGIN`）；兩欄各有標題（地點列表／攝影機）讓上緣對齊；`新增地點` 只在沒有地點時出現在列表正中間（之後用列表空白處右鍵）；右下角 `新增`、`刪除`、`儲存`（間隔 8 px）；拿掉 `關閉`（已即時存檔，用標題列 ×）。腳本以空 `Workspace` 按下按鈕，
確認建立地點、表單啟用並截圖；`uv run --group dev pytest -q` → 192 passed。

---

## 2026-10-19：AI 辨識連線對話框改善（分支 `feature/ai-feed-dialog`）

**狀態：已實作、已驗證，依功能分批 commit 並合併回 `main`（未 push）。**

- 右鍵選單（側欄、影像格）改以主視窗為 parent：libvlc 讓側欄變成原生子視窗，選單掛在它下面時
  Qt 會印 `QWidgetWindow(... siteNavigationWindow) must be a top level window.`。已用腳本重現並確認消失。
- 側欄按鈕文字改為「AI 辨識連線」（無 …，新 key `ai_feeds_button`）；右鍵選單項目仍有 …（會開對話框）。
- 攝影機對照：試過「每台攝影機一列」，使用者的 Demo 地點攝影機多半沒有名稱而只列出一台，最後改回
  「AI 端識別值＋攝影機下拉選單」。真正原因是對應只認 `Camera.name`，未命名的
  攝影機進不了選單；現在 AI 對應一律用 `Camera.label`（未命名時是不含帳密的網址）：對照選單、
  `WallView.show_ai_event`、AI 側欄篩選、`Site` 的唯一性檢查都改用 label。「新增對照」預選尚未被任何連線
  使用的攝影機。資料格式不變（`cameras` 仍是識別值 → 顯示名稱）。
- 嚴格同步的綠畫面：GStreamer 從 GOP 中途開始解碼，關鍵影格前的 P-frame 沒有參考畫面而輸出綠色。
  `rtph264depay` 設 `wait-for-keyframe`、`request-keyframe`；`GStreamerSyncPlayer.state()` 在 sink 還沒有
  `last-sample`（第一張畫面）前回報 OPENING，畫格下方顯示「同步中 — 等待共同播放時間…」（level `sync`）。
  已用腳本確認提示顯示／消失與管線建立；**未用實際攝影機驗證綠畫面消失**。
- IP 與連接埠放同一行。
- 未做：依 `created` 時間自動建議顯示延遲（見對話中的說明：只能量到 AI 端延遲，影像延遲讀不到）。
- 關閉程式時偶發 `RuntimeError: Internal C++ object (VideoTile) already deleted`（`_release_detached` 執行緒）：
  `WallView.stop()` 把畫格設成無 parent 交給背景執行緒釋放，程式結束時 Qt 可能先刪掉它；`deleteLater()`
  遇到已刪除的物件改為略過。新增回歸測試 `TestReleaseDetached`（修正前失敗、修正後通過）。
- 檢查：`uv run --group dev pytest -q` → 192 passed；腳本操作對話框確認列出／存檔結果、截圖確認版面。

---

## 2026-10-19：介面改版與功能精簡（分支 `refactor/ui-redesign`）

**狀態：已實作、已驗證，依功能分批 commit 在 `refactor/ui-redesign`，已合併回 `main` 並 push，分支已刪除。**
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
2. `uv run --group dev pytest -q` → 應為 **220 passed**。
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
