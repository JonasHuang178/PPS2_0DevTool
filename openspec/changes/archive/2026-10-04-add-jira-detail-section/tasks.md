# Tasks

全部在命令列上驗 —— 這一輪是純渲染，不需要 GitLab、JIRA 連線、AI 端點或 Windows 實機。
手寫幾份 `03_summary.json` 餵進步驟 5 就能逐條核對。

## 1. 渲染

- [x] 1.1 `device/default/merge_to_md.py` 的 `render()` 在 `## Code Changes` 之後多組一節：
      標題 `## 詳細資料`，內容一行
      `- For more information, please refer to [KEY](URL)`
- [x] 1.2 條件：`analysis["jira_state"] == contract.JIRA_STATE_OK` **且**
      `contract.plain(analysis["jira_key"])` 非空。兩者缺一就整節不產生
- [x] 1.3 網址取 `analysis["jira_url"]`；為空時只印 key 的純文字，不產生 `[](...)`
- [x] 1.4 不重新判定 key 的有效性、不自己呼叫 `contract.jira_url()` ——
      狀態與網址都由步驟 3 填好帶過來
- [x] 1.5 `key` 與 `url` 都經 `contract.plain()` 收斂，避免 `None` 被印進報告

## 2. 範本

- [x] 2.1 `device/_template/merge_to_md.py` 的 docstring 補上 `analysis` 裡
      `jira_state` / `jira_key` / `jira_url` 三個欄位，並說明 default 用它們做了什麼
- [x] 2.2 同處註明：有自己 `merge_to_md.py` 的 device 不會自動獲得這一節
      （design 決策五）

## 3. 命令列上的核對

以手寫的產物實跑步驟 5，逐條比對輸出字串，不是目視。

- [x] 3.1 `jira_state=ok` + key + url → 該節出現，一行可點連結，位於各檔案發現之後
- [x] 3.2 `jira_state=ok` + key，`jira_url=""` → 該節出現，印純文字 key，不含 `](`
- [x] 3.3 `jira_state=none` → 該節完全不出現（連標題都沒有）
- [x] 3.4 `jira_state=invalid` + key=`WIP` → 該節不出現，且報告中**任何地方**都不出現
      `WIP`（出處已不印 JIRA；確認這一輪沒有不小心把它帶回來）
- [x] 3.5 `jira_state=ok` 但 `jira_key=""` → 該節不出現（不產生指向空字串的指引）
- [x] 3.6 `mrDiff` 為空、只有總覽 → 該節仍然出現，接在 `## Summary` 之後
- [x] 3.7 `overview` 與 `mrDiff` 都空、只有 JIRA → `render()` 回空字串（連這一節也不放），
      且入口腳本以 `MERGE_NOTHING_TO_DO` 失敗。這一節**不得**讓一份沒有內容的報告通過
      「是否有可合併的內容」的判斷（與涵蓋範圍同一個理由）
- [x] 3.8 版本 3 的舊產物（帶 `jira_state=none`）→ 該節不出現，其餘各段照常產出。
      註：`jira_state` 對版本 3／4／5 一律必填，缺漏會在 `validate_analysis()` 就以
      `ANALYSIS_JIRA_STATE_BAD` 失敗 —— 那是既有行為，不是這一輪要處理的事
- [x] 3.9 把產出的報告當成描述再跑一次步驟 1 的切段 → 該節連同舊分析一起被切掉，
      重跑後的報告中該節只出現一次
- [x] 3.10 `contract.plain()` 的收斂：`jira_key=None`、`jira_url=None` → 不印 `None`、
      不拋例外

## 4. 文件

- [x] 4.1 `README.md` 報告版面那一節的範例補上 `## 詳細資料`
- [x] 4.2 同處說明出現條件（三種狀態各自的行為），並註明出處那一段已不印 JIRA ——
      這一節是報告裡唯一提到該議題的地方
- [x] 4.3 確認 README 報告版面範例中的出處那一段是現行的 `<sub>` 逐行形狀
      （`0d2e622` 之後），不是舊的 `|` 分隔單行

## 5. 待實機驗證

- [ ] 5.1 在 GitLab 的討論串裡確認該行連結可點、樣式正常
      （本容器沒有 GitLab，驗不到實際渲染）
- [ ] 5.2 確認結果視窗（`QPlainTextEdit`，不渲染 markdown）中
      `- For more information, please refer to [PPS-1234](https://...)` 這一行
      讀起來仍可接受 —— 純文字下 markdown 連結語法會原樣顯示

## 6. 併入主規格

- [x] 6.1 把 delta 併入 `openspec/specs/ai-analysis-gitlab-mr/spec.md`，注意這一輪是
      **收窄**既有那句「模式名稱與 JIRA 連結 SHALL NOT 出現在報告中」，不是整句刪除
