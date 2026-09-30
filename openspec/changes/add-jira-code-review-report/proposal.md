# Proposal

## Why

分析流程的步驟 4「取得程式碼審閱報告」至今是 stub —— 它回傳固定內容、不連任何外部服務，原因是來源尚未定案。

來源現在定了：工程師用 AI code review 工具產出一份 markdown 報告，以附件掛在該 Merge Request 標題所指的 JIRA issue 上。接起來之後，五步流程才真的全部有實作，報告裡也才有「人審過什麼」那一節 —— 而那一節的價值不在把整份審閱貼進報告，而在**呈現總表並附上連結**，讓 reviewer 連回去看全文。

## What Changes

- **步驟 4 改為真實實作**：自 JIRA issue 的附件中取得 code review 報告，擷取其中的風險評估總表，交給步驟 5。附件以檔名前綴篩選，多筆時取上傳時間最新的一筆。
- **步驟 4 的產物由 markdown 改為結構**（`04_code_review.md` → `04_code_review.json`），渲染交給步驟 5 —— 與步驟 3 的 `03_summary.json` 同一套。理由是報告要印出附件的日期、作者與連結，而那些值只有步驟 4 拿得到，步驟 5 卻只收到一個檔案路徑。
- **移除 `fetch_code_review` 參數**。「要不要真的去抓」改由 `jira_key` 與 `jira_state` 決定；與路徑或狀態並存的布林開關是多餘的，它只多一個能自相矛盾的狀態。
- **報告新增 code review 那一段的版面**：段落標題、日期／作者／連結三行、總表小標題，全部由步驟 5 寫出；步驟 4 只交出表格本身。
- `CODE_REVIEW_HEADING` 由 `# 程式碼審閱` 改為 `# Code Review 報告`。
- **新增設定鍵 `PPS_Scripts_CodeReview_File_StartsWith`**（值為 `CodeReview_`），由 Qt 注入為環境變數 `PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH`。未設定時步驟 4 回報失敗並結束整條流程。
- **device 得宣告來源文件中總表那一節的標題**（`CODE_REVIEW_SOURCE_HEADING`）。各條產品線的 code review 工具產出格式不同，那一節不一定叫同一個名字。擷取的**運算**與報告的**版面**仍不因 device 而異。
- 新增失敗的三分類原則：**部署缺漏**（本機即可判定）失敗並結束流程；**外部服務的回答**與**別人文件的內容不合約定**寫成訊息顯示在報告中。

不做（本輪明確排除）：

- **不把 code review 交給 AI 分析參考。** 步驟 4 在步驟 3 之後，要餵給 AI 就得搬到步驟 2，而那會讓附件的取得發生在 JIRA key 的有效性被判定之前 —— 每一筆標題前綴是 `[WIP]`、`[Draft]` 的 MR 都會白打一趟 JIRA。
- **不新增第五個 device 鉤子。** device 只宣告一個字串，不在步驟 4 執行任何程式碼，因此步驟 4 不會有「哪一個 device 的鉤子壞了」這類失敗。
- **不支援沒有前後 `|` 的表格寫法。** 改成「這一行含有 `|`」的寬鬆偵測會把散文裡任何一個管線符號當成表格開頭。
- **不把報告寫回 GitLab 或 JIRA。** 與既有規格一致。
- **不在 Qt 端預先檢查新設定鍵。** 只留腳本那一道，一個地方一個真相。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `ai-analysis-gitlab-mr`: 步驟 4 由 stub 改為連線 JIRA 取得附件；新增附件的選取規則、總表的擷取規則、失敗的三分類、步驟 4 的結構與版本；報告新增 code review 段落的版面與出處 metadata；device 的宣告項目新增一項。

## Impact

**腳本**

- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_code_review.py` —— 全面改寫：讀環境變數、列附件、選檔、下載、擷取總表、落檔為結構
- `scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_merge_to_md.py` —— code review 那一段改為讀結構並渲染，不再原樣貼上一段 markdown
- `scripts/ai_analysis_gitlab_mr/__init__.py` —— 三個標題常數、總表擷取、code review 結構的建構與驗證、段落渲染
- `scripts/ai_analysis_gitlab_mr/device/_template/__init__.py` 與 `device/default/__init__.py` —— 可宣告項目的註解清單新增 `CODE_REVIEW_SOURCE_HEADING`

**Qt（需重新建置）**

- `AIAnalysisGitLabMR.cpp` —— `kServiceKey[]` 新增一筆；`kStepArtifactName[3]` 改為 `04_code_review.json`；case 3 轉送 `jira_key` 與 `jira_state`、移除 `fetch_code_review`；case 4 的參數改名為 `code_review_json_file_path`
- `PPS2_0DevTool.example.json` —— `Function` 底下新增 `PPS_Scripts_CodeReview_File_StartsWith`

**文件**

- `README.md` —— 步驟 4 不再是 stub、報告版面、`04_code_review.json` 的格式、新設定鍵、device 新宣告項目、除錯目錄新增的檔案
- `scripts/AUTHORING.md` —— §4.2 的環境變數表新增一列

**相依**

- 無新的第三方套件。`jira_utils` 既有的 `get_issue_attachments()` 與 `download_issue_attachment()` 已足夠。

**相容性**

- 既有部署的設定檔不會長出新鍵，因此升級後步驟 4 會失敗並點名該鍵。這是刻意的取捨，見 design。
- `04_code_review.md` → `04_code_review.json`：中間產物每次執行重新產生，沒有需要相容的舊檔。
- 既有 device 不受影響：未宣告 `CODE_REVIEW_SOURCE_HEADING` 時落到預設值，行為與現在相同。
- `JIRA_SERVER_URL` / `JIRA_ACCESS_TOKEN` 未設定時步驟 4 失敗，而步驟 3 對同一組變數是寬容的。兩者的嚴格度刻意不同，見 design。
