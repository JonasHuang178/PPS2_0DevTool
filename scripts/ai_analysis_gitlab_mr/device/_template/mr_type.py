#!/usr/bin/env python3
"""步驟 2 的鉤子：抽出 Merge Request 的**種類**。

種類決定步驟 3 與步驟 5 會用哪一份 `summary.py` 與 `merge_to_md.py`（見
`_type_template/`）。**這一支只負責讀出來**，認不認得、要不要報錯都不在這裡。

與 `jira_key.py` 是對稱的一對：同一份 Merge Request、同一次連線、同一組欄位，只是
各自抽不同的東西。這一支**不因種類而異** —— 它就是決定種類的那一支。

⚠️ **標題格式與 default 不同的話，這兩支通常要一起寫。** 只寫 `mr_type.py` 的話，
`jira_key.py` 會沿用 default 的規則（標題第一個方括號），於是安靜地抽到錯的東西。
症狀看得見（報告印出 `JIRA: Alpha (invalid)`），但要看報告才看得見。
"""

import ai_analysis_gitlab_mr as contract       # noqa: F401  （需要時使用）


def extract(mr):
    """自 Merge Request 的欄位抽出種類。**回傳字串；沒有就回空字串。**

    收到的 mr 是整理過的欄位，與 `jira_key.py` 完全相同：

        title           標題
        source_branch   來源分支
        target_branch   目標分支
        description     描述
        repo            namespace/project
        mr_iid          編號

    要更多欄位（例如 GitLab 的 label）目前拿不到。真的需要的話，這支鉤子可以自己
    `from script_utils import gitlab_utils` 並用 `contract.gitlab_credentials()` 去抓
    —— 它是普通的 Python，沒東西擋你。代價是連線與錯誤處理變成你的事。

    **回傳值會由入口正規化**：去頭尾空白、轉小寫、檢查形狀。所以

        回 "NewTestCase"  ->  對應到 newtestcase/ 目錄
        回 "  Bug  "      ->  對應到 bug/ 目錄

    你也可以做**映射**：標題寫 `[FW-Update]`、這裡回 `"fw_update"`。目錄名必須是合法
    的識別字（小寫英數與底線、不以數字開頭），而標題長什麼樣是你們自己的約定。

    不合法的字串（`緊急`、`bug fix`、含路徑分隔字元的東西）視同**沒有種類**，不會報錯
    —— 那是 MR 作者打的字，不是部署的問題。後續行為見 `__init__.py` 的 `STRICT_TYPE`。

    回傳非字串會直接失敗（那是這支鉤子寫壞了，不是「這筆 MR 沒有種類」）。
    """
    title = mr.get("title") or ""

    # （你的規則。以下只是示意：取標題第三個方括號。）
    import re
    found = re.findall(r"\[([^\[\]]*)\]", title)
    return found[2] if len(found) > 2 else ""
