# 貢獻指南

## 開始之前

```bash
uv sync                                 # 建立環境
uv run --group dev pytest -q            # 應為 222 passed（不需要 VLC、不連網）
uv run cctv-wall --dry-run              # 用假後端建整個 GUI 後立刻結束
```

`.venv` 曾出現沒有 pytest 的狀況，測試請一律加 `--group dev`。

## 送 PR 之前

- [ ] `uv run --group dev pytest -q` 全綠
- [ ] `git status` 沒有 `workspace.json`（含攝影機網址與帳號，見 [SECURITY.md](SECURITY.md)）
- [ ] 改了行為就順手更新 README／`docs/`

README 與程式碼不同步已經發生過兩次。最容易過期的是：**測試數量、exe 體積、
疑難排解表、「刻意不做的事」清單**。

## 兩個守門測試會擋你

| 測試 | 規則 |
| --- | --- |
| `tests/test_i18n.py` | 掃描 `src/` 所有 `t("字面值")` 並比對翻譯目錄。新增文字**兩種語言都要加**；刪功能要刪對應的鍵；動態組出的鍵加進 `DYNAMIC_KEYS` 白名單。迴圈裡請寫 `self._translator.t("move_up")` 而非 `t(key)`，否則會被判成死鍵 |
| `tests/test_sync.py` | 比對 `REQUIRED_ELEMENTS` 與 `play()` 實際建構的 GStreamer 元件。改管線要同步兩邊 |

## 架構規則

依賴方向單向朝內，**不要打破**：

- 領域層（`models` / `urls` / `vendors` / `layout`）不 import Qt 或 VLC
- `repository.py` 是唯一碰硬碟的檔案
- `player.py` 是唯一 `import vlc` 的檔案
- 不可變模型在建構時就完成驗證

## 改動 `cctv_wall.spec` 之前

先讀 [docs/BUILD.md](docs/BUILD.md) 的「exe 體積與 GStreamer 去重」。
那兩道去重拿掉，exe 會直接胖 50 MB；plugin `bin/` 的支援 DLL 砍掉，
Windows 10 目標機會完全沒有畫面。

## Commit 格式

```
<type>: <description>
```

type：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci`

## 發行

1. 更新 `pyproject.toml` 的 `version`
2. `git tag v0.3.0 && git push origin v0.3.0`
3. GitHub Actions 會打包、自我診斷（`--check` 要回報 `strict sync : available`）
   並建立含 exe 的 Release

**驗收一定要在實際部署的 Windows 10 機器上跑打包後的 exe**，開發機（Win11）
跑得動不代表過關——見 [docs/BUILD.md](docs/BUILD.md) 的 Win10 相容性說明。
