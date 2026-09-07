#!/usr/bin/env python3
"""Single Building —— 寫入設定。

把結果清單中的絕對路徑寫進暫存設定檔，覆蓋原有內容。

    python single_building_modify_setting.py --help
    python single_building_modify_setting.py --dump-config > run.json
    python single_building_modify_setting.py --request run.json
"""

import script_io
from script_utils import logger
from script_utils import single_building

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

    logger.info("寫入 %d 筆設定", len(files))
    script_io.progress("寫入設定…")

    written = single_building.write_setting(files)
    path = single_building.setting_file_path()

    logger.info("寫入完成：%s", path)

    script_io.reply(
        message="已保存 %d 筆設定" % written,
        detail="設定檔：%s" % path,
        data={"count": written},
    )


if __name__ == "__main__":
    script_io.run(main)
