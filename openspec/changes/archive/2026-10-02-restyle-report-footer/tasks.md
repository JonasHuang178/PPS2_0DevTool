# Tasks

## 1. 版號

- [x] 1.1 `SCRIPT_NAME` → `AI Analysis GitLab MR`、`SCRIPT_VERSION` `1.3` → `2.0`
- [x] 1.2 `device/default/__init__.py` 與 `device/_template/__init__.py` 的 `VERSION`
      `1.0` → `2.0`，並寫上規則註解（兩碼、第一碼要一致、不檢查不強制）
- [x] 1.3 `TEMPLATE_VERSION` 完全不動

## 2. 出處版面

- [x] 2.1 `render_footer()` 改成四行清單，每行包在 `<sub>` 裡
- [x] 2.2 `SCRIPT_NAME` 真的印出來（它原本定義了卻從未被使用）
- [x] 2.3 補上 AI 模型名稱，與模式並列
- [x] 2.4 同時呈現 device 與通用兩個版號
- [x] 2.5 移除 JIRA 與涵蓋標示（代價見 proposal）
- [x] 2.6 刪掉因此無人呼叫的 `_jira_label()` 與 `_coverage_label()`

## 3. 核對

- [x] 3.1 工具端：四行齊全，欄位內容與順序正確
- [x] 3.2 CI 端：最後一行換成 pipeline 與 commit 的連結
- [x] 3.3 命令列：沒有工具也沒有 CI → 產生方式整行不出現，剩三行
- [x] 3.4 各欄位缺席：沒有 device／沒有種類／只有模式／只有模型／全空
- [x] 3.5 通用腳本那一行在任何情況下都出現
- [x] 3.6 以真的轉譯器確認是四個 `<li><sub>` 正確巢狀，沒有孤兒的 `<p><sub>`
- [x] 3.7 版號常數：兩碼、device 第一碼與通用一致（`default` 與 `_template` 都驗）
- [x] 3.8 既有的四組回歸測試全過

## 4. 文件

- [x] 4.1 `README.md` 的報告版面範例與出處說明更新

## 5. 待實機驗證

- [ ] 5.1 把報告貼進 GitLab 的 Merge Request 頁面，確認 `<sub>` 真的縮小字級、
      四行分開（本容器用的是 Python 的 markdown 套件，與 GitLab 的轉譯器不是同一個）
- [ ] 5.2 確認結果視窗（純文字）裡那四行讀起來可以接受 —— `<sub>` 會原樣顯示

## 6. 併入主規格

- [x] 6.1 把 delta 併入 `openspec/specs/ai-analysis-gitlab-mr/spec.md`
