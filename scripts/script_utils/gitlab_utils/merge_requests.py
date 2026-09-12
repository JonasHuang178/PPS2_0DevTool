#!/usr/bin/env python3
"""GitLab Merge Request 的查詢。

以標準函式庫的 urllib 實作，不引入第三方套件：本專案沒有任何 Python 相依
清單，`.pro` 的註解也寫明 Windows 端拿到專案用 Qt Creator 開啟即可建置。
加一個 requests 等於替部署與 CI 各加一個安裝步驟，而這裡的需求只是一個帶
標頭的 GET。

共用模組的四條規則在這裡一樣適用：不印 stdout、不結束行程、不自行讀環境
變數或設定檔、回傳資料結構而非 JSON 字串。權杖與「要不要驗證 TLS」都由
入口腳本明著傳入。
"""

import datetime
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from script_utils import logger
from script_utils.gitlab_utils.errors import (
    GitLabAuthError,
    GitLabConnectionError,
    GitLabHttpError,
    GitLabNotFoundError,
    GitLabTlsError,
)

__all__ = ["PER_PAGE_LIMIT", "list_merge_requests"]

# GitLab 的 per_page 上限就是 100，所以這是「一次請求拿得到的最大值」。
#
# 不翻頁是刻意的：畫面上的表格是單選的，使用者要從中挑出一筆。取回上千筆
# 不會讓那個動作更容易，只會讓等待變長、表格更難掃。範圍太大時正確的操作是
# 調緊查詢條件。
PER_PAGE_LIMIT = 100

_TIMEOUT_SECONDS = 30


def _build_ssl_context(verify_ssl):
    if verify_ssl:
        return ssl.create_default_context()

    # 呼叫端明著要求不驗證。暴露的是權杖本身 —— 任何能插入連線的人出示
    # 假憑證即可取得它。這個決定在設定檔裡看得見（Gitlab_Verify_SSL），
    # 不藏在程式碼中。
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _created_after_iso(days):
    """把「N 天內」換算成 GitLab 要的 ISO 8601 時間點。"""
    moment = datetime.datetime.now(datetime.timezone.utc) \
        - datetime.timedelta(days=int(days))
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise(raw):
    """把 GitLab 的回應收斂成畫面需要的五個欄位。

    呼叫端不該認得 GitLab 的完整 schema —— 那會讓「換一個欄位來源」變成要
    改兩個地方。
    """
    author = raw.get("author") or {}
    return {
        "iid": raw.get("iid"),
        "title": raw.get("title") or "",
        "author": author.get("name") or author.get("username") or "",
        "created_at": raw.get("created_at") or "",
        "state": raw.get("state") or "",
        "web_url": raw.get("web_url") or "",
    }


def list_merge_requests(server_url, token, project,
                        only_open=True,
                        created_after_days=None,
                        verify_ssl=True,
                        limit=PER_PAGE_LIMIT):
    """列出指定專案的 Merge Request。

    project 是 `namespace/project` 形式的字串 —— GitLab 接受 URL 編碼後的
    專案路徑作為識別，不需要另外查數字 ID。

    回傳 {"merge_requests": [...], "truncated": bool}。truncated 為真代表
    取回筆數達到上限，結果可能未完整；呼叫端據此決定要不要告訴使用者。

    失敗時拋出 gitlab_utils.errors 底下的例外，不結束行程。
    """
    if not server_url:
        raise GitLabConnectionError("未指定 GitLab 伺服器位址")
    if not project:
        raise GitLabNotFoundError("未指定專案")

    encoded = urllib.parse.quote(str(project), safe="")

    query = {
        "per_page": int(limit),
        "order_by": "created_at",
        "sort": "desc",
    }
    if only_open:
        query["state"] = "opened"
    if created_after_days:
        query["created_after"] = _created_after_iso(created_after_days)

    url = "%s/api/v4/projects/%s/merge_requests?%s" % (
        str(server_url).rstrip("/"),
        encoded,
        urllib.parse.urlencode(query),
    )

    # 權杖不進 log。這裡只記路徑與條件。
    logger.debug("GET %s", url)

    request = urllib.request.Request(url, method="GET")
    request.add_header("PRIVATE-TOKEN", token or "")
    request.add_header("Accept", "application/json")

    context = _build_ssl_context(verify_ssl)

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS,
                                    context=context) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GitLabAuthError(
                "GitLab 拒絕了這次請求（HTTP %d）" % exc.code)
        if exc.code == 404:
            raise GitLabNotFoundError(
                "GitLab 找不到專案 %s（HTTP 404）" % project)
        raise GitLabHttpError(
            "GitLab 回應 HTTP %d：%s" % (exc.code, exc.reason))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLError):
            raise GitLabTlsError("TLS 憑證驗證失敗：%s" % reason)
        raise GitLabConnectionError("無法連線至 GitLab：%s" % reason)

    try:
        raw_items = json.loads(payload.decode("utf-8"))
    except ValueError as exc:
        raise GitLabHttpError("GitLab 的回應不是合法的 JSON：%s" % exc)

    if not isinstance(raw_items, list):
        raise GitLabHttpError("GitLab 的回應不是預期的陣列")

    items = [_normalise(item) for item in raw_items]

    logger.debug("取回 %d 筆 Merge Request", len(items))

    return {
        "merge_requests": items,
        "truncated": len(items) >= int(limit),
    }
