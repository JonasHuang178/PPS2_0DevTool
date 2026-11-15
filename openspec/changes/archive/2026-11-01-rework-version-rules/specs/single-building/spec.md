## MODIFIED Requirements

### Requirement: 腳本版號的宣告

Single Building SHALL 依「腳本的版號」規則宣告自己的功能名稱與版號，由四支入口腳本共用一份。

該功能沒有可由他人各自維護的實作層，因此 SHALL 只有一份版號，且該版號 SHALL 為帶 `v` 前綴
的三碼。

每一支入口腳本 SHALL 在開始執行時將功能名稱與版號記入診斷輸出。

理由：這個功能的產出不會脫離產生它的環境 —— 結果顯示在畫面上，使用者看完就關掉，沒有一份
會被貼到別處的報告可以承載版號。診斷輸出是唯一看得到它的地方，而「請看 console 的第一行」
在支援時足以問出使用者手上跑的是哪一版。

每一支入口腳本另外宣告的請求／回應格式版本 SHALL 與功能版號分開，MUST NOT 共用同一個名稱。

#### Scenario: 版號記入診斷

- **WHEN** 任何一支 Single Building 的入口腳本開始執行
- **THEN** 診斷輸出中有一筆紀錄帶著功能名稱與版號

#### Scenario: 版號的形狀

- **WHEN** 讀取 Single Building 的功能版號
- **THEN** 它是帶 `v` 前綴的三碼

#### Scenario: 兩類版號分開宣告

- **WHEN** 開發者閱讀任何一支 Single Building 的入口腳本
- **THEN** 功能版號與請求／回應格式版本是兩個不同名字的宣告
