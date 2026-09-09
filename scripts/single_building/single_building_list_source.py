#!/usr/bin/env python3
"""Single Building —— 取得來源清單。

列出來源路徑該層目錄中的 .cpp 檔案（不遞迴），供使用者在畫面上挑選。

    python single_building_list_source.py --help
    python single_building_list_source.py --dump-config > run.json
    python single_building_list_source.py --request run.json
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提：
# 命令列與 CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import script_io
import single_building
from script_utils import logger
from script_utils import system_utils

TEMPLATE_VERSION = "2.0.0"
ACTION           = "list_source"
DESCRIPTION      = "列出來源路徑該層的 .cpp 檔案"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 這支腳本不需要任何自訂設定鍵：來源路徑走信封的 source_path，
        # 暫存設定檔的位置由 single_building 套件決定。
        config=[],

        # 也不需要參數 —— 要掃哪裡完全由 source_path 決定。
        params=[],
    )

    source_path = req["source_path"]
    if not source_path:
        # Qt 端在來源路徑為空時根本不會呼叫這支腳本，但命令列使用者會。
        script_io.reply_fail("未指定來源路徑", code="SOURCE_PATH_EMPTY")

    logger.info("掃描來源路徑：%s", source_path)
    script_io.progress("掃描來源路徑…")

    files = system_utils.list_files_by_suffix(source_path,
                                              single_building.SOURCE_SUFFIX)

    logger.info("找到 %d 個 %s", len(files), single_building.SOURCE_SUFFIX)

    # 找到 0 個是成功而非失敗 ——「這個目錄沒有 cpp」不是錯誤，
    # 回 FAIL 會讓使用者每次選到空目錄都看到一個錯誤訊息框。
    script_io.reply(
        message="找到 %d 個 %s 檔案" % (len(files), single_building.SOURCE_SUFFIX),
        detail="來源路徑：%s" % source_path,
        data={"files": files},
    )


if __name__ == "__main__":
    script_io.run(main)
