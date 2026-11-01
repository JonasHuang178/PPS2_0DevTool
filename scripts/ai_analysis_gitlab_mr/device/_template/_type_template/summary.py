#!/usr/bin/env python3
"""某一個種類專屬的步驟 3 擴充腳本：AI 分析。

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

**不看程式碼的種類記得宣告 `ANALYZES_CODE = False`**（見底下那一行）。種類專屬的實作
特別容易是這一種 —— 一個種類會被切出來，往往正是因為它要回答的問題不在 diff 裡。
"""

import ai_analysis_gitlab_mr as contract
from script_utils import ai_utils

# 這一份有沒有讓 AI 看程式碼。**未宣告即 True**，絕大多數的種類不必動這一行。
#
# 這個種類的 prompt 完全不放差異（例如要總結的是一張 JIRA 單）時取消註解。涵蓋範圍問的
# 是「送進分析的檔案，這一支回報了多少」—— 一個檔案都沒送進去的話，不宣告會讓整份差異
# 的每一個檔案都落進「已送進分析，但 AI 沒有回報」，於是每一份報告都掛著一段讀起來像
# 缺陷的警告，而涵蓋層的重查（`Recheck_Count`）也會為了永遠補不回來的東西把次數用完。
#
# 宣告之後：報告裡涵蓋範圍那一段整段不出現，重查不執行。
#
# ⚠️ 哪一天把差異加回 prompt，**這一行要跟著拿掉** —— 留著的話真正的漏報就再也不會出現
# 在報告上了。能跑的例子見 `device/sd/new_test_case/summary.py`。
#
# ANALYZES_CODE = False


def analyze(inputs):
    """產生這次分析的內容。回傳 contract.analysis_body(...) 的結果。"""
    # **必要步驟（每一個 device 都必須做）：** 拆連線字串、查模型名稱，寫進分析結構。
    # 報告出處的 AI 那一行只讀它們；沒做不會失敗，只是出處少了那一行。
    provider, url, share_code = ai_utils.split_connection(inputs.get("ai_connection"))
    model = ai_utils.lookup_model(url, share_code, inputs.get("ai_api_key"),
                                  verify_ssl=contract.ai_verify_ssl())

    return contract.analysis_body(
        overview=u"（這個種類專屬的總覽）",
        provider=provider,
        model=model,
        jira_key=inputs.get("jira_key"),
        jira_state=contract.JIRA_STATE_NONE,
        mr_diff={},
    )
