#!/usr/bin/env python3
"""向 AI 服務提問的共用模組。

使用者是 device 的 `summary.py`：**它組 prompt，這裡負責問與等。** prompt 不進這個
模組 —— 那正是每條產品線要自己掌握的東西，收進共用模組會把 device 機制的意義抵消掉。

    from script_utils import ai_utils

    text = ai_utils.ask(url, key, model, prompt)              # 原始回覆
    data = ai_utils.ask_json(url, key, model, prompt)         # 解析過的 JSON

落地模型的封包形狀集中在 **_build_payload() 與 _extract_reply()** 兩支。要換供應商、
或改成自家的請求格式，改那兩支即可；重試、退避、逾時與錯誤分類都與封包形狀無關，
不必跟著動。目前預設的是 OpenAI 相容的 /chat/completions 形狀，因為那是多數地端服務
與代理都提供的介面。

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
# 其餘的 4xx 一律不重試：401 是金鑰錯、404 是端點或模型名打錯、413 是 prompt 太長、
# 400 多半是封包形狀不對。這些重試三次結果完全一樣，只是把同一個錯誤等三倍時間。
RETRY_STATUS = (408, 429, 500, 502, 503, 504)

# 回覆不符預期時，追加在 prompt 尾端再問一次的提示。
REASK_HINT = "\n\n只回覆結果本身，不要任何開場白、說明或註解。"


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
# 封包形狀 —— 換供應商只要動這一段
# ---------------------------------------------------------------------------

def _build_payload(model, prompt, system, options):
    """組出請求的 body。

    目前是 OpenAI 相容的 /chat/completions 形狀：

        {"model": ..., "messages": [{"role": "system"|"user", "content": ...}]}

    落地模型若是別的形狀（例如只吃 {"prompt": ...}），改這裡。`options` 是呼叫端
    傳進來的額外欄位（temperature、max_tokens 之類），原樣合併進去 —— 哪些欄位有效
    是供應商的事，這一層不篩。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model, "messages": messages}
    if options:
        payload.update(options)
    return payload


def _extract_reply(body, url):
    """從回應裡取出模型講的那段話。

    目前是 OpenAI 相容的 choices[0].message.content。落地模型若把答案放在別的欄位，
    改這裡。

    取不到時**回報實際拿到的鍵**：這個錯誤最常見的成因就是封包形狀猜錯，而「解析
    不到回覆」這五個字幫不上任何忙。
    """
    if not isinstance(body, dict):
        raise AiError("AI 回應不是物件（收到 %s）" % type(body).__name__, url=url)

    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        # 有些相容實作把答案放在 choices[0].text（舊的 completions 形狀）。
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text

    raise AiError(
        "解析不出 AI 的回覆內容",
        url=url)


def _auth_headers(api_key):
    """認證標頭。

    落地模型若用別的標頭（例如 `api-key` 或自家的名稱），改這裡。金鑰只進標頭，
    絕不進 URL query —— query 會被伺服器與代理記進存取紀錄。
    """
    return {"Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json"}


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

    訊息按「使用者的下一步」分開寫：換金鑰、改設定檔、縮短 prompt、稍後再試，
    這四件事完全不一樣。
    """
    status = response.status_code
    body = (response.text or "").strip()
    # 伺服器回的錯誤訊息通常很有用，但可能很長（有些會把整個 prompt 回貼）。
    if len(body) > 500:
        body = body[:500] + "…"

    if status in (401, 403):
        error = AiError(
            "AI 服務拒絕了這次請求，請檢查 API 金鑰",
            status_code=status, url=url)
    elif status == 404:
        error = AiError(
            "AI 端點不存在（404），請檢查設定檔的 Api_URL 與 Model",
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
        # 回應本身壞掉（截斷的 JSON、代理插進來的 HTML 錯誤頁）—— 重試有機會。
        error = AiError("AI 回應不是合法的 JSON（HTTP %d）" % response.status_code,
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
    if on_retry:
        try:
            on_retry(attempt, why)
        except Exception:                           # noqa: BLE001
            # 回呼只是報進度，它自己壞掉不該讓整次分析失敗。
            logger.debug("on_retry 回呼失敗，忽略")
    time.sleep(seconds)


def ask(api_url, api_key, model, prompt, system="", timeout=DEFAULT_TIMEOUT,
        retries=MAX_RETRIES, on_retry=None, verify_ssl=True, options=None,
        parse=None, reask=0, reask_hint=REASK_HINT):
    """問一次 AI，回傳它講的那段話。

    參數攤開而不是收一個 inputs 字典 —— 與 gitlab_utils、jira_utils 同一個慣例，
    這個模組因此不認得任何一個功能的參數形狀。

    兩種重試，界線不同：

      **連線層**（逾時、斷線、429、5xx）重試 `retries` 次，指數退避，429 優先
      照 Retry-After 指定的秒數等。

      **內容層**（`parse` 丟出 ValueError）重問 `reask` 次，第二次起在 prompt 尾端
      追加 `reask_hint`。模型偶爾會在答案前面加一句「好的，以下是分析：」，重問一次
      的成功率很高 —— 但它要錢也要時間，所以預設是 0，由呼叫端明確開啟。

    `parse` 是轉換而不是檢查：拿到原始文字、回傳呼叫端要的東西，格式不對就丟
    ValueError。JSON 只是它的一個特例（見 ask_json），自製格式寫一支自己的 parse
    傳進來即可，兩種格式共用同一套重試。

    **prompt 與金鑰都不進 log。** prompt 裡有整份 diff，印出來會把 log 撐爆，也把
    原始碼落到磁碟上。
    """
    http_utils.require_requests(AiError)

    if not api_url:
        raise AiError("未指定 AI 端點（Api_URL）")
    if not model:
        raise AiError("未指定 AI 模型（Model）")

    session = http_utils.new_session(_auth_headers(api_key))
    logger.info("送交 AI：model=%s prompt=%d 字元 timeout=%ds",
                model, len(prompt or ""), timeout)

    # 內容層的迴圈在外：重問是換一份 prompt 重新走完整套連線層重試。
    for round_no in range(reask + 1):
        text = _ask_raw(session, api_url, model,
                        prompt if round_no == 0 else prompt + reask_hint,
                        system, timeout, retries, on_retry, verify_ssl, options)

        if parse is None:
            return text

        try:
            return parse(text)
        except ValueError as exc:
            if round_no >= reask:
                raise AiError(
                    "AI 的回覆不是預期的格式：%s" % exc,
                    url=api_url)
            logger.warn("AI 回覆格式不符（%s），重問一次", exc)
            if on_retry:
                try:
                    on_retry(round_no + 1, "回覆格式不符")
                except Exception:                   # noqa: BLE001
                    logger.debug("on_retry 回呼失敗，忽略")


def _ask_raw(session, api_url, model, prompt, system, timeout, retries,
             on_retry, verify_ssl, options):
    """連線層：送出、失敗就退避重試，回傳原始回覆文字。"""
    payload = _build_payload(model, prompt, system, options)
    last = None

    for attempt in range(retries + 1):
        try:
            return _call_once(session, api_url, payload, timeout, verify_ssl)
        except AiError as exc:
            last = exc

            # 不值得重試的錯誤立刻拋 —— 金鑰錯重試三次還是金鑰錯，封包形狀猜錯
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
                    status_code=exc.status_code, url=api_url)

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


def ask_json(api_url, api_key, model, prompt, system="", require=(),
             reask=1, **kwargs):
    """問一次 AI 並把回覆解析成 dict。

    `require` 列出一定要有的頂層鍵；缺了就當成回覆格式不符，觸發重問。

    預設 `reask=1`：模型偶爾會在 JSON 前面加一句話，或回一段根本不是 JSON 的東西，
    重問一次通常就對了。不想付那次錢的話傳 reask=0。
    """
    return ask(api_url, api_key, model, prompt, system=system,
               parse=lambda text: as_json(text, require),
               reask=reask, **kwargs)
