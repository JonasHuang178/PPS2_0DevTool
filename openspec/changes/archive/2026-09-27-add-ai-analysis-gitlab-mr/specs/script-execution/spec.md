## MODIFIED Requirements

### Requirement: 請求信封組裝

外殼 SHALL 組裝請求信封並經由標準輸入交給腳本。信封 SHALL 包含四個欄位：`source_path`、`config`、`action`、`params`。

`source_path` SHALL 由外殼自動填入目前的來源路徑，功能不需傳入；空字串為合法值。

`config` SHALL 為工具層級 `Service` 區塊併上該功能在設定檔 `Function` 底下的完整區塊；兩邊出現同名鍵時，SHALL 以功能區塊的值為準。

理由：跨功能共用的服務端點與憑證在設定檔中只有一份來源，腳本卻不需要認識這個結構 —— 它收到的仍是一個平坦的 `config` 物件。功能區塊優先，是為了讓個別功能能指向與共用設定不同的伺服器。

信封格式 MUST NOT 因此增加欄位 —— 合併發生在外殼組裝信封之前，腳本端、信封處理層與設定模板的格式皆不改變。

信封 MUST NOT 包含工具身分欄位 —— 工具身分經由環境變數傳遞。

寫入標準輸入後，外殼 MUST 關閉寫入通道，否則腳本會永久停在讀取標準輸入而使介面凍結。

#### Scenario: 信封內容

- **WHEN** 功能以動作名稱與參數呼叫腳本執行介面
- **THEN** 腳本從標準輸入收到含 `source_path`、`config`、`action`、`params` 四個欄位的 JSON 物件
- **AND** `config` 同時含有 `Service` 區塊的鍵與該功能區塊的鍵

#### Scenario: 同名鍵以功能區塊為準

- **WHEN** `Service` 與某功能區塊都有一個同名的鍵，該功能執行腳本
- **THEN** 腳本收到的 `config` 中該鍵的值來自功能區塊
- **AND** `Service` 中的值不出現在該次信封裡

#### Scenario: 不需要 Service 的功能不受影響

- **WHEN** 一個不使用任何共用服務的功能執行它既有的腳本
- **THEN** 該腳本正常執行
- **AND** 多出來的 `Service` 鍵因協定是加法式的而被忽略，腳本不需要修改

#### Scenario: 寫入後關閉寫入通道

- **WHEN** 信封寫入腳本的標準輸入完成
- **THEN** 寫入通道被關閉
- **AND** 腳本讀取標準輸入的動作能夠結束
