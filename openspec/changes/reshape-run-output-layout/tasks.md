## 1. 信封層：遮罩宣告與信封紀錄（script_io）

- [x] 1.1 `_Param` 的 `__slots__` 與 `arg()` 新增 `mask`（`None` / `True` / callable，見 design D4）。
  驗證：`--help` 與 `--dump-config` 的輸出不受影響（遮罩只影響信封紀錄，不影響宣告的呈現）。
- [x] 1.2 `parse_request()` 新增選填參數指定紀錄目錄的鍵名（預設 `"log_dir"`），並在尾端把
  **實際收到的信封**遮罩後寫到 `<log_dir>/requests/<action>.json`。紀錄目錄為空就不寫。
  驗證：用一支臨時腳本宣告一個 `mask=True` 的參數，以**檔案**與**標準輸入**兩種方式各投遞
  一次，確認：
  - 兩次寫出的檔案內容相同
  - 該參數在檔案裡是 `***`，原值不出現
  - 紀錄目錄給空字串時完全不產生檔案
- [x] 1.3 `ai_utils` 新增連線字串的遮罩函式（保留 provider 與端點、遮掉 shareCode，沿用
  `split_connection()`）。驗證：`openai:https://h/api/external/v1/chat:ABC` 遮成
  `openai:https://h/api/external/v1/chat:***`；沒有 provider、沒有 shareCode 的輸入都不拋例外。

## 2. 紀錄層：一步一檔與時間戳（ai_analysis_gitlab_mr）

- [x] 2.1 `write_debug_log()` → `write_log()`：檔名改由 `out_path` 的基底名導出
  （`out_path` 為空時用 action 名），每行前加 `[YYYY-MM-DD HH:MM:SS.mmm]`；移除
  `DEBUG_LOG_NAME`。簽章要能同時拿到 `log_dir`、`out_path` 與 action。
  驗證：以同一個 `log_dir` 分別用兩組 `out_path` 各寫一行，確認產生兩個檔、各自只有自己那一行、
  每行開頭都是時間戳。
- [x] 2.2 `write_debug_file()` → `write_log_file()`、`debug_writer()` → `log_writer()`，
  並讓它們寫進 `<log_dir>/` 之下。驗證：`grep -rn "write_debug_\|debug_writer\|DEBUG_LOG_NAME" scripts`
  無結果。
- [x] 2.3 參數 `debug_dir` → `log_dir`，六支入口腳本與 `__init__.py` 全面換名；鉤子的
  `inputs["debug_write"]` → `inputs["log_write"]`。驗證：
  - `grep -rn "debug_dir\|debug_write" scripts` 無結果
  - 六支腳本的 `--help` 都列出 `log_dir`
  - `grep -rn "Debug_Mode\|debugMode" scripts *.cpp *.h` 的結果數量與改動前相同（確認沒有誤改）
- [x] 2.4 步驟 3 的整份內容紀錄掛步驟前綴（`03_ai_prompt.txt`、`03_ai_reply_1.txt`、
  `03_recheck1_ai_prompt.txt`），前綴同樣由 `out_path` 導出。驗證：跑一次步驟 3（對模擬服務），
  確認 `logs/` 下的檔名都帶 `03_`，且重查輪次的前綴仍在。
- [x] 2.5 宣告步驟 3 的兩個憑證參數的遮罩：`ai_api_key` 用 `True`，`ai_connection` 用 1.3 的函式。
  驗證：跑一次步驟 3，確認 `requests/ai_summary.json` 裡金鑰是 `***`、連線字串只有尾端被遮、
  provider 與端點仍可讀。
- [x] 2.6 `ai_analysis_gitlab_mr_list_models.py` 補上 `log_dir` 與 `out_path`。驗證：
  `--help` 列出兩者；給了 `log_dir` 後產生 `logs/list_models.log`。
- [x] 2.7 `SCRIPT_VERSION` → `2.13`；`device/default` 與 `device/_template` 的 `VERSION`
  第二碼各加一。驗證：報告出處的腳本那一行顯示 `2.13`。

## 3. device 與範本

- [x] 3.1 `device/default/summary.py`、`device/_template/summary.py`、
  `_template/_type_template/summary.py`：`debug_write` → `log_write`，範本的 inputs 說明同步。
  驗證：三個檔 `python -m py_compile` 通過；範本的 docstring 裡沒有 `debug_` 字樣。

## 4. Qt

- [ ] 4.1 `context.debugDir` → `logDir`，值改為 `workDir + "/logs"`（未勾選時仍為空字串）；
  傳給步驟的參數鍵改為 `log_dir`。驗證：編譯通過；勾選後跑一次，產物在工作目錄、紀錄在
  `logs/`、信封在 `requests/`。
- [ ] 4.2 `m_widgets.debugFileCheck` → `logFileCheck`、`.ui` 的 `aiDebugFileCheckBox` →
  `aiLogFileCheckBox`、字樣 → `Save run log`。驗證：編譯通過；
  `grep -rn "aiDebugFileCheckBox\|debugFileCheck\|Add Debug" *.cpp *.h *.ui` 無結果。
- [ ] 4.3 `saveDirEdit` 填入時改用 `resolvedSaveDir()` 的絕對路徑。驗證：設定填 `./analysis`，
  啟動後輸入框顯示絕對路徑，而設定檔的值未被改寫。
- [ ] 4.4 `showResultDialog()` 新增選填的 `folder`：非空時加一行可選取的路徑與一顆開啟按鈕
  （`QDesktopServices::openUrl`），空時版面不變。驗證：編譯通過；兩種情況各跑一次看版面。
- [ ] 4.5 `onFlowFinished()` 的失敗路徑改用 `showResultDialog()`（標題與內容標明第幾步失敗與
  原因），成功與失敗都帶上 `context.logDir`。驗證：
  - 成功時結果視窗有路徑與按鈕，按下會開啟那一次的 `logs/`
  - 故意讓某一步失敗，失敗的視窗同樣有路徑與按鈕，且仍指出第幾步與原因
  - 未勾選 `Save run log` 時兩種情況都沒有按鈕

## 5. 持續整合

- [ ] 5.1 `ci/pps-ai-analysis.gitlab-ci.yml`：新增變數指向 `$CI_PROJECT_DIR/pps-requests`，
  五步的 `cat > "$W/req<N>.json"` 改寫到該目錄，`D` 改為 `pps-work/logs`，移除兩行 `rm -f`。
  驗證：
  - `grep -n "req[1-5].json" ci/` 的路徑都不在 `pps-work/` 之下
  - `grep -n "rm -f" ci/` 沒有刪 req 檔的那兩行
  - 以該檔的請求形狀實際跑步驟 3 與步驟 5，兩步都成功
  - 跑完後 `pps-work/requests/ai_summary.json` 裡的金鑰是 `***`

## 6. 文件

- [ ] 6.1 更新 `docs/user-guide.md`（勾選字樣、絕對路徑、三層版面）、
  `docs/ai-analysis-gitlab-mr/README.md`（畫面圖的勾選字樣、行為那一節）、
  `cli.md` 與 `cli.html`（`log_dir`、`requests/` 與遮罩、CI 的 req 路徑）、
  `device-authoring.md` 與 `device-authoring.html`（`inputs["log_write"]`、紀錄版面）、
  `scripts/AUTHORING.md`（`write_log` 系列與遮罩宣告）。驗證：
  `grep -rn "debug_dir\|debug_write\|debug.log\|Add Debug" docs scripts/AUTHORING.md` 無結果。
- [ ] 6.2 文件中寫明三件代價：遮過的信封要補值才能重跑、`inputs` 鍵名改了（樹外 device 要改
  一行）、輸入框顯示的絕對路徑不寫回設定檔。驗證：三處都找得到對應段落。

## 7. 整體驗證

- [ ] 7.1 對模擬服務跑完整的五步（勾選與未勾選各一次），確認：
  - 勾選時：產物五個在工作目錄、`logs/` 有五個 `NN_*.log` 加步驟 3 的整份內容紀錄、
    `requests/` 有五個遮過的信封
  - 未勾選時：存放目錄之下一個檔案都沒有，結果視窗仍有完整報告但沒有開啟按鈕
  - 兩種情況的報告內容完全相同
- [ ] 7.2 執行 `openspec validate reshape-run-output-layout --strict`。
