#!/usr/bin/env python3
"""ssd device 的步驟 2 擴充腳本：從 Merge Request 標題擷取出 JIRA key。

慣例是 key 寫在標題的第一個方括號裡：

    [PPS-1234] 修正重試上限的競態      ->  PPS-1234

**這裡不判定有效性**，擷取到什麼就回什麼。判定在 ssd/summary.py —— 擷取規則與判定規則
同屬一個 device，放在一起才不會各自漂移。所以像 `[WIP] [PPS-1234] ...` 這種標題，這裡會
回 `WIP`，由 ssd/summary.py 判定它不合格。

這一支是 **ssd 自己的規則**，不是後備：default 不擷取 JIRA key，所以沒寫這一支的 device
拿到的一律是空字串。
"""

import re

# 第一個方括號裡的內容。非貪婪，且不跨行 —— 標題本來就是一行。
_FIRST_BRACKET = re.compile(r"\[([^\]\n]*)\]")


def extract(mr):
    """擷取出標題第一個方括號裡的字串；沒有就回空字串。"""
    title = mr.get("title") or ""
    match = _FIRST_BRACKET.search(title)
    if not match:
        return ""
    return match.group(1).strip()
