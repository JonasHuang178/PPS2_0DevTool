#!/usr/bin/env python3
"""AI Analysis GitLab MR 的功能專屬定義。

只有「這個功能自己的東西」放在這裡 —— 通用能力（GitLab REST、檔案讀寫）都在
script_utils/ 之下，任何功能都能用。

這裡的三個 helper 服務同一件事：**讓同一支腳本同時服務 Qt 與 CI/CD 的 shell**。

    Qt   結果走信封的 data，內容直接放進下一步的 params。完全不碰檔案系統。
    CI   結果落檔，下一步以路徑讀進來。bash 的原生貨幣就是檔案。

因此每支腳本的契約是：
    輸出  data 一定有完整結果；params 給了 out_path 才**額外**落檔
    輸入  params 裡有內容就用內容；沒內容但有 <key>_path 就讀那個檔
"""

import json
import os

from script_utils import logger

__all__ = [
    "DEBUG_LOG_NAME",
    "write_artifact",
    "write_debug_log",
    "resolve_text_input",
    "resolve_json_input",
]

# 除錯目錄下的日誌檔名。debug_dir 為空字串時整個機制關閉。
DEBUG_LOG_NAME = "debug.log"


def write_artifact(out_path, content):
    """把內容寫到 out_path。out_path 為空就什麼都不做。

    回傳是否真的寫了檔案。

    「沒給路徑就不寫」是這個功能的核心行為之一：使用者沒有勾選產生除錯分析
    檔時，整條流程不應該在檔案系統留下任何東西。
    """
    if not out_path:
        return False

    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)

    directory = os.path.dirname(os.path.abspath(out_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(content)

    logger.debug("寫出產物 %s（%d 字元）", out_path, len(content))
    return True


def write_debug_log(debug_dir, message):
    """把一行訊息追加到除錯目錄下的日誌。debug_dir 為空就什麼都不做。

    「有效的目錄」本身就是「要不要寫」的開關 —— 不另外設一個布林參數，
    也就不會出現「開關為真但路徑為空」這種矛盾狀態。
    """
    if not debug_dir:
        return False

    if not os.path.isdir(debug_dir):
        os.makedirs(debug_dir, exist_ok=True)

    path = os.path.join(debug_dir, DEBUG_LOG_NAME)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(str(message) + "\n")
    return True


def _read_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def resolve_text_input(params, key):
    """取一段文字輸入：params[key] 有值就用它，否則讀 params[key + '_path']。

    兩者都沒有時回傳空字串 —— 缺漏由腳本自己的必填宣告負責擋，不在這裡。
    """
    value = params.get(key)
    if isinstance(value, str) and value.strip():
        return value

    path = params.get("%s_path" % key)
    if isinstance(path, str) and path.strip():
        logger.debug("自 %s 讀取 %s", path, key)
        return _read_file(path)

    return ""


def resolve_json_input(params, key):
    """同 resolve_text_input，但值是一個物件。"""
    value = params.get(key)
    if isinstance(value, dict) and value:
        return value

    path = params.get("%s_path" % key)
    if isinstance(path, str) and path.strip():
        logger.debug("自 %s 讀取 %s", path, key)
        return json.loads(_read_file(path))

    return {}
