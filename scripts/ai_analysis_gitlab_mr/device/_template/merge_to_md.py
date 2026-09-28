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

        analysis        分析內容（已驗證過的結構）
        description     原始描述那一段的內容
        code_review     程式碼審閱報告；沒有就是空字串
        repo            專案，namespace/project
        mr_iid          編號
        device          這個 device 的名稱

    description 與 code_review 給你**唯讀參考**（例如想讓分析對照描述的哪幾點），
    但它們各自的區段由入口腳本輸出，你回傳的內容不該重複它們。

    回傳一個字串。

    ## 請用這些，不要自己重寫

        contract.plain(value)           None 與非字串收斂成字串。不用的話報告會印出 "None"
        contract.fence_for(code)        算程式碼圍籬的長度
        contract.MAX_FINDING_DIFF_BYTES 單筆 diff 的位元組上限

    `fence_for()` 特別重要：寫死三個反引號的話，內容本身含有反引號的 diff（改到
    markdown 檔就會）會讓程式碼區塊提前結束，後面的內容變成一般文字 —— 而報告仍然
    「成功」產出。
    """
    lines = []
    overview = contract.plain(analysis_overview(inputs))
    if overview:
        lines.append(overview)
    return "\n\n".join(lines)


def analysis_overview(inputs):
    return (inputs["analysis"] or {}).get("overview")
