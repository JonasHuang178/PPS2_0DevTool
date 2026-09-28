#!/usr/bin/env python3
"""步驟 3 的鉤子：AI 分析。

這是三個鉤子裡最自由的一個 —— 要問 AI 什麼、怎麼解析回應、組出什麼分析內容，全部由
你決定。入口腳本負責信封、參數、**把素材備好**、落檔與驗證。

素材指的是 MR 的 diff 與 JIRA issue 的內容：兩者都要連線、要憑證、要處理錯誤，而你
在改 prompt 的時候不該為了一句話去面對 HTTP。你拿到的已經是現成的文字。

怎麼問 AI 見 script_utils.ai_utils —— 重試、退避、限流與重問都在那裡，你不需要自己
寫一份。可以直接抄 default/summary.py，它是一份能跑的完整範例。
"""

import ai_analysis_gitlab_mr as contract
from script_utils import ai_utils


def analyze(inputs):
    """產生這次分析的內容。

    inputs 是一個 dict：

        description     MR 的原始描述（已扣掉上一輪的 AI 分析）
        mr_diff         unified diff 純文字。太大時已截斷，尾端會註明
        jira_issue      dict 或 None，鍵有 key / summary / description /
                        status / type / url。沒有 key、查不到、或沒設定 JIRA
                        連線都是 None —— 那不是錯誤，prompt 少那一段即可
        jira_key        該次採用的 key；沒有就是空字串
        jira_mode       none / manual / auto —— 讓你分辨 key 是抽的還是使用者填的
        ai_mode_name    使用者選的 AI 模式名稱
        ai_api_url      AI 端點
        ai_api_key      AI 金鑰
        ai_model        模型名稱
        repo            專案，namespace/project
        mr_iid          編號
        device          這個 device 的名稱
        progress        progress(text)，在對話框上顯示一行字

    AI 的呼叫是分鐘級的，而那個對話框是固定尺寸、只有一行字 —— 兩分鐘沒動靜看起來
    就是當掉了。把 progress 包成 ai_utils 的 on_retry 回呼，重試時使用者才看得到。

    **必須回傳 contract.analysis_body(...) 的結果。** 不要自己組 dict，也不要填
    schema_version —— 版本由入口腳本蓋章。回傳之後入口會立刻驗證，不符合就在這一步
    失敗（而不是兩步之後的渲染），訊息會指名是哪個 device 的哪個檔案。

    JIRA 的有效性由**你**判定：

        通過檢查    jira_state=contract.JIRA_STATE_OK，jira_key 放那個 key
        沒有要用    jira_state=contract.JIRA_STATE_NONE
        抽到但無效  jira_state=contract.JIRA_STATE_INVALID，jira_key 放**被拒絕的原值**

    最後一項很重要：報告會印出那個原值（`JIRA: WIP (invalid)`），讀的人一眼就知道標題
    的第一個方括號放錯了東西。只說「無效」等於要人自己猜。

    真的要問 AI 的話大致長這樣（完整版見 default/summary.py）：

        url, key, model = contract.ai_credentials(inputs)
        overview, mr_diff = ai_utils.ask(
            url, my_prompt, api_key=key,
            parse=lambda text: my_parse(ai_utils.as_json(text)),
            reask=1)

    `url` 直接傳設定檔的 Api_URL，shareCode 黏在尾端也沒關係 —— ai_utils 會拆。`model`
    **不進請求**（模型由 shareCode 那一端決定），它只是報告出處要印的資訊，所以拿到之後
    是交給 contract.analysis_body(model=...)，不是交給 ask()。

    parse 把原始回覆轉成你要的東西，格式不對就丟 ValueError —— ai_utils 會追加一句
    「只回覆結果本身」重問一次。**JSON 解析與結構檢查要串在同一個 parse 裡**，分兩段
    寫的話第二段跑在 ask() 之外，重問永遠觸發不到，而「JSON 合法但結構不對」恰好是
    模型最常見的失手方式。
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
