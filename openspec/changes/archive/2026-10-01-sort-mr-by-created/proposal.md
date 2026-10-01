# Proposal

## Why

Merge Request 表格載入後的排序是 Qt 的預設 —— `setSortingEnabled(true)` 會依表頭當下的
排序指示器排，而指示器的預設是第 0 欄（編號）遞增。於是畫面上第一列是編號最小的那一筆，
也就是**最舊**的。

使用者要挑的幾乎都是最近的那幾筆。每次載入都要自己先點一下 `Created` 才看得到想要的。

## What Changes

- **修改「Merge Request 表格」需求**：每次重建表格後 SHALL 預設依建立日期由新到舊排序；
  使用者之後改動的排序 SHALL 保留到下一次重建為止。
- `Created` 欄寬由 90 放寬到 115 —— 那一欄現在固定帶著排序指示器的箭頭，維持 90 會把
  `2026-09-30` 截成 `2026-0…`。

不做：

- **不改排序所依據的值。** 既有需求已經規定依實際時間先後排序，而資料裡放的本來就是完整
  時間戳（畫面只顯示到日），所以同一天的多筆也排得開。
- **不記住使用者的排序選擇。** 重新整理是一批新資料，回到預設才是可預期的；而這個專案
  一向不持久化使用者在畫面上的操作。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「Merge Request 表格」加上預設排序的規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**Qt**

- `AIAnalysisGitLabMR.cpp` —— 重建表格時設定預設排序，並放寬 `Created` 欄寬

**相容性**

- 只有畫面的初始排序與一欄的寬度改變。
