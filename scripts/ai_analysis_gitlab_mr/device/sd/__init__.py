#!/usr/bin/env python3
"""SD device —— SD 產品線自己的 JIRA key 與 MR 種類擷取規則。

設定檔的 `PPS_Device` 填 `sd` 時選用這一份（CI 則是環境變數 `PPS_DEVICE`）。

這個 device 覆寫兩支擴充腳本，都在步驟 2：

    jira_key.py     標題的**第一個**方括號
    mr_type.py      標題的**第二個**方括號

        mod:[PPS-1234][Bug] 修正重試上限
            ^^^^^^^^^^ 第一個：JIRA key
                      ^^^^^ 第二個：種類  ->  bug

其餘三支（`summary`、`parse_code_review`、`merge_to_md`）**沒有放**，逐支回退到
`device/default/`。回退是逐支的，所以沒放的那幾支拿到的是 default 當下的實作，而不是
一份會慢慢與 default 漂移的複本。

> **種類目前還沒有任何子目錄，所以種類實際上還不生效。** `mr_type.py` 會把第二個方括號
> 擷取出來，但入口腳本接著會發現這個 device 認不得它（底下沒有同名目錄），於是**回退成
> 空字串** —— `02_mr_info.json` 與報告出處的 `Type` 都會是空的，兩支因種類而異的擴充腳本
> 一律走通用版（也就是 default 的那兩份）。唯一看得見那個字串的地方是 `Debug_Mode` 開啟時
> console 上那一行「device sd 認不得種類 'bug'（認得的是：(無)）」。
>
> 要讓某個種類真的生效，就在這個目錄底下開一個以它命名的子目錄（見
> `device/_template/_type_template/`）—— 目錄一存在，那個種類就被認得，也才會進產物。
"""

# 這個 device 的版本，會印在報告末尾的出處資訊裡。**必填。**
#
# 版號兩碼：
#
#     2  .  0
#     │     └── 第二碼：這個 device 的任何修改都 +1，包含只改註解
#     └──────── 第一碼：**要與通用層的 SCRIPT_VERSION 一致**
#
# 第一碼一致，讀報告的人才看得出這份 device 是照哪一代的契約寫的。通用層升到 3.0 時，
# 這裡也該改成 3.0（第二碼歸零）。
#
# **不一致不會讓執行失敗**，也沒有任何機制強迫你更新第二碼 —— 忘了就是忘了，由開發者
# 自負。報告照實印出讀到的值，兩個版號都在眼前，對照得出來。
VERSION = "2.0"

# `new_test_case` 那張工單狀態表，「項目」欄要印的字樣。
#
# 改這一行就改了報告上那一格，不必動擴充腳本。沒有宣告時用那一支自己的預設值
# （`JIRA 單`），所以拿掉這一行不會壞。
#
# 這是 **sd 自己的宣告**，不是通用層認得的項目 —— 通用層只讀 VERSION、STRICT_TYPE 與
# CODE_REVIEW_SOURCE_HEADING 三個。讀它的人是 `new_test_case/merge_to_md.py`：那一支
# import 這個套件再 getattr，所以這裡要加第二、第三個宣告也是同一個做法，不需要改通用層。
#
# 欄位的標題（`項目`／`內容`／`狀態`）在 `new_test_case/merge_to_md.py` 最上面，與這一行
# 分開放：那三個字決定表格的形狀，改了要連帶看那一支怎麼填每一列，所以留在它旁邊。
NEW_TEST_CASE_ITEM_LABEL = u"JIRA 單"

# `new_test_case` 那張表的**第二列**：另一張用 JQL 找出來的 JIRA 單。
#
# **這裡只寫 JQL 固定的那一段。** 隨每一筆 MR 變動的條件由 `new_test_case/summary.py`
# 接上去 —— 預設接的是主單的標題：
#
#     宣告     project = PPS AND issuetype = "Test Plan"
#     實際送出 project = PPS AND issuetype = "Test Plan" AND summary ~ "補上 TRIM 的邊界測試"
#
# 接上去的文字會被包成 JQL 的字串常量並跳脫（反斜線與雙引號）—— 標題裡一個雙引號就會讓
# 整段 JQL 語法錯誤，而 JIRA 回的 400 會指著一段你從沒寫過的查詢字串。
#
# **要自己決定那一段接在哪裡**（例如查詢帶 ORDER BY，或變動的條件不在最後）就用佔位符：
#
#     {summary}   主單的標題
#     {key}       主單的 key
#
# 兩個佔位符代入的都是**已經包好引號的字串常量**，所以 `summary ~ {summary}`、
# `issue in linkedIssues({key})` —— **不要自己再加引號**。宣告裡只要出現任一個佔位符，
# 就完全照你寫的位置代入，不再自動往後接。
#
# ⚠️ 帶 ORDER BY 的查詢**必須用佔位符** —— 自動接在最後會變成 `ORDER BY … AND summary ~ …`，
# 那是語法錯誤。
#
# 幾種常見的寫法：
#
#     project = PPS AND issuetype = "Test Plan"       固定條件 + 自動接標題
#     issue in linkedIssues({key})                    與主單有連結的
#     parent = {key}                                  主單的子任務
#     project = PPS AND summary ~ {summary} ORDER BY created DESC  自己決定位置
#
# 設成空字串就**完全不查**，報告那一列印「（未查詢）」。查不到、查詢失敗、沒設定 JIRA
# 連線也都不會讓流程失敗 —— JIRA 在這裡是補充資料。
#
# 符合的單子超過一張時取**第一張**，並在診斷輸出記一筆（寫明共幾張、取了哪一張）。要的是
# 一列，而「哪一張才對」只有寫這條 JQL 的人知道 —— 排序請寫進 JQL 的 ORDER BY。
NEW_TEST_CASE_RELATED_JQL = u'project = PPS AND issuetype = "Test Plan"'

# 第二列「項目」欄要印的字樣。
NEW_TEST_CASE_RELATED_LABEL = u"New test case"

# 這裡**還沒有宣告** STRICT_TYPE 與 CODE_REVIEW_SOURCE_HEADING，兩者都沿用預設值。
#
# STRICT_TYPE 未宣告即 False：標題解不出種類、或解出的名稱這裡沒有對應目錄時，走通用版
# 而不失敗。「MR 一定要標明種類」是一條團隊紀律 —— 要不要強制由 SD 自己決定，而現在還
# 沒有任何種類目錄，宣告 True 會讓每一筆 MR 都在步驟 2 失敗。
#
# 不要為了「寫清楚」先照抄一份與預設值相同的宣告 —— 日後通用層改了預設值，這裡抄的那
# 一份不會跟著動，而且不會有任何徵兆。
#
# 可宣告的項目及其預設值見 `device/_template/__init__.py` 的註解。
