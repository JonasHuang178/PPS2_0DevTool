#!/usr/bin/env python3
"""GitLab REST 的共用 API。

該放這裡的東西：對 GitLab REST API 的呼叫封裝（專案、分支、merge request、
issue、pipeline…），以資料結構回傳，不做 UI、不讀設定檔、不結束行程 ——
與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）。

不該放這裡的東西：只服務單一應用功能的邏輯。那屬於該功能自己的目錄。

認證權杖一律由入口腳本自設定檔取出後明著傳入，共用模組 MUST NOT 自行讀取
環境變數或設定檔。

## 呼叫形狀

所有公開函式的前兩個參數都是 `server_url` 與 `token`，沒有 client 物件：

    mrs = gitlab_utils.get_merge_requests(
        cfg["Gitlab_Server_URL"], cfg["Gitlab_Access_Token"],
        "group/project", created_after_days=7)

這是本專案先前就寫進 README 的契約，也與 system_utils 的平坦函式一致。代價是
每次呼叫各自建立連線；入口腳本通常只打一兩支 API，那點成本可以忽略，而真正
會累積的分頁查詢在內部共用同一個 session。哪天某個呼叫端真的要連打數十次，
那時才是引入 client 物件的時機 —— 現在引入只是多一套並存的用法。

## 相依

這個模組需要 **requests**（本專案唯一的第三方相依，見 requirements.txt）。

匯入失敗時不在 import 階段爆掉，而是延到真正呼叫時才拋出 GitLabError。理由：
入口腳本的 `from script_utils import gitlab_utils` 發生在 `script_io.run()`
之前，那個階段拋例外的話不會有結果信封，Qt 端只會顯示「腳本沒有回傳結果
(exit code 1)」—— 使用者完全看不出是少裝了套件。延到呼叫時，錯誤就會走
script_io 的統一處理變成一則說得清楚的 FAIL。
"""

import base64
import time

try:
    import requests
except ImportError:      # 見上面「相依」段落，這裡刻意不讓它在 import 階段爆掉
    requests = None

from script_utils import logger

__all__ = [
    "GitLabError",
    "request",
    "get_paged",
    "get_project",
    "list_branches",
    "get_file_content",
    "get_merge_requests",
    "get_merge_request",
]


# 逾時一律要有：沒有逾時的請求會讓整個 Qt 流程卡死，而使用者只能按取消。
DEFAULT_TIMEOUT = 30

# 這些狀態碼重試有意義：429 是被限流，5xx 多半是伺服器端的暫時狀況。
# 4xx 的其餘成員（401 權杖錯、404 找不到）重試幾次結果都一樣，只是拖長失敗。
_RETRY_STATUS = (429, 500, 502, 503, 504)
_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.0

# GitLab 每頁上限 100。取小了只是讓同樣的資料多跑幾趟。
_PER_PAGE = 100

# 分頁的硬上限，防止伺服器回傳異常的 next page 時無限迴圈。
_MAX_PAGES = 1000


class GitLabError(Exception):
    """GitLab 呼叫失敗。

    共用模組不結束行程也不自己印訊息，一律以例外拋出，由入口腳本決定怎麼回報。

    `code` 是給結果信封的 `error.code` 用的，形如 `GITLAB_401`；沒有 HTTP 狀態
    碼時（連線失敗、逾時、少裝套件）為 `GITLAB_ERROR`。入口腳本可以直接：

        except gitlab_utils.GitLabError as exc:
            script_io.reply_fail(str(exc), code=exc.code)
    """

    def __init__(self, message, status_code=None, url=""):
        super(GitLabError, self).__init__(message)
        self.status_code = status_code
        self.url = url

    @property
    def code(self):
        if self.status_code is None:
            return "GITLAB_ERROR"
        return "GITLAB_%d" % self.status_code


# --- 內部 ------------------------------------------------------------------

def _require_requests():
    if requests is None:
        raise GitLabError(
            "缺少 requests 套件，無法呼叫 GitLab。請執行 pip install requests")


def _api_root(server_url):
    """https://gitlab.example.com/ -> https://gitlab.example.com/api/v4"""
    if not isinstance(server_url, str) or not server_url.strip():
        raise GitLabError("GitLab 伺服器網址不可為空")
    return server_url.strip().rstrip("/") + "/api/v4"


def _encode_path(value):
    """把路徑片段編碼成可以塞進 URL 的樣子。

    GitLab 允許用 "group/project" 當專案 ID，但那個斜線必須編成 %2F，否則會被
    當成路徑分隔而打到不存在的端點。檔案路徑同理。
    """
    from urllib.parse import quote
    return quote(str(value), safe="")


def _new_session(token):
    """建立帶認證標頭的 session。

    權杖只放進標頭，絕不進 log、也不放進 URL query —— query 會被伺服器與代理
    記進存取紀錄。
    """
    if not isinstance(token, str) or not token.strip():
        raise GitLabError("GitLab 存取權杖不可為空")

    session = requests.Session()
    session.headers.update({
        "PRIVATE-TOKEN": token,
        "Accept": "application/json",
    })
    return session


def _parse_error_message(response):
    """從 GitLab 的錯誤回應裡挖出可讀的說明。

    GitLab 有時回 {"message": ...}、有時回 {"error": ...}，而 message 可能是
    字串也可能是物件。挖不出來時退回狀態碼本身，不要回傳整段 HTML —— 那會
    把一整頁錯誤頁塞進結果信封的 message（規格要求 message 是單行）。
    """
    try:
        body = response.json()
    except ValueError:
        return ""

    if isinstance(body, dict):
        for key in ("message", "error", "error_description"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value:
                return str(value)
    return ""


def _check_response(response, url):
    if response.status_code < 400:
        return

    detail = _parse_error_message(response)
    hint = ""
    if response.status_code == 401:
        hint = "：token 無效或已過期"
    elif response.status_code == 403:
        hint = "：token 權限不足"
    elif response.status_code == 404:
        hint = "：找不到該資源，或 token 沒有讀取權限"

    message = "GitLab 回應 %d%s" % (response.status_code, hint)
    if detail:
        # 單行：message 同時服務訊息框、命令列與 CI 日誌。
        message += "（%s）" % " ".join(detail.split())

    raise GitLabError(message, status_code=response.status_code, url=url)


def _send(session, method, url, params, json_body, timeout, verify_ssl):
    """送出一次請求，必要時重試，回傳 requests 的 response。

    重試只針對限流與伺服器端暫時狀況（見 _RETRY_STATUS）。連線錯誤與逾時也
    重試 —— 那多半是網路抖動。
    """
    last_error = None

    for attempt in range(_MAX_RETRIES + 1):
        if attempt:
            wait = _RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warn("GitLab 呼叫失敗，%.1f 秒後重試（第 %d 次）", wait, attempt)
            time.sleep(wait)

        try:
            response = session.request(method, url, params=params,
                                       json=json_body, timeout=timeout,
                                       verify=verify_ssl)
        except requests.exceptions.RequestException as exc:
            last_error = GitLabError("無法連線 GitLab：%s" % exc, url=url)
            continue

        if response.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
            last_error = GitLabError(
                "GitLab 回應 %d" % response.status_code,
                status_code=response.status_code, url=url)
            continue

        return response

    raise last_error


def _json_body(response, url):
    """回應轉成 Python 資料結構。

    204 之類沒有內容的回應回傳 None —— 那是正常結果，不是錯誤。
    """
    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except ValueError:
        raise GitLabError("GitLab 回應不是合法的 JSON（HTTP %d）"
                          % response.status_code,
                          status_code=response.status_code, url=url)


# --- 通用呼叫 --------------------------------------------------------------

def request(server_url, token, method, path, params=None, json_body=None,
            timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """對任意 GitLab API 端點送出一次請求，回傳解析後的資料結構。

    path 是 /api/v4 之後的部分，例如 "/projects/群組%2F專案"。需要編碼的片段
    請先自行處理，或使用底下針對常見資源寫好的函式。

    這支是刻意保留的逃生口：需要的端點還沒有對應的封裝時，呼叫端不必等人補
    函式，也不必自己重寫一次認證、重試與錯誤轉換。

    verify_ssl 預設開啟。內部 GitLab 用自簽憑證時才關掉，而那是一個要明著寫出來
    的決定，不是預設值。
    """
    _require_requests()

    url = _api_root(server_url) + path
    session = _new_session(token)
    try:
        logger.debug("GitLab %s %s", method, url)
        response = _send(session, method, url, params, json_body,
                         timeout, verify_ssl)
        _check_response(response, url)
        return _json_body(response, url)
    finally:
        session.close()


def get_paged(server_url, token, path, params=None, timeout=DEFAULT_TIMEOUT,
              verify_ssl=True, max_items=None):
    """取得一個清單型端點的全部項目，自動翻頁，回傳 list。

    翻頁依 GitLab 的 X-Next-Page 標頭；該標頭為空即結束。整趟共用同一個
    session，連線只建立一次。

    max_items 用來為「可能很大」的查詢設上限，達到即停止翻頁。None 表示不限。

    另有 _MAX_PAGES 作為硬上限：伺服器回傳異常的 next page 時，沒有這道防線
    會變成無限迴圈，而使用者看到的只是一個永遠不結束的進度條。
    """
    _require_requests()

    url = _api_root(server_url) + path
    query = dict(params or {})
    query.setdefault("per_page", _PER_PAGE)

    items = []
    session = _new_session(token)
    try:
        page = 1
        for _ in range(_MAX_PAGES):
            query["page"] = page
            logger.debug("GitLab GET %s（第 %d 頁）", url, page)

            response = _send(session, "GET", url, query, None,
                             timeout, verify_ssl)
            _check_response(response, url)

            body = _json_body(response, url)
            if body is None:
                break
            if not isinstance(body, list):
                raise GitLabError("該端點回傳的不是清單，無法分頁：%s" % path,
                                  url=url)

            items.extend(body)
            if max_items is not None and len(items) >= max_items:
                return items[:max_items]

            next_page = response.headers.get("X-Next-Page", "")
            if not next_page:
                break
            page = int(next_page)
        else:
            logger.warn("GitLab 分頁超過 %d 頁，提前停止：%s", _MAX_PAGES, path)
    finally:
        session.close()

    logger.debug("GitLab %s 取得 %d 筆", path, len(items))
    return items


# --- 專案與檔案 ------------------------------------------------------------

def get_project(server_url, token, repo, timeout=DEFAULT_TIMEOUT,
                verify_ssl=True):
    """取得專案資訊。repo 為 "group/project" 或數字專案 ID。"""
    return request(server_url, token, "GET",
                   "/projects/%s" % _encode_path(repo),
                   timeout=timeout, verify_ssl=verify_ssl)


def list_branches(server_url, token, repo, search=None,
                  timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出專案的分支。search 有值時只回傳名稱含該字串的分支。"""
    params = {}
    if search:
        params["search"] = search

    return get_paged(server_url, token,
                     "/projects/%s/repository/branches" % _encode_path(repo),
                     params=params, timeout=timeout, verify_ssl=verify_ssl)


def get_file_content(server_url, token, repo, file_path, ref,
                     timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """讀出 repo 中某個檔案的內容，回傳字串。

    ref 是分支、tag 或 commit SHA。

    GitLab 這個端點回的是 base64，這裡解碼後以 UTF-8 轉成字串 —— 回傳可直接
    使用的資料結構是共用模組的規則之一，讓呼叫端各自解一次 base64 只是把同樣
    的程式碼複製到每個呼叫點。

    檔案不是 UTF-8 文字時拋出 GitLabError：與其回傳一串亂碼讓呼叫端在更下游
    才發現，不如在這裡說清楚。
    """
    body = request(server_url, token, "GET",
                   "/projects/%s/repository/files/%s"
                   % (_encode_path(repo), _encode_path(file_path)),
                   params={"ref": ref}, timeout=timeout, verify_ssl=verify_ssl)

    encoded = (body or {}).get("content", "")
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitLabError("無法解讀檔案內容（%s@%s）：%s" % (file_path, ref, exc))


# --- Merge request ---------------------------------------------------------

def get_merge_requests(server_url, token, repo, state="opened",
                       created_after_days=None, target_branch=None,
                       source_branch=None, max_items=None,
                       timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出專案的 merge request。

    state 為 "opened" / "closed" / "merged" / "all"。

    created_after_days 只取最近 N 天建立的 MR。None 或**負數**表示不限 ——
    負數也接受，是因為入口腳本常把「不限」寫成 -1（參數宣告要有預設值，而
    「不限」沒有自然的數字表示）。

    回傳 GitLab 原樣的 MR 物件清單，不做欄位挑選 —— 要挑哪些欄位是呼叫端的
    決定，共用模組先砍掉欄位的話，下一個呼叫端就得回來改這裡。
    """
    params = {"state": state}

    if created_after_days is not None and created_after_days >= 0:
        # GitLab 收 ISO 8601。用 UTC 是因為伺服器與使用者未必同一時區，
        # 而這個條件只要求「最近 N 天」，不需要當地日界線的精確度。
        cutoff = time.gmtime(time.time() - created_after_days * 86400)
        params["created_after"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", cutoff)

    if target_branch:
        params["target_branch"] = target_branch
    if source_branch:
        params["source_branch"] = source_branch

    return get_paged(server_url, token,
                     "/projects/%s/merge_requests" % _encode_path(repo),
                     params=params, timeout=timeout, verify_ssl=verify_ssl,
                     max_items=max_items)


def get_merge_request(server_url, token, repo, mr_iid,
                      timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得單一 merge request。

    mr_iid 是專案內的編號（GitLab 畫面上的 !123），不是跨專案的全域 id ——
    兩者都存在且不相等，傳錯會拿到別的 MR 或 404。
    """
    return request(server_url, token, "GET",
                   "/projects/%s/merge_requests/%s"
                   % (_encode_path(repo), _encode_path(mr_iid)),
                   timeout=timeout, verify_ssl=verify_ssl)
