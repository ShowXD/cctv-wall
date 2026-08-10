# 交接概要（給後續 session 直接銜接）

> 這份文件記錄**程式碼看不出來的決策與陷阱**。
> 功能說明、操作方式、打包指令請看 [`../README.md`](../README.md) 與 `docs/` 底下的
> [USAGE](USAGE.md) / [BUILD](BUILD.md) / [ARCHITECTURE](ARCHITECTURE.md) /
> [TROUBLESHOOTING](TROUBLESHOOTING.md)。
> 最後更新：2026-08-06 17:30

---

## 一句話

多地點 Qt 影像牆：RTSP 監視器 / 本機影片 / YouTube 混播，主打低階電腦，
可打包成單一 exe。兩套播放後端：VLC（一般）與 GStreamer（嚴格時間戳同步）。

## 環境與常用指令

```bash
uv sync                        # 開發環境
uv run --group dev pytest -q   # 154 passed（不需要 VLC、不連網）
uv run cctv-wall               # 啟動 GUI
uv run cctv-wall --check       # 環境診斷（含 strict sync 探測）
uv run cctv-wall --dry-run     # 用假後端建完整 GUI 後立刻結束
uv run build cctv-wall         # 打包（一律 onefile）
```

**注意**：`.venv` 曾出現沒有 pytest 的狀況，測試請用 `uv run --group dev pytest`。

## 目前狀態（皆為實測，非估計）

| 項目 | 值 |
| --- | --- |
| 測試 | **154 passed** |
| exe | **231,630,302 bytes（220.9 MiB）** |
| 最新建置 | `dist/releases/CCTVWall-0.2.0-20260806-171645/`，2026-08-06 17:19 |
| `--check` | 開發環境回報 `strict sync : available` |

**exe 比先前記錄的 186 MB 大了約 36 MB，這是刻意的**——見陷阱 3。

---

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

側欄（`ui/navigation.py`）的地點右鍵選單**沒有**加排序，只有設定視窗有。
刻意不做兩套，避免功能重複。

### 3. 註解繁體中文化（**只完成約 20%**）

實測目前覆蓋率：

| 類型 | 繁中 | 英文 |
| --- | --- | --- |
| `#` 註解 | 8 行 | **85 行** |
| docstring | 31 個 | **138 個** |

**已完成的檔案**：`layout.py`、`quality.py`、`vendors.py`、`vlc_runtime.py`、
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

### 7. 效能檔對嚴格同步無效

`build(profile, strict_sync=True)` 會忽略 `profile`——那些是 libvlc 專屬選項。
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

其餘分層仍乾淨：領域層（`models`/`urls`/`vendors`/`quality`/`layout`）不依賴 Qt 或 VLC，
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
| yt-dlp extractors | ~7 MB | 2098 個檔只需要 youtube + generic；省得不多但會拖慢 onefile 解壓 |
| **只留 GStreamer、砍掉 VLC** | **136 MB** | 架構級重寫：`player.py` 整支、`performance.py` 三種效能檔（全是 libvlc 選項）、`resolvers.py` 的 YouTube 串接都要改。GStreamer 功能上是 VLC 的超集，但工程量與回歸風險都大 |

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
2. `uv run --group dev pytest -q` → 應為 **154 passed**。
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
