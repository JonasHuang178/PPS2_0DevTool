#!/usr/bin/env python3
"""步驟 4 的鉤子：看懂別人的 code review 報告。

來源是**別人的文件** —— 工程師用 AI code review 工具產出一份 markdown，以附件掛在該
Merge Request 標題所指的 JIRA 議題上。各條產品線用的工具不同，那份文件的格式也就不同，
所以「怎麼看懂它」掛在 device 上。

**查附件、挑最新那一份、擋大小上限、下載、解碼都不在這裡**，入口腳本已經做完了。你拿到
的是現成的全文。理由有兩個：那些動作要 JIRA 權杖，而權杖不交給 device 的程式碼；附件的
挑選規則與大小上限也不該每個 device 重寫一次。

**不因種類（type）而異。** 這份報告的格式取決於你們用哪一套 code review 工具，而不是
這一筆 MR 是 bug 還是 feature，所以兩段解析：<device>/ -> default/。

沒有提供這一支時用 default 的那一份，它的規則是「風險評估總表的最後一欄是數量，全部列
加總為 0 判定通過」。你們的總表是這個形狀的話就不必覆寫。
"""

import ai_analysis_gitlab_mr as contract


def parse(inputs):
    """從報告全文裡擷取要進報告的那一段，並判定這份審閱的結論。

    inputs：

        text          報告全文（字串，一定有值）
        heading       要找的那一節的標題。來自你的 device 的
                      CODE_REVIEW_SOURCE_HEADING 宣告，沒宣告就是契約的預設值
        jira_key      這一筆的 JIRA key，只用於診斷訊息
        debug_write   debug_write(檔名, 內容)；除錯沒開時什麼都不做，可以無條件呼叫

    回傳 contract.code_review_parsed(risk_table, review_result)：

        risk_table      要放進報告的那一段 markdown。**不要自帶標題** ——
                        「## 風險評估表」由步驟 5 寫出，它才知道自己在第幾層
        review_result   contract.REVIEW_RESULT_PASS / _FAIL / _UNKNOWN

    結論判不出來時可以回 REVIEW_RESULT_UNKNOWN（空字串），報告上那一行就不出現 ——
    **不要猜**：印一個 PASS 或 FAIL 出去，讀的人會以為那是真的結論。

    擷取不到那一段時 raise contract.RiskTableError(訊息, 細節, 錯誤碼)。入口會把訊息寫進
    結構的 error 欄位，報告顯示那一段，而**流程繼續** —— 這一步跑在 AI 分析之後，讓它
    失敗會把一份已經完成、已經付費的分析整份丟掉。

    丟任何其他例外也不會中斷流程（入口一律攔下來），但訊息會是那個例外的字面文字，
    指不出你想說的事。要表達「這份文件不合約定」就用 RiskTableError。

    可以直接用的工具：

        contract.extract_risk_table(text, heading)   擷取某一節裡的第一張表格
        contract.plain(value)                        None 與非字串收斂成字串
        contract.REVIEW_RESULT_PASS / _FAIL / _UNKNOWN
    """
    table = contract.extract_risk_table(inputs["text"], inputs["heading"])

    # TODO: 換成你們的判定規則。
    return contract.code_review_parsed(
        risk_table=table,
        review_result=contract.REVIEW_RESULT_UNKNOWN)
