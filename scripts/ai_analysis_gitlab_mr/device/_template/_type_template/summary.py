#!/usr/bin/env python3
"""某一個種類專屬的步驟 3 鉤子：AI 分析。

**與 device 層的 summary.py 是同一個介面** —— 一樣的 analyze(inputs)、一樣的 inputs、
一樣要回 contract.analysis_body(...) 的結果。唯一的差別是它只在這個種類被選中時執行。

最省事的作法是複製 default/summary.py 過來，只改 ROLE_PROMPT 與 PROMPT_TEMPLATE。
那一份是可以直接跑的完整實作，prompt 都在最上面幾個字串常數裡。

想沿用別人寫好的邏輯、只換 prompt，就明著 import：

    from ai_analysis_gitlab_mr.device.default import summary as base

    def analyze(inputs):
        base.ROLE_PROMPT = MY_ROLE_PROMPT     # 只在這個行程內有效
        return base.analyze(inputs)

介面的完整說明見 ../summary.py（device 層的範本）。inputs 多一個欄位：

    mr_type    選中這一份的種類名稱。種類專屬的實作通常用不到它 —— 它是給通用的
               那一份用的，讓它能在不分開檔案的情況下微調。
"""

import ai_analysis_gitlab_mr as contract


def analyze(inputs):
    """產生這次分析的內容。回傳 contract.analysis_body(...) 的結果。"""
    return contract.analysis_body(
        overview=u"（這個種類專屬的總覽）",
        model=inputs.get("ai_model"),
        jira_key=inputs.get("jira_key"),
        jira_state=contract.JIRA_STATE_NONE,
        mr_diff={},
    )
