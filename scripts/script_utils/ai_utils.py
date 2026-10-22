#!/usr/bin/env python3
"""向 AI 服務提問的共用模組。

使用者是 device 的 `summary.py`：**它組 prompt，這裡負責問與等。** prompt 不進這個
模組 —— 那正是每條產品線要自己掌握的東西，收進共用模組會把 device 機制的意義抵消掉。

    from script_utils import ai_utils

    provider, url, share_code = ai_utils.split_connection(connection)
    text = ai_utils.ask(url, prompt, share_code=share_code)        # 原始回覆
    data = ai_utils.ask_json(url, prompt, share_code=share_code)   # 解析過的 JSON
    model = ai_utils.lookup_model(url, share_code, api_key)        # 出處用的模型名稱

**這個模組是為特定一家地端服務寫的，不是通用的多供應商客戶端。** 請求形狀集中在
_build_payload()，回應的取值集中在 _extract_reply()，要換服務改那兩支即可；重試、
退避、逾時與錯誤分類都與封包形狀無關，不必跟著動。

**為什麼不用 curl 子行程**：金鑰與 prompt 不能上命令列（Windows 的命令列上限是 32767
字元，一份 diff 輕易就超過），而 curl 的失敗要靠解析 exit code 分類。走 requests 的話
這些 http_utils 已經處理好了。

**為什麼不直接用 http_utils.send()**：AI 的呼叫是分鐘級而不是秒級，重試次數、退避長度
與逾時都要另一組預設；而且 429 常常附 Retry-After，等它指定的秒數比指數退避準得多。
共用的部分（session、requests 檢查、例外基底）仍然沿用。
"""

import json
import re
import time

from script_utils import http_utils
from script_utils import logger

__all__ = ["AiError", "ask", "ask_json", "as_json", "strip_fence",
           "split_connection", "mask_connection", "ROLE_USER",
           "DEFAULT_TIMEOUT", "MAX_RETRIES",
           "API_ROOT", "MODEL_LIST_PATH", "MODEL_LOOKUP_TIMEOUT",
           "model_list_url", "fetch_model_list", "find_model", "lookup_model"]


# AI 的呼叫是分鐘級的。30 秒（http_utils 的預設）會把正常的長回答當成逾時，
# 然後重試三次 —— 結果是等更久，而且每一次都付錢。
DEFAULT_TIMEOUT = 120

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

# 單次退避的上限。429 的 Retry-After 偶爾會給出很大的值，照單全收會讓那個固定尺寸的
# 對話框枯坐十分鐘而且看不出在等什麼。超過就放棄重試，讓使用者知道服務正在限流。
MAX_BACKOFF_SECONDS = 30.0

# 重試有意義的狀態碼。408 是請求逾時、429 是限流、5xx 是伺服器端的暫時狀況。
#
# 其餘的 4xx 一律不重試：401 是憑證錯、404 是端點打錯、413 是 prompt 太長、400 多半是
# 封包形狀不對。這些重試三次結果完全一樣，只是把同一個錯誤等三倍時間。
RETRY_STATUS = (408, 429, 500, 502, 503, 504)

# 回覆不符預期時，追加在 prompt 尾端再問一次的提示。
REASK_HINT = "\n\n只回覆結果本身，不要任何開場白、說明或註解。"

# previousMessage 裡的 role 編號。
#
# ⚠️ 只確定 0 是這個服務接受的值（來自實際可用的 payload 範例），還不知道它代表
# 「使用者」還是「系統」，也不知道其他編號有哪些。查清楚之後把常數補齊，呼叫端就能
# 用名字而不是數字 —— 一個裸的 0 散在各處，改的時候找不完。
ROLE_USER = 0


class AiError(http_utils.HttpError):
    """AI 呼叫失敗。

    沿用 http_utils 的基底，因此 `code` 會是 AI_401、AI_429 這種形狀，入口腳本
    可以直接依服務分流。

    `retryable` 由**拋出的那一方**決定，不由重試那一段從狀態碼反推。理由是有一整類
    錯誤根本沒有狀態碼卻要分成兩邊：連線中斷該重試，而「回應的欄位跟預期不一樣」
    重試三次結果完全一樣 —— 那是封包形狀猜錯，不是網路抖動。

    `retry_after` 是伺服器在 429 時指定的等待秒數，沒有就是 None。
    """

    CODE_PREFIX = "AI"

    retryable = False
    retry_after = None


# ---------------------------------------------------------------------------
# 連線字串：provider、位址與 shareCode
# ---------------------------------------------------------------------------

# provider 前綴：開頭一段只含英數字與 . _ - 的字，後面緊接著冒號與 http(s)://。
#
# **只有「冒號後面緊接著通訊協定」才算前綴。** 位址本身以通訊協定開頭，裡面就有一個
# 冒號；不看後面那一段的話，`https://...` 會被當成 provider 是 `https`。
_PROVIDER_RE = re.compile(r"^([A-Za-z0-9._-]+):(?=https?://)")


def split_connection(connection):
    """把連線字串拆成 (provider, url, share_code)。

    連線字串是 provider、位址與 shareCode 以冒號相接：

        openai:https://ai.example.com/v1/chat:ABC123
        →  ("openai", "https://ai.example.com/v1/chat", "ABC123")

    provider 是選填的。開頭那一段不符合前綴的規則（見 _PROVIDER_RE）時 provider 是空
    字串，整串都當成位址與 shareCode 拆 —— 照樣能問 AI，只是出處少了 provider。

    **問 AI、查模型、列出模型都用這一支拆。** 同一串字在兩個地方各拆一次，規則遲早
    分岔，而分岔的症狀是「分析成功、模型查不到」或反過來，兩者都不會指出原因。

    找不到 shareCode 時 share_code 是空字串，由呼叫端決定那是不是錯誤。
    """
    text = (connection or "").strip()
    provider = ""
    match = _PROVIDER_RE.match(text)
    if match:
        provider = match.group(1)
        text = text[match.end():]

    url, share_code = _split_share_code(text)

    # **只印長度，不印值。** 這個服務沒有認證標頭，shareCode 本身就是憑證，而
    # Debug_Mode 開啟時這一行會進 debug console，崩潰時還會被寫進 crash.log。
    # 端點印得出來是因為它是分隔冒號**之前**那一段，不含 shareCode。
    logger.debug("連線字串拆解：provider %s，端點 %s，shareCode %d 字元",
                 provider or "(無)", url or "(空)", len(share_code))

    return provider, url, share_code


def mask_connection(connection):
    """把連線字串裡的 shareCode 遮掉，provider 與端點原樣留著。

        openai:https://host/api/external/v1/chat:ABC123
        →  openai:https://host/api/external/v1/chat:***

    給信封紀錄用（script_io.arg(mask=...)）。**只遮第三段**：前兩段是「送去哪一個供應者
    的哪一個端點」，那正是看紀錄時最想知道的事；整串遮掉等於把有用的部分一起丟掉。

    沒有 shareCode 時原樣回傳 —— 沒有東西可遮，而硬加一個 `:***` 會讓讀的人以為有。

    遮罩字串與 script_io 的 MASKED 刻意**各自宣告**：這一支不 import script_io（那是 Qt
    那條呼叫管線專用的模組，script_utils 底下不該依賴它）。
    """
    provider, url, share_code = split_connection(connection)

    if not share_code:
        return (connection or "").strip()

    head = "%s:%s" % (provider, url) if provider else url
    return "%s:***" % head


def _split_share_code(address):
    """把 `位址:shareCode` 拆成 (url, share_code)。

    **不能直接用 split(":")，也不能無條件用 rsplit**：一個位址裡至少有一個冒號
    （`https:`），而且可能還有連接埠（`host:8080`）。切錯的下場是把整個路徑當成
    shareCode 送出去，而伺服器只會回一個看不出原因的 400。

    規則是「**path 裡的第一個**冒號才算分隔，其後整段都是 shareCode」：

        https://host:8080/v1/chat          path 裡沒有冒號 → 沒有 shareCode
        https://host:8080/v1/chat:ABC      → ("https://host:8080/v1/chat", "ABC")
        https://host:8080/v1/chat:ABC/123  → ("https://host:8080/v1/chat", "ABC/123")
        https://host/v1/chat:ABC:DEF       → (".../chat", "ABC:DEF")

    先把 path 的起點找出來，scheme 與 authority（`host:8080`）的冒號後面就不必再防，
    而 shareCode 被當成**不透明的字串**：裡面有斜線或冒號都照樣整段取出。

    這裡原本的規則是「最後一個斜線之後的冒號才算分隔」，它擋得住 scheme 與連接埠，
    但同時擋死了含斜線的 shareCode —— 那個斜線會變成「最後一個斜線」，真正的分隔冒號
    於是落在它前面而被當成連接埠，結果是明明填了卻回報「沒帶 shareCode」。shareCode
    是服務那端發的不透明識別碼，本專案無權規定它不能含斜線。

    代價寫明白：改成這條規則之後，**端點的 path 自己不能含冒號**（例如
    `/v1/models/foo:generate` 這種形狀會被切錯）。path 是部署者自己填的、而且固定不變，
    shareCode 則是人家發的、換了就得照抄 —— 兩者之中該讓哪一個受限很清楚。
    """
    url = (address or "").strip()
    if not url:
        return "", ""

    # 只在 path 裡找分隔冒號。scheme 的 "://" 與 authority 的連接埠都在 path 之前，
    # 把起點定出來就一次排除了，不必再逐種情況判斷。
    scheme_end = url.find("://")
    authority_start = scheme_end + 3 if scheme_end >= 0 else 0
    path_start = url.find("/", authority_start)

    if path_start < 0:
        # 沒有 path 就沒有能放 shareCode 的地方，位址裡的冒號只會是 scheme 或連接埠。
        return url, ""

    sep = url.find(":", path_start)
    if sep < 0:
        return url, ""

    return url[:sep], url[sep + 1:]


# ---------------------------------------------------------------------------
# 封包形狀 —— 換服務只要動這一段
# ---------------------------------------------------------------------------

def _build_payload(prompt, share_code, history, file_ids):
    """組出請求的 body。

        {
          "shareCode": "...",
          "prompt": "...",
          "previousMessage": [{"role": 0, "message": ""}],
          "files": [{"fileID": 1}]
        }

    history 是 [(role, message), ...] 或 [{"role": ..., "message": ...}, ...]，
    兩種都收 —— 呼叫端用 tuple 比較省事，而從 JSON 讀回來的會是 dict。

    **沒有 history 時送一筆 message 為空字串的紀錄**，而不是空陣列：那是實際可用的
    payload 範例裡的寫法，也就是我們唯一確定這個服務會接受的形狀。空陣列或省略這個
    鍵都沒驗證過，不拿正式流程去賭。

    files 預設是空陣列。範例裡的 `{"fileID": 1}` 是示意用的 —— 那個編號指向某個真實
    檔案，預設送出去等於替呼叫端引用了一份它沒要求的東西。
    """
    return {
        "shareCode": share_code,
        "prompt": prompt,
        "previousMessage": _history_payload(history),
        "files": [{"fileID": one} for one in (file_ids or [])],
    }


def _history_payload(history):
    """把 history 正規化成服務要的形狀。"""
    if not history:
        return [{"role": ROLE_USER, "message": ""}]

    items = []
    for entry in history:
        if isinstance(entry, dict):
            items.append({"role": entry.get("role", ROLE_USER),
                          "message": entry.get("message", "")})
        else:
            role, message = entry
            items.append({"role": role, "message": message})
    return items


# 業務層成功的 status 值。HTTP 200 不代表這次問成功 —— 服務會以 200 回一個
# status 不是 success 的結果，把它當成回覆就會拿到 None 往下走。
STATUS_SUCCESS = "success"


def _extract_reply(body, url):
    """從回應裡取出模型講的那段話。

    回應的形狀：

        {"status": "success", "statusCode": ..., "content": <AI 回的 JSON>}

    content 可能是字串，也可能已經被服務解析成物件。**兩種都收，一律回字串** ——
    這個函式對外的約定是「回一段文字」，下游統一用 as_json() 解析。在這裡就分岔的話，
    呼叫端每次都要先問「這次拿到的是字串還是 dict」。

    status 不是 success 時拋錯而不是回內容：那是服務明確說這次失敗，而 content 在
    那種情況下通常是錯誤說明，硬拿去當分析會產出一份看起來正常的報告。
    """
    if not isinstance(body, dict):
        raise AiError("AI 回應不是物件（收到 %s）" % type(body).__name__, url=url)

    status = body.get("status")
    code = body.get("statusCode")

    if status is not None and str(status).strip().lower() != STATUS_SUCCESS:
        error = AiError(
            "AI 服務回報失敗：status=%s statusCode=%s%s"
            % (status, code, _content_hint(body.get("content"))),
            url=url)
        # statusCode 若是 HTTP 風格的碼，沿用同一組重試判斷；不是的話不重試 ——
        # 猜一個不認得的錯誤碼值不值得重試，只會把失敗拖長三倍。
        error.retryable = isinstance(code, int) and code in RETRY_STATUS
        raise error

    content = body.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, (dict, list)):
        # 服務已經幫忙解析過了。轉回字串讓下游只有一條路徑；ensure_ascii=False 是
        # 為了讓解析失敗時的錯誤訊息印得出中文，而不是一串 \\uXXXX。
        return json.dumps(content, ensure_ascii=False)

    if content is None:
        raise AiError(
            "AI 回應沒有 content 欄位。回應的頂層欄位：%s"
            % ("、".join(sorted(body.keys())) or "(沒有欄位)"),
            url=url)

    raise AiError("AI 回應的 content 不是文字也不是物件（收到 %s）"
                  % type(content).__name__, url=url)


def _content_hint(content):
    """失敗時把 content 的開頭附在訊息後面 —— 服務的錯誤說明通常在那裡。"""
    if not content:
        return ""
    text = content if isinstance(content, str) else json.dumps(
        content, ensure_ascii=False)
    text = text.strip().replace("\n", " ")
    return "：%s" % (text[:200] + "…" if len(text) > 200 else text)


def _headers(api_key):
    """請求標頭。

    這個服務以 X-Api-Key 認證，不是 Authorization: Bearer。金鑰空著也照送 —— 服務端
    會回 401，而那比在這裡自己判斷「空金鑰一定不行」準確：能不能免金鑰是它的規則。

    金鑰只進標頭，絕不進 URL query：query 會被伺服器與代理記進存取紀錄。
    """
    return {"Content-Type": "application/json",
            "X-Api-Key": api_key or ""}


# ---------------------------------------------------------------------------
# 以下與封包形狀無關
# ---------------------------------------------------------------------------

def _retry_after(response):
    """讀 Retry-After 標頭，回傳秒數；沒有或看不懂時回 None。

    限流時伺服器自己說要等多久，那個值比指數退避準得多。規格允許秒數或 HTTP 日期，
    這裡只認秒數 —— 日期格式在實務上幾乎沒有 AI 服務在用，為它引進時區解析不划算。
    """
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.debug("看不懂的 Retry-After：%r", raw)
        return None


def _describe(response, url):
    """把失敗的回應轉成一個訊息講得清楚的 AiError。

    訊息按「使用者的下一步」分開寫：換憑證、改設定檔、縮短 prompt、稍後再試，
    這四件事完全不一樣。
    """
    status = response.status_code
    body = (response.text or "").strip()
    # 伺服器回的錯誤訊息通常很有用，但可能很長（有些會把整個 prompt 回貼）。
    if len(body) > 500:
        body = body[:500] + "…"

    if status in (401, 403):
        error = AiError(
            "AI 服務拒絕了這次請求，請檢查 Api_Key 與 Api_URL 尾端的 shareCode",
            status_code=status, url=url)
    elif status == 404:
        error = AiError(
            "AI 端點不存在（404），請檢查設定檔的 Api_URL",
            status_code=status, url=url)
    elif status == 413:
        error = AiError(
            "prompt 太長，AI 服務拒收（413）",
            status_code=status, url=url)
    elif status == 429:
        error = AiError(
            "AI 服務限流中（429），稍後再試",
            status_code=status, url=url)
    else:
        error = AiError("AI 服務回應 %d：%s" % (status, body or "(沒有內容)"),
                        status_code=status, url=url)

    # 伺服器自己說要等多久的話，把秒數帶在例外上 —— 重試那一段據此決定退避長度，
    # 而它拿不到 response（那是這一層的東西）。
    error.retry_after = _retry_after(response)
    error.retryable = status in RETRY_STATUS
    return error


def _is_ssl_error(exc):
    """這個連線層例外是不是憑證問題。

    **憑證問題不重試。** 一張不被信任的憑證不會在兩秒後變得被信任 —— 重試三次只是把
    一個註定的失敗等三倍，而使用者盯著的是一個沒有動靜的對話框。

    以類別名稱判斷而不是 isinstance：這個模組刻意不 import requests（見 http_utils 的
    require_requests），為了一個分類就把它變成硬相依不划算。requests 的 SSLError 繼承
    自 ConnectionError，所以要走整條繼承鏈看，不能只看最外層那個名字。
    """
    for klass in type(exc).__mro__:
        if "SSL" in klass.__name__ or "Certificate" in klass.__name__:
            return True
    return False


def _call_once(session, url, payload, timeout, verify_ssl):
    """送出一次請求並取出回覆文字。失敗時拋 AiError。"""
    try:
        response = session.post(url, json=payload, timeout=timeout,
                                verify=verify_ssl)
    except Exception as exc:                        # noqa: BLE001
        # requests 的連線層例外。這一層不 import requests，所以以基底型別接。
        # 逾時與斷線在分鐘級的呼叫上很常見，值得重試 —— 但憑證問題不是（見下）。
        if _is_ssl_error(exc):
            raise AiError(
                "AI 服務的 TLS 憑證驗證失敗：%s" % exc, url=url)

        error = AiError("無法連線至 AI 服務：%s" % exc, url=url)
        error.retryable = True
        raise error

    if response.status_code >= 400:
        raise _describe(response, url)

    try:
        body = response.json()
    except ValueError:
        # 這個服務一律回 JSON，所以不是 JSON 就是出事了 —— 截斷的回應，或代理插進來
        # 的 HTML 錯誤頁。兩者都可能是暫時的，值得重試；訊息帶一小段實際內容，否則
        # 「不是合法的 JSON」看不出到底收到什麼。
        head = (response.text or "").strip()[:200]
        error = AiError(
            "AI 回應不是合法的 JSON（HTTP %d）：%s"
            % (response.status_code, head or "(沒有內容)"),
            status_code=response.status_code, url=url)
        error.retryable = True
        raise error

    return _extract_reply(body, url)


def _sleep(seconds, attempt, why, on_retry):
    """退避並通知呼叫端。

    on_retry 是回呼而不是直接呼叫 script_io.progress()：script_utils 底下沒有任何
    模組 import script_io，破例會讓這些模組不能獨立測。入口腳本傳一個會回報進度的
    函式進來即可，使用者才不會對著一個兩分鐘沒動靜的對話框。
    """
    logger.warn("AI 呼叫失敗（%s），%.1f 秒後重試（第 %d 次）", why, seconds, attempt)
    _notify(on_retry, attempt, why)
    time.sleep(seconds)


def _notify(on_retry, attempt, why):
    """呼叫進度回呼。它自己壞掉不該讓整次分析失敗。"""
    if not on_retry:
        return
    try:
        on_retry(attempt, why)
    except Exception:                               # noqa: BLE001
        logger.debug("on_retry 回呼失敗，忽略")


def ask(url, prompt, share_code="", history=None, file_ids=None, api_key="",
        timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES, on_retry=None,
        verify_ssl=True, parse=None, reask=0, reask_hint=REASK_HINT):
    """問一次 AI，回傳它講的那段話。

    `url` 與 `share_code` 是**已經拆好的**兩段（見 split_connection）。這裡不再拆 ——
    拆解只有一份規則，由呼叫端拆一次、問 AI 與查模型共用同一組結果。

    參數攤開而不是收一個 inputs 字典 —— 與 gitlab_utils、jira_utils 同一個慣例，
    這個模組因此不認得任何一個功能的參數形狀。

    **沒有 model 參數**：這個服務的 payload 裡沒有模型欄位，模型是由 shareCode 那一端
    決定的。報告出處要的模型名稱另外向服務查（見 lookup_model）。

    兩種重試，界線不同：

      **連線層**（逾時、斷線、429、5xx）重試 `retries` 次，指數退避，429 優先
      照 Retry-After 指定的秒數等。

      **內容層**（`parse` 丟出 ValueError）重問 `reask` 次，第二次起在 prompt 尾端
      追加 `reask_hint`。模型偶爾會在答案前面加一句「好的，以下是分析：」，重問一次
      的成功率很高 —— 但它要錢也要時間，所以預設是 0，由呼叫端明確開啟。

    `parse` 是轉換而不是檢查：拿到原始文字、回傳呼叫端要的東西，格式不對就丟
    ValueError。JSON 只是它的一個特例（見 ask_json），自製格式寫一支自己的 parse
    傳進來即可，兩種格式共用同一套重試。

    **prompt 與 shareCode 的內容都不進 log。** prompt 裡有整份 diff，印出來會把 log
    撐爆，也把原始碼落到磁碟上；shareCode 是這個服務唯一的憑證。拆解那一支會以
    DEBUG 記下**長度**（見 split_connection），因為「冒號切在哪裡」缺了就無從診斷 ——
    長度不足以還原憑證。
    """
    http_utils.require_requests(AiError)

    url = (url or "").strip()

    if not url:
        raise AiError("未指定 AI 端點（設定檔的 Api_URL 是空的）")

    if not share_code:
        # 這是設定錯誤而不是服務問題，訊息要直接講出正確的寫法 —— 否則使用者只會
        # 看到伺服器回的 400，完全猜不到是少了尾端那一段。
        raise AiError(
            "Api_URL 沒有帶 shareCode",
            url=url)

    session = http_utils.new_session(_headers(api_key))
    logger.info("送交 AI：prompt=%d 字元 timeout=%ds files=%d",
                len(prompt or ""), timeout, len(file_ids or []))

    # 內容層的迴圈在外：重問是換一份 prompt 重新走完整套連線層重試。
    for round_no in range(reask + 1):
        text = _ask_raw(session, url, share_code,
                        prompt if round_no == 0 else prompt + reask_hint,
                        history, file_ids, timeout, retries, on_retry,
                        verify_ssl)

        if parse is None:
            return text

        try:
            return parse(text)
        except ValueError as exc:
            if round_no >= reask:
                raise AiError("AI 的回覆不是預期的格式：%s" % exc, url=url)
            logger.warn("AI 回覆格式不符（%s），重問一次", exc)
            _notify(on_retry, round_no + 1, "回覆格式不符")


def _ask_raw(session, url, share_code, prompt, history, file_ids, timeout,
             retries, on_retry, verify_ssl):
    """連線層：送出、失敗就退避重試，回傳原始回覆文字。"""
    payload = _build_payload(prompt, share_code, history, file_ids)
    last = None

    for attempt in range(retries + 1):
        try:
            return _call_once(session, url, payload, timeout, verify_ssl)
        except AiError as exc:
            last = exc

            # 不值得重試的錯誤立刻拋 —— 憑證錯重試三次還是憑證錯，封包形狀猜錯
            # 也一樣。判斷由拋出的那一方給（見 AiError.retryable）。
            if not exc.retryable:
                raise
            if attempt >= retries:
                break

            # 伺服器指定了等待秒數就照它的，否則指數退避 —— 限流時它自己說的
            # 比我們猜的準得多。
            wait = exc.retry_after
            if wait is None:
                wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
            elif wait > MAX_BACKOFF_SECONDS:
                # 伺服器要求的等待比我們願意讓使用者枯坐的還長，就別假裝在重試 ——
                # 一個卡五分鐘、最後還是失敗的對話框比立刻說明白糟得多。
                raise AiError(
                    "AI 服務要求等待 %.0f 秒後再試，超過上限 %.0f 秒"
                    % (wait, MAX_BACKOFF_SECONDS),
                    status_code=exc.status_code, url=url)

            _sleep(wait, attempt + 1, str(exc), on_retry)

    raise last


# ---------------------------------------------------------------------------
# JSON 回覆
# ---------------------------------------------------------------------------

# 模型很愛把 JSON 包在 markdown 圍籬裡回來，有時還標上語言。
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*?)\n?\s*```\s*$", re.S)


def strip_fence(text):
    """剝掉包在外層的 markdown 圍籬。沒有圍籬就原樣回傳。

    公開給自製格式的解析用 —— 不只 JSON 會被包起來。
    """
    if not isinstance(text, str):
        return text
    match = _FENCE_RE.match(text.strip())
    return match.group(1) if match else text.strip()


def as_json(text, require=()):
    """把回覆轉成 dict。格式不對時丟 ValueError，交給 ask() 決定要不要重問。

    公開給「JSON 之外還要再驗一層結構」的呼叫端用：把這一支和自己的結構檢查
    串成一個 parse 傳給 ask()，兩層的失敗就共用同一套重問。分兩段做的話，
    第二段的失敗發生在 ask() 之外，重問永遠觸發不到。
    """
    body = strip_fence(text)
    try:
        data = json.loads(body)
    except ValueError as exc:
        # 訊息要帶一小段實際內容，否則「不是合法的 JSON」看不出模型到底回了什麼。
        head = body[:120].replace("\n", " ")
        raise ValueError("不是合法的 JSON（%s）：%s…" % (exc, head))

    if not isinstance(data, dict):
        raise ValueError("最外層不是物件，而是 %s" % type(data).__name__)

    missing = [key for key in require if key not in data]
    if missing:
        raise ValueError("缺少必要欄位：%s" % "、".join(missing))

    return data


def ask_json(url, prompt, require=(), reask=1, **kwargs):
    """問一次 AI 並把回覆解析成 dict。

    `require` 列出一定要有的頂層鍵；缺了就當成回覆格式不符，觸發重問。

    預設 `reask=1`：模型偶爾會在 JSON 前面加一句話，或回一段根本不是 JSON 的東西，
    重問一次通常就對了。不想付那次錢的話傳 reask=0。
    """
    return ask(url, prompt,
               parse=lambda text: as_json(text, require),
               reask=reask, **kwargs)


# ---------------------------------------------------------------------------
# 模型名稱的查詢 —— 報告出處用
# ---------------------------------------------------------------------------

# API 的根路徑。模型清單掛在它底下，所以查詢網址從端點裡它出現的位置組出來。
API_ROOT = "api/external/v1"

# 根路徑底下列出模型清單的那一段。**部署者填入**：這是服務端的協定，不是使用者該調的
# 設定，所以寫死而不進設定檔；但實際值不隨本專案公開。
#
# 沒填（仍是佔位值）時不送任何請求 —— 送一個指向佔位字串的網址只會換來一個 404，
# 而訊息看不出原因。
MODEL_LIST_PATH = "__FILL_IN_MODEL_LIST_PATH__"
_MODEL_LIST_PLACEHOLDER = "__FILL_IN_MODEL_LIST_PATH__"

# 查模型的逾時。**不用問 AI 的那個逾時**：那一個是為「等模型生成一整份分析」調的，
# 常見兩分鐘；列清單是一個輕量的 GET，拿兩分鐘去等它，服務連不上時使用者每次啟動
# 工具都得被擋兩分鐘。只試一次、不重試，理由相同 —— 它只是顯示用的值。
MODEL_LOOKUP_TIMEOUT = 10


def model_list_url(url):
    """由端點組出模型清單的網址；組不出來時回空字串。

        https://host:8443/api/external/v1/chat/completions
        →  https://host:8443/api/external/v1/<MODEL_LIST_PATH>

    取 API_ROOT **第一次**出現之前的那一段，接上 API_ROOT 與 MODEL_LIST_PATH，其後的
    部分捨棄。中間的斜線由這裡補，MODEL_LIST_PATH 不必自帶。
    """
    url = (url or "").strip()
    if not url:
        return ""

    path = (MODEL_LIST_PATH or "").strip().strip("/")
    if not path or path == _MODEL_LIST_PLACEHOLDER:
        logger.info("模型清單路徑尚未設定（ai_utils.MODEL_LIST_PATH），不查詢模型名稱")
        return ""

    at = url.find(API_ROOT)
    if at < 0:
        logger.info("端點中找不到 API 根路徑 %s，不查詢模型名稱（端點 %s）",
                    API_ROOT, url)
        return ""

    return "%s%s/%s" % (url[:at], API_ROOT, path)


def fetch_model_list(list_url, api_key="", timeout=MODEL_LOOKUP_TIMEOUT,
                     verify_ssl=True):
    """GET 模型清單，回傳陣列；任何失敗都回 None 並記一筆。**不拋例外。**

    回應的形狀是 `[{"shareCode": "...", "name": "..."}, ...]`。

    分成單獨一支，是因為列出模型的腳本要先把同一個服務的數個項目併成一次請求，
    再各自比對 —— lookup_model 那種「一項一問」的形狀做不到。
    """
    if not list_url:
        return None

    try:
        http_utils.require_requests(AiError)
        session = http_utils.new_session(_headers(api_key))
        response = session.get(list_url, timeout=timeout, verify=verify_ssl)
    except Exception as exc:                        # noqa: BLE001
        logger.info("查詢模型清單失敗（%s）：%s", list_url, exc)
        return None

    if response.status_code >= 400:
        logger.info("查詢模型清單失敗（%s）：HTTP %d",
                    list_url, response.status_code)
        return None

    try:
        body = response.json()
    except ValueError:
        logger.info("模型清單的回應不是合法的 JSON（%s）", list_url)
        return None

    if not isinstance(body, list):
        logger.info("模型清單的回應不是陣列，而是 %s（%s）",
                    type(body).__name__, list_url)
        return None

    return body


def find_model(models, share_code):
    """在模型清單裡找出 shareCode 相同的那一項，回傳它的 name；找不到回空字串。"""
    if not share_code or not isinstance(models, list):
        return ""

    for item in models:
        if not isinstance(item, dict):
            continue
        if str(item.get("shareCode", "")) == share_code:
            name = item.get("name")
            return name.strip() if isinstance(name, str) else ""

    # 只記筆數，不記 shareCode —— 它是憑證。
    logger.info("模型清單（%d 項）中沒有相符的 shareCode", len(models))
    return ""


def lookup_model(url, share_code, api_key="", verify_ssl=True,
                 timeout=MODEL_LOOKUP_TIMEOUT):
    """查出這組端點與 shareCode 對應的模型名稱；查不到回空字串。**不拋例外。**

    模型名稱只用於報告出處。一個顯示用的值查不到，不值得讓一次已經付出等待的分析
    失敗；原因都記在 log 裡，回答得了「出處為什麼少了模型」。
    """
    models = fetch_model_list(model_list_url(url), api_key=api_key,
                              timeout=timeout, verify_ssl=verify_ssl)
    if models is None:
        return ""
    return find_model(models, share_code)
