#!/usr/bin/env python3
"""Single Building 的功能專屬定義。

只有「這個功能自己的東西」放在這裡 —— 通用能力（掃描目錄、行式文字檔讀寫、
暫存檔路徑）都在 script_utils/ 之下（system_utils.py 與 file_utils.py），
任何功能都能用。

暫存設定檔的名稱在這裡決定一次，三支讀寫它的入口腳本共用。指不一致的症狀是
「寫進去讀不出來」，而且從任何一支腳本單獨看都毫無異狀。
"""

from script_utils import system_utils

__all__ = ["FEATURE_NAME", "FEATURE_VERSION",
           "SETTING_FILE_NAME", "SOURCE_SUFFIX", "setting_file_path"]

# 這個功能的名稱與版號。四支入口腳本共用這一份。
#
# 版號規則見 docs/contributing.md 的「版號」一節 —— 那裡是唯一的來源，這裡只放值。
#
# 這個功能的產出不會脫離產生它的環境（結果顯示在畫面上，看完就關掉），所以版號沒有一份
# 報告可以承載 —— 四支腳本因此在開始時把它記進診斷輸出，那是唯一看得到它的地方。
FEATURE_NAME = "Single Building"
FEATURE_VERSION = "v2.0.0"

SETTING_FILE_NAME = "PPS2_0DevTool_single_building.txt"

# 這個功能挑選的檔案類型。
SOURCE_SUFFIX = ".cpp"


def setting_file_path():
    """回傳暫存設定檔的絕對路徑。

    放在系統暫存目錄，重新開機後消失是預期行為。若日後需要跨重啟保留，
    改這一個函式即可（%LOCALAPPDATA% 是正確的去處）。
    """
    return system_utils.temp_file_path(SETTING_FILE_NAME)
