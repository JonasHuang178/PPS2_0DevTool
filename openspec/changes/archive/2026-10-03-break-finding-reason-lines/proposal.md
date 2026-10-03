# 每一筆發現的理由也依句末標點斷行

## Why

總覽（`## Summary`）早先已經改成「遇到句末標點就斷行」，但 `## Code Changes` 底下每一筆
發現的**理由**還是原樣的一整段：

```
- 這裡沒有檢查回傳值
  這裡沒有檢查回傳值。失敗時會往下走。呼叫端看不出差別。多載入一次就多一筆洩漏。
```

理由與總覽是同一種東西 —— 模型回來的一整段文字，而且**通常比總覽長**。一邊斷行一邊不斷，
差異無從解釋。

## What Changes

- `default` device 的步驟 5 鉤子對每一筆發現的理由套用 `contract.as_list()`，與總覽同一個
  函式、同一組規則（自帶換行原樣、自帶編號保留、否則依句末標點斷開、只有一段原樣）。
- 斷成兩行以上時呈現為該筆發現之下的**子清單**；該筆的 diff 仍與子清單同層，隸屬於該筆發現。
- 沒有標題的發現，各句直接作為該筆的條目，不多包一層。
- 規格把斷行規則的適用範圍從「總覽那一節」擴到「總覽那一節與每一筆發現的理由」，並寫明
  子清單與 diff 的歸屬。
- `SCRIPT_VERSION` 依版號規則加一碼。

## Impact

- `scripts/ai_analysis_gitlab_mr/device/default/merge_to_md.py`
- `scripts/ai_analysis_gitlab_mr/__init__.py`（只動 `SCRIPT_VERSION`）
- `openspec/specs/ai-analysis-gitlab-mr/spec.md`（最終報告的組成）
- `README.md`

`as_list()` 本身不動 —— 它已經是 device 作者的公開 API，行為不變，只是多一個呼叫點。
產物（`03_summary.json`）也不動：斷行在渲染端做，既有的產物重跑步驟 5 就會變好看。
