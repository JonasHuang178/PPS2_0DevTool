#!/usr/bin/env python3
"""sd / new_test_case 的步驟 3 擴充腳本：只總結 JIRA 單，不看程式碼。

`[New Test Case]` 的 MR 要回答的是「這次要測的是什麼」，而那寫在 JIRA 單裡，不在
diff 裡 —— 新增一支測試案例的程式碼差異多半是一份照模板長出來的檔案，對它做程式碼審閱
產出的是一堆沒有人要看的意見，而且照樣要付 token 的錢。

所以這一支與 default 的差別只有兩件事：

- prompt 只放 JIRA 單的內容，**不放 diff**
- 回傳的分析沒有任何 finding（`mr_diff` 是空的），報告因此沒有 `## Code Changes`

版面由 `merge_to_md.py` 配合（那一支會把 JIRA key 的狀態做成一行標題）。

## 兩件要知道的事

**差異仍然會被取得。** 入口腳本在呼叫這一支**之前**就把 diff 取好了，而且整份差異一段
內容都沒有時它會失敗（規格明文：對著幾行檔名做出的分析看起來完全正常）。這一支只是不看
它 —— 省掉的是 token 與模型的注意力，不是那一趟 GitLab。

**涵蓋範圍會把送出的檔案全部算成「AI 沒有回報」。** 涵蓋範圍由入口腳本計算、拿送進分析
的檔案對照這一支回報了哪些，而這一支刻意不回報任何檔案。於是報告的「分析涵蓋範圍」那一段
會出現「N 個檔案已送進分析，但 AI 沒有回報」。那句話在這個種類底下**不是缺陷而是事實**，
但它讀起來像缺陷。要消掉它只有一種做法：把每一個送出的檔案都回報成空清單（規格承認空清單
等於「看過了，沒有值得注意的地方」）—— 但這個種類根本沒讓模型看那些檔案，那樣寫是在宣稱
一件沒有發生的事。目前選擇誠實，代價寫在這裡。
"""

import ai_analysis_gitlab_mr as contract
from script_utils import ai_utils
from script_utils import jira_utils
from script_utils import logger

# JIRA key 的狀態判定與 issue 的取得都沿用 **sd 自己那一層**（`device/sd/summary.py`）。
#
# **刻意共用，不複製。**「什麼算有效的 key」是 sd 的政策，只該有一個來源 —— 各寫一份的
# 結果是兩邊慢慢分岔，症狀是同一個 key 在不同種類的 MR 下一個有效一個無效。
#
# **指向 sd 而不是 default**：sd 那一支就是這個 device 的政策所在，日後 SD 的單號格式改了
# 只會改那裡，而這一支要跟著變。指向 default 的話，改了 sd/summary.py 的樣式這個種類不會
# 跟著動，而且不會有任何徵兆。
#
# 明著 import 是文件指定的共用方式（「真的要共用就明著 import，不要靠回退機制」）。代價是
# 這裡依賴了那一支的內部函式：它改名的話這一支會在**載入時**就失敗，而入口腳本會指名是哪一
# 個 device 的哪一支擴充腳本 —— 一個會被看見的失敗，不是安靜的行為改變。
from ai_analysis_gitlab_mr.device.sd import summary as base


# ===========================================================================
# 要改的東西都在這一段
# ===========================================================================

ROLE_PROMPT = u"""\
你是一位資深的測試工程師，正在檢視一張要新增測試案例的工單。
你的讀者是同組的工程師，他們熟悉這個專案，不需要基礎概念的解釋。
一律以繁體中文回答。
"""


# 主 prompt。送給 AI 的素材**只有那張 JIRA 單的描述**。
#
# 兩樣東西刻意不在這裡：
#
#   {diff}         程式碼。這個種類不看它 —— 新增一支測試案例的差異多半是照模板長出來的
#                  檔案，對它做程式碼審閱產出的是沒有人要看的意見，而且照樣要付 token 的錢
#   {description}  MR 自己的描述。要總結的是工單說了什麼，不是 MR 的作者寫了什麼；兩份
#                  素材一起送，模型會把它們揉成一段，而讀者分不出哪一句出自哪裡
#
# **兩者 build_prompt() 都還是備好了**（`format()` 忽略沒用到的值），所以要把任何一段加
# 回來，只要在這個樣板裡放一個對應的佔位符，底下的程式不用動。可用的：
# {role} {repo} {mr_iid} {description} {diff} {jira} {output_spec}
PROMPT_TEMPLATE = u"""\
{role}
請閱讀以下工單的描述，並依照最後指定的格式回覆。
{jira}
{output_spec}
"""


# JIRA 那一段。沒有 issue 就整段不放（見 _jira_block）。
#
# 狀態與類型刻意不放進 prompt：它們是那張單的現況，不是要被總結的內容（狀態另有去處 ——
# 它由步驟 3 帶進產物，印在報告的工單狀態表上）。key 與標題留著是為了讓模型知道自己在
# 讀哪一張單，一行的成本。
JIRA_TEMPLATE = u"""
## 工單 {key}：{summary}

{description}
"""


OUTPUT_SPEC = u"""\
## 回覆格式
只回覆一個 JSON 物件，不要有任何開場白、說明或 markdown 圍籬。

{
  "summary": "這張工單要測什麼、怎麼測、通過的條件是什麼，三到五句"
}

只依上面那份工單描述作答，不要自己補沒有寫在裡面的東西。
不要回傳任何其他欄位。這次**不需要**審閱程式碼，也不需要列出任何檔案。
"""


# 沒有可總結的工單時，overview 放這一段。
#
# 這個種類的整份分析就是「那張單子說了什麼」，所以沒有單子時沒有東西可問 —— 與其拿一份
# 空的素材去打一趟 AI 換回一段它自己編的話，不如直接說明白。報告的標題那一行會同時標出
# 狀態（見 merge_to_md.py）。
NO_JIRA_OVERVIEW = {
    contract.JIRA_STATE_NONE: u"這筆 Merge Request 沒有指定 JIRA 單，所以沒有可以總結的內容。",
    contract.JIRA_STATE_INVALID: u"這筆 Merge Request 標題上的 JIRA key 不是合法的單號，所以沒有可以總結的內容。",
}


# ===========================================================================
# 以下是接線，通常不用改
# ===========================================================================

def _jira_block(issue):
    """工單那一段。沒有 issue 就回空字串，整段不出現在 prompt 裡。

    不放的理由不只是省 context：一段寫著「（無）」的區塊會讓模型以為那張單子存在但內容
    是空的，然後對著它生出一段總結。
    """
    if not issue:
        return ""

    # status 與 type 仍然備著（樣板想加回去就有），但目前的 JIRA_TEMPLATE 不用它們。
    return base._fill(
        "JIRA_TEMPLATE", JIRA_TEMPLATE,
        key=contract.plain(issue.get("key")),
        summary=contract.plain(issue.get("summary")),
        status=contract.plain(issue.get("status")) or u"（未知）",
        type=contract.plain(issue.get("type")) or u"（未知）",
        description=(contract.plain(issue.get("description"))
                     or base.NO_DESCRIPTION))


def build_prompt(inputs):
    """把素材組成要送給 AI 的 prompt。回傳一個字串。

    單獨拉成一支函式是為了能不打 AI 就印出來看：

        python3 -c "...; print(summary.build_prompt({...}))"

    `jira_issue` 是 analyze() 在確認 key 有效之後才取回來放進去的；單獨呼叫這一支時
    自己塞一個 dict 或 None 即可。
    """
    return base._fill(
        "PROMPT_TEMPLATE", PROMPT_TEMPLATE,
        role=ROLE_PROMPT.strip(),
        repo=contract.plain(inputs.get("repo")) or u"（未指定）",
        mr_iid=contract.plain(inputs.get("mr_iid")) or u"?",
        description=(contract.plain(inputs.get("description"))
                     or base.NO_DESCRIPTION),
        jira=_jira_block(inputs.get("jira_issue")),
        # 備著但樣板沒用到 —— 要把程式碼加回 prompt 只要在樣板裡放一個 {diff}。
        diff=contract.plain(inputs.get("mr_diff")) or u"（沒有取到任何差異）",
        output_spec=OUTPUT_SPEC,
    )


def parse_reply(data):
    """把 AI 回的 JSON 轉成 overview 那一段文字。

    ⚠️ 與 OUTPUT_SPEC 是同一件事的兩面，改格式要一起改。

    格式不對時丟 ValueError —— ai_utils 收到 ValueError 會追加一句「只回覆結果本身」
    重問（次數見 contract.ai_reask）。湊一個半殘的結果比重問糟得多：湊出來的報告看起來
    是完整的。

    `code_changes` 這個種類不要，模型若還是回了就**直接忽略** —— 不報錯：那不影響這一段
    要呈現的東西，而為此重問一次是拿使用者的時間去修一個不影響結果的瑕疵。
    """
    if not isinstance(data, dict):
        raise ValueError("回覆不是一個物件，而是 %s" % type(data).__name__)

    summary = contract.plain(data.get("summary"))
    if not summary:
        raise ValueError(
            "回覆裡沒有 summary（實際收到的欄位：%s）"
            % ("、".join(sorted(data.keys())) or "(沒有任何欄位)"))

    return summary


# 相關工單的 JQL 一次最多看幾張。取的是第一張，多要幾張只為了在診斷輸出寫出「共幾張」——
# 一條寫得太寬的 JQL（例如忘了限定專案）會回成千上萬張，而那時最該看到的就是這個數字。
_RELATED_MAX_ITEMS = 5

# 搜尋只要這兩個欄位。key 一律會回，status 是表格要印的那一格 —— 不限定欄位的話每一張都
# 會連描述一起拖回來。
_RELATED_FIELDS = "status"

# 宣告沒有佔位符時，自動接在後面的那一段。`~` 是 JQL 的文字比對（不是完全相等）——
# 標題不會一字不差，所以用它；要完全相等就在宣告裡用 {summary} 佔位符自己寫 `summary = `。
_APPEND_OPERATOR = u"AND summary ~"


def _declared(name, default=u""):
    """讀 device 的宣告；沒宣告就用預設值。

    用 getattr 而不是 import 那個名字：import 不存在的名字會在**載入時**就讓這一支失敗，
    而選填的宣告缺了不該讓整份分析做不出來。
    """
    from ai_analysis_gitlab_mr.device import sd

    value = getattr(sd, name, None)
    return value if isinstance(value, str) else default


def _build_jql(template, key, issue_summary):
    """把宣告的那一段 JQL 組成真正要送出的查詢；組不出來回空字串。

    宣告裡只寫 JQL **固定的那一段**，隨每一筆 MR 變動的條件在這裡接上去。兩種形式：

        有佔位符   照宣告的位置代入 {summary} / {key}
        沒有佔位符 自動在最後接上 `AND summary ~ "<主單標題>"`

    兩個佔位符代入的都是**已經包好引號的 JQL 字串常量**，所以宣告寫 `summary ~ {summary}`
    而不是 `summary ~ "{summary}"` —— 統一成「代入的值自帶引號」才不會有一個要加、一個
    不要加的陷阱。

    引號與反斜線的跳脫用 `jira_utils` 那一份，不自己寫：標題是人打的字，一個雙引號就會讓
    整段 JQL 語法錯誤（JIRA 回 400，訊息指著一段呼叫端從沒寫過的查詢字串），刻意構造的標題
    更可以改寫查詢條件。跳脫規則只該有一份來源。

    代入用字串替換而不是 `format()`：JQL 裡的大括號、引號與括號都原樣送出，寫宣告的人不必
    疊兩層大括號（通用層的 prompt 樣板就是因為 `format()` 而有那個坑）。

    主單標題是空的時候回空字串，呼叫端據此不查：一條用來比對標題的查詢少了標題，剩下的
    固定條件會回一整個專案的單子，而「取第一張」在那時完全是任意的。
    """
    has_summary = u"{summary}" in template
    has_key = u"{key}" in template

    # 只有 {key} 的那一種（`issue in linkedIssues({key})`）用不到標題，少了它照樣查得成。
    # 其餘兩種都要標題：用了 {summary} 的，以及沒有任何佔位符、要自動接標題的。
    if (has_summary or not has_key) and not issue_summary:
        return u""

    if has_summary or has_key:
        return (template.replace(u"{summary}", jira_utils._quote_jql(issue_summary))
                        .replace(u"{key}", jira_utils._quote_jql(key)))

    return u"%s %s %s" % (template.strip(), _APPEND_OPERATOR,
                          jira_utils._quote_jql(issue_summary))


def _search_related(inputs, key, issue_summary):
    """用 device 宣告的 JQL 找出第二張單，回傳 {"searched":…, "key":…, "status":…}。

    **連線與錯誤處理都在這裡**，而這是一條有代價的路：入口腳本只交給擴充腳本
    `fetch_jira(key)`（單筆查詢），沒有搜尋的能力，所以這一支自己拿憑證、自己打 JIRA。
    文件開了這條路（「它是普通的 Python，沒東西擋你 —— 代價是連線與錯誤處理變成你的事」）。

    > 要讓**每一個 device** 都能用 JQL 搜尋的話，該做的是在入口腳本多交一個
    > `inputs["search_jira"]`，而那要動通用層與規格。目前只有 SD 的一個種類需要，所以
    > 先留在這裡；真的有第二個用途時再往上搬。

    **任何一步取不到都不讓流程失敗**，只回一個空的結果讓那一列印「查無」或「未查詢」：
    這一列是補充資料，與入口腳本對 `fetch_jira` 的政策一致。

    三種結果在報告上印不同的字，因為使用者的下一步不同：

        searched 為假                沒查 —— 宣告是空的，或這一筆沒有主單可代入
        searched 為真、error 有值    查了但沒查完 —— JQL 寫壞了，或沒設 JIRA 連線
        searched 為真、key 為空      查完了，沒有符合的單子 —— 去看 JQL 的條件
    """
    empty = {"searched": False, "key": u"", "status": u"", "error": u""}

    def failed(reason):
        """查了但沒查完。與「沒查」分開 —— 印一樣的字會把該修 JQL 的人送去填宣告。"""
        return {"searched": True, "key": u"", "status": u"", "error": reason}

    template = _declared("NEW_TEST_CASE_RELATED_JQL")
    if not template.strip():
        logger.debug("sd 沒有宣告 NEW_TEST_CASE_RELATED_JQL，不查相關工單")
        return empty

    jql = _build_jql(template, key, issue_summary)
    if not jql:
        logger.info("主單沒有標題可代入，不查相關工單（JQL 宣告：%s）", template)
        return empty

    try:
        base_url, token = contract.jira_credentials()
    except contract.CredentialError as exc:
        logger.warn("未設定 JIRA 連線資訊，相關工單那一列留空：%s", exc)
        return failed(u"未設定 JIRA 連線資訊")

    base._progress(inputs)(u"以 JQL 搜尋相關工單…")
    logger.info("相關工單的 JQL：%s", jql)

    try:
        # 不傳 verify_ssl，用 jira_utils 的預設（驗證開啟）。入口腳本的 _fetch_jira 也是
        # 這樣呼叫的 —— 同一支腳本對 JIRA 的 TLS 政策只能有一套，而那一套在那裡。
        # （GitLab 與 AI 各有自己的環境變數開關，JIRA 目前沒有。）
        issues = jira_utils.search_issues(base_url, token, jql,
                                          fields=_RELATED_FIELDS,
                                          max_items=_RELATED_MAX_ITEMS)
    except jira_utils.JiraError as exc:
        logger.warn("相關工單的 JQL 查詢失敗，那一列留空：%s", exc)
        return failed(u"%s" % exc)

    if not issues:
        logger.info("相關工單的 JQL 沒有符合的單子")
        return {"searched": True, "key": u"", "status": u"", "error": u""}

    first = issues[0] or {}
    fields = first.get("fields") or {}
    status = (fields.get("status") or {}).get("name") or u""

    if len(issues) > 1:
        # 多張就取第一張，但要讓人知道有多張 —— 否則「為什麼印的是這一張」無從回答。
        logger.warn("相關工單的 JQL 符合 %d 張（上限 %d），取第一張 %s；"
                    "要指定哪一張請在 JQL 加 ORDER BY",
                    len(issues), _RELATED_MAX_ITEMS, first.get("key") or u"?")

    return {"searched": True,
            "key": contract.plain(first.get("key")),
            "status": contract.plain(status),
            "error": u""}


def _body(overview, key, state, provider="", model="", jira_status="",
          related=None):
    """組回傳值。`mr_diff` 一律是空的 —— 這個種類不產生 finding。

    **多帶一個 `jira_status`**：那是 JIRA 單在 JIRA 上的狀態（`In Progress` 這種），報告的
    工單狀態表要印它，而步驟 5 拿到的只有 `03_summary.json` —— 它沒有憑證、也刻意沒有任何
    外部依賴，所以這個值只能由這一步帶過去。與 `mr_type` 必須進產物是同一條理由。

    `analysis_body()` 的參數裡沒有它，所以**在它回傳的 dict 上補一個鍵**。這是合法的：
    結構的驗證不排斥多出來的欄位（協定是加法式的），而讀的人只有這個種類自己的
    `merge_to_md.py`。放進通用層的 `analysis_body()` 才需要動通用層與規格，而這個欄位目前
    只有 SD 的一個種類在用。

    `related` 是第二列那張用 JQL 找出來的單（見 `_search_related`），同樣只有這個種類在讀。

    代價寫清楚：這兩個鍵都不在通用層的契約裡，所以 `contract` 那一側不保證它們的存在 ——
    讀的那一支必須自己給預設值（它用的是 `.get()`）。
    """
    body = contract.analysis_body(
        overview=overview,
        provider=provider,
        model=model,
        jira_key=key,
        jira_state=state,
        jira_url=(contract.jira_url(key)
                  if state == contract.JIRA_STATE_OK else ""),
        mr_diff={})
    body["jira_status"] = contract.plain(jira_status)
    body["related_issue"] = dict(related or {"searched": False, "key": u"",
                                             "status": u"", "error": u""})
    return body


def analyze(inputs):
    """產生這次分析的內容。

    只回內容。版本、種類與涵蓋範圍都由入口腳本蓋章。
    """
    key = contract.plain(inputs.get("jira_key"))
    state, key = base._jira_state(inputs.get("jira_mode"), key)

    # 沒有有效的單號就沒有東西可總結 —— 不打 AI。這與 default 不同：那一份的素材是 diff，
    # 沒有 key 也還有程式碼可以分析；這一份的素材就是那張單子。
    if state != contract.JIRA_STATE_OK:
        logger.info("JIRA 狀態是 %s，沒有可總結的工單，不呼叫 AI", state)
        return _body(NO_JIRA_OVERVIEW[state], key, state)

    if not contract.plain(inputs.get("ai_connection")):
        # 規格要求：沒有 AI 端點時產出替代內容而非失敗，且首行言明未經過 AI。
        logger.warn("未設定 AI 端點，產生替代內容而非真的總結")
        return _body(u"\n".join([
            u"⚠️ 這份總結沒有經過 AI —— 設定檔的 Service.AI_Provider_List 沒有填 Api_URL。",
            u"以下內容是佔位用的，不反映 %s 的實際內容。" % key,
        ]), key, state)

    connection, api_key = contract.ai_credentials(inputs)

    # **必要步驟：拆連線字串、查模型名稱。** 兩者都寫進分析結構，報告出處的 AI 那一行
    # 就靠它們；沒做不會失敗，只是出處少了那一行 —— 一個不會報錯的遺漏。
    provider, url, share_code = ai_utils.split_connection(connection)
    model = ai_utils.lookup_model(url, share_code, api_key,
                                  verify_ssl=contract.ai_verify_ssl())

    # 確認有效**之後**才去抓工單內容（理由見 default 的同一段）。這個種類沒有它就沒有
    # prompt，但抓不到仍然不讓流程失敗 —— 入口腳本已經記了警告。
    issue = base._lookup_jira(inputs, key, state)
    if not issue:
        logger.warn("取不到 %s 的內容，沒有可總結的素材，不呼叫 AI", key)
        return _body(
            u"取不到 JIRA 單 %s 的內容，所以沒有可以總結的東西。"
            u"（可能是查不到這張單子，或沒有設定 JIRA 的連線）" % key,
            key, state, provider, model)

    # JIRA 上的狀態（`In Progress` 這種）。報告的工單狀態表要印它，而步驟 5 拿不到 JIRA ——
    # 所以在這裡取出來，隨產物帶過去。取不到就是空字串，那一格印「（未取得）」。
    jira_status = contract.plain(issue.get("status"))

    # 要總結的素材就是這張單的描述。描述是空的就沒有東西可總結 —— 送出去的話，模型手上
    # 只有一個 key 與一行標題，而它仍然會交出一段三到五句、讀起來很合理的「總結」。
    # 那份報告看起來正常，實際上是編的，而使用者不會知道要懷疑它。
    if not contract.plain(issue.get("description")):
        logger.warn("JIRA 單 %s 沒有描述，沒有可總結的素材，不呼叫 AI", key)
        return _body(
            u"JIRA 單 %s 沒有填寫描述，所以沒有可以總結的內容。" % key,
            key, state, provider, model, jira_status,
            _search_related(inputs, key, contract.plain(issue.get("summary"))))

    # 第二列那張單。放在送 AI **之前**：它不進 prompt（總結講的是主單），但失敗了也只是
    # 那一列留空，而這裡做完就不必在等了兩分鐘的 AI 之後再多等一趟 JIRA。
    related = _search_related(inputs, key, contract.plain(issue.get("summary")))

    prompt = build_prompt(dict(inputs, jira_issue=issue))
    logger.info("prompt 組好了，%d 字元", len(prompt))

    log_write = inputs.get("log_write") or (lambda name, text: False)
    log_write("ai_prompt.txt", prompt)

    # JSON 解析與結構檢查串成同一個 parse 交給 ask()。分兩段寫的話第二段跑在 ask() 之外，
    # 重問永遠觸發不到，而「JSON 合法但結構不對」恰好是模型最常見的失手方式。
    attempt = [0]

    def parse(text):
        # 每一次嘗試各寫一個檔，而且**寫在解析之前** —— 解析失敗的那一份才是線索。
        attempt[0] += 1
        log_write("ai_reply_%d.txt" % attempt[0], text)
        return parse_reply(ai_utils.as_json(text))

    # 送出**之前**報一行，而且由這裡報 —— 只有這裡知道什麼時候真的送出去。等 AI 回覆是
    # 整條流程最久的一段，沒有這一行的話畫面上留著的是一件已經做完的事。
    base._progress(inputs)(u"送交 AI 總結工單，等待回覆…")

    overview = ai_utils.ask(
        url, prompt,
        share_code=share_code,
        api_key=api_key,
        timeout=contract.ai_timeout(inputs),
        verify_ssl=contract.ai_verify_ssl(),
        parse=parse,
        retries=contract.ai_retries(inputs),
        reask=contract.ai_reask(inputs),
        on_retry=base._on_retry(inputs.get("progress")))

    logger.info("工單總結完成，%d 字元（JIRA 狀態 %s）",
                len(overview), jira_status or u"（未取得）")

    return _body(overview, key, state, provider, model, jira_status, related)
