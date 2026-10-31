#!/usr/bin/env python3
"""sd / new_test_case 的步驟 5 擴充腳本：AI 分析那一段的版面。

版面沿用 sd 的通用版（也就是 default 那一套），只有兩處不同：

    ## Summary          <- 與通用版一字不差
    <AI 的工單總結>

    ## 工單狀態          <- 通用版的 ## Code Changes 換成這張表
    | 項目 | 內容 | 狀態 |
    |---|---|---|
    | JIRA 單 | `PPS-1234` | In Progress |

    ## 詳細資料          <- 與通用版一字不差（只在 key 有效時出現）

`## Code Changes` 拿掉是因為這個種類不產生任何 finding（見 `summary.py`：prompt 不放
diff、回傳的 `mrDiff` 永遠是空的）。通用版對空的 `mrDiff` 本來就整段不印，所以拿掉不是
為了避免空區塊，而是**那個位置要放別的東西** —— 這個種類的讀者要知道的是「這份總結是讀
哪一張單子來的、到底有沒有讀到」，而那在通用版裡沒有位置可放。

用表格而不是一行標題：三個值（哪一個項目、哪一張單、它在 JIRA 上是什麼狀態）各有自己的
欄位，掃一眼就分得出哪個是哪個；塞進一行標題則得用標點把它們隔開，而那一行同時還要承載節名。

「狀態」是**JIRA 上那張單子的狀態**（`In Progress` / `Done`），不是本工具對 key 的判定。
「項目」那一欄的字樣由 `device/sd/__init__.py` 的 `NEW_TEST_CASE_ITEM_LABEL` 決定，改字樣
不必動這一支（沒宣告就用 `DEFAULT_ITEM_LABEL`）。

**只負責「AI 分析標題底下那一段」。** 那一行 `# AI 分析結果`、原始描述、程式碼審閱那一段
與末尾的出處都由入口腳本寫出 —— 這一支改不到也不必管。那一行標題不歸這裡管，是因為它
同時是下一輪切出原始描述的邊界。

輸入已經過 `contract.validate_analysis()` 驗證，所以這裡不再檢查型別。
"""

import ai_analysis_gitlab_mr as contract

# 版面的其餘部分與 **sd 自己那一層**（`device/sd/merge_to_md.py`）一模一樣，所以明著沿用
# 它的那幾支，不複製。
#
# 複製一份就是宣告「從今天起與它無關」—— 之後 sd 改了 finding 的排版或 diff 的收合方式，
# 這份複本不會跟著動，而且不會有任何徵兆。
#
# **指向 sd 而不是 default**：sd 那一層是這個 device 的版面，`pattern_issue/` 也是回退到
# 它。這個種類只是在那個版面之上換掉一節，所以它要跟著 sd 走。
from ai_analysis_gitlab_mr.device.sd import merge_to_md as base


# 總覽那一節的標題。**與通用版一字不差**，所以直接取用它的那一行，不自己寫一份字面文字 ——
# 兩邊各寫一份的話，通用版哪天改了字樣（`## Summary` -> `## 總覽`），這個種類會悄悄落單。
SUMMARY_HEADING = base.SUMMARY_HEADING

# 工單狀態那一節。
#
# 三個欄位標題決定表格的形狀，所以與填值的 _status_table() 放在一起 —— 改欄位要連帶看
# 每一列怎麼填。「項目」那一欄的**值**則是 device 的宣告（見 _item_label），改字樣不必
# 動這一支。
STATUS_HEADING = u"## 工單狀態"
STATUS_TABLE_HEADER = u"| 項目 | 內容 | 狀態 |\n|---|---|---|"

# 兩列「項目」欄的預設字樣。device 沒有宣告對應的名字時用這些。
DEFAULT_ITEM_LABEL = u"JIRA 單"
DEFAULT_RELATED_LABEL = u"相關工單"

# 「內容」那一格：沒有可用的 key 時印什麼。
#
# ⚠️ `invalid` **不印那個被拒絕的原值**。規格明文要求報告裡任何地方都不得出現它
# （sd 取標題第一個方括號，那裡常常是 `WIP` —— 印出來會讓讀者以為 WIP 是一張單子）。
# 要查原值就看 `03_summary.json` 的 `jira_key`。
_KEY_CELL = {
    contract.JIRA_STATE_NONE: u"（未指定）",
    contract.JIRA_STATE_INVALID: u"（不是合法的單號）",
}

# 「狀態」那一格：取不到 JIRA 上的狀態時印什麼。
#
# 兩種情況分開寫，因為讀者的下一步不同：根本沒有單子可查，與有單子但狀態沒拿到（查詢失敗、
# 或那份產物是加這個欄位之前產生的）。
NO_ISSUE_CELL = u"—"
UNKNOWN_STATUS_CELL = u"（未取得）"

# 第二列「內容」那一格：查了但沒有符合的單子，與根本沒查。
#
# 三者分開，因為使用者的下一步不同：查無要去看 JQL 的條件寫對了沒；未查詢要去看
# `NEW_TEST_CASE_RELATED_JQL` 這個宣告有沒有填（或這一筆根本沒有主單可代入）；查詢失敗
# 是 JQL 送出去被 JIRA 退回、或沒設 JIRA 連線，原因在診斷輸出那一行。
NOT_FOUND_CELL = u"（查無）"
NOT_SEARCHED_CELL = u"（未查詢）"
SEARCH_FAILED_CELL = u"（查詢失敗）"


def _label(name, default):
    """「項目」那一欄要印的字樣，取自 device 的宣告。

    讀法與通用層讀 `CODE_REVIEW_SOURCE_HEADING` 同一個形狀：**宣告沒寫就用預設值**，所以
    拿掉 `device/sd/__init__.py` 那幾行不會壞，而其他 device 若哪天也用這個種類的版面，
    不必為此補宣告。

    用 getattr 而不是 import 那個名字：import 不存在的名字會在**載入時**就讓這一支失敗，
    而一個選填的宣告缺了不該讓整份報告產不出來。
    """
    from ai_analysis_gitlab_mr.device import sd

    return contract.plain(getattr(sd, name, "")) or default


def _cell(text):
    """把值放進儲存格。

    `|` 要跳脫 —— JIRA 的狀態是那一端自己定義的字串，裡面出現一個垂直線就會把那一列切成
    多欄，而表格仍然「成功」產出，只是從那一列起全錯。key 本身受樣式約束不會有，但同一個
    函式一起管掉比記住哪一格安全省事。
    """
    return contract.plain(text).replace(u"|", u"\\|")


def _status_table(analysis):
    """工單狀態那張表。永遠印出來 —— 連「沒有指定」也要印。

    這個種類的整份總結就是「那張單子說了什麼」，所以「讀的是哪一張、它現在什麼狀態」是這份
    報告的前提，不是可有可無的補充。沒讀到時整段總結講的會是「沒有可以總結的內容」，而這張
    表就是那句話的原因。空著不印的話，讀者只會看到一段沒頭沒尾的說明。

    「狀態」指的是**JIRA 上那張單子的狀態**（`In Progress` / `Done`），不是本工具對 key 的
    判定 —— 後者已經由「內容」那一格表達（印得出 key 就是採用了它）。

    那個值由步驟 3 隨產物帶過來（`jira_status`，見 `summary.py` 的 `_body`）。步驟 5 拿不到
    JIRA：它沒有憑證，也刻意沒有任何外部依賴。欄位缺了就印「（未取得）」—— 加這個欄位之前
    產生的 `03_summary.json` 重跑步驟 5 會走到這一條。

    `ok` 而 key 是空的時候（`validate_analysis()` 不保證兩者一致）退回「未指定」的字樣，
    否則那一格會是空白的儲存格。
    """
    state = contract.plain(analysis.get("jira_state"))
    key = contract.plain(analysis.get("jira_key"))
    has_issue = state == contract.JIRA_STATE_OK and bool(key)

    if has_issue:
        content_cell = u"`%s`" % _cell(key)
    else:
        # 認不得的狀態一律當成「沒有指定」。這裡不為此失敗：狀態的值域由
        # validate_analysis() 把關，走到這裡還認不得的話，報告少一點資訊比整份產不出來好。
        content_cell = _KEY_CELL.get(state,
                                     _KEY_CELL[contract.JIRA_STATE_NONE])

    if not has_issue:
        status_cell = NO_ISSUE_CELL
    else:
        status_cell = _cell(analysis.get("jira_status")) or UNKNOWN_STATUS_CELL

    return u"\n".join([
        STATUS_TABLE_HEADER,
        u"| %s | %s | %s |" % (_cell(_label("NEW_TEST_CASE_ITEM_LABEL",
                                            DEFAULT_ITEM_LABEL)),
                               content_cell, status_cell),
        _related_row(analysis),
    ])


def _related_row(analysis):
    """第二列：用 JQL 找出來的那張單。

    那一列**永遠印出來**，連「沒查」也印 —— 與第一列同一條理由：這張表回答的是「這份總結
    的前提是什麼」，而「有沒有找到相關工單」本身就是答案的一部分。整列抽掉的話，表格會隨
    JQL 有沒有命中而長短不一，讀的人以為是版面壞了。

    值由步驟 3 隨產物帶過來（`related_issue`，見 `summary.py` 的 `_search_related`）——
    步驟 5 不連 JIRA。欄位整個缺了（加這一列之前產生的 `03_summary.json`，或別的 device
    的產物）時 `.get()` 給空 dict，`searched` 為假，印「（未查詢）」。
    """
    related = analysis.get("related_issue") or {}

    key = contract.plain(related.get("key"))
    if key:
        content_cell = u"`%s`" % _cell(key)
        status_cell = _cell(related.get("status")) or UNKNOWN_STATUS_CELL
    elif not related.get("searched"):
        content_cell = NOT_SEARCHED_CELL
        status_cell = NO_ISSUE_CELL
    elif related.get("error"):
        # 失敗的原因不印在報告上：那是部署或 JQL 的問題，讀報告的人幫不上忙，而原因
        # 可能夾帶一長串 JIRA 的錯誤訊息。它在診斷輸出與該步的 .log 裡。
        content_cell = SEARCH_FAILED_CELL
        status_cell = NO_ISSUE_CELL
    else:
        content_cell = NOT_FOUND_CELL
        status_cell = NO_ISSUE_CELL

    return u"| %s | %s | %s |" % (_cell(_label("NEW_TEST_CASE_RELATED_LABEL",
                                               DEFAULT_RELATED_LABEL)),
                                  content_cell, status_cell)


def render(inputs):
    """把步驟 3 的結構化分析渲染成報告裡「AI 分析結果」底下的內容。

    版面：

        ## Summary
        - <總覽第一句>
        - <總覽第二句>

        ## 工單狀態
        | 項目 | 內容 | 狀態 |
        |---|---|---|
        | JIRA 單 | `PPS-1234` | In Progress |

        ## 詳細資料
        - For more information, please refer to [PPS-1234](<網址>)

    總覽排成逐行的清單（`contract.as_list()`，與通用版同一個函式）—— AI 回來的是一句接一句
    的一整段，在結果視窗會折成一片文字牆、貼到討論串則是一個段落。斷行在這裡做而不是改掉
    產物裡的原文：產物存的是 AI 說了什麼，版面由它推導。

    最後那一節沿用通用版的判定（只在採用了有效的 key 時出現）。**狀態不在這裡重新判定**，
    `jira_state` 由步驟 3 判定並隨結構帶過來。

    整段沒有任何內容時回空字串 —— 入口腳本據此判定「沒有可合併的內容」。**那張表不足以撐起
    這一段**：一份只有那一列、沒有任何總結的報告會被當成成功的產出交出去，而它什麼都沒說。這與通用版「只有詳細資料那一節時整段不放」是同一條規則。
    """
    analysis = inputs["analysis"]

    blocks = []

    overview = contract.as_list(analysis.get("overview"))
    if overview:
        blocks.append(SUMMARY_HEADING)
        blocks.append(overview)
        blocks.append(STATUS_HEADING)
        blocks.append(_status_table(analysis))

    # 指引放最後，而且只在有其他內容時才放（見通用版的同一段）。
    jira = base._jira_entry(analysis)
    if blocks and jira:
        blocks.append("## 詳細資料")
        blocks.append(jira)

    return "\n\n".join(blocks)
