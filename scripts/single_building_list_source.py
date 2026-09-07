#!/usr/bin/env python3
"""Single Building —— 取得來源清單。

列出來源路徑該層目錄中的 .cpp 檔案（不遞迴），供使用者在畫面上挑選。

    python single_building_list_source.py --help
    python single_building_list_source.py --dump-config > run.json
    python single_building_list_source.py --request run.json
"""

import script_io
from script_utils import logger
from script_utils import single_building

TEMPLATE_VERSION = "2.0.0"
ACTION           = "list_source"
DESCRIPTION      = "列出來源路徑該層的 .cpp 檔案"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 這支腳本不需要任何自訂設定鍵：來源路徑走信封的 source_path，
        # 暫存設定檔的位置由 script_utils 決定。
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

    files = single_building.scan_cpp_files(source_path)

    logger.info("找到 %d 個 .cpp", len(files))

    # 找到 0 個是成功而非失敗 ——「這個目錄沒有 cpp」不是錯誤，
    # 回 FAIL 會讓使用者每次選到空目錄都看到一個錯誤訊息框。
    script_io.reply(
        message="找到 %d 個 .cpp 檔案" % len(files),
        detail="來源路徑：%s" % source_path,
        data={"files": files},
    )


if __name__ == "__main__":
    script_io.run(main)
