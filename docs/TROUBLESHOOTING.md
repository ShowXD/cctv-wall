# 疑難排解

**任何症狀的第一步**：按控制列的 `☷` 看事件紀錄，或直接開 `CCTVWall.exe` 旁邊的
`cctv-wall.log`（與 `workspace.json` 同一個資料夾）。每格的失敗原因都會寫在裡面。

第二步：跑 `CCTVWall.exe --check`（打包後）或 `uv run cctv-wall --check`（開發環境）。

---

## 症狀對照表

| 症狀 | 原因與處理 |
| --- | --- |
| 啟動就說 `libvlc is unavailable` | VLC 沒裝或位元數不符。跑 `--check` 看細節；64-bit Python 要 64-bit VLC |
| 打包後的 exe 開不起來 | 命令列跑 `CCTVWall.exe --check` 看報告 |
| 全部格子都紅字 `Connection failed` | 網路或帳密。先用 VLC 本體開同一條 RTSP 網址驗證 |
| 單一攝影機紅字 | 該機型路徑不同。改 `Vendor` 或用 `custom` 填樣板 |
| 畫面卡頓、CPU 100% | 效能檔調 `low_end`、攝影機改 stream 2/3、減少每頁格數 |
| 大量 `stale plugins cache` 錯誤 | spec 被改成有打包 `plugins.dat`。移除即可 |
| YouTube 紅字 `yt-dlp failed` | 影片私人／地區限制／yt-dlp 過期。`uv sync --upgrade-package yt-dlp` |
| 斷線後畫面一直沒回來 | 已會自動重連（最長每 30 秒一次）。想立刻重試就按控制列的 `↻` |
| 某格只有滑過提示說「未收到影像」 | 攝影機接受連線但沒送資料。多半是串流路徑或帳密錯，右鍵換 Stream 或改 Vendor |
| 設定改了但沒生效 | 效能檔需重開程式；其他設定按 `儲存並重新載入` 後才會寫入並套用 |
| `Could not save settings` | exe 所在資料夾沒有寫入權限。用 `CCTV_WALL_CONFIG` 指到可寫的路徑 |
| 同步按鈕按下去彈警告後自己彈回 | GStreamer 沒載入成功。跑 `--check` 看 `strict sync` 那行；打包相關原因見 [BUILD.md](BUILD.md) |
| Windows 10 上完全沒有畫面 | plugin `bin/` 的 FFmpeg 支援 DLL 沒進 exe。見 [BUILD.md](BUILD.md) 的 Win10 相容性 |

`--check` 輸出範例（開發環境）：

```text
config file : C:\Saves\Local\cctv_gui\workspace.json
bundled VLC : no (using the VLC installed on this PC)
libvlc      : 3.0.23 Vetinari
library     : C:\Tools\VLC
yt-dlp      : 2026.07.04
strict sync : available
```

---

## 嚴格時間戳同步（RTCP / NTP）

一般影像牆沿用 VLC，兼顧最低硬體需求。若同一地點所有 RTSP 攝影機在
`☷` →「時間戳同步」→「檢查目前地點」中都顯示可用，才可按「啟用嚴格時間戳同步」。

此模式以 GStreamer 的 `rtspsrc` 將 RTCP Sender Report 對應到 NTP 時鐘，再讓所有格子使用
共同播放時鐘；慢啟動的攝影機會追上目前時間，不會以較舊畫面填滿格子。

需要 **GStreamer 1.x Windows runtime、RTSP/RTP、H.264 與 D3D11 插件**。
標準打包指令會一併納入這些元件與 Python GI bindings；目標電腦不必另外安裝 GStreamer。
若某台攝影機未提供可用的 RTCP Sender Report，程式會顯示原因並維持 VLC 一般播放。

開發環境的安裝方式就是 `uv sync`——它會裝上打包所需的官方 `gstreamer-bundle`。

**注意**：開啟嚴格同步後效能檔失效，只剩「每頁格數」有作用。
見 [ARCHITECTURE.md](ARCHITECTURE.md)。
