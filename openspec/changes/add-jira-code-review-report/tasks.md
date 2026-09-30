# Tasks

## 1. 契約層：常數、擷取、結構與渲染

`scripts/ai_analysis_gitlab_mr/__init__.py`

- [x] 1.1 新增三個標題常數：`CODE_REVIEW_SOURCE_HEADING`（`## 風險評估表總表`）、
      `CODE_REVIEW_TABLE_HEADING`（`## 風險評估表`），並把既有的 `CODE_REVIEW_HEADING`
      改為 `# Code Review 報告`；三個都加入 `__all__`。驗證：`python3 -c "import
      ai_analysis_gitlab_mr as c; print(c.CODE_REVIEW_HEADING, c.CODE_REVIEW_SOURCE_HEADING,
      c.CODE_REVIEW_TABLE_HEADING)"` 印出三個值
- [x] 1.2 新增 `source_heading(device_name)`：讀該 device `__init__.py` 的
      `CODE_REVIEW_SOURCE_HEADING`，未宣告回 `CODE_REVIEW_SOURCE_HEADING` 預設值。
      驗證：對未宣告的 `default` 回預設值；臨時在一個 device 目錄宣告不同字串後回該字串
- [x] 1.3 新增 `extract_risk_table(text, heading)`：依 design 決策八的演算法擷取表格
      （標題比對由 `_heading_pattern()` 導出、圍籬追蹤同時套用於標題與表格掃描、範圍限定
      在下一個 ATX 標題之前、取第一個表格、形狀檢查要求表頭與分隔列）。抓不到時回空字串
      並附帶可辨識原因。驗證：以命令列對下列輸入各跑一次並確認結果 —— 正常、標題階層不同、
      找不到標題、那一節沒有表格而下一節有（**必須抓不到**）、圍籬區塊內有假標題與假表格、
      缺分隔列、同一節兩張表格（取第一張）
- [x] 1.4 新增 `code_review_body(...)` 與 `validate_code_review(payload)`：建構與驗證步驟 4
      的結構（`schema_version` 由入口標記、欄位含檔名／上傳時間／上傳者／網址／表格／
      錯誤訊息），版本比對容許數值與純數字字串。驗證：合法結構通過；版本寫成 `"1"` 通過；
      未知版本與欄位型別錯誤各拋出帶欄位名的例外
- [x] 1.5 新增 `render_code_review_section(payload)`：渲染段落標題（H1）、日期／作者／連結
      三行、總表小標題（H2）與表格；檔名進入連結文字時轉義；結構為 None 時回空字串。
      驗證：正常結構產出的 markdown 與 design 的版面一致；檔名含 `[` `]` `(` `)` 時連結仍
      有效；只有 `error` 沒有表格時三行仍印出且附上訊息
- [x] 1.6 確認 `CODE_REVIEW_HEADING` 仍**不**進入 `_heading_pattern()` 的切段比對式
      （切段邊界只有 `AI_HEADING`），並在該處留一則註解說明理由。驗證：對一份含
      `# Code Review 報告` 的報告文字呼叫 `split_description()`，該段隨 AI 分析一併被切掉

## 2. 步驟 4：取得程式碼審閱報告

`scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_code_review.py`（全面改寫）

- [x] 2.1 移除 `fetch_code_review` 參數，新增 `jira_key`（預設空字串）與 `jira_state`
      （預設 `"ok"`）；更新 docstring 與 `DESCRIPTION`。驗證：`--dump-config` 的模板含新
      參數且不含 `fetch_code_review`；`--help` 的說明同步更新
- [x] 2.2 在 `main()` 最前面**無條件**檢查 `PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH` 與
      `jira_credentials()`，缺任一項即 `reply_fail`，訊息同時點名環境變數與設定檔中的鍵。
      驗證：未設定該變數時（含 `jira_key` 為空的情況）都回 FAIL、exit code 1，訊息含設定
      鍵名；設定後不再擋下
- [x] 2.3 `jira_key` 為空或 `jira_state != "ok"` 時不發任何請求，`reply` 成功且**不落檔**。
      驗證：以 `--request-stdin` 送入空 `jira_key`，stdout 只有一個 `PASS` JSON，且
      `out_path` 指定的檔案不存在
- [x] 2.4 以 `jira_utils.get_issue_attachments()` 列附件，依前綴（區分大小寫）與 `.md`
      篩選，以**解析後**的 `created` 取最新、同時間以 `id` 較大者為新。驗證：對一組模擬的
      附件清單確認選中的是最新那一筆；檔名僅大小寫不同者不被選中；`created` 帶不同時區而
      字典序與實際相反時選對
- [x] 2.5 下載前以 JIRA 回報的 `size` 拒絕超過上限者；下載以**固定路徑**
      `<out_path 所在目錄>/04_code_review_src.md`，不傳目錄給
      `download_issue_attachment()`。驗證：超過上限時不發下載請求且結構帶對應訊息；正常
      下載後該檔案存在於工作目錄
- [x] 2.6 以 `utf-8-sig` 嚴格讀取，解碼失敗不猜其他編碼；讀入後仍套用同一個位元組上限並
      在截斷處留可見記號。驗證：含 BOM 的檔案讀出的內容開頭沒有 `﻿`；以 cp950 編碼的
      中文檔案得到說明應存為 UTF-8 的訊息；超長內容被截斷且有記號
- [x] 2.7 呼叫 `extract_risk_table()`，並依 design 決策五把失敗歸入三類：部署缺漏
      `reply_fail`；外部服務的回答與內容不合約定一律 `reply` 成功並把訊息寫進結構。
      驗證：逐一觸發連線失敗、401、議題不存在、找不到那一節、沒有表格、形狀不符，六種
      都回 `PASS` 且結構的 `error` 有值
- [x] 2.8 以 `code_review_body()` 建構結構、由入口標記 `schema_version`，落檔為
      `out_path`（JSON）；並在 `write_debug_log()` 記一行「看到哪些附件、篩掉哪些」。
      驗證：正常路徑落下的 JSON 可被 `validate_code_review()` 通過；`debug_dir` 有值時
      `debug.log` 含候選檔名那一行
- [x] 2.9 更新 `scripts/AUTHORING.md` §4.2 的環境變數表，新增
      `PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH` 一列（含「沒設定時」欄）。驗證：表格中該列
      的變數名與腳本實際讀的字串一致
- [x] 2.10 依 `AUTHORING.md` 第 10 章驗證這支腳本：`--help`、`--dump-config`、`--request`、
      `--request-stdin` 四種操作皆成功，且**刻意不設定 `PYTHONPATH`**。驗證：四條命令都
      成功，stdout 都只有一個 JSON 物件

## 3. 步驟 5：渲染 code review 那一段

`scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_merge_to_md.py`

- [x] 3.1 參數 `code_review_md_file_path` 改名為 `code_review_json_file_path`，更新
      `--dump-config` 說明與 docstring。驗證：`--dump-config` 的模板含新名稱、不含舊名稱
- [x] 3.2 該路徑改為讀 JSON 並以 `validate_code_review()` 驗證；版本認不得時
      `reply_fail` 並指出讀到的版本與認得的版本。驗證：合法結構成功；版本改成未知值時
      回 FAIL 且訊息含兩個版本號
- [x] 3.3 改以 `render_code_review_section()` 產出該段落，取代原本「原樣貼上一段
      markdown」的作法；段落順序仍為描述 → AI 分析 → code review → 出處。驗證：三段
      齊全時的報告順序正確，且 code review 段落標題為 H1、總表小標題為 H2
- [x] 3.4 沒有給該路徑時整段不出現（沿用既有的 `_is_given()`）；只有 `error` 沒有表格時
      仍輸出該段落。驗證：省略該參數時報告不含該段落的標題與任何佔位文字；只有 `error`
      時段落出現且含訊息
- [x] 3.5 確認「沒有任何可合併的內容」的判斷仍成立：三段皆空時 `reply_fail`。驗證：三個
      路徑都不給時回 FAIL，code `MERGE_NOTHING_TO_DO`
- [x] 3.6 更新 `README.md` 的報告版面一節：加入 code review 段落的實際版面（H1、三行、
      H2、表格）與「兩個標題常數各自獨立」的說明。驗證：README 中的範例版面與
      `render_code_review_section()` 的實際產出逐行相同
- [x] 3.7 更新 `README.md` 的中間產物與除錯目錄清單：`04_code_review.md` →
      `04_code_review.json`，新增 `04_code_review_src.md`，並補上 `04_code_review.json`
      的格式說明。驗證：清單中的檔名與步驟 4 實際寫出的檔名一致
- [x] 3.8 依 `AUTHORING.md` 第 10 章驗證這支腳本的四種操作皆成功。驗證：四條命令都成功，
      stdout 都只有一個 JSON 物件

## 4. device 的宣告與範本

- [x] 4.1 `device/_template/__init__.py` 的註解式宣告清單新增 `CODE_REVIEW_SOURCE_HEADING`
      及其預設值，並說明它只影響「在來源文件裡找哪一節」、不影響報告版面。驗證：開啟該檔案
      即可看到所有可宣告項目（`VERSION`、`STRICT_TYPE`、`CODE_REVIEW_SOURCE_HEADING`）
- [x] 4.2 `device/default/__init__.py` 不宣告該項（沿用預設），並在註解說明為什麼不必宣告。
      驗證：`source_heading("default")` 回預設值
- [x] 4.3 更新 `README.md` 的 device 一節：新增這個宣告、說明它是**宣告不是鉤子**（步驟 4
      不載入任何 device 實作），以及「運算與版面不因 device 而異」。驗證：README 的可宣告
      項目清單與 `_template/__init__.py` 的註解一致
- [x] 4.4 驗證宣告覆寫確實生效：臨時建一個 device 目錄，宣告 `VERSION` 與一個不同的
      `CODE_REVIEW_SOURCE_HEADING`，以 `PPS_DEVICE` 指定後單獨執行步驟 4。驗證：擷取以該
      device 宣告的標題進行，而報告版面與 `default` 相同

## 5. Qt

`AIAnalysisGitLabMR.cpp`、`PPS2_0DevTool.example.json`

- [x] 5.1 `kServiceKey[]` 新增 `"PPS_Scripts_CodeReview_File_StartsWith"`。驗證：
      `serviceEnvVars()` 的回傳含 `PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH`
- [x] 5.2 `kStepArtifactName[3]` 改為 `"04_code_review.json"`。驗證：步驟 4 的 `out_path`
      與步驟 5 的 `code_review_json_file_path` 指向同一個檔名
- [x] 5.3 case 3 移除 `fetch_code_review`，改為轉送 `jira_key`（自步驟 2 的 data）與
      `jira_state`（自步驟 3 的 data，位於 `analysis` 物件之內）。驗證：編譯通過；兩個值
      的取法與 case 2 轉送 `jira_key` 的寫法一致
- [x] 5.4 case 4 的 `insertArtifactPath()` 鍵名改為 `code_review_json_file_path`。驗證：
      編譯通過
- [x] 5.5 `PPS2_0DevTool.example.json` 的 `Function["AI Analysis GitLab MR"]` 新增
      `"PPS_Scripts_CodeReview_File_StartsWith": "CodeReview_"`。驗證：檔案仍是合法 JSON；
      鍵名 `toUpper()` 後等於腳本讀的環境變數名
- [x] 5.6 更新 `README.md` 的設定檔一節：新增該鍵、說明未設定時步驟 4 會失敗、以及升級後
      要對照 `example.json` 補鍵。驗證：README 中的鍵名與 `example.json` 及
      `kServiceKey[]` 三處完全一致
- [x] 5.7 更新 `README.md` 的「功能：AI Analysis GitLab MR」開頭狀態說明與五步流程表：
      步驟 4 不再是 stub，改為連線議題系統取得附件。驗證：README 不再有任何一處說步驟 4
      回傳固定內容
- [x] 5.8 確認整個專案編譯通過（`qmake && make`，macOS/Linux 僅確認編得過）。驗證：建置
      無錯誤與新增的警告

## 6. 端到端整合驗證

- [x] 6.1 `openspec validate --changes add-jira-code-review-report --strict` 與
      `--specs` 皆通過
- [x] 6.2 以命令列串接五個步驟跑完一次（設定同名環境變數、以檔案在步驟之間傳遞），
      確認最終報告含 code review 那一段。驗證：`05_report.md` 的段落順序與版面正確
- [ ] 6.3 **需 Windows 實機**：勾選除錯分析檔跑一次完整分析，確認工作目錄中同時有
      `04_code_review.json` 與 `04_code_review_src.md`，且結果視窗顯示的報告含 code review
      那一段。驗證：要以「只有真的取得附件才會出現的字串」（附件檔名）判定，不能只看流程
      成不成功 —— Qt 沒轉送 `jira_key` 時會靜默走「沒有這一段」，與正常跑完長得一樣
- [ ] 6.4 **需 Windows 實機**：未勾選除錯分析檔跑一次，確認使用者指定的存放目錄之下沒有
      任何檔案，而結果視窗仍顯示完整報告
- [ ] 6.5 **需 Windows 實機**：把設定檔的 `PPS_Scripts_CodeReview_File_StartsWith` 刪掉
      後跑一次，確認在步驟 4 失敗、錯誤訊息框同時點名環境變數與設定鍵，且畫面上的
      Repository 清單與 MR 表格內容不變
- [x] 6.6 把一份含 code review 那一段的報告貼回 MR 描述後再跑一次，確認新報告中 code
      review 與 AI 分析各只有一段，且原始描述中不殘留上一輪的內容
