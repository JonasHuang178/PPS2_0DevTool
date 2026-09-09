#!/usr/bin/env python3
"""GitLab REST 的共用 API。

本次交付尚未有任何 GitLab 需求，因此這個分組目前是空的。

該放這裡的東西：對 GitLab REST API 的呼叫封裝（專案、分支、merge request、
issue、pipeline…），以資料結構回傳，不做 UI、不讀設定檔、不結束行程 ——
與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）。

不該放這裡的東西：只服務單一應用功能的邏輯。那屬於該功能自己的目錄。

認證權杖一律由入口腳本自設定檔取出後明著傳入，共用模組 MUST NOT 自行讀取
環境變數或設定檔。
"""

__all__ = []
