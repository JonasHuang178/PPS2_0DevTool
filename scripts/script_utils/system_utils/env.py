#!/usr/bin/env python3
"""環境變數。"""

import os

from script_utils import logger

__all__ = ["get_env_var"]


def get_env_var(var_name, default_value=None):
    """讀出環境變數 var_name，未設定時回傳 default_value。

    這是給**入口腳本**用的薄封裝。共用模組不得拿它來自行取得自己需要的
    設定 —— 那條規則（見 openspec/specs/script-envelope）沒有因為這個函式
    存在而鬆動：所需的值仍然由呼叫端明著傳入，讀環境變數是入口腳本的職責。
    典型用法是入口腳本讀 TOOLNAME / TOOLVERSION，再把值當參數傳下去。

    「未設定」涵蓋三種情況：變數不存在、值為空字串、值只有空白。三者對呼叫端
    而言是同一件事 —— 拿不到可用的值 —— 分開處理只會讓每個呼叫端各寫一次
    同樣的判斷。判定與 script_io 的必填檢查一致。

    值本身原樣回傳，不做 strip：要不要去掉前後空白由呼叫端決定，這裡代為
    修剪會讓「刻意帶空白的值」無法傳遞。

    var_name 不是非空字串時拋出 ValueError —— 共用模組不結束行程，是否要
    中止由入口腳本決定。
    """
    if not isinstance(var_name, str) or not var_name.strip():
        raise ValueError("環境變數名稱必須是非空字串：%r" % (var_name,))

    value = os.environ.get(var_name)

    # 只記名稱與有無，不記值 —— 環境變數是權杖與密碼最常見的傳遞方式，
    # 而 Debug_Mode 開啟時這行會出現在 console 上。
    if value is None or value.strip() == "":
        logger.debug("環境變數 %s 未設定，使用預設值", var_name)
        return default_value

    logger.debug("環境變數 %s 已設定", var_name)
    return value
