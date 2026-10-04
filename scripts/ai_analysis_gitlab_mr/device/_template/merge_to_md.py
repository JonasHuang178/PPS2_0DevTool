#!/usr/bin/env python3
"""步驟 5 的鉤子：AI 分析那一段的版面。

**你只負責「AI 分析標題底下那一段」。** 標題那一行、原始描述那一段、分隔線與末尾的
出處都由入口腳本寫出。

那一行標題不給你碰是有原因的：它同時是下一輪切出原始描述的邊界。如果每個 device 都能
改寫它，某個 device 把它寫成別的字，下一輪就找不到邊界 —— 整份舊報告被當成原始描述，
再接上新的一段，於是每跑一次疊一段，而每一步都回報成功。
"""

import ai_analysis_gitlab_mr as contract


def render(inputs):
    """把分析內容排成 markdown。

    inputs 是一個 dict：

        analysis          分析內容（已驗證過的結構）
        description       原始描述那一段的內容
        code_review       風險評估總表的 markdown；沒有就是空字串
        code_review_info  程式碼審閱的完整結構（附件檔名／上傳時間／作者／網址／
                          總表／失敗訊息），沒有那一段時是 None
        repo              專案，namespace/project
        mr_iid            編號
        device            這個 device 的名稱

    description 與 code_review 給你**唯讀參考**（例如想讓分析對照描述的哪幾點），
    但它們各自的區段由入口腳本輸出，你回傳的內容不該重複它們。

    code_review_info 是 code_review 的來源，多給的 —— 想在分析裡提到「總表是哪一份
    附件」時從那裡取檔名或連結。程式碼審閱**那一段本身**（標題、日期／作者／連結三行、
    總表）一律由入口腳本寫出，不因 device 而異，你改不到也不必管。

    回傳一個字串。

    ## JIRA 那三個欄位

    `analysis` 裡有這三個，想在你的版面裡提到那張單子就用它們：

        jira_state  "ok"（採用了）／"none"（沒要用）／"invalid"（抽到但不是 key）
        jira_key    該次採用的 key；invalid 時是**被拒絕的原值**
        jira_url    組好的網址；沒設 JIRA_SERVER_URL 時是空字串

    **這是報告裡唯一能提到那張單子的地方。** 出處那一段曾經印過 `JIRA: <key>`，後來
    移除了，所以你不寫、報告就完全不會提它 —— 而那張單子往往正是這份分析的前提。
    `default/merge_to_md.py` 的做法是在最後加一節 `## 詳細資料`，放一行指向它的指引，
    只在 `jira_state == "ok"` 且 key 非空時出現。

    **狀態不要自己重新判定**，也不要自己呼叫 `contract.jira_url()`：兩者都由步驟 3 填好
    帶過來，重算一次就多一個可能與產物不一致的來源。

    ⚠️ **你這一份一旦存在，就完全接管了那一段的版面** —— `default` 的那一節不會自動
    出現在你的報告裡。要的話得自己寫（三行：判狀態、取 key 與 url、組一行）。

    ## 請用這些，不要自己重寫

        contract.plain(value)           None 與非字串收斂成字串。不用的話報告會印出 "None"
        contract.as_list(text)          把一整段文字排成逐行的清單
        contract.fence_for(code)        算程式碼圍籬的長度
        contract.MAX_FINDING_DIFF_BYTES 單筆 diff 的位元組上限

    `fence_for()` 特別重要：寫死三個反引號的話，內容本身含有反引號的 diff（改到
    markdown 檔就會）會讓程式碼區塊提前結束，後面的內容變成一般文字 —— 而報告仍然
    「成功」產出。

    `as_list()` 用在總覽那種「一句接一句的一整段」上：AI 回來的總覽通常是一段，在結果
    視窗會折成一片文字牆。它會尊重來源已有的結構（自帶換行、自帶有序編號），切不動就
    原樣回傳，所以可以無條件套用。**不要在步驟 3 把原文改掉** —— 產物存的是 AI 說了
    什麼，版面在這一步決定；改了原文，想換版面就只能重新呼叫一次 AI。
    """
    lines = []
    overview = contract.plain(analysis_overview(inputs))
    if overview:
        lines.append(overview)
    return "\n\n".join(lines)


def analysis_overview(inputs):
    return (inputs["analysis"] or {}).get("overview")
