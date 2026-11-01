# Proposal

## Why

表格裡兩個固定寬度的欄位放不下自己的內容：

| 欄位 | 寬度 | 內容實際需要 | 畫面上 |
|---|---:|---:|---|
| Status | 70 | `merged` 74、`opened` 72 | `open…` |
| Author | 110 | `Jonas Huang` 114 | `Jonas Hua…` |

兩者都只差幾個像素，所以**每一列**都被截斷 —— 而 Status 只有四種值，截斷之後
`opened` 與 `closed` 在畫面上都是 `…`，完全失去這一欄的意義。

## What Changes

- Status 欄寬 70 → 85（容得下最寬的 `merged`，並留一些給別的字型與 DPI）。
- Author 欄寬 110 → 150（容得下「名 姓」這種常見長度）。
- Author 欄加上提示文字 —— 150 容不下所有名字，截斷的那幾筆否則就看不到全名。
- **新增一條需求**：固定寬度的欄位 SHALL 容得下其內容的常見值；仍會截斷的欄位 SHALL 以
  提示文字提供完整內容。

不做：

- **不追求 Author 容得下所有名字。** 再長的名字一定存在，而這一欄每多一像素，會伸縮的
  標題欄就少一像素。這正是提示文字存在的理由。
- **不改欄位的伸縮模式。** 標題欄仍是唯一會伸縮的那一欄。

## Capabilities

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 「Merge Request 表格」加上固定欄位寬度與截斷補償的規定。

## Impact

**規格**

- `openspec/specs/ai-analysis-gitlab-mr/spec.md` —— 修改一條需求

**Qt**

- `AIAnalysisGitLabMR.cpp` —— 兩個欄寬，以及 Author 的提示文字

**相容性**

- 只有外觀改變。兩欄共多佔 55px，由會伸縮的標題欄吸收。
