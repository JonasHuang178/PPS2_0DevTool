#!/usr/bin/env python3
"""系統層面的共用 API：檔案系統、暫存目錄、環境變數與路徑表示法。

放這裡的東西不認得任何一個應用功能 —— 它們是「作業系統提供什麼」的薄封裝，
任何功能都能拿去用。只服務單一功能的邏輯不屬於這裡，應該留在該功能自己的
目錄下。
"""

from .env import get_env_var
from .files import (create_folder, list_files_by_suffix, read_lines,
                    write_lines)
from .paths import to_windows_path_format
from .temp import temp_file_path

__all__ = [
    "get_env_var",
    "create_folder",
    "list_files_by_suffix",
    "read_lines",
    "write_lines",
    "to_windows_path_format",
    "temp_file_path",
]
