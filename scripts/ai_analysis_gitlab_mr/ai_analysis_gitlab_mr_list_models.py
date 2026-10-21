#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 列出每一個 AI provider 項目對應的模型名稱。

工具每次啟動後**第一次**進入本功能時執行一次，結果用來把選單的每一項顯示成
`provider / 模型名稱`。分析本身不靠它 —— 步驟 3 會在分析當下自己再查一次，報告出處印
的是那一次的值。

    python ai_analysis_gitlab_mr_list_models.py --help
    python ai_analysis_gitlab_mr_list_models.py --dump-config > run.json
    python ai_analysis_gitlab_mr_list_models.py --request run.json

連線字串與金鑰走 params（與步驟 3 相同的理由：它們隨設定項目而變），所以會落在請求
檔裡；從命令列跑的話用完就刪。

拆連線字串、組清單網址、比對 shareCode 都用 ai_utils —— 與步驟 3 同一份規則。

**個別項目查不到不算失敗**：該項的 model 是空字串，其餘照常。整支腳本只在參數形狀不對
時失敗。
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提：
# 命令列與 CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import ai_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "list_models"
DESCRIPTION      = "列出每一個 AI provider 項目對應的模型名稱"


def _entries(raw):
    """把 modes 參數正規化成 [(connection, api_key), ...]；形狀不對時回報失敗。

    型別不交給 script_io 的轉換：list("abc") 會把一個誤傳的字串拆成三個字元，然後
    安靜地查三次。
    """
    if not isinstance(raw, list):
        script_io.reply_fail("參數 modes 必須是陣列，收到的是 %s" % type(raw).__name__)

    entries = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            script_io.reply_fail("參數 modes 的第 %d 項必須是物件，收到的是 %s"
                                 % (index + 1, type(item).__name__))
        entries.append((ai_analysis_gitlab_mr.plain(item.get("connection")),
                        ai_analysis_gitlab_mr.plain(item.get("api_key"))))
    return entries


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            script_io.arg("modes", type=None, required=True,
                          help="[{connection, api_key}, ...]，順序即回傳的順序；"
                               "connection 是 provider:端點:shareCode"),
        ],
    )

    entries = _entries(req["params"]["modes"])
    verify_ssl = ai_analysis_gitlab_mr.ai_verify_ssl()

    # 先全部拆好、組出清單網址，再依 (清單網址, 金鑰) 分組 —— 同一個服務底下的數個項目
    # 查的是同一份清單，每一項各問一次只是讓使用者多等。
    parsed = []
    groups = {}
    for connection, api_key in entries:
        provider, url, share_code = ai_utils.split_connection(connection)
        list_url = ai_utils.model_list_url(url)
        parsed.append((provider, share_code, list_url, api_key))
        if list_url:
            groups.setdefault((list_url, api_key), None)

    for index, (list_url, api_key) in enumerate(groups, start=1):
        script_io.progress("查詢模型清單 (%d/%d)…" % (index, len(groups)))
        groups[(list_url, api_key)] = ai_utils.fetch_model_list(
            list_url, api_key=api_key, verify_ssl=verify_ssl)

    modes = []
    for provider, share_code, list_url, api_key in parsed:
        models = groups.get((list_url, api_key)) if list_url else None
        model = ai_utils.find_model(models, share_code) if models is not None else ""
        modes.append({"provider": provider, "model": model})

    found = sum(1 for one in modes if one["model"])
    logger.info("列出模型：%d 項，查得 %d 項，送出 %d 次查詢",
                len(modes), found, len(groups))

    script_io.reply(
        message="查得 %d / %d 項的模型名稱" % (found, len(modes)),
        data={"modes": modes},
    )


if __name__ == "__main__":
    # 統一的錯誤處理：未攔截的例外 -> {"result":"FAIL",...} + exit 1
    script_io.run(main)
