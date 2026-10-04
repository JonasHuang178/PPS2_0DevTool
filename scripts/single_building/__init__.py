#!/usr/bin/env python3
"""Single Building 的功能專屬定義。

只有「這個功能自己的東西」放在這裡 —— 通用能力（掃描目錄、行式文字檔讀寫、
暫存檔路徑）都在 script_utils/ 之下（system_utils.py 與 file_utils.py），
任何功能都能用。

暫存設定檔的名稱在這裡決定一次，三支讀寫它的入口腳本共用。指不一致的症狀是
「寫進去讀不出來」，而且從任何一支腳本單獨看都毫無異狀。
"""

from script_utils import system_utils

__all__ = ["SCRIPT_NAME", "SCRIPT_VERSION",
           "SETTING_FILE_NAME", "SOURCE_SUFFIX", "setting_file_path"]

# 這個功能的名稱與版號。四支入口腳本共用這一份。
#
# 版號兩碼：第一碼留給重大修改，第二碼是修改計數。**這個功能每改一次就把第二碼加一**
# ——包含只改註解或診斷文字；第一碼更新時第二碼歸零。沒有判斷餘地是刻意的：需要判斷
# 「這算大改還是小改」的規則，就是會被漏掉的規則。
#
# **不要與 TEMPLATE_VERSION 搞混。** 那一個是信封模板的版本，說的是請求與回應長什麼樣，
# 全專案共用一個值（Single Building、AI Analysis 與功能範本都是 2.0.0），只有信封格式
# 本身改了才動。拿它來當這個功能的版號，它就會隨這個功能一直往上跳而其他功能停著不動,
# 兩個本該代表同一份格式的數字於是分岔 —— 而它還會被 --dump-config 印出去給呼叫端看。
#
# 這個功能的產出不會脫離產生它的環境（結果顯示在畫面上，看完就關掉），所以版號沒有一份
# 報告可以承載 —— 四支腳本因此在開始時把它記進診斷輸出，那是唯一看得到它的地方。
SCRIPT_NAME = "Single Building"
SCRIPT_VERSION = "2.0"

SETTING_FILE_NAME = "PPS2_0DevTool_single_building.txt"

# 這個功能挑選的檔案類型。
SOURCE_SUFFIX = ".cpp"


def setting_file_path():
    """回傳暫存設定檔的絕對路徑。

    放在系統暫存目錄，重新開機後消失是預期行為。若日後需要跨重啟保留，
    改這一個函式即可（%LOCALAPPDATA% 是正確的去處）。
    """
    return system_utils.temp_file_path(SETTING_FILE_NAME)
