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

    mrs = gitlab_utils.get_all_mr(
        cfg["Gitlab_Server_URL"], cfg["Gitlab_Access_Token"],
        "group/project", created_after="2026-09-01", status=("opened",))

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
import datetime
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
    "get_repo_id",
    "list_branches",
    "get_file_content",
    "get_all_mr",
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

# GitLab 的 merge request state 只收這幾個值，而且一次只收一個。
_MR_STATES = ("opened", "closed", "merged", "locked", "all")


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


def _to_iso(value):
    """把時間值正規化成 GitLab 吃的 ISO 8601。

    收字串與 date / datetime 物件。字串原樣送出 —— 呼叫端已經自己寫好格式了，
    在這裡二次解析只會多一種解析失敗的方式。

    刻意**不收**「幾天前」這種數字：同一個參數有時是日期、有時是天數，呼叫端
    讀簽章讀不出來該傳什麼。需要那種語意請自己先換算成日期。
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    raise GitLabError("時間參數只接受 ISO 8601 字串或 date/datetime，收到 %r"
                      % (value,))


def _normalize_states(status):
    """把 status 正規化成一個 tuple。

    字串與序列都收。收字串是因為 ("opened") 在 Python 裡**不是 tuple** 而是
    字串（逗號才是關鍵，不是括號），那個寫法太容易打錯；若只當序列處理，
    它會被迭代成 'o','p','e','n','e','d' 六個狀態，而錯誤訊息會指向一個
    看起來毫無道理的地方。

    含 "all" 時直接收斂成 ("all",) —— GitLab 的 all 已經涵蓋其餘狀態，
    再多打幾趟只是拿回重複的資料。
    """
    if isinstance(status, str):
        states = (status,)
    else:
        try:
            states = tuple(status)
        except TypeError:
            raise GitLabError("status 必須是字串或字串序列，收到 %r" % (status,))

    if not states:
        raise GitLabError("status 不可為空")

    for one in states:
        if one not in _MR_STATES:
            raise GitLabError("不支援的 merge request 狀態 %r，可用的有：%s"
                              % (one, "、".join(_MR_STATES)))

    if "all" in states:
        return ("all",)
    # 去重但保留呼叫端給的次序
    seen, unique = set(), []
    for one in states:
        if one not in seen:
            seen.add(one)
            unique.append(one)
    return tuple(unique)


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


def get_repo_id(server_url, token, repo_name, timeout=DEFAULT_TIMEOUT,
                verify_ssl=True):
    """把專案的完整路徑換成數字專案 ID。

    repo_name 是**完整路徑**，例如 "group/subgroup/project" —— 不是只有專案名。
    只給名字的話得走 /projects?search=，而 search 是模糊比對：三個群組底下
    都有 tool 時會回三筆，挑第一筆是賭博，挑錯了症狀會出現在很後面。

    找不到時拋出 GitLabError（code 為 GITLAB_404），不回 None —— 回 None 的話
    呼叫端忘了檢查就會拿 None 去打下一支 API，錯誤在很遠的地方才爆開。

    多數端點其實可以直接吃編碼過的完整路徑，不需要先換 ID。需要數字 ID 的場合
    是少數（例如某些跨專案端點），以及單純想確認「這個專案存在而且我看得到」。
    """
    project = get_project(server_url, token, repo_name,
                          timeout=timeout, verify_ssl=verify_ssl)
    return (project or {}).get("id")


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

def get_all_mr(server_url, token, repo, created_after, status=("opened",),
               target_branch=None, source_branch=None, max_items=None,
               timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出專案的 merge request。

    repo 為 "group/project" 完整路徑或數字專案 ID。

    created_after 收 ISO 8601 字串或 date / datetime 物件；None 表示不限時間。

    status 收單一字串或字串序列，合法值見 _MR_STATES。GitLab 的 state 參數
    **一次只收一個值**（"opened,merged" 它不認），所以多狀態是一個狀態打一趟
    再把結果合併。狀態通常只有一兩個，這比「抓 state=all 回來自己過濾」省得多
    —— 後者要把整個專案的歷史 MR 都拉回來。

    合併後依 id 去重（呼叫端給重複狀態時不會拿到重複資料），再依建立時間新到舊
    排序 —— 不排的話輸出會是「所有 opened、接著所有 merged」，那個次序對呼叫端
    沒有意義，而且同一批資料每次跑的順序還可能不同。

    回傳 GitLab 原樣的 MR 物件清單，不挑欄位 —— 挑哪些欄位是呼叫端的決定。
    共用模組先砍的話，下一個呼叫端就得回來改這裡。一筆 MR 約 2～4 KB，入口腳本
    放進結果信封之前請自行挑選需要的欄位。
    """
    states = _normalize_states(status)

    base_params = {}
    iso = _to_iso(created_after)
    if iso:
        base_params["created_after"] = iso
    if target_branch:
        base_params["target_branch"] = target_branch
    if source_branch:
        base_params["source_branch"] = source_branch

    path = "/projects/%s/merge_requests" % _encode_path(repo)

    merged = []
    seen_ids = set()
    for one in states:
        params = dict(base_params)
        params["state"] = one

        for item in get_paged(server_url, token, path, params=params,
                              timeout=timeout, verify_ssl=verify_ssl):
            identifier = item.get("id")
            if identifier is not None and identifier in seen_ids:
                continue
            if identifier is not None:
                seen_ids.add(identifier)
            merged.append(item)

    # 新到舊。缺 created_at 的排最後，不讓一筆異常資料把整串的次序弄亂。
    merged.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    logger.debug("MR 查詢 %s 狀態 %s，共 %d 筆", repo, states, len(merged))

    if max_items is not None:
        return merged[:max_items]
    return merged


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
