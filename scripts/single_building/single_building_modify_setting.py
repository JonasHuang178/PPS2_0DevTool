#!/usr/bin/env python3
"""Single Building —— 寫入設定。

把結果清單中的絕對路徑寫進暫存設定檔，覆蓋原有內容。

    python single_building_modify_setting.py --help
    python single_building_modify_setting.py --dump-config > run.json
    python single_building_modify_setting.py --request run.json
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
ACTION           = "modify_setting"
DESCRIPTION      = "把指定的檔案清單寫入暫存設定檔"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            # required=False：空清單是有效的設定（使用者什麼都沒選），
            # 標成必填會讓「清空後保存」這個正常操作被擋下來。
            script_io.arg("files", type=list, default=[],
                          help="要保存的絕對路徑清單，一個字串一筆"),
        ],
    )

    files = req["params"]["files"] or []
    path = single_building.setting_file_path()

    logger.info("寫入 %d 筆設定", len(files))
    script_io.progress("寫入設定…")

    written = system_utils.write_lines(path, files)

    logger.info("寫入完成：%s", path)

    script_io.reply(
        message="已保存 %d 筆設定" % written,
        detail="設定檔：%s" % path,
        data={"count": written},
    )


if __name__ == "__main__":
    script_io.run(main)
