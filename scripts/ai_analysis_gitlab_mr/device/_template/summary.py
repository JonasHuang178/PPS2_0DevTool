#!/usr/bin/env python3
"""步驟 3 的鉤子：AI 分析。

這是三個鉤子裡最自由的一個 —— 要問 AI 什麼、怎麼解析回應、組出什麼分析內容，全部由
你決定。入口腳本只負責信封、參數、落檔與驗證。
"""

import ai_analysis_gitlab_mr as contract


def analyze(inputs):
    """產生這次分析的內容。

    inputs 是一個 dict：

        description     MR 的原始描述（已扣掉上一輪的 AI 分析）
        jira_key        該次採用的 key；沒有就是空字串
        jira_mode       none / manual / auto —— 讓你分辨 key 是抽的還是使用者填的
        ai_mode_name    使用者選的 AI 模式名稱
        ai_api_url      AI 端點
        ai_api_key      AI 金鑰
        ai_model        模型名稱
        repo            專案，namespace/project
        mr_iid          編號
        device          這個 device 的名稱

    **必須回傳 contract.analysis_body(...) 的結果。** 不要自己組 dict，也不要填
    schema_version —— 版本由入口腳本蓋章。回傳之後入口會立刻驗證，不符合就在這一步
    失敗（而不是兩步之後的渲染），訊息會指名是哪個 device 的哪個檔案。

    JIRA 的有效性由**你**判定：

        通過檢查    jira_state=contract.JIRA_STATE_OK，jira_key 放那個 key
        沒有要用    jira_state=contract.JIRA_STATE_NONE
        抽到但無效  jira_state=contract.JIRA_STATE_INVALID，jira_key 放**被拒絕的原值**

    最後一項很重要：報告會印出那個原值（`JIRA: WIP (invalid)`），讀的人一眼就知道標題
    的第一個方括號放錯了東西。只說「無效」等於要人自己猜。
    """
    return contract.analysis_body(
        overview=u"（你的總覽）",
        model=inputs["ai_model"],
        jira_key=inputs["jira_key"],
        jira_state=contract.JIRA_STATE_NONE,
        mr_diff={
            u"path/to/file.cpp": [
                contract.finding(
                    title=u"（一句話說明發現什麼）",
                    reason=u"（為什麼）",
                    diff_code=u"@@ ...",          # 沒有就省略
                ),
            ],
        },
    )
