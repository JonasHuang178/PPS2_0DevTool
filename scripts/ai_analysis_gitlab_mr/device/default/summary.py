#!/usr/bin/env python3
"""default device 的步驟 3 鉤子：AI 分析。

這一支要改的地方集中在**最上面那幾個字串常數**：ROLE_PROMPT、PROMPT_TEMPLATE、
JIRA_TEMPLATE、OUTPUT_SPEC。想換問法、加一段規則、改輸出格式，改字串就好，底下的
程式不用動。

素材（MR 的 diff、JIRA issue 的內容）由入口腳本備好放進 inputs，這裡拿到的已經是
現成的文字 —— 寫 prompt 的人不必面對 HTTP、憑證與重試。

    inputs["description"]   MR 的原始描述
    inputs["mr_diff"]       unified diff 純文字（可能已截斷，尾端會註明）
    inputs["jira_issue"]    dict 或 None；沒有 key、查不到、沒設定連線都是 None
    inputs["jira_key"]      上一步抽出的 key，未經有效性判定
    inputs["jira_mode"]     none / manual / auto
    inputs["repo"]          namespace/project
    inputs["mr_iid"]        MR 編號
    inputs["progress"]      progress(text) —— 回報進度給那個固定尺寸的對話框
    inputs["ai_*"]          端點、金鑰、模型名

JIRA key 的有效性也在這裡判定（見 _jira_state）。
"""

import re

import ai_analysis_gitlab_mr as contract
from script_utils import ai_utils
from script_utils import logger


# ===========================================================================
# 要改的東西都在這一段
# ===========================================================================

# 角色與語氣。
#
# 這一段放在 prompt 最前面，而不是另一個 system 欄位 —— 這個服務的 payload 只有一個
# prompt 欄位（見 ai_utils._build_payload），角色設定沒有別的地方可去。
ROLE_PROMPT = u"""\
你是一位資深的韌體工程師，正在審閱一份 Merge Request。
你的讀者是同組的工程師，他們熟悉這個專案，不需要基礎概念的解釋。
只指出真正值得注意的地方；沒有問題的檔案就不要提。
一律以繁體中文回答。
"""


# 主 prompt。用 str.format() 代入，佔位符見底下的 build_prompt()。
#
# diff 裡的大括號不會被當成佔位符 —— format() 只解析樣板本身，代入的值原樣放進去。
PROMPT_TEMPLATE = u"""\
{role}
請審閱以下 Merge Request，並依照最後指定的格式回覆。

## Merge Request
{repo} !{mr_iid}

### 原始 MR 的描述
{description}
{jira}
## 程式碼差異
```diff
{diff}
```

{output_spec}
"""


# 有 JIRA issue 時插進 prompt 的那一段；沒有就整段不放（見 _jira_block）。
JIRA_TEMPLATE = u"""
## 相關的 JIRA Issue
{key}：{summary}
狀態：{status}　類型：{type}

### Issue 描述
{description}
"""


# 期望的回覆格式。
#
# ⚠️ 這一段與底下的 parse_reply() 是**同一件事的兩面**：這裡怎麼要求，那裡就怎麼解析。
# 改格式時兩邊要一起改，否則模型照新格式回、程式照舊格式讀，症狀是「AI 的回覆不是
# 預期的格式」而不是任何有用的訊息。
#
# code_changes 是**以檔名為鍵的物件**。規格最初寫成方括號（陣列）卻裝著鍵值對，那在
# JSON 裡不合法；這裡用物件，因為它與最終產出的 mrDiff 形狀一致，少一層轉換。
# 但 parse_reply() 兩種都收 —— 規格有歧義的時候模型也會兩種都產。
#
# hunkHeader 要的是 diff 裡那一行 @@ **標頭**，不是那一段程式碼 —— 程式碼由
# contract.hunk_of() 從入口備好的 diff 切出來（為什麼不讓模型回內容，見那一支的
# 說明）。這裡只要一個位置，欄位名也因此終於名副其實。
#
# 「不要加圍籬」的交代留著：模型仍然可能把那一行包進 ```diff。剝除在 parse_reply()，
# 因為模型對否定指令的服從度不高。
OUTPUT_SPEC = u"""\
## 回覆格式
只回覆一個 JSON 物件，不要有任何開場白、說明或 markdown 圍籬。

{
  "summary": "整體變更的摘要，三到五句",
  "code_changes": {
    "修改的檔案名稱": [
      {
        "title": "一句話講完這個發現",
        "reason": "為什麼值得注意，兩三句",
        "hunkHeader": "@@ -12,7 +12,7 @@"
      }
    ]
  }
}

hunkHeader 只填上面 diff 裡那一行 @@ 開頭的標頭，一字不差地照抄。
**不要**填 diff 的內容，也不要加 ``` 圍籬 —— 程式碼會由工具自己從 diff 取出，
你填在這裡的程式碼不會被使用。
一個發現對應一個 hunk；同一個檔案有多處要講就分成多筆。
檔名要與上面 diff 裡出現的一致。沒有值得注意之處的檔案不要放進 code_changes。
"""


# 描述為空時放進 prompt 的替代文字。留白會讓模型以為那一段被截掉了。
NO_DESCRIPTION = u"（作者沒有填寫描述）"


# 認得的 JIRA key 樣式：大寫專案碼 + 連字號 + 數字。
#
# 收得這麼緊是有理由的：抽取那一支拿的是標題第一個方括號，而 [WIP]、[Draft]、[Hotfix]
# 這類前綴非常常見。放寬成「非空字串就算數」的話，jira_key 會變成 "WIP"，然後被拿去
# 組 prompt 或查 JIRA —— 得到一個查不到的 issue，或一段引用了錯誤 issue 的分析，而
# 每一步都回報成功。
#
# 這是 default 的政策，不是全域規則。key 格式不同的產品線自己寫一份 summary.py 即可。
_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")


# ===========================================================================
# 以下是接線，通常不用改
# ===========================================================================

class PromptError(Exception):
    """樣板本身有問題（佔位符打錯、大括號沒跳脫）。

    與「素材有問題」分開：素材是每次執行都不一樣的東西，樣板是改了就每次都壞。訊息
    要直接指出改哪裡，而不是丟一個 KeyError 讓人自己對。
    """


def _fill(name, template, **values):
    """把值代進樣板，並且在樣板寫壞時給一個講得清楚的錯誤。

    str.format() 對樣板裡的每一個大括號都當佔位符看待，所以 prompt 裡只要有 JSON
    範例、C 的程式碼片段或 {變數} 這種東西，就會冒出一個 KeyError 說某個名字不存在
    —— 而那個名字往往就是使用者剛貼進去的內容的一部分，完全看不出是跳脫的問題。

    這三種都轉成同一句話：要原樣印出大括號就疊成兩層。
    """
    try:
        return template.format(**values)
    except KeyError as exc:
        raise PromptError(
            u"%s 裡有認不得的佔位符 {%s}。可用的是：%s。\n"
            u"如果那對大括號是你要原樣印出來的內容（JSON 範例、程式碼片段），"
            u"請寫成兩層：{{ 與 }}。"
            % (name, exc.args[0], u"、".join(sorted(values))))
    except IndexError:
        raise PromptError(
            u"%s 裡有一個空的 {}。要原樣印出大括號請寫成兩層：{{ 與 }}。" % name)
    except ValueError as exc:
        # 單獨一個 { 或 }（format() 會說 Single '{' encountered…）。
        raise PromptError(
            u"%s 的大括號不成對（%s）。要原樣印出大括號請寫成兩層：{{ 與 }}。"
            % (name, exc))


def _jira_block(issue):
    """JIRA 那一段。沒有 issue 就回空字串，整段不出現在 prompt 裡。

    不放的理由不只是省 context：一段寫著「（無）」的 JIRA 區塊會讓模型以為那張 issue
    存在但內容是空的，然後對著它生出評論。
    """
    if not issue:
        return ""

    return _fill("JIRA_TEMPLATE", JIRA_TEMPLATE,
                 key=contract.plain(issue.get("key")),
                 summary=contract.plain(issue.get("summary")),
                 status=contract.plain(issue.get("status")) or u"（未知）",
                 type=contract.plain(issue.get("type")) or u"（未知）",
                 description=(contract.plain(issue.get("description"))
                              or NO_DESCRIPTION))


def build_prompt(inputs):
    """把素材組成要送給 AI 的 prompt。回傳一個字串。

    單獨拉成一支函式而不是塞在 analyze() 裡，是為了能單獨看、單獨測：

        python -c "import summary; print(summary.build_prompt({...}))"

    這樣改完 prompt 可以先印出來確認，不必真的打一次 AI。

    JIRA 那一段吃 inputs["jira_issue"]，那是 analyze() 在確認 key 有效之後才取回來
    放進去的（見底下）。單獨呼叫這一支時自己塞一個 dict 或 None 即可。
    """
    # 這裡備妥的值可以比樣板實際用到的多。format() 會忽略沒用到的，所以把某一段
    # 從樣板拿掉或加回去只要動字串、不用動程式 —— 佔位符打錯時 _fill 列出的
    # 「可用的是」也才是完整的清單。
    return _fill(
        "PROMPT_TEMPLATE", PROMPT_TEMPLATE,
        role=ROLE_PROMPT.strip(),
        repo=contract.plain(inputs.get("repo")) or u"（未指定）",
        mr_iid=contract.plain(inputs.get("mr_iid")) or u"?",
        description=contract.plain(inputs.get("description")) or NO_DESCRIPTION,
        jira=_jira_block(inputs.get("jira_issue")),
        diff=contract.plain(inputs.get("mr_diff")) or u"（沒有取到任何差異）",
        output_spec=OUTPUT_SPEC,
    )


def _file_pairs(code_changes):
    """把 code_changes 正規化成 [(檔名, findings), ...]。

    兩種形狀都收：

        {"a.cpp": [...], "b.cpp": [...]}        以檔名為鍵的物件
        [{"a.cpp": [...]}, {"b.cpp": [...]}]    每個元素一個單鍵物件

    規格原本寫成方括號卻裝著鍵值對，那在 JSON 裡不合法，所以兩種讀法都說得通 ——
    而規格有歧義的時候模型也會兩種都產。只認一種的話，另一種會變成「缺少必要欄位」，
    而那個訊息完全指不出真正的原因。

    順序有意義（報告的檔案編號照這個順序），dict 與 list 都保留原順序。
    """
    if isinstance(code_changes, dict):
        return list(code_changes.items())

    if isinstance(code_changes, list):
        pairs = []
        for index, entry in enumerate(code_changes):
            if not isinstance(entry, dict):
                raise ValueError("code_changes[%d] 不是物件，而是 %s"
                                 % (index, type(entry).__name__))
            if not entry:
                continue
            pairs.extend(entry.items())
        return pairs

    raise ValueError("code_changes 不是物件也不是陣列，而是 %s"
                     % type(code_changes).__name__)


def parse_reply(data, diff_text=""):
    """把 AI 回的 JSON 轉成 (summary, mrDiff)。

    ⚠️ 與 OUTPUT_SPEC 是同一件事的兩面，改格式要一起改。

    對應關係：

        summary                     → 報告的 ## Summary
        code_changes[檔名][*].title  → finding 的標題
        code_changes[檔名][*].reason → finding 的理由
        code_changes[檔名][*].hunkHeader → 在 diff_text 裡定位，切出的那個 hunk
                                           成為 finding 的 diffCode

    diff_text 是入口備好的那份 diff（inputs["mr_diff"]）。**程式碼一律從它切出來，
    不採用模型回的內容** —— 模型只負責指位置。沒給 diff_text 時每一筆都對不上，
    findings 只會有標題與理由；單獨測解析邏輯時這樣就夠了。

    格式不對時丟 ValueError —— ai_utils 收到 ValueError 會重問一次（見 ask 的 reask）。
    拿回一個半殘的結構硬湊比重問糟得多：湊出來的報告看起來是完整的。
    """
    summary = contract.plain(data.get("summary"))

    code_changes = data.get("code_changes")
    pairs = _file_pairs(code_changes) if code_changes else []

    mr_diff = {}
    missed = []
    for path, findings in pairs:
        clean = contract.plain(path)
        if not clean:
            # 沒有檔名的發現放不進報告 —— mrDiff 是以檔名為鍵的。
            raise ValueError("code_changes 裡有一筆沒有檔名")

        if findings is None:
            findings = []
        if not isinstance(findings, list):
            raise ValueError("code_changes[%r] 不是陣列，而是 %s"
                             % (clean, type(findings).__name__))

        items = []
        for item in findings:
            if not isinstance(item, dict):
                raise ValueError("%s 底下有一筆發現不是物件，而是 %s"
                                 % (clean, type(item).__name__))

            # 圍籬還是剝一次。OUTPUT_SPEC 已經交代不要加，但模型對否定指令的服從度
            # 不高 —— 一行 ```diff\n@@ …\n``` 抽不出標頭，會白白變成「對不上」。
            ref = ai_utils.strip_fence(contract.plain(item.get("hunkHeader")))

            # 程式碼從入口備好的 diff 切出來，不用模型回的內容。
            code = contract.hunk_of(diff_text, clean, ref)

            # 指不到就沒有 diff，但標題與理由仍然有價值 —— 不讓一筆對不上的引用
            # 毀掉整份分析。**但不能安靜地少一段**：收集起來一次警告，那正是這個
            # 做法要觀察的東西（模型抄標頭的準度）。
            if ref and not code:
                missed.append("%s %s"
                              % (clean, contract.hunk_header_of(ref) or repr(ref)))

            items.append(contract.finding(
                title=contract.plain(item.get("title")),
                reason=contract.plain(item.get("reason")),
                diff_code=code))

        if items:
            # 空的檔案整個不放：一個底下什麼都沒有的標題會讓人以為內容漏掉了。
            mr_diff[clean] = items

    if missed:
        logger.warn("有 %d 筆 hunk 標頭在 diff 裡找不到，那幾筆沒有程式碼：%s",
                    len(missed), "；".join(missed))

    if not summary and not mr_diff:
        # 訊息帶上實際收到的鍵。這個分支最常見的成因是模型用了別的欄位名，而
        # 「都是空的」看不出那件事 —— 重問一次還是失敗的話，這一行就是要查的線索。
        raise ValueError(
            "summary 與 code_changes 都是空的（實際收到的欄位：%s）"
            % ("、".join(sorted(data.keys())) if isinstance(data, dict)
               else "(不是物件)"))

    return summary, mr_diff


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


def _lookup_jira(inputs, key, state):
    """key 有效時取回 issue 的內容，否則回 None（prompt 就少那一段）。

    取不到也回 None：JIRA 在這裡是補充資料，一張查不到的 issue 不該讓整份分析做不
    出來。入口腳本已經記了警告。
    """
    if state != contract.JIRA_STATE_OK:
        return None

    fetch = inputs.get("fetch_jira")
    if not callable(fetch):
        # 命令列單獨呼叫 analyze() 時可能沒帶這個。不是錯誤，少那一段而已。
        logger.debug("inputs 沒有 fetch_jira，prompt 不放 JIRA 那一段")
        return None

    return fetch(key)


def _on_retry(progress):
    """給 ai_utils 的重試回呼，把狀況轉成對話框上的一行字。

    沒有 progress 可用時回 None，ai_utils 就不通知 —— 命令列執行時本來就沒有對話框。
    """
    if not callable(progress):
        return None

    def report(attempt, why):
        progress(u"AI 沒有回應，第 %d 次重試（%s）" % (attempt, why))

    return report


def _stub_analysis(inputs, key, state):
    """沒有設定 AI 端點時的替代內容。

    **不讓流程失敗**是刻意的：開發期常常還沒有可用的端點，而整條流程（信封、驗證、
    渲染、圍籬處理）需要能跑完才驗得到。

    但它會在 overview 第一行明說自己是假的 —— 一份看起來正常、實際上沒問過 AI 的
    報告，比一個錯誤訊息糟得多。
    """
    logger.warn("未設定 AI 端點，產生替代內容而非真的分析")

    overview = u"\n".join([
        u"⚠️ 這份分析沒有經過 AI —— 設定檔的 Service.AI_Mode_List 沒有填 Api_URL。",
        u"以下內容是佔位用的，不反映任何實際的程式碼變更。",
        u"（diff %d 字元、JIRA %s）"
        % (len(contract.plain(inputs.get("mr_diff"))),
           key or u"無"),
    ])

    return contract.analysis_body(
        overview=overview,
        model=inputs.get("ai_model"),
        jira_key=key,
        jira_state=state,
        jira_url=contract.jira_url(key) if state == contract.JIRA_STATE_OK else "",
        mr_diff={})


def analyze(inputs):
    """產生這次分析的內容。"""
    key = contract.plain(inputs.get("jira_key"))
    state, key = _jira_state(inputs.get("jira_mode"), key)

    if state == contract.JIRA_STATE_INVALID:
        # 不讓流程失敗：一個格式不對的 key 不該讓整份分析做不出來。報告的出處會標示它。
        logger.warn("JIRA key %r 不符合樣式，視為無效", key)

    if not contract.plain(inputs.get("ai_api_url")):
        # 這一條要在取 JIRA 之前：替代內容用不到 issue，先抓等於為一份假分析打一趟
        # 網路。
        return _stub_analysis(inputs, key, state)

    api_url, api_key, model = contract.ai_credentials(inputs)

    # 確認有效**之後**才去抓 issue 的內容。
    #
    # 順序有意義：抽取那一支拿的是 MR 標題的第一個方括號，而 [WIP]、[Draft] 非常
    # 常見。先抓的話每一次都會為了這種前綴打一趟 JIRA，換回一個 404 和一筆警告。
    #
    # 抓取本身由入口腳本提供（inputs["fetch_jira"]）—— 憑證與錯誤分類留在那邊，
    # 這裡只決定「這個 key 值不值得去查」。
    inputs = dict(inputs, jira_issue=_lookup_jira(inputs, key, state))

    prompt = build_prompt(inputs)
    # prompt 本身不進 log：裡面有整份 diff，印出來會把 log 撐爆，也把原始碼落到磁碟。
    # 要看實際送出去的內容就打開除錯輸出，它會整份寫成一個檔（見下）。
    logger.info("prompt 組好了，%d 字元", len(prompt))

    debug_write = inputs.get("debug_write") or (lambda name, text: False)
    debug_write("ai_prompt.txt", prompt)

    # 兩層驗證串成同一個 parse：先要是合法 JSON，再要是認得的結構。任何一層不過都
    # 丟 ValueError，ai_utils 據此重問一次（reask=1）。
    #
    # 分兩段寫的話，第二段跑在 ask() 之外，重問就永遠觸發不到 —— 而「JSON 合法但
    # 結構不對」恰好是模型最常見的失手方式。
    attempt = [0]

    def parse(text):
        # 每一次嘗試各寫一個檔（ai_reply_1.txt、ai_reply_2.txt…）。**寫在解析之前**，
        # 所以解析失敗時那一份仍然留著 —— 那正是你需要看的那一份。覆寫同一個檔的話，
        # 重問成功會把失敗的那次蓋掉，而失敗的那次才是線索。
        attempt[0] += 1
        debug_write("ai_reply_%d.txt" % attempt[0], text)
        return parse_reply(ai_utils.as_json(text),
                           contract.plain(inputs.get("mr_diff")))

    summary, mr_diff = ai_utils.ask(
        api_url, prompt,
        api_key=api_key,
        verify_ssl=contract.ai_verify_ssl(),
        parse=parse,
        reask=1,
        on_retry=_on_retry(inputs.get("progress")))

    logger.info("AI 回覆解析完成：%d 個檔案", len(mr_diff))

    # AI 回的欄位叫 summary，產出的欄位叫 overview —— 名字在這一行交接。兩邊各自
    # 命名是刻意的：回覆格式是那個服務的事，產出格式是報告的事，其中一邊改名不該
    # 逼另一邊跟著改。
    return contract.analysis_body(
        overview=summary,
        model=model,
        jira_key=key,
        jira_state=state,
        jira_url=contract.jira_url(key) if state == contract.JIRA_STATE_OK else "",
        mr_diff=mr_diff,
    )
