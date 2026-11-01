# Proposal

## Why

**報告裡現在沒有任何地方提到 JIRA。**

曾經有過：出處那一行印著 `JIRA: PPS-1234`（有效時連回該頁面，無效時印出被拒絕的原值並
標示 invalid）。`0d2e622`（出處改版）把它移除了，而那是一個明著做的取捨 —— 該輪的說明
就寫著 JIRA「確實有損失」。於是目前 key 只存在於 `03_summary.json` 的資料裡，讀報告的人
看不到。

而 AI 分析確實採用了 JIRA 議題當輔助資料的時候，那張單子就是這份分析的前提。讀的人看完
Summary 與 Code Changes，下一步往往正是想點開它確認背景 —— 現在他無從得知那是哪一張。

這一輪不是把出處那一行的欄位搬回來（那個形狀本身就是被移除的原因之一：七八個值以 `|`
擠成一行，掃不到，而且 `JIRA: PPS-1234` 與旁邊的 `Script: v1.3` 形狀相同，讀不出那是一個
可以點進去的入口）。這一輪在分析那一段的最後開一節，形狀就是一行指引。

## What Changes

- **修改「最終報告的組成」需求**：AI 分析那一段的版面在該次分析採用了有效的 JIRA key 時
  SHALL 多出一節，內容是一行指向該議題的指引；JIRA 沒有要用、或抽到但無效時 SHALL 不出現。
  原本「結構中的 JIRA 連結 SHALL NOT 出現在報告中」那一條**收窄**為「只准用於該節」。
- 預設 device 的步驟 5 鉤子（`device/default/merge_to_md.py`）據此多渲染一節。
- 不改產物結構、不改 schema 版本、不改 prompt、不改步驟 3、不動出處那一段。

不做（本輪明確排除）：

- **不恢復「抽錯了」那個訊號。** `0d2e622` 移除 JIRA 時失去的是 `invalid` 這個狀態在報告上
  的可見性（持續整合環境只跑自動抽取，而自動抽取正是唯一會抽錯的模式）。本輪的節只在狀態
  **有效**時出現，所以**不恢復它** —— 詳見 design 風險二。要恢復得另開一輪，決定它該出現在
  哪裡、長什麼形狀。
- **不改判定 JIRA key 有效性的規則。** 狀態由步驟 3 的 device 鉤子判定、隨結構帶過來，
  步驟 5 不重新判定（既有需求已如此規定）。
- **不新增「議題是否真的抓到了」的欄位。** 目前的結構分不出「key 有效但議題抓不到」
  （見 design 風險一）。要分得出來得動 schema 與步驟 3，超出這一輪。
- **不改其他 device。** 有自己 `merge_to_md.py` 的 device 不會自動獲得這一節，這是鉤子
  設計的既有性質（見 design 決策五）。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「最終報告的組成」裡 AI 分析那一段的版面，增加 JIRA 指引那一節
  的規定，並收窄 JIRA 連結的禁止條款。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**腳本**

- `scripts/ai_analysis_gitlab_mr/device/default/merge_to_md.py` —— 多渲染一節
- `scripts/ai_analysis_gitlab_mr/device/_template/merge_to_md.py` —— docstring 提一下
  `analysis` 裡有 `jira_state` / `jira_key` / `jira_url` 可用

**契約**

- 無。`analysis` 裡的 `jira_state`、`jira_key`、`jira_url` 三個欄位都已經存在且已驗證，
  這一輪只是讀它們。不新增公開函式（見 design 決策四）。

**Qt**

- 無。

**文件**

- `README.md` —— 報告版面那一節的範例補上這一節

**相容性**

- 產物結構不變，schema 版本不動。既有的 `03_summary.json`（含版本 3、4、5）重跑步驟 5
  就會得到新版面；狀態不是 `ok` 的那些整節不出現。
- `jira_state` **對三個版本一律必填**，這是 `validate_analysis()` 既有的規則（缺漏或填了
  認不得的值會以 `ANALYSIS_JIRA_STATE_BAD` 失敗，與本輪無關；只有 `coverage` 對版本 3、4
  是選填的）。所以本輪不需要、也不應該為「缺少該欄位」另立行為。
- 其他 device 的鉤子不受影響。
- 報告多出一節，但它在 `# AI 分析結果` 這個 H1 之內，所以下一輪重新分析時會跟著既有的
  切段規則一起被切掉，不會在 MR 描述裡越疊越多。
