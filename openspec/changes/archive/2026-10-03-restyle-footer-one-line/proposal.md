# 出處資訊改成一個 `<sub>` 加 `<br>`

## Why

報告末尾的出處資訊目前是四個清單項目，每一項各自包一個 `<sub>`：

```
- <sub>**Device**　`ssd`　`2.1`　·　**Type**　`bug`</sub>
- <sub>**腳本**　AI Analysis GitLab MR `2.0`</sub>
```

兩個問題：

1. **四個項目、四個 `<sub>`**，貼到 MR 討論串後是一個四點的清單，視覺重量與正文的清單
   相同，而它只是出處。使用者要的形狀是 `<sub>test<br>test2</sub>` —— 一段縮小的文字，
   行與行之間斷開，不是一個清單。
2. **分隔用了全形字元** —— 全形空白（U+3000）、`·`、全形斜線 `／`。這些字元寬度在等寬
   字型下不定，貼上後也不保證照原樣保留，而它們做的事半形空白與 ` | ` 就做得到。

## What Changes

- `render_footer()` 改為輸出單一個 `<sub>`，行與行之間以 `<br>` 斷開。
- 所有分隔字元改為 ASCII：欄位之間一個半形空白，同一行內兩組值之間 ` | `。
- 規格中兩條與新形狀相反的敘述（「各行為結構上彼此分開的元素」、「縮小字級的標記置於
  每一行之內」）改寫；另外寫明分隔字元限於 ASCII。
- `SCRIPT_VERSION` 依版號規則加一碼。

## Impact

- `scripts/ai_analysis_gitlab_mr/__init__.py`（`render_footer()`、`SCRIPT_VERSION`）
- `openspec/specs/ai-analysis-gitlab-mr/spec.md`（最終報告的組成）
- `README.md`（出處資訊那一節的範例與說明）

不影響資料結構、信封協定或任何一步的輸入輸出 —— 只有最後一段 markdown 的字面形狀改變。
