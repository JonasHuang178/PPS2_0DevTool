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

### 作者填寫的描述
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
OUTPUT_SPEC = u"""\
## 回覆格式
只回覆一個 JSON 物件，不要有任何開場白、說明或 markdown 圍籬。

{
  "overview": "整體變更的摘要，三到五句",
  "files": [
    {
      "path": "檔案路徑，與上面 diff 裡的一致",
      "findings": [
        {
          "title": "一句話講完這個發現",
          "reason": "為什麼值得注意，兩三句",
          "diff": "相關的那幾行 diff，可留空"
        }
      ]
    }
  ]
}

沒有值得注意之處的檔案不要放進 files。
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

def _jira_block(issue):
    """JIRA 那一段。沒有 issue 就回空字串，整段不出現在 prompt 裡。

    不放的理由不只是省 context：一段寫著「（無）」的 JIRA 區塊會讓模型以為那張 issue
    存在但內容是空的，然後對著它生出評論。
    """
    if not issue:
        return ""

    return JIRA_TEMPLATE.format(
        key=contract.plain(issue.get("key")),
        summary=contract.plain(issue.get("summary")),
        status=contract.plain(issue.get("status")) or u"（未知）",
        type=contract.plain(issue.get("type")) or u"（未知）",
        description=contract.plain(issue.get("description")) or NO_DESCRIPTION,
    )


def build_prompt(inputs):
    """把素材組成要送給 AI 的 prompt。回傳一個字串。

    單獨拉成一支函式而不是塞在 analyze() 裡，是為了能單獨看、單獨測：

        python -c "import summary; print(summary.build_prompt({...}))"

    這樣改完 prompt 可以先印出來確認，不必真的打一次 AI。
    """
    return PROMPT_TEMPLATE.format(
        role=ROLE_PROMPT.strip(),
        repo=contract.plain(inputs.get("repo")) or u"（未指定）",
        mr_iid=contract.plain(inputs.get("mr_iid")) or u"?",
        description=contract.plain(inputs.get("description")) or NO_DESCRIPTION,
        jira=_jira_block(inputs.get("jira_issue")),
        diff=contract.plain(inputs.get("mr_diff")) or u"（沒有取到任何差異）",
        output_spec=OUTPUT_SPEC,
    )


def parse_reply(data):
    """把 AI 回的 JSON 轉成 (overview, mrDiff)。

    ⚠️ 與 OUTPUT_SPEC 是同一件事的兩面，改格式要一起改。

    格式不對時丟 ValueError —— ai_utils 收到 ValueError 會重問一次（見 ask_json 的
    reask）。拿回一個半殘的結構硬湊比重問糟得多：湊出來的報告看起來是完整的。
    """
    overview = contract.plain(data.get("overview"))

    files = data.get("files")
    if files is None:
        files = []
    if not isinstance(files, list):
        raise ValueError("files 不是陣列，而是 %s" % type(files).__name__)

    mr_diff = {}
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise ValueError("files[%d] 不是物件，而是 %s"
                             % (index, type(entry).__name__))

        path = contract.plain(entry.get("path"))
        if not path:
            # 沒有路徑的發現放不進報告 —— mrDiff 是以路徑為鍵的。
            raise ValueError("files[%d] 少了 path" % index)

        findings = entry.get("findings")
        if findings is None:
            findings = []
        if not isinstance(findings, list):
            raise ValueError("files[%d].findings 不是陣列，而是 %s"
                             % (index, type(findings).__name__))

        items = []
        for item in findings:
            if not isinstance(item, dict):
                raise ValueError("%s 底下有一筆發現不是物件，而是 %s"
                                 % (path, type(item).__name__))
            items.append(contract.finding(
                title=contract.plain(item.get("title")),
                reason=contract.plain(item.get("reason")),
                diff_code=contract.plain(item.get("diff"))))

        if items:
            # 空的檔案整個不放：一個底下什麼都沒有的標題會讓人以為內容漏掉了。
            mr_diff[path] = items

    if not overview and not mr_diff:
        raise ValueError("overview 與 files 都是空的")

    return overview, mr_diff


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
        return _stub_analysis(inputs, key, state)

    api_url, api_key, model = contract.ai_credentials(inputs)

    prompt = build_prompt(inputs)
    # prompt 本身不進 log：裡面有整份 diff，印出來會把 log 撐爆，也把原始碼落到磁碟。
    logger.info("prompt 組好了，%d 字元", len(prompt))

    # 兩層驗證串成同一個 parse：先要是合法 JSON，再要是認得的結構。任何一層不過都
    # 丟 ValueError，ai_utils 據此重問一次（reask=1）。
    #
    # 分兩段寫的話，第二段跑在 ask() 之外，重問就永遠觸發不到 —— 而「JSON 合法但
    # 結構不對」恰好是模型最常見的失手方式。
    overview, mr_diff = ai_utils.ask(
        api_url, prompt,
        api_key=api_key,
        parse=lambda text: parse_reply(ai_utils.as_json(text)),
        reask=1,
        on_retry=_on_retry(inputs.get("progress")))

    logger.info("AI 回覆解析完成：%d 個檔案", len(mr_diff))

    return contract.analysis_body(
        overview=overview,
        model=model,
        jira_key=key,
        jira_state=state,
        jira_url=contract.jira_url(key) if state == contract.JIRA_STATE_OK else "",
        mr_diff=mr_diff,
    )
