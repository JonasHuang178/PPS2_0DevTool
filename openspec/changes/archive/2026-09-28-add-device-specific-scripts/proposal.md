## Why

一個 Merge Request 該怎麼分析，會因為它屬於哪一條產品線而不同。SD 與 SSD 要問 AI 的
問題不一樣，報告要怎麼排也不一樣，連 JIRA key 藏在標題哪裡都可能不一樣。

目前六支腳本只有一種行為。要支援第二條產品線，只能在腳本裡塞 if，或整份複製一次 ——
前者讓每條產品線的邏輯互相干擾，後者在共用的那些部分（GitLab 的四種錯誤指引、圍籬
長度計算、diff 截斷、往返切段的邊界）製造出會各自漂移的複本。

封存的 `add-ai-analysis-gitlab-mr` 把這件事留成兩個 Open Question：「`device` 的來源」
與「`handler` 的 dispatch 內容」。本 change 回答它們 —— 而答案是**沒有 handler，軸是
device**。

## What Changes

### 新增 device 機制

`scripts/ai_analysis_gitlab_mr/device/` 之下每個目錄是一個 device。目錄名即 device 名。

- device 名稱由環境變數 `PPS_DEVICE` 指定。**空值或未設定**時用 `default`；**指定了但
  沒有對應目錄**時失敗，並在訊息中列出認得哪些
- 工具端由 Qt 從設定檔注入該環境變數，CI 由 runner 自行設定 —— 腳本端只有一條取值
  路徑，兩個呼叫端對它來說長得一模一樣（沿用憑證的既有作法）
- 認得哪些 device 由掃目錄決定，不維護註冊表 —— 放一個目錄進去就是新增一個 device

### 三個 device 鉤子

固定五步與各步的腳本路徑**不變**。每一步的入口腳本保留共用的外殼（信封、憑證、
GitLab 呼叫、產物落檔、錯誤訊息），只把「因 device 而異的那一段」交給鉤子：

| 步驟 | 鉤子 | device 決定什麼 |
|---|---|---|
| 2 | `jira_key` | 怎麼從 MR 抽出 JIRA key |
| 3 | `summary` | 問 AI 什麼、怎麼解析、組出什麼分析內容 |
| 5 | `merge_to_md` | AI 分析那一段的版面 |

步驟 1（取得描述）與步驟 4（程式碼審閱）不因 device 而異。

**fallback 是逐鉤子的，不是逐 device**：`device/ssd/` 只放 `merge_to_md.py` 是合法的，
缺的鉤子自動用 `default` 的那一份。否則只想改報告風格的 device 也得複製一整支 summary，
而那份複本會跟著 default 漂移。

### 新增 device 腳本範本

`device/_template/` 提供三個鉤子的範本，說明各自收到什麼參數、必須回傳什麼。底線開頭
因此不會被當成 device（與 `scripts/_function_template.py` 同一個慣例）。

### **BREAKING** 步驟 2 改名並改變職責

- 檔名 `ai_analysis_gitlab_mr_script_selector.py` 改為 `ai_analysis_gitlab_mr_info.py`，
  action `script_selector` 改為 `mr_info`，產物 `02_script_info.json` 改為 `02_mr_info.json`
- 它現在**自己連線 GitLab** 取得 MR（標題、分支等），再交給 device 的 `jira_key` 鉤子
- 回傳的 `script_info` 攤平：`handler` / `source` / `path` / `status` / `device` 全部移除

舊名稱來自更早的實作，那時它真的在「選腳本」—— 而那正是既有設計明文禁止的事（Qt 不得
依回傳資料決定執行哪支腳本）。留著它會讓人去找一個不存在的機制。

### **BREAKING** 分析結構升到 schema_version 3

`analysis` 新增三個 JIRA 欄位：`jira_key`（抽到的原值）、`jira_state`
（`ok` / `none` / `invalid`）、`jira_url`（只有 `ok` 且伺服器位址有設才有值）。

原本只有 `jira_url` 一個欄位，它同時要承載「有沒有 key」「key 對不對」「伺服器位址有
沒有設」三件事 —— 第三件與前兩件無關，卻會污染判斷。

### 報告末尾的出處加上 device 與 JIRA

```
Script: v1.0 | Device: ssd v1.2 | AI Mode: Open AI | JIRA: WIP (invalid)
Gitlab Pipeline #1000 | Commit e456d23
```

同一份 MR 用不同 device 跑出來的報告不一樣，而讀報告的人看不出用了哪一個。每個 device
有自己的 `VERSION`，與入口腳本的版本分開標示。

### 順手修正：程式碼審閱那一段沒有自己的標題

步驟 5 目前把程式碼審閱原樣接上，而它寫的是 `##` 層級 —— 會縮在 `# AI 分析結果` 底下，
讀起來像是分析的子節。目前 `fetch_code_review` 固定為假所以還看不到，一開啟就會現形。

### 本次不做

- `script_utils/ai_utils.py`（AI 呼叫的共用模組）
- 各 device 真實的 AI 呼叫與 prompt —— 等 `ai_utils` 定案，否則第一批 device 腳本寫完
  就要為了改用共用模組再重寫一次
- JIRA 內容的讀取（只處理 key 的抽出與判定）

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 新增 device 機制的需求（名稱來源與解析、兩層 fallback、
  鉤子的邊界與回傳、載入失敗的回報）；修改既有需求 —— 步驟 2 的名稱與職責（改名、
  自行連線 GitLab、`script_info` 攤平）、JIRA key 三種模式的分派位置、分析結構升到
  版本 3 並新增三個 JIRA 欄位、報告出處新增 device 與 JIRA、程式碼審閱段的標題層級

## Impact

### 腳本

- 新增 `scripts/ai_analysis_gitlab_mr/device/`：載入器、`default/`、`_template/`
- `ai_analysis_gitlab_mr_script_selector.py` 改名為 `ai_analysis_gitlab_mr_info.py`，
  並改為連線 GitLab + 呼叫鉤子
- `ai_analysis_gitlab_mr_summary.py`、`ai_analysis_gitlab_mr_merge_to_md.py` 改為呼叫鉤子
- `ai_analysis_gitlab_mr/__init__.py`：部分私有 helper 升格為 device 作者可用的公開
  API（圍籬長度計算、字串正規化、diff 上限、`AI_HEADING` 唯讀）；新增分析結構的驗證
  函式，供步驟 3（收到鉤子回傳時）與步驟 5（渲染前）共用

### 程式碼

- `AIAnalysisGitLabMR.cpp`：`kServiceKey[]` 新增一筆，讓設定檔的 device 值注入為
  `PPS_DEVICE`；步驟 2 的腳本路徑常數與 action 跟著改名
- 其餘 Qt 側不受影響：固定五步、腳本路徑寫死、決策函式都不變

### 設定與部署

- `PPS2_0DevTool.example.json` 的功能區塊新增 device 鍵
- `scripts/` 的複製規則不變。`device/default/` 在 repo 裡，每次建置會被覆蓋；開發者
  自行新增的 device 目錄因為 repo 裡沒有同名檔案，不會被覆蓋也不會被刪除

### 文件

- `README.md`：新增 device 機制與「如何新增一個 device」；`03_summary.json` 的格式更新
  到版本 3；報告出處的形狀更新
