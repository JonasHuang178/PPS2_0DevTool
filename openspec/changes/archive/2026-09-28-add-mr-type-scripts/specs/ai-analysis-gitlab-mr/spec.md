## ADDED Requirements

### Requirement: Merge Request 種類的抽出

流程 SHALL 為每一次分析解析出該 Merge Request 的**種類**，並 SHALL 以 device 的鉤子
進行，使判斷規則可因產品線而異。

理由：各條產品線的標題約定各自演化 —— 一條看第二個方括號、另一條看第三個。把規則寫死在
共用的腳本裡，等於要求所有產品線先達成共識。

抽出 SHALL 與抽出 JIRA key 在**同一個步驟**進行，MUST NOT 為此新增流程步驟或新增一次
對 GitLab 的取得。

理由：兩者解的是同一份 Merge Request 的同一個標題。分成兩步會讓同一筆 MR 被取得三次。

鉤子 SHALL 收到與抽出 JIRA key 的鉤子相同的欄位。

抽出的結果 SHALL 一律轉為小寫後比對。

理由：目錄名一律小寫（見「種類的名稱規則」），而標題裡寫的是 `[NewTestCase]` 這種給人
看的形式。

鉤子 SHALL 得以把標題中的寫法映射為不同的名稱。

理由：標題可能寫 `[FW-Update]`，而目錄名必須是合法的識別字。映射由該 device 決定，標題
長什麼樣是各產品線自己的約定。

#### Scenario: 不同 device 有不同的抽出規則

- **WHEN** 兩個 device 分別宣告自標題第二與第三個方括號抽出種類
- **THEN** 同一份標題在兩個 device 下解析出不同的種類

#### Scenario: 與 JIRA key 同一次取得

- **WHEN** 一次分析執行完畢
- **THEN** 該 Merge Request 被取得的次數與未加入種類之前相同

#### Scenario: 大小寫

- **WHEN** 標題中的種類寫作 `NewTestCase`
- **THEN** 解析出的種類為 `newtestcase`

### Requirement: 種類的名稱規則

種類的名稱 SHALL 與 device 的名稱適用同一套規則：小寫英數與底線、不以數字開頭。

理由：種類對應到一個目錄，而該目錄會被當成模組匯入。

以底線開頭的目錄 MUST NOT 被視為種類。

抽出的字串不符合該規則時 SHALL 視同沒有抽出種類，MUST NOT 另外回報「名稱不合法」。

理由：那是 Merge Request 作者打的字，不是部署者的錯誤。兩者的後續處理相同（見「認不得的
種類」），分開回報只會多一種使用者無法行動的訊息。

#### Scenario: 不合法的字串

- **WHEN** 鉤子自標題抽出含有空白或非英數字元的字串
- **THEN** 該次分析視同沒有種類

#### Scenario: 底線開頭的目錄

- **WHEN** 列出某個 device 目前認得的種類
- **THEN** 以底線開頭的目錄不出現在清單中

### Requirement: 種類只在自身 device 之內解析

因種類而異的鉤子 SHALL 依序尋找：該 device 底下該種類的實作、該 device 底下的實作、
預設 device 的實作。

系統 MUST NOT 尋找「預設 device 底下該種類的實作」。

理由：各 device 的種類字彙互相獨立且各自演化，同一個名稱在兩個 device 下不保證是同一件
事。跨 device 尋找同名的種類，會在字彙撞名時套用另一條產品線的邏輯 —— 而每一個步驟都會
回報成功。這與「未知的 device 必須失敗」要避免的是同一種失敗。

附帶的結果是解析順序沒有任何模稜兩可之處：少了那一段，就不需要裁決「自身的通用實作」與
「預設的種類實作」孰先。

跨 device 的共用 SHALL 以明確的匯入達成，MUST NOT 由回退機制隱含提供。

理由：明確匯入時，是撰寫者自己決定要用哪一份。

#### Scenario: 種類有專屬實作

- **WHEN** 某 device 底下存在該種類的 AI 分析實作
- **THEN** 使用該實作

#### Scenario: 種類沒有專屬實作

- **WHEN** 某 device 底下存在該種類的目錄，但其中沒有報告版面的實作
- **THEN** 使用該 device 的報告版面實作；該 device 也沒有時使用預設 device 的

#### Scenario: 不跨 device 尋找種類

- **WHEN** 某 device 沒有某種類的實作，而預設 device 有同名種類的實作
- **THEN** 使用該 device 的通用實作或預設 device 的通用實作，MUST NOT 使用預設 device
  的該種類實作

### Requirement: 認不得的種類

抽不到種類、抽出的字串不合法、或該 device 底下沒有該種類的目錄時，系統 SHALL 使用該
device 的通用實作，MUST NOT 回報失敗 —— 除非該 device 宣告了嚴格模式。

理由：device 的名稱來自設定檔，打錯是操作者的責任，因此未知的 device 必須失敗。種類則
來自 Merge Request 的標題 —— 那是任何能開 MR 的人打的字。為了一個沒照約定的標題讓整份
分析做不出來，等於把工具的可用性綁在他人的打字習慣上。

device SHALL 得以宣告要求每一筆 Merge Request 都解析出認得的種類；未宣告時 SHALL 視為
不要求。

理由：「Merge Request 一定要標明種類」是一條團隊紀律，而紀律是各條產品線自己的事。全域
的開關會迫使字彙都不共用的兩條產品線在這件事上達成一致。定義字彙的人正是知道那些種類
該不該強制的人。

該宣告 MUST NOT 為必填。

理由：設為必填會讓每一個既有的 device 立刻失效，而預設值有一個明確且安全的選擇。

#### Scenario: 未宣告嚴格模式

- **WHEN** 標題中的種類在該 device 底下沒有對應的目錄，而該 device 未宣告嚴格模式
- **THEN** 分析以該 device 的通用實作完成

#### Scenario: 既有的 device 不受影響

- **WHEN** 某個 device 沒有任何種類目錄，也未宣告嚴格模式
- **THEN** 其行為與加入種類機制之前完全相同

### Requirement: 嚴格模式的範圍與時機

宣告了嚴格模式的 device SHALL 在解析不出認得的種類時回報失敗。

該檢查 SHALL 在抽出種類的那一步進行，MUST NOT 延後到後續步驟。

理由：在任何 AI 花費之前失敗。一個打錯的標題不該先付一次費用才被告知。

嚴格模式 SHALL 只針對「種類本身認不認得」，MUST NOT 要求種類目錄提供所有鉤子。

理由：否則新增一個種類就必須放齊所有鉤子，而逐項回退正是為了避免那種複製。

失敗訊息 SHALL 區分「沒有宣告種類」與「宣告了認不得的種類」，且後者 SHALL 列出該 device
目前認得哪些種類。

理由：兩者的下一步不同 —— 一個是去補標題，一個是去確認名稱或新增目錄。而由於沒有中央
的種類清單，錯誤發生的當下正是使用者需要那份清單的時刻。

#### Scenario: 沒有宣告種類

- **WHEN** 某 device 宣告嚴格模式，而某筆 Merge Request 解析不出種類
- **THEN** 該步驟回報失敗，訊息指出這筆 Merge Request 沒有宣告種類
- **AND** 失敗發生在任何 AI 呼叫之前

#### Scenario: 宣告了認不得的種類

- **WHEN** 某 device 宣告嚴格模式，而標題中的種類在該 device 底下沒有對應目錄
- **THEN** 該步驟回報失敗，訊息列出該 device 目前認得哪些種類

#### Scenario: 嚴格模式不要求放齊鉤子

- **WHEN** 某 device 宣告嚴格模式，而某個種類目錄中只有部分鉤子
- **THEN** 缺少的鉤子照常回退，分析完成

### Requirement: 種類隨分析結果傳遞

解析出的種類 SHALL 由抽出它的那一步產出，並 SHALL 由 AI 分析那一步寫入分析結構。

合併為 markdown 那一步 SHALL 自分析結構讀取種類以解析自己的鉤子，MUST NOT 另行取得。

理由：種類因此被記入產物，可用於報告的出處與其他消費者；而圖形介面只需要把它從一步轉送
到下一步一次。

種類 SHALL 由入口腳本寫入，鉤子 MUST NOT 自行填寫。

理由：與結構版本同一個理由 —— 讓鉤子填寫，複製範本時遲早有人忘記。

分析結構中沒有種類時 SHALL 視為沒有種類並使用通用實作，MUST NOT 回報失敗。

理由：與結構版本的寬鬆比對一致，使舊的產物仍可被渲染。

報告末尾的出處資訊 SHALL 包含種類。

#### Scenario: 種類進入分析結構

- **WHEN** 一次分析解析出種類
- **THEN** 分析結構中含有該種類

#### Scenario: 合併那一步自產物取得種類

- **WHEN** 合併為 markdown 那一步執行
- **THEN** 它使用分析結構中的種類解析自己的鉤子

#### Scenario: 舊的分析結構

- **WHEN** 合併為 markdown 那一步讀到不含種類的分析結構
- **THEN** 使用該 device 的通用版面，流程成功

### Requirement: 由 Merge Request 內容選擇實作的界線

系統 SHALL 允許由 Merge Request 的內容決定套用哪一個種類的實作，此為「執行哪一段運算不
取自回傳資料」的明確例外。

該例外 SHALL 受兩項限制：名稱必須通過名稱規則的檢查，且必須對應到一個**已經部署在該
device 底下**的目錄。

理由：Merge Request 的標題是任何能開 MR 的人打的字。上述兩項限制使它只能在既有的選項
之間挑選，MUST NOT 引入任何未部署的程式碼，也 MUST NOT 指向該 device 以外的位置。

#### Scenario: 名稱無法指向其他位置

- **WHEN** Merge Request 的標題中含有路徑分隔字元或上層目錄的寫法
- **THEN** 該字串不通過名稱規則，視同沒有種類

#### Scenario: 只能挑既有的選項

- **WHEN** Merge Request 的標題宣告了一個未部署的種類
- **THEN** 系統回退或失敗，MUST NOT 載入任何其他位置的實作

## MODIFIED Requirements

### Requirement: device 鉤子的範圍

流程中 SHALL 只有三個步驟因 device 而異：取得相關資訊（抽出 JIRA key 與種類）、AI 分析、
合併為 markdown。

取得 Merge Request 描述與取得程式碼審閱報告 MUST NOT 因 device 而異。

鉤子 SHALL 分為兩類，其解析方式不同：

- **不因種類而異**：抽出 JIRA key、抽出種類。兩者在種類被決定之前執行（後者正是決定它的
  那一支），因此種類對它們沒有意義。
- **因種類而異**：AI 分析、合併為 markdown。

每一步的入口腳本 SHALL 保留共用的部分 —— 信封處理、憑證取得、對外服務的呼叫、產物落檔、
失敗訊息與進度回報 —— 並只將業務運算交給 device 的鉤子。

理由：若每個 device 各有一支完整的腳本，共用部分（服務錯誤的分類指引、程式碼區塊界線的
計算、diff 的長度上限）會在每個 device 中各出現一次並各自漂移。

#### Scenario: 只有三個步驟因 device 而異

- **WHEN** 以不同的 device 執行同一個 Merge Request 的分析
- **THEN** 取得描述與取得程式碼審閱報告的行為相同
- **AND** 抽出 JIRA key、抽出種類、AI 分析與報告版面可以不同

#### Scenario: 抽出用的鉤子不因種類而異

- **WHEN** 解析抽出 JIRA key 或抽出種類的鉤子
- **THEN** 只在該 device 與預設 device 之間尋找，不涉及任何種類

#### Scenario: 共用部分不因 device 重複

- **WHEN** 某個 device 的鉤子執行失敗
- **THEN** 失敗訊息的形式與其他 device 相同，因為它由入口腳本產生

### Requirement: 鉤子的逐項回退

device 的實作 SHALL 允許只提供部分鉤子。缺少的鉤子 SHALL 使用預設 device 的對應實作。

理由：只想改變報告版面的 device 不應被迫複製其他鉤子 —— 那份複本會與預設實作漸漸不同。

同一個原則 SHALL 適用於種類：種類目錄 SHALL 允許只提供部分鉤子，缺少的依「種類只在自身
device 之內解析」的順序回退。

此回退 SHALL 只適用於「device 存在但缺少某個鉤子」與「種類目錄存在但缺少某個鉤子」。
device 本身不存在時的行為見其對應需求（失敗）；種類不存在時的行為見「認不得的種類」。

#### Scenario: 只提供一個鉤子

- **WHEN** 某個 device 只提供報告版面的鉤子
- **THEN** 報告版面使用該 device 的實作
- **AND** 抽出 JIRA key 與 AI 分析使用預設 device 的實作

#### Scenario: 種類目錄只提供一個鉤子

- **WHEN** 某個種類目錄只提供 AI 分析的鉤子
- **THEN** AI 分析使用該種類的實作
- **AND** 報告版面回退到該 device 的通用實作

#### Scenario: 兩種缺失的區別

- **WHEN** device 存在但缺少某個鉤子
- **THEN** 使用預設的該鉤子，流程繼續
- **AND** 這與 device 本身不存在時的失敗是不同的行為

### Requirement: device 實作的版本

每一個 device SHALL 宣告自己的版本。未宣告時 SHALL 視為錯誤。

理由：該版本會出現在報告的出處資訊中。若它可以是空的，那一行就無法說明報告是由哪一版
邏輯產生的 —— 而那正是它存在的理由。

版本之外的其他宣告 SHALL 為選填，且 SHALL 有明確的預設值。

理由：既有的 device 不應因為新增了一項宣告而失效。版本是例外，因為它沒有合理的預設。

#### Scenario: device 未宣告版本

- **WHEN** 被指定的 device 沒有宣告版本
- **THEN** 該步驟回報失敗，訊息指出是哪一個 device

#### Scenario: 未宣告選填項目

- **WHEN** 某個 device 只宣告了版本
- **THEN** 其餘宣告使用預設值，該 device 正常執行

### Requirement: device 實作的範本

專案 SHALL 提供 device 鉤子的範本，說明每一個鉤子收到什麼、必須回傳什麼，以及可供使用
的共用函式。

範本 SHALL 包含種類目錄的範本。

範本的宣告檔 SHALL 以註解列出所有可用的宣告項目及其預設值。

理由：這些名稱沒有別的地方會提示。要使用時得翻文件或讀載入器的原始碼，而那是一個每次
都要付、且容易讓人直接放棄的成本。

範本與其中的種類範本 MUST NOT 被視為可用的 device 或種類。

#### Scenario: 依範本新增 device

- **WHEN** 開發者複製範本並填入自己的邏輯
- **THEN** 該 device 可被環境變數指定並正常執行

#### Scenario: 宣告項目可被發現

- **WHEN** 開發者開啟範本的宣告檔
- **THEN** 所有可用的宣告項目及其預設值以註解列出

### Requirement: 取得相關資訊的 GitLab 連線

取得相關資訊那一步 SHALL 自行連線 GitLab 取得該 Merge Request，MUST NOT 依賴其他步驟
轉送這些資料。

理由：抽出 JIRA key 與種類的預設規則需要 Merge Request 的標題，而取得描述那一步的產物
只有描述本文。圖形介面也不可靠 —— 使用者手動輸入編號時畫面上沒有標題。自行取得使該步
可以單獨執行，且圖形介面與持續整合不需要多傳任何東西。

已知代價：同一個 Merge Request 在一次分析中被取得兩次。加入種類的抽出 MUST NOT 使這個
次數增加。

交給抽取鉤子的 SHALL 是整理過的欄位（至少包含標題、來源分支、目標分支、描述、專案與
編號），MUST NOT 是 GitLab 原樣的回應物件。抽出 JIRA key 與抽出種類的鉤子 SHALL 收到
相同的欄位。

理由：原樣傳遞會讓 GitLab 回應的所有欄位成為對 device 作者的契約，日後無法更換取得方式。

取得失敗時 SHALL 回報失敗並結束流程，且失敗訊息的分類 SHALL 與其他連線 GitLab 的腳本
一致（存取權杖、專案或 Merge Request 不存在、憑證驗證失敗各自不同且可行動）。

#### Scenario: 取得 Merge Request

- **WHEN** 該步驟執行且環境中的存取權杖有效
- **THEN** 它自行取得該 Merge Request 的資料
- **AND** 不需要其他步驟轉送標題或分支

#### Scenario: 鉤子收到整理過的欄位

- **WHEN** 抽取鉤子被呼叫
- **THEN** 它收到的是整理過的欄位，而非 GitLab 原樣的回應物件

#### Scenario: 兩個抽取鉤子共用同一次取得

- **WHEN** 該步驟同時抽出 JIRA key 與種類
- **THEN** 只向 GitLab 取得該 Merge Request 一次

#### Scenario: 取得失敗

- **WHEN** 無法取得該 Merge Request
- **THEN** 該步驟回報失敗，流程結束
- **AND** 訊息的分類與其他連線 GitLab 的腳本一致
