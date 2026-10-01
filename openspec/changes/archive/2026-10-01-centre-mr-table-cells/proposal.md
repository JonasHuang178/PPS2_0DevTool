# Proposal

## Why

Merge Request 表格的儲存格文字目前靠左（`QStandardItem` 的預設），而表頭置中
（`QHeaderView` 水平表頭的預設）。五欄裡有四欄是短字串 —— 編號、狀態、作者、日期 ——
固定寬度之下靠左會在每一欄右側留一片空白，與置中的表頭對不齊，看起來像是沒對好。

這是純粹的版面問題，使用者要的是整張表一致置中。

## What Changes

- **修改「Merge Request 表格」需求**：儲存格的文字 SHALL 置中，與表頭一致。
- Qt 側在既有的逐欄迴圈裡多設一次對齊，不逐欄分開設。

不做：

- **不改欄寬、不改伸縮模式、不改截斷方式。** 標題欄仍然伸縮、仍然過長即截斷。
- **不改空白狀態那一列。** 它本來就已經置中。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「Merge Request 表格」加上一條對齊的規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**Qt**

- `AIAnalysisGitLabMR.cpp` —— 建列的那個迴圈多設一次對齊

**腳本**

- 無。

**相容性**

- 只有外觀改變，資料、排序與點擊行為都不動。
