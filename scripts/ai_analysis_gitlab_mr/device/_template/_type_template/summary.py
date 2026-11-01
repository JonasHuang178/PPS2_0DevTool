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

**不看程式碼的種類記得把底下的 `ANALYZES_CODE` 改成 `False`。** 種類專屬的實作特別容易
是這一種 —— 一個種類會被切出來，往往正是因為它要回答的問題不在 diff 裡。
"""

import ai_analysis_gitlab_mr as contract
from script_utils import ai_utils

# 這一份有沒有把差異送給 AI 看。這個種類的 prompt 完全不放差異（例如要總結的是一張
# JIRA 單）時改成 False。
#
# 寫成 True 擺在這裡而不是註解掉，是因為**兩種答案都是常見的**：改一個字就切換，而取消
# 註解要先讀懂那一段註解在說什麼。不宣告的預設值也是 True，所以這一行不影響行為。
#
# 改成 False 之後：報告裡「分析涵蓋範圍」那一段整段不出現，涵蓋層的重查
# （`Recheck_Count`）不執行。
#
# 維持 True 而 prompt 其實沒放差異的話，涵蓋範圍會把整份差異的每一個檔案都算成「已送進
# 分析，但 AI 沒有回報」—— 那句話在這種種類底下是事實，但它讀起來像缺陷，而重查會為了
# 永遠補不回來的東西把次數用完。
#
# ⚠️ 反過來也要記得：改成 False 之後哪天把差異加回 prompt，**這一行要改回 True** ——
# 留著 False 的話真正的漏報就再也不會出現在報告上了。
#
# 能跑的例子見 `device/sd/new_test_case/summary.py`（那一份是 False）。
ANALYZES_CODE = True


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
