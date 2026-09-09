#!/usr/bin/env python3
"""暫存目錄。"""

import os
import tempfile

__all__ = ["temp_file_path"]


def temp_file_path(name):
    """回傳系統暫存目錄下某個檔名的絕對路徑。

    tempfile.gettempdir() 在各平台解析為：

        Windows        %TEMP%（通常是 C:\\Users\\<user>\\AppData\\Local\\Temp）
        Linux / macOS  $TMPDIR 或 /tmp

    每個使用者的暫存目錄互相獨立，多人共用同一台機器不會互相蓋掉。

    注意：Windows 的磁碟清理與「儲存空間感知」會清理 %TEMP%，放在這裡的
    檔案可能在重新開機或系統維護後消失。需要跨重啟保留的資料不該用這裡，
    正確的去處是 %LOCALAPPDATA%。
    """
    return os.path.join(tempfile.gettempdir(), name)
