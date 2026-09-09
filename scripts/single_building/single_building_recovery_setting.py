#!/usr/bin/env python3
"""Single Building —— 清空設定。

清空暫存設定檔的內容後回讀，回傳的清單因此必為空。

自己回讀而不是讓呼叫端再跑一次讀取設定的腳本：管線一次只能執行一支腳本，
少一次串接就少一次處理中對話框的開關。

    python single_building_recovery_setting.py --help
    python single_building_recovery_setting.py --dump-config > run.json
    python single_building_recovery_setting.py --request run.json
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
ACTION           = "recovery_setting"
DESCRIPTION      = "清空暫存設定檔後回讀其內容"


def main():
    script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[],
    )

    path = single_building.setting_file_path()

    logger.info("清空設定檔：%s", path)
    script_io.progress("清空設定…")
    system_utils.write_lines(path, [])

    # 回讀而不是直接回傳空清單：讓回傳的內容真的來自檔案，
    # 清空沒生效時這裡就會顯示出來，而不是靜默地宣稱成功。
    files = [{"name": os.path.basename(line), "path": line}
             for line in system_utils.read_lines(path)]
    logger.info("清空後回讀 %d 筆", len(files))

    script_io.reply(
        message="設定已清空",
        detail="設定檔：%s" % path,
        data={"files": files},
    )


if __name__ == "__main__":
    script_io.run(main)
