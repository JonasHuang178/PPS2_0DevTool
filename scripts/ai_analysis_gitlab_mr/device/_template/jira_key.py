#!/usr/bin/env python3
"""步驟 2 的鉤子：從 Merge Request 抽出 JIRA key。

**只有 auto 模式會呼叫這裡。** 三種模式的分派在入口腳本：不使用時不呼叫、手動指定時
用使用者輸入的值。你只要處理「怎麼從這個 MR 抽出來」。

**這裡不判定有效性。** 抽到什麼就回什麼，判定在步驟 3 的 summary 鉤子 —— 判定規則與
抽取規則同屬一個 device，放在一起才不會各自漂移。
"""


def extract(mr):
    """從 Merge Request 的資料抽出 JIRA key。

    mr 是整理過的欄位，**不是** GitLab 原樣的回應物件：

        mr["title"]           標題
        mr["source_branch"]   來源分支
        mr["target_branch"]   目標分支
        mr["description"]     描述（已扣掉上一輪的 AI 分析）
        mr["repo"]            專案，namespace/project
        mr["mr_iid"]          編號

    回傳一個字串。抽不到就回空字串 —— 不要回 None，也不要自己回 "NONE"，那個表示法
    由入口腳本統一。
    """
    raise NotImplementedError("把這裡換成你的抽取邏輯")
