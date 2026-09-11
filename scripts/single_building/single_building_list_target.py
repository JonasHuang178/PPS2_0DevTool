#!/usr/bin/env python3
"""Single Building —— 讀取設定。

讀出暫存設定檔中的絕對路徑，填入畫面的結果清單。

    python single_building_list_target.py --help
    python single_building_list_target.py --dump-config > run.json
    python single_building_list_target.py --request run.json
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提：
# 命令列與 CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os

import script_io
import single_building
from script_utils import logger
from script_utils import system_utils

TEMPLATE_VERSION = "2.0.0"
ACTION           = "list_target"
DESCRIPTION      = "讀出暫存設定檔中已保存的檔案清單"


def main():
    script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[],
    )

    path = single_building.setting_file_path()
    logger.info("讀取設定檔：%s", path)
    script_io.progress("讀取設定…")

    # 設定檔存的是絕對路徑；畫面顯示的是檔名，因此兩者一起回傳。
    files = [{"name": os.path.basename(line), "path": line}
             for line in system_utils.read_lines(path)]

    logger.info("讀出 %d 筆", len(files))

    # 檔案不存在或內容為空都是「設定為空」，不是錯誤 ——
    # 第一次使用時檔案本來就還不存在。
    script_io.reply(
        message="讀出 %d 筆已保存的設定" % len(files),
        detail="設定檔：%s" % path,
        data={"files": files},
    )


if __name__ == "__main__":
    script_io.run(main)
