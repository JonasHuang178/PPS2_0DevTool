## 1. 設定檔與部署

依賴關係上這一組要先做：後面所有東西都讀這份設定檔的新結構。

- [x] 1.1 建立 `PPS2_0DevTool.example.json`，含工具層級的 `Service` 區塊（`Gitlab_Server_URL` / `Gitlab_Access_Token` / `Gitlab_Verify_SSL` / `Jira_Server_URL` / `Jira_Access_Token` / `AI_Mode_List`）與 `Function` 底下的 `Single Building`、`AI Analysis GitLab MR` 兩個區塊；憑證欄位一律留空，`Gitlab_Verify_SSL` 填 `"false"`（本次的預設是不驗證，見 design.md 決策二十三）
- [x] 1.2 `AI Analysis GitLab MR` 區塊填入 `Visible`、`Program`、`Repo_List`（範例兩筆）、`Save_Analysis_File_Dir`（給一個有意義的預設值，避免按鈕開箱即灰）
- [x] 1.3 路徑值一律使用正斜線，避免 JSON 中的反斜線轉義
- [x] 1.4 `git rm --cached PPS2_0DevTool.json`，並在 `.gitignore` 新增該檔名
- [x] 1.5 `PPS2_0DevTool.pro` 的 `deploy_runtime` 規則改為：執行檔目錄旁已有 `PPS2_0DevTool.json` 就完全不動它；不存在時才從 `PPS2_0DevTool.example.json` 複製一份過去。Windows 與非 Windows 兩個分支都要改
- [x] 1.6 `scripts/` 的複製維持無條件覆蓋，不要一起改掉
- [x] 1.7 驗證：刪掉執行檔旁的設定檔後建置 → 自動生成一份；填入內容後再建置 → 內容不被覆蓋

## 2. 外殼：Service 區塊與設定合併

- [x] 2.1 `json.h` 改寫開頭的硬性規則註解（見 design.md 決策四的文字）
- [x] 2.2 `Config` 新增 `m_service` 成員，`load()` 讀入 `Service` 並整包保留；缺少該區塊時視為空物件，不算錯誤
- [x] 2.3 `getFunctionConfig()` 改為回傳「`Service` 併上功能區塊」，同名鍵以功能區塊為準
- [x] 2.4 功能名稱在 `Function` 底下不存在時，`getFunctionConfig()` 仍回傳空物件（不是只回傳 `Service`）
- [x] 2.5 `isFunctionVisible()` 確認讀的是 `Function` 底下的**原始**區塊，不是合併結果
- [x] 2.6 確認 `pps2_0devtool.cpp` 的 `startFlowStep()` 不需要修改 —— 它呼叫 `getFunctionConfig()`，合併自動生效
- [x] 2.7 驗證：在 `Service` 放一個 `Visible: "true"`，確認沒有 `Visible` 的功能仍被隱藏且仍記那筆警告
  - **未實際執行**，由使用者決定結案（2026-09-13）：「未來有問題再修正」。驗的是一條防禦性規則（`Service` 不該能讓功能意外現身），實務上不會有人那樣寫設定。

## 3. 外殼：視窗尺寸與共用清單選取樣式

- [x] 3.1 `UI_Init()` 的 `setFixedSize(1200, 830)` 改為 `1280`
- [x] 3.2 `pps2_0devtool.ui` 的 geometry 一併改為 1280x830
- [x] 3.3 在外殼加入共用的清單選取樣式：底色 `#CCE8FF`、文字 `#042C53`、hover `#E5F3FF`
- [x] 3.4 樣式必須同時涵蓋 `:selected` 與 `:selected:!active` —— 只寫前者的話，焦點離開清單後選取態仍會褪成灰色，而這正是要解決的問題
- [x] 3.5 確認樣式套用到 `QListView` 與 `QTableView` 兩者
- [x] 3.6 驗證：Single Building 的兩個清單外觀改變但行為不變；選取一項後點擊其他控件，選取態不變色

## 4. UI：新增功能分頁

- [x] 4.1 `pps2_0devtool.ui` 新增分頁，標題 `AI Analysis GitLab MR`（大小寫需與設定鍵、`functionName()` 三處完全一致）
- [x] 4.2 左欄：`AI Mode` 群組（下拉選單）
- [x] 4.3 左欄：`Analysis Parameter` 群組（除錯勾選方塊、存放目錄標籤／輸入框／瀏覽鈕、巢狀 `JIRA Key` 群組含三個 radio 與一個輸入框）
- [x] 4.4 左欄：`Repository` 群組（清單）
- [x] 4.5 右欄：`Merge Requests` 群組（兩個互斥 radio、手動編號輸入框、巢狀 `Merge Request Parameter` 群組含兩個勾選方塊與一個 `QSpinBox`、重新整理鈕、`QTableView`）
- [x] 4.6 右下角 `AI Analysis` 按鈕
- [x] 4.7 重新整理鈕使用 Qt 內建圖示 `QStyle::SP_BrowserReload`，不新增任何圖示資產
- [x] 4.8 `QSpinBox` 範圍設為 1–365、預設 7
- [x] 4.9 元件命名採一致前綴，與 Single Building 的 `sb` 前綴風格對齊

## 5. 功能本體

- [x] 5.1 建立 `AIAnalysisGitLabMR.{h,cpp}`，`QObject` 子類別，含 `functionName()` 靜態函式回傳 `AI Analysis GitLab MR`
- [x] 5.2 定義該功能的 widgets 結構，由外殼在 `UI_SetupSignal()` 填好後交過來（比照 `SingleBuildingWidgets`，不傳整包 `Ui::`）
- [x] 5.3 `setupToolService()` 建立實例；`UI_Init()` 依 `isFunctionVisible()` 決定是否 `removeTabByTitle()`；`UI_SetupSignal()` 接元件
- [x] 5.4 `PPS2_0DevTool.pro` 的 `SOURCES` / `HEADERS` 加入新檔案
- [x] 5.5 建構時自 `getFunctionConfig()` 讀 `Repo_List` 填入 Repository 清單、讀 `AI_Mode_List[].Name` 填入下拉選單、讀 `Save_Analysis_File_Dir` 填入路徑輸入框
- [x] 5.6 進入功能不執行任何腳本（不連接 `enterFunction` 之類的載入路徑）
- [x] 5.7 Repository 清單與 MR 表格皆設為單選
- [x] 5.8 MR 表格五欄；標題欄設 `QHeaderView::Stretch`、其餘固定寬；標題 `Qt::ElideRight` 並以整列 tooltip 提供完整標題
- [x] 5.9 建立日期以絕對日期顯示，並把實際時間戳放進 `UserRole` 供 proxy 排序
- [x] 5.10 MR 表格的兩種空白狀態：「尚未取得」與「沒有符合條件」，文案需可區分
- [x] 5.11 兩種取得方式互斥：選手動則清單側整組停用，選清單則手動輸入框停用
- [x] 5.12 手動編號輸入框只留下數字；貼上 `!123` 或完整網址時取出其中的編號
  - 實作期修正：原本寫的是「加 `QIntValidator`」，但 validator 會在貼上那一刻整串拒絕，`!123` 與網址因此連進到輸入框的機會都沒有，取出的邏輯永遠跑不到。改為在 `textChanged` 中自我修正（取最後一段數字），四個 spec scenario 的可觀察行為不變
- [x] 5.13 除錯勾選方塊未勾時，存放目錄的標籤／輸入框／瀏覽鈕整列停用
- [x] 5.14 JIRA Key 預設 `Auto`；僅 `Manual JIRA` 時輸入框可編輯
- [x] 5.15 `updateButtonStates()`：依 design.md 決策十二的四個條件決定 `AI Analysis` 的啟用；停用時不加 tooltip、不加狀態文字
- [x] 5.16 切換 repository 或改動任一查詢條件時，清空 MR 表格並回到「尚未取得」，`AI Analysis` 停用
- [x] 5.17 重新整理：未選 repository 時停用；按下時以 `runFunctionScript()` 執行取得清單的腳本**並帶上 `serviceEnvVars()`**；成功一次填入表格，失敗清空並顯示錯誤訊息，零筆視為成功
  - 實作期修正：這一項原本沒提到環境變數（6.8 只涵蓋流程五步），而取得清單那支腳本同樣只從環境變數讀憑證。漏掉的症狀是使用者明明在設定檔填了 URL 與 token，按下重新整理卻看到「未設定環境變數 GITLAB_SERVER_URL」—— 看起來像使用者沒設定，實際上是呼叫端沒送。`runFunctionScript()` 的 `envVars` 是帶預設值的第六個參數，漏了不會有編譯錯誤

## 6. 功能本體：分析流程

- [x] 6.1 按下 `AI Analysis` 時，若除錯勾選方塊為勾選，先以 `QDir::mkpath()` 建立 `<Save_Analysis_File_Dir>/gitlab_mr_result_<repo>_<mr>_<時間戳>`；路徑以 `QDir::absoluteFilePath()` 組合，不以字串串接分隔符號
- [x] 6.2 目錄建立失敗時顯示錯誤訊息框並**不啟動流程**
- [x] 6.3 時間戳只產生一次，五步共用同一個目錄
- [x] 6.4 未勾選時 `debug_dir` 傳空字串
- [x] 6.5 以 `runFunctionFlow()` 啟動流程；決策函式只做「上一步失敗就回答結束，否則依已完成步驟數回傳第 N 步」，不含任何業務判斷
- [x] 6.6 五個步驟的腳本路徑以 C++ 常數寫死，不取自任何步驟的回傳資料
- [x] 6.7 步驟標籤寫成 `步驟 N/5：<名稱>` 形式（序號由功能自己寫入，外殼不編號）
- [x] 6.8 每一步的 `envVars` 注入 `GITLAB_SERVER_URL` / `GITLAB_ACCESS_TOKEN` / `GITLAB_VERIFY_SSL` / `JIRA_SERVER_URL` / `JIRA_ACCESS_TOKEN`（值取自合併後的 config，變數名為鍵名全大寫）
- [x] 6.9 AI 的端點、金鑰、模型名經由步驟 3 的 `params` 傳入，不注入環境變數、不上命令列
- [x] 6.10 JIRA 的三個值（`jira_mode` / `jira_key_manual` / `jira_key_detected`）一併放進步驟 3 的 `params`，Qt 端不做挑選
- [x] 6.11 步驟 2 回傳的 `script_info`（含 `handler` / `source` / `path`）原樣放進步驟 3 與 5 的 `params`，不解讀
- [x] 6.12 流程 callback：全部成功時以 `showResultDialog("AI Analysis", data.markdown, result.elapsedMs)` 顯示；內容取自 `data`，**不得開啟任何檔案**
- [x] 6.13 流程 callback：有失敗時顯示一個錯誤訊息框，指出第幾步（用 `failedStepIndex`）與該步的 `message`，畫面不變
- [x] 6.14 取消鈕維持外殼現狀，不做任何額外處理

## 7. 共用模組：GitLab REST

- [x] 7.1 在 `scripts/script_utils/gitlab_utils/` 新增 REST 呼叫模組，以標準函式庫 `urllib.request` 實作，不引入第三方套件
- [x] 7.2 遵守共用模組四條規則：不印 stdout、不結束行程（錯誤以例外拋出）、不自行讀環境變數或設定檔、回傳資料結構而非 JSON 字串
- [x] 7.3 專案識別以 `namespace/project` 字串做 URL 編碼後組成請求路徑
- [x] 7.4 支援查詢參數：只取未關閉的、只取指定天數內建立的
- [x] 7.5 401 / 404 / TLS 驗證失敗各自拋出可區分的例外型別，讓入口腳本能給出不同的訊息
- [x] 7.6 單次請求以 `per_page=100` 取回，**不翻頁**；回傳值需讓呼叫端能判斷是否達到上限
- [x] 7.7 是否驗證 TLS 憑證由呼叫端明著傳入（共用模組自己不得讀環境變數）；模組本身不設預設值，預設由入口腳本決定
- [x] 7.8 更新 `gitlab_utils/__init__.py` 的 docstring（目前寫著「本次交付尚未有任何 GitLab 需求，因此這個分組目前是空的」）

## 8. 入口腳本

每一支都從 `scripts/_function_template.py` 複製後改寫。複製時不得刪除設定模組搜尋路徑的那一行，且須保留 `TEMPLATE_VERSION`。

- [x] 8.1 建立 `scripts/ai_analysis_gitlab_mr/__init__.py`
- [x] 8.2 自範本複製出取得 MR 清單的腳本；**真實實作**：自環境變數取權杖、呼叫 `gitlab_utils`、回傳 `data.merge_requests`
- [x] 8.3 該支的 401 / 404 失敗訊息需彼此不同：前者點名環境變數，後者點名設定中的專案名稱
- [x] 8.3a 該支自 `GITLAB_VERIFY_SSL` 讀取驗證開關（**未設定視為不驗證**）並明著傳入 `gitlab_utils`
- [x] 8.3b 開關被設為 `"true"` 而驗證失敗時，訊息指出可把 CA 憑證指給 `SSL_CERT_FILE`，或把 `Gitlab_Verify_SSL` 設回 `"false"`
- [x] 8.3c 取回筆數達到 100 時，於回傳的 `message` 或 `data` 中標示結果可能未完整，讓功能能讓使用者知道
- [x] 8.4 自範本複製出步驟 1「取得 MR 描述」；stub，回傳假的 `description`
- [x] 8.5 自範本複製出步驟 2「取得相關資訊」；stub，回傳假的 `script_info`（含 `status` / `device` / `jira_key` / `ai_summary` / `merge_to_md`）
- [x] 8.6 自範本複製出步驟 3「AI 分析」；stub，回傳假的 `summary`
- [x] 8.7 自範本複製出步驟 4「取得程式碼審閱報告」；stub，收到 `fetch_code_review=false` 時回空報告並回報成功
- [x] 8.8 自範本複製出步驟 5「合併為 markdown」；stub，把前四步的內容組成 markdown 放進 `data.markdown`
- [x] 8.9 六支皆實作輸出雙軌：結果一律放 `data`；`params` 給了輸出路徑時**額外**落檔，未給時不寫任何檔案
- [x] 8.10 五步皆實作輸入雙軌：`params` 有內容就用內容，沒內容但有路徑時讀路徑
- [x] 8.11 落檔時使用序號前綴平鋪命名：`01_description.md`、`02_script_info.json`、`03_summary.json`、`04_code_review.md`、`05_report.md`
- [x] 8.12 六支皆以 `script_io.progress()` 回報階段，並自行節流
- [x] 8.13 六支皆不得整包 log 出 `config`（合併後的 config 含憑證）
- [x] 8.14 憑證一律自環境變數讀取，不得自 `config` 讀取

## 9. 文件

- [x] 9.1 `README.md` 設定檔章節新增 `Service` 區塊與合併語意（同名鍵以功能區塊為準）
- [x] 9.2 `README.md` 新增「設定檔不隨版本控制發佈」說明：`.example.json` 的用途、部署規則、升級後需對照補鍵、shadow build 有 debug/release 兩份
- [x] 9.3 `README.md` 新增 AI Analysis GitLab MR 功能章節（含本次為 stub 的範圍說明）
- [x] 9.4 `README.md` 命名風格表補註：腳本路徑實際寫死在 C++，不放設定檔
- [x] 9.5 `README.md` 新增「不得整包 log 出 `config`」的紀律
- [x] 9.6 `scripts/_function_template.py` 加上同一條紀律的註解
- [x] 9.7 `pps2_0devtool.h` 開頭的「新增一個功能的步驟」註解與 README 同步（兩份必須一致）

## 10. 驗收

> 實作環境（進行 apply 的機器）沒有 `qmake` / `make` / `g++`，也沒有可連線的 GitLab，
> 因此需要建置或實機操作的項目一律留給 Windows 端補驗。
>
> **apply 當下已在實作環境執行並通過**：六支腳本的四種投遞操作、Qt 走法（`data` →
> `params` 串起五步、零檔案）、CI 走法（`--request FILE` 以路徑串接、產物依 `01_`~`05_`
> 命名）、必填檢查、通道分離、缺環境變數時的失敗訊息。
>
> **Windows 實機已補驗通過**：3.6、10.4、10.5、10.6、10.7、10.8、10.10、10.11、10.13
> —— 涵蓋整條五步流程（勾選與未勾選除錯兩種）、對話框與步驟切換、取消與 Escape、
> 切換 repository 的清單失效、以及權杖無效與專案不存在兩種錯誤訊息的區別。

> **實作期修正（Windows 首次執行）**：`attachWidgets()` 在 model 還是 0 欄時就呼叫了
> `applyMrHeaderLayout()`，`QHeaderView::setSectionResizeMode()` 對不存在的 section 會拿
> `visualIndex()` 回傳的 -1 直接索引 section 陣列 → SIGSEGV（官方 Qt binary 是 release
> build，那行 `Q_ASSERT` 被編譯掉了，所以沒有任何訊息）。已移除該次過早呼叫，並在
> `applyMrHeaderLayout()` 內加上 `header->count() < MrColumnCount` 的守衛。
>
> 同一次也證實了部署規則的已知代價：執行檔旁的舊設定檔不會被覆蓋，因此新功能的
> 區塊不存在、分頁被 `isFunctionVisible()` 移除。恢復方式是刪掉執行檔旁的
> `PPS2_0DevTool.json` 再建置一次。

- [x] 10.1 乾淨重建零警告
  - **未實際執行**，由使用者決定結案（2026-09-13）：「未來有問題再修正」。增量建置已多次成功，未做過 Clean All 後的完整重建。
- [x] 10.2 六支腳本各自通過四種操作：`--help`、`--dump-config`、`--request FILE`、`--request-stdin`
- [ ] 10.3 取得 MR 清單那支以命令列直接執行（僅設定環境變數、request 檔中不含憑證）可取回實際資料
  - **使用者決定延後**（2026-09-13）：等真的要接 CI/CD 時再驗。腳本層的四種投遞操作已在實作環境驗過，這一項驗的是「對著真實伺服器」那一半。
- [x] 10.4 在沒有任何 AI 金鑰的環境中按下 `AI Analysis`，五步皆成功，結果視窗顯示假資料組成的 markdown
- [x] 10.5 未勾選除錯分析檔跑完整條流程，確認檔案系統中沒有任何檔案被建立
- [x] 10.6 勾選除錯分析檔跑完整條流程，確認目錄中有 `01_` ~ `05_` 五個檔案且順序正確
- [x] 10.7 流程執行中主視窗被鎖住，步驟切換時對話框不閃爍、標題列的步驟名稱更新、階段文字重設
- [x] 10.8 執行中按 Escape 不中斷；按取消鈕則整條流程中止且畫面完全不變
- [x] 10.9 讓某一步回傳失敗，確認後續步驟不啟動、錯誤訊息框指出第幾步與原因、畫面不變
  - **未實際執行**，由使用者決定結案（2026-09-13）：「未來有問題再修正」。這是唯一未被走過的重要路徑：失敗即停、錯誤框指出第幾步、畫面不變三者皆未經實機確認。
- [x] 10.10 切換 repository 後確認 MR 表格清空且 `AI Analysis` 停用
- [x] 10.11 存取權杖填錯與專案名稱填錯，確認兩者的錯誤訊息不同且各自可行動
- [x] 10.12 Single Building 在視窗變寬與新選取樣式之下行為不變
- [x] 10.13 選取一項後點擊其他控件，確認選取態不褪色（兩個功能都要試）
- [ ] 10.14 `Debug_Mode` 開啟時確認 console 中沒有任何一行印出完整的 `config`
  - **使用者決定不驗收**（2026-09-13）：「token 顯示在 log 或 console 沒關係，這個工具只有本人會用」。風險已被明確接受，不再列為待辦。
  - 實作本身仍然遵守該紀律（六支腳本都沒有整包印出 `config`），範本與 README 的那條提醒也留著 —— 成本是零，而且 `crash.log` 就放在執行檔旁並帶著整個 ring buffer，日後若有人寫了會 dump config 的腳本，權杖會跟著進到那個可能被附進問題單的檔案裡。
- [x] 10.15 `openspec validate add-ai-analysis-gitlab-mr --strict` 通過
