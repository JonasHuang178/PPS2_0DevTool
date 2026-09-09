#!/usr/bin/env python3
"""檔案系統的共用能力。"""

import os

from script_utils import logger

__all__ = ["list_files_by_suffix", "read_lines", "write_lines"]


def list_files_by_suffix(directory, suffix, recursive=False):
    """列出 directory 中副檔名為 suffix 的檔案。

    suffix 含點，例如 ".cpp"。比對**不分大小寫** —— Windows 的檔案系統本身
    就不分，只收小寫會讓使用者看不到自己明明放在那裡的 .CPP。

    預設不遞迴。需要整棵樹時明著傳 recursive=True，不要讓呼叫端在「只想要
    這一層」時意外收到幾千筆。

    回傳 [{"name": 檔名, "path": 絕對路徑}, ...]。

    目錄中沒有符合的檔案是正常結果，回傳空清單而不是拋出例外。
    """
    if not os.path.isdir(directory):
        raise ValueError("路徑不是一個目錄：%s" % directory)

    wanted = suffix.lower()
    entries = []

    if recursive:
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if os.path.splitext(name)[1].lower() == wanted:
                    entries.append({"name": name,
                                    "path": os.path.abspath(os.path.join(root, name))})
    else:
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            if os.path.splitext(name)[1].lower() != wanted:
                continue
            entries.append({"name": name, "path": os.path.abspath(full)})

    logger.debug("在 %s 找到 %d 個 %s（recursive=%s）",
                 directory, len(entries), suffix, recursive)
    return entries


def read_lines(path):
    """讀出行式文字檔的內容，去掉空白行。

    檔案不存在時回傳空清單而不是拋出例外 —— 對呼叫端而言「還沒建立」與
    「內容是空的」是同一件事。
    """
    if not os.path.isfile(path):
        logger.debug("檔案尚不存在：%s", path)
        return []

    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read().splitlines()

    lines = []
    for line in raw:
        line = line.strip()
        if line:
            lines.append(line)

    logger.debug("自 %s 讀出 %d 行", path, len(lines))
    return lines


def write_lines(path, lines):
    """把每一行寫入檔案，覆蓋原有內容。空白行會被略過。

    lines 為空時寫入空內容 —— 那是有效的結果，不是錯誤。

    回傳實際寫入的行數。
    """
    cleaned = []
    for line in lines:
        line = str(line).strip()
        if line:
            cleaned.append(line)

    with open(path, "w", encoding="utf-8") as handle:
        for line in cleaned:
            handle.write(line + "\n")

    logger.debug("寫入 %s，共 %d 行", path, len(cleaned))
    return len(cleaned)
