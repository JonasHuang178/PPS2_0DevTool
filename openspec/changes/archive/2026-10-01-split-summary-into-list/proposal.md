# Proposal

## Why

報告的 `## Summary` 那一節是一整段文字，擠成一團不好讀。

成因不是渲染吃掉了換行 —— 從步驟 3 到報告，換行是一路通的（`plain()` 只去頭尾空白、保留
內部換行；沒有 AI 端點時的替代內容本來就是三行）。成因是 prompt 要的就是「整體變更的摘要，
三到五句」，模型照辦，回來的是一句接一句的一段。

於是使用者看到的是：

```
## Summary
此問題OO。XXXX。YYYY。ZZZZ。
```

兩個呈現面都受影響：結果視窗（`QPlainTextEdit`，不渲染 markdown）會依視窗寬度自動折行成
一片文字牆；貼到 GitLab 則是一個段落。

模型有時也會自己回有序清單（`1. xxx 2. xxx`），但同樣寫在一行裡，所以那個結構目前完全
看不出來。

## What Changes

- **修改「報告中 AI 分析那一段的版面」需求**：總覽那一節在來源是單一段落時 SHALL 依句末
  標點斷成逐行的清單；來源已自帶有序編號時 SHALL 保留該編號並呈現為有序清單；來源已自帶
  換行時 SHALL 原樣呈現。
- 契約新增一支公開的 `as_list()`，由預設 device 的步驟 5 鉤子呼叫。
- 不改 prompt、不改 AI 的回覆格式、不改產物結構。

不做（本輪明確排除）：

- **不改 prompt。** 這一輪完全落在渲染端 —— 這樣既有的 `03_summary.json` 重跑步驟 5 也會
  變好看，不必重新花錢問一次 AI。
- **不動產物裡的 `overview`。** 產物存的是 AI 的原文（真相），版面是由它推導出來的。改了
  原文，之後想換版面就只能重問 AI。
- **不處理每一筆發現的 `reason`。** 它有同樣的問題，但它縮排在條目底下，再加一層清單會變成
  巢狀，版面要另外想。先把總覽做對，看過實際效果再決定。
- **不認中文數字與圈號編號**（`一、`、`①`）。只認阿拉伯數字。認不出來時會落到句末標點那一條，
  結果仍然是逐行的清單，不是災難。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「報告中 AI 分析那一段的版面」加上總覽那一節的斷行規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**腳本**

- `scripts/ai_analysis_gitlab_mr/__init__.py` —— 新增公開的 `as_list()`
- `scripts/ai_analysis_gitlab_mr/device/default/merge_to_md.py` —— 總覽那一節改用它
- `scripts/ai_analysis_gitlab_mr/device/_template/merge_to_md.py` —— 註解提一下有這支可用

**Qt**

- 無。

**相容性**

- 產物結構不變，版本號不動。既有的 `03_summary.json`（含版本 3、4）重跑步驟 5 會得到新版面
  —— 那正是這一輪想要的。
- 其他 device 的鉤子不受影響；想用就呼叫 `as_list()`，不呼叫就維持原樣。
