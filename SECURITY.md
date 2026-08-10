# 安全性政策

## 回報漏洞

請勿開 public issue。請透過 GitHub 的
[Private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
回報，或直接聯絡維護者。

## 這個專案的機密資料在哪裡

| 檔案 | 內容 | 狀態 |
| --- | --- | --- |
| `workspace.json` | 攝影機 IP、RTSP 帳號、**明碼密碼** | 已列入 `.gitignore`，**永遠不要提交** |
| `workspace.example.json` | 同樣結構，值都是佔位字串 | 可安全提交 |
| `cctv-wall.log` | 事件紀錄，可能含主機位址 | 已列入 `.gitignore` |

密碼以明碼存放是目前的刻意取捨（現場單機部署、無伺服器）。
若你的環境需要更高安全等級，只需改 `src/cctv_wall/repository.py`
——它是唯一讀寫設定檔的模組，可改為讀環境變數或 Windows 認證管理員。

## 提交前的自我檢查

```bash
git ls-files | grep -x workspace.json   # 應該沒有輸出
git status --short                      # workspace.json 不該出現
```

CI（`.github/workflows/ci.yml`）也會在每次 push 檢查：

1. `workspace.json` 是否被納入版控 → 是就讓 build 失敗
2. gitleaks 全歷史掃描 → 找出誤入的金鑰、token、密碼

## 若密碼已經被推上去

改密碼比清歷史重要。順序是：

1. **立刻更換所有被暴露的 RTSP 帳號密碼**（推上去的那一刻就算外洩）
2. 用 [`git filter-repo`](https://github.com/newren/git-filter-repo) 或
   [BFG](https://rtyley.github.io/bfg-repo-cleaner/) 清掉歷史中的檔案
3. force push，並請所有協作者重新 clone
