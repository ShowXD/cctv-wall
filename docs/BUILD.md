# 打包與部署

## 標準打包指令

```powershell
uv sync
uv run build cctv-wall
```

此指令固定產生一個 EXE，並自動內含 VLC（打包電腦有安裝 VLC 時）、GStreamer
嚴格時間戳同步元件與啟動進度畫面。每次輸出至：
`dist/releases/CCTVWall-0.2.0-YYYYMMDD-HHMMSS/CCTVWall.exe`，不會覆寫舊版。
`uv run build` 也可使用，`cctv-wall` 是明確標示建置目標的寫法。

完整輸出範例：

```text
[cctv-wall] VLC bundling: 367 files from C:\Tools\VLC
[cctv-wall] output mode : onefile
[cctv-wall] GStreamer strict-sync bundling: 374 files
[cctv-wall] dropped 130 duplicate GStreamer files from the bundle root
[cctv-wall] release : CCTVWall-0.2.0-20260805-143012
[cctv-wall] mode    : onefile (VLC + strict timestamp sync included)
[cctv-wall] output  : ...\dist\releases\CCTVWall-0.2.0-20260805-143012
[cctv-wall] building…
[cctv-wall] complete: ...\CCTVWall.exe
```

**出貨前務必確認**第一行是 `VLC bundling: N files from …` 而不是 `DISABLED`
（`DISABLED` 代表這台打包機找不到 VLC，做出來的 exe 需要現場電腦自行安裝）。
CI 的 release workflow 會自動擋下這種情況。

### `--label`

只保留英數字（含中日韓文字）與 `-` `_` `.`，其餘一律換成 `-`，頭尾的 `.` `-` 會去掉：

| 輸入 | 產出的發行名稱 |
| --- | --- |
| `rc1` | `CCTVWall-0.2.0-rc1` |
| `client a` | `CCTVWall-0.2.0-client-a` |
| `客戶 A/B` | `CCTVWall-0.2.0-客戶-A-B` |
| `..--..` | **中止**：`the build label must contain a letter or number` |

```bash
uv run build cctv-wall --label client-a            # → dist/releases/CCTVWall-0.2.0-client-a/
uv run build cctv-wall --label client-a --replace  # 明確清掉該單一發行資料夾並重建
```

中間產物在 `build/releases/<發行名稱>/`，**可以安全整個刪掉**（只是快取，重建會變慢）。
`dist/releases/` 才是實際要出貨的東西。

### 打包失敗的訊息

| 訊息 | 結束碼 | 處理 |
| --- | --- | --- |
| `build aborted: … already exists` | 2 | 換 `--label`，或確定要重建時加 `--replace` |
| `build aborted: the build label must contain a letter or number` | 2 | `--label` 至少要有一個英數字 |
| `PyInstaller is not installed. Run: uv sync` | 2 | 先跑 `uv sync` |
| `build failed with exit code N` | N | PyInstaller 本身失敗，往上找它的錯誤訊息 |

`--replace` 會撞檔案鎖：若剛執行過該版 exe（或 Explorer 開著那個資料夾），
`shutil.rmtree()` 會失敗，訊息是 `close any running CCTVWall.exe`。照做即可。

---

## 自動打包（GitHub Actions）

`.github/workflows/release.yml`：

```bash
# 1. 更新 pyproject.toml 的 version
# 2. 打 tag
git tag v0.3.0
git push origin v0.3.0
```

workflow 會在 `windows-latest` 上：檢查 tag 與 `pyproject.toml` 版本一致 →
`choco install vlc` → `uv sync` → `uv run build cctv-wall` → 確認沒有
`VLC bundling: DISABLED` → 用打出來的 exe 跑 `--check` 確認 `strict sync : available`
→ 上傳 artifact → 建立含 exe 的 GitHub Release。

也可在 Actions 頁面手動觸發（`workflow_dispatch`），只產出 artifact、不建立 Release。

### 為什麼 Release 只有一個 exe，而不是 Win10 / Win11 各一個

**同一個 exe 同時支援 Windows 10 與 Windows 11，不需要分兩個檔案。**

會有這個疑問是因為兩者的解碼路徑不同，但**差異在執行期自動選擇，不在編譯期**：

| | Windows 11（開發機） | Windows 10（部署目標） |
| --- | --- | --- |
| 影像轉譯 | `d3d11videosink` + `d3d11h264dec`（硬體） | 該路徑失敗，退回 `avdec_h264`（軟體） |
| 需要的檔案 | D3D11 plugin | D3D11 plugin **＋** FFmpeg 支援 DLL |

現在的打包**兩套都放進去了**（就是那 +36 MB 的 plugin `bin/` 支援 DLL，見下方
Win10 相容性說明），GStreamer 在啟動時自己挑能用的那條。做兩個版本只會多一份
要維護的東西，而且「Win10 版」跟「Win11 版」的位元組內容會完全一樣。

真正需要分檔的情況只有兩種，目前都不成立：
架構不同（x64 / ARM64），或刻意做一個砍掉 FFmpeg DLL 的瘦身版
——後者等於讓 Win10 目標機沒有畫面，不要做。

> **CI 的綠燈不等於驗收通過。** runner 是 Windows Server，測不出 Win10 的
> 轉譯問題。每次出貨仍要在實際那台 Win10 上跑一次打包後的 exe。

---

## exe 體積與 GStreamer 去重

目前 **231,630,302 bytes（約 221 MiB）**。下表是加入 plugin `bin/` 支援 DLL
之前（186 MB 那版）的組成，比例仍可參考；那批支援 DLL 讓 exe 增加約 36 MB。

| 組成 | 未壓縮 | 說明 |
| --- | --- | --- |
| `gstreamer/` | 210 MB | 嚴格時間戳同步用，執行期唯一會被載入的那份 |
| `vlc/` | 136 MB | 一般播放後端 |
| `PySide6` | 73 MB | 其中 `opengl32sw.dll` 佔 20 MB（Qt 軟體 OpenGL 後援） |
| 其他 | 41 MB | Python 執行期、yt-dlp、OpenSSL |

`cctv_wall.spec` 有兩道刻意的去重，**改動前請先讀懂，否則體積會直接回胖 50 MB**。

### 一、`_is_unreachable_gstreamer_copy()`（Analysis 之後過濾）

`gstreamer-bundle` 的 `gstreamer_bundle.pth` 內容是
`import gstreamer_libs; gstreamer_libs.setup_python_environment()`。這行在**打包時**執行，
把各個 wheel 目錄加進 `sys.path`，於是 PyInstaller 的相依掃描器把它們當成一般套件，
在包根額外收集一份**所有 GStreamer DLL**（約 145 MB）。

執行期永遠不會用到那份：`gst_sync._prepare_frozen_runtime()` 把 `GI_TYPELIB_PATH`、
`GST_PLUGIN_SYSTEM_PATH_1_0` 與 `PATH` 全部指向 `gstreamer/` 子目錄，而包根的
`gstreamer_plugins_libs/bin/` 之類的位置不在任何搜尋路徑上。

**`excludes` 攔不住它們** —— `excludes` 只阻止「被 import 的模組」，這些是「被掃描器收集的
binary」，屬於不同機制。所以只能在 `Analysis()` 之後過濾 `analysis.binaries` 與
`analysis.datas`，砍掉目的地第一層以 `gstreamer_` 開頭的項目。

### 二、`SKIPPED_PLUGIN_PACKAGES`

複製各 wheel 的 plugin 時跳過兩個套件：

| 套件 | 為何跳過 |
| --- | --- |
| `gstreamer_libs` | 它的 plugin 已隨 `include_tree(runtime_root, …)` 進到 `gstreamer/runtime/lib/gstreamer-1.0/`，再複製一次到 `plugins/` 會有 156 個同名檔重複（約 79 MB） |
| `gstreamer_gtk` | GTK4 的 video sink。本專案是 Qt，走 `d3d11videosink`，用不到 |

### Windows 10 相容性：plugin `bin/` 的支援 DLL 不能砍

為了相容 Windows 10、較舊 GPU 與顯示卡驅動，plugin wheel 的 `bin/` 支援 DLL 也會放進
`gstreamer/runtime/bin`。這包含 `gstreamer_plugins_libs/bin` 的 `avcodec-61.dll` 等
FFmpeg DLL，因此 `gstlibav.dll` 的 `avdec_h264` 能作為 `d3d11h264dec` 的軟體解碼後援。

**直接原因（實際遇到的）**：部署目標是 Windows 10，該環境走
`d3d11videosink` / `d3d11h264dec` 這條路失敗。舊版沒複製這些支援 DLL，
`avdec_h264` 從來就是壞的，等於在那台機器上完全沒有可用的解碼器。

**代價**：exe 從 186 MB 變成 220.9 MiB（約 +36 MB）。這是刻意的取捨，
**要瘦身時第一個會被盯上的就是這裡——砍掉等於讓 Win10 目標機再次沒有畫面。**
除非確定所有目標機都是 Win11 且 `d3d11h264dec` 正常，否則不要動。

### 驗證

改完 spec 後**務必**用打包出來的 exe 跑一次 `CCTVWall.exe --check`。該指令會實際建構
同步工廠並驗證 6 個管線元件（`rtspsrc`／`rtph264depay`／`h264parse`／`decodebin`／
`videoconvert`／`d3d11videosink`），以及至少一個 H.264 decoder
（`d3d11h264dec` 或 `avdec_h264`）；輸出 `strict sync : available` 才算過關。

### 還可以再瘦身的地方（刻意沒動）

| 項目 | 未壓縮 | 顧慮 |
| --- | --- | --- |
| plugin `bin/` 支援 DLL | ~36 MB | **不能砍**，見上方 Win10 相容性 |
| `opengl32sw.dll` | 20 MB | Qt 軟體 OpenGL 後援。純 Widgets 理論上不需要，但本專案主打低階電腦，顯卡驅動不全時可能真的會退回它——要實機測 |
| `gstreamer_plugins_gpl_restricted` | 23 MB | 含 x264/x265（編碼器，播放用不到）。另有散布 GPL 的授權問題值得確認 |
| yt-dlp extractors | ~7 MB | 2098 個檔只需要 youtube + generic；省得不多但會拖慢 onefile 解壓 |
| **只留 GStreamer、砍掉 VLC** | **136 MB** | 架構級重寫：`player.py` 整支、`performance.py` 三種效能檔（全是 libvlc 選項）、`resolvers.py` 的 YouTube 串接都要改 |

---

## spec 檔做了什麼

| 決定 | 原因 |
| --- | --- |
| 把 `libvlc.dll`、`libvlccore.dll`、整個 `plugins/`（367 個檔）放進 `vlc/` 子目錄 | 現場電腦不必安裝 VLC；目錄名稱必須與 `vlc_runtime.BUNDLE_SUBDIRECTORY` 一致 |
| **不**打包 `plugins.dat` | 那是 VLC 的外掛快取，記錄打包機的絕對路徑與時間戳。帶著它會讓 libvlc 對每個外掛噴 `stale plugins cache` 錯誤然後照樣重掃；不帶它則自己重建一次即可 |
| plugins 放在 `binaries` 而非 `datas` | PyInstaller 會順帶處理 DLL 的相依性，當成 data 複製則不會 |
| `upx=False` | UPX 壓縮會破壞部分 VLC 外掛 DLL |
| `console=False` | GUI 程式，不要黑窗 |
| `collect_all("yt_dlp")` | yt-dlp 的 extractor 是延遲匯入，不收集會在執行時找不到 |
| `excludes=[numpy, matplotlib, PIL, ...]` | 本程式不用這些，排除可縮小體積 |

### 內含 VLC 的搜尋順序

`CCTV_WALL_VLC_DIR` → python-vlc 找到的位置（它會查登錄檔與 PATH）
→ `C:\Program Files\VideoLAN\VLC` → `C:\Program Files (x86)\VideoLAN\VLC`。

全部找不到時打包**不會失敗**，只會印出 `VLC bundling: DISABLED`。

### 打包後的執行期行為

- `src/cctv_wall/vlc_runtime.py` 在 `import vlc` **之前**把 `PYTHON_VLC_LIB_PATH`、
  `PYTHON_VLC_MODULE_PATH`、`VLC_PLUGIN_PATH` 指向包內的 `vlc/`，並用
  `os.add_dll_directory()` 讓載入器找得到 `libvlccore.dll`。沒打包時這支程式什麼都不做。
- **GStreamer 走 `PATH`，不是 `add_dll_directory()`**：`gst_sync._prepare_frozen_runtime()`
  裡把 `runtime/bin` 前置到 `os.environ["PATH"]` 的那一行**不能刪**。typelib 宣告的 DLL 由
  GLib 的 `g_module_open()` 載入，走 Win32 `LoadLibrary`，**不帶**
  `LOAD_LIBRARY_SEARCH_USER_DIRS`，因此完全看不到 `add_dll_directory()` 註冊的目錄。
  刪掉的症狀非常誤導：`gi` 匯入成功、`Gst` 變成空殼、以 `TypeError: must be an interface`
  收場，同步按鈕彈警告後自己彈回，畫面繼續用 VLC 播——「有影像但不同步」。
  `tests/test_sync.py` 有一項專門鎖住這個 `PATH` 行為。
- `workspace.json` 存在 **exe 旁邊**，不是包內。PyInstaller 的解壓目錄結束時會被刪掉，
  所以設定檔絕不能用 `__file__` 定位（`repository.default_config_path()` 有對應處理與測試）。
- 打包後的 `--check` 若是被雙擊執行（沒有 console），報告會用對話框顯示；
  從命令列執行則印到 stdout。
- 單檔版每次啟動會先解壓程式元件，完成後顯示單一分段進度條。這是可攜性與啟動時間的取捨。

---

## 部署到現場電腦

1. 把 `CCTVWall.exe` 複製到現場電腦（例如 `C:\CCTVWall\`）。
2. 先跑一次診斷：命令列 `CCTVWall.exe --check`，或直接雙擊後看對話框。
   `libvlc` 那行要有版本號才算過關。
3. 把設定檔 `workspace.json` 放到 `CCTVWall.exe` 旁邊
   （可從 [`workspace.example.json`](../workspace.example.json) 複製修改，
   或直接開程式用左下角的「管理設定」建立）。
4. 要放到別的路徑：設環境變數 `CCTV_WALL_CONFIG=D:\config\workspace.json`。
5. 要開機自動啟動：把 `CCTVWall.exe` 的捷徑丟進
   `shell:startup`（`Win+R` 輸入這串即可開啟該資料夾）。

多個地點共用一份設定時，把同一個 `workspace.json` 複製到各台即可 —— 每台記住的
`last_site` 會各自被覆寫成該台實際在看的地點。

> `workspace.json` 含**明碼密碼**，別放共用磁碟、別進版控。見 [SECURITY.md](../SECURITY.md)。

### 換機器 / 搬移專案後要確認的事

1. `uv sync` 重建環境（`.venv` 不要跟著搬）。
2. `uv run --group dev pytest -q` → 應為 **154 passed**。
   `tests/test_persistence.py` 有一項會檢查專案根目錄存在 `pyproject.toml`。
3. `uv run cctv-wall --check` → `libvlc` 要有版本號、`strict sync` 要 available。
   原機 VLC 在 `C:\Tools\VLC`；換機器要確認 `find_vlc_dir()` 找得到，或用 `--vlc-dir` 指定。
   **64-bit Python 必須配 64-bit VLC。**
4. 重新打包一次，看 stderr 的三行 `[cctv-wall]` 訊息（VLC 檔數、GStreamer 檔數、
   丟掉的重複檔數）。體積若明顯偏離 220 MiB，先查上面的兩道去重。
5. **實際部署目標是 Windows 10，該機影像轉譯不正常**。驗收一定要在那台 Win10 上
   跑打包後的 exe，開發機（Win11）跑得動不代表過關。
