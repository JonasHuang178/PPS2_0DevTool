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

from script_utils import http_utils
from script_utils import logger

__all__ = [
    "JiraError",
    "request",
    "get_paged",
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
