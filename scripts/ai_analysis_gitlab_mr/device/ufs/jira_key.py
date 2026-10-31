#!/usr/bin/env python3
"""ufs device 的步驟 2 擴充腳本：從 Merge Request **描述**擷取出 JIRA key。

慣例是描述的第一行寫一條指向該議題的網址，key 就是網址路徑的最後一段：

    https://jira.example.com/browse/PPS-1234      ->  PPS-1234

描述可能有很多行（後面常接著改了什麼、怎麼測），所以**只看第一行**，其餘一概不看。

**這裡不判定有效性**，擷取到什麼就回什麼 —— 判定在步驟 3 的 summary 擴充腳本。ufs 沒有
自己的 `summary.py`，所以判定沿用 default 的樣式（見 `device/ufs/__init__.py`）。

這一支是 **ufs 自己的規則**，不是後備：default 不擷取 JIRA key，所以沒寫這一支的 device
拿到的一律是空字串。
"""

import re

from script_utils import logger

# 第一行必須長得像一條 http(s) 網址，否則視同沒有 key。
#
# 不檢查的話，描述第一行是一句中文（「修正重試上限」）時，底下依 `/` 切割的規則會把
# 整句話當成 key 回出去 —— 而那個字串會一路走到 jira_state 判定才被擋下，報告上只看得到
# 「詳細資料那一節不見了」，指不出成因。先認出「這不是網址」，回空字串才是誠實的答案。
_HTTP_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def _first_line(text):
    """第一個**非空白**的行，已去除頭尾空白；整段都是空白時回空字串。

    取第一個非空白行而不是字面上的第 0 行：描述開頭多一個空行在 GitLab 的編輯器裡看不
    出來，而把它當成「沒有 key」會是一個使用者完全看不見的失敗。
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def extract(mr):
    """從描述第一行的網址取出最後一段當 JIRA key；取不到就回空字串。

    mr 是整理過的欄位（title / source_branch / target_branch / description / repo /
    mr_iid），這一支只看 description。
    """
    line = _first_line(mr.get("description") or "")

    if not line:
        logger.debug("ufs/jira_key：描述沒有任何內容，視為沒有 JIRA key")
        return ""

    if not _HTTP_SCHEME_RE.match(line):
        logger.debug("ufs/jira_key：描述第一行不是 http(s) 網址（%r），視為沒有 JIRA key",
                     line)
        return ""

    # 先切掉 scheme 再依 `/` 切割。整串直接找最後一個 `/` 也會得到同樣的答案，但少了這
    # 一步就分辨不出「只有主機、沒有路徑」那一種 —— `https://jira.example.com` 的最後
    # 一段會是主機名稱，而那會變成一個看起來像答案的錯值。
    path = _HTTP_SCHEME_RE.sub("", line)

    # 尾端的 `/` 要去掉，否則最後一段是空字串。複製網址時多帶一個斜線很常見。
    path = path.rstrip("/")

    if "/" not in path:
        logger.debug("ufs/jira_key：網址只有主機沒有路徑（%r），視為沒有 JIRA key", line)
        return ""

    key = path.rsplit("/", 1)[-1]

    # 查詢字串與片段（`?filter=…`、`#comment-1`）刻意**不處理**：規則就是依 `/` 切割取
    # 最後一段。真的貼進一條帶查詢字串的網址時，擷取出的 key 會因為不符樣式而被判為
    # invalid，而不是靜靜地指向另一張議題。要收這種寫法就在這裡多切一刀。
    logger.debug("ufs/jira_key：自描述第一行擷取出 %r", key)
    return key
