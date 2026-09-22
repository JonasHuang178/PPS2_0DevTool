#!/usr/bin/env python3
"""共用模組層。

分組依**技術領域**，不依應用功能：

    logger.py        所有共用模組與入口腳本共用的 log（唯一設定 logging 的地方）
    system_utils.py  向作業系統要東西：環境變數、建目錄、列目錄、暫存目錄、路徑格式
    file_utils.py    檔案內容的讀寫
    http_utils.py    REST 呼叫的共用底層（session、逾時、重試、例外基底）
    gitlab_utils.py  GitLab REST
    jira_utils.py    Jira REST（Server/DC，/rest/api/2）

依功能分組會讓第二個功能需要同一個能力時無處可放。只服務單一功能的邏輯不
屬於這裡，應該留在 scripts/<功能>/ 之下。

一個分組**預設是單一 .py 檔案**，而且**不以行數為拆檔的理由**。唯一該拆成
目錄的情況是：分組內出現**彼此不相依的獨立關切**（例如 GitLab 的 REST client，
與一個完全不經過 client 的 webhook 簽章驗證）。

行數曾經是判準之一（「超過約 500 行就拆」），後來拿掉了：長度只是內聚性的代理
指標，而它指錯方向的時候比指對的時候多。jira_utils 七百多行，但整份圍繞同一個
client、同一種認證、同一套錯誤處理 —— 照行數拆只會把一件事切成三份，讓「改一個
行為要動幾個檔案」從一變三。Python 標準庫的 argparse 約 2500 行、http/client.py
約 1500 行，都是單檔。

拆的時候由該目錄的 __init__.py 原樣 re-export。呼叫端一律寫
`from script_utils import <分組>`，兩種形式在 import 端完全相同，因此拆與不拆
都不需要更動任何一行呼叫。

因此：**先全部寫在單一檔案裡，真的該拆的時候一口氣拆開**。分組還小就先拆成
目錄，換到的只有一份要跟著維護的再匯出清單 —— 漏掉一筆的症狀是「函式明明寫好了
卻搆不到」。這個決定晚做比早做便宜：拆的成本是一次搬移，零個呼叫端改動。

共用模組的規則（見 openspec/specs/script-envelope）：
    不印任何東西到 stdout —— stdout 是結果通道
    不結束行程，錯誤以例外拋出，是否結束由入口腳本決定
    不自行讀取設定檔或環境變數，所需的值由呼叫端明著傳入
    回傳資料結構，不回傳 JSON 字串
"""
