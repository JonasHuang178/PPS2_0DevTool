#!/usr/bin/env python3
"""SD device —— SD 產品線自己的 JIRA key 與 MR 種類擷取規則。

設定檔的 `PPS_Device` 填 `sd` 時選用這一份（CI 則是環境變數 `PPS_DEVICE`）。

這個 device 覆寫四支擴充腳本：

    jira_key.py     步驟 2：標題的**第一個**方括號
    mr_type.py      步驟 2：標題的**第二個**方括號
    summary.py      步驟 3：SD 自己的 prompt 與解析
    merge_to_md.py  步驟 5：SD 自己的版面

        mod:[PPS-1234][New Test Case] 補上 TRIM 的邊界測試
            ^^^^^^^^^^ 第一個：JIRA key
                      ^^^^^^^^^^^^^^^ 第二個：種類  ->  new_test_case

`parse_code_review` **沒有放**，回退到 `device/default/`。回退是逐支的，所以沒放的那
一支拿到的是 default 當下的實作，而不是一份會慢慢與 default 漂移的複本。

> **目前有一個種類生效：`new_test_case/`**（標題寫 `[New Test Case]`，對照表見
> `mr_type.py`）。那個種類兩支因種類而異的擴充腳本都自己覆寫，而且是明著 import sd
> 這一層來共用排版。
>
> `mr_type.py` 擷取出來但這裡沒有同名目錄的種類，入口腳本會**回退成空字串** ——
> `02_mr_info.json` 與報告出處的 `Type` 都會是空的，兩支因種類而異的擴充腳本一律走
> sd 的通用版。唯一看得見那個字串的地方是 `Debug_Mode` 開啟時 console 上那一行
> 「device sd 認不得種類 …」。
>
> 要讓某個種類真的生效，就在這個目錄底下開一個以它命名的子目錄（見
> `device/_template/_type_template/`）**並在 `mr_type.py` 的對照表加一列** —— 目錄名
> 只能用小寫英數與底線，所以 `[New Test Case]` 這種給人看的寫法要靠那張表對過來。
"""

# 這個 device 的版本，會印在報告末尾的出處資訊裡。**必填。**
#
# 版號 vA.B.C：前兩碼指出這個 device 照的是哪一代通用層，第三碼是它自己動過的次數。
# 完整規則見 docs/contributing.md 的「版號」一節 —— 那裡是唯一的來源，這裡只放值。
DEVICE_VERSION = "v2.0.0"

# `new_test_case` 那張 Pattern 資訊表的**第一列**叫什麼：MR 指到的那張單。
#
# 改這一行就改了報告上那一格，不必動擴充腳本。沒有宣告時用那一支自己的預設值
# （`Task`），所以拿掉這一行不會壞。
#
# 這是 **sd 自己的宣告**，不是通用層認得的項目 —— 通用層只讀 VERSION、STRICT_TYPE 與
# CODE_REVIEW_SOURCE_HEADING 三個。讀它的人是 `new_test_case/merge_to_md.py`：那一支
# import 這個套件再 getattr，所以這裡要加第二、第三個宣告也是同一個做法，不需要改通用層。
#
# 欄位的標題（`項目`／`內容`／`狀態`）在 `new_test_case/merge_to_md.py` 最上面，與這一行
# 分開放：那三個字決定表格的形狀，改了要連帶看那一支怎麼填每一列，所以留在它旁邊。
NEW_TEST_CASE_TASK_LABEL = u"Task"

# `new_test_case` 那張表的**第二列**：另一張用 JQL 找出來的 JIRA 單。
#
# **這裡只寫 JQL 固定的那一段。** 隨每一筆 MR 變動的條件由 `new_test_case/summary.py`
# 接上去 —— 預設接的是**主單標題的最後一段**：
#
#     主單標題 SSD-FW-Secure Erase
#     宣告     project = PPS AND issuetype = "Test Plan"
#     實際送出 project = PPS AND issuetype = "Test Plan" AND summary ~ "Secure Erase"
#
# 接最後一段而不是整個標題，是因為測試計畫的標題不帶開發單的產品與模組前置詞，兩者
# 共有的就是那一段功能名稱。切法在 `new_test_case/summary.py` 的 `_issue_title()`，
# 改分隔字元改那一支；切不出來時（標題除了分隔字元以外沒有字）退回接整個標題。
#
# 接上去的文字會被包成 JQL 的字串常量並跳脫（反斜線與雙引號）—— 標題裡一個雙引號就會讓
# 整段 JQL 語法錯誤，而 JIRA 回的 400 會指著一段你從沒寫過的查詢字串。
#
# **要自己決定那一段接在哪裡**（例如查詢帶 ORDER BY，或變動的條件不在最後）就用佔位符：
#
#     {summary}   主單標題的最後一段（與自動接上去的是同一個值）
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

# 第二列叫什麼：上面那條 JQL 找出來的那張單。
NEW_TEST_CASE_TEST_CASE_LABEL = u"Test case"

# 報告 Check list 那一節的兩條狀態檢查，各自的期望值。
#
# 狀態不是那一個就在報告上標 ❌，**但不會讓任何一步失敗** —— 那一節是給 reviewer 的
# 資訊，兩張單該不該放行是他的判斷。
#
# 比對忽略大小寫與前後空白，不做模糊比對：`In Review` 與 `in review` 是同一個狀態，
# 與 `Review` 不是。
#
# 兩條分開宣告，因為 Task 與 Test case 常常走不同的工作流；目前兩者剛好都是 In Review，
# 但那是現況，不是同一件事。沒有宣告時用 `new_test_case/merge_to_md.py` 的預設值。
NEW_TEST_CASE_EXPECTED_TASK_STATUS = u"In Review"
NEW_TEST_CASE_EXPECTED_TEST_CASE_STATUS = u"In Review"

# 這裡**還沒有宣告** STRICT_TYPE 與 CODE_REVIEW_SOURCE_HEADING，兩者都沿用預設值。
#
# STRICT_TYPE 未宣告即 False：標題解不出種類、或解出的名稱這裡沒有對應目錄時，走通用版
# 而不失敗。「MR 一定要標明種類」是一條團隊紀律 —— 要不要強制由 SD 自己決定，而目前只有
# `new_test_case` 一個種類，宣告 True 會讓其餘每一筆 MR 都在步驟 2 失敗。
#
# 不要為了「寫清楚」先照抄一份與預設值相同的宣告 —— 日後通用層改了預設值，這裡抄的那
# 一份不會跟著動，而且不會有任何徵兆。
#
# 可宣告的項目及其預設值見 `device/_template/__init__.py` 的註解。
