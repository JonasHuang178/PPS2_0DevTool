#!/usr/bin/env python3
"""JSON 的讀寫與序列化。

與 file_utils 的分工：file_utils 處理**任意檔案內容**（字串、位元組、行），
這裡處理**已經是 JSON 的東西** —— 解析、序列化，以及它們各自的錯誤該怎麼講。

注意 write_file() 在這裡與 file_utils 同名。呼叫端一律以模組名限定
（json_utils.write_file / file_utils.write_file），因此不會撞在一起，但讀 code
時要看一眼 import 才知道是哪一個。

與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）：不印任何東西
到 stdout、不結束行程、不自行讀取設定檔或環境變數、回傳資料結構。
"""

import json
import os
import tempfile

from script_utils import logger

__all__ = ["read_data", "write_file", "dump"]


# 縮排 2 格：與 script_io 傾印的請求模板一致，也是多數人讀 JSON 時的預期。
DEFAULT_INDENT = 2


def read_data(file_path):
    """讀出 JSON 檔案，回傳對應的 Python 資料結構（dict / list / 純量）。

    檔案不存在時拋 FileNotFoundError，與 file_utils.read_file() 一致。

    **內容不是合法 JSON 時，錯誤訊息會帶上檔案路徑與出錯的行列位置。**
    json 標準函式庫的訊息只說「Expecting ',' delimiter: line 12 column 5」，
    不會提到是哪一個檔案 —— 一次讀好幾個設定檔時，那句話等於沒說。

    空檔案也算格式錯誤，訊息會明講「檔案是空的」。把空檔當成 {} 是猜測，而猜錯
    的那次會讓呼叫端拿著空設定一路跑下去，直到很後面才發現什麼都沒讀到。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    with open(file_path, "r", encoding="utf-8") as handle:
        raw = handle.read()

    if not raw.strip():
        raise ValueError("JSON 檔案是空的：%s" % file_path)

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("JSON 格式錯誤（%s）：%s" % (file_path, exc))

    logger.debug("自 %s 讀出 JSON（%s）", file_path, type(data).__name__)
    return data


def write_file(file_path, data, indent=DEFAULT_INDENT):
    """把資料序列化成 JSON 寫入檔案，回傳寫入的位元組數。

    indent 傳 None 得到單行的緊湊格式。

    **中文不會被轉成 \\uXXXX**（ensure_ascii=False）。轉義過的檔案人是讀不了的，
    而這個專案的設定檔與報表裡到處都是中文。

    檔尾補一個換行：少了它，git diff 會在每次修改時多報一行「\\ No newline at
    end of file」，而多數編輯器也會自動補上，於是檔案在誰存過之後就無謂地變動。

    寫入採「先寫暫存檔再原子置換」，與 file_utils.replace_lines() 相同。這一點
    與 file_utils.write_file() 刻意不同：寫到一半的純文字檔仍然是可讀的文字，
    寫到一半的 JSON 則**完全無法解析** —— 原本好好的設定檔會因為一次中斷而整個
    報廢。暫存檔建在同一個目錄，跨檔案系統時 os.replace 不是原子操作。

    data 含無法序列化的物件時，json 會拋出 TypeError 並指出型別，原樣往上拋。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    payload = dump(data, indent=indent) + "\n"
    encoded = payload.encode("utf-8")

    folder = os.path.dirname(os.path.abspath(file_path))
    handle_fd, temp_path = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "wb") as temp:
            temp.write(encoded)
        os.replace(temp_path, file_path)
    except BaseException:
        # 失敗時不要留下暫存垃圾；原檔此時尚未被動過。
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    logger.debug("寫入 JSON 至 %s，共 %d bytes", file_path, len(encoded))
    return len(encoded)


def dump(data, indent=DEFAULT_INDENT):
    """把資料序列化成 JSON 字串。

    indent 傳 None 得到單行的緊湊格式（要塞進 log 或單行訊息時用）。

    中文原樣保留，不轉成 \\uXXXX，理由同 write_file()。

    鍵的次序**原樣保留、不排序**：dict 的插入次序通常有意義（設定檔的欄位順序、
    腳本組出來的報表欄位），排序會把那個意圖洗掉。需要穩定次序的呼叫端自己先
    整理好再傳進來。

    無法序列化的物件會讓 json 拋出 TypeError 並指出型別，原樣往上拋 —— 共用模組
    不替呼叫端決定「不認得的東西就轉成字串」，那會把一個該修的錯誤藏起來。
    """
    return json.dumps(data, ensure_ascii=False, indent=indent)
