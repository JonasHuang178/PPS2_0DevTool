## 1. 專案骨架與建置

- [ ] 1.1 建立 `PPS2_0DevTool.pro`（Qt5 + qmake，widgets），驗證：Windows 上 Qt Creator + MinGW 編譯通過並產出執行檔
- [x] 1.2 建立 `version.h`（工具名稱、版本 `v2.0.0`、設定檔名常數、建置日期），驗證：編譯通過且版本常數為 `v2.0.0`
- [x] 1.3 建立 `result_code.h`，定義框架層級三類錯誤碼（設定類、行程類、回應類），驗證：編譯通過；功能自訂錯誤碼不在此檔
- [x] 1.4 建立 `common.{h,cpp}` 的 `formatElapsedTime()`，驗證：輸入 5025000 毫秒輸出 `01h 23m 45s`
- [x] 1.5 建立最小可執行的 `main.cpp` 與 `pps2_0devtool.{h,cpp,ui}`（來源路徑列 + 空 tab widget + 進度條，固定 1200x830），驗證：程式啟動後顯示空的主視窗
- [x] 1.6 確認 macOS 上同一份程式碼編譯通過，Windows 專屬 API 皆以 `#ifdef Q_OS_WIN` 隔離，驗證：macOS 上 qmake + make 成功

## 2. 診斷基礎設施

- [x] 2.1 實作 `debug.{h,cpp}`：`QTDebug` / `QTWarn` / `QTError` 三個等級，格式為含毫秒的時間戳記加固定寬度等級名稱，驗證：輸出形如 `[2026-09-06 14:30:12.345] [ QT DEBUG ] 訊息`
- [x] 2.2 加入 300 行環形緩衝，所有等級的輸出都寫入，驗證：輸出 350 則訊息後緩衝內僅保留最後 300 則
- [ ] 2.3 `Debug_Mode` 為 true 時開啟 console（`AllocConsole()` + `SetConsoleOutputCP(CP_UTF8)` + 重導向標準輸出與錯誤輸出），驗證：console 出現且中文訊息不亂碼
- [ ] 2.4 註冊 console 控制處理常式：收到關閉事件時先終止腳本子行程再結束程式，驗證：執行腳本期間關閉 console，程式結束且工作管理員中無殘留 Python 行程

## 3. 設定讀取

- [x] 3.1 實作 `json.cpp`：只讀 `Debug_Mode` / `User_Guide_Link` / `Function` 三個工具層級欄位，`Function` 以未解析的原始物件保留，驗證：設定檔含未知欄位時仍正常載入
- [x] 3.2 實作 `getFunctionConfig(name)`：回傳該功能完整區塊；名稱不存在時回傳空物件不報錯，驗證：查詢不存在的名稱得到空物件且程式繼續執行
- [x] 3.3 實作 `isFunctionVisible(name)`：`Visible` 為字串 `"true"` 才顯示；區塊或鍵不存在時回傳 false 並記一筆 `QTWarn`，驗證：三種情況（`"true"` / `"false"` / 未設定）行為與警告皆正確
- [x] 3.4 設定檔不存在或非合法 JSON 時顯示錯誤訊息框並結束程式，驗證：刪除設定檔啟動顯示訊息框並結束；設定檔填入壞掉的 JSON 亦同
- [x] 3.5 建立 `PPS2_0DevTool.json`，`Function` 為空物件，驗證：程式以此設定檔正常啟動且無任何 tab

## 4. Python 層（可獨立於 Qt 驗證）

- [x] 4.1 建立 `scripts/script_utils/__init__.py`（留空）與 `scripts/script_utils/logger.py`：全部等級走錯誤輸出、預設 INFO、提供 `set_verbose()`、格式對齊 Qt 端、重複匯入只有一份 handler，驗證：匯入兩次後每則訊息只輸出一次，且 DEBUG 預設不顯示
- [x] 4.2 實作 `script_io.arg()` 與 `script_io.cfg()` 宣告物件（名稱、型別、預設值、必填、說明），驗證：宣告後可取得完整欄位
- [x] 4.3 實作 `script_io.parse_request()`：支援 `--request-stdin` 與 `--request FILE` 兩種投遞，回傳含 `source_path` / `config` / `action` / `params` 四鍵的結果，驗證：兩種投遞方式對同一份信封得到相同結果
- [x] 4.4 在 `parse_request()` 中實作必填檢查與預設值回填，缺漏時回傳失敗結果並在 `message` 指出缺少的項目名稱，驗證：移除一個必填設定鍵後訊息明確指出該鍵名，且業務邏輯未被執行
- [x] 4.5 實作 `--dump-config`：輸出含 `_template_version` / `action` / `source_path` / `config` / `params` / `_help` 的模板，`config` 鍵來自 `cfg()` 宣告且值為空，有預設值的參數預先填入，驗證：傾印後直接以 `--request` 執行成功
- [x] 4.6 實作 `-v` 旗標連動 `logger.set_verbose(True)`，以及 `--help` 輸出參數與設定說明，驗證：加 `-v` 後 DEBUG 訊息出現；`--help` 列出所有宣告的項目
- [x] 4.7 實作 `script_io.progress(stage)`：往錯誤輸出印單行 `{"progress":{"stage":...}}` 並立即排清緩衝，驗證：以管線接收時進度即時出現而非結束時一次噴出
- [x] 4.8 實作 `script_io.reply()` / `reply_fail()` / `run()`：結果只印標準輸出、`result` 固定全大寫、成功結束碼 0、業務失敗結束碼 1、未攔截例外轉為失敗結果加結束碼 1，驗證：三種情境的標準輸出與結束碼皆符合
- [x] 4.9 撰寫 `scripts/_function_template.py`：攜帶 `TEMPLATE_VERSION`，示範 `cfg()` 宣告、`arg()` 宣告、`logger` 使用、`progress()` 回報與 `reply()` 回傳，驗證：`--help`、`--dump-config`、`--request run.json`、`--request-stdin` 四種操作原樣皆成功且後兩者回傳 `PASS`
- [x] 4.10 確認腳本在 Linux 與 Windows 皆可執行：路徑使用 `pathlib`、外部執行檔不寫死副檔名、開檔明確指定 UTF-8，驗證：範本腳本在兩個平台上以同一份信封執行皆回傳 `PASS`

## 5. PythonRunner

- [x] 5.1 建立 `PythonRunner.{h,cpp}` 與 `PythonRunnerResult` 結構（`success` / `hasJson` / `result` / `message` / `detail` / `data` / `errorCode` / `exitCode`），驗證：編譯通過且結構不含任何輸出尾端欄位
- [x] 5.2 實作行程環境注入：`PYTHONPATH`（附加執行檔目錄下 `scripts`，以 `QDir::listSeparator()` 分隔且原值為空時無前導分隔符號）、`PYTHONUTF8=1`、`PYTHONUNBUFFERED=1`、`TOOLNAME`、`TOOLVERSION`，並支援功能疊加自訂變數，驗證：腳本印出這些變數的值皆正確
- [x] 5.3 設定行程工作目錄為執行檔目錄，並以該目錄解析設定檔中的相對腳本路徑（絕對路徑原樣使用），驗證：從三種不同的當前目錄啟動程式，同一份設定檔解析出相同的腳本路徑
- [x] 5.4 啟動前檢查腳本檔案存在，不存在時不啟動行程並回報含完整解析後路徑的訊息，驗證：設定一個不存在的路徑，訊息中出現完整路徑
- [x] 5.5 實作信封組裝（`source_path` / `config` / `action` / `params` 四欄位，不含 `tool`），寫入標準輸入後呼叫 `closeWriteChannel()`，驗證：腳本能讀完標準輸入並正常結束，不會卡住
- [x] 5.6 實作錯誤輸出逐行讀取與跨讀取邊界的殘餘緩衝，行程結束時處理剩餘內容，驗證：以刻意分段送出的長訊息測試，該行未被拆成兩則
- [x] 5.7 區分進度行與診斷行：行首為 `{` 才嘗試解析，含 `progress` 欄位者更新對話框、其餘走診斷輸出；`Debug_Mode` 關閉時仍逐行讀取但不輸出非進度行，驗證：`Debug_Mode` 關閉時進度仍更新且 console 未開啟
- [x] 5.8 實作標準輸出解析：整段解析為單一 JSON 物件，不實作任何退回掃描，驗證：腳本額外印一行到標準輸出時整段解析失敗且不嘗試撈取片段
- [x] 5.9 實作成敗判定：不論結束碼一律先解析標準輸出；有 JSON 時依 `result` 判斷（比對不分大小寫）並取出各欄位；無 JSON 時視為未回傳結果並在訊息中包含結束碼，驗證：腳本回 `FAIL` 且結束碼 1 時顯示的是腳本寫的 `message`
- [x] 5.10 處理 `errorOccurred(FailedToStart)`，給出「無法啟動 Python：找不到 '<指令>'。請檢查設定檔的 Program 欄位」訊息，且與腳本崩潰訊息不同，驗證：把 `Program` 改成不存在的指令，顯示的是此訊息

## 6. 執行模型

- [x] 6.1 建立處理中對話框子類別：攔掉 Escape 按鍵與關閉事件、移除關閉鈕提示旗標，只保留取消鈕作為取消途徑，驗證：執行中按 Escape 不中斷、標題列無關閉鈕
- [x] 6.2 設定對話框為 application-modal、`setMinimumDuration(0)`、`setRange(0, 0)`，且不呼叫 `setValue()`，並顯示功能名稱與初始文字，驗證：腳本開始執行的瞬間主視窗即無法操作，進度呈現為跑馬燈且無百分比
- [x] 6.3 收到進度回報時更新對話框階段文字，驗證：範本腳本回報三個階段，對話框文字依序變化
- [x] 6.4 實作「閒置 / 執行中 / 取消中」單一執行狀態機，非閒置狀態下的執行請求回 false 並記一筆 `QTWarn`，不跳訊息框，驗證：在 callback 內立即再次呼叫執行介面，第二次回 false 且無訊息框
- [x] 6.5 實作取消：進入取消中狀態、要求行程終止、以計時器在 3 秒後檢查並強制終止，等待期間不阻塞事件迴圈，驗證：以一支忽略終止訊號的腳本測試，3 秒後被強制結束且期間跑馬燈持續動作
- [x] 6.6 取消中狀態收到行程結束通知時丟棄結果且不呼叫 callback，驗證：腳本正常結束的同時按下取消，功能的 callback 未被呼叫且畫面無變化

## 7. 外殼整合

- [x] 7.1 實作 `runFunctionScript(功能名稱, 腳本路徑, 動作, 參數, callback, 額外環境變數)`：立即回傳是否成功啟動，結果經由 callback 送達，全程不開巢狀事件迴圈，驗證：執行期間主視窗持續重繪，作業系統未將視窗標為沒有回應
- [x] 7.2 由 `runFunctionScript` 內部自動填入 `source_path`（取自來源路徑列）與 `config`（取自 `getFunctionConfig()`），功能不需傳入，驗證：腳本收到的信封含正確的來源路徑與功能設定區塊
- [x] 7.3 `Debug_Mode` 為 true 時在執行命令加上 `-v`，驗證：`Debug_Mode` 開啟後 console 中同時出現 Qt 與 Python 的 DEBUG 訊息且格式對齊
- [x] 7.4 實作功能掛勾訊號 `sourcePathChanged` 與 `workingDataCleared`，驗證：變更來源路徑時訊號發出並附帶新路徑；未連接訊號的功能不受影響
- [x] 7.5 實作共用 UI 服務：資訊／警告／錯誤訊息框、結果視窗（標題、內容、耗時）、取得目前來源路徑、依標題移除 tab，驗證：各服務皆可從功能端呼叫並顯示統一樣式
- [ ] 7.6 實作視窗行為：關閉主視窗隱藏至系統匣、雙擊還原、系統匣右鍵選單只有結束、About 顯示工具名稱／版本／Qt 版本／建置日期／使用手冊連結，驗證：四項行為逐一操作皆正確，About 顯示 `v2.0.0`
- [x] 7.7 實作啟動檢查：Python 3 可用性、單一實例鎖（`QSharedMemory`）、SIGSEGV 時輸出 crash log，驗證：重複啟動時第二個實例不會出現；移除 Python 後啟動顯示對應錯誤

## 8. 端到端驗收

- [x] 8.1 以範本腳本跑通完整路徑：Qt 送信封、腳本回結果、Qt 正確解析並交給 callback，驗證：`data` 內容與腳本回傳的一致
- [x] 8.2 腳本回 `FAIL` 加結束碼 1 時，Qt 顯示的是腳本寫的 `message`，驗證：訊息框內容為腳本的 `message`，而非「找不到 JSON」之類的通用訊息
- [x] 8.3 腳本崩潰（無 JSON）時，Qt 顯示未回傳結果並包含結束碼，驗證：以一支立即拋例外的腳本測試，訊息含結束碼
- [x] 8.4 腳本印額外內容到標準輸出時，該次執行明確失敗且未走任何退回解析，驗證：以一支同時印雜訊與結果的腳本測試，結果為失敗
- [x] 8.5 執行中對話框跑馬燈會動、階段文字會更新、取消鈕可按；按下取消後畫面完全無變化，驗證：以一支分階段回報並可被取消的腳本逐項確認
- [x] 8.6 執行中無法啟動第二支腳本，驗證：程式化連續呼叫時第二次回 false
- [ ] 8.7 `Debug_Mode` 開啟時 Qt 與 Python 的訊息都出現在同一個 console 且格式對齊，中文不亂碼，驗證：console 中兩種來源的訊息時間戳記與等級欄位寬度一致
- [ ] 8.8 最終確認：Windows 與 macOS 皆編譯通過，程式啟動後為空的 tab widget 且無任何功能，驗證：兩平台建置成功且主視窗無 tab
