# Proposal

## Why

AI 服務忙碌時，使用者只能對著那個固定尺寸的對話框等逾時 —— 而逾時是寫死在腳本裡的
120 秒，他沒有任何辦法把它調短。

實際的等待比 120 秒長得多。逾時屬於「可重試」的錯誤，所以一次逾時會觸發連線層的重試，
而內容層又會再重問一輪：

| 設定的逾時 | 最壞情況的等待 |
|---:|---:|
| 120 秒（現況） | 約 16 分鐘 |
| 60 秒 | 約 8.5 分鐘 |
| 30 秒 | 約 4.5 分鐘 |

（連線層最多重試 3 次 → 每一輪最多 4 次嘗試；內容層再重問 1 次 → 兩輪；另加退避。）

使用者要的是「早點知道這次不行」，而那個決定取決於他自己的 AI 服務有多快 —— 腳本裡的
一個常數答不出來。

## What Changes

- **修改「AI 服務的呼叫」需求**：逾時 SHALL 可由設定指定；未指定時 SHALL 採用實作的預設值。
- 設定的位置是**每個 AI 模式自己的欄位**（`Service.AI_Mode_List[].Timeout_Seconds`），
  不是一個全域值。
- 值不合法（非數字或非正數）時 SHALL 明確失敗，MUST NOT 退回預設值；且 SHALL 在取得差異
  **之前**就失敗。

不做（本輪明確排除）：

- **不讓重試次數可設定。** 這一輪照使用者要求只動逾時。但逾時並不單獨決定總等待時間 ——
  上面那張表就是證據。要真正把等待時間封頂，重試次數也得能調，那是另一輪。
- **不改預設值。** 120 秒維持不變，沒有設定的人行為完全不變。
- **不在畫面上提供這個設定。** 它屬於「這個 AI 服務有多快」，與 repository、JIRA 模式那種
  每次都會換的東西不同，放在設定檔比較恰當。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「AI 服務的呼叫」加上逾時可設定的規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**腳本**

- `scripts/ai_analysis_gitlab_mr/__init__.py` —— 新增 `ai_timeout()` 與 `DEFAULT_AI_TIMEOUT`
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py` —— 新增 `ai_timeout` 參數，
  在取得差異之前驗證
- `scripts/ai_analysis_gitlab_mr/device/default/summary.py` —— 問 AI 時帶上它

**Qt**

- `AIAnalysisGitLabMR.{h,cpp}` —— 自所選的 AI 模式讀出該欄位並轉送

**設定檔**

- `PPS2_0DevTool.example.json` —— 示範這個欄位

**相容性**

- 完全是加法式的。沒有這個欄位的設定檔行為與先前相同。
