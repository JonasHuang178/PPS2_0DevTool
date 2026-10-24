#!/usr/bin/env python3
"""default device 的步驟 2 擴充腳本：**不擷取** JIRA key。

default 刻意不猜 JIRA key 寫在哪裡 —— 標題慣例是各產品線自己的約定，猜錯的症狀是報告上
印出一個看似有效、其實是從別的方括號撈來的 key，而那要看報告才看得見。所以這裡一律回
空字串，等於「這筆 MR 沒有 JIRA key」。

要自動擷取的 device 自己寫一份 `jira_key.py`（規則見 `device/_template/jira_key.py`）。
在那之前，JIRA 模式選「手動指定」照樣可用 —— 手動的值由入口腳本處理，根本不會呼叫這裡。

回空字串不是錯誤：入口腳本會把 jira_key 記成「(無)」，流程照常往下走。
"""


def extract(mr):
    """一律回空字串 —— default 不擷取 JIRA key。

    收到的 mr 是整理過的欄位（title / source_branch / target_branch / description /
    repo / mr_iid），這裡刻意不看。
    """
    return ""
