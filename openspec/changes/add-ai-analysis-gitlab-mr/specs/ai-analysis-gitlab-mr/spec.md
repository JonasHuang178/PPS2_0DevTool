## ADDED Requirements

### Requirement: 畫面配置

功能 tab 的標題 SHALL 為 `AI Analysis GitLab MR`，其設定區塊在設定檔 `Function` 底下的鍵名 SHALL 與標題相同。

畫面 SHALL 分為左右兩欄。左欄由上而下為 `AI Mode`、`Analysis Parameter`、`Repository` 三個群組；右欄為 `Merge Requests` 群組。右下角 SHALL 提供 `AI Analysis` 動作按鈕。

`Analysis Parameter` 群組內 SHALL 包含除錯分析檔的勾選方塊、分析檔存放目錄的輸入框與瀏覽鈕，以及巢狀的 `JIRA Key` 群組。

`Merge Requests` 群組內 SHALL 包含兩個互斥的取得方式、巢狀的 `Merge Request Parameter` 查詢條件群組，以及 Merge Request 表格。

#### Scenario: 顯示功能畫面

- **WHEN** 使用者切換到 AI Analysis GitLab MR
- **THEN** 左欄顯示 AI Mode、Analysis Parameter、Repository 三個群組
- **AND** 右欄顯示 Merge Requests 群組
- **AND** 右下角顯示 AI Analysis 按鈕

### Requirement: 進入功能不執行任何腳本

進入本功能（切換到本分頁，或啟動時本分頁即為當前分頁）SHALL NOT 啟動任何腳本。

Repository 清單 SHALL 於功能建立時自設定檔填入。Merge Request 表格 SHALL 保持在「尚未取得」的狀態，直到使用者按下重新整理。

理由：本功能的每一次載入都是一次對外部服務的請求。若比照「進入即載入」，使用者每次切換到這個分頁都會被一個應用程式互斥的處理中對話框擋住並等待網路回應。

#### Scenario: 切換到本功能

- **WHEN** 使用者從其他功能切換到本功能
- **THEN** 沒有任何腳本被啟動，也沒有處理中對話框出現
- **AND** Repository 清單已填入設定檔中的項目

#### Scenario: 啟動時本功能即為當前分頁

- **WHEN** 應用程式啟動且本功能是當前分頁
- **THEN** Repository 清單已填入，Merge Request 表格顯示尚未取得的提示
- **AND** 沒有任何腳本被啟動

### Requirement: Repository 清單

Repository 清單 SHALL 列出功能設定中 `Repo_List` 的所有項目，每項為 `namespace/project` 形式的字串，並以該字串原樣顯示。

清單 SHALL 為單選。

`Repo_List` 不存在或為空時，清單 SHALL 為空，MUST NOT 視為錯誤，也 MUST NOT 顯示訊息框。

#### Scenario: 顯示設定中的 repository

- **WHEN** 設定的 `Repo_List` 含兩個項目
- **THEN** 清單顯示這兩個項目，內容與設定完全相同

#### Scenario: 單選

- **WHEN** 使用者已選取一個 repository，接著點選另一個
- **THEN** 只有後者處於選取狀態

#### Scenario: 設定中沒有 repository

- **WHEN** 設定中沒有 `Repo_List` 或其為空陣列
- **THEN** 清單為空
- **AND** 不顯示任何訊息框

### Requirement: Merge Request 的兩種取得方式互斥

`Merge Requests` 群組 SHALL 提供兩個互斥的取得方式：手動輸入 Merge Request 編號，或依查詢條件取得清單。

選定其中一種時，另一種所屬的所有控件 SHALL 為停用狀態。

#### Scenario: 選擇取得清單

- **WHEN** 使用者選擇依查詢條件取得清單
- **THEN** 手動輸入編號的輸入框為停用狀態
- **AND** 查詢條件群組、重新整理鈕與表格皆可操作

#### Scenario: 選擇手動輸入

- **WHEN** 使用者選擇手動輸入 Merge Request 編號
- **THEN** 輸入框可編輯
- **AND** 查詢條件群組、重新整理鈕與表格皆為停用狀態

### Requirement: 手動輸入的 Merge Request 編號

手動輸入的編號 SHALL 只接受數字。

貼上以 `!` 開頭的字串或一整條 Merge Request 網址時，SHALL 自其中取出編號，MUST NOT 直接拒絕。

理由：使用者最自然的動作是從瀏覽器複製，完全擋死只會逼他們手動刪字。

#### Scenario: 輸入數字

- **WHEN** 使用者輸入 `123`
- **THEN** 輸入框接受該值

#### Scenario: 貼上含驚嘆號的編號

- **WHEN** 使用者貼上 `!123`
- **THEN** 輸入框的內容成為 `123`

#### Scenario: 貼上完整網址

- **WHEN** 使用者貼上一條指向某個 Merge Request 的網址
- **THEN** 輸入框的內容成為該 Merge Request 的編號

#### Scenario: 輸入非數字

- **WHEN** 使用者鍵入字母
- **THEN** 輸入框不接受該字元

### Requirement: Merge Request 的查詢條件

查詢條件 SHALL 包含「只取尚未關閉的」與「只取指定天數內建立的」兩個可各自開關的條件，天數 SHALL 以數值輸入控件呈現，範圍 1 至 365，預設 7。

理由：以純文字輸入框承載天數會讓負數、零、空字串與超大值各自需要一段檢查；數值輸入控件免費處理掉全部。

#### Scenario: 天數的範圍

- **WHEN** 使用者嘗試把天數設為 0 或大於 365 的值
- **THEN** 控件不接受該值

#### Scenario: 預設值

- **WHEN** 使用者第一次進入本功能
- **THEN** 兩個條件皆為開啟，天數為 7

### Requirement: 取得 Merge Request 清單

按下重新整理 SHALL 以目前選取的 repository 與查詢條件執行取得清單的腳本。

未選取 repository 時，重新整理 SHALL 為停用狀態。

腳本成功時 SHALL 以回傳的資料一次填入表格；失敗時表格 SHALL 被清空並顯示錯誤訊息說明原因。

取得到零筆 SHALL 視為成功而非失敗：表格為空，MUST NOT 顯示錯誤訊息框。

#### Scenario: 成功取得

- **WHEN** 使用者選取 repository 後按下重新整理，腳本成功回傳三筆
- **THEN** 表格顯示這三筆
- **AND** 不顯示任何訊息框

#### Scenario: 沒有符合條件的結果

- **WHEN** 腳本成功回傳零筆
- **THEN** 表格為空並顯示「沒有符合條件」的提示
- **AND** 不顯示錯誤訊息框

#### Scenario: 取得失敗

- **WHEN** 腳本回報失敗
- **THEN** 表格被清空
- **AND** 顯示錯誤訊息說明腳本回報的原因

#### Scenario: 未選取 repository

- **WHEN** Repository 清單沒有任何項目處於選取狀態
- **THEN** 重新整理鈕為停用狀態

### Requirement: Merge Request 表格

表格 SHALL 有五個欄位：編號、標題、作者、建立日期、狀態。MUST NOT 有 repository 欄 —— 表格的內容一律屬於當前選取的那一個 repository。

標題欄 SHALL 為唯一會隨視窗寬度伸縮的欄位，其餘四欄寬度固定。標題過長時 SHALL 截斷顯示，並以整列的提示文字提供完整標題。

建立日期 SHALL 以絕對日期顯示，排序 SHALL 依該日期的實際先後。

表格 SHALL 為單選。

表格 SHALL 區分兩種空白狀態：尚未取得，以及已取得但沒有符合條件的結果。

理由：兩種空白在畫面上完全相同，但使用者該採取的下一步不同 —— 前者要按重新整理，後者要放寬條件。

#### Scenario: 標題欄取得剩餘寬度

- **WHEN** 表格顯示資料
- **THEN** 編號、作者、建立日期、狀態四欄為固定寬度
- **AND** 標題欄佔用其餘的全部寬度

#### Scenario: 標題過長

- **WHEN** 某筆的標題長度超過標題欄的寬度
- **THEN** 顯示的標題被截斷
- **AND** 該列提供完整標題的提示文字

#### Scenario: 兩種空白狀態可區分

- **WHEN** 使用者尚未按下重新整理
- **THEN** 表格顯示「尚未取得」的提示
- **AND** 該提示與「沒有符合條件」的提示不同

#### Scenario: 單選

- **WHEN** 使用者已選取一筆，接著點選另一筆
- **THEN** 只有後者處於選取狀態

### Requirement: 清單於條件改變後失效

切換 repository，或改動任何一項查詢條件，SHALL 清空 Merge Request 表格並使其回到「尚未取得」的狀態。

理由：清單的內容屬於取得它時的那一組條件。若保留，畫面上顯示的會是前一個 repository 的 Merge Request，而按下 AI Analysis 時採用的卻是當前選取的 repository。

#### Scenario: 切換 repository

- **WHEN** 使用者已取得 repository A 的清單並選取其中一筆，接著改選 repository B
- **THEN** 表格被清空並顯示「尚未取得」的提示
- **AND** `AI Analysis` 變為停用

#### Scenario: 改動查詢條件

- **WHEN** 使用者已取得清單，接著改動天數
- **THEN** 表格被清空並顯示「尚未取得」的提示

### Requirement: AI Mode 選單

`AI Mode` 下拉選單 SHALL 列出設定中 `AI_Mode_List` 每一項的 `Name`，順序與設定相同，預設選取第一項。

外殼與功能 MUST NOT 在畫面上呈現該項目的其他欄位（端點、金鑰、模型名）。

`AI_Mode_List` 不存在或為空時，選單 SHALL 為空。

#### Scenario: 列出設定中的模式

- **WHEN** 設定的 `AI_Mode_List` 含一項且其 `Name` 為 `Open AI`
- **THEN** 選單顯示 `Open AI` 且為選取狀態

#### Scenario: 順序即預設

- **WHEN** 設定的 `AI_Mode_List` 含多項
- **THEN** 選單的順序與設定相同
- **AND** 預設選取第一項

### Requirement: 除錯分析檔的開關與存放目錄

`Analysis Parameter` 群組的除錯分析檔勾選方塊 SHALL 決定本次分析是否產生任何檔案。

未勾選時，存放目錄的標籤、輸入框與瀏覽鈕 SHALL 一併為停用狀態。

存放目錄的初始值 SHALL 取自功能設定，瀏覽鈕 SHALL 開啟目錄選擇對話框。

#### Scenario: 未勾選時停用整列

- **WHEN** 使用者取消勾選除錯分析檔
- **THEN** 存放目錄的輸入框與瀏覽鈕皆為停用狀態

#### Scenario: 初始值來自設定

- **WHEN** 使用者第一次進入本功能，而設定中的存放目錄有值
- **THEN** 輸入框顯示該值

### Requirement: JIRA Key 的三種模式

`JIRA Key` 群組 SHALL 提供三個互斥的模式：不使用、手動指定、自動取得。預設 SHALL 為自動取得。

只有選擇手動指定時，其輸入框 SHALL 可編輯；其餘模式下 SHALL 為停用狀態。

模式、手動輸入的值、以及流程中取得的值 SHALL 一併傳給分析步驟，由腳本決定最終採用哪一個。功能 MUST NOT 在 Qt 端先行決定。

理由：若在 Qt 端解析這三種模式，以命令列或持續整合呼叫同一批腳本時就必須重寫一次相同的判斷，兩份實作必然漂移。

#### Scenario: 預設為自動

- **WHEN** 使用者第一次進入本功能
- **THEN** JIRA Key 的模式為自動取得
- **AND** 手動輸入框為停用狀態

#### Scenario: 手動模式才可編輯

- **WHEN** 使用者選擇手動指定
- **THEN** 輸入框可編輯

#### Scenario: 三個值一併傳入

- **WHEN** 使用者以自動模式執行分析
- **THEN** 分析步驟收到的參數同時包含模式、手動輸入的值與流程中取得的值
- **AND** Qt 端沒有依模式挑選其中之一

### Requirement: AI Analysis 的啟用條件

`AI Analysis` SHALL 只在下列條件全部成立時為啟用狀態：已選取一個 repository；已指定一個 Merge Request（手動輸入的編號非空，或表格中已選取一筆）；勾選除錯分析檔時存放目錄非空；選擇手動指定 JIRA Key 時其輸入框非空。

停用時 MUST NOT 顯示任何說明原因的提示文字或提示框。

理由：與既有功能的作法一致。已知代價是使用者無從得知缺少什麼，緩解方式是讓範本設定檔提供可用的預設值。

#### Scenario: 條件齊備

- **WHEN** 使用者選取了 repository 與一筆 Merge Request，且其餘條件皆滿足
- **THEN** `AI Analysis` 為啟用狀態

#### Scenario: 未選取 Merge Request

- **WHEN** 使用者選取了 repository 但表格中沒有任何一筆處於選取狀態
- **THEN** `AI Analysis` 為停用狀態

#### Scenario: 勾選除錯但存放目錄為空

- **WHEN** 除錯分析檔為勾選狀態而存放目錄為空
- **THEN** `AI Analysis` 為停用狀態
- **AND** 畫面上沒有任何說明原因的文字

### Requirement: 除錯輸出目錄於流程啟動前建立

勾選除錯分析檔時，功能 SHALL 在流程啟動之前建立一個目錄，其位置為存放目錄之下、名稱含 repository、Merge Request 編號與時間戳記。

該目錄的絕對路徑 SHALL 傳入流程的每一個步驟。未勾選時 SHALL 傳入空字串，腳本據此不產生任何檔案。

目錄建立失敗時 SHALL 顯示錯誤訊息框，且流程 MUST NOT 啟動。

理由：以同一個參數承載「寫到哪裡」與「要不要寫」，就不會出現「開關為真但路徑為空」的矛盾狀態。在流程啟動前建立，則使路徑錯誤或權限不足在任何工作開始之前就被發現，而不是在耗費了時間與外部服務的費用之後才失敗。

時間戳記 SHALL 只產生一次，使所有步驟寫入同一個目錄。

#### Scenario: 勾選時建立目錄

- **WHEN** 使用者勾選除錯分析檔並按下 `AI Analysis`
- **THEN** 在存放目錄之下建立一個含 repository、Merge Request 編號與時間戳記的目錄
- **AND** 每一個步驟收到的參數都含有該目錄的絕對路徑

#### Scenario: 未勾選時不建立

- **WHEN** 使用者未勾選除錯分析檔並按下 `AI Analysis`
- **THEN** 沒有任何目錄被建立
- **AND** 每一個步驟收到的該參數為空字串

#### Scenario: 目錄建立失敗

- **WHEN** 存放目錄指向一個無法寫入的位置
- **THEN** 顯示錯誤訊息框
- **AND** 沒有任何腳本被啟動

#### Scenario: 所有步驟寫入同一個目錄

- **WHEN** 一次分析的五個步驟都產生檔案
- **THEN** 五個步驟的檔案位於同一個目錄中

### Requirement: 分析流程的組成

按下 `AI Analysis` SHALL 啟動一條固定五步的流程，依序為：取得 Merge Request 描述、取得相關資訊、AI 分析、取得程式碼審閱報告、合併為 markdown。

五個步驟 SHALL 全部執行，MUST NOT 由 Qt 端依條件跳過任何一步。「是否真的執行工作」SHALL 由該步的腳本依收到的參數自行決定，不執行工作時 SHALL 回傳空結果並回報成功。

各步驟的腳本路徑 SHALL 固定，MUST NOT 取自任何步驟的回傳資料。

理由：同一批腳本必須能被持續整合以相同順序直接呼叫。若分支判斷寫在 Qt 端，持續整合那一側就成為第二份編排實作，兩份必然漂移；把判斷壓進腳本後，兩邊都只是固定順序的線性呼叫，判斷邏輯只有一份。

#### Scenario: 五步依序執行

- **WHEN** 使用者按下 `AI Analysis` 且每一步皆成功
- **THEN** 五個步驟依序各執行一次
- **AND** 同一時刻沒有一支以上的腳本在執行

#### Scenario: 不需要工作的步驟仍被執行

- **WHEN** 取得程式碼審閱報告的參數指示不需要取得
- **THEN** 該步驟仍被啟動
- **AND** 它回傳空的報告內容並回報成功

#### Scenario: 腳本路徑不受回傳資料影響

- **WHEN** 取得相關資訊的步驟回傳的資料中含有處理方式的名稱與路徑
- **THEN** 後續步驟執行的仍是固定的腳本
- **AND** 該資料被原樣放入後續步驟的參數中，由腳本自行解讀

### Requirement: 流程步驟的參數組裝

功能 SHALL 依已完成步驟的結果組裝下一步的參數，且該組裝 MUST NOT 包含任何業務判斷 —— 只做挑選欄位、更名與轉送。

AI 模式的端點、金鑰與模型名 SHALL 經由參數傳入，MUST NOT 出現在命令列。

#### Scenario: 前一步的結果轉送至下一步

- **WHEN** 取得相關資訊的步驟成功結束
- **THEN** 其回傳的資料被原樣放入後續步驟的參數
- **AND** 功能沒有對該資料做任何解讀或分支

#### Scenario: AI 設定經由參數傳入

- **WHEN** AI 分析步驟被啟動
- **THEN** 選定模式的端點、金鑰與模型名出現在該步的參數中
- **AND** 不出現在行程的命令列上

### Requirement: 服務憑證經由環境變數傳遞

功能 SHALL 把設定中的 GitLab 與 JIRA 服務端點與存取權杖，注入為每一個步驟的環境變數，變數名為設定鍵名的全大寫形式。

腳本 SHALL 只從環境變數取用這些值，MUST NOT 自 `config` 取用。

理由：持續整合以相同名稱設定環境變數即可執行同一批腳本，腳本端因此只有一條取值路徑，兩個呼叫端對它而言完全相同。

腳本 MUST NOT 將整包 `config` 輸出至診斷訊息 —— 合併後的 `config` 仍含有這些權杖。

#### Scenario: 環境變數被注入

- **WHEN** 流程的任一步被啟動
- **THEN** 該行程的環境中含有 GitLab 與 JIRA 的服務端點與存取權杖

#### Scenario: 命令列不含憑證

- **WHEN** 流程的任一步被啟動
- **THEN** 該行程的命令列參數中不含任何權杖

#### Scenario: 以命令列直接執行

- **WHEN** 開發者在已設定相同環境變數的環境中直接執行其中一支腳本
- **THEN** 該腳本取得相同的服務端點與權杖
- **AND** 不需要在請求檔案中填入任何憑證

### Requirement: 腳本的輸出入雙軌

流程中每一支腳本的完整結果 SHALL 放在回應的 `data` 中。當參數指定了輸出路徑時，SHALL 額外寫出對應的檔案；未指定時 MUST NOT 寫出任何檔案。

每一支腳本 SHALL 同時接受兩種輸入形式：參數中直接帶入的內容，以及指向前一步產物的路徑。兩者皆提供時 SHALL 以內容為準。

寫出的中間產物 SHALL 以兩位數序號前綴命名，使目錄的列出順序即為流程的執行順序。

理由：圖形介面呼叫端不觸碰檔案系統，因此需要 `data`；持續整合以 shell 串接，檔案是它的原生形式。兩者皆支援使得同一批腳本服務兩個呼叫端，而協定本身是加法式的。

#### Scenario: 圖形介面呼叫時取得結果

- **WHEN** 流程的某一步成功結束
- **THEN** 其結果完整地存在於回應的 `data` 中
- **AND** 功能不需要開啟任何檔案即可取得該結果

#### Scenario: 未指定輸出路徑時不寫檔

- **WHEN** 使用者未勾選除錯分析檔而執行整條流程
- **THEN** 檔案系統中沒有任何檔案被建立或修改

#### Scenario: 以路徑作為輸入

- **WHEN** 開發者以命令列執行某一步，參數中只提供指向前一步產物的路徑
- **THEN** 該步讀取該檔案作為輸入並正常執行

#### Scenario: 中間產物的命名

- **WHEN** 使用者勾選除錯分析檔而執行整條流程
- **THEN** 目錄中的檔案帶有兩位數序號前綴
- **AND** 依檔名排序的順序即為五個步驟的執行順序

### Requirement: 失敗即結束流程

流程中任一步回報失敗時，功能 SHALL 結束整條流程，MUST NOT 執行後續步驟，也 MUST NOT 執行補救步驟。

流程結束後 SHALL 顯示一個錯誤訊息框，內容 SHALL 指出失敗發生在第幾步，並包含該步腳本回報的原因。

畫面上的任何元素 MUST NOT 因此改變。

#### Scenario: 第三步失敗

- **WHEN** 流程的第三步回報失敗
- **THEN** 第四、第五步不被啟動
- **AND** 顯示一個錯誤訊息框，指出第三步失敗與該步回報的原因
- **AND** Repository 清單與 Merge Request 表格的內容不變

#### Scenario: 啟動前失敗

- **WHEN** 某一步的腳本檔案不存在
- **THEN** 顯示錯誤訊息框指出該腳本路徑
- **AND** 流程結束，畫面不變

### Requirement: 結果呈現

流程的所有步驟皆成功時，功能 SHALL 以結果視窗顯示最後一步回傳的 markdown 內容，並附上整條流程的耗時。

顯示的內容 SHALL 取自回應的 `data`，功能 MUST NOT 為此開啟任何檔案。

#### Scenario: 成功後顯示結果

- **WHEN** 流程的五個步驟皆成功
- **THEN** 結果視窗顯示最後一步回傳的 markdown 內容與整條流程的耗時

#### Scenario: 未勾選除錯時仍能看到結果

- **WHEN** 使用者未勾選除錯分析檔而執行整條流程且全部成功
- **THEN** 結果視窗仍顯示完整的 markdown 內容
- **AND** 沒有任何檔案被建立

#### Scenario: 取消後畫面不變

- **WHEN** 使用者在流程執行中按下取消
- **THEN** 不顯示結果視窗，也不顯示錯誤訊息框
- **AND** 畫面上沒有任何元素改變

### Requirement: 取得 Merge Request 清單為真實實作

取得 Merge Request 清單的腳本 SHALL 真的連線至設定的 GitLab 伺服器並取回實際的 Merge Request。

專案 SHALL 以 `namespace/project` 字串識別，腳本 SHALL 對其做 URL 編碼後再組成請求。

畫面上的查詢條件 SHALL 對應到實際的查詢參數：只取尚未關閉的、以及只取指定天數內建立的。

憑證無效與專案不存在 SHALL 給出彼此不同且可行動的失敗訊息：前者 SHALL 指向存取權杖所在的環境變數，後者 SHALL 指向設定中的專案名稱。

理由：兩者的使用者下一步完全不同 —— 一個要去換權杖，一個要去改設定檔的拼字。給同一句「取得失敗」等於要使用者自己猜。

單次取回的筆數 SHALL 以 100 筆為上限，MUST NOT 跟著分頁連結往下翻。取回筆數達到上限時 SHALL 讓使用者知道結果可能未完整。

理由：表格是單選的，使用者要從中挑出一筆。取回上千筆不會讓那個動作更容易，只會讓等待變長、讓表格更難掃；範圍過大時正確的操作是調緊查詢條件。

HTTPS 連線的憑證驗證 SHALL 由設定中的一個開關控制，未設定時 SHALL 視為**不驗證**。

此預設值是明確的取捨：目標環境是否使用自簽憑證尚不確定，而驗證失敗會使功能完全無法使用。代價是關閉驗證時存取權杖會暴露於連線中間人，且被攔截時沒有任何徵兆。

驗證為開啟且憑證無法通過驗證時，錯誤訊息 SHALL 指出可將受信任的 CA 憑證指給對應的環境變數，或關閉該設定開關。

該開關 MUST NOT 寫死在程式碼中 —— 它必須在設定檔中看得見，且可逐台機器調整。

GitLab REST 的呼叫 SHALL 置於共用模組的 GitLab 分組中，並遵守共用模組的既有規則；存取權杖 SHALL 由入口腳本自環境變數取出後明著傳入。

#### Scenario: 取回實際的 Merge Request

- **WHEN** 使用者選取一個確實存在的 repository 並按下重新整理，而環境中的存取權杖有效
- **THEN** 表格顯示該專案實際的 Merge Request
- **AND** 顯示的編號、標題、作者、建立日期與狀態來自 GitLab 的回應

#### Scenario: 專案名稱含斜線

- **WHEN** 選取的 repository 為 `namespace/project` 形式
- **THEN** 請求中的專案識別為該字串的 URL 編碼形式
- **AND** 請求成功

#### Scenario: 查詢條件生效

- **WHEN** 使用者開啟「只取尚未關閉的」並將天數設為 7
- **THEN** 取回的內容不含已關閉或已合併的 Merge Request
- **AND** 不含建立於 7 天之前的 Merge Request

#### Scenario: 存取權杖無效

- **WHEN** 環境中的存取權杖無效或未設定
- **THEN** 表格被清空
- **AND** 錯誤訊息指出存取權杖的問題並點名該環境變數

#### Scenario: 專案不存在

- **WHEN** 設定中的專案名稱在伺服器上不存在
- **THEN** 表格被清空
- **AND** 錯誤訊息指出找不到該專案並點名設定中的專案名稱
- **AND** 該訊息與存取權杖無效時的訊息不同

#### Scenario: 取回筆數達到上限

- **WHEN** 符合查詢條件的 Merge Request 超過 100 筆
- **THEN** 表格顯示 100 筆
- **AND** 使用者被告知結果可能未完整
- **AND** 腳本沒有為了取回其餘筆數而發出額外的請求

#### Scenario: 未設定驗證開關時連上自簽憑證的伺服器

- **WHEN** 設定中沒有驗證開關，而伺服器使用自簽憑證
- **THEN** 請求成功
- **AND** 表格顯示取回的 Merge Request

#### Scenario: 明確開啟驗證且憑證無法通過

- **WHEN** 設定中的開關被設為開啟驗證，而伺服器的憑證無法通過驗證
- **THEN** 表格被清空
- **AND** 錯誤訊息指出可指定受信任的 CA 憑證，或關閉該設定開關

### Requirement: 分析流程五步本次以假資料實作

分析流程五個步驟的腳本 SHALL 完整實作對外契約：標準輸出只有一個結果 JSON、診斷與進度走錯誤輸出、結束碼、參數與設定鍵的宣告、必填檢查、設定模板傾印、以及標準輸入與檔案兩種投遞方式。

這五支的業務運算本次 SHALL 以固定的假資料實作，MUST NOT 連線至 GitLab、AI 供應商或 JIRA。真實的連線實作屬於後續變更。

本能力的每一支腳本 SHALL 自功能腳本範本複製後改寫。

#### Scenario: 契約可被獨立驗證

- **WHEN** 開發者對本能力的任一支腳本執行說明、傾印模板、檔案投遞與標準輸入投遞
- **THEN** 四種操作都成功
- **AND** 兩種投遞方式都回傳 `result` 為 `PASS` 的結果

#### Scenario: 不需要 AI 金鑰即可跑完整條流程

- **WHEN** 使用者在沒有任何 AI 金鑰的環境中指定一個 Merge Request 並按下 `AI Analysis`
- **THEN** 五個步驟皆成功
- **AND** 結果視窗顯示由假資料組成的 markdown

#### Scenario: 腳本自範本複製

- **WHEN** 檢視任一支新增的腳本
- **THEN** 它保有範本的版本號常數
- **AND** 它保有範本中設定模組搜尋路徑的那一段，因此可在未設定任何模組搜尋路徑的情況下直接執行
