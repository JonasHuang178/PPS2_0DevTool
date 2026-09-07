## Why

v2.0.0 的外殼已經完成，但沒有任何功能 tab —— 框架與腳本執行管線都還沒有被真實的功能走過一遍。Single Building 是第一個功能：使用者從來源目錄挑出要處理的 `.cpp` 檔案，把選擇存成一份設定，之後可以修改或清空它。

這個功能同時會補上外殼交付時延後的兩項驗收（關閉 Debug console 時清理子行程、Qt 與 Python 的訊息同時出現在 console 中）—— 那兩項當初就是因為「空外殼沒有觸發腳本的入口」而無法驗證。

同時暴露出一個外殼層級的缺口：來源路徑目前是所有功能共用的單一值。使用者為了某個 tab 改路徑，其他 tab 的內容就跟著被牽動。功能之間應該互相獨立，來源路徑也該如此。

## What Changes

### 新增 Single Building 功能 tab

- 左右兩個清單的挑選介面：Source（來源池，唯讀）與 Target（結果集），中間以 `->` / `<-` 搬移
- Source 具備即時過濾（區分大小寫的子字串比對）
- 兩個清單皆為自然排序（數字依數值比較）、不區分大小寫
- 右下角兩個動作按鈕：Recovery Setting、Modify Setting

### 新增四支 Python 腳本

四支皆由 `scripts/_function_template.py` 複製而來，業務邏輯放在 `script_utils/` 共用：

| 腳本 | 職責 |
|---|---|
| 列出來源 | 掃描來源目錄該層的 `.cpp`（不遞迴），回傳檔名與絕對路徑 |
| 讀取設定 | 讀暫存 txt，回傳其中的絕對路徑 |
| 寫入設定 | 把 Target 的內容寫進暫存 txt |
| 清空設定 | 清空暫存 txt 後回讀（結果必為空） |

暫存 txt 位於系統暫存目錄（Windows 上是 `%TEMP%`），內容為絕對路徑，一行一筆。它是這個功能唯一的狀態儲存處，重開機後消失是預期行為。

### **BREAKING** 外殼的來源路徑改為每個功能各自保有

- 外殼為每個功能保存各自的來源路徑；切換 tab 時，共用的來源路徑欄位顯示該功能的路徑
- 在某個功能中修改來源路徑，只有該功能反應，其他功能不受影響
- 切換 tab 時還原路徑不視為「變更」，不觸發任何功能的重新載入
- **BREAKING**：來源路徑變更訊號從「廣播給所有功能、各自重新載入」改為「只有路徑所屬的功能反應」。目前沒有任何功能連接此訊號，實際衝擊為零

## Capabilities

### New Capabilities

- `single-building`: Single Building 功能 tab 的完整行為 —— 兩個清單的挑選與過濾介面、四支腳本的觸發時機與串接、暫存設定檔的讀寫、失敗與取消的處理

### Modified Capabilities

- `app-shell`: 「功能掛勾訊號」需求變更 —— 來源路徑從全域共用改為每個功能各自保有，並釐清「使用者修改」與「切換 tab 還原」的差別。「啟動時不含任何功能」需求隨第一個功能 tab 的加入而失效

## Impact

### 程式碼

- `pps2_0devtool.{h,cpp,ui}` —— 新增 tab、每個功能的來源路徑保存、訊號語意調整
- 新增 `SingleBuilding.{h,cpp}` —— 功能本體
- `PPS2_0DevTool.pro` —— 新檔案加入 SOURCES / HEADERS
- `PPS2_0DevTool.json` —— `Function` 底下新增 `Single Building` 區塊

### 腳本

- `scripts/` 新增四支入口腳本
- `scripts/script_utils/` 新增 Single Building 的業務邏輯模組

### 不受影響

- `json.cpp`（設定讀取不需修改，`Function` 以原始物件保留）
- `PythonRunner`、`ProcessingDialog`、`debug`、`common`
