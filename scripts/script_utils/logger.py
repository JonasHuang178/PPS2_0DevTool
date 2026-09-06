#!/usr/bin/env python3
"""給 script_utils 與入口腳本共用的 log 工具。

這是**唯一**設定 logging 的地方。每個模組自行 import 使用，不要在別處
呼叫 logging.basicConfig() —— 兩邊各設一次會造成訊息重複輸出。

全部等級一律走 stderr，包含 DEBUG —— stdout 已經被結果佔用，
任何一行 log 進去都會讓 Qt 端的整段 parse 失敗。

格式對齊 Qt 端的 debug.h，兩邊的訊息會出現在同一個 debug console：

    [2026-09-06 14:30:12.345] [ QT DEBUG ] 來自 Qt
    [2026-09-06 14:30:12.352] [ PY DEBUG ] 來自 Python
"""

import datetime
import logging
import sys

__all__ = ["debug", "info", "warn", "error", "set_verbose", "is_verbose"]


class AlignedFormatter(logging.Formatter):
    """等級名稱補成固定寬度 10，對齊 Qt 端 debug.h 的樣子。"""

    LEVEL_NAMES = {
        logging.DEBUG:    " PY DEBUG ",
        logging.INFO:     " PY INFO  ",
        logging.WARNING:  " PY WARN  ",
        logging.ERROR:    " PY ERROR ",
        logging.CRITICAL: " PY FATAL ",
    }

    def formatTime(self, record, datefmt=None):
        # 覆寫 formatTime 而不是在 format() 裡塞 record.asctime：
        # Formatter.format() 在 usesTime() 為真時會自己呼叫 formatTime，
        # 先設好的 asctime 會被覆蓋掉。
        stamp = datetime.datetime.fromtimestamp(record.created)
        return stamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def format(self, record):
        original = record.levelname
        record.levelname = self.LEVEL_NAMES.get(record.levelno, original)
        try:
            return super(AlignedFormatter, self).format(record)
        finally:
            record.levelname = original


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"

_logger = logging.getLogger("pps")
_logger.setLevel(logging.INFO)      # 預設 INFO；-v 時由 script_io 打開 DEBUG
_logger.propagate = False           # 避免與 root logger 重複輸出

# handler 在模組載入時建立一次，所以不管被 import 幾次都只有一份。
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)    # 一律 stderr
    _handler.setFormatter(AlignedFormatter(LOG_FORMAT))
    _logger.addHandler(_handler)


def set_verbose(verbose):
    """打開或關閉 DEBUG。由 script_io 在收到 -v 時呼叫。"""
    _logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def is_verbose():
    return _logger.isEnabledFor(logging.DEBUG)


# 用 %s 佔位傳參數，不要自己組字串 —— 等級沒開啟時就不會付出格式化的成本：
#     logger.debug("讀取 %s", path)      # ✓
#     logger.debug(f"讀取 {path}")       # ✗ 不論如何都會先組好字串

def debug(msg, *args):
    _logger.debug(msg, *args)


def info(msg, *args):
    _logger.info(msg, *args)


def warn(msg, *args):
    _logger.warning(msg, *args)


def error(msg, *args):
    _logger.error(msg, *args)
