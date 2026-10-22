# 把一次執行留下的東西整理成三層版面，並改名為執行紀錄

## Why

一次執行會留下四種東西，但它們全部堆在同一層，而且只有產物有編號：

```
gitlab_mr_result_lw-os_123_20261022_001600/
├── 01_description.md … 05_report.md   ← 產物，有編號
├── debug.log                          ← 五步共用一個檔，append
├── ai_prompt.txt / ai_reply_1.txt     ← 只有步驟 3 寫，沒有編號
└── （CI 另有 req1.json…req5.json）
```

四個具體的問題：

1. **產物有編號，紀錄沒有。** Qt 替產物命名時寫明了編號的理由 ——「序號前綴讓目錄的列出
   順序就是流程的執行順序，出問題時一眼看得出停在哪一步」。同一個論點對紀錄完全成立，
   但紀錄一個編號都沒有。

2. **`debug.log` 認不出是哪一步寫的。** 寫入那一支不加任何東西，步驟身分全靠呼叫端在訊息
   開頭自己寫一個字；而**失敗那一行沒寫** —— 步驟 2 與步驟 3 的失敗紀錄都是
   `FAIL [CODE] message`，長得一模一樣。失敗的那一刻正是最需要知道是哪一步的時候。

3. **沒有時間戳。** Qt 的 debug console 有、持續整合的 job log 有，只有這個檔沒有，所以
   兩邊的紀錄對不起來。

4. **兩個呼叫端的版面不一樣。** 持續整合把紀錄放在 `pps-work/debug/` 子目錄，Qt 勾選時
   卻把紀錄與產物混在同一層。同一批腳本、同樣五步，目錄長相取決於誰呼叫。

另外兩件與「使用者怎麼拿到這次的紀錄」同一件事的兩面：

5. **畫面上看不到紀錄在哪裡。** 存放目錄的輸入框顯示的是設定檔的相對路徑（`./analysis`），
   而實際的紀錄在它底下某個帶時間戳的子目錄裡 —— 那個路徑畫面上完全不出現。流程**失敗**
   時更明顯：只跳一個訊息框，而失敗正是最需要去翻紀錄的時候。

6. **「debug」這個詞說的是「你為什麼會來看」，而不是「裡面是什麼」。** 勾選方塊寫
   `Add Debug Analysis file`（而且 `file` 是單數，它其實產生一整個目錄）。

## What Changes

### 版面

- 兩個呼叫端一律三層：產物在上層，`logs/` 放過程紀錄，`requests/` 放信封。
- **BREAKING** 持續整合的 `req<N>.json` 移到 `$CI_PROJECT_DIR/pps-requests/`，也就是
  artifact 收集路徑之外；`script` 與 `after_script` 的兩行 `rm -f` 隨之移除 —— 真憑證
  從頭到尾不進 artifact，所以沒有東西需要刪。

### 執行紀錄

- **BREAKING** 一步一個 log 檔，取代共用的 `debug.log`；`DEBUG_LOG_NAME` 移除。
- 檔名由 `out_path` 的基底名推導（`03_summary.json` → `03_summary.log`），所以「log 與
  產物同名」變成結構性的，不靠呼叫端維持；`out_path` 沒給時改用 action 名。
- 每一行前面加 `[YYYY-MM-DD HH:MM:SS.mmm]`，與 debug console 同格式。
- 整份內容的紀錄掛步驟號：`03_ai_prompt.txt`、`03_ai_reply_1.txt`、
  `03_recheck1_ai_prompt.txt`。
- 流程外的腳本用 action 命名：`list_merge_requests.log`、`list_models.log`。

### 信封紀錄與憑證遮罩

- **腳本自己寫 `requests/`**，不是呼叫端寫。腳本本來就拿得到信封與紀錄目錄，也是它自己
  宣告哪些參數是憑證，所以遮罩規則只存在一個地方，兩個呼叫端的行為自動一致，Qt 不需要
  為此新增任何程式碼。
- 參數宣告新增遮罩欄位：可宣告為整個遮掉，或給一個自訂的遮罩方式。
- `ai_api_key` 整個遮掉；`ai_connection` 保留 provider 與端點、只遮掉尾端的 shareCode ——
  前兩段對診斷有用，第三段是憑證。
- 檔名按 action（`requests/ai_summary.json`），不帶步驟號 —— 步驟號是呼叫端的命名慣例，
  腳本不該去解析它。

### 改名

- **BREAKING** 參數 `debug_dir` → `log_dir`。
- **BREAKING** device 鉤子的 `inputs["debug_write"]` → `inputs["log_write"]`。
- 共用函式 `write_debug_log` → `write_log`、`write_debug_file` → `write_log_file`、
  `debug_writer` → `log_writer`。
- 勾選方塊的字樣 `Add Debug Analysis file` → `Save run log`。
- Qt 內部的 `debugDir`、`debugFileCheck`、`aiDebugFileCheckBox` 一併改為 log 字樣。
- **不動** `Debug_Mode` 與 debug console（那是另一個概念），也不動設定鍵
  `Save_Analysis_File_Dir`（它是那個時間戳目錄的父目錄，不是 `logs/`）。

### 畫面上的路徑

- 存放目錄的輸入框啟動時填入解析後的絕對路徑，可以直接複製。
- 結果視窗多收一個選填的目錄：給了就多出開啟紀錄目錄的按鈕與一行可選取的完整路徑，
  沒給則與現在完全相同。未勾選 `Save run log` 時不提供該入口（那次的產物在暫存目錄，
  流程結束就被刪了）。
- **流程失敗時改用同一種能承載按鈕的視窗**，不再只跳訊息框 —— 失敗比成功更需要那個入口。

### 其他

- `list_models` 補上 `log_dir` 與 `out_path`，否則版面裡的 `logs/list_models.log`
  沒有人寫得出來。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `ai-analysis-gitlab-mr`：執行紀錄的開關與存放目錄（改名、絕對路徑）、工作目錄於流程
  啟動前建立（三層版面與 `log_dir`）、執行紀錄的內容（一步一個 log、時間戳、信封紀錄）、
  結果呈現（開啟目錄的入口、失敗也走同一種視窗）、畫面配置（勾選字樣）、分析流程的對外
  契約（`list_models` 的參數）
- `script-envelope`：參數與設定的單一宣告點（新增遮罩宣告），並新增一條「信封紀錄與憑證
  遮罩」
- `app-shell`：共用 UI 服務（結果視窗可承載一個開啟目錄的入口）

## Impact

- **Python**
  - `scripts/script_io.py`：參數宣告的遮罩欄位、信封紀錄的寫出
  - `scripts/ai_analysis_gitlab_mr/__init__.py`：`write_log` 系列、`log_dir`、
    `DEBUG_LOG_NAME` 移除
  - `scripts/script_utils/ai_utils.py`：`ai_connection` 的遮罩（沿用 `split_connection`）
  - 本功能六支入口腳本 ＋ `ai_analysis_gitlab_mr_list_models.py`
  - `device/default/`、`device/_template/`、`device/_template/_type_template/`
- **Qt**
  - `AIAnalysisGitLabMR.cpp/.h`：`logDir`、三層版面、輸入框的絕對路徑、結果與失敗兩條
    路徑的目錄入口
  - `pps2_0devtool.cpp/.h`：結果視窗的選填目錄參數
  - `pps2_0devtool.ui`：勾選方塊的名稱與字樣
- **持續整合**：`ci/pps-ai-analysis.gitlab-ci.yml`
- **文件**：`docs/user-guide.md`、`docs/ai-analysis-gitlab-mr/`（`README.md`、`cli.md`、
  `cli.html`、`device-authoring.md`、`device-authoring.html`）、`scripts/AUTHORING.md`
- **規格**：`ai-analysis-gitlab-mr`、`script-envelope`、`app-shell`

不影響報告的內容與版面、分析結構的格式，或任何一步的產物格式。
