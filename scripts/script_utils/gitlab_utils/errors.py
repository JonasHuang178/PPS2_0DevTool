#!/usr/bin/env python3
"""GitLab 呼叫的例外型別。

分成不同型別而不是共用一個，是為了讓入口腳本能給出**不同的**失敗訊息：
權杖無效與專案不存在，使用者要做的下一步完全不同 —— 一個去換權杖，一個去
改設定檔的拼字。兩者都回「取得失敗」等於要他自己猜。

共用模組不結束行程、不印 stdout：錯誤一律以這些例外拋出，是否結束、要顯示
什麼訊息，由入口腳本決定。
"""

__all__ = [
    "GitLabError",
    "GitLabAuthError",
    "GitLabNotFoundError",
    "GitLabTlsError",
    "GitLabHttpError",
    "GitLabConnectionError",
]


class GitLabError(Exception):
    """所有 GitLab 呼叫錯誤的基底。"""


class GitLabAuthError(GitLabError):
    """權杖缺失、無效或權限不足（HTTP 401 / 403）。"""


class GitLabNotFoundError(GitLabError):
    """專案或資源不存在（HTTP 404）。

    注意：權杖沒有該專案權限時，GitLab 也會回 404 而不是 403 —— 這是刻意的
    設計（不讓外人以狀態碼探測專案是否存在）。所以這個例外的訊息不該斷言
    「專案一定不存在」，而該把兩種可能都講出來。
    """


class GitLabTlsError(GitLabError):
    """TLS 憑證驗證失敗。"""


class GitLabHttpError(GitLabError):
    """其他 HTTP 錯誤。"""


class GitLabConnectionError(GitLabError):
    """連線層級的失敗：DNS、逾時、拒絕連線。"""
