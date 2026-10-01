# Proposal

## Why

上一輪把 Merge Request 表格五欄全部置中（`2026-10-01-centre-mr-table-cells`）。四個短欄位
置中是對的，但標題欄跟著置中有個代價：它是唯一的長文字欄，置中之後**每一列的起點隨標題
長短而異**，一整排掃下來是跳的 —— 而那一欄正是使用者用來找出要分析的那一筆的。

上一輪的 design.md 已經把這個風險寫下來並接受了（「這是使用者要求的外觀」）。看過之後決定
不接受：四欄置中、標題欄靠左。

## What Changes

- **修改「Merge Request 表格」需求**：標題欄水平靠左，其餘四欄水平置中，五欄都垂直置中。
- Qt 側把對齊的規則從「一律置中」改成「標題欄以外一律置中」，仍在同一個迴圈裡一次套用。

不做：

- **不改欄寬、伸縮模式、截斷方式或點擊行為。**
- **不改表頭。** 表頭維持置中（`QHeaderView` 的預設）。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「Merge Request 表格」的對齊規定改為標題欄例外。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**Qt**

- `AIAnalysisGitLabMR.cpp` —— 建列迴圈裡的對齊改成一個條件式

**相容性**

- 只有外觀改變。
