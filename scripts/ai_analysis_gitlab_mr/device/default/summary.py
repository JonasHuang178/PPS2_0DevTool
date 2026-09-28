#!/usr/bin/env python3
"""default device 的步驟 3 鉤子：AI 分析。

**目前回傳寫死的假分析，不呼叫任何 AI 供應商。** 真實的呼叫等共用的 AI 模組定案 ——
在那之前各自寫一份 HTTP，每個 device 都會有一份自己的重試與錯誤處理。

JIRA key 的有效性在這裡判定（見 _jira_state）。
"""

import re

import ai_analysis_gitlab_mr as contract
from script_utils import logger

# 認得的 JIRA key 樣式：大寫專案碼 + 連字號 + 數字。
#
# 收得這麼緊是有理由的：抽取那一支拿的是標題第一個方括號，而 [WIP]、[Draft]、[Hotfix]
# 這類前綴非常常見。放寬成「非空字串就算數」的話，jira_key 會變成 "WIP"，然後被拿去
# 組 prompt 或查 JIRA —— 得到一個查不到的 issue，或一段引用了錯誤 issue 的分析，而
# 每一步都回報成功。
#
# 這是 default 的政策，不是全域規則。key 格式不同的產品線自己寫一份 summary.py 即可。
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")


def _jira_state(mode, key):
    """判定這次的 JIRA 狀態。回傳 (state, key)。

    key 無效時**原值原樣留著** —— 報告會印出 `JIRA: WIP (invalid)`，讀的人一眼就知道
    標題的第一個方括號放錯了東西。換成 NONE 的話只剩「失敗了」三個字。
    """
    if mode == "none" or not key:
        return contract.JIRA_STATE_NONE, ""
    if _JIRA_KEY_RE.match(key):
        return contract.JIRA_STATE_OK, key
    return contract.JIRA_STATE_INVALID, key


def analyze(inputs):
    """產生這次分析的內容。"""
    key = contract.plain(inputs.get("jira_key"))
    state, key = _jira_state(inputs.get("jira_mode"), key)

    if state == contract.JIRA_STATE_INVALID:
        # 不讓流程失敗：一個格式不對的 key 不該讓整份分析做不出來。報告的出處會標示它。
        logger.warn("JIRA key %r 不符合樣式，視為無效", key)

    # ---- stub：真實實作會在這裡組 prompt 並呼叫 AI ----
    #
    # 假的是內容，不是形狀 —— 底下用的是與真實實作同一組建構函式，所以入口的驗證、
    # 步驟 5 的渲染、圍籬處理與版本檢查全都被這條流程驗到。
    overview = "\n".join([
        "這是 default device 的 stub 分析，尚未呼叫任何 AI 供應商。",
        "模式 %s、模型 %s、描述 %d 字元。"
        % (contract.plain(inputs.get("ai_mode_name")) or "(未指定)",
           contract.plain(inputs.get("ai_model")) or "(未指定)",
           len(contract.plain(inputs.get("description")))),
    ])

    mr_diff = {
        "cpp/example.cpp": [
            contract.finding(
                title="重試上限調高後可能超過呼叫端的逾時",
                reason="單次逾時 30s、重試 10 次，最壞情況 300s。",
                diff_code="@@ -12,7 +12,7 @@\n-    retry = 3\n+    retry = 10"),
            contract.finding(
                title="競態修正只涵蓋讀取路徑",
                reason="寫入路徑用的是同一個 cache，未一併加鎖。"),
        ],
        "tests/example_test.cpp": [
            contract.finding(
                title="新增的測試蓋不到這次修的問題",
                reason="只有單執行緒的案例。"),
        ],
    }
    # ---------------------------------------------------------

    return contract.analysis_body(
        overview=overview,
        model=inputs.get("ai_model"),
        jira_key=key,
        jira_state=state,
        jira_url=contract.jira_url(key) if state == contract.JIRA_STATE_OK else "",
        mr_diff=mr_diff,
    )
