#!/usr/bin/env python3
"""Single Building —— 清空設定。

清空暫存設定檔的內容後回讀，回傳的清單因此必為空。

自己回讀而不是讓呼叫端再跑一次讀取設定的腳本：管線一次只能執行一支腳本，
少一次串接就少一次處理中對話框的開關。

    python single_building_recovery_setting.py --help
    python single_building_recovery_setting.py --dump-config > run.json
    python single_building_recovery_setting.py --request run.json
"""

import script_io
from script_utils import logger
from script_utils import single_building

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
    single_building.clear_setting()

    # 回讀而不是直接回傳空清單：讓回傳的內容真的來自檔案，
    # 清空沒生效時這裡就會顯示出來，而不是靜默地宣稱成功。
    files = single_building.read_setting()
    logger.info("清空後回讀 %d 筆", len(files))

    script_io.reply(
        message="設定已清空",
        detail="設定檔：%s" % path,
        data={"files": files},
    )


if __name__ == "__main__":
    script_io.run(main)
