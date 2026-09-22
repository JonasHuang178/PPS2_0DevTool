#!/usr/bin/env python3
"""檔案內容的讀寫。

跟**檔案內容**打交道的東西放這裡：讀進來、寫出去。向作業系統要東西的
（環境變數、建立目錄、列出目錄內容、暫存目錄位置、路徑格式）在 system_utils.py。

與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）：不印任何東西
到 stdout、不結束行程、不自行讀取設定檔或環境變數、回傳資料結構。
"""

import os
import shutil

from script_utils import logger

__all__ = ["read_file", "write_file", "copy_file",
           "read_lines", "write_lines"]


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


def read_file(file_path):
    """讀出整個檔案的內容，回傳字串。

    以 UTF-8 解碼，內容原樣回傳 —— 不去空白行、不 strip、換行保留。要逐行處理
    且想略過空白行的，用 read_lines()。

    **檔案不存在時拋出 FileNotFoundError**，這點與 read_lines() 刻意不同。
    read_lines() 回空清單是因為它服務的情境裡「還沒建立」與「內容是空的」是
    同一件事（例如尚未存過的暫存設定檔）。read_file() 是通用讀取，路徑打錯時
    回空字串會讓錯誤裝成「檔案是空的」，而那個誤會會一路帶到很下游才爆開。

    非 UTF-8 的內容拋出 UnicodeDecodeError，不靜默替換 —— 共用模組不替呼叫端
    決定「壞掉的位元組可以忽略」。

    共用模組不結束行程：上述例外原樣拋出，是否中止由入口腳本決定。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    logger.debug("自 %s 讀出 %d 個字元", file_path, len(content))
    return content


def write_file(file_path, data):
    """把內容寫入檔案，覆蓋原有內容，回傳實際寫入的位元組數。

    data 為字串時以 UTF-8 編碼寫入；為 bytes 時原樣寫入二進位。兩種型別都收是
    因為呼叫端拿到的東西本來就兩種都有（文字報表 / 下載回來的檔案），而規則
    一句話講得完：字串當文字、bytes 當二進位。

    **覆蓋**既有檔案，不先問。理由是腳本必須可重入（見 openspec/specs/
    script-execution）：同樣的輸入重跑一次要得到同樣的結果，而不是第二次就因為
    「檔案已存在」而失敗。

    **不自動建立上層目錄**，目錄不存在時拋出 FileNotFoundError。自動建立會讓
    打錯的路徑靜默生出一棵沒人要的目錄樹，而使用者要等到「檔案怎麼不在我以為的
    地方」才發現。需要的話先呼叫 system_utils.create_folder()。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    if isinstance(data, bytes):
        with open(file_path, "wb") as handle:
            handle.write(data)
        written = len(data)
    elif isinstance(data, str):
        payload = data.encode("utf-8")
        with open(file_path, "wb") as handle:
            handle.write(payload)
        written = len(payload)
    else:
        raise ValueError("data 必須是字串或 bytes，收到 %s"
                         % type(data).__name__)

    logger.debug("寫入 %s，共 %d bytes", file_path, written)
    return written


def copy_file(source_path, target_path):
    """複製檔案，回傳複製後的絕對路徑。

    target_path 是**目的檔案的路徑**；若它是一個已存在的目錄，則複製進該目錄
    並沿用來源檔名（與 shutil 的慣例一致）。

    以 shutil.copy2 複製，連同修改時間與權限一併保留 —— 少了這些，複製出來的
    檔案在「比對哪份比較新」時會全部看起來像剛產生的。

    目的檔案已存在時**直接覆蓋**，與 write_file() 同一個理由：腳本要可重入，
    重跑不能因為「上一次已經複製過」而失敗。

    來源不存在、目的目錄不存在、來源與目的是同一個檔案，都以例外拋出
    （FileNotFoundError / shutil.SameFileError），由入口腳本決定怎麼回報。
    """
    for name, value in (("來源路徑", source_path), ("目的路徑", target_path)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s必須是非空字串：%r" % (name, value))

    if not os.path.isfile(source_path):
        # 先擋掉最常見的情況，錯誤訊息才指得出是哪一個路徑有問題 ——
        # 讓 shutil 自己去撞的話，訊息裡不會說那是「來源」還是「目的」。
        raise FileNotFoundError("來源檔案不存在：%s" % source_path)

    result = shutil.copy2(source_path, target_path)
    absolute = os.path.abspath(result)

    logger.debug("複製 %s -> %s", source_path, absolute)
    return absolute
