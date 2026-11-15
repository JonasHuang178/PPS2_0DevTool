## MODIFIED Requirements

### Requirement: device 實作的版本

每一個 device SHALL 宣告自己的版本。未宣告時 SHALL 視為錯誤。

理由：該版本會出現在報告的出處資訊中。若它可以是空的，那一行就無法說明報告是由哪一版
邏輯產生的 —— 而那正是它存在的理由。

該版本 SHALL 依「腳本的版號」規則中實作層的形狀宣告，即 `vA.B.C`：前兩碼指出這個 device
是照哪一代的通用層寫的，第三碼是它自己動過的次數。

該 device 之下種類目錄的改動 SHALL 算進該 device 版本的第三碼，種類 MUST NOT 有自己的版本。

第二碼是否跟上最新的通用版號 SHALL 由該 device 的維護者決定。版本落後 MUST NOT 使載入或
執行失敗，亦 MUST NOT 被回報為問題。

理由：通用層的某一代可能完全不影響某個 device。由維護者判斷，才不會為了對齊數字而製造一批
說不出任何事情的提交；而版號落後本身就是出處那幾行要傳達的資訊之一。

版本之外的其他宣告 SHALL 為選填，且 SHALL 有明確的預設值。

理由：既有的 device 不應因為新增了一項宣告而失效。版本是例外，因為它沒有合理的預設。

#### Scenario: device 未宣告版本

- **WHEN** 被指定的 device 沒有宣告版本
- **THEN** 該步驟回報失敗，訊息指出是哪一個 device

#### Scenario: 未宣告選填項目

- **WHEN** 某個 device 只宣告了版本
- **THEN** 其餘宣告使用預設值，該 device 正常執行

#### Scenario: device 版本的形狀

- **WHEN** 讀取某個 device 宣告的版本
- **THEN** 它是帶 `v` 前綴的三碼，前兩碼對應它所依據的那一代通用版號

#### Scenario: 種類改動算進 device 的版本

- **WHEN** 某個 device 之下某個種類的擴充腳本被改動
- **THEN** 該 device 版本的第三碼累加
- **AND** 該種類沒有自己的版本

#### Scenario: device 版本落後於通用層

- **WHEN** 通用版號的第二碼已經往前，而某個 device 宣告的版本仍停在先前那一代
- **THEN** 該 device 照常被載入並執行
- **AND** 報告的出處照實呈現該版本，不另外回報為問題
