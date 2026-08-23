# 安全性政策

## 回報漏洞

請勿開 public issue。請透過 GitHub 的
[Private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
回報，或直接聯絡維護者。

## 這個專案的機密資料在哪裡

| 檔案 | 內容 | 狀態 |
| --- | --- | --- |
| `workspace.json` | 攝影機 IP、RTSP 帳號、密碼（DPAPI 加密） | 已列入 `.gitignore`，**永遠不要提交** |
| `workspace.example.json` | 同樣結構，值都是佔位字串 | 可安全提交 |
| `cctv-wall.log` | 事件紀錄，可能含主機位址 | 已列入 `.gitignore` |

## 密碼如何存放

存檔時 `password` 欄位以 Windows DPAPI 加密，寫成 `"password": "dpapi:…"`。
金鑰綁定當前 Windows 使用者帳號，設定檔被複製到別台電腦或別的帳號都解不開
（解不開時該欄位讀成空字串，程式照常啟動）。其餘欄位仍是明文，設定檔可以手改。

手寫的明文密碼照樣讀得進來，下次存檔時自動加密。加密只在 Windows 生效，
其他平台原樣存放明文。加解密集中在 `src/cctv_wall/credentials.py`，
唯一呼叫點是 `src/cctv_wall/repository.py`。

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
