#!/usr/bin/env python3
"""暫存設定檔的讀寫。

檔案格式：每行一個絕對路徑。空行忽略。

保存絕對路徑而不是檔名：設定必須指向確切的檔案。使用者換了來源目錄之後，
同名的檔案是不同的檔案。
"""

import os

from script_utils import logger

from .paths import setting_file_path

__all__ = ["read_setting", "write_setting", "clear_setting"]


def read_setting():
    """讀出設定檔中的絕對路徑。

    回傳 [{"name": 檔名, "path": 絕對路徑}, ...]，形狀與 scan_cpp_files()
    相同，Qt 端因此可以共用同一段解析。

    檔案不存在或內容為空一律視為「設定為空」，回傳空清單而不是拋出例外 ——
    第一次使用時檔案本來就還不存在。
    """
    path = setting_file_path()
    if not os.path.isfile(path):
        logger.debug("設定檔尚不存在：%s", path)
        return []

    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        entries.append({"name": os.path.basename(line), "path": line})

    logger.debug("自 %s 讀出 %d 筆", path, len(entries))
    return entries


def write_setting(paths):
    """把絕對路徑寫入設定檔，覆蓋原有內容。

    paths 為空清單時寫入空內容 —— 那是有效的設定（什麼都沒選），
    不是錯誤。

    回傳實際寫入的路徑數。
    """
    path = setting_file_path()

    cleaned = []
    for item in paths:
        item = str(item).strip()
        if item:
            cleaned.append(item)

    with open(path, "w", encoding="utf-8") as handle:
        for item in cleaned:
            handle.write(item + "\n")

    logger.debug("寫入 %s，共 %d 筆", path, len(cleaned))
    return len(cleaned)


def clear_setting():
    """清空設定檔的內容。

    清空而不是刪除檔案：讀取端對「檔案不存在」與「內容為空」的處理相同，
    但保留一個空檔案讓使用者在檔案總管裡看得到它確實被清過。
    """
    return write_setting([])
