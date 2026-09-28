#!/usr/bin/env python3
"""向 AI 服務提問的共用模組。

使用者是 device 的 `summary.py`：**它組 prompt，這裡負責問與等。** prompt 不進這個
模組 —— 那正是每條產品線要自己掌握的東西，收進共用模組會把 device 機制的意義抵消掉。

    from script_utils import ai_utils

    text = ai_utils.ask(api_url, prompt)              # 原始回覆
    data = ai_utils.ask_json(api_url, prompt)         # 解析過的 JSON

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
           "split_share_code", "ROLE_USER",
           "DEFAULT_TIMEOUT", "MAX_RETRIES"]


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
# URL 與 shareCode
# ---------------------------------------------------------------------------

def split_share_code(api_url):
    """把設定檔的 Api_URL 拆成 (url, share_code)。

    設定檔裡的寫法是把 shareCode 以冒號黏在位址後面：

        https://ai.example.com/v1/chat:ABC123
        →  ("https://ai.example.com/v1/chat", "ABC123")

    **不能直接用 split(":")，也不能無條件用 rsplit**：一個位址裡至少有一個冒號
    （`https:`），而且可能還有連接埠（`host:8080`）。切錯的下場是把整個路徑當成
    shareCode 送出去，而伺服器只會回一個看不出原因的 400。

    這裡用的規則是「**最後一個斜線之後**的冒號才算分隔」：

        https://host:8080/v1/chat          最後一個 / 之後沒有冒號 → 沒有 shareCode
        https://host:8080/v1/chat:ABC      → ("https://host:8080/v1/chat", "ABC")
        https://host/v1/chat:ABC:DEF       → (".../chat:ABC", "DEF")  取最後一個

    找不到 shareCode 時 share_code 是空字串，由呼叫端決定那是不是錯誤。
    """
    url = (api_url or "").strip()
    if not url:
        return "", ""

    tail_start = url.rfind("/") + 1
    sep = url.rfind(":")
    if sep < tail_start:
        # 冒號在最後一個斜線之前 —— 那是 scheme 或連接埠，不是分隔符。
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


# 回應裡可能放答案的欄位名，依序試。
#
# ⚠️ 這個服務實際回什麼還沒確認，所以先容許幾種常見的寫法。確認之後把這一段換成單一
# 欄位 —— 依序猜會讓「欄位改名了」變成一個安靜的行為改變，而不是一個錯誤。
_REPLY_KEYS = ("message", "response", "answer", "result", "content", "text")


def _extract_reply(body, url):
    """從回應裡取出模型講的那段話。

    取不到時**列出實際拿到的鍵**：這個錯誤最常見的成因就是回應形狀跟預期不同，而
    「解析不到回覆」這五個字幫不上任何忙。第一次接上真的服務時，這個訊息就是你需要
    的那份資料。
    """
    if isinstance(body, str):
        # 有些服務直接回一段文字而不是 JSON 物件。
        return body

    if not isinstance(body, dict):
        error = AiError("AI 回應不是物件也不是文字（收到 %s）"
                        % type(body).__name__, url=url)
        raise error

    for key in _REPLY_KEYS:
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            logger.debug("回覆取自欄位 %r", key)
            return value

    # data 底下再找一層 —— 把結果包一層 data 的服務很常見。
    inner = body.get("data")
    if isinstance(inner, (dict, str)):
        return _extract_reply(inner, url)

    raise AiError(
        "解析不出 AI 的回覆內容。回應的頂層欄位：%s"
        % ("、".join(sorted(body.keys())) or "(沒有欄位)"),
        url=url)


def _headers(api_key):
    """請求標頭。

    這個服務以 payload 裡的 shareCode 辨識呼叫者，**沒有認證標頭**。設定檔的 Api_Key
    有填時才額外加上 Bearer —— 為了讓「服務改成要金鑰」不必動這個模組，但沒填時不送
    多餘的標頭（有些閘道看到不認得的 Authorization 會直接擋掉）。

    金鑰只進標頭，絕不進 URL query：query 會被伺服器與代理記進存取紀錄。
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    return headers


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
            "AI 服務拒絕了這次請求，請檢查 Api_URL 尾端的 shareCode",
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


def _call_once(session, url, payload, timeout, verify_ssl):
    """送出一次請求並取出回覆文字。失敗時拋 AiError。"""
    try:
        response = session.post(url, json=payload, timeout=timeout,
                                verify=verify_ssl)
    except Exception as exc:                        # noqa: BLE001
        # requests 的連線層例外。這一層不 import requests，所以以基底型別接。
        # 逾時與斷線在分鐘級的呼叫上很常見，值得重試。
        error = AiError("無法連線至 AI 服務：%s" % exc, url=url)
        error.retryable = True
        raise error

    if response.status_code >= 400:
        raise _describe(response, url)

    try:
        body = response.json()
    except ValueError:
        # 不是 JSON 也可能是正常的（有些服務直接回文字），交給 _extract_reply 判斷。
        text = (response.text or "").strip()
        if text:
            return _extract_reply(text, url)
        error = AiError("AI 回應是空的（HTTP %d）" % response.status_code,
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


def ask(api_url, prompt, history=None, file_ids=None, api_key="",
        timeout=DEFAULT_TIMEOUT, retries=MAX_RETRIES, on_retry=None,
        verify_ssl=True, parse=None, reask=0, reask_hint=REASK_HINT):
    """問一次 AI，回傳它講的那段話。

    `api_url` 直接收設定檔 Service.AI_Mode_List 裡的 Api_URL，shareCode 黏在尾端
    也沒關係 —— 這裡會拆（見 split_share_code）。呼叫端不必自己處理那個冒號。

    參數攤開而不是收一個 inputs 字典 —— 與 gitlab_utils、jira_utils 同一個慣例，
    這個模組因此不認得任何一個功能的參數形狀。

    **沒有 model 參數**：這個服務的 payload 裡沒有模型欄位，模型是由 shareCode 那一端
    決定的。設定檔的 Model 仍然有用，但那是報告出處要印的資訊，不是請求的一部分 ——
    收一個送不出去的參數只會讓人以為換了它就會換模型。

    兩種重試，界線不同：

      **連線層**（逾時、斷線、429、5xx）重試 `retries` 次，指數退避，429 優先
      照 Retry-After 指定的秒數等。

      **內容層**（`parse` 丟出 ValueError）重問 `reask` 次，第二次起在 prompt 尾端
      追加 `reask_hint`。模型偶爾會在答案前面加一句「好的，以下是分析：」，重問一次
      的成功率很高 —— 但它要錢也要時間，所以預設是 0，由呼叫端明確開啟。

    `parse` 是轉換而不是檢查：拿到原始文字、回傳呼叫端要的東西，格式不對就丟
    ValueError。JSON 只是它的一個特例（見 ask_json），自製格式寫一支自己的 parse
    傳進來即可，兩種格式共用同一套重試。

    **prompt 與 shareCode 都不進 log。** prompt 裡有整份 diff，印出來會把 log 撐爆，
    也把原始碼落到磁碟上。
    """
    http_utils.require_requests(AiError)

    url, share_code = split_share_code(api_url)

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


def ask_json(api_url, prompt, require=(), reask=1, **kwargs):
    """問一次 AI 並把回覆解析成 dict。

    `require` 列出一定要有的頂層鍵；缺了就當成回覆格式不符，觸發重問。

    預設 `reask=1`：模型偶爾會在 JSON 前面加一句話，或回一段根本不是 JSON 的東西，
    重問一次通常就對了。不想付那次錢的話傳 reask=0。
    """
    return ask(api_url, prompt,
               parse=lambda text: as_json(text, require),
               reask=reask, **kwargs)
