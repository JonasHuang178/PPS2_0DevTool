#!/usr/bin/env python3
"""Jira REST 的共用 API。

尚未有任何實作，這個檔案目前只說明什麼該放進來。

該放這裡的東西：對 Jira REST API 的呼叫封裝（issue、專案、搜尋、附件、
transition…），以資料結構回傳，不做 UI、不讀設定檔、不結束行程 —— 與其他共用
模組遵守同一組規則（見 openspec/specs/script-envelope）。

不該放這裡的東西：只服務單一應用功能的邏輯。那屬於該功能自己的目錄。

認證資訊一律由入口腳本自設定檔取出後明著傳入，共用模組 MUST NOT 自行讀取
環境變數或設定檔。權杖只進標頭，不進 log、不進 URL query —— query 會被伺服器
與代理記進存取紀錄。

相依 requests，與 gitlab_utils 相同（見 requirements.txt）。匯入失敗會延到真正
呼叫時才拋出例外，不在 import 階段爆掉：入口腳本的匯入發生在 script_io.run()
之前，在那裡拋例外不會有結果信封，Qt 端只會顯示「腳本沒有回傳結果」。
"""

__all__ = []
