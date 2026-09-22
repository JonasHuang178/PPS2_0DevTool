#!/usr/bin/env python3
"""Jira REST 的共用 API。

該放這裡的東西：對 Jira REST API 的呼叫封裝（issue、專案、搜尋、附件、
transition…），以資料結構回傳，不做 UI、不讀設定檔、不結束行程 —— 與其他共用
模組遵守同一組規則（見 openspec/specs/script-envelope）。

不該放這裡的東西：只服務單一應用功能的邏輯。那屬於該功能自己的目錄。

## 呼叫形狀

所有公開函式的前兩個參數都是 `base_url` 與 `token`，與 gitlab_utils 一致：

    issue = jira_utils.get_issue(cfg["Jira_Server_URL"],
                                 cfg["Jira_Access_Token"], "PROJ-123")

認證走 `Authorization: Bearer <token>`（Jira Server / Data Center 的 personal
access token）。權杖只進標頭，不進 log、不進 URL query —— query 會被伺服器與
代理記進存取紀錄。

## API 版本

打的是 **`/rest/api/2/`**，也就是 Jira Server / Data Center 那一套。與 Cloud 的
`/rest/api/3/` 差別不只是網址：v3 的 `description`、`comment.body` 等欄位是
ADF（Atlassian Document Format）的巢狀 JSON，v2 則是單純的字串。拿 v3 當 v2 用
的症狀是「description 怎麼變成一包 JSON」。

日後若要改打 Cloud，改動集中在 _API_PATH 與那幾個文字欄位的處理，公開介面不必動。

## 共用的底層

建立 session、逾時、重試、JSON 解析與例外基底在 http_utils，與 gitlab_utils
共用一份。留在這裡的是 Jira 自己的部分：Bearer 認證、API 根路徑、錯誤訊息怎麼挖
（Jira 放在 errorMessages / errors，GitLab 放在 message），以及 startAt / total
的分頁機制。

## 相依

需要 **requests**（見 requirements.txt）。匯入失敗時不在 import 階段爆掉，而是
延到真正呼叫時由 http_utils.require_requests() 拋出 JiraError —— 入口腳本的匯入
發生在 script_io.run() 之前，在那裡拋例外不會有結果信封，Qt 端只會顯示「腳本
沒有回傳結果 (exit code 1)」，完全看不出是少裝了套件。
"""

import json
import os

from urllib.parse import unquote

from script_utils import http_utils
from script_utils import logger

__all__ = [
    "JiraError",
    "request",
    "get_paged",
    "get_issue_info",
    "get_issue_description",
    "create_issue",
    "ensure_issue",
    "search_issues",
    "add_issue_comment",
    "update_issue_description",
    "get_issue_attachments",
    "download_issue_attachment",
]


DEFAULT_TIMEOUT = http_utils.DEFAULT_TIMEOUT

# Jira Server / Data Center。Cloud 是 /rest/api/3 且文字欄位為 ADF，見模組說明。
_API_PATH = "/rest/api/2"

# Jira 的分頁上限依端點而異，多數吃 100；取小了只是讓同樣的資料多跑幾趟。
_PAGE_SIZE = 100

# 分頁的硬上限，防止伺服器回傳異常的 total 時無限迴圈。
_MAX_PAGES = 1000


class JiraError(http_utils.HttpError):
    """Jira 呼叫失敗。

    `code` 由基底依 CODE_PREFIX 產生，形如 `JIRA_401`；沒有 HTTP 狀態碼時
    （連線失敗、逾時、少裝套件）為 `JIRA_ERROR`。入口腳本可以直接：

        except jira_utils.JiraError as exc:
            script_io.reply_fail(str(exc), code=exc.code)
    """

    CODE_PREFIX = "JIRA"


# --- 內部 ------------------------------------------------------------------

def _api_root(base_url):
    """https://jira.example.com/ -> https://jira.example.com/rest/api/2"""
    if not isinstance(base_url, str) or not base_url.strip():
        raise JiraError("Jira 伺服器網址不可為空")
    return base_url.strip().rstrip("/") + _API_PATH


def _new_session(token):
    """建立帶 Bearer 認證標頭的 session。"""
    if not isinstance(token, str) or not token.strip():
        raise JiraError("Jira 存取權杖不可為空")

    return http_utils.new_session({"Authorization": "Bearer %s" % token})


def _parse_error_message(response):
    """從 Jira 的錯誤回應裡挖出可讀的說明。

    Jira 把錯誤放在兩個地方，而且常常只有其中一個有值：

        {"errorMessages": ["Issue does not exist"], "errors": {}}
        {"errorMessages": [], "errors": {"summary": "Summary is required"}}

    兩個都挖，挖不出來時回空字串讓呼叫端只給狀態碼 —— 不要把整頁 HTML 錯誤頁
    塞進結果信封（規格要求 message 是單行）。
    """
    try:
        body = response.json()
    except ValueError:
        return ""

    if not isinstance(body, dict):
        return ""

    parts = []

    messages = body.get("errorMessages")
    if isinstance(messages, list):
        parts.extend(str(one) for one in messages if one)

    errors = body.get("errors")
    if isinstance(errors, dict):
        parts.extend("%s: %s" % (key, value) for key, value in errors.items())
    elif isinstance(errors, str) and errors.strip():
        parts.append(errors)

    return "；".join(parts)


def _check_response(response, url):
    if response.status_code < 400:
        return

    detail = _parse_error_message(response)
    hint = ""
    if response.status_code == 401:
        hint = "：token 無效或已過期"
    elif response.status_code == 403:
        # Jira Server 的 403 常常不是權限不足，而是 CAPTCHA 或 WebSudo，
        # 那兩種都不是「再試一次」能解決的，要講出來。
        hint = "：token 權限不足，或帳號被要求通過 CAPTCHA／二次驗證"
    elif response.status_code == 404:
        hint = "：找不到該資源，或 token 沒有檢視權限"

    message = "Jira 回應 %d%s" % (response.status_code, hint)
    if detail:
        message += "（%s）" % " ".join(detail.split())

    raise JiraError(message, status_code=response.status_code, url=url)


def _guard_html(response, url):
    """Jira Server 前面若有 SSO，未通過認證時可能回 200 + 登入頁 HTML。

    不擋的話，JSON 解析會失敗並報「回應不是合法的 JSON」—— 那句話指不出真正的
    成因，使用者會往「Jira 壞了」的方向查。
    """
    if "html" in response.headers.get("Content-Type", "").lower():
        raise JiraError(
            "收到 HTML 而不是 JSON，多半是被導去登入頁："
            "請確認 token 有效，且這台 Jira 不需要另外的網頁登入",
            status_code=response.status_code, url=url)


# --- 通用呼叫 --------------------------------------------------------------

def request(base_url, token, method, path, params=None, json_body=None,
            timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """對任意 Jira API 端點送出一次請求，回傳解析後的資料結構。

    path 是 /rest/api/2 之後的部分，例如 "/issue/PROJ-123"。

    這支是刻意保留的逃生口：需要的端點還沒有對應的封裝時，呼叫端不必等人補
    函式，也不必自己重寫一次認證、重試與錯誤轉換。

    verify_ssl 預設開啟，也收 CA 憑證檔的路徑（requests 原生支援）。內部 CA 的
    正解是給 CA 路徑，不是把驗證關掉。
    """
    http_utils.require_requests(JiraError)

    url = _api_root(base_url) + path
    session = _new_session(token)
    try:
        logger.debug("Jira %s %s", method, url)
        response = http_utils.send(session, method, url, params, json_body,
                                   timeout, verify_ssl, JiraError)
        _check_response(response, url)
        _guard_html(response, url)
        return http_utils.parse_json(response, url, JiraError)
    finally:
        session.close()


def get_paged(base_url, token, path, params=None, items_key="values",
              max_items=None, timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得一個分頁端點的全部項目，回傳 list。

    Jira 的分頁與 GitLab 不同：不看標頭，而是以回應中的 startAt / maxResults /
    total 推進，因此這段無法與 gitlab_utils 共用。

    items_key 是清單在回應中的欄位名 —— Jira 各端點不一致：搜尋放在 "issues"、
    多數新端點放在 "values"、留言放在 "comments"。寫死任何一個都會在下一個端點
    壞掉，所以由呼叫端指定。

    端點直接回傳陣列（例如 /project）時原樣回傳，不強求分頁結構。

    max_items 為「可能很大」的查詢設上限，達到即停止翻頁。None 表示不限。
    另有 _MAX_PAGES 作為硬上限：伺服器回傳異常的 total 時，沒有這道防線會變成
    無限迴圈，而使用者看到的只是一個永遠不結束的進度條。
    """
    http_utils.require_requests(JiraError)

    url = _api_root(base_url) + path
    query = dict(params or {})
    query.setdefault("maxResults", _PAGE_SIZE)

    items = []
    session = _new_session(token)
    try:
        start_at = 0
        for _ in range(_MAX_PAGES):
            query["startAt"] = start_at
            logger.debug("Jira GET %s（startAt=%d）", url, start_at)

            response = http_utils.send(session, "GET", url, query, None,
                                       timeout, verify_ssl, JiraError)
            _check_response(response, url)
            _guard_html(response, url)

            body = http_utils.parse_json(response, url, JiraError)
            if body is None:
                break

            # 不分頁的端點直接回陣列。
            if isinstance(body, list):
                items.extend(body)
                break

            if not isinstance(body, dict):
                raise JiraError("該端點的回應不是物件或陣列，無法分頁：%s" % path,
                                url=url)

            page = body.get(items_key)
            if page is None:
                raise JiraError(
                    "回應中沒有欄位 %r，請確認 items_key 是否正確（可用的有：%s）"
                    % (items_key, "、".join(sorted(body.keys())) or "無"),
                    url=url)
            if not isinstance(page, list):
                raise JiraError("回應的 %r 不是清單，無法分頁：%s"
                                % (items_key, path), url=url)

            items.extend(page)
            if max_items is not None and len(items) >= max_items:
                return items[:max_items]

            start_at += len(page)
            total = body.get("total")
            # 沒有 total 的端點（Jira 的部分 API 只給 isLast）以「這頁空了」為準。
            if not page or (isinstance(total, int) and start_at >= total):
                break
        else:
            logger.warn("Jira 分頁超過 %d 頁，提前停止：%s", _MAX_PAGES, path)
    finally:
        session.close()

    logger.debug("Jira %s 取得 %d 筆", path, len(items))
    return items


# --- Issue ------------------------------------------------------------------

def get_issue_info(base_url, token, key, fields=None,
                   timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得一張 issue 的完整資訊。key 形如 "PROJ-123"。

    fields 可指定只取某些欄位（字串或字串序列），None 表示全部。一張 issue 的
    完整 JSON 動輒數十 KB，多數呼叫端只用得到幾個欄位，而結果最終要經 stdout
    送回 Qt —— 只要能列舉就列舉。

    回傳 Jira 原樣的 issue 物件，不挑欄位也不攤平巢狀結構 —— 挑欄位是呼叫端的
    決定，共用模組先砍的話下一個呼叫端就得回來改這裡。
    """
    if not isinstance(key, str) or not key.strip():
        raise JiraError("issue key 不可為空")

    params = {}
    if fields:
        params["fields"] = fields if isinstance(fields, str) else ",".join(fields)

    return request(base_url, token, "GET", "/issue/%s" % key.strip(),
                   params=params or None, timeout=timeout, verify_ssl=verify_ssl)


def get_issue_description(base_url, token, key,
                          timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得一張 issue 的描述文字，回傳字串。

    只向伺服器要 description 一個欄位，不把整張 issue 拉回來。

    **沒有描述時回傳空字串**，不是 None 也不是錯誤 —— 「這張單沒寫描述」是正常
    狀態，讓呼叫端每次都要先判斷 None 只是把同一段 if 複製到每個呼叫點。

    若伺服器其實是 Jira Cloud（/rest/api/3），description 會是 ADF 的巢狀 JSON
    而不是字串。那種情況這裡**明確拋出 JiraError**，而不是回傳一包 dict ——
    回 dict 的話，錯誤會在呼叫端拿它去做字串處理時才爆，訊息還完全指不出成因。
    """
    issue = get_issue_info(base_url, token, key, fields="description",
                           timeout=timeout, verify_ssl=verify_ssl)

    description = (issue or {}).get("fields", {}).get("description")

    if description is None:
        return ""
    if isinstance(description, str):
        return description

    raise JiraError(
        "description 不是字串（收到 %s），這台伺服器看起來是 Jira Cloud："
        "Cloud 的 /rest/api/3 以 ADF 巢狀 JSON 表示文字欄位，而本模組打的是 "
        "Server / DC 的 /rest/api/2" % type(description).__name__)


def create_issue(base_url, token, project, result_json,
                 timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """建立一張 issue，回傳 Jira 的回應（含 id、key、self）。

    project 是專案的 key（例如 "PROJ"），會被填進欄位中；result_json 裡若已經
    有 project，以這個參數為準 —— 參數是呼叫端當下明講的，比資料裡帶的舊值可信。

    result_json 收 dict 或 JSON 字串，兩種形狀都認：

        {"summary": "標題", "issuetype": {"name": "Bug"}}
        {"fields": {"summary": "標題", "issuetype": {"name": "Bug"}}}

    沒有 fields 外層時自動包一層。兩種都收是因為呼叫端可能直接沿用上一支腳本
    回傳的 data，而那份資料是哪一種形狀取決於它怎麼產生的；認錯了只會換來一個
    看不懂的 400。

    必填欄位（summary、issuetype，以及各專案自訂的必填項）不在這裡檢查 ——
    每個 Jira 專案的必填欄位都不一樣，寫死一份只會在別的專案上擋住合法的呼叫。
    缺漏時 Jira 會回 400 並指出是哪個欄位，那份訊息會被挖進 JiraError。

    ⚠️ **這支不是可重入的。** 重跑一次會多建一張 issue，而規格要求參與流程的
    腳本可重入（見 openspec/specs/script-execution）。呼叫端若會出現在多步驟
    流程裡，要自己先查有沒有既有的那張單再決定建不建 —— 共用模組不代為判斷，
    因為「算不算同一張單」是各功能自己的定義（同標題？同 label？同自訂欄位？）。
    """
    if not isinstance(project, str) or not project.strip():
        raise JiraError("專案 key 不可為空")

    if isinstance(result_json, str):
        try:
            payload = json.loads(result_json)
        except ValueError as exc:
            raise JiraError("result_json 不是合法的 JSON：%s" % exc)
    elif isinstance(result_json, dict):
        payload = dict(result_json)
    else:
        raise JiraError("result_json 必須是 dict 或 JSON 字串，收到 %s"
                        % type(result_json).__name__)

    if "fields" in payload and isinstance(payload["fields"], dict):
        fields = dict(payload["fields"])
    else:
        fields = payload

    fields["project"] = {"key": project.strip()}

    logger.info("在 %s 建立 issue", project)
    response = request(base_url, token, "POST", "/issue",
                       json_body={"fields": fields},
                       timeout=timeout, verify_ssl=verify_ssl)

    logger.info("已建立 %s", (response or {}).get("key", "(未回傳 key)"))
    return response


def _quote_jql(value):
    """把值包成 JQL 的字串常量，並跳脫其中的反斜線與雙引號。

    不跳脫的話，標題裡一個雙引號就會讓整段 JQL 語法錯誤（Jira 回 400，而訊息
    指向一段呼叫端從沒寫過的查詢字串），刻意構造的標題更可以改寫查詢條件。
    """
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % text


def search_issues(base_url, token, jql, fields=None, max_items=None,
                  timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """以 JQL 搜尋 issue，回傳 issue 物件清單。

    fields 可指定只取某些欄位（字串或序列），None 表示 Jira 的預設欄位集。
    max_items 為可能很大的查詢設上限。

    分頁由 get_paged 處理；搜尋端點的清單欄位是 "issues"。
    """
    if not isinstance(jql, str) or not jql.strip():
        raise JiraError("JQL 不可為空")

    params = {"jql": jql}
    if fields:
        params["fields"] = fields if isinstance(fields, str) else ",".join(fields)

    return get_paged(base_url, token, "/search", params=params,
                     items_key="issues", max_items=max_items,
                     timeout=timeout, verify_ssl=verify_ssl)


def ensure_issue(base_url, token, project, result_json, match_jql=None,
                 timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """建立 issue，但**已經有一張同樣的就沿用既有的**，回傳 (issue, created)。

    這是 create_issue() 的可重入版本。規格要求參與流程的腳本可重入（見
    openspec/specs/script-execution）：一條三步流程的第三步失敗、使用者重跑時，
    第一步的建單會再跑一次，用 create_issue 就會累積出一堆重複的單。

    created 為 True 表示這次真的建了一張，False 表示沿用既有的。回傳這個布林
    而不是讓呼叫端自己比對，是因為「新建」與「已存在」往往要給使用者不同的訊息。

    ## 怎麼算「同一張單」

    預設是**同專案 + 標題完全相同**。要換別的判準就自己傳 match_jql：

        ensure_issue(url, token, "PROJ", fields,
                     match_jql='project = "PROJ" AND labels = "auto" '
                               'AND status != Closed')

    預設判準用 JQL 的 summary ~ 做初篩，**但 ~ 是模糊比對**（依詞彙斷字，
    "修正 A" 可能撈到 "修正 A 與 B"），所以撈回來之後還會在本地做一次標題的
    完全相等比對。少了那一步，ensure 會把一張只是標題相似的單誤認成同一張，
    然後該建的單永遠不會被建 —— 而那個錯誤沒有任何訊息，只有「怎麼沒有新單」。

    自訂 match_jql 時**不做本地複驗**：那段查詢是呼叫端寫的，它自己定義了什麼
    叫同一張。

    比對到多張時沿用**最早建立**的那張並記一筆警告 —— 重跑時每次都挑同一張，
    行為才穩定。

    ## 回傳形狀

    兩條路徑回傳的 issue 物件結構相同：新建之後會再讀一次那張單，而不是直接回
    Jira 建立 API 那份只有 id / key / self 的精簡回應。不這麼做的話，呼叫端拿到
    的欄位會依「這次有沒有建」而不同，那種依路徑而異的回傳值遲早會在某個分支
    上爆掉。代價是新建路徑多一次請求。
    """
    if not isinstance(project, str) or not project.strip():
        raise JiraError("專案 key 不可為空")

    # 先把 result_json 正規化成 fields，這樣預設判準才拿得到 summary。
    if isinstance(result_json, str):
        try:
            payload = json.loads(result_json)
        except ValueError as exc:
            raise JiraError("result_json 不是合法的 JSON：%s" % exc)
    elif isinstance(result_json, dict):
        payload = dict(result_json)
    else:
        raise JiraError("result_json 必須是 dict 或 JSON 字串，收到 %s"
                        % type(result_json).__name__)

    fields = dict(payload["fields"]) if (
        "fields" in payload and isinstance(payload["fields"], dict)) else payload

    summary = fields.get("summary")
    jql = match_jql
    verify_summary = False

    if not jql:
        if not isinstance(summary, str) or not summary.strip():
            raise JiraError(
                "預設是以標題判斷是否為同一張單，因此 result_json 必須有 "
                "summary；要用別的判準請傳 match_jql")
        jql = ("project = %s AND summary ~ %s ORDER BY created ASC"
               % (_quote_jql(project.strip()), _quote_jql(summary)))
        verify_summary = True

    logger.debug("ensure_issue 以 JQL 尋找既有單：%s", jql)
    candidates = search_issues(base_url, token, jql, fields="summary",
                               max_items=50, timeout=timeout,
                               verify_ssl=verify_ssl)

    if verify_summary:
        # ~ 是模糊比對，這裡做完全相等的複驗（見 docstring）。
        candidates = [one for one in candidates
                      if (one.get("fields") or {}).get("summary") == summary]

    if candidates:
        if len(candidates) > 1:
            logger.warn("找到 %d 張符合的既有單，沿用最早建立的 %s",
                        len(candidates), candidates[0].get("key"))
        key = candidates[0].get("key")
        logger.info("沿用既有的 %s，不建立新單", key)
        return (get_issue_info(base_url, token, key, timeout=timeout,
                               verify_ssl=verify_ssl), False)

    created = create_issue(base_url, token, project, fields,
                           timeout=timeout, verify_ssl=verify_ssl)
    key = (created or {}).get("key")
    if not key:
        raise JiraError("建立 issue 的回應沒有 key，無法回讀該單")

    # 回讀，讓兩條路徑的回傳結構一致（見 docstring）。
    return (get_issue_info(base_url, token, key, timeout=timeout,
                           verify_ssl=verify_ssl), True)


# --- 留言與描述 -------------------------------------------------------------

def add_issue_comment(base_url, token, key, comment,
                      timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """在 issue 底下新增一則留言，回傳 Jira 建立的留言物件。

    comment 是純文字（Jira Server 的 wiki markup 也可以）。v2 的留言 body 就是
    字串；Cloud 的 v3 是 ADF 巢狀 JSON，傳字串過去會被拒絕 —— 本模組打的是 v2。

    空白留言在這裡就擋掉，不送出去換一個 Jira 的 400：空留言一定是呼叫端上游
    算出了空字串，訊息說清楚比轉述伺服器的抱怨有用。

    ⚠️ **這支不可重入。** 重跑會多留一則一樣的言。會出現在多步驟流程裡的呼叫端，
    要自己先讀既有留言判斷該不該留 —— 「算不算重複」是各功能自己的定義。
    """
    if not isinstance(key, str) or not key.strip():
        raise JiraError("issue key 不可為空")
    if not isinstance(comment, str) or not comment.strip():
        raise JiraError("留言內容不可為空")

    logger.info("在 %s 新增留言", key)
    return request(base_url, token, "POST", "/issue/%s/comment" % key.strip(),
                   json_body={"body": comment},
                   timeout=timeout, verify_ssl=verify_ssl)


def update_issue_description(base_url, token, key, content,
                             timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """更新 issue 的描述，成功時回傳 None。

    content 必須是字串（v2 的描述就是字串）。傳 dict 進來會被擋下並指出那是
    Cloud 的 ADF 格式 —— 與 get_issue_description() 的守衛是同一件事的兩面：
    讀的時候不讓 ADF 偽裝成字串，寫的時候不讓 ADF 被送進 v2 端點。

    空字串是合法的，意思是把描述清空。

    這支**是可重入的**：把描述設成同一個值兩次，結果與設一次相同，因此放進
    多步驟流程裡重跑是安全的（與 add_issue_comment 相反）。

    Jira 更新成功時回 204 沒有內容，所以這裡回傳 None；失敗一律以 JiraError
    表示，不需要檢查回傳值。
    """
    if not isinstance(key, str) or not key.strip():
        raise JiraError("issue key 不可為空")
    if not isinstance(content, str):
        raise JiraError(
            "描述必須是字串（收到 %s）。巢狀物件是 Jira Cloud 的 ADF 格式，"
            "本模組打的是 Server / DC 的 /rest/api/2" % type(content).__name__)

    logger.info("更新 %s 的描述", key)
    return request(base_url, token, "PUT", "/issue/%s" % key.strip(),
                   json_body={"fields": {"description": content}},
                   timeout=timeout, verify_ssl=verify_ssl)


# --- 附件 -------------------------------------------------------------------

def get_issue_attachments(base_url, token, key,
                          timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出 issue 的附件，回傳附件物件清單。

    每一筆含 Jira 原樣的欄位，其中 `content` 是該附件的下載網址，正是
    download_issue_attachment() 的第一個參數：

        for item in get_issue_attachments(url, token, "PROJ-1"):
            download_issue_attachment(item["content"], token,
                                      os.path.join(folder, item["filename"]))

    沒有附件時回傳空清單，不是錯誤 —— 多數 issue 本來就沒有附件。
    """
    issue = get_issue_info(base_url, token, key, fields="attachment",
                           timeout=timeout, verify_ssl=verify_ssl)

    attachments = (issue or {}).get("fields", {}).get("attachment")
    if not attachments:
        return []
    if not isinstance(attachments, list):
        raise JiraError("attachment 欄位不是清單，收到 %s"
                        % type(attachments).__name__)

    logger.debug("%s 有 %d 個附件", key, len(attachments))
    return attachments


def _filename_from_response(response, download_url):
    """決定存檔用的檔名：優先用伺服器給的，其次用網址尾巴。

    Jira 的附件下載網址結尾常常是附件 ID 而不是檔名，所以先看
    Content-Disposition。兩者都沒有時給一個明確的預設，總比寫出一個叫
    "content" 的檔案好。

    非 ASCII 檔名要先看 `filename*=`：HTTP 標頭只能承載 latin-1，因此中文等
    檔名一律以 RFC 5987 的 `filename*=UTF-8''%E5%A0%B1...` 形式傳送，而同一個
    標頭裡的 `filename=` 往往是伺服器退而求其次的 ASCII 版本（常常只剩底線或
    問號）。只解析 `filename=` 的話，中文附件會被存成一個名字面目全非的檔案。
    """
    disposition = response.headers.get("Content-Disposition", "")

    # RFC 5987：filename*=<charset>'<language>'<percent-encoded>
    if "filename*=" in disposition:
        raw = disposition.split("filename*=", 1)[1].split(";", 1)[0].strip()
        parts = raw.split("'", 2)
        if len(parts) == 3:
            charset, _language, encoded = parts
            try:
                name = os.path.basename(
                    unquote(encoded, encoding=charset or "utf-8"))
                if name:
                    return name
            except (LookupError, ValueError):
                pass      # 編碼名稱怪異時退回底下的 filename=

    marker = "filename="
    if marker in disposition:
        name = disposition.split(marker, 1)[1].strip()
        if name.startswith('"'):
            name = name[1:].split('"', 1)[0]
        else:
            name = name.split(";", 1)[0].strip()
        name = os.path.basename(name.strip())
        if name:
            return name

    tail = os.path.basename(unquote(download_url.split("?", 1)[0].rstrip("/")))
    return tail or "attachment.bin"


def download_issue_attachment(download_url, token, save_path,
                              timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """下載一個附件，回傳寫出的絕對路徑。

    第一個參數是**附件的下載網址**（get_issue_attachments() 每筆的 `content`），
    不是伺服器根網址 —— 那個網址已經是完整的，不必再拼 /rest/api/2。

    save_path 是目的檔案的路徑；若它是一個已存在的目錄，則存進該目錄，檔名取自
    伺服器的 Content-Disposition，取不到才用網址尾巴。

    內容以**串流**寫入，不先進記憶體：附件可能是幾百 MB 的 log 或 dump，而腳本
    行程沒有多餘的空間可揮霍。

    目的檔案已存在直接覆蓋（重跑同一條流程要得到同樣的結果）；上層目錄不存在
    則拋出例外，不自動建立 —— 與 file_utils.write_file() 同一個理由：自動建立會
    讓打錯的路徑靜默生出一棵沒人要的目錄樹。需要時先呼叫
    system_utils.create_folder()。

    收到 HTML 時明確報錯（多半是被導去登入頁），不把登入頁存成附件 —— 那種檔案
    打開來才發現不對，而那時已經離成因很遠了。
    """
    http_utils.require_requests(JiraError)

    if not isinstance(download_url, str) or not download_url.strip():
        raise JiraError("附件下載網址不可為空")
    if not isinstance(save_path, str) or not save_path.strip():
        raise JiraError("存檔路徑不可為空")

    session = _new_session(token)
    # 這條路由回的是檔案內容，不是 JSON。
    session.headers["Accept"] = "*/*"

    response = None
    try:
        logger.debug("下載附件 %s", download_url)
        response = http_utils.send(session, "GET", download_url.strip(),
                                   None, None, timeout, verify_ssl, JiraError,
                                   stream=True)
        _check_response(response, download_url)
        _guard_html(response, download_url)

        destination = save_path
        if os.path.isdir(save_path):
            destination = os.path.join(
                save_path, _filename_from_response(response, download_url))

        written = 0
        with open(destination, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
                    written += len(chunk)
    finally:
        if response is not None:
            response.close()
        session.close()

    absolute = os.path.abspath(destination)
    logger.info("附件已下載：%s（%d bytes）", absolute, written)
    return absolute
