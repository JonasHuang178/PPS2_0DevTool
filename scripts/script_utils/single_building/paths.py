#!/usr/bin/env python3
"""暫存設定檔的位置。

三支腳本（讀取、寫入、清空）必須指向**同一個**檔案。指不一致的症狀是
「寫進去讀不出來」，而且從任何一支腳本單獨看都毫無異狀 —— 因此位置只在
這裡決定一次，三支共用。

不放進設定檔：多一個設定鍵就多一個使用者可以填錯的地方，而這個路徑沒有
需要隨環境調整的理由。

tempfile.gettempdir() 在各平台解析為：

    Windows        %TEMP%（通常是 C:\\Users\\<user>\\AppData\\Local\\Temp）
    Linux / macOS  $TMPDIR 或 /tmp

每個使用者的暫存目錄互相獨立，多人共用同一台機器不會互相蓋掉。

注意：Windows 的磁碟清理與「儲存空間感知」會清理 %TEMP%，這份設定因此
可能在重新開機或系統維護後消失 —— 這是刻意接受的行為。若日後需要跨重啟
保留，正確位置是 %LOCALAPPDATA%，只需要改動這個函式。
"""

import os
import tempfile

__all__ = ["SETTING_FILE_NAME", "setting_file_path"]

SETTING_FILE_NAME = "PPS2_0DevTool_single_building.txt"


def setting_file_path():
    """回傳暫存設定檔的絕對路徑。"""
    return os.path.join(tempfile.gettempdir(), SETTING_FILE_NAME)
