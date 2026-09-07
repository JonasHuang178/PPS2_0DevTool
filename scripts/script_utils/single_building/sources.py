#!/usr/bin/env python3
"""來源目錄的掃描。"""

import os

from script_utils import logger

__all__ = ["scan_cpp_files"]

CPP_SUFFIX = ".cpp"


def scan_cpp_files(directory):
    """列出 directory 這一層的 .cpp 檔案。

    **不遞迴**進入子目錄：使用者選的是「要處理哪一批檔案」，把整棵樹掃進來
    會讓清單長到無法選擇。

    回傳 [{"name": 檔名, "path": 絕對路徑}, ...]。
    name 給畫面顯示，path 是寫進設定檔的內容 —— 完整路徑前綴完全相同又很長，
    顯示出來只會撐爆清單寬度。

    副檔名比對不分大小寫：Windows 的檔案系統本身就不分，只收小寫 .cpp 會讓
    使用者看不到自己明明放在那裡的 .CPP。

    目錄中沒有任何 .cpp 是正常結果，回傳空清單而不是拋出例外 ——
    「這個目錄沒有 cpp」不是錯誤。
    """
    if not os.path.isdir(directory):
        raise ValueError("來源路徑不是一個目錄：%s" % directory)

    entries = []
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(name)[1].lower() != CPP_SUFFIX:
            continue
        entries.append({"name": name, "path": os.path.abspath(full)})

    logger.debug("掃描 %s，找到 %d 個 %s", directory, len(entries), CPP_SUFFIX)
    return entries
