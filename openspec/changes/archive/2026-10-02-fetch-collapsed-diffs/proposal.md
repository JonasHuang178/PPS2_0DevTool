# Proposal

## Why

送進 prompt 的差異只有幾行檔名，沒有任何一段程式碼：

```
diff --git a/src/a.cpp b/src/a.cpp
diff --git a/src/b.cpp b/src/b.cpp
```

而同一支 Merge Request 在 GitLab 網頁上看得到完整的變更。

成因是 GitLab 的 diff 大小限制比直覺低得多：**單一 patch 到門檻的 10%（預設 200 KB 的 10%，
約 20 KB）就會被「收合」**，收合的檔案在 API 回來的 `diff` 欄位是**空字串**。網頁看得到是
因為它點開才另外載入。

本工具走的 `/diffs` 端點**沒有任何參數可以繞過它** —— 它只吃 `page`、`per_page`、`unidiff`。
能繞過的是舊的 `/changes` 加上 `access_raw_diffs=true`（直接向 Gitaly 取，不受資料庫端的
大小限制）。本工具兩者都沒有用上。

而且這件事**完全沒有被擋下來**：組出來的差異照樣送進 AI，模型對著幾行檔名給出一份自信的
分析，每一步都回報成功 —— 使用者拿到一份看起來正常、實際上沒看過任何程式碼的報告，還付了錢。

查證過程中另外發現一顆地雷：**`/diffs` 的 `per_page` 大於 30 時，多個 GitLab 版本直接回
500**（gitlab-org/gitlab#427168、#428187），而本工具送的是 100。退回 `/changes` 只在 404 時
發生，所以那個 500 會變成一個指不出原因的「GitLab 查詢失敗」。

## What Changes

- **修改「AI 分析的素材備置」需求**：取得差異時 SHALL 在內容被來源收合時改以不受其大小限制
  的方式重取；重取後仍然一行內容都沒有時 SHALL 失敗，MUST NOT 送進 AI。
- `/diffs` 的每頁筆數由 100 降為 30。
- 把來源給的 `overflow` / `collapsed` / `too_large` 三個旗標讀出來並記入診斷。

不做：

- **不改成一律走 `/changes`。** 它已被標記為 deprecated（API v5 移除），而且較慢、較耗資源。
  只在真的出現空內容時才走那一條。
- **不自行調整伺服器端的大小限制。** 那是管理者的設定，工具只負責把成因說清楚。
- **不改既有的涵蓋範圍結構。** 它本來就會把這些檔案算進「差異內容是空的」那一類。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「AI 分析的素材備置」加上收合時的重取與無內容時的失敗。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**腳本**

- `scripts/script_utils/gitlab_utils.py` —— 每頁筆數、重取、三個旗標
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py` —— 無內容時失敗

**Qt**

- 無。

**相容性**

- 正常的 Merge Request 行為完全不變（沒有空內容就不會多打任何一次 API）。
- 先前會「安靜地分析空差異」的那些，現在會明確失敗 —— 那是這次要的。
