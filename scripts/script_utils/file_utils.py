#!/usr/bin/env python3
"""檔案內容的讀寫。

跟**檔案內容**打交道的東西放這裡：讀進來、寫出去。向作業系統要東西的
（環境變數、建立目錄、列出目錄內容、暫存目錄位置、路徑格式）在 system_utils.py。

與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）：不印任何東西
到 stdout、不結束行程、不自行讀取設定檔或環境變數、回傳資料結構。
"""

import os

from script_utils import logger

__all__ = ["read_lines", "write_lines"]


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
