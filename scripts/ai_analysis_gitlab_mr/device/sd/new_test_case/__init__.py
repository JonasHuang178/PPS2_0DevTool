#!/usr/bin/env python3
"""sd / new_test_case 這個種類共用的東西：主單標題的約定。

這個種類的單子，標題寫成 `<產品>-<模組>-<功能>`，而**最後一段就是這張單在講什麼**：

    SSD-FW-Secure Erase
            ^^^^^^^^^^^^ 這一段

兩步都要它，而且必須是同一段：

    步驟 3  相關工單的 JQL 比對的是這一段（`summary.py`）
    步驟 5  工單狀態那一節的標題用這一段（`merge_to_md.py`）

所以切法放在這裡，不放在其中任何一支。兩支各切一次的話就有兩份規則，而兩份必然漂移 ——
漂移的形狀還特別難看：報告的標題寫著一個功能，底下那一列卻是用另一個字串查出來的單子，
而兩步都會回報成功。

**種類目錄本來不需要 `__init__.py`**（namespace package，「放一個目錄進去」就是新增一個
種類）。這裡放一個，純粹是因為有東西要讓同一個種類的兩支擴充腳本共用；放一個不影響種類
的辨識（`device.types()` 只數目錄）。
"""

import ai_analysis_gitlab_mr as contract

# 切標題的分隔字元。抽成常數是為了改它不必讀函式的本體。
TITLE_SEPARATOR = u"-"


def issue_title(issue_summary):
    """主單標題的最後一段；推導不出來時回空字串。

        SSD-FW-Secure Erase    ->  Secure Erase
        SSD-Secure Erase       ->  Secure Erase
        Secure Erase           ->  Secure Erase     （沒有分隔字元：整行就是最後一段）
        SSD-FW-                ->  u""              （以分隔字元結尾）
        u""                    ->  u""

    取**最後一段**，所以標題裡有幾個分隔字元都無所謂，一個都沒有也無所謂 —— 整行就是最後
    一段。這比「沒有分隔字元就當作推導失敗」好：單子標題怎麼寫是人的約定，不是這一步有資格
    強制的格式，而一個只寫了功能名稱的標題正好是最清楚的那種。

    回空字串的只有兩種：標題本身是空的（取不到那張單子），以及切完之後什麼都不剩。呼叫端
    各自決定那時候要怎麼辦 —— 步驟 5 退回固定的節名，步驟 3 退回用整個標題去查。

    空白在這裡一併收掉（不只首尾）：`plain()` 只做首尾 strip，而標題是人打進 JIRA 的字，
    中間夾一個折行就會讓步驟 5 那一行 markdown 標題斷掉、後半段變成內文。
    """
    summary = contract.plain(issue_summary)
    return u" ".join(summary.split(TITLE_SEPARATOR)[-1].split())
