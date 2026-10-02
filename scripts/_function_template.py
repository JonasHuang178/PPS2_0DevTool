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

五件必須遵守的事：

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

4. 不要整包 log 出 config。跨功能共用的憑證會被併進來，而 Debug_Mode 開啟時
   那一行會直接出現在 debug console 上。憑證優先走環境變數，log 時只印出
   你真正需要的那幾個鍵。

5. **每一個功能要宣告自己的腳本名稱與版號**，宣告在該功能的套件裡
   （`scripts/<功能>/__init__.py`），由該功能的所有入口腳本共用一份。
   版號兩碼、每改一次就把第二碼加一 —— 詳見底下那一段。
"""

import os
import sys

# 見上面第 1 點。這一行要在匯入 script_io / script_utils 之前執行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import script_io
from script_utils import logger

# --- 功能的名稱與版號 -------------------------------------------------------
#
# **真正的功能把這兩個放在 `scripts/<功能>/__init__.py`**，由該功能的所有入口腳本
# 匯入共用一份。這份範本不屬於任何功能，所以就地宣告示範。
#
# 版號兩碼：
#
#     2  .  0
#     │     └── 第二碼：任何修改都 +1，包含只改註解或診斷文字
#     └──────── 第一碼：重大修改才動，動的時候第二碼歸零
#
# 兩碼而不是三碼是刻意的：三碼的中間那一碼需要判斷「這算 minor 還是 patch」，而需要
# 判斷的規則就是會被漏掉的規則。兩碼沒有判斷餘地。
#
# 若這個功能有「由別人各自維護的實作層」（例如 AI Analysis 的 device 機制），那一層
# 要另外宣告自己的版號，而且**第一碼要與這裡一致** —— 讀的人一眼就看得出那份擴充是照
# 哪一代的契約寫的。
#
# 沒有任何機制強迫你更新它：忘了就是忘了，由開發者自負。不一致也不會讓執行失敗。
SCRIPT_NAME    = "Example Function"
SCRIPT_VERSION = "2.0"

# --- 改這三個常數 -----------------------------------------------------------
#
# TEMPLATE_VERSION 與上面的 SCRIPT_VERSION **是兩個不同的東西，不要搞混**：
# 它是**信封模板**的版本（請求與回應長什麼樣），全專案共用一個值，只有信封格式
# 本身改了才動。改你的功能不要動它。
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

    # 每一支入口腳本在開始時把功能名稱與版號記進診斷 —— 支援時問一句
    # 「console 第一行是什麼」就知道使用者手上跑的是哪一版。
    logger.info("%s %s", SCRIPT_NAME, SCRIPT_VERSION)

    cfg         = req["config"]
    source_path = req["source_path"]
    name        = req["params"]["example_name"]
    count       = req["params"]["example_count"]

    # 需要知道呼叫方是誰的腳本自己讀環境變數。
    # 命令列直接執行時不存在，所以一定要給預設值。
    tool_name = os.environ.get("TOOLNAME", "")

    logger.info("開始處理 %s（%d 筆）", name, count)          # -> stderr
    logger.debug("呼叫方 =%r，來源路徑 =%r", tool_name, source_path)

    # 不要整包印出 cfg。設定檔的 Service 區塊會被併進 config，裡面有權杖，
    # 而 Debug_Mode 開啟時這一行會出現在 console 上。只印你真正需要的鍵：
    #
    #     logger.debug("伺服器 =%r", cfg.get("Example_Server_URL"))

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
