## Purpose

Single Building 讓使用者從來源目錄中挑出要處理的 `.cpp` 檔案，把選擇保存成一份設定，並可隨時修改或清空它。它是本工具的第一個功能 tab，也是「Qt 只負責讓使用者選擇、業務邏輯全在 Python」這條原則的第一個實例。

## ADDED Requirements

### Requirement: 畫面配置

功能 tab 的標題 SHALL 為 `Single Building`，其設定區塊在設定檔中的鍵名 SHALL 與標題相同。

畫面 SHALL 由左右兩個群組與中間的搬移按鈕構成：左為 `Source`（來源池），右為 `Target`（結果集），中間上方為 `->`、下方為 `<-`。

`Source` 群組內 SHALL 於最上方提供過濾標籤、過濾文字框與一個清除鈕，其下為來源清單。

`Target` 群組內 SHALL 於右上方提供一個清除鈕，其下為結果清單。

主畫面右下角 SHALL 提供兩個動作按鈕，左為 `Recovery Setting`，右為 `Modify Setting`。

兩個清單 SHALL 支援以 Ctrl 與 Shift 進行多重選取。

#### Scenario: 顯示功能畫面

- **WHEN** 使用者切換到 Single Building
- **THEN** 畫面左側顯示 Source 群組（過濾列與來源清單），右側顯示 Target 群組（清除鈕與結果清單）
- **AND** 兩個群組之間顯示 `->` 與 `<-` 兩個按鈕
- **AND** 右下角顯示 Recovery Setting 與 Modify Setting

### Requirement: 清單項目的顯示與保存形式

兩個清單 SHALL 只顯示檔案名稱，MUST NOT 顯示完整路徑。

每個清單項目 SHALL 同時保有該檔案的絕對路徑；寫入與讀取設定時 SHALL 使用絕對路徑。

判斷項目是否重複 SHALL 依顯示的檔案名稱。

理由：完整路徑會撐爆清單寬度且前綴完全相同，難以閱讀；但設定必須指向確切的檔案，因此保存時使用絕對路徑。

#### Scenario: 清單顯示檔名

- **WHEN** 來源目錄為 `C:\proj\src` 且其中有 `main.cpp`
- **THEN** 來源清單顯示 `main.cpp`
- **AND** 不顯示 `C:\proj\src\main.cpp`

#### Scenario: 保存時使用絕對路徑

- **WHEN** 結果清單含 `main.cpp`，其來源目錄為 `C:\proj\src`，使用者寫入設定
- **THEN** 設定檔中保存的是 `C:\proj\src\main.cpp`

### Requirement: 清單排序

兩個清單 SHALL 永遠維持排序狀態，且 SHALL 在項目加入或移除後自動維持該狀態。

排序 SHALL 為自然排序：名稱中的數字段落依數值大小比較，而非逐字元比較。

排序 SHALL NOT 區分大小寫。

#### Scenario: 數字依數值排序

- **WHEN** 清單中含 `a1.cpp`、`a2.cpp`、`a10.cpp`
- **THEN** 顯示次序為 `a1.cpp`、`a2.cpp`、`a10.cpp`
- **AND** `a10.cpp` 不排在 `a2.cpp` 之前

#### Scenario: 大小寫不影響次序

- **WHEN** 清單中含 `Beta.cpp`、`alpha.cpp`、`Gamma.cpp`
- **THEN** 顯示次序為 `alpha.cpp`、`Beta.cpp`、`Gamma.cpp`

#### Scenario: 加入項目後仍維持排序

- **WHEN** 結果清單已含 `a1.cpp` 與 `a10.cpp`，使用者加入 `a2.cpp`
- **THEN** `a2.cpp` 出現在 `a1.cpp` 與 `a10.cpp` 之間
- **AND** 不是附加在清單尾端

### Requirement: 來源清單的內容

來源清單 SHALL 列出當前來源路徑「該層目錄」中所有副檔名為 `.cpp` 的檔案，MUST NOT 遞迴進入子目錄。

掃描 SHALL 由腳本執行，Qt 端 MUST NOT 自行讀取目錄。

來源清單 SHALL 為唯讀的來源池：項目被加入結果清單後仍保留在來源清單中，MUST NOT 減少。

來源目錄中沒有任何 `.cpp` 檔案 SHALL 視為成功而非失敗：來源清單為空，且 MUST NOT 顯示錯誤訊息框。

#### Scenario: 只列出該層的 .cpp

- **WHEN** 來源目錄含 `a.cpp`、`b.cpp`、`readme.txt` 與子目錄 `sub/`（內有 `c.cpp`）
- **THEN** 來源清單顯示 `a.cpp` 與 `b.cpp`
- **AND** 不含 `readme.txt`
- **AND** 不含 `c.cpp`

#### Scenario: 目錄中沒有 .cpp

- **WHEN** 來源目錄中不存在任何 `.cpp` 檔案
- **THEN** 來源清單為空
- **AND** 不顯示錯誤訊息框

#### Scenario: 加入結果清單後來源不變

- **WHEN** 使用者把 `a.cpp` 加入結果清單
- **THEN** `a.cpp` 仍留在來源清單中

### Requirement: 來源清單的過濾

過濾文字框 SHALL 即時過濾來源清單，只顯示名稱中含有該文字的項目。

比對 SHALL 為子字串比對且 SHALL 區分大小寫。

比對 MUST NOT 支援萬用字元或正規表示法；`*`、`?` 等字元 SHALL 視為一般字元參與比對。

過濾文字為空時 SHALL 顯示全部項目。

過濾文字每次變動 SHALL 清空來源清單目前的選取。

理由：過濾會把項目藏起來。若保留選取，使用者按下加入時會送出畫面上看不到的項目。

Source 群組的清除鈕 SHALL 只清空過濾文字，MUST NOT 改變來源清單的內容。過濾文字為空時該鈕 SHALL 為停用狀態。

#### Scenario: 輸入子字串過濾

- **WHEN** 來源清單含 `alpha.cpp`、`beta.cpp`、`alphabet.cpp`，使用者輸入 `alpha`
- **THEN** 清單只顯示 `alpha.cpp` 與 `alphabet.cpp`

#### Scenario: 過濾區分大小寫

- **WHEN** 來源清單含 `Alpha.cpp` 與 `alpha.cpp`，使用者輸入 `alpha`
- **THEN** 清單只顯示 `alpha.cpp`
- **AND** 不顯示 `Alpha.cpp`

#### Scenario: 萬用字元視為一般字元

- **WHEN** 來源清單含 `a1.cpp` 與 `a*b.cpp`，使用者輸入 `a*`
- **THEN** 清單只顯示 `a*b.cpp`

#### Scenario: 清空過濾文字後顯示全部

- **WHEN** 過濾生效中，使用者清空過濾文字
- **THEN** 來源清單顯示全部項目

#### Scenario: 過濾文字變動清空選取

- **WHEN** 使用者選取了數個來源項目後修改過濾文字
- **THEN** 來源清單沒有任何項目處於選取狀態
- **AND** `->` 按鈕變為停用

#### Scenario: 清除鈕只清過濾文字

- **WHEN** 過濾文字為 `alpha`，使用者按下 Source 群組的清除鈕
- **THEN** 過濾文字變為空
- **AND** 來源清單顯示全部項目，內容未減少

#### Scenario: 過濾文字為空時清除鈕停用

- **WHEN** 過濾文字為空
- **THEN** Source 群組的清除鈕為停用狀態

### Requirement: 加入項目至結果清單

按下 `->` SHALL 把來源清單中所有選取的項目複製到結果清單；來源清單的內容 MUST NOT 因此改變。

在來源清單的項目上按兩下 SHALL 把該項目加入結果清單，效果與選取該項目後按下 `->` 相同。

加入時，結果清單中已存在的項目 SHALL 被靜默略過：不重複加入，且 MUST NOT 顯示訊息框或其他提示。

來源清單沒有任何選取項目時，`->` SHALL 為停用狀態。

#### Scenario: 加入選取的項目

- **WHEN** 使用者選取 `a.cpp` 與 `b.cpp` 後按下 `->`
- **THEN** 結果清單含 `a.cpp` 與 `b.cpp`
- **AND** 來源清單仍含 `a.cpp` 與 `b.cpp`

#### Scenario: 雙擊加入

- **WHEN** 使用者在來源清單的 `a.cpp` 上按兩下
- **THEN** 結果清單含 `a.cpp`

#### Scenario: 略過已存在的項目

- **WHEN** 結果清單已含 `b.cpp`，使用者選取 `a.cpp`、`b.cpp`、`c.cpp` 後按下 `->`
- **THEN** 結果清單含 `a.cpp`、`b.cpp`、`c.cpp`，且 `b.cpp` 只出現一次
- **AND** 不顯示任何訊息框

#### Scenario: 沒有選取時按鈕停用

- **WHEN** 來源清單沒有任何項目處於選取狀態
- **THEN** `->` 為停用狀態

### Requirement: 移出結果清單的項目

按下 `<-` SHALL 從結果清單移除所有選取的項目。

在結果清單的項目上按兩下 SHALL 移除該項目。

移除 MUST NOT 影響來源清單的內容。

結果清單沒有任何選取項目時，`<-` SHALL 為停用狀態。

#### Scenario: 移除選取的項目

- **WHEN** 結果清單含 `a.cpp` 與 `b.cpp`，使用者選取 `a.cpp` 後按下 `<-`
- **THEN** 結果清單只剩 `b.cpp`
- **AND** 來源清單的內容不變

#### Scenario: 雙擊移除

- **WHEN** 使用者在結果清單的 `a.cpp` 上按兩下
- **THEN** 結果清單不再含 `a.cpp`

#### Scenario: 沒有選取時按鈕停用

- **WHEN** 結果清單沒有任何項目處於選取狀態
- **THEN** `<-` 為停用狀態

### Requirement: 清空結果清單

Target 群組的清除鈕 SHALL 清空結果清單的所有項目。

該操作 SHALL 只改變畫面，MUST NOT 寫入或清空暫存設定檔。

結果清單為空時該鈕 SHALL 為停用狀態。

#### Scenario: 清空結果清單

- **WHEN** 結果清單含數個項目，使用者按下 Target 群組的清除鈕
- **THEN** 結果清單為空
- **AND** 來源清單的內容不變

#### Scenario: 清空不影響已保存的設定

- **WHEN** 使用者按下 Target 群組的清除鈕後，未按下 Modify Setting 就離開並重新進入功能
- **THEN** 結果清單顯示暫存設定檔中原有的內容

#### Scenario: 結果清單為空時清除鈕停用

- **WHEN** 結果清單為空
- **THEN** Target 群組的清除鈕為停用狀態

### Requirement: 暫存設定檔

功能的設定 SHALL 保存於單一文字檔，位於作業系統的暫存目錄中（Windows 上即 `%TEMP%`）。

檔案內容 SHALL 為每行一個絕對路徑。

檔案不存在或內容為空 SHALL 視為「設定為空」，MUST NOT 視為錯誤。

該檔案 SHALL 為此功能唯一的狀態儲存處；設定因作業系統清理暫存目錄或重新開機而消失 SHALL 為預期行為，MUST NOT 另行備援。

暫存設定檔的讀取、寫入與清空 SHALL 全部由腳本執行，Qt 端 MUST NOT 直接存取該檔案。

#### Scenario: 設定檔不存在

- **WHEN** 暫存設定檔尚未被建立過，使用者進入功能
- **THEN** 結果清單為空
- **AND** 不顯示錯誤訊息框

#### Scenario: 讀出保存的內容

- **WHEN** 暫存設定檔含 `C:\proj\src\a.cpp` 與 `C:\proj\src\b.cpp`，使用者進入功能
- **THEN** 結果清單顯示 `a.cpp` 與 `b.cpp`

### Requirement: 進入功能時載入內容

每次進入功能 SHALL 重新載入來源清單並重新讀取暫存設定檔，包含應用程式啟動時該功能已處於顯示狀態的情形。

理由：啟動時功能 tab 已是當前分頁，切換事件不會發生，因此必須另有一次明確的初次載入，否則使用者第一眼看到的會是空白畫面。

載入 SHALL 先取得來源清單、後讀取設定。

當前來源路徑為空時 SHALL NOT 載入來源清單：來源清單保持為空，MUST NOT 視為失敗，MUST NOT 顯示錯誤訊息框；讀取暫存設定檔仍照常進行。

理由：應用程式啟動時來源路徑尚未由使用者指定。若此時視為失敗，使用者每次啟動都會看到一個無從避免的錯誤訊息框。

結果清單中尚未寫入設定檔的變更 SHALL 在重新進入功能時被設定檔的內容覆蓋而遺失。此為明確定義的行為，MUST NOT 另行提示或保留。

#### Scenario: 啟動時功能已顯示

- **WHEN** 應用程式啟動且 Single Building 是當前分頁
- **THEN** 讀取暫存設定檔並填入結果清單
- **AND** 使用者不需要切走再切回才看得到內容

#### Scenario: 來源路徑為空

- **WHEN** 使用者進入功能而當前來源路徑為空
- **THEN** 來源清單為空
- **AND** 不顯示錯誤訊息框
- **AND** 結果清單仍依暫存設定檔的內容填入

#### Scenario: 切回功能時重新載入

- **WHEN** 使用者切換到其他功能後再切回 Single Building
- **THEN** 來源清單依當前來源路徑重新載入
- **AND** 結果清單依暫存設定檔重新填入

#### Scenario: 未寫入的變更會遺失

- **WHEN** 使用者調整結果清單但未按下 Modify Setting，切換到其他功能後再切回
- **THEN** 結果清單顯示的是暫存設定檔的內容
- **AND** 先前未寫入的調整不再存在

### Requirement: 來源路徑變更後重新開始

在此功能中變更來源路徑 SHALL 清空暫存設定檔，並依新路徑重新載入來源清單；結果清單隨之為空。

理由：設定保存的是絕對路徑，換了來源目錄之後原有的設定不再指向使用者當下在看的檔案。

在其他功能中變更來源路徑 MUST NOT 影響本功能的暫存設定檔與畫面內容。

#### Scenario: 在本功能變更來源路徑

- **WHEN** 使用者已保存設定，接著在 Single Building 中把來源路徑改為另一個目錄
- **THEN** 暫存設定檔的內容被清空
- **AND** 結果清單為空
- **AND** 來源清單顯示新目錄中的 `.cpp` 檔案

#### Scenario: 在本功能清除來源路徑

- **WHEN** 使用者在 Single Building 中清除來源路徑
- **THEN** 暫存設定檔的內容被清空
- **AND** 來源清單與結果清單皆為空

#### Scenario: 在其他功能變更來源路徑

- **WHEN** 使用者切換到其他功能並變更其來源路徑，之後切回 Single Building
- **THEN** Single Building 的來源路徑仍是先前設定的值
- **AND** 暫存設定檔的內容未被清空

### Requirement: 寫入設定

按下 Modify Setting SHALL 把結果清單中所有項目的絕對路徑寫入暫存設定檔，覆蓋原有內容。

結果清單為空時按下 Modify Setting SHALL 寫入空內容，此為有效操作而非錯誤。

寫入成功後 MUST NOT 重新讀取設定檔：畫面上的結果清單已與檔案內容一致。

#### Scenario: 寫入結果清單的內容

- **WHEN** 結果清單含 `a.cpp` 與 `b.cpp`（來源目錄為 `C:\proj\src`），使用者按下 Modify Setting
- **THEN** 暫存設定檔的內容為 `C:\proj\src\a.cpp` 與 `C:\proj\src\b.cpp` 兩行
- **AND** 原有內容被覆蓋

#### Scenario: 寫入空的結果清單

- **WHEN** 結果清單為空，使用者按下 Modify Setting
- **THEN** 暫存設定檔的內容為空
- **AND** 不顯示錯誤訊息框

#### Scenario: 寫入成功後畫面不變

- **WHEN** 寫入成功
- **THEN** 結果清單維持原本顯示的內容
- **AND** 不重新讀取設定檔

### Requirement: 清空設定

按下 Recovery Setting SHALL 先顯示確認對話框說明此操作會清空已保存的設定。

理由：清空後暫存設定檔的原有內容無法復原。

使用者確認後 SHALL 清空暫存設定檔並重新讀取其內容，結果清單因此為空。

使用者取消確認時 MUST NOT 執行任何動作：暫存設定檔與兩個清單皆不改變。

#### Scenario: 確認後清空

- **WHEN** 暫存設定檔含數筆路徑，使用者按下 Recovery Setting 並確認
- **THEN** 暫存設定檔的內容被清空
- **AND** 結果清單為空
- **AND** 來源清單的內容不變

#### Scenario: 取消確認

- **WHEN** 使用者按下 Recovery Setting 後在確認對話框選擇取消
- **THEN** 暫存設定檔的內容不變
- **AND** 結果清單的內容不變

### Requirement: 腳本失敗與取消的處理

腳本回報失敗時，其對應的清單 SHALL 被清空，並 SHALL 顯示錯誤訊息說明原因。

理由：保留失敗前的舊內容會讓使用者誤以為那是當前來源或當前設定的內容。

同一次進入功能中若取得來源清單與讀取設定皆失敗，SHALL 只顯示一個訊息框，內含兩者的失敗原因。

使用者取消腳本執行時，畫面 SHALL 完全不變：兩個清單維持取消前的內容。

一次操作需要接續執行多支腳本時，使用者取消其中一支 SHALL 中止整串執行，後續腳本 MUST NOT 被啟動。

#### Scenario: 取得來源清單失敗

- **WHEN** 來源路徑指向一個不存在的目錄，使用者進入功能
- **THEN** 來源清單為空
- **AND** 顯示錯誤訊息說明原因

#### Scenario: 讀取設定失敗

- **WHEN** 暫存設定檔存在但無法讀取
- **THEN** 結果清單為空
- **AND** 顯示錯誤訊息說明原因

#### Scenario: 兩者皆失敗

- **WHEN** 取得來源清單與讀取設定在同一次進入功能中都失敗
- **THEN** 只顯示一個錯誤訊息框
- **AND** 該訊息框同時說明兩者的失敗原因

#### Scenario: 取消執行

- **WHEN** 使用者在腳本執行中按下取消
- **THEN** 來源清單與結果清單維持取消前的內容
- **AND** 不顯示錯誤訊息框

#### Scenario: 取消中止後續腳本

- **WHEN** 進入功能時使用者取消了取得來源清單的執行
- **THEN** 不啟動讀取設定的腳本
- **AND** 兩個清單維持原本的內容
