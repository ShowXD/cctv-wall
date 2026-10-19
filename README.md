<div align="center">

# CCTV Wall

**多地點、多路影像的 Qt 桌面影像牆 — RTSP 監視器與本機影片混在同一面牆上播放。**

專為**低階電腦**設計，可打包成單一 exe，現場電腦不必安裝任何東西。

[![CI](https://github.com/ShowXD/cctv-wall/actions/workflows/ci.yml/badge.svg)](https://github.com/ShowXD/cctv-wall/actions/workflows/ci.yml)
[![Release](https://github.com/ShowXD/cctv-wall/actions/workflows/release.yml/badge.svg)](https://github.com/ShowXD/cctv-wall/actions/workflows/release.yml)
[![Latest release](https://img.shields.io/github/v/release/ShowXD/cctv-wall?include_prereleases)](https://github.com/ShowXD/cctv-wall/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6.svg)](#安裝)

[安裝](#安裝) · [功能](#功能) · [文件](#文件) · [貢獻](CONTRIBUTING.md) · [安全性](SECURITY.md)

</div>

---

## 功能

- **多地點管理** — 一個地點多支攝影機，切換地點只連該地點，其餘連線不建立、不解碼
- **混合來源** — RTSP 監視器、本機 MP4/MKV/AVI/MOV/TS；攝影機只需填名稱、網址、帳號、密碼
- **兩套播放後端** — VLC（一般播放，硬體需求最低）與 GStreamer（RTCP/NTP 嚴格時間戳同步）
- **斷線自動重連** — 掉線的那一格自己退避重試（5→10→20→30 秒），不必人工按 `↻`
- **每頁格數自訂** — 頂部列直接輸入每頁格數（預設 4，最多 36），自動排成接近正方形，開啟時視窗會調成每格剛好 16:9；影像一律靜音、GPU 解碼，為低階電腦調校
- **可收合側欄與快捷鍵** — 側欄可拖曳調寬、`Ctrl+B` 隱藏；`PgUp`/`PgDn` 翻頁、`Ctrl+PgUp`/`Ctrl+PgDn` 切換地點、`F5` 重連、`F11` 全螢幕
- **設定立即存檔** — 設定視窗的每個動作當下寫入，關閉時影像牆重新載入一次
- **全狀態記憶** — 地點、攝影機、帳密、每頁格數、側欄寬度與顯示狀態、視窗大小、介面語言自動存回 `workspace.json`，密碼以 Windows DPAPI 加密；舊版設定（效能檔、廠牌樣板）載入時自動轉換
- **失敗隔離** — 單格失敗只顯示紅字，不影響其他畫面
- **雙語介面** — 繁體中文／English 即時切換
- **內建事件紀錄** — 不必開終端機就能查看失敗原因
- **AI 結果對照** — 地點可設定多條 TCP 來源（每行一筆 JSON，一條可帶多台攝影機），結果延遲對齊後顯示在畫格下方與側欄
- **單一 exe** — 內含 VLC 與 GStreamer，現場電腦零安裝

192 個測試，不需要 VLC、不連網。

---

## 安裝

### 一般使用者（現場電腦）

到 [Releases](https://github.com/ShowXD/cctv-wall/releases/latest) 下載 `CCTVWall-*.exe`。

**同一個 exe 同時支援 Windows 10 與 Windows 11**，不需要挑版本 —— 硬體／軟體解碼路徑
在執行期自動選擇，兩套元件都已內含。

```powershell
CCTVWall.exe --check    # 先跑診斷，libvlc 那行要有版本號
```

接著把 `workspace.json` 放到 exe 旁邊（從
[`workspace.example.json`](workspace.example.json) 複製修改），或直接開程式用
左下角的「地點與攝影機」建立。詳見 [部署說明](docs/BUILD.md)。

### 開發者

前置條件：**VLC 桌面版**，位元數需與 Python 一致（64-bit Python → 64-bit VLC）。

```bash
git clone https://github.com/ShowXD/cctv-wall.git
cd cctv-wall
uv sync                                    # 建立 .venv，安裝 Qt、python-vlc、GStreamer
cp workspace.example.json workspace.json   # 填入你自己的攝影機
uv run cctv-wall                           # 啟動
```

| 指令 | 用途 |
| --- | --- |
| `uv run cctv-wall` | 啟動 GUI |
| `uv run cctv-wall --check` | 環境診斷：設定檔位置、libvlc 版本、嚴格同步可用性 |
| `uv run cctv-wall --dry-run` | 用假的播放後端建整個 GUI 後立刻結束（不需要 VLC） |
| `uv run --group dev pytest -q` | 執行 192 個測試 |
| `uv run build cctv-wall` | 打包成單一 exe |

---

## 打包與自動發行

```powershell
uv run build cctv-wall
# → dist/releases/CCTVWall-<版本>-YYYYMMDD-HHMMSS/CCTVWall.exe
#   版本取自 pyproject.toml（目前 0.4.0）
```

推 tag 就會自動打包並建立 GitHub Release：

```bash
# 先更新 pyproject.toml 的 version，再打 tag
git tag v0.4.0 && git push origin v0.4.0
```

GitHub Actions 會在 Windows runner 上安裝 VLC、打包、用產出的 exe 跑 `--check`
自我診斷（`strict sync : available` 才算過關），然後上傳到 Release。
完整說明見 [docs/BUILD.md](docs/BUILD.md)。

---

## 文件

| 文件 | 內容 |
| --- | --- |
| [docs/USAGE.md](docs/USAGE.md) | 主畫面操作、快捷鍵、設定視窗、AI 結果對照、`workspace.json` 欄位 |
| [docs/BUILD.md](docs/BUILD.md) | 打包指令、exe 體積與 GStreamer 去重、Win10 相容性、部署到現場電腦 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 模組分層、效能設計、已知技術債 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 症狀對照表、嚴格時間戳同步 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 交接文件：程式碼看不出來的決策與踩過的陷阱 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 開發流程、守門測試、架構規則、發行步驟 |
| [SECURITY.md](SECURITY.md) | 機密資料位置、提交前檢查、外洩處理 |

---

## ⚠️ 安全性

`workspace.json` 含攝影機 IP 與 RTSP 帳號（密碼已用 DPAPI 加密），已列入 `.gitignore`，**永遠不要提交**。
CI 每次 push 都會檢查它有沒有被誤加進版控。詳見 [SECURITY.md](SECURITY.md)。

---

## 技術棧

| | |
| --- | --- |
| GUI | PySide6 / Qt Widgets |
| 播放 | libvlc（python-vlc）、GStreamer 1.x（PyGObject） |
| 環境 | uv |
| 打包 | PyInstaller（onefile） |

依賴方向單向朝內：領域層（`models` / `urls` / `vendors` / `layout`）
不 import Qt 或 VLC，`repository.py` 是唯一碰硬碟的檔案，`player.py` 是唯一
`import vlc` 的檔案。所以換掉任何一層都只動一個檔案。

---

## 刻意不做的事

錄影、PTZ 控制、移動偵測、ONVIF 自動搜尋攝影機、每個地點各自記住頁碼、
多螢幕佈局、程式內更新。

---

## 授權

[MIT](LICENSE) © 薛佾展

<!-- CI test -->