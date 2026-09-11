## MODIFIED Requirements

### Requirement: 目錄結構

入口腳本 SHALL 依功能分組，放在 `scripts/<功能>/` 之下。

入口腳本 SHALL 自行確保 `scripts/` 根目錄位於模組搜尋路徑中，不論它被放在第幾層，且 MUST NOT 依賴呼叫端設定 `PYTHONPATH`。

理由：Qt 這條管線會注入指向 `scripts/` 的 `PYTHONPATH`，但命令列與持續整合直接執行腳本時沒有那個環境。共用模組的匯入必須在兩種情境下都成立，因此可匯入性是入口腳本自己的責任，而不是「腳本只准放在特定深度」的限制。

所有共用模組 SHALL 放在 `scripts/script_utils/` 之下，並 SHALL 依技術領域分組（例如系統層面的共用能力、GitLab REST 的共用能力）。

共用模組的分組 SHALL 依技術領域劃分，MUST NOT 依應用功能劃分 —— 只服務單一功能的邏輯不屬於共用模組層。

診斷輸出 SHALL 由 `script_utils` 之下單一的 log 模組提供，供所有共用模組與入口腳本使用。

信封處理層 SHALL 放在 `script_utils/` 之外，因為它是這條呼叫管線專用的元件，而非通用工具。

範本檔案 SHALL 以底線開頭，與真正的入口腳本區隔，並 SHALL 留在 `scripts/` 這一層，不歸屬於任何功能。

#### Scenario: 直接執行入口腳本

- **WHEN** 使用者在未設定任何模組搜尋路徑的情況下直接執行功能目錄底下的入口腳本
- **THEN** 共用模組的匯入成功

#### Scenario: 入口腳本依功能分組

- **WHEN** 開發者為某個功能新增入口腳本
- **THEN** 該腳本放在以該功能命名的目錄之下
- **AND** 同一個功能的多支入口腳本位於同一個目錄

#### Scenario: 共用模組依技術領域分組

- **WHEN** 開發者新增一個服務多個功能的共用能力
- **THEN** 該能力放進 `script_utils/` 底下對應技術領域的分組
- **AND** 不會為單一應用功能在 `script_utils/` 底下建立分組

#### Scenario: 透過 Qt 執行時亦不依賴注入的搜尋路徑

- **WHEN** 入口腳本由 Qt 以注入 `PYTHONPATH` 的方式啟動
- **THEN** 共用模組的匯入成功
- **AND** 該成功不依賴注入的 `PYTHONPATH`，移除它之後匯入仍然成立
