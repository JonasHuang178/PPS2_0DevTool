## Why

工具目前只有 Single Building 一個功能，而它不需要對外連線。AI Analysis GitLab MR 是第二個功能，也是第一個需要對外部服務認證的功能 —— GitLab、AI 供應商，以及日後的 JIRA。它讓使用者在工具裡瀏覽指定 repo 的 Merge Request，並把選定的 MR 交給 AI 分析。

加這個功能會撞上三個外殼層級的缺口，它們在「沒有任何憑證、沒有任何表格」的時候都不痛，現在會痛：

**設定檔沒有地方放共用憑證。** 依現況，GitLab token 只能抄進每一個需要它的功能區塊。使用者換 token 時漏改其中一份，那個 tab 就開始回 401 —— 而 401 的第一直覺是「token 過期了」，於是去 GitLab 重發一把新的，找錯方向。這與 `script_io` 註解裡記載過的舊坑是同一種。

**設定檔被 git 追蹤，而且每次建置都無條件覆蓋執行檔旁那一份。** 目前這個檔案裡一個祕密都沒有，所以沒人撞到過。一旦放進三把憑證，使用者就只剩兩個選擇：填在執行檔旁那份（下次建置被蓋掉），或填在專案那份（`git status` 永遠顯示被改過，遲早 commit 上去）。後者是那種發現時已經來不及的錯。

**1200 的寬度撐不住表格。** MR 清單需要 MR / Title / Author / Created / State 五欄，其中只有 Title 需要伸縮。1200 寬度下 Title 只剩約 324px，而標題正是使用者唯一用來認出「是哪一筆 MR」的欄位；那一欄被截掉，這張表就退化成一行字的清單。

## What Changes

### 新增 AI Analysis GitLab MR 功能 tab

畫面左右兩欄。左欄由上而下為 AI Mode（下拉選單）、Analysis Parameter（除錯分析檔開關、存檔目錄、JIRA Key 三選一）、Repository（單選清單，內容來自設定檔）；右欄為 Merge Requests（手動輸入 MR 編號或取得清單二選一、查詢條件、MR 表格），右下角為 AI Analysis 動作按鈕。

- 分析單位是**一個 repo 的一個 MR** —— Repository 與 MR 表格皆為單選
- **進入 tab 不執行任何腳本**：Repository 清單來自設定檔，MR 清單一律由使用者按重新整理才取得
- 切換 repository 會清空 MR 清單並停用 AI Analysis，使用者必須重新取得 —— 否則畫面上是 A 的 MR、選定的卻是 repo B
- MR 表格區分「尚未取得」與「沒有符合條件的結果」兩種空白狀態
- 動作按鈕在條件不足時停用，不另外說明原因（與 Single Building 的既有作法一致）

### 新增六支 Python 腳本

全部由 `scripts/_function_template.py` 複製而來，放在 `scripts/ai_analysis_gitlab_mr/` 之下：一支供重新整理鈕取得 Merge Request 清單，五支為分析流程的各個步驟。

GitLab REST 的呼叫封裝放進 `scripts/script_utils/gitlab_utils/` —— 該分組在上一個 change 建立時即已保留給這個用途，本次首次有內容。呼叫以 Python 標準函式庫實作，不引入第三方套件（本專案目前沒有任何 Python 相依清單，加一個就等於替部署與 CI 加一個安裝步驟）。

**取得 Merge Request 清單那一支為真實實作**，其餘五支本次回傳寫死的假資料（見下）。

### **BREAKING** 設定檔新增工具層級 `Service` 區塊

外殼認得的工具層級欄位從三個（`Debug_Mode` / `User_Guide_Link` / `Function`）增為四個，新增的 `Service` 存放跨功能共用的服務端點與憑證。

`Service` 與 `Function` 同樣**整包保留、不做任何解析**。功能取設定時得到的是「`Service` 併上自己區塊」的結果，同名鍵以功能自己的區塊為準（讓個別功能能指向不同的伺服器）。信封的 `config` 因此改為這個合併後的物件。

- **BREAKING**：信封 `config` 的定義從「該功能在 `Function` 底下的完整區塊」改為「`Service` 併上該區塊」。協定是加法式的，既有腳本收到多出來的鍵會忽略，`scripts/single_building/` 四支腳本不需要修改
- `json.h` 上「新增一個功能不得修改這個檔案」的硬性規則隨之改寫。規則的牙齒保留（不准逐鍵解析），但誠實反映結構已是兩個區塊：新增功能與新增共用服務鍵都不需要改它，只有新增整個工具層級區塊才需要

### **BREAKING** 設定檔移出 git 追蹤

- `PPS2_0DevTool.json` 停止追蹤並加入 `.gitignore`
- 新增 `PPS2_0DevTool.example.json`（追蹤，憑證欄位留空）作為範本
- 建置的複製規則改為：執行檔旁已有設定檔就完全不動它，沒有才從範本生成一份

代價是新增的設定鍵不會傳播到既有部署。症狀由腳本層的必填檢查負責回報（「缺少必填項目：設定 `Gitlab_Access_Token`」），指名道姓、使用者知道下一步做什麼。

此檔案自第一次 commit 起從未裝過任何憑證，因此不需要改寫 git 歷史。

### **BREAKING** 主視窗固定尺寸 1200x830 改為 1280x830

高度不變，維持固定尺寸。Single Building 的兩個清單會連帶變寬，行為不變。

### 共用清單選取樣式進外殼

清單項目的選取樣式改由外殼統一提供，且**選取態不因視窗焦點離開而變色**。

Windows 上焦點離開清單後，預設的選取高亮會退成很淡的灰色。這個功能的操作順序每次都會踩到它：選 repository、按重新整理、到表格挑 MR —— 三步之後使用者已經看不清楚自己選的是哪個 repo，而按下 AI Analysis 時真正生效的正是那一個。此問題不是本功能特有，任何「有清單又有其他控件」的分頁都會遇到，因此放進外殼的共用服務，所有功能一併受惠。

### AI Analysis 的執行流程

按下 AI Analysis 啟動一條**固定五步**的流程：取得 Merge Request 描述 → 取得相關資訊 → AI 分析 → 取得程式碼審閱報告 → 合併為 markdown。

- 五步全部執行，Qt 端 MUST NOT 依條件跳過任何一步。「是否真的做事」由該步的腳本看參數自行決定
- 各步的腳本路徑固定，MUST NOT 取自任何步驟的回傳資料
- 任一步失敗即結束流程，以一個錯誤訊息框指出第幾步與該步回報的原因
- 全部成功時以結果視窗顯示最後一步回傳的 markdown 內容與整條流程耗時

理由：這批腳本同時要能被 CI/CD 的 shell 直接串接。若分支判斷寫在 Qt 端，CI 那一側就成為第二份編排實作，兩份必然漂移。把判斷壓進腳本後，兩個呼叫端都只是固定順序的線性呼叫。

GitLab 與 JIRA 的服務端點與存取權杖由功能注入為環境變數（鍵名的全大寫形式），腳本只從環境變數取用；AI 的端點、金鑰與模型名經由參數傳入。兩者皆不出現在行程的命令列上。

JIRA Key 的模式（`none` / `manual` / `auto`）、手動指定的 key、以及流程中取得的 key 三者一併傳入分析步驟，由腳本決定採用哪一個。

勾選 `Add Debug Analysis file` 時，Qt 在流程啟動前建立一個帶時間戳記的目錄並把路徑傳入每一步；未勾選時傳空字串，整條流程不產生任何檔案 —— 報告內容一律經由回應的 `data` 送回，Qt 從不開檔。

### 本次的實作範圍：契約為真，流程五步的內臟為假

六支腳本的**對外契約一律為真**（標準輸出只有結果 JSON、進度走錯誤輸出、結束碼、必填檢查、參數宣告、模板傾印、兩種投遞方式）。

| | 本次 |
|---|---|
| Qt 側全部 | 真實實作 |
| 取得 Merge Request 清單 | **真實實作**，真的連線至 GitLab |
| 分析流程五步 | 回傳寫死的假資料 |

取得清單那支做成真的，是因為它一次驗證掉四件否則要等下一個 change 才知道的事：`namespace/project` 字串是否足以識別專案、憑證經環境變數的整條路徑是否接通、`gitlab_utils` 第一次有內容時的形狀、以及畫面上的查詢條件如何對應到實際的查詢參數。它同時是風險最低的一支：唯讀、單一端點、失敗了只是表格空著。

## Capabilities

### New Capabilities

- `ai-analysis-gitlab-mr`: AI Analysis GitLab MR 功能 tab 的完整行為 —— 畫面配置與元件啟用規則、Repository 與 MR 清單的來源與取得時機、單選語意與過期清單的處理、JIRA Key 三種模式、五步分析流程的組成與參數組裝、憑證的傳遞方式、失敗與結果的呈現，以及本次交付的腳本實作範圍

### Modified Capabilities

- `app-shell`: 三項需求變更 ——（1）工具層級設定讀取新增 `Service` 區塊，功能設定查詢改為回傳合併結果，顯示與否仍只看功能自己的區塊；（2）主視窗固定尺寸改為 1280x830；（3）共用 UI 服務新增清單選取樣式，且不因焦點離開而變色
- `script-execution`: 「請求信封組裝」需求變更 —— `config` 欄位從功能區塊改為 `Service` 併上功能區塊，並定義同名鍵的優先順序

## Impact

### 程式碼

- `json.{h,cpp}` —— 保留 `Service`、`getFunctionConfig()` 改回傳合併結果、硬性規則改寫。**注意：上一個 change 曾把此檔列為「不受影響」，本次是它首次因結構變更而被修改**
- `pps2_0devtool.{h,cpp,ui}` —— 新增 tab 與其元件、視窗尺寸、共用清單選取樣式、功能實例的建立與訊號連接
- 新增 `AIAnalysisGitLabMR.{h,cpp}` —— 功能本體
- `PPS2_0DevTool.pro` —— 新檔案加入 SOURCES / HEADERS、設定檔複製規則改為不覆蓋既有檔案
- `PythonRunner`、`ProcessingDialog`、`debug`、`common`、`SingleBuilding` 不受影響（`SingleBuilding` 的畫面會因視窗變寬與選取樣式而改變外觀，行為不變）

### 腳本

- `scripts/ai_analysis_gitlab_mr/` 新增入口腳本
- `scripts/script_utils/gitlab_utils/` 首次填入內容：GitLab REST 的呼叫封裝
- `scripts/single_building/` 四支腳本不需修改

### 設定與部署

- `PPS2_0DevTool.json` 移出 git 追蹤、`.gitignore` 新增一條
- 新增 `PPS2_0DevTool.example.json`
- 既有部署的設定檔需手動補上新增的鍵

### 文件

- `README.md` —— 設定檔章節新增 `Service`、命名風格補註腳本路徑的實際作法、新增設定檔與 git 的說明、新增功能章節
- `pps2_0devtool.h` 開頭的「新增一個功能的步驟」註解與 README 是同一份，兩邊都要更新
