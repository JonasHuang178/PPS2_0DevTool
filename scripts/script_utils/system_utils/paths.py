#!/usr/bin/env python3
"""路徑字串的表示法轉換。

這裡的函式**不碰檔案系統**，也不看自己跑在哪個作業系統上：純粹是字串轉換，
在 Windows 與 Linux 上得到完全相同的結果。腳本在 Linux 或 CI 上被直接執行、
而處理的是 Windows 風格的 `source_path`，是本專案明確支援的用法。

注意這不是「自行串接分隔符號」的許可（見 openspec/specs/script-envelope 的
跨平台要求）：組路徑一律用 os.path.join，只有在**確定要輸出成 Windows 樣子**
的那一刻才呼叫這裡 —— 寫進給 Windows 工具吃的檔案、或顯示給使用者看。
"""

import re

__all__ = ["to_windows_path_format"]


# 兩種分隔符號都收：來源可能是 Qt、Python、設定檔或使用者手打，混用很常見。
_SEPARATOR_RUN = re.compile(r"[\\/]+")


def to_windows_path_format(path_string):
    """把路徑字串轉成 Windows 表示法：分隔符號一律為反斜線。

    連續的分隔符號收斂成一個，但**開頭的兩個保留**（`\\\\server\\share` 的
    UNC 路徑與 `\\\\?\\C:\\...` 的長路徑前綴都靠那兩個反斜線辨識，收斂掉就
    指向別的地方了）。

    結尾的分隔符號保留（只收斂成一個）：`C:\\proj\\` 與 `C:\\proj` 在某些
    Windows 工具眼中是不同的輸入，代為刪掉會改變呼叫端的意思。

    相對路徑**不會**被轉成絕對路徑。在 Linux 上執行時，「絕對化」只能以
    Linux 的當前目錄為基準，那對一個要交給 Windows 用的路徑毫無意義。

    空字串原樣回傳，不視為錯誤 —— 信封的 `source_path` 允許為空，這裡
    拋例外的話每個呼叫端都得先寫一次 if。

    path_string 不是字串時拋出 ValueError。
    """
    if not isinstance(path_string, str):
        raise ValueError("路徑必須是字串：%r" % (path_string,))

    if not path_string:
        return ""

    leading = ""
    body = path_string

    match = _SEPARATOR_RUN.match(path_string)
    if match:
        # 開頭兩個以上 = UNC 或長路徑前綴，保留兩個；單一個就是根目錄。
        leading = "\\\\" if len(match.group(0)) >= 2 else "\\"
        body = path_string[match.end():]

    return leading + _SEPARATOR_RUN.sub(r"\\", body)
