## Why

同一條產品線裡，不同種類的 Merge Request 該用不同的方式分析 —— 一筆修 bug 的 MR 與一筆
新增測試案例的 MR，要問 AI 的問題不一樣，報告該長什麼樣也不一樣。目前 device 機制只能
讓「每條產品線」有自己的邏輯，同一個 device 底下所有 MR 一律走同一支 `summary.py` 與
`merge_to_md.py`。

而「這筆 MR 是什麼種類」這件事，各產品線的判斷方式本來就不同：SSD 看標題的第二個方括號、
SD 看第三個。判斷規則與種類的字彙都是各自演化的，沒有共識，也不需要有。

## What Changes

- device 新增第四個鉤子 `mr_type.py`，由**步驟 2（取得相關資訊）**執行，與 `jira_key.py`
  共用同一次 GitLab 取得。**不新增流程步驟**，五步維持不變。
- device 目錄底下可放**種類子目錄**（`bug/`、`newtestcase/`），內含該種類專屬的
  `summary.py` 與 `merge_to_md.py`。認得哪些種類由掃目錄決定，各 device 自己的字彙，
  不需協調。
- `summary` 與 `merge_to_md` 兩個鉤子的解析改為三段：
  `<device>/<type>/` → `<device>/` → `default/`。`jira_key` 與 `mr_type` 兩個鉤子
  **不因種類而異**，維持現有的兩段解析。
- device 可在 `__init__.py` 宣告 `STRICT_TYPE`，決定抽不到或認不得種類時要回退還是失敗。
  未宣告視為回退。
- 種類隨分析結果傳遞：步驟 2 產出 → 步驟 3 蓋章進 `03_summary.json` → 步驟 5 自該檔讀取。
  **分析結構的版本自 3 提升為 4**（新增 `mr_type` 欄位）。
- 報告末尾的出處資訊新增種類。
- device 範本的 `__init__.py` 以註解列出所有可用的宣告，使人不必翻文件就知道名稱。

不做（本輪明確排除）：

- **不加寬交給鉤子的 MR 欄位。** 目前只看標題就夠，未來需要 label 等欄位時再議。
- **不加全域強制種類的環境變數。** `STRICT_TYPE` 是各產品線的紀律，一個機制比兩個好。
- **不做跨 device 的種類回退。** 兩套字彙撞名時會安靜地跑錯邏輯，見 design。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `ai-analysis-gitlab-mr`: device 的鉤子集合、解析順序與回退規則改變；分析結構新增
  `mr_type` 欄位並提升版本；步驟 2 的產出新增種類；報告出處新增種類；新增種類解析
  失敗的處理與 `STRICT_TYPE` 的語意。

## Impact

**腳本**

- `scripts/ai_analysis_gitlab_mr/device/__init__.py` —— `HOOK_NAMES` 增為四個，
  解析加入種類這一層，新增種類的發現與名稱檢查、`STRICT_TYPE` 的讀取
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_info.py` —— 執行 `mr_type` 鉤子，
  嚴格模式的檢查在此進行（在任何 AI 花費之前）
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py` —— 收下並蓋章 `mr_type`
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_merge_to_md.py` —— 自分析結構讀取
  `mr_type` 以解析鉤子
- `scripts/ai_analysis_gitlab_mr/__init__.py` —— 結構版本、`mr_type` 的驗證、出處
- `scripts/ai_analysis_gitlab_mr/device/default/` —— 新增 `mr_type.py`
- `scripts/ai_analysis_gitlab_mr/device/_template/` —— 新增 `mr_type.py`、種類子目錄的
  範本、`__init__.py` 的註解式宣告清單

**Qt**

- `AIAnalysisGitLabMR.cpp` —— 一行：把步驟 2 產出的 `mr_type` 轉送給步驟 3。
  **需要重新建置。**

**文件**

- `README.md` —— 種類機制、目錄長相、解析鏈、`STRICT_TYPE`、`03_summary.json` 的新欄位

**相容性**

- 既有的 device 不受影響：沒有種類子目錄時解析鏈的第一段直接跳過，行為與現在完全相同。
- 既有的 `03_summary.json`（版本 3，沒有 `mr_type`）仍可被步驟 5 讀取，視為沒有種類。
