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

匯入失敗時不在 import 階段爆掉（那個 try/except 在 http_utils），而是延到真正
呼叫時由 http_utils.require_requests() 拋出 GitLabError。理由：入口腳本的
`from script_utils import gitlab_utils` 發生在 `script_io.run()` 之前，那個階段
拋例外的話不會有結果信封，Qt 端只會顯示「腳本沒有回傳結果 (exit code 1)」——
使用者完全看不出是少裝了套件。延到呼叫時，錯誤就會走 script_io 的統一處理變成
一則說得清楚的 FAIL。

## 共用的底層

建立 session、逾時、重試、JSON 解析與例外基底在 http_utils，與 jira_utils 共用。
留在這裡的是 GitLab 自己的部分：認證標頭、API 根路徑、錯誤訊息怎麼挖、以及
依 X-Next-Page 標頭的分頁。
"""

import base64
import datetime
import time

from script_utils import http_utils
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
    "get_mr_info",
    "get_mr_plain_diff",
    "get_mr_diff_detail",
]


# 逾時、重試策略與連線建立都在 http_utils，與 Jira 共用一份。
DEFAULT_TIMEOUT = http_utils.DEFAULT_TIMEOUT

# GitLab 每頁上限 100。取小了只是讓同樣的資料多跑幾趟。
_PER_PAGE = 100

# merge request 的 /diffs 端點每頁上限。
#
# **不能用 _PER_PAGE 的 100。** 已知多個 GitLab 版本在這個端點收到大於 30 的 per_page
# 時直接回 500（gitlab-org/gitlab#427168、#428187）。那個失敗不會退回 /changes ——
# 退回只在 404 時發生 —— 所以它會變成一個指不出原因的「GitLab 查詢失敗」。
_DIFFS_PER_PAGE = 30

# 分頁的硬上限，防止伺服器回傳異常的 next page 時無限迴圈。
_MAX_PAGES = 1000

# GitLab 的 merge request state 只收這幾個值，而且一次只收一個。
_MR_STATES = ("opened", "closed", "merged", "locked", "all")


class GitLabError(http_utils.HttpError):
    """GitLab 呼叫失敗。

    共用模組不結束行程也不自己印訊息，一律以例外拋出，由入口腳本決定怎麼回報。

    `code` 由基底依 CODE_PREFIX 產生，形如 `GITLAB_401`；沒有 HTTP 狀態碼時
    （連線失敗、逾時、少裝套件）為 `GITLAB_ERROR`。入口腳本可以直接：

        except gitlab_utils.GitLabError as exc:
            script_io.reply_fail(str(exc), code=exc.code)
    """

    CODE_PREFIX = "GITLAB"


# --- 內部 ------------------------------------------------------------------

def _require_requests():
    http_utils.require_requests(GitLabError)


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
    """建立帶 GitLab 認證標頭的 session。

    權杖只放進標頭，絕不進 log、也不放進 URL query —— query 會被伺服器與代理
    記進存取紀錄。
    """
    if not isinstance(token, str) or not token.strip():
        raise GitLabError("GitLab 存取權杖不可為空")

    return http_utils.new_session({"PRIVATE-TOKEN": token})


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
        response = http_utils.send(session, method, url, params, json_body,
                                   timeout, verify_ssl, GitLabError)
        _check_response(response, url)
        return http_utils.parse_json(response, url, GitLabError)
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

            response = http_utils.send(session, "GET", url, query, None,
                                       timeout, verify_ssl, GitLabError)
            _check_response(response, url)

            body = http_utils.parse_json(response, url, GitLabError)
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

def get_project(server_url, token, project_id, timeout=DEFAULT_TIMEOUT,
                verify_ssl=True):
    """取得專案資訊。

    project_id 收數字專案 ID，也收 "group/project" 完整路徑 —— GitLab 兩種都認，
    路徑中的斜線由這裡編碼成 %2F。模組內所有函式的這個參數都是同一個語意。
    """
    return request(server_url, token, "GET",
                   "/projects/%s" % _encode_path(project_id),
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


def list_branches(server_url, token, project_id, search=None,
                  timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出專案的分支。search 有值時只回傳名稱含該字串的分支。"""
    params = {}
    if search:
        params["search"] = search

    return get_paged(server_url, token,
                     "/projects/%s/repository/branches" % _encode_path(project_id),
                     params=params, timeout=timeout, verify_ssl=verify_ssl)


def get_file_content(server_url, token, project_id, file_path, ref,
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
                   % (_encode_path(project_id), _encode_path(file_path)),
                   params={"ref": ref}, timeout=timeout, verify_ssl=verify_ssl)

    encoded = (body or {}).get("content", "")
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitLabError("無法解讀檔案內容（%s@%s）：%s" % (file_path, ref, exc))


# --- Merge request ---------------------------------------------------------

def get_all_mr(server_url, token, project_id, created_after, status=("opened",),
               target_branch=None, source_branch=None, max_items=None,
               timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """列出專案的 merge request。

    project_id 收數字專案 ID 或 "group/project" 完整路徑。

    created_after 收 ISO 8601 字串或 date / datetime 物件；None 表示不限時間。

    status 收單一字串或字串序列，合法值見 _MR_STATES。GitLab 的 state 參數
    **一次只收一個值**（"opened,merged" 它不認），所以多狀態是一個狀態打一趟
    再把結果合併。狀態通常只有一兩個，這比「抓 state=all 回來自己過濾」省得多
    —— 後者要把整個專案的歷史 MR 都拉回來。

    合併後依 id 去重（呼叫端給重複狀態時不會拿到重複資料），再依建立時間新到舊
    排序 —— 不排的話輸出會是「所有 opened、接著所有 merged」，那個次序對呼叫端
    沒有意義，而且同一批資料每次跑的順序還可能不同。

    max_items 會往下傳給翻頁層，取夠就停止翻頁 —— 不是先抓完再切。專案的歷史
    MR 動輒數千筆，兩者的差別是幾趟請求與幾 MB 的傳輸。

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

    path = "/projects/%s/merge_requests" % _encode_path(project_id)

    merged = []
    seen_ids = set()
    for one in states:
        params = dict(base_params)
        params["state"] = one

        # max_items 要往下傳，否則翻頁層會把整個專案的 MR 都拉回來再由這裡
        # 切掉 —— 那不只是多切幾筆，是多打好幾趟請求、多拉回幾 MB 的資料。
        #
        # 多狀態時每個狀態各自取到 max_items 為止：合併後要依建立時間取最新的
        # max_items 筆，而那些筆數必定落在「各狀態各自最新的 max_items 筆」之內。
        for item in get_paged(server_url, token, path, params=params,
                              timeout=timeout, verify_ssl=verify_ssl,
                              max_items=max_items):
            identifier = item.get("id")
            if identifier is not None and identifier in seen_ids:
                continue
            if identifier is not None:
                seen_ids.add(identifier)
            merged.append(item)

    # 新到舊。缺 created_at 的排最後，不讓一筆異常資料把整串的次序弄亂。
    merged.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    logger.debug("MR 查詢 %s 狀態 %s，共 %d 筆", project_id, states, len(merged))

    if max_items is not None:
        return merged[:max_items]
    return merged


def get_mr_info(server_url, token, project_id, mr_iid,
                timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得單一 merge request 的完整資訊。

    ⚠️ mr_iid 是**專案內編號**（畫面上的 !7），不是全實例唯一的 id。GitLab 的
    MR 物件同時有這兩個欄位：

        mr["id"]    12345   全實例唯一
        mr["iid"]   7       專案內編號  <- 端點吃的是這個

    傳錯的後果不只是 404：同一個專案裡剛好有一支 MR 的 iid 等於你傳的那個 id
    時，你會拿到**另一支 MR 的資料**，而且不會有任何錯誤。參數因此命名為
    mr_iid 而不是 mr_id —— 名字對了，呼叫端才不會順手把 m["id"] 填進來。

    回傳 GitLab 原樣的 MR 物件。
    """
    return request(server_url, token, "GET",
                   "/projects/%s/merge_requests/%s"
                   % (_encode_path(project_id), _encode_path(mr_iid)),
                   timeout=timeout, verify_ssl=verify_ssl)


def _render_file_diff(entry):
    """把 GitLab 的單檔 diff 物件還原成 git 風格的區段。

    GitLab 的 `diff` 欄位只有 `@@` 起頭的內容，沒有檔頭三行，因此這裡補上
    `diff --git` / `---` / `+++`。新增與刪除的檔案要指向 /dev/null，改名要補
    rename 兩行 —— 少了這些，輸出雖然看得懂，但餵給任何吃 unified diff 的工具
    都會在那幾個情況失敗。
    """
    old_path = entry.get("old_path") or entry.get("new_path") or ""
    new_path = entry.get("new_path") or old_path

    lines = ["diff --git a/%s b/%s" % (old_path, new_path)]

    if entry.get("new_file"):
        lines.append("new file mode %s" % (entry.get("b_mode") or "100644"))
    elif entry.get("deleted_file"):
        lines.append("deleted file mode %s" % (entry.get("a_mode") or "100644"))
    elif entry.get("renamed_file"):
        lines.append("rename from %s" % old_path)
        lines.append("rename to %s" % new_path)

    body = entry.get("diff") or ""

    # 二進位檔沒有 @@ 區段，GitLab 給的是一句說明（或空字串）。那種情況補
    # --- / +++ 只會產生一份不合法的 diff，直接放說明本身。
    if body.startswith("@@"):
        lines.append("--- %s" % ("/dev/null" if entry.get("new_file")
                                 else "a/%s" % old_path))
        lines.append("+++ %s" % ("/dev/null" if entry.get("deleted_file")
                                 else "b/%s" % new_path))

    text = "\n".join(lines) + "\n"
    if body:
        text += body if body.endswith("\n") else body + "\n"
    return text


def _entry_path(entry):
    """一筆 diff 項目對應的檔案路徑。"""
    return entry.get("new_path") or entry.get("old_path") or ""


def _changes_entries(server_url, token, base, timeout, verify_ssl):
    """走 /changes 取得項目清單，回傳 (entries, overflow)。

    overflow 是 GitLab 在「大小限制影響了這次結果」時給的旗標 —— 先前沒有讀它，於是
    一份被截掉一半的 diff 與一份完整的 diff 在呼叫端看起來完全一樣。
    """
    body = request(server_url, token, "GET", base + "/changes",
                   params={"access_raw_diffs": "true"},
                   timeout=timeout, verify_ssl=verify_ssl)
    body = body or {}
    return (body.get("changes") or []), bool(body.get("overflow"))


def _raw_entries(server_url, token, base, entries, overflow, timeout, verify_ssl):
    """以 access_raw_diffs 重取，**內容較多的那一份勝出**。

    不無條件採用重取的結果：那條路是舊端點，在某些版本上它自己也回空的
    （gitlab-org/gitlab#300385）。比較「有內容的檔案數」再決定，所以重取失敗時至少
    不會比原本更糟。

    重取本身失敗（端點不在、權限不足）不讓整件事失敗 —— 原本那一份仍然可用，而且
    呼叫端會從空的檔案數看見問題。
    """
    def with_content(items):
        return sum(1 for one in items if (one.get("diff") or ""))

    try:
        raw, raw_overflow = _changes_entries(server_url, token, base,
                                             timeout, verify_ssl)
    except GitLabError as exc:
        logger.warn("以 access_raw_diffs 重取失敗，沿用原本的結果：%s", exc)
        return entries, overflow

    if with_content(raw) > with_content(entries):
        logger.info("access_raw_diffs 取回較完整的內容（%d → %d 個檔案有內容）",
                    with_content(entries), with_content(raw))
        return raw, bool(raw_overflow)

    logger.warn("access_raw_diffs 沒有取回更多內容（仍有 %d 個檔案是空的）—— "
                "多半是伺服器端的 diff 大小限制，需由管理者調整",
                len(entries) - with_content(entries))
    return entries, overflow or bool(raw_overflow)


def get_mr_diff_detail(server_url, token, project_id, mr_iid, max_bytes=None,
                       timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得 merge request 的 unified diff，**連同取得過程中知道的事實**。

    回傳一個 dict：

        text          組好的 unified diff（截斷時含結尾那行說明）
        files         完整收進 text 的檔案路徑，依出現順序
        dropped_files 因為截斷而沒有完整收進去的檔案路徑
        file_count    這支 merge request 共有幾個檔案變更（截斷前）
        empty_files   差異內容是空的那些檔案路徑（files 的子集合）
        truncated     是否因為超過 max_bytes 而截斷
        bytes_total   截斷前的位元組數
        bytes_sent    text 中實際的差異位元組數（不含結尾那行說明）
        overflow      GitLab 表示大小限制影響了這次結果
        collapsed_files / too_large_files
                      GitLab 明說被收合／過大的檔案（18.4 以後才有這兩個欄位）

    **為什麼不只回文字**：截斷這件事原本只留在 text 的結尾與一筆警告裡，而那兩個地方
    呼叫端都無法據以判斷「少了幾個檔案」。少了幾個是呼叫端唯一真正想知道的 —— 一份
    只涵蓋 21/90 個檔案的分析，與一份完整的分析，在文字上看起來完全一樣。

    `files` 只收**完整**放得下的檔案。截斷是對整份差異做的一刀，切點可能落在某個檔案
    中間；把那個被切一半的檔案算成「有送到」會讓呼叫端少算一筆缺口，而那一筆正指向
    「上限要調」。

    `empty_files` 的成因有三種（二進位檔、只有模式變更、來源自己的大小限制），在 API
    回來的資料上都是一個空的 diff 欄位，這裡不猜是哪一種 —— 只如實說「這個檔案沒有
    內容」。要分開得多打幾支 API，那是另一件事。

    取得差異的方式見 get_mr_plain_diff。
    """
    if not isinstance(mr_iid, (str, int)) or str(mr_iid).strip() == "":
        raise GitLabError("merge request iid 不可為空")

    base = "/projects/%s/merge_requests/%s" % (_encode_path(project_id),
                                               _encode_path(mr_iid))

    overflow = False

    try:
        entries = get_paged(server_url, token, base + "/diffs",
                            params={"per_page": _DIFFS_PER_PAGE},
                            timeout=timeout, verify_ssl=verify_ssl)
    except GitLabError as exc:
        if exc.status_code != 404:
            raise
        # 舊版沒有 /diffs。/changes 回的是物件，清單在 changes 欄位底下。
        logger.debug("/diffs 不存在，改試 /changes：%s", base)
        entries, overflow = _changes_entries(server_url, token, base,
                                             timeout, verify_ssl)

    if not isinstance(entries, list):
        raise GitLabError("diff 端點回傳的不是清單：%s" % base)

    # **被收合的檔案要再抓一次。**
    #
    # GitLab 的 diff 大小限制比直覺低得多：patch 只要到門檻的 10%（預設 200 KB 的
    # 10%，約 20 KB）就會被「收合」，而收合的檔案在 API 回來的 diff 欄位是**空字串**。
    # 網頁上看得到（點開才載入），API 拿到的卻只有一行檔頭 —— 於是 prompt 裡只剩
    # `diff --git a/… b/…`，而每一步都回報成功。
    #
    # /diffs 沒有任何參數可以繞過它（它只吃 page / per_page / unidiff）。能繞過的是舊的
    # /changes 加上 access_raw_diffs=true —— 那條路直接向 Gitaly 取，不受資料庫端的大小
    # 限制。較慢也較耗資源，所以**只在真的有空的時候**才走。
    if any(not (one.get("diff") or "") for one in entries):
        logger.warn("MR %s 有檔案的差異內容是空的（多半是被 GitLab 的大小限制收合），"
                    "改以 access_raw_diffs 重取", mr_iid)
        entries, overflow = _raw_entries(server_url, token, base, entries,
                                         overflow, timeout, verify_ssl)

    collapsed_files = [_entry_path(one) for one in entries if one.get("collapsed")]
    too_large_files = [_entry_path(one) for one in entries if one.get("too_large")]
    if collapsed_files or too_large_files:
        # collapsed / too_large 是 GitLab 18.4 才有的欄位；有就直接說，沒有就只能靠
        # 「內容是空的」間接判斷。
        logger.warn("MR %s：GitLab 標示 %d 個檔案被收合、%d 個過大",
                    mr_iid, len(collapsed_files), len(too_large_files))

    chunks = [_render_file_diff(one).encode("utf-8") for one in entries]
    raw = b"".join(chunks)
    bytes_total = len(raw)
    logger.debug("MR %s 的 diff 共 %d 個檔案、%d bytes",
                 mr_iid, len(entries), len(raw))

    # 逐檔累加，決定切點之前有幾個檔案**完整**放得下。這與下面那一刀是同一個切點：
    # 兩邊各算一次就會有兩份規則，而漂移的症狀是報告說送出了某個檔案、模型卻沒看到它。
    files = []
    dropped_files = []
    empty_files = []
    used = 0
    full = True
    for entry, chunk in zip(entries, chunks):
        path = entry.get("new_path") or entry.get("old_path") or ""
        if full and max_bytes is not None and used + len(chunk) > max_bytes:
            full = False
        if not full:
            dropped_files.append(path)
            continue
        used += len(chunk)
        files.append(path)
        if not (entry.get("diff") or ""):
            empty_files.append(path)

    truncated_note = ""
    truncated = max_bytes is not None and bytes_total > max_bytes
    if truncated:
        truncated_note = ("\n（已截斷：只取前 %d bytes，原始大小 %d bytes；"
                          "完整收進的檔案 %d / %d）\n"
                          % (max_bytes, bytes_total, len(files), len(entries)))
        logger.warn("MR %s 的 diff 有 %d bytes，截斷為 %d bytes，"
                    "完整收進 %d / %d 個檔案",
                    mr_iid, bytes_total, max_bytes, len(files), len(entries))
        raw = raw[:max_bytes]

    # 截斷可能切在多位元組字元中間，errors="replace" 讓它變成替代字元而不是例外。
    return {
        "text": raw.decode("utf-8", errors="replace") + truncated_note,
        "files": files,
        "dropped_files": dropped_files,
        "file_count": len(entries),
        "empty_files": empty_files,
        "truncated": truncated,
        "bytes_total": bytes_total,
        "bytes_sent": len(raw),
        "overflow": overflow,
        "collapsed_files": collapsed_files,
        "too_large_files": too_large_files,
    }


def get_mr_plain_diff(server_url, token, project_id, mr_iid, max_bytes=None,
                      timeout=DEFAULT_TIMEOUT, verify_ssl=True):
    """取得 merge request 的 unified diff 純文字。

    走 /api/v4 取回各檔案的 diff，再組成一份 git 風格的 unified diff。

    **為什麼不抓網頁路由的 `.diff`**：那條路由（`/<group>/<project>/-/
    merge_requests/<iid>.diff`）回來的是原汁原味的 diff，不需要重組，本函式
    最初就是那樣寫的。但它**不接受 PRIVATE-TOKEN 標頭認證** —— GitLab 只在
    /api/v4 底下認那個標頭，網頁路由把請求當成匿名訪客，而私有專案對匿名訪客
    一律回 404（不是 403，那是為了不洩漏「這個專案存在」）。症狀是「token 明明
    可以用，卻說找不到」，實測後改走這條。

    代價是 `diff --git` / `---` / `+++` 這幾行由本函式重組，不是 GitLab 給的。
    新增、刪除、改名與二進位檔都有對應處理（見 _render_file_diff），但與 git
    自己產生的輸出仍可能有細微差異。

    端點先試 `/diffs`（較新），404 時退回 `/changes`（較舊、已標記為 deprecated
    但仍可用）—— 兩者在不同版本的 GitLab 上各自存在，寫死任何一個都會在某些
    伺服器上失敗。

    max_bytes 限制回傳大小，None 表示不限。改了幾十個檔案的 MR，diff 輕易就是
    數百 KB 到數 MB，而它要經 stdout 進結果信封再交給 Qt。截斷時會在結尾附一行
    說明 —— 靜默截斷的話呼叫端會把半截 diff 當成完整的。

    **只要文字就用這一支。** 想知道少了哪幾個檔案的，用 get_mr_diff_detail ——
    那些事實在這裡會被丟掉。
    """
    return get_mr_diff_detail(server_url, token, project_id, mr_iid,
                              max_bytes=max_bytes, timeout=timeout,
                              verify_ssl=verify_ssl)["text"]
