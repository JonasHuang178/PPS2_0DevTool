# Proposal

## Why

步驟 3 執行時，處理中對話框上的那一行字與實際在做的事對不起來。

實際的順序是這樣的（有 JIRA key 時）：

| 畫面上顯示 | 腳本實際在做的事 |
|---|---|
| `取得程式碼差異…` | 取 diff ✅ |
| `送交 AI 分析…` | **還沒送** —— 正要呼叫 device 的鉤子 |
| `取得 JIRA PPS-1234…` | 取 issue ✅ |
| `取得 JIRA PPS-1234…` | **組 prompt、送出、等 AI 回覆（分鐘級）** ❌ |

兩個毛病：

1. **`送交 AI 分析…` 出現得太早。** 入口腳本在呼叫鉤子**之前**就報了這一行，但鉤子接著
   才去取 JIRA、組 prompt。報這一行的那一刻，prompt 根本還不存在。

2. **真正等待的那幾分鐘，畫面上留著的是一段已經做完的工作。** `fetch_jira` 報完
   `取得 JIRA PPS-1234…` 之後，到 `ai_utils.ask()` 回來之前沒有任何一行蓋掉它。而那一段
   正是整條流程最久的 —— 使用者盯著「取得 JIRA」看兩分鐘，合理的結論是當掉了。

沒有 JIRA key 時症狀較輕：停在 `送交 AI 分析…`，字面上碰巧沒錯，但它仍然是在 prompt 組好
之前就印出來的。

這與 `ProcessingDialog` 自己寫下的理由是同一件事 —— 它為了「新步驟在回報第一則 stage 之前，
畫面上留著的會是上一步最後回報的階段文字，使用者看到的是一段已經結束的工作」而在
`setStep()` 重設文字。同樣的毛病發生在**步驟內部**，而目前沒有任何東西擋它。

根因是「誰該報這一行」沒有被規定過：只有真正送出去的那一方知道什麼時候送出去，而那一方
是 device 的鉤子，不是入口腳本。

## What Changes

- **修改 `script-envelope` 的「進度回報」需求**：`stage` 文字 SHALL 描述回報當下正在進行的
  工作；一段明顯耗時的工作開始前 SHALL 有屬於它自己的回報。
- **新增一條 `ai-analysis-gitlab-mr` 的需求**：呼叫 AI 服務之前 SHALL 回報一次進度，且該
  回報 SHALL 由實際發出呼叫的那一方做出。入口腳本在呼叫鉤子之前的那一次回報 MUST NOT
  宣稱已經送交 AI。
- 腳本側照著改：入口那一行改成描述當下真正在做的事；預設 device 的鉤子在 `ai_utils.ask()`
  之前自己報一行。
- device 範本補上這條慣例，否則照抄範本的新 device 會重現同樣的毛病。

不做（本輪明確排除）：

- **不改對話框本身。** `ProcessingDialog` 沒有問題 —— 它忠實顯示腳本回報的東西。
- **不加「已經過多久」之類的計時。** 進度一律跑馬燈是既有的決定，這一輪不動它。
- **不要求鉤子回報每一個內部階段。** 只要求耗時的那一段有自己的回報；其餘由該 device 自己
  決定。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `script-envelope`: 「進度回報」加上「文字要描述當下」與「耗時的工作要有自己的回報」。
- `ai-analysis-gitlab-mr`: 新增「AI 呼叫前的進度回報」—— 規定由誰報、什麼時候報。

## Impact

**規格**

- `openspec/specs/script-envelope/spec.md` —— 修改一條需求
- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 新增一條需求

**腳本**

- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py` —— 呼叫鉤子前那一行改掉
- `scripts/ai_analysis_gitlab_mr/device/default/summary.py` —— 送出前自己報一行
- `scripts/ai_analysis_gitlab_mr/device/_template/summary.py` —— 補上這條慣例

**Qt**

- 無。對話框忠實顯示腳本回報的內容，問題不在它那邊。

**相容性**

- 只有畫面上的文字與時機改變，信封、產物與參數都不動。
- 既有 device 若有自己的鉤子，不報那一行也不會壞 —— 只是會留著入口那一行，而入口那一行
  不再謊稱已經送出。
