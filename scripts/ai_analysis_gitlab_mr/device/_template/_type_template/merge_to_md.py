#!/usr/bin/env python3
"""某一個種類專屬的步驟 5 鉤子：AI 分析那一段的版面。

**與 device 層的 merge_to_md.py 是同一個介面** —— 一樣的 render(inputs)，一樣只負責
「AI 分析標題底下那一段」。

標題那一行、原始描述那一段、分隔線與末尾的出處都由入口腳本寫出，**種類不能改變它們**。
那一行標題同時是下一輪切出原始描述的邊界，只能有一個來源。

最省事的作法是複製 default/merge_to_md.py 過來改版面。inputs 多一個 mr_type，內容是
選中這一份的種類名稱。

輸入已經過 contract.validate_analysis() 驗證，所以這裡不必再檢查型別。
"""

import ai_analysis_gitlab_mr as contract


def render(inputs):
    """回傳接在 AI 分析標題底下的那一段 markdown。"""
    analysis = inputs["analysis"]
    return u"\n\n".join([
        u"## （這個種類專屬的版面）",
        contract.plain(analysis.get("overview")),
    ])
