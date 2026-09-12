#!/usr/bin/env python3
"""GitLab REST 的共用 API。

對 GitLab REST API 的呼叫封裝（專案、分支、merge request、issue、pipeline…），
以資料結構回傳，不做 UI、不讀設定檔、不結束行程 —— 與其他共用模組遵守同一組
規則（見 openspec/specs/script-envelope）。

不該放這裡的東西：只服務單一應用功能的邏輯。那屬於該功能自己的目錄。

認證權杖一律由入口腳本自環境變數或設定檔取出後明著傳入，共用模組 MUST NOT
自行讀取環境變數或設定檔。「要不要驗證 TLS 憑證」同理 —— 這裡不設預設值，
由呼叫端明著指定。

以標準函式庫實作，不引入第三方套件：本專案沒有任何 Python 相依清單，多一個
就等於替部署與持續整合各多一個安裝步驟。

    merge_requests.py   Merge Request 的查詢
    errors.py           例外型別（權杖、找不到、TLS、HTTP、連線各自分開）
"""

from script_utils.gitlab_utils.errors import (
    GitLabAuthError,
    GitLabConnectionError,
    GitLabError,
    GitLabHttpError,
    GitLabNotFoundError,
    GitLabTlsError,
)
from script_utils.gitlab_utils.merge_requests import (
    PER_PAGE_LIMIT,
    list_merge_requests,
)

__all__ = [
    "GitLabError",
    "GitLabAuthError",
    "GitLabNotFoundError",
    "GitLabTlsError",
    "GitLabHttpError",
    "GitLabConnectionError",
    "PER_PAGE_LIMIT",
    "list_merge_requests",
]
