#!/usr/bin/env python3
"""Single Building 的業務邏輯。

入口腳本只做轉接（收信封 -> 呼叫這裡 -> 回信封）。要把這些能力整合進自己
流程的人，正確的介面是這個模組，不是那四支腳本。
"""

from .paths import SETTING_FILE_NAME, setting_file_path
from .setting import clear_setting, read_setting, write_setting
from .sources import scan_cpp_files

__all__ = [
    "SETTING_FILE_NAME",
    "setting_file_path",
    "scan_cpp_files",
    "read_setting",
    "write_setting",
    "clear_setting",
]
