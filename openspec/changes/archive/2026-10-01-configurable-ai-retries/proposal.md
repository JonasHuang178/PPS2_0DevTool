# Proposal

## Why

上一輪讓逾時可以設定，但逾時並不單獨決定使用者等多久 —— 那一輪的 design.md 就寫下了這件事：

> 逾時屬於可重試的錯誤，所以連線層會重試、內容層會再重問 —— 最壞情況約是逾時值的八倍再
> 加退避。把逾時設成 30 秒仍可能等上四分半。

於是「我把逾時設成 30 秒」與「我最多等 30 秒」之間還差兩個寫死的常數：連線層重試 3 次、
內容層重問 1 次。使用者把逾時調短之後仍然等了四分半，看起來就像設定沒有生效。

## What Changes

- **修改「AI 呼叫的重試界線」需求**：兩層重試的次數 SHALL 皆可由設定指定；未指定時 SHALL
  採用實作的預設值。
- 設定的位置與逾時相同 —— 每個 AI 模式自己的欄位（`Retry_Count`、`Reask_Count`）。
- `0` SHALL 為合法值（那正是「服務很忙時不要再等」的那一個值）。不合法時與逾時同樣明確
  失敗，且在取得差異之前就失敗。
- 該步驟 SHALL 把三個值與算出來的最壞情況記進診斷輸出。

不做：

- **不改任何預設值。** 120 / 3 / 1 維持不變，沒有設定的人行為完全不變。
- **不改「哪些錯誤值得重試」。** 那條需求不動 —— 這一輪只讓次數可調。
- **不加總等待時間的上限設定。** 三個值相乘就是上限，再加一個「總上限」會有兩套互相矛盾
  的規則，而使用者無從得知哪一套生效。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「AI 呼叫的重試界線」加上次數可設定的規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**腳本**

- `scripts/ai_analysis_gitlab_mr/__init__.py` —— 新增 `ai_retries()`、`ai_reask()` 與兩個
  預設值常數；三個數值設定共用一支讀取與驗證
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py` —— 兩個新參數，與逾時
  一起在取得差異之前驗證，並記一行診斷
- `scripts/ai_analysis_gitlab_mr/device/default/summary.py` —— 問 AI 時帶上兩者

**Qt**

- `AIAnalysisGitLabMR.{h,cpp}` —— 自所選的 AI 模式多讀兩個鍵並轉送

**設定檔**

- `PPS2_0DevTool.example.json` —— 示範這兩個欄位

**相容性**

- 加法式。沒有這兩個欄位的設定檔行為與先前相同。
