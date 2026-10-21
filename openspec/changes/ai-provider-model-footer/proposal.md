# 出處的 AI 那一行改為 Provider / Model，兩者都取自 AI 服務本身

## Why

報告末尾出處的 AI 那一行目前印的是 `Open AI | gpt-4o`，兩個值都來自設定檔：左邊是使用者
替那一組設定取的名字（`Name`），右邊是使用者自己填的模型名（`Model`）。兩個問題：

1. **沒有標示**。讀報告的人看不出左邊是什麼、右邊是什麼。
2. **模型名不可信**。依現行規格，送出的請求裡沒有模型欄位，模型由服務端依識別碼
   （shareCode）決定 —— 設定檔的 `Model` 只是使用者寫下的「應該是」，與實際跑的那一個可以
   不一致，而報告照樣印出它。

AI 服務另外提供一個「列出模型」的端點，回傳每一個識別碼對應的模型名稱。改為向服務查詢，
報告印的就是服務自己說的模型；左邊則改為明確的 provider。

## What Changes

- **BREAKING** 設定檔：`Service.AI_Mode_List` 改名為 `Service.AI_Provider_List`；每一項的 `Name`
  改名為 `Provider`；`Model` 移除。
  不相容舊版設定檔（工具尚未發布）。
- **BREAKING** AI 分析那一步（步驟 3）的參數：`ai_api_url` 改名為 `ai_connection`，其值為
  `provider:端點:識別碼`；`ai_mode_name` 與 `ai_model` 移除。圖形介面以 `Provider + ":" +
  Api_URL` 組出此值。
- **BREAKING** 合併為 markdown 那一步（步驟 5）移除 `ai_mode` 參數；provider 與模型名稱都
  只從分析結構讀取。
- 持續整合：**`ci/pps-ai-analysis.gitlab-ci.yml` 一行都不改**，以維持與工具 v1.0 的相容。
  - 步驟 3 仍接受舊參數名 `ai_api_url`，作為 `ai_connection` 的別名（`ai_connection` 有值時
    以它為準）。
  - 舊的 `ai_mode_name`、`ai_model`（步驟 3）與 `ai_mode`（步驟 5）照樣可以送，腳本不再讀取。
  - `AI_API_URL` 的值可以加上 `provider:` 前綴；不加照舊可以執行，只是出處沒有 provider。
- 共用 AI 模組新增：
  - 拆解連線字串為 provider、端點、識別碼三段（取代原本只拆兩段的那一支）。
  - 依端點組出「列出模型」的網址並查詢，以識別碼找出對應的模型名稱。查詢路徑以寫死的
    常數表示，其中一段為佔位值，由部署者填入。
  - 問 AI 的那一支改為直接收已拆好的端點與識別碼，不再自行拆解。
- **BREAKING** device 鉤子的輸入移除 `ai_mode_name`，`ai_api_url` 改為 `ai_connection`。
  鉤子自行拆解 provider、查詢模型，並把兩者寫進分析結構；範本示範這兩個步驟。
- 分析結構版本由 7 升為 8，新增 `provider` 欄位。讀取 3 到 7 版時視為沒有 provider。
- 出處的 AI 那一行改為 `**AI** **Provider** \`openai\` | **Model** \`gpt-4o\``；任一值為空時
  該半邊不出現，兩者皆空時整行不出現。
- 模型查詢失敗、查無相符的識別碼、端點中找不到 API 根路徑或查詢路徑仍為佔位值時：模型名稱
  留空、分析照常完成、記一筆診斷。
- 圖形介面：
  - 群組 `AI Mode` 改名為 `AI Provider`。
  - 選單每一項顯示 `provider / model`。
  - 選取改以索引對應設定項目，不再以文字比對。
  - 執行前檢查 `Provider` 只含 `A-Z a-z 0-9 . _ -`。
- 新增一支列出模型的腳本。每次啟動工具後，**第一次**進入本功能時執行一次，以處理中對話框
  呈現；此後不再查詢。
  - **BREAKING（規格）** 「進入功能不執行任何腳本」改為允許這一個例外。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `ai-analysis-gitlab-mr`：
  - 畫面配置（群組名稱、進入時的腳本）
  - 進入功能不執行任何腳本（加入列出模型的例外）
  - AI Mode 選單（改為 AI Provider 選單）
  - 流程步驟的參數組裝
  - 服務憑證經由環境變數傳遞
  - 最終報告的組成（出處的 AI 那一行）
  - 鉤子的輸入與輸出邊界
  - device 實作的範本
  - AI 服務的呼叫（連線字串的拆解、模型名稱的來源）
  - AI 服務的憑證與傳輸
  - 分析流程的對外契約
  - 新增「模型名稱的查詢」與「列出模型」兩條需求

## Impact

- **Qt**：
  - `AIAnalysisGitLabMR.cpp/.h`：選單、索引查找、`ai_connection` 組裝、移除 mode 參數、
    第一次進入時的查詢
  - `pps2_0devtool.ui`：群組名稱
  - `pps2_0devtool.cpp`：進入分頁的時機
- **Python**：
  - `scripts/script_utils/ai_utils.py`
  - `scripts/ai_analysis_gitlab_mr/__init__.py`：契約、分析結構、出處
  - `ai_analysis_gitlab_mr_summary.py`
  - `ai_analysis_gitlab_mr_merge_to_md.py`
  - 新增 `ai_analysis_gitlab_mr_list_models.py`
  - `device/default/summary.py`
  - `device/_template/summary.py`、`device/_template/_type_template/summary.py`
- **設定與持續整合**：
  - `PPS2_0DevTool.example.json`
  - `ci/pps-ai-analysis.gitlab-ci.yml`
- **文件**：
  - `docs/user-guide.md`
  - `docs/ai-analysis-gitlab-mr/` 底下的 `README.md`、`cli.md`、`cli.html`、
    `device-authoring.md`
  - `scripts/AUTHORING.md`
- **規格**：`openspec/specs/ai-analysis-gitlab-mr/spec.md`
