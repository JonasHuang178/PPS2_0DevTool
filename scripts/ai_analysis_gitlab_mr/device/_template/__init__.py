#!/usr/bin/env python3
"""device 鉤子的範本。複製整個目錄、改成你的 device 名稱，再把不需要的鉤子刪掉。

    cp -r device/_template device/ssd

**目錄名就是 device 名**，而它會被當成模組名 import，所以必須是合法的 Python 識別字：
小寫英數與底線、不以數字開頭。`ssd` 可以，`ssd_gen4` 可以，`ssd-gen4` 不行。

指定方式是環境變數 `PPS_DEVICE`（工具端來自設定檔的 `PPS_Device`）。未指定時用
`default`；指定了一個不存在的名稱會直接失敗並列出認得哪些。

**三個鉤子都是選用的。** 只放你要覆寫的那幾支，缺的會自動用 `default` 的 —— 只想改
報告版面的 device 不需要複製 summary。

底線開頭的目錄不會被當成 device，所以這份範本不會出現在可用清單裡。
"""

# 這個 device 的版本，會印在報告末尾的出處資訊裡。
#
# **改了產出方式就把它往上加。** 沒有任何機制強迫，忘了加的話新舊報告在外觀上分不
# 出來 —— 而那正是那一行存在的理由。
VERSION = "1.0"
