#!/usr/bin/env python3
"""sd device 的步驟 2 擴充腳本：從 Merge Request 標題擷取出 JIRA key。

SD 的規則是 key 寫在標題的**第一個**方括號裡：

    [PPS-1234] 修正重試上限的競態      ->  PPS-1234
    mod:[PPS-1234][Bug] 調高上限       ->  PPS-1234

第二個方括號是種類，由 `mr_type.py` 取 —— 兩支是對稱的一對，同一份標題、同一次連線，
只是各自取不同的位置。

**這裡不判定有效性**，擷取到什麼就回什麼。所以 `[WIP] [PPS-1234] …` 這種標題，這一支會
回 `WIP`。判定在步驟 3 的 summary 擴充腳本；sd 沒有自己的 `summary.py`，所以判定沿用
default 的樣式（`^[A-Z][A-Z0-9]*-[0-9]+$`），那個 `WIP` 於是被判為 `invalid`，報告的
「詳細資料」那一節不出現、步驟 4 的程式碼審閱也整段略過。

**只有 auto 模式會呼叫這裡。** 三種模式的分派在入口腳本：不使用時不呼叫、手動指定時用
使用者輸入的值。

這一支是 **sd 自己的規則**，不是任何人的後備：default 不擷取 JIRA key，所以沒寫這一支的
device 拿到的一律是空字串。
"""

import re

# 第一個方括號裡的內容。非貪婪，且不跨行 —— 標題本來就是一行。
_FIRST_BRACKET = re.compile(r"\[([^\]\n]*)\]")


def extract(mr):
    """擷取出標題第一個方括號裡的字串；沒有就回空字串。

    收到的 mr 是整理過的欄位（不是 GitLab 原樣的物件），與 mr_type 擴充腳本相同：

        title / source_branch / target_branch / description / repo / mr_iid
    """
    title = mr.get("title") or ""

    match = _FIRST_BRACKET.search(title)
    if not match:
        # 沒有方括號的標題很常見，那不是錯誤：回 "" 就是「這一筆沒有 key」。不要回
        # None，也不要自己回 "NONE" —— 對外的表示法由入口腳本統一。
        return ""

    # `[ PPS-1234 ]` 這種寫法會帶空白進來，不去掉的話組出來的 JIRA 網址會壞掉。
    return match.group(1).strip()
