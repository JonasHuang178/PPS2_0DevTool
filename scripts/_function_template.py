#!/usr/bin/env python3
"""功能腳本範本 —— 複製這個檔案開始寫新腳本。

這份範本留在 scripts/ 這一層（不屬於任何功能）。複製到 scripts/<功能>/
底下再改，原樣就能執行：

    python _function_template.py --help
    python _function_template.py --dump-config > run.json
    python _function_template.py --request run.json
    echo '{"action":"example_action","params":{"example_name":"x"}}' \
        | python _function_template.py --request-stdin

要寫新腳本，改三個常數、列出 config / params、填實作區就完成了。

三件必須遵守的事：

1. 入口腳本放在 scripts/<功能>/ 底下，同一個功能的腳本收在一起。因為放進
   了子目錄，**底下那段 sys.path 設定不能刪** —— Python 只把「腳本所在目錄」
   放進 sys.path，少了它，命令列直接執行時 script_io 與 script_utils 都匯
   不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但別把那當成前提：命令列與
   CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。

2. 業務邏輯寫在 script_utils/ 裡，這支腳本只做轉接（收信封 → 呼叫
   script_utils → 回信封）。「給別人用」的正確介面是 script_utils，
   不是腳本。

   script_utils/ 依**技術領域**分組（system_utils、gitlab_utils…），不依
   應用功能分組 —— 依功能分組的話，第二個功能需要同一個能力時就無處可放。
   只服務單一功能的東西留在 scripts/<功能>/ 之下。

3. 只有結果 JSON 可以印到 stdout。診斷訊息用 logger（走 stderr）。
"""

import os
import sys

# 見上面第 1 點。這一行要在匯入 script_io / script_utils 之前執行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import script_io
from script_utils import logger

# --- 改這三個常數 -----------------------------------------------------------

TEMPLATE_VERSION = "2.0.0"
ACTION           = "example_action"
DESCRIPTION      = "範本腳本：示範信封的收送方式"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 這支腳本需要哪些設定鍵。Qt 會從 PPS2_0DevTool.json 的
        # Function/<功能名> 區塊挖出來放進信封的 config。
        # required=True 的缺漏會在進入業務邏輯之前就被擋下來。
        config=[
            script_io.cfg("Example_Server_URL", required=False,
                          help="範例設定鍵；實際腳本改成自己需要的鍵"),
        ],

        # 這支腳本需要哪些參數。宣告一次，同時產生 --help 的說明與
        # --dump-config 的模板 —— 不要另外寫死一份模板，它一定會漂移。
        params=[
            script_io.arg("example_name", required=True,
                          help="範例參數，字串"),
            script_io.arg("example_count", type=int, default=3,
                          help="範例參數，整數，預設 3"),
        ],
    )

    cfg         = req["config"]
    source_path = req["source_path"]
    name        = req["params"]["example_name"]
    count       = req["params"]["example_count"]

    # 需要知道呼叫方是誰的腳本自己讀環境變數。
    # 命令列直接執行時不存在，所以一定要給預設值。
    tool_name = os.environ.get("TOOLNAME", "")

    logger.info("開始處理 %s（%d 筆）", name, count)          # -> stderr
    logger.debug("呼叫方 =%r，來源路徑 =%r，設定 =%r",
                 tool_name, source_path, cfg)                  # -v 才會出現

    # ---- 實作區：呼叫 script_utils，拿回資料結構 ----
    items = []
    for index in range(count):
        # 進度自己節流：跑幾千筆時不要每筆都報，每 1% 或每 N 筆一次就好。
        script_io.progress("處理中 (%d/%d)" % (index + 1, count))
        items.append({"index": index, "name": name})
    # ------------------------------------------------

    logger.info("處理完成")

    script_io.reply(
        message="完成，共 %d 筆" % count,
        detail="來源路徑：%s\n呼叫方：%s" % (source_path or "(未指定)",
                                            tool_name or "(命令列)"),
        data={"items": items},
    )


if __name__ == "__main__":
    # 統一的錯誤處理：未攔截的例外 -> {"result":"FAIL",...} + exit 1
    script_io.run(main)
