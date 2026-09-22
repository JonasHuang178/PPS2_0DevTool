#!/usr/bin/env python3
"""HTTP 呼叫的共用底層，給各個 REST 封裝（gitlab_utils、jira_utils…）共用。

這裡只放**與服務無關**的部分：建立 session、逾時、重試、把回應轉成資料結構、
例外的共同基底。各服務自己的東西不在這裡：

    認證標頭長什麼樣     各服務自己組好後傳進 new_session()
    API 根路徑           各服務自己拼
    錯誤訊息怎麼挖        GitLab 回 {"message": ...}，Jira 回 {"errorMessages": [...]}
    分頁怎麼翻            GitLab 看 X-Next-Page 標頭，Jira 用 startAt / total

抽出來的理由：這段東西兩個服務一字不差。各寫一份的話兩份會慢慢長歪，而且改了
一邊忘了另一邊時，症狀只在其中一個服務出現 —— 那種不對稱最難聯想到成因。

與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）：不印任何
東西到 stdout、不結束行程、不自行讀取設定檔或環境變數、回傳資料結構。
"""

import time

try:
    import requests
except ImportError:      # 見各服務模組「相依」段落，刻意不在 import 階段爆掉
    requests = None

from script_utils import logger

__all__ = ["HttpError", "DEFAULT_TIMEOUT", "RETRY_STATUS", "MAX_RETRIES",
           "RETRY_BACKOFF_SECONDS", "require_requests", "new_session",
           "send", "parse_json"]


# 逾時一律要有：沒有逾時的請求會讓整個 Qt 流程卡死，而使用者只能按取消。
DEFAULT_TIMEOUT = 30

# 這些狀態碼重試有意義：429 是被限流，5xx 多半是伺服器端的暫時狀況。
# 4xx 的其餘成員（401 權杖錯、404 找不到）重試幾次結果都一樣，只是拖長失敗。
RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0


class HttpError(Exception):
    """REST 呼叫失敗的共同基底。

    共用模組不結束行程也不自己印訊息，一律以例外拋出，由入口腳本決定怎麼回報。

    `code` 是給結果信封的 `error.code` 用的。各服務以 CODE_PREFIX 決定字首，
    因此 GitLab 的 401 是 GITLAB_401、Jira 的是 JIRA_401 —— 入口腳本可以直接
    依服務分流，不必再自己拼字串。
    """

    CODE_PREFIX = "HTTP"

    def __init__(self, message, status_code=None, url=""):
        super(HttpError, self).__init__(message)
        self.status_code = status_code
        self.url = url

    @property
    def code(self):
        if self.status_code is None:
            return "%s_ERROR" % self.CODE_PREFIX
        return "%s_%d" % (self.CODE_PREFIX, self.status_code)


def require_requests(error_class=HttpError):
    """確認 requests 裝了。沒裝時拋出呼叫端指定的例外型別。

    延到呼叫時才檢查，不在 import 階段爆掉：入口腳本的匯入發生在
    script_io.run() 之前，在那裡拋例外不會有結果信封，Qt 端只會顯示「腳本沒有
    回傳結果 (exit code 1)」，完全看不出是少裝套件。
    """
    if requests is None:
        raise error_class(
            "缺少 requests 套件，無法呼叫 REST API。請執行 pip install requests")


def new_session(headers=None):
    """建立帶指定標頭的 session。

    認證標頭由呼叫端組好傳進來 —— 這一層不認得任何一個服務的認證方式。
    權杖只放進標頭，絕不進 log、也不放進 URL query：query 會被伺服器與代理
    記進存取紀錄。
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    if headers:
        session.headers.update(headers)
    return session


def send(session, method, url, params=None, json_body=None,
         timeout=DEFAULT_TIMEOUT, verify_ssl=True, error_class=HttpError,
         stream=False):
    """送出一次請求，必要時重試，回傳 requests 的 response。

    重試只針對限流與伺服器端暫時狀況（見 RETRY_STATUS）。連線錯誤與逾時也
    重試 —— 那多半是網路抖動。

    stream=True 時內容不會先讀進記憶體，由呼叫端自行以 iter_content 取用並
    負責關閉 response。下載附件那類「可能幾百 MB」的回應一定要走這條，否則
    整個檔案會先進記憶體，而 Qt 端的腳本行程沒有多餘的空間可揮霍。

    狀態碼的檢查不在這裡：各服務的錯誤訊息藏在不同欄位，而且 4xx 要給的提示
    也不一樣，那些留給各自的 check_response()。
    """
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warn("REST 呼叫失敗，%.1f 秒後重試（第 %d 次）", wait, attempt)
            time.sleep(wait)

        try:
            response = session.request(method, url, params=params,
                                       json=json_body, timeout=timeout,
                                       verify=verify_ssl, stream=stream)
        except requests.exceptions.RequestException as exc:
            last_error = error_class("無法連線：%s" % exc, url=url)
            continue

        if response.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
            last_error = error_class("伺服器回應 %d" % response.status_code,
                                     status_code=response.status_code, url=url)
            continue

        return response

    raise last_error


def parse_json(response, url, error_class=HttpError):
    """回應轉成 Python 資料結構。

    204 之類沒有內容的回應回傳 None —— 那是正常結果，不是錯誤。
    """
    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except ValueError:
        raise error_class("回應不是合法的 JSON（HTTP %d）" % response.status_code,
                          status_code=response.status_code, url=url)
