#!/usr/bin/env python3
"""共用模組層。

分組依**技術領域**，不依應用功能：

    logger.py       所有共用模組與入口腳本共用的 log（唯一設定 logging 的地方）
    system_utils/   系統層面：檔案系統、暫存目錄
    gitlab_utils/   GitLab REST

依功能分組會讓第二個功能需要同一個能力時無處可放。只服務單一功能的邏輯不
屬於這裡，應該留在 scripts/<功能>/ 之下。

共用模組的規則（見 openspec/specs/script-envelope）：
    不結束行程，錯誤以例外拋出，是否結束由入口腳本決定
    不自行讀取設定檔或環境變數，所需的值由呼叫端明著傳入
    回傳資料結構，不回傳 JSON 字串
"""
