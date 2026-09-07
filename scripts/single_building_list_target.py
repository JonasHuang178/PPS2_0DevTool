#!/usr/bin/env python3
"""Single Building —— 讀取設定。

讀出暫存設定檔中的絕對路徑，填入畫面的結果清單。

    python single_building_list_target.py --help
    python single_building_list_target.py --dump-config > run.json
    python single_building_list_target.py --request run.json
"""

import script_io
from script_utils import logger
from script_utils import single_building

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

    files = single_building.read_setting()

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
