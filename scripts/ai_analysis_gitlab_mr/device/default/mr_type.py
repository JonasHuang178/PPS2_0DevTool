#!/usr/bin/env python3
"""default device 的步驟 2 鉤子：抽出 Merge Request 的種類。

種類決定步驟 3 與步驟 5 會用哪一份 summary.py 與 merge_to_md.py。

**這是所有 device 的起點，也是後備** —— 沒有自己 mr_type.py 的 device 都用這一份。

default 的規則：標題的**第二個**方括號。第一個留給 JIRA key（見 jira_key.py），所以

    mod:[PPS-1234][Bug] 修正重試上限
        ^^^^^^^^^^ 第一個：JIRA key
                  ^^^^^ 第二個：種類  -> "Bug"

抽不到就回空字串 —— 那不是錯誤。回空字串的後果是走該 device 的通用版；除非該 device
在 __init__.py 宣告了 STRICT_TYPE = True，那時入口腳本會失敗。**這個判斷不在這裡做**，
這一支只負責「讀出來」。

回傳的字串會被入口正規化（去空白、轉小寫）並檢查形狀，所以這裡不必自己處理大小寫。
不合法的字串（`[緊急]`、`[bug fix]`）視同沒有種類。

標題格式與這一份不同的 device，請自己寫一份 mr_type.py。順帶提醒：格式不同通常也意味著
JIRA key 的位置不同，**兩個鉤子多半要一起寫** —— 只寫一支的話，另一支會沿用這裡的規則，
安靜地抽到錯的東西。
"""

import re

# 標題裡所有的方括號內容，依出現順序。
#
# [^][]* 而不是 .*? ：巢狀或未閉合的括號不該被當成一組。標題是人手打的，`[a[b]c]`
# 這種東西出現得比想像中多。
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")

# 取第幾個方括號（0 起算）。抽成常數是因為這是這一份規則唯一的可變之處 ——
# 取第三個的 device 只要複製這個檔案並改這一行。
_BRACKET_INDEX = 1


def extract(mr):
    """自 Merge Request 的欄位抽出種類。回傳字串；沒有就回空字串。

    收到的 mr 是整理過的欄位（不是 GitLab 原樣的物件），與 jira_key 鉤子相同：

        title / source_branch / target_branch / description / repo / mr_iid
    """
    title = mr.get("title") or ""
    found = _BRACKET_RE.findall(title)

    if len(found) <= _BRACKET_INDEX:
        return ""

    return found[_BRACKET_INDEX]
