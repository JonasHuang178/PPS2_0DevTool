## Purpose

應用程式外殼提供功能（tab）賴以存在的共同基礎：工具層級設定的讀取與查詢、功能掛勾訊號、除錯輸出、共用 UI 服務，以及視窗與啟動行為。外殼本身不含任何業務邏輯，它的職責是讓功能能被安全地一個一個加進來。

## Requirements

### Requirement: 工具層級設定讀取

外殼 SHALL 從設定檔 `PPS2_0DevTool.json`（根鍵 `PPS2_0DevTool`）只讀取三個工具層級欄位：`Debug_Mode`、`User_Guide_Link`、`Function`。

`Function` 物件 MUST NOT 被逐欄位解析，它 SHALL 以未解析的原始物件形式保留，供功能自行取用。

布林值在設定檔中 SHALL 以字串 `"true"` / `"false"` 表示。

#### Scenario: 讀取工具層級欄位

- **WHEN** 應用程式啟動且設定檔存在且格式正確
- **THEN** `Debug_Mode`、`User_Guide_Link` 被讀入，`Function` 整包以原始物件保留
- **AND** `Function` 底下各功能區塊的任何欄位都未被外殼解讀

#### Scenario: 新增功能不需修改設定讀取

- **WHEN** 開發者在 `Function` 底下新增一個功能區塊，內含該功能自訂的任意鍵
- **THEN** 設定讀取模組不需要任何修改
- **AND** 該功能可透過設定查詢介面取得自己的完整區塊

### Requirement: 功能設定查詢介面

外殼 SHALL 提供兩個查詢介面供功能使用：取得指定功能的完整設定區塊，以及查詢指定功能是否應顯示。

取得設定區塊時，若該功能名稱在 `Function` 底下不存在，SHALL 回傳空物件而非錯誤 —— 缺漏的必填設定由腳本層的必填檢查負責回報。

#### Scenario: 取得存在的功能設定

- **WHEN** 功能以自己的名稱查詢設定
- **THEN** 回傳該名稱在 `Function` 底下的完整物件，包含所有自訂鍵

#### Scenario: 取得不存在的功能設定

- **WHEN** 功能以一個 `Function` 底下不存在的名稱查詢設定
- **THEN** 回傳空物件
- **AND** 不中止程式、不跳訊息框

### Requirement: 功能顯示與否

外殼 SHALL 依據功能設定區塊中的 `Visible` 鍵決定該功能的 tab 是否保留。`Visible` 的值不是字串 `"true"` 時，該 tab SHALL 被移除。

當功能區塊不存在、或區塊中沒有 `Visible` 鍵時，SHALL 視為不顯示，並記錄一筆警告說明原因。

#### Scenario: 明確設為顯示

- **WHEN** 功能區塊的 `Visible` 為 `"true"`
- **THEN** 該功能的 tab 保留在畫面上

#### Scenario: 明確設為隱藏

- **WHEN** 功能區塊的 `Visible` 為 `"false"` 或其他非 `"true"` 的值
- **THEN** 該功能的 tab 被移除

#### Scenario: 未設定 Visible

- **WHEN** 功能區塊不存在，或存在但沒有 `Visible` 鍵
- **THEN** 該功能的 tab 被移除
- **AND** 記錄一筆警告，指出該功能未設定 `Visible` 因此預設隱藏

### Requirement: 設定檔缺失或損毀時中止啟動

當設定檔不存在、無法讀取、或不是合法 JSON 時，外殼 SHALL 顯示錯誤訊息框說明原因，並在使用者確認後結束程式。

理由：每個功能區塊都必須提供執行 Python 的指令，沒有設定檔時所有功能都無法運作，讓程式帶著空設定啟動只會讓使用者在每個 tab 都撞牆。

#### Scenario: 設定檔不存在

- **WHEN** 應用程式啟動時找不到設定檔
- **THEN** 顯示錯誤訊息框指出設定檔路徑
- **AND** 使用者確認後程式結束

#### Scenario: 設定檔格式錯誤

- **WHEN** 設定檔存在但不是合法 JSON
- **THEN** 顯示錯誤訊息框指出解析失敗的原因
- **AND** 使用者確認後程式結束

### Requirement: 功能掛勾訊號

外殼 SHALL 提供兩個訊號作為功能唯一的掛勾點：來源路徑變更、以及工作資料被清空。

不需要來源路徑的功能 SHALL 可以不連接任何訊號而正常運作。

#### Scenario: 來源路徑變更

- **WHEN** 使用者變更來源路徑
- **THEN** 外殼發出來源路徑變更訊號，並附帶新的路徑
- **AND** 已連接的功能各自重新載入自己的內容

#### Scenario: 工作資料清空

- **WHEN** 外殼需要各功能清空自己的畫面
- **THEN** 外殼發出工作資料清空訊號
- **AND** 已連接的功能各自清空自己的畫面

### Requirement: 除錯輸出與 Debug console

外殼 SHALL 提供三個等級的診斷輸出（DEBUG / WARN / ERROR），輸出內容 SHALL 同時寫入一個容量 300 行的環形緩衝區。

當 `Debug_Mode` 為 true 時，外殼 SHALL 開啟一個 console 視窗顯示這些輸出，且 console 的輸出編碼 SHALL 為 UTF-8。

外殼讀取腳本的錯誤輸出時 SHALL 一律以 UTF-8 解碼，MUST NOT 使用系統地區編碼。

Qt 與腳本的訊息會混在同一個 console，兩邊格式 SHALL 對齊：時間戳記含毫秒，等級名稱補成固定寬度。

#### Scenario: Debug_Mode 開啟

- **WHEN** `Debug_Mode` 為 true 且應用程式啟動
- **THEN** console 視窗開啟
- **AND** Qt 端與腳本端的訊息都出現在該視窗，格式對齊

#### Scenario: 中文訊息不亂碼

- **WHEN** 腳本輸出含中文的診斷訊息，而作業系統的地區編碼不是 UTF-8
- **THEN** console 上顯示的中文正確無誤

#### Scenario: Debug_Mode 關閉

- **WHEN** `Debug_Mode` 為 false
- **THEN** 不開啟 console 視窗
- **AND** 診斷訊息不輸出到任何可見位置

### Requirement: 關閉 Debug console 即結束程式

console 視窗的關閉鈕 SHALL 保持可用。使用者關閉 console 時，整個應用程式 SHALL 結束。

結束前，若當下有腳本正在執行，外殼 SHALL 先終止該子行程，避免留下孤兒行程。

#### Scenario: 執行中關閉 console

- **WHEN** 有腳本正在執行，使用者關閉 console 視窗
- **THEN** 該腳本的子行程被終止
- **AND** 應用程式結束，系統中沒有殘留的子行程

#### Scenario: 閒置時關閉 console

- **WHEN** 沒有腳本在執行，使用者關閉 console 視窗
- **THEN** 應用程式結束

### Requirement: 共用 UI 服務

外殼 SHALL 提供以下共用服務供所有功能使用：統一樣式的資訊／警告／錯誤訊息框、統一樣式的結果視窗（標題、內容、耗時）、取得目前來源路徑、依標題移除 tab、以及耗時格式化（形如 `01h 23m 45s`）。

#### Scenario: 功能顯示結果

- **WHEN** 功能取得腳本結果並選擇以結果視窗呈現
- **THEN** 結果視窗以統一樣式顯示標題、內容與耗時

### Requirement: 視窗與啟動行為

主視窗 SHALL 為固定尺寸 1200x830。

關閉主視窗 SHALL 隱藏至系統匣而非結束程式；系統匣圖示被啟動（雙擊，或在只送出單擊事件的平台上以單擊）SHALL 還原視窗，其右鍵選單 SHALL 只提供結束。

About 對話框 SHALL 顯示工具名稱、版本、Qt 版本、建置日期與使用手冊連結。工具版本 SHALL 為 `v2.0.0`。

啟動時 SHALL 檢查系統上有可用的 Python 3，並以單一實例鎖確保同時只有一個實例執行；程式因記憶體區段錯誤而崩潰時 SHALL 輸出 crash log。

#### Scenario: 關閉主視窗

- **WHEN** 使用者關閉主視窗
- **THEN** 視窗隱藏至系統匣，程式繼續執行

#### Scenario: 從系統匣還原

- **WHEN** 使用者雙擊系統匣圖示
- **THEN** 主視窗還原顯示並取得焦點

#### Scenario: 單擊即為啟動的平台

- **WHEN** 平台對系統匣圖示只送出單擊事件，使用者單擊該圖示
- **THEN** 主視窗還原顯示並取得焦點

#### Scenario: 重複啟動

- **WHEN** 應用程式已在執行，使用者再次啟動它
- **THEN** 第二個實例不會啟動

#### Scenario: 缺少 Python 3

- **WHEN** 應用程式啟動且系統上找不到可用的 Python 3
- **THEN** 顯示錯誤訊息說明缺少 Python 3

### Requirement: 啟動時不含任何功能

本次交付的外殼 SHALL 不包含任何功能 tab。tab widget SHALL 為空，設定檔的 `Function` 物件 SHALL 為空物件。

#### Scenario: 空的外殼啟動

- **WHEN** 應用程式以預設設定檔啟動
- **THEN** 主視窗顯示來源路徑列、空的 tab widget 與進度條
- **AND** 沒有任何功能 tab
