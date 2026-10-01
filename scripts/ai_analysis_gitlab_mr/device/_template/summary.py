#!/usr/bin/env python3
"""步驟 3 的鉤子：AI 分析。

這是四個鉤子裡最自由的一個 —— 要問 AI 什麼、怎麼解析回應、組出什麼分析內容，全部由
你決定。

**這一支因種類而異。** 想讓不同種類的 MR 走不同的 prompt，在 device 底下建一個種類
目錄、把 summary.py 放進去即可（見 `_type_template/`）。放在 device 層的這一份是該
device 的通用版，種類目錄裡沒有時會落到它。入口腳本負責信封、參數、**把素材備好**、落檔與驗證。

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
        mr_diff         unified diff 純文字。太大時已截斷，尾端會註明。

                        **報告裡的程式碼一律從這裡切，不要用 AI 回覆帶回來的
                        那一份。** 讓模型回位置（例如 diff 裡那一行 @@ 標頭），
                        再用 contract.hunk_of(mr_diff, 檔名, 位置) 取出內容。
                        理由見 contract 裡那一支的說明；簡短版是：複述而來的
                        程式碼可能與 MR 上的不一致，而沒有任何一步會發現。
                        取不到時給空字串即可 —— 那一筆只剩標題與理由，不要
                        回退成用回覆裡的原文。
        fetch_jira      fetch_jira(key) -> dict 或 None。鍵有 key / summary /
                        description / status / type / url。查不到、或沒設定
                        JIRA 連線都回 None —— 那不是錯誤，prompt 少那一段即可。

                        **這是函式而不是現成的內容，因為「key 有沒有效」是你的
                        政策。** 入口不認得那個政策，先抓的話 [WIP]、[Draft] 這種
                        從標題方括號抽出來的東西每次都會白打一趟 JIRA。判定有效
                        之後再呼叫它。憑證與錯誤分類仍然在入口那邊。
        jira_key        該次採用的 key；沒有就是空字串
        jira_mode       none / manual / auto —— 讓你分辨 key 是抽的還是使用者填的
        mr_type         選中這一份的種類名稱；沒有種類時是空字串
        ai_mode_name    使用者選的 AI 模式名稱
        ai_api_url      AI 端點
        ai_api_key      AI 金鑰
        ai_model        模型名稱
        repo            專案，namespace/project
        mr_iid          編號
        device          這個 device 的名稱
        progress        progress(text)，在對話框上顯示一行字
        debug_write     debug_write(檔名, 內容)，寫一份除錯檔。除錯輸出沒打開
                        時什麼都不做，所以可以無條件呼叫。調 prompt 時把實際
                        送出的 prompt 與 AI 的原始回覆各寫一份 —— 那兩份不
                        進 log（prompt 含原始碼，回覆動輒幾萬字元），除錯檔
                        是唯一看得到它們的地方

    AI 的呼叫是分鐘級的，而那個對話框是固定尺寸、只有一行字 —— 兩分鐘沒動靜看起來
    就是當掉了。把 progress 包成 ai_utils 的 on_retry 回呼，重試時使用者才看得到。

    **送出之前自己報一行 progress。** 入口腳本在呼叫這支鉤子之前只會報「準備 AI 分析」
    —— 它不知道你接下來要做什麼，也不知道你什麼時候真的送出去。你不報的話，等待回覆
    的那幾分鐘畫面上留著的會是你做的上一件事（例如「取得 JIRA …」），而那件事已經做完
    了。這條適用於任何一段明顯耗時的工作，不只 AI 呼叫。

    **必須回傳 contract.analysis_body(...) 的結果。** 不要自己組 dict，也不要填
    schema_version —— 版本由入口腳本蓋章。回傳之後入口會立刻驗證，不符合就在這一步
    失敗（而不是兩步之後的渲染），訊息會指名是哪個 device 的哪個檔案。

    `mr_type` 與 `coverage`（這次分析涵蓋了多少）同樣由入口蓋章，這裡填了會被覆蓋。
    coverage 尤其不要填：它正是用來說明「這支鉤子回報了多少個檔案」的，報告會把
    「差異裡有、你沒回報」的那些列出來。想讓那個數字好看，唯一的辦法是真的多回報。

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

    TLS 憑證的驗證預設是**關的**（見 contract.ai_verify_ssl），地端服務多半用自簽
    憑證。自己寫 ask() 的時候記得帶上 verify_ssl=contract.ai_verify_ssl()，否則會用
    ai_utils 的預設（開啟），對著自簽憑證就連不上。

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
                    # 從 inputs["mr_diff"] 切出來，不是用 AI 回的那一份
                    diff_code=contract.hunk_of(
                        inputs["mr_diff"], u"path/to/file.cpp", u"@@ ..."),
                ),
            ],
        },
    )
